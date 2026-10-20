"""AI fields: a field whose value an agent writes. The prompt, the agent and
the two switches live on `ir.model.fields`, so any stored field of any model
can become one (Settings > Technical > Fields, or AI Pro > Configuration >
AI fields). Auto fill computes empty records nightly; auto update recomputes,
nightly, the values whose inputs changed. A value a person typed is left
alone. The compute itself is runtime/field.py.
"""

import logging
import re
import time

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import SQL
from odoo.tools.sql import column_exists, table_exists

from ..compat import clear_ormcache, ormcache, params

_logger = logging.getLogger(__name__)

# Fill now: the field ids whose empty records the next cron wake fills.
FILL_NOW_PARAM = "pan_ai.fill_now"
# The nightly loop's place when a wake ran out of time: the last field served.
NIGHTLY_CURSOR_PARAM = "pan_ai.fill_cursor"

FILLABLE = (
    "char",
    "text",
    "html",
    "integer",
    "float",
    "monetary",
    "boolean",
    "date",
    "datetime",
    "selection",
    "many2one",
)
# {{ object.partner_id.name }} names an input: its root field is watched.
INPUT_RE = re.compile(r"\{\{\s*object\.([a-zA-Z_][a-zA-Z0-9_]*)")


class IrModelFields(models.Model):
    _inherit = "ir.model.fields"

    pan_ai_prompt = fields.Text(
        string="AI prompt",
        help="What the agent should put in this field; {{ object.name }} and other fields are filled in and watched.",
    )
    pan_ai_agent_id = fields.Many2one(
        "pan_ai.agent", string="AI agent", ondelete="set null", help="Empty: the first agent."
    )
    pan_ai_auto_fill = fields.Boolean(string="Auto fill", help="Fill empty records nightly.")
    pan_ai_auto_update = fields.Boolean(
        string="Auto update",
        help="Recompute stale values nightly; a value goes stale when an input named in the prompt changes.",
    )
    pan_ai_use_tools = fields.Boolean(
        string="Let the agent use its tools",
        help="Off: the prompt and the record are all the agent sees.",
    )
    pan_ai_is_ai = fields.Boolean(compute="_compute_pan_ai_is_ai", store=True, index=True)

    # Our columns may change on any field, base fields included: they
    # describe what the agent does, not the field itself.
    _PAN_AI_COLUMNS = (
        "pan_ai_prompt",
        "pan_ai_agent_id",
        "pan_ai_auto_fill",
        "pan_ai_auto_update",
        "pan_ai_use_tools",
    )

    def _get_writable_properties(self):
        # Odoo 20: the whitelist of properties a base field accepts.
        return super()._get_writable_properties() + list(self._PAN_AI_COLUMNS)

    def write(self, vals):
        # Odoo 19 has no such whitelist and refuses every write on a base
        # field; a write that touches only our columns skips that guard.
        ours_only = bool(vals) and all(key in self._PAN_AI_COLUMNS for key in vals)
        if ours_only and not hasattr(super(), "_get_writable_properties"):
            result = models.BaseModel.write(self, vals)
        else:
            result = super().write(vals)
        if any(key in self._PAN_AI_COLUMNS for key in vals):
            clear_ormcache(self.env)
        return result

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if any(vals.get("pan_ai_prompt") for vals in vals_list):
            clear_ormcache(self.env)
        return records

    def unlink(self):
        if self._pan_ai_column_ready() and any(self.mapped("pan_ai_is_ai")):
            clear_ormcache(self.env)
        return super().unlink()

    @api.constrains("pan_ai_prompt", "ttype", "store")
    def _check_pan_ai(self):
        for field in self.filtered("pan_ai_prompt"):
            if field.ttype not in FILLABLE or not field.store:
                raise UserError(
                    _("An AI field must be a stored field of type %s.", ", ".join(FILLABLE))
                )

    def pan_ai_inputs(self):
        """The record fields the prompt names, so a change to one marks the value stale."""
        self.ensure_one()
        return set(INPUT_RE.findall(self.pan_ai_prompt or ""))

    @api.model
    def pan_ai_fields_of(self, model_name):
        """The AI fields of a model. Every write on every model asks; the
        answer is cached per model until an AI field changes."""
        if not self._pan_ai_column_ready():
            return self.browse()
        return self.sudo().browse(self._pan_ai_field_ids(model_name))

    @ormcache("model_name")
    def _pan_ai_field_ids(self, model_name):
        # Cleared by write, create and unlink above whenever a prompt changes.
        return self.sudo().search([("model", "=", model_name), ("pan_ai_is_ai", "=", True)]).ids

    @api.depends("pan_ai_prompt")
    def _compute_pan_ai_is_ai(self):
        for field in self:
            field.pan_ai_is_ai = bool(field.pan_ai_prompt)

    @api.model
    def _pan_ai_column_ready(self):
        """False while the module's code is on disk but its upgrade has not run:
        a host pulls the code first and upgrades later, and in between the
        column is not there. Every write would fail on it (measured on
        odoo.pantalytics.com, 2026-10-19). Only a True answer is kept.
        Since _pan_ai_add_missing_columns below the column is there from the
        first registry load; this guard is what a failed load falls back on."""
        registry = self.env.registry
        if getattr(registry, "_pan_ai_column_ready", False):
            return True
        ready = column_exists(self.env.cr, "ir_model_fields", "pan_ai_is_ai")
        if ready:
            registry._pan_ai_column_ready = True
        return ready

    def _register_hook(self):
        # On this model, not on `base`: a hook hung on `base` runs only if
        # every module loaded after this one calls super() in its own, and
        # on staging-pantalytics (317 modules) it never ran, 2026-10-20.
        # Here this module's class is first in line.
        self._pan_ai_add_missing_columns()
        return super()._register_hook()

    @api.model
    def _pan_ai_add_missing_columns(self):
        """A host pulls the code first and upgrades later (Cloudpepper,
        measured on staging-pantalytics 2026-10-19 and 2026-10-20). Until the
        upgrade the registry declares this module's columns on tables that do
        not have them, and every read of ir.model.fields, which every /web
        request makes, fails with a 500. So the bare columns are added at
        registry load (the hook above); the upgrade adds the index, the
        foreign key and the data. Idempotent and safe under several workers
        loading at once. Returns the (table, column) pairs added."""
        cr = self.env.cr
        added = []
        for name in self.pool.models:
            model = self.env[name]
            ours = [
                field
                for field in model._fields.values()
                if getattr(field, "_module", None) == "pan_ai_pro"
                and field.store
                and field.column_type
            ]
            if not ours or model._abstract or not model._auto:
                continue
            if not table_exists(cr, model._table):
                continue  # one of this module's own tables: the upgrade's
            for field in ours:
                if column_exists(cr, model._table, field.name):
                    continue
                column_type = field.column_type[1]
                cr.execute(
                    SQL(
                        "ALTER TABLE %s ADD COLUMN IF NOT EXISTS %s %s %s",
                        SQL.identifier(model._table),
                        SQL.identifier(field.name),
                        SQL(column_type),
                        SQL("DEFAULT false" if column_type.upper() in ("BOOL", "BOOLEAN") else ""),
                    )
                )
                added.append((model._table, field.name))
        if added:
            _logger.warning(
                "[AI Pro] the code on disk is newer than the database; added %s. "
                "Upgrade AI Pro (Apps > AI Pro > Upgrade) to finish.",
                ", ".join(f"{table}.{column}" for table, column in added),
            )
        return added

    def action_pan_ai_fill_all(self):
        """Fill now: every empty record of this field, on the AI-fields cron
        in batches (one model call per record; a request could not hold
        them). The cron runs as the person who set the field up."""
        self.ensure_one()
        from ..runtime import field as field_runtime

        n = len(field_runtime.missing_records(self, self.env.user, limit=10000))
        if n:
            self._pan_ai_fill_now(self.ids)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "message": (
                    _("1 record is being filled. See AI Pro > Runs.")
                    if n == 1
                    else _("%s records are being filled. See AI Pro > Runs.", n)
                )
                if n
                else _("Nothing to fill."),
                "type": "info",
            },
        }

    @api.model
    def _pan_ai_fill_now(self, field_ids):
        """Queue these fields for the cron and wake it."""
        queued = {int(i) for i in params(self.env).get_str(FILL_NOW_PARAM, "").split(",") if i}
        queued |= set(field_ids)
        params(self.env).set_str(FILL_NOW_PARAM, ",".join(str(i) for i in sorted(queued)))
        cron = self.env.ref("pan_ai_pro.cron_fields", raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger()

    def _pan_ai_cron_user(self):
        """Whose rights a nightly fill carries: the administrator who set the
        field up, or the first administrator when they are gone."""
        self.ensure_one()
        if self.write_uid.active and not self.write_uid.share:
            return self.write_uid
        _logger.warning(
            "[AI Pro] AI field %s.%s: its author %s is gone, the fill runs as the administrator",
            self.model,
            self.name,
            self.write_uid.login,
        )
        return self.env.ref("base.user_admin")

    @api.model
    def _cron_fill_ai_fields(self, batch_size=20):
        """Nightly: auto fill empties, auto update stale, as the agent's
        dedicated user or the administrator who set the field up. First
        what Fill now queued, one batch per wake until the field is full.
        Every value is one model call of up to a minute, so the wake has a
        deadline well inside the cron's limit; what is left waits for the
        next wake, which this one arms. A killed cron worker would be counted
        against the cron and switch it off after a few nights."""
        from ..runtime import field as field_runtime
        from ..runtime.slices import server_limit

        # Room for the value this wake starts last (one model call of up to
        # field_runtime.TIMEOUT) and a margin, inside the cron's limit.
        limit = server_limit("limit_time_real_cron")
        deadline = time.monotonic() + max(1.0, limit - field_runtime.TIMEOUT - limit * 0.1)
        queued = [int(i) for i in params(self.env).get_str(FILL_NOW_PARAM, "").split(",") if i]
        still = []
        for ir_field in self.sudo().browse(queued).exists():
            if time.monotonic() >= deadline:
                still.append(ir_field.id)
                continue
            user = ir_field._pan_ai_cron_user()
            try:
                records = field_runtime.missing_records(ir_field, user, limit=batch_size)
                if records:
                    field_runtime.fill(records, ir_field, user, deadline=deadline)
            except Exception:  # noqa: BLE001 - one bad field never stops the others
                _logger.exception("[AI Pro] AI field %s.%s failed", ir_field.model, ir_field.name)
                continue
            # A full batch was taken, or the deadline cut it short: more may
            # be waiting, whatever was written.
            if len(records) >= batch_size or time.monotonic() >= deadline:
                still.append(ir_field.id)
        params(self.env).set_str(FILL_NOW_PARAM, ",".join(str(i) for i in still))
        if still:
            self.env.ref("pan_ai_pro.cron_fields").sudo()._trigger()
            return
        # Every field gets one batch a night, in id order; a wake that runs out
        # of time leaves its place for the next wake and never starts over.
        cursor = params(self.env).get_int(NIGHTLY_CURSOR_PARAM, 0)
        for ir_field in self.sudo().search(
            [("pan_ai_is_ai", "=", True), ("id", ">", cursor)], order="id"
        ):
            if time.monotonic() >= deadline:
                params(self.env).set_int(NIGHTLY_CURSOR_PARAM, cursor)
                self.env.ref("pan_ai_pro.cron_fields").sudo()._trigger()
                return
            cursor = ir_field.id
            user = ir_field._pan_ai_cron_user()
            try:
                if ir_field.pan_ai_auto_fill:
                    field_runtime.fill_missing(ir_field, user, limit=batch_size, deadline=deadline)
                if ir_field.pan_ai_auto_update:
                    field_runtime.fill_stale(ir_field, user, limit=batch_size, deadline=deadline)
            except Exception:  # noqa: BLE001 - one bad field never stops the others
                _logger.exception("[AI Pro] AI field %s.%s failed", ir_field.model, ir_field.name)
        params(self.env).set_str(NIGHTLY_CURSOR_PARAM, "")
