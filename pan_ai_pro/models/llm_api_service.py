# -*- coding: utf-8 -*-
"""Monkey-patch LLMApiService to add Anthropic Claude support.

The base ai module's LLMApiService uses plain Python (not Odoo models),
so we cannot use _inherit. Instead, we patch the class at module load time.
"""
import json
import logging
import os

from odoo import _
from odoo.exceptions import UserError

from odoo.addons.ai.utils.llm_api_service import LLMApiService
from odoo.addons.ai.utils.ai_logging import api_call_logging

_logger = logging.getLogger(__name__)

# --- Patch __init__ to support anthropic provider ---

_original_init = LLMApiService.__init__


def _patched_init(self, env, provider='openai'):
    if provider == 'anthropic':
        self.provider = provider
        self.base_url = "https://api.anthropic.com/v1"
        self.env = env
    else:
        _original_init(self, env, provider)


LLMApiService.__init__ = _patched_init

# --- Patch _get_api_token to support anthropic ---

_original_get_api_token = LLMApiService._get_api_token


def _patched_get_api_token(self):
    if self.provider == 'anthropic':
        if api_key := (
            self.env["ir.config_parameter"].sudo().get_param("x_ai.anthropic_key")
            or os.getenv("ODOO_AI_CLAUDE_TOKEN")
        ):
            return api_key
        raise UserError(_("No API key set for provider 'anthropic'"))
    return _original_get_api_token(self)


LLMApiService._get_api_token = _patched_get_api_token

# --- Patch _request_llm to route to anthropic ---

_original_request_llm = LLMApiService._request_llm


def _patched_request_llm(self, *args, **kwargs):
    if self.provider == 'anthropic':
        return self._request_llm_anthropic(*args, **kwargs)
    return _original_request_llm(self, *args, **kwargs)


LLMApiService._request_llm = _patched_request_llm

# --- Patch _request_llm_silent to convert inputs for anthropic ---

_original_request_llm_silent = LLMApiService._request_llm_silent


def _patched_request_llm_silent(self, *args, **kwargs):
    if self.provider == 'anthropic':
        # Convert OpenAI-style inputs to Anthropic format
        inputs = kwargs.get('inputs') or (args[7] if len(args) > 7 else None) or []
        converted = []
        for msg in inputs:
            if isinstance(msg, dict) and 'role' in msg and 'content' in msg:
                converted.append({
                    'role': msg['role'],
                    'content': msg['content'],
                })
            else:
                converted.append(msg)
        if 'inputs' in kwargs:
            kwargs['inputs'] = converted
        elif len(args) > 7:
            args = list(args)
            args[7] = converted
            args = tuple(args)
    return _original_request_llm_silent(self, *args, **kwargs)


LLMApiService._request_llm_silent = _patched_request_llm_silent

# --- Patch _build_tool_call_response to support anthropic ---

_original_build_tool_call_response = LLMApiService._build_tool_call_response


def _patched_build_tool_call_response(self, tool_call_id, return_value):
    if self.provider == 'anthropic':
        return {
            'role': 'user',
            'content': [{
                'type': 'tool_result',
                'tool_use_id': tool_call_id,
                'content': str(return_value),
            }],
        }
    return _original_build_tool_call_response(self, tool_call_id, return_value)


LLMApiService._build_tool_call_response = _patched_build_tool_call_response


# --- Add _request_llm_anthropic method ---

