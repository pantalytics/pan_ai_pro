# -*- coding: utf-8 -*-
"""Extend ai.agent with web search toggle for Anthropic provider."""
import logging

from odoo import fields, models
from odoo.addons.ai.models.ai_agent import TEMPERATURE_MAP
from odoo.addons.ai.utils.llm_api_service import LLMApiService

_logger = logging.getLogger(__name__)


class AIAgent(models.Model):
    _inherit = 'ai.agent'

    x_web_search = fields.Boolean(
        string="Web Search",
        default=False,
        help="Allow this agent to search the web for current information. "
             "Currently supported for Anthropic Claude models only.",
    )

    def _generate_response(self, prompt, chat_history=None, extra_system_context=""):
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
