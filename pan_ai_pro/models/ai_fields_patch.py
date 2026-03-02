# -*- coding: utf-8 -*-
"""Monkey-patch ai_fields to use a configurable AI agent per field.

The base ai_fields module hardcodes OpenAI (gpt-4.1) in get_ai_value().
This patch adds per-field agent selection (like Airtable), with a global
default configured in Settings → AI → AI Fields Agent.
"""
import json
import logging

import pytz
import requests
from datetime import datetime

from odoo import _
from odoo.exceptions import UserError

from odoo.addons.ai.models.ai_agent import TEMPERATURE_MAP
from odoo.addons.ai.utils.llm_api_service import LLMApiService
from odoo.addons.ai_fields.models.ir_model_fields import IrModelFields
from odoo.addons.ai_fields.models.models import Base
import odoo.addons.ai_fields.tools as ai_fields_tools
import odoo.addons.ai_fields.models.models as ai_fields_models
from odoo.addons.ai_fields.tools import (
    AI_FIELDS_INSTRUCTIONS,
    UnresolvedQuery,
    parse_ai_response,
)

_logger = logging.getLogger(__name__)


def _agent_config(agent):
    """Extract provider, model, temperature, web_grounding from an ai.agent record."""
    return (
        agent._get_provider(),
        agent.llm_model,
        TEMPERATURE_MAP.get(agent.response_style, 0.2),
        getattr(agent, 'x_web_search', False),
    )


def _get_ai_fields_config(env):
    """Get provider, model, temperature, web_grounding for AI field computation.

    Priority:
    1. Per-field agent (passed via context by _fill_ai_field / get_ai_field_value)
    2. Global default agent (Settings → AI → AI Fields Agent)

    Raises UserError if no agent is configured.
    """
    # 1. Per-field agent (set via context)
    agent_id = env.context.get('x_ai_field_agent_id')
    if agent_id:
        agent = env['ai.agent'].sudo().browse(agent_id).exists()
        if agent:
            return _agent_config(agent)

    # 2. Global default agent
    agent_id = int(env["ir.config_parameter"].sudo().get_param("x_ai.ai_fields_agent_id", "0"))
    if agent_id:
        agent = env['ai.agent'].sudo().browse(agent_id).exists()
        if agent:
            return _agent_config(agent)

    raise UserError(_("No AI Fields Agent configured. Go to Settings → AI to select an agent."))


# --- Patch _fill_ai_field to pass per-field agent via context ---

_original_fill_ai_field = Base._fill_ai_field


def _patched_fill_ai_field(self, field, field_prompt=None):
    """Look up per-field agent and pass it via context."""
    ir_field = self.env['ir.model.fields'].sudo().search(
        [('model', '=', self._name), ('name', '=', field.name)], limit=1)
    if ir_field.x_ai_agent_id:
        self = self.with_context(x_ai_field_agent_id=ir_field.x_ai_agent_id.id)
    return _original_fill_ai_field(self, field, field_prompt)


Base._fill_ai_field = _patched_fill_ai_field


# --- Patch get_ai_field_value to pass per-field agent via context ---

_original_get_ai_field_value = Base.get_ai_field_value


def _patched_get_ai_field_value(self, fname, changes):
    """Look up per-field agent and pass it via context."""
    ir_field = self.env['ir.model.fields'].sudo().search(
        [('model', '=', self._name), ('name', '=', fname)], limit=1)
    if ir_field.x_ai_agent_id:
        self = self.with_context(x_ai_field_agent_id=ir_field.x_ai_agent_id.id)
    return _original_get_ai_field_value(self, fname, changes)


Base.get_ai_field_value = _patched_get_ai_field_value


# --- Patch get_ai_value ---

_original_get_ai_value = ai_fields_tools.get_ai_value


