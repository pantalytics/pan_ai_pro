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
    get_field_prompt_vals,
    parse_ai_response,
)

_logger = logging.getLogger(__name__)


def _update_ai_metadata(env, model_name, record_ids, field_name, **values):
    """Create or update AI field metadata for given records."""
    if not record_ids:
        return
    Metadata = env['x_ai.field.metadata'].sudo()
    for rec_id in record_ids:
        existing = Metadata.search([
            ('model_name', '=', model_name),
            ('res_id', '=', rec_id),
            ('field_name', '=', field_name),
        ], limit=1)
        if existing:
            existing.write(values)
        else:
            Metadata.create({
                'model_name': model_name,
                'res_id': rec_id,
                'field_name': field_name,
                **values,
            })


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
    """Look up per-field agent and pass it via context. Clear metadata after generation."""
    ir_field = self.env['ir.model.fields'].sudo().search(
        [('model', '=', self._name), ('name', '=', field.name)], limit=1)
    if ir_field.x_ai_agent_id:
        self = self.with_context(x_ai_field_agent_id=ir_field.x_ai_agent_id.id)
    result = _original_fill_ai_field(self, field, field_prompt)
    # Clear stale/human-edited flags after AI generation
    _update_ai_metadata(self.env, self._name, self.ids, field.name,
                        is_stale=False, human_edited=False)
    return result


Base._fill_ai_field = _patched_fill_ai_field


# --- Patch get_ai_field_value to pass per-field agent via context ---

_original_get_ai_field_value = Base.get_ai_field_value


def _patched_get_ai_field_value(self, fname, changes):
    """Look up per-field agent and pass it via context. Clear stale flag after generation."""
    ir_field = self.env['ir.model.fields'].sudo().search(
        [('model', '=', self._name), ('name', '=', fname)], limit=1)
    if ir_field.x_ai_agent_id:
        self = self.with_context(x_ai_field_agent_id=ir_field.x_ai_agent_id.id)
    result = _original_get_ai_field_value(self, fname, changes)
    # Clear stale flag after manual generation (button click)
    if self.ids:
        _update_ai_metadata(self.env, self._name, self.ids, fname,
                            is_stale=False, human_edited=False)
    return result


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
    _original_cron(self, batch_size)
    # Process auto-generate fields (without ai_domain restriction)
    _process_auto_regenerate(self.env, batch_size)


IrModelFields._cron_fill_ai_fields = _patched_cron_fill_ai_fields


# --- Patch Base.write() for auto-generate AI fields ---

_original_base_write = Base.write


def _patched_base_write(self, vals):
    result = _original_base_write(self, vals)
    if vals and not self.env.context.get('_ai_auto_regenerating'):
        try:
            _handle_ai_field_writes(self, vals)
        except Exception:
            _logger.warning("[AI Pro] Error in AI field tracking", exc_info=True)
    return result


Base.write = _patched_base_write


def _handle_ai_field_writes(records, vals):
    """Handle writes that affect AI fields: auto-regenerate, mark stale, track human edits."""
    if not records:
        return

    # Fast check: does this model have any AI fields?
    ai_field_names = [f.name for f in records._fields.values() if hasattr(f, 'ai') and f.ai]
    if not ai_field_names:
        return

    env = records.env
    written_fields = set(vals.keys())
    _logger.info("[AI Pro] _handle_ai_field_writes: model=%s, records=%s, written_fields=%s, ai_fields=%s",
                 records._name, records.ids, written_fields, ai_field_names)

    # Track human edits: when user writes directly to an AI field
    _track_human_edits(records, written_fields)

    # Check context field changes for auto-regenerate and is_stale
    _check_context_field_changes(records, written_fields)


def _track_human_edits(records, written_fields):
    """Mark AI fields as human-edited when user writes to them directly."""
    for fname in written_fields:
        field = records._fields.get(fname)
        if field and hasattr(field, 'ai') and field.ai:
            _logger.info("[AI Pro] _track_human_edits: %s.%s → human_edited=True, is_stale=False",
                         records._name, fname)
            _update_ai_metadata(records.env, records._name, records.ids, fname,
                                human_edited=True, is_stale=False)


