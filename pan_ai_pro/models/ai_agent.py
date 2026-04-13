# -*- coding: utf-8 -*-
"""Extend ai.agent with web search toggle for Anthropic provider."""
import logging
import re

from odoo import fields, models
from odoo.addons.ai.models.ai_agent import TEMPERATURE_MAP
from odoo.addons.ai.utils.llm_api_service import LLMApiService

try:
    from markdown2 import markdown as md_convert
except ImportError:
    md_convert = None

_logger = logging.getLogger(__name__)


def _markdown_to_html(text):
    """Convert markdown to HTML, with regex fallback if markdown2 is unavailable."""
    if md_convert:
        return md_convert(text, extras=['fenced-code-blocks', 'tables', 'strike'])
    # Minimal regex fallback for common markdown patterns
    html = text
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
    html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
    html = re.sub(r'^- (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
    html = re.sub(r'(<li>.*?</li>)', r'<ul>\1</ul>', html, flags=re.DOTALL)
    html = html.replace('\n\n', '<br/><br/>').replace('\n', '<br/>')
    return html


class AIAgent(models.Model):
    _inherit = 'ai.agent'

    x_web_search = fields.Boolean(
        string="Web Search",
        default=False,
        help="Allow this agent to search the web for current information. "
             "Currently supported for Anthropic Claude models only.",
    )

    def _post_ai_response(self, channel, message):
        """Ensure markdown is converted to HTML for Anthropic responses.

        The base implementation relies on markdown2 being installed. If it's
        missing, raw markdown is posted as plain text. We guarantee conversion
        with a regex fallback.
        """
        if self._get_provider() == 'anthropic':
            from odoo.tools import html_sanitize
            formatted = html_sanitize(_markdown_to_html(message))
            channel.sudo().message_post(
                author_id=self.partner_id.id,
                body=formatted,
                message_type='comment',
                silent=True,
                subtype_xmlid='mail.mt_comment',
            )
        else:
            super()._post_ai_response(channel, message)

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