def _patched_get_ai_value(record, field_type, user_prompt, context_fields, allowed_values):
    """Query a LLM with the given prompt and return the cast value.

    Uses per-field agent (from context) or global default agent.
    """
    if field_type in ('many2many', 'many2one', 'selection', 'tags') and not allowed_values:
        raise UnresolvedQuery(record.env._("No allowed values are provided in the prompt."))
    record_context, files = record._get_ai_context(context_fields)

    provider, model, temperature, web_grounding = _get_ai_fields_config(record.env)
    llm_api = LLMApiService(record.env, provider)

    if field_type == 'boolean':
        field_schema = {'type': 'boolean'}
    elif field_type == 'char':
        field_schema = {
            'type': 'string',
            'description': 'A short, concise string, without any Markdown formatting.',
        }
    elif field_type == 'date':
        field_schema = {
            'type': ['string', 'null'],
            'format': 'date',
            'description': 'A date (year, month and day should be correct), or null to leave empty',
        }
    elif field_type == 'datetime':
        field_schema = {
            'type': ['string', 'null'],
            'format': 'date-time',
            'description': 'A datetime (year, month and day should be correct), including the correct timezone or null to leave empty',
        }
    elif field_type == 'integer':
        field_schema = {
            'type': 'integer',
            'description': "A whole number. If a number is expressed in words (e.g. '6.67 billion'), it must be converted into its full numeric form (e.g. '6670000000')",
        }
    elif field_type in ('float', 'monetary'):
        field_schema = {'type': 'number'}
    elif field_type == 'html':
        field_schema = {
            'type': 'string',
            'description': 'A well-structured Markdown (it may contain tables). It will be converted to HTML after generation',
        }
    elif field_type == 'text':
        field_schema = {
            'type': 'string',
            'description': 'A few sentences, without any Markdown formatting',
        }
    elif field_type == 'many2many':
        field_schema = {
            'type': 'array',
            'items': {'type': 'integer', 'enum': list(allowed_values)},
            'description': 'The list of IDs of records to select. Leave empty to leave the field empty',
        }
    elif field_type == 'many2one':
        field_schema = {
            'type': ['integer', 'null'],
            'enum': list(allowed_values) + [None],
            'description': 'The ID of the record to select. null to leave the field empty if no value matches the user query',
        }
    elif field_type == 'selection':
        field_schema = {
            'type': ['string', 'null'],
            'enum': list(allowed_values) + [None],
            'description': 'Key of the value to select. null to leave the field empty',
        }
    elif field_type == 'tags':
        field_schema = {
            'type': 'array',
            'items': {'type': 'string', 'enum': list(allowed_values)},
            'description': 'List of keys of the tags to select. Leave empty to leave the field empty',
        }
    else:
        field_schema = {'type': 'text'}

    schema = {
        'type': 'object',
        'properties': {
            'value': field_schema,
            'could_not_resolve': {
                'type': 'boolean',
                'description': 'True if the model could not confidently determine a value due to missing information, ambiguity, or unknown references in the input.',
            },
            'unresolved_cause': {
                'type': ['string', 'null'],
                'description': 'Short explanation of what is missing or why no value could be generated. Required if could_not_resolve is true.',
            },
        },
        'required': ['value', 'could_not_resolve', 'unresolved_cause'],
        'additionalProperties': False,
    }

    instructions = f"{AI_FIELDS_INSTRUCTIONS}\n# Context"
    if allowed_values:
        instructions += f"\n## Allowed Values\n{json.dumps(allowed_values)}"
    instructions += f"\n The current date is {datetime.now(pytz.utc).astimezone().replace(second=0, microsecond=0).isoformat()}"

    if record_context != '{}':
        user_prompt += f"\n# Context Dict\n{record_context}"
        user_prompt += f"\nThe current record is {{'model': {record._name}, 'id': {record.id}}}"

    try:
        response, *__ = llm_api._request_llm(
            llm_model=model,
            system_prompts=[instructions],
            user_prompts=[user_prompt],
            files=files,
            schema=schema,
            temperature=temperature,
            web_grounding=web_grounding,
        )
    except requests.exceptions.Timeout:
        raise UserError(record.env._("Oops, the request timed out."))
    except requests.exceptions.ConnectionError:
        raise UserError(record.env._("Oops, the connection failed."))

    if not response:
        raise UserError(record.env._("Oops, an unexpected error occurred."))

    try:
        response = json.loads(response[0], strict=False)
    except json.JSONDecodeError:
        raise UserError(record.env._("Oops, the response could not be processed."))
    if response.get('could_not_resolve'):
        raise UnresolvedQuery(response.get('unresolved_cause'))

    return parse_ai_response(
        response.get('value'),
        field_type,
        allowed_values,
    )


ai_fields_tools.get_ai_value = _patched_get_ai_value
ai_fields_models.get_ai_value = _patched_get_ai_value


# --- Patch _cron_fill_ai_fields to check configured agent's provider ---

_original_cron = IrModelFields._cron_fill_ai_fields


def _patched_cron_fill_ai_fields(self, batch_size=10):
    """Check for a valid AI provider key before running the cron."""
    try:
        provider, *__ = _get_ai_fields_config(self.env)
    except UserError:
        _logger.info('[AI Pro] AI Fields cron skipped, no AI agent configured')
        return
    try:
        LLMApiService(self.env, provider)._get_api_token()
    except (UserError, NotImplementedError):
        _logger.info('[AI Pro] AI Fields cron skipped, no %s key found', provider)
        return
    return _original_cron(self, batch_size)


IrModelFields._cron_fill_ai_fields = _patched_cron_fill_ai_fields

_logger.info("[AI Pro] Patched ai_fields with per-field AI agent support")