def _request_llm_anthropic(
    self, llm_model, system_prompts, user_prompts, tools=None,
    files=None, schema=None, temperature=0.2, inputs=(), web_grounding=False
):
    """Make a request to the Anthropic Messages API.

    https://docs.anthropic.com/en/api/messages
    https://docs.anthropic.com/en/docs/build-with-claude/tool-use

    Returns:
    - list of response text strings
    - list of tool calls [(tool_name, call_id, {arguments})]
    - list of inputs to include in next call
    """
    # Build messages list
    messages = list(inputs) if inputs else []

    # Add user prompts
    if user_prompts:
        user_content = [{"type": "text", "text": prompt} for prompt in user_prompts]

        if files:
            for idx, file in enumerate(files, start=1):
                if file["mimetype"] == "text/plain":
                    user_content.append({"type": "text", "text": file["value"]})
                elif file["mimetype"].startswith("image/"):
                    user_content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": file["mimetype"],
                            "data": file["value"],
                        },
                    })
                elif file["mimetype"] == "application/pdf":
                    user_content.append({
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": file["value"],
                        },
                    })

        messages.append({"role": "user", "content": user_content})

    body = {
        "model": llm_model,
        "max_tokens": 4096,
        "temperature": temperature,
        "messages": messages,
    }

    # System prompt
    if system_prompts:
        body["system"] = "\n\n".join(system_prompts)

    # Tools
    if tools:
        body["tools"] = [{
            "name": tool_name,
            "description": tool_description,
            "input_schema": tool_parameter_schema,
        } for tool_name, (tool_description, __, __, tool_parameter_schema) in tools.items()]

    # Structured output via tool_choice
    if schema:
        body["tools"] = body.get("tools", []) + [{
            "name": "json_response",
            "description": "Respond with structured JSON",
            "input_schema": schema,
        }]
        body["tool_choice"] = {"type": "tool", "name": "json_response"}

    # Web search — Anthropic server-side tool
    if web_grounding:
        search_tool = {
            'type': 'web_search_20250305',
            'name': 'web_search',
            'max_uses': 5,
        }
        if country_code := self.env.company.country_id.code:
            search_tool['user_location'] = {
                'type': 'approximate',
                'country': country_code,
            }
            if city := self.env.company.city:
                search_tool['user_location']['city'] = city
        body.setdefault("tools", []).append(search_tool)

    headers = {
        "Content-Type": "application/json",
        "x-api-key": self._get_api_token(),
        "anthropic-version": "2023-06-01",
    }

    with api_call_logging(messages, tools) as record_response:
        response, to_call, next_inputs = self._request_llm_anthropic_helper(body, headers, inputs)
        if record_response:
            record_response(to_call, response)
        return response, to_call, next_inputs


def _request_llm_anthropic_helper(self, body, headers, inputs=()):
    llm_response = self._request(
        method="post",
        endpoint="/messages",
        headers=headers,
        body=body,
        timeout=120,
    )

    to_call = []
    next_inputs = list(inputs or ())

    content_blocks = llm_response.get("content") or []
    # json_response is our schema emulation tool — not a real tool call
    has_tool_calls = any(
        block.get("type") == "tool_use" and block.get("name") != "json_response"
        for block in content_blocks
    )

    text_parts = []
    for block in content_blocks:
        block_type = block.get("type")
        if block_type == "tool_use":
            if block["name"] == "json_response":
                # Schema response — return as text, not as tool call
                text_parts.append(json.dumps(block.get("input", {})))
            else:
                to_call.append((block["name"], block["id"], block.get("input", {})))
        elif block_type in ("server_tool_use", "web_search_tool_result"):
            # Server-side tool blocks — handled by Anthropic, just preserve
            pass
        elif block_type == "text":
            if text := block.get("text", "").strip():
                text_parts.append(text)

    # Join all text blocks into a single response to avoid multiple messages
    response = ["\n\n".join(text_parts)] if text_parts else []

    # If there were tool calls or a paused turn, add assistant response to inputs
    stop_reason = llm_response.get("stop_reason")
    if has_tool_calls or stop_reason == "pause_turn":
        next_inputs.append({
            "role": "assistant",
            "content": content_blocks,
        })

    return response, to_call, next_inputs


LLMApiService._request_llm_anthropic = _request_llm_anthropic
LLMApiService._request_llm_anthropic_helper = _request_llm_anthropic_helper

_logger.info("[AI Pro] Patched LLMApiService with Anthropic support")
