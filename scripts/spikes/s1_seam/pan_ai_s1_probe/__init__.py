"""Spike S1. Installed on a 20 Enterprise database we own, this hook zips the
source of the AI modules on disk (never anything from the database) into
one attachment reachable with an access token, and logs the URL. Nothing
else: no model, no data, no AI call, no credits.
"""

import io
import logging
import os
import zipfile

from odoo.modules.module import get_module_path

_logger = logging.getLogger(__name__)

MODULES = ["ai", "ai_app", "ai_agentic", "ai_fields", "ai_mcp", "web_studio", "iap"]
KEEP = (".py", ".xml", ".js", ".scss", ".csv", ".md", ".txt")


def post_init_hook(env):
    buf = io.BytesIO()
    found = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in MODULES:
            path = get_module_path(name, display_warning=False)
            if not path:
                continue
            found.append(name)
            for root, _dirs, files in os.walk(path):
                if "/static/lib" in root or "/i18n" in root or "/tests" in root:
                    continue
                for f in files:
                    if f.endswith(KEEP):
                        full = os.path.join(root, f)
                        try:
                            if os.path.getsize(full) < 400_000:
                                zf.write(full, os.path.relpath(full, os.path.dirname(path)))
                        except OSError:
                            pass
    att = env["ir.attachment"].sudo().create({
        "name": "pan_ai_s1_seam.zip",
        "type": "binary",
        "raw": buf.getvalue(),
        "mimetype": "application/zip",
        "res_model": "res.company",
        "res_id": env.company.id,
    })
    token = att.generate_access_token()[0]
    base = env["ir.config_parameter"].sudo().get_str("web.base.url")
    _logger.warning("[pan_ai_s1] modules on disk: %s; %d bytes at %s/web/content/%s?access_token=%s&download=1",
                    found, len(buf.getvalue()), base, att.id, token)