def _check_context_field_changes(records, written_fields):
    """Handle context field changes: auto-regenerate or mark stale."""
    env = records.env

    # Find ALL AI fields for this model (both auto-generate and manual)
    ir_fields = env['ir.model.fields'].sudo().search([
        ('model', '=', records._name),
        ('ai', '=', True),
        ('system_prompt', '!=', False),
    ])
    if not ir_fields:
        _logger.info("[AI Pro] _check_context_field_changes: no AI fields found for %s", records._name)
        return

    _logger.info("[AI Pro] _check_context_field_changes: model=%s, found %d AI fields: %s",
                 records._name, len(ir_fields),
                 [(f.name, f.ttype) for f in ir_fields])

    fields_to_stale = []

    for ir_field in ir_fields:
        field = records._fields.get(ir_field.name)
        if not field:
            _logger.info("[AI Pro]   %s: field not found in _fields", ir_field.name)
            continue
        try:
            _, context_fields, _ = get_field_prompt_vals(env, field)
        except Exception as e:
            _logger.info("[AI Pro]   %s: get_field_prompt_vals failed: %s", ir_field.name, e)
            continue
        # Get root field names from context paths (e.g. 'partner_id.name' → 'partner_id')
        root_fields = {cf.split('.')[0] for cf in context_fields}
        _logger.info("[AI Pro]   %s: context_fields=%s, root_fields=%s, overlap=%s",
                     ir_field.name, context_fields, root_fields, root_fields & written_fields)
        if not (root_fields & written_fields):
            continue

        # Context fields changed → mark as stale.
        # The frontend handles the distinction:
        # - auto_update=True → frontend auto-triggers regeneration (spinner + inline update)
        # - auto_update=False → frontend shows "Inputs changed" indicator
        _logger.info("[AI Pro]   %s: → fields_to_stale (auto_update=%s)", ir_field.name, ir_field.x_ai_auto_update)
        fields_to_stale.append(ir_field.name)

    # Mark stale fields
    if fields_to_stale:
        for fname in fields_to_stale:
            _logger.info("[AI Pro] Marking %s.%s as stale for records %s",
                         records._name, fname, records.ids)
            _update_ai_metadata(env, records._name, records.ids, fname, is_stale=True)


def _process_auto_regenerate(env, batch_size=10):
    """Process AI fields with NULL values where auto_fill or auto_update is enabled."""
    ir_fields = env['ir.model.fields'].sudo().search([
        ('ai', '=', True),
        '|', ('x_ai_auto_fill', '=', True), ('x_ai_auto_update', '=', True),
        ('system_prompt', '!=', False),
        ('ttype', 'in', ('char', 'text', 'html')),
    ])
    Metadata = env['x_ai.field.metadata'].sudo()

    for ir_field in ir_fields:
        try:
            Model = env[ir_field.model]
        except KeyError:
            continue
        field = Model._fields.get(ir_field.name)
        if not field:
            continue

        # Find records where field is NULL/empty — no ai_domain restriction
        records = Model.search([(ir_field.name, '=', False)], limit=batch_size)
        if not records:
            continue

        # Skip human-edited records
        human_metas = Metadata.search([
            ('model_name', '=', ir_field.model),
            ('field_name', '=', ir_field.name),
            ('res_id', 'in', records.ids),
            ('human_edited', '=', True),
        ])
        if human_metas:
            skip_ids = set(human_metas.mapped('res_id'))
            records = records.filtered(lambda r: r.id not in skip_ids)
        if not records:
            continue

        _logger.info("[AI Pro] Auto-regenerating %s.%s for %d records",
                     ir_field.model, ir_field.name, len(records))

        if ir_field.x_ai_agent_id:
            records = records.with_context(x_ai_field_agent_id=ir_field.x_ai_agent_id.id)

        records.with_context(_ai_auto_regenerating=True)._fill_ai_field(field)


_logger.info("[AI Pro] Patched ai_fields with per-field AI agent support")
