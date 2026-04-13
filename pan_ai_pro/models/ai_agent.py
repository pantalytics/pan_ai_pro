# -*- coding: utf-8 -*-
"""Extend ai.agent with web search toggle and streaming for Anthropic."""
import copy
import logging
import time

from odoo import fields, models
from odoo.tools import html_sanitize

from odoo.addons.ai.models.ai_agent import TEMPERATURE_MAP
from odoo.addons.ai.utils.llm_api_service import LLMApiService
from odoo.addons.ai.utils.ai_logging import ai_response_logging, get_ai_logging_session
from odoo.addons.mail.tools.discuss import Store

try:
    from markdown2 import markdown as md_convert
except ImportError:
    md_convert = None

_logger = logging.getLogger(__name__)

# Minimum interval between bus updates during streaming (seconds)
_STREAM_THROTTLE = 0.15


def _markdown_to_html(text):
    """Convert markdown to HTML using markdown2."""
    if not text:
        return ""
    if md_convert:
        return md_convert(text, extras=['fenced-code-blocks', 'tables', 'strike'])
    return html_sanitize(text)


class AIAgent(models.Model):
    _inherit = 'ai.agent'

    x_web_search = fields.Boolean(
        string="Web Search",
        default=False,
        help="Allow this agent to search the web for current information. "
             "Currently supported for Anthropic Claude models only.",
    )

    def _post_ai_response(self, channel, message):
        """Convert markdown to HTML before posting."""
        formatted = html_sanitize(_markdown_to_html(message))
        channel.sudo().message_post(
            author_id=self.partner_id.id,
            body=formatted,
            message_type='comment',
            silent=True,
            subtype_xmlid='mail.mt_comment',
        )

    def _generate_response_for_channel(self, mail_message, channel):
        """Override to stream Anthropic responses token-by-token."""
        self.ensure_one()
        if self._get_provider() != 'anthropic':
            return super()._generate_response_for_channel(mail_message, channel)

        prompt, session_info_context = self._parse_user_message(mail_message)
        agent = self.with_context(discuss_channel=channel)

        try:
            self._generate_response_streaming(
                agent, channel, prompt, session_info_context)
        except Exception:
            if self.env.user._is_internal():
                raise
            self._post_ai_response(
                channel, self.env._("Oops, it looks like our AI is unreachable"))

    def _generate_response_streaming(self, agent, channel, prompt, session_info_context):
        """Stream an Anthropic response into a discuss channel message."""
        system_messages = agent._build_system_context(
            extra_system_context=agent._build_extra_system_context(channel))
        if rag_context := agent._build_rag_context(prompt):
            system_messages.extend(rag_context)

        chat_history = (
            [{'content': session_info_context, 'role': 'user'}]
            + agent._retrieve_chat_history(channel)
        )

        llm = LLMApiService(env=self.env, provider='anthropic')
        tools = agent.topic_ids.tool_ids._get_ai_tools()
        temperature = TEMPERATURE_MAP[agent.response_style]
        web_grounding = agent.x_web_search

        # Build Anthropic request body (reuse logic from _request_llm_anthropic)
        messages = list(chat_history) + [{'role': 'user', 'content': prompt}]
        body = {
            "model": agent.llm_model,
            "max_tokens": 4096,
            "temperature": temperature,
            "messages": messages,
        }
        if system_messages:
            body["system"] = "\n\n".join(system_messages)
        if tools:
            body["tools"] = [{
                "name": name,
                "description": desc,
                "input_schema": schema,
            } for name, (desc, __, __, schema) in tools.items()]
        if web_grounding:
            body.setdefault("tools", []).append({
                'type': 'web_search_20250305',
                'name': 'web_search',
                'max_uses': 5,
            })
        headers = {
            "Content-Type": "application/json",
            "x-api-key": llm._get_api_token(),
            "anthropic-version": "2023-06-01",
        }

        # Create placeholder message
        placeholder = channel.sudo().message_post(
            author_id=agent.partner_id.id,
            body="",
            message_type='comment',
            silent=True,
            subtype_xmlid='mail.mt_comment',
        )
        self.env.cr.commit()

        last_update = [0.0]

        def on_token(accumulated_text):
            now = time.monotonic()
            if now - last_update[0] < _STREAM_THROTTLE:
                return
            last_update[0] = now
            html_body = html_sanitize(_markdown_to_html(accumulated_text))
            placeholder.sudo().write({'body': html_body})
            Store(bus_channel=channel).add(placeholder, ["body"]).bus_send()
            self.env.cr.commit()

        max_calls = int(self.env["ir.config_parameter"].sudo().get_param(
            "ai.max_successive_calls", "20"))
        max_tools_per_call = int(self.env["ir.config_parameter"].sudo().get_param(
            "ai.max_tool_calls_per_call", "20"))

        all_responses = []

        with ai_response_logging(agent.llm_model):
            for api_call in range(max_calls):
                stream_body = copy.deepcopy(body)
                response, to_call, next_inputs = llm._request_llm_anthropic_stream(
                    stream_body, headers, on_token=on_token)
                all_responses.extend(response)

                if not to_call:
                    break

                # Execute tool calls (non-streaming)
                session = get_ai_logging_session()
                if session:
                    session["tool_calls"] += min(len(to_call), max_tools_per_call)

                done = False
                for i, (tool_name, call_id, arguments) in enumerate(to_call):
                    if i >= max_tools_per_call:
                        next_inputs.append(llm._build_tool_call_response(
                            call_id, "Error: tool call limit reached"))
                        continue
                    if tool_name not in tools:
                        next_inputs.append(llm._build_tool_call_response(
                            call_id, f"Error: unknown tool '{tool_name}'"))
                        continue

                    has_end = "__end_message" in arguments
                    end_msg = arguments.pop("__end_message", None)
                    result, error = tools[tool_name][2](arguments=arguments)
                    next_inputs.append(llm._build_tool_call_response(call_id, result))

                    if has_end and error is None:
                        done = True
                        if end_msg and end_msg.strip():
                            all_responses.append(end_msg.strip())

                if done:
                    break

                # Add tool call history to messages for next iteration
                body["messages"].extend(next_inputs)

        # Final update with complete response
        if all_responses:
            final_text = "\n\n".join(all_responses)
            if rag_context:
                final_text = agent._get_llm_response_with_sources([final_text])[0]
            final_html = html_sanitize(_markdown_to_html(final_text))
            placeholder.sudo().write({'body': final_html})
            Store(bus_channel=channel).add(placeholder, ["body"]).bus_send()
            self.env.cr.commit()

    def _generate_response(self, prompt, chat_history=None, extra_system_context=""):
        """Override for web search (non-streaming path, used by non-channel callers)."""
        self.ensure_one()
        if self.x_web_search and self._get_provider() == 'anthropic':
            _logger.debug("[AI Pro] Using web search for agent %s", self.name)
            system_messages = self._build_system_context(extra_system_context=extra_system_context)
            if rag_context := self._build_rag_context(prompt):
                system_messages.extend(rag_context)
            llm_response = LLMApiService(env=self.env, provider=self._get_provider()).request_llm(
                self.llm_model,
                system_messages,
                [],
                inputs=(chat_history or []) + [{'role': 'user', 'content': prompt}],
                tools=self.topic_ids.tool_ids._get_ai_tools(),
                temperature=TEMPERATURE_MAP[self.response_style],
                web_grounding=True,
            )
            if rag_context:
                llm_response = self._get_llm_response_with_sources(llm_response)
            return llm_response
        return super()._generate_response(prompt, chat_history=chat_history, extra_system_context=extra_system_context)
