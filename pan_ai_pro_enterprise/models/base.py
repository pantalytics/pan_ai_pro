"""The seam spike S1 found on Enterprise 20: Odoo's own AI-field widget and
its nightly cron both end in `get_ai_field_value` and then `_fill_ai_field`
on `base`, which calls IAP. Here `_fill_ai_field` runs AI Pro's agent
instead, with the field's Odoo prompt (`system_prompt` on `ir.model.fields`)
as the AI Pro prompt when the field has none of its own. Odoo's widget,
Studio panel and columns stay; IAP credits are never spent.

Not measured on a real Enterprise 20 yet (the demo could not pull this
module, plan S3); the method names and arguments are from S1's log lines
(`ai_fields/models/models.py` line 218).
"""

import logging

from odoo import models
from odoo.tools import html2plaintext

_logger = logging.getLogger(__name__)


class Base(models.AbstractModel):
    _inherit = "base"

    def _fill_ai_field(self, field, field_prompt=None):
        from odoo.addons.pan_ai_pro.runtime import field as field_runtime

        ir_field = (
            self.env["ir.model.fields"]
            .sudo()
            .search([("model", "=", self._name), ("name", "=", field.name)], limit=1)
        )
        if not ir_field:
            return super()._fill_ai_field(field, field_prompt=field_prompt)
        if not ir_field.pan_ai_prompt:
            prompt = html2plaintext(field_prompt or ir_field.system_prompt or "")
            if not prompt:
                return super()._fill_ai_field(field, field_prompt=field_prompt)
            ir_field.write({"pan_ai_prompt": prompt})
        field_runtime.fill(self, ir_field, self.env.user)
        return True
