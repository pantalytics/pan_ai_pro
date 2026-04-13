# -*- coding: utf-8 -*-
"""Extend ai.agent with streaming, web search, code execution, and file support."""
import base64
import copy
import logging
import time

from markdown2 import markdown as md_convert

from odoo import fields, models
from odoo.tools import html_sanitize

from odoo.addons.ai.models.ai_agent import TEMPERATURE_MAP
from odoo.addons.ai.utils.llm_api_service import LLMApiService
from odoo.addons.ai.utils.ai_logging import ai_response_logging, get_ai_logging_session
from odoo.addons.mail.tools.discuss import Store

_logger = logging.getLogger(__name__)



def _markdown_to_html(text):
    if not text:
        return ""
    return md_convert(text, extras=['fenced-code-blocks', 'tables', 'strike'])


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
        formatted = html_sanitize(_markdown_to_html(message))
        channel.sudo().message_post(
            author_id=self.partner_id.id,
            body=formatted,
            message_type='comment',
            silent=True,
            subtype_xmlid='mail.mt_comment',
        )

    # --- Source file upload ---

    def _extract_file_urls(self, result_str):
        """Extract large base64 blobs from tool results and replace with Odoo URLs.

        When a tool returns large data (base64 file content), find the
        corresponding ir.attachment, generate a public access token URL,
        and return document blocks that Anthropic can fetch directly.

        Returns:
            (shortened_result, file_blocks) where file_blocks is a list
            of document content blocks with URLs.
        """
        if len(result_str) < 10000:
            return result_str, []

        import re
        b64_pattern = re.compile(r'[A-Za-z0-9+/]{1000,}={0,2}')
        matches = b64_pattern.findall(result_str)
        if not matches:
            return result_str, []

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        file_blocks = []

        for match in matches:
            # Find the attachment by matching checksum
            try:
                raw = base64.b64decode(match)
            except Exception:
                continue

            checksum = self.env['ir.attachment']._compute_checksum(
                base64.b64encode(raw).decode())
            attachment = self.env['ir.attachment'].sudo().search(
                [('checksum', '=', checksum)], limit=1)
            if not attachment:
                continue

            # Generate access token and build URL
            tokens = attachment.generate_access_token()
            url = (f"{base_url}/web/content/{attachment.id}"
                   f"?access_token={tokens[0]}")

            file_blocks.append({
                "type": "document",
                "source": {"type": "url", "url": url},
                "title": attachment.name,
            })

            result_str = result_str.replace(
                match,
                f"[File: {attachment.name} ({attachment.file_size} bytes) — "
                f"available as document attachment]"
            )

        return result_str, file_blocks

    # --- Streaming ---

    def _generate_response_for_channel(self, mail_message, channel):
        self.ensure_one()
        prompt, session_info_context = self._parse_user_message(mail_message)
        agent = self.with_context(discuss_channel=channel)
        try:
            self._generate_response_streaming(agent, channel, prompt, session_info_context)
        except Exception:
            if self.env.user._is_internal():
                raise
            self._post_ai_response(channel, self.env._("Oops, it looks like our AI is unreachable"))

    def _generate_response_streaming(self, agent, channel, prompt, session_info_context):
        provider = agent._get_provider()

        system_messages = agent._build_system_context(
            extra_system_context=agent._build_extra_system_context(channel))
        rag_context = agent._build_rag_context(prompt)
        if rag_context:
            system_messages.extend(rag_context)

        chat_history = (
            [{'content': session_info_context, 'role': 'user'}]
            + agent._retrieve_chat_history(channel)
        )
        tools = agent.topic_ids.tool_ids._get_ai_tools()
        temperature = TEMPERATURE_MAP[agent.response_style]

        llm, body, headers = self._build_stream_request(
            agent, provider, system_messages, chat_history, prompt, tools, temperature)


        # Create placeholder message
        placeholder = channel.sudo().message_post(
            author_id=agent.partner_id.id,
            body="…",
            message_type='comment',
            silent=True,
            subtype_xmlid='mail.mt_comment',
        )
        msg_id = placeholder.id
        self.env.cr.commit()

        prev_len = [0]
        last_commit = [time.monotonic()]

        def on_token(text):
            delta = text[prev_len[0]:]
            if not delta:
                return
            prev_len[0] = len(text)
            channel._bus_send("ai_pro.stream_token", {
                "message_id": msg_id,
                "delta": delta,
            })
            # Batch commits: bus notifications queue up until commit
            now = time.monotonic()
            if now - last_commit[0] > 0.08:
                self.env.cr.commit()
                last_commit[0] = now

        max_calls = int(self.env["ir.config_parameter"].sudo().get_param(
            "ai.max_successive_calls", "20"))
        max_tools_per_call = int(self.env["ir.config_parameter"].sudo().get_param(
            "ai.max_tool_calls_per_call", "20"))

        all_responses = []

        with ai_response_logging(agent.llm_model):
            for _ in range(max_calls):
                response, to_call, next_inputs = self._stream_call(
                    provider, llm, copy.deepcopy(body), headers, agent.llm_model, on_token)
                all_responses.extend(response)

                if not to_call:
                    break

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

                    # Replace large base64 blobs with Odoo download URLs
                    result_str = str(result)
                    file_blocks = []
                    if provider == 'anthropic' and len(result_str) > 10000:
                        result_str, file_blocks = agent._extract_file_urls(result_str)
                    next_inputs.append(llm._build_tool_call_response(call_id, result_str))

                    # Add file URL documents so Anthropic can fetch them directly
                    if file_blocks:
                        next_inputs.append({
                            'role': 'user',
                            'content': file_blocks + [{
                                "type": "text",
                                "text": "The files above are available for download. "
                                        "Use the code execution tool to read and analyze them.",
                            }],
                        })

                    if has_end and error is None:
                        done = True
                        if end_msg and end_msg.strip():
                            all_responses.append(end_msg.strip())

                if done:
                    break

                # Append tool call history for next iteration
                msg_key = {'anthropic': 'messages', 'openai': 'input', 'google': 'contents'}[provider]
                body[msg_key].extend(next_inputs)

        # Flush remaining bus notifications
        self.env.cr.commit()

        # Final update: write formatted HTML to DB and notify frontend
        if all_responses:
            final_text = "\n\n".join(all_responses)
            if rag_context:
                final_text = agent._get_llm_response_with_sources([final_text])[0]
            placeholder.sudo().write({'body': html_sanitize(_markdown_to_html(final_text))})
            Store(bus_channel=channel).add(placeholder, ["body"]).bus_send()
            self.env.cr.commit()


    # --- Request builders ---

    def _build_stream_request(self, agent, provider, system_messages, chat_history,
                              prompt, tools, temperature):
        if provider == 'anthropic':
            return self._build_stream_request_anthropic(
                agent, system_messages, chat_history, prompt, tools, temperature)
        elif provider == 'openai':
            return self._build_stream_request_openai(
                agent, system_messages, chat_history, prompt, tools, temperature)
        elif provider == 'google':
            return self._build_stream_request_google(
                agent, system_messages, chat_history, prompt, tools, temperature)
        raise NotImplementedError(f"Streaming not supported for provider: {provider}")

    def _build_stream_request_anthropic(self, agent, system_messages, chat_history,
                                        prompt, tools, temperature):
        llm = LLMApiService(env=self.env, provider='anthropic')
        body = {
            "model": agent.llm_model,
            "max_tokens": 4096,
            "temperature": temperature,
            "messages": list(chat_history) + [{'role': 'user', 'content': prompt}],
        }
        if system_messages:
            body["system"] = "\n\n".join(system_messages)
        if tools:
            body["tools"] = [{
                "name": name, "description": desc, "input_schema": schema,
            } for name, (desc, __, __, schema) in tools.items()]
        if agent.x_web_search:
            body.setdefault("tools", []).append({
                'type': 'web_search_20250305', 'name': 'web_search', 'max_uses': 5,
            })
        if agent.x_code_execution:
            body.setdefault("tools", []).append({
                'type': 'code_execution_20250825', 'name': 'code_execution',
            })
        headers = {
            "Content-Type": "application/json",
            "x-api-key": llm._get_api_token(),
            "anthropic-version": "2023-06-01",
        }
        return llm, body, headers

    def _build_stream_request_openai(self, agent, system_messages, chat_history,
                                     prompt, tools, temperature):
        llm = LLMApiService(env=self.env, provider='openai')
        body = {
            "model": agent.llm_model,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": p} for p in system_messages]},
                {"role": "user", "content": [{"type": "input_text", "text": prompt}]},
                *chat_history,
            ],
            "store": False,
        }
        if agent.llm_model not in ('gpt-5', 'gpt-5-mini'):
            body["temperature"] = temperature
        if tools:
            body["tools"] = llm._to_open_ai_tool_schema([{
                "description": desc, "parameters": schema,
                "type": "function", "name": name, "strict": True,
            } for name, (desc, __, __, schema) in tools.items()])
            body["parallel_tool_calls"] = True
        if agent.x_web_search:
            search_tool = {'type': 'web_search_preview'}
            if country_code := self.env.company.country_id.code:
                search_tool['user_location'] = {'type': 'approximate', 'country': country_code}
                if city := self.env.company.city:
                    search_tool['user_location']['city'] = city
            body.setdefault("tools", []).append(search_tool)
        return llm, body, None

    def _build_stream_request_google(self, agent, system_messages, chat_history,
                                     prompt, tools, temperature):
        llm = LLMApiService(env=self.env, provider='google')
        gemini_history = [
            {"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]}
            for m in chat_history if isinstance(m, dict) and "content" in m
        ]
        body = {
            "contents": gemini_history + [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature},
        }
        if system_messages:
            body["systemInstruction"] = {"parts": [{"text": p} for p in system_messages]}
        if tools:
            body["tools"] = {"functionDeclarations": [{
                "description": desc, "parameters": schema, "name": name,
            } for name, (desc, __, __, schema) in tools.items()]}
        if agent.x_web_search:
            body["tools"] = {'google_search': {}}
        return llm, body, None

    def _stream_call(self, provider, llm, body, headers, llm_model, on_token):
        if provider == 'anthropic':
            return llm._request_llm_anthropic_stream(body, headers, on_token=on_token)
        elif provider == 'openai':
            return llm._request_llm_openai_stream(body, on_token=on_token)
        elif provider == 'google':
            return llm._request_llm_google_stream(body, llm_model, on_token=on_token)
        raise NotImplementedError(f"Streaming not supported for provider: {provider}")

    # --- Non-streaming path (used by non-channel callers like AI Fields) ---

    def _generate_response(self, prompt, chat_history=None, extra_system_context=""):
        self.ensure_one()
        if self._get_provider() == 'anthropic' and (self.x_web_search or self.x_code_execution):
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
                web_grounding=self.x_web_search,
                code_execution=self.x_code_execution,
            )
            if rag_context:
                llm_response = self._get_llm_response_with_sources(llm_response)
            return llm_response
        return super()._generate_response(
            prompt, chat_history=chat_history, extra_system_context=extra_system_context)
