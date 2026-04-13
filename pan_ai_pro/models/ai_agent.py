# -*- coding: utf-8 -*-
"""Extend ai.agent with web search toggle and streaming for all providers."""
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
    x_code_execution = fields.Boolean(
        string="Code Execution",
        default=False,
        help="Allow this agent to run Python code for calculations, data parsing, "
             "and visualizations. Currently supported for Anthropic Claude models only.",
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
        """Override to stream responses token-by-token for all providers."""
        self.ensure_one()
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

    # --- Provider-specific body builders ---

    def _build_stream_request_anthropic(self, agent, system_messages, chat_history,
                                        prompt, tools, temperature, web_grounding,
                                        code_execution=False):
        """Build Anthropic Messages API request body and headers."""
        llm = LLMApiService(env=self.env, provider='anthropic')
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
        if code_execution:
            body.setdefault("tools", []).append({
                'type': 'code_execution_20250825',
                'name': 'code_execution',
            })
        headers = {
            "Content-Type": "application/json",
            "x-api-key": llm._get_api_token(),
            "anthropic-version": "2023-06-01",
        }
        return llm, body, headers

    def _build_stream_request_openai(self, agent, system_messages, chat_history,
                                     prompt, tools, temperature, web_grounding):
        """Build OpenAI Responses API request body."""
        llm = LLMApiService(env=self.env, provider='openai')
        user_content = [{"type": "input_text", "text": prompt}]
        body = {
            "model": agent.llm_model,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": p} for p in system_messages],
                },
                {"role": "user", "content": user_content},
                *chat_history,
            ],
            "store": False,
        }
        if agent.llm_model not in ('gpt-5', 'gpt-5-mini'):
            body["temperature"] = temperature
        if tools:
            body["tools"] = llm._to_open_ai_tool_schema([{
                "description": desc,
                "parameters": schema,
                "type": "function",
                "name": name,
                "strict": True,
            } for name, (desc, __, __, schema) in tools.items()])
            body["parallel_tool_calls"] = True
        if web_grounding:
            search_tool = {'type': 'web_search_preview'}
            if country_code := self.env.company.country_id.code:
                search_tool['user_location'] = {'type': 'approximate', 'country': country_code}
                if city := self.env.company.city:
                    search_tool['user_location']['city'] = city
            body.setdefault("tools", []).append(search_tool)
        return llm, body, None

    def _build_stream_request_google(self, agent, system_messages, chat_history,
                                     prompt, tools, temperature, web_grounding):
        """Build Google Gemini API request body."""
        llm = LLMApiService(env=self.env, provider='google')
        # Convert OpenAI-style chat history to Gemini format
        gemini_history = [
            {"role": "user" if m["role"] == "user" else "model",
             "parts": [{"text": m["content"]}]}
            for m in chat_history if isinstance(m, dict) and "content" in m
        ]
        body = {
            "contents": gemini_history + [
                {"role": "user", "parts": [{"text": prompt}]},
            ],
            "generationConfig": {"temperature": temperature},
        }
        if system_messages:
            body["systemInstruction"] = {
                "parts": [{"text": p} for p in system_messages],
            }
        if tools:
            body["tools"] = {
                "functionDeclarations": [{
                    "description": desc,
                    "parameters": schema,
                    "name": name,
                } for name, (desc, __, __, schema) in tools.items()]
            }
        if web_grounding:
            body["tools"] = {'google_search': {}}
        return llm, body, None

    def _stream_call(self, provider, llm, body, headers, llm_model, on_token):
        """Dispatch to the correct streaming method based on provider."""
        if provider == 'anthropic':
            return llm._request_llm_anthropic_stream(body, headers, on_token=on_token)
        elif provider == 'openai':
            return llm._request_llm_openai_stream(body, on_token=on_token)
        elif provider == 'google':
            return llm._request_llm_google_stream(body, llm_model, on_token=on_token)
        raise NotImplementedError(f"Streaming not supported for provider: {provider}")

    # --- Main streaming orchestrator ---

    def _generate_response_streaming(self, agent, channel, prompt, session_info_context):
        """Stream a response into a discuss channel message. Works for all providers."""
        provider = agent._get_provider()

        system_messages = agent._build_system_context(
            extra_system_context=agent._build_extra_system_context(channel))
        if rag_context := agent._build_rag_context(prompt):
            system_messages.extend(rag_context)

        chat_history = (
            [{'content': session_info_context, 'role': 'user'}]
            + agent._retrieve_chat_history(channel)
        )

        tools = agent.topic_ids.tool_ids._get_ai_tools()
        temperature = TEMPERATURE_MAP[agent.response_style]
        web_grounding = getattr(agent, 'x_web_search', False) and provider == 'anthropic'
        code_execution = getattr(agent, 'x_code_execution', False) and provider == 'anthropic'

        # Build provider-specific request
        if provider == 'anthropic':
            llm, body, headers = self._build_stream_request_anthropic(
                agent, system_messages, chat_history, prompt, tools, temperature,
                web_grounding, code_execution=code_execution)
        elif provider == 'openai':
            llm, body, headers = self._build_stream_request_openai(
                agent, system_messages, chat_history, prompt, tools, temperature, web_grounding)
        elif provider == 'google':
            llm, body, headers = self._build_stream_request_google(
                agent, system_messages, chat_history, prompt, tools, temperature, web_grounding)
        else:
            raise NotImplementedError(f"Streaming not supported for provider: {provider}")

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
                response, to_call, next_inputs = self._stream_call(
                    provider, llm, stream_body, headers, agent.llm_model, on_token)
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

                # Add tool call history for next iteration
                if provider == 'anthropic':
                    body["messages"].extend(next_inputs)
                elif provider == 'openai':
                    body["input"].extend(next_inputs)
                elif provider == 'google':
                    body["contents"].extend(next_inputs)

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
        """Override for web search / code execution (non-streaming path)."""
        self.ensure_one()
        web_search = self.x_web_search and self._get_provider() == 'anthropic'
        code_exec = self.x_code_execution and self._get_provider() == 'anthropic'
        if web_search or code_exec:
            _logger.debug("[AI Pro] Using server tools for agent %s (web=%s, code=%s)",
                          self.name, web_search, code_exec)
            system_messages = self._build_system_context(extra_system_context=extra_system_context)
            if rag_context := self._build_rag_context(prompt):
                system_messages.extend(rag_context)
            llm_response = LLMApiService(env=self.env, provider='anthropic').request_llm(
                self.llm_model,
                system_messages,
                [],
                inputs=(chat_history or []) + [{'role': 'user', 'content': prompt}],
                tools=self.topic_ids.tool_ids._get_ai_tools(),
                temperature=TEMPERATURE_MAP[self.response_style],
                web_grounding=web_search,
                code_execution=code_exec,
            )
            if rag_context:
                llm_response = self._get_llm_response_with_sources(llm_response)
            return llm_response
        return super()._generate_response(prompt, chat_history=chat_history, extra_system_context=extra_system_context)
