"""This database's connection to a Pantalytics account, and what it allows.

The module runs nothing until somebody connects it. The administrator
presses **Connect to Pantalytics** on the settings page; Odoo asks the
Pantalytics server for a pairing and opens its page in a new tab with the
code already in the link. The administrator signs in there, checks that the
page names this Odoo, and approves; the button back lands on
`/ai_pro/pantalytics/return`, which collects the key. Nobody types a code
or copies a key. **Check approval** on the settings page does the same
collection by hand.

After that, one heartbeat a day: the database id, versions and counts go
out, a signed entitlement comes back. Every run start asks `require_entitled()`:
not connected, revoked, or a cached answer older than its `valid_until`
(14 days of grace for a server that cannot be reached) refuses the run with
"Connect to Pantalytics in Settings".

**Trust.** An entitlement is only stored after its Ed25519 signature checks
out against the public key this module ships and its `db_uuid` matches this
database. The key is held in a field only `base.group_system` can read.

**There is one row**, created the first time somebody connects. `current()`
is the answer. The server side is `pantalytics/odoo-mcp-pro-admin`,
`mcp_server_odoo_admin/apps/ai_pro.py`. Mail Pro's client, paths swapped.
"""

import base64
import json
import logging
import os
from datetime import UTC, datetime, timedelta

import requests

from odoo import _, api, fields, models, release
from odoo.exceptions import AccessError, UserError

from ..compat import params

_logger = logging.getLogger(__name__)

SERVER_URL = "https://mcp.pantalytics.com"
# The verifying half of the key Pantalytics signs entitlements with: the same
# one Mail Pro and Self Learning pin. It can only check a signature.
PUBLIC_KEY = "ZWLGGpks2iRjFguGsGlhpDl64ekFiDCM7L/O/g3xK/8="

ENV_URL = "PAN_AI_PRO_SERVER_URL"
ENV_PUBLIC_KEY = "PAN_AI_PRO_PUBLIC_KEY"

LINK_PREFIX = "/api/v1/ai-pro/link"
HEARTBEAT_PATH = "/api/v1/ai-pro/heartbeat"
TIMEOUT = 15

STATUS_SELECTION = [
    ("not_connected", "Not connected"),
    ("pending", "Waiting for approval"),
    ("active", "Connected"),
    ("revoked", "Disconnected at Pantalytics"),
    ("invalid", "Key refused"),
]
NOT_CONNECTED_MESSAGE = "Connect to Pantalytics in Settings > AI Pro before running an agent."


def _server_url():
    return (os.environ.get(ENV_URL) or SERVER_URL).rstrip("/")


def _public_key():
    return os.environ.get(ENV_PUBLIC_KEY) or PUBLIC_KEY


def canonical_json(payload):
    """The bytes the server signed. Must match the platform's `apps/signing.py`."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def verify_signature(payload, signature_b64, public_key_b64):
    """True only for a payload our server signed. Any doubt is a no."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    if not public_key_b64 or not signature_b64:
        return False
    try:
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64))
        key.verify(base64.b64decode(signature_b64), canonical_json(payload))
    except (InvalidSignature, ValueError, TypeError):
        return False
    return True


def _naive_utc(iso_value):
    if not iso_value:
        return False
    value = datetime.fromisoformat(iso_value)
    if value.tzinfo:
        value = value.astimezone(UTC).replace(tzinfo=None)
    return value


class License(models.Model):
    _name = "pan_ai.license"
    _description = "Pantalytics account link"

    status = fields.Selection(STATUS_SELECTION, default="not_connected", required=True)
    key = fields.Char(groups="base.group_system", copy=False)

    user_code = fields.Char(copy=False)
    verify_url = fields.Char(copy=False)
    device_token = fields.Char(groups="base.group_system", copy=False)
    pairing_expires_at = fields.Datetime(copy=False)

    plan = fields.Char(readonly=True, copy=False)
    latest_version = fields.Char(readonly=True, copy=False)
    valid_until = fields.Datetime(readonly=True)
    message = fields.Char(readonly=True)
    entitlement_json = fields.Text(readonly=True, copy=False)
    signature = fields.Char(readonly=True, copy=False)

    last_check = fields.Datetime(readonly=True, copy=False)
    last_error = fields.Char(readonly=True, copy=False)
    connected_user_id = fields.Many2one("res.users", readonly=True, copy=False, ondelete="set null")
    connected_on = fields.Datetime(readonly=True, copy=False)

    # ---- one row -------------------------------------------------------

    @api.model
    def current(self):
        return self.sudo().search([], limit=1)

    def is_entitled(self):
        """May this Odoo run agents? Connected, a key in hand, an answer with
        a plan that has not lapsed."""
        self.ensure_one()
        if self.status != "active" or not self.sudo().key or not self.plan:
            return False
        return bool(self.valid_until and self.valid_until > fields.Datetime.now())

    @api.model
    def require_entitled(self):
        link = self.current()
        if not link or not link.is_entitled():
            raise UserError(_(NOT_CONNECTED_MESSAGE))

    def _check_admin(self):
        if not self.env.su and not self.env.user.has_group("base.group_system"):
            raise AccessError(_("Only an administrator can change the connection to Pantalytics."))

    # ---- pairing -------------------------------------------------------

    @api.model
    def action_connect(self):
        self._check_admin()
        link = self.current() or self.sudo().create({})
        if link.is_entitled():
            raise UserError(
                _(
                    "This Odoo is already connected to Pantalytics. Disconnect it first to connect it again."
                )
            )
        code, body = link._post(
            LINK_PREFIX + "/start",
            {
                "db_uuid": self._db_uuid(),
                "odoo_url": params(self.env).get_str("web.base.url", ""),
                "module_version": self._module_version(),
            },
        )
        if code == 429:
            raise UserError(
                _("Too many connection attempts from this Odoo. Try again in a few minutes.")
            )
        if code != 200 or body.get("status") != "started":
            raise UserError(
                _("Pantalytics did not accept the request (HTTP %s). Try again later.", code)
            )
        link.write(
            {
                "status": "pending",
                "user_code": body["user_code"],
                "verify_url": body.get("verify_url_complete") or body["verify_url"],
                "device_token": body["device_token"],
                "pairing_expires_at": _naive_utc(body.get("expires_at")),
                "last_error": False,
            }
        )
        return link

    def action_check_approval(self):
        self.ensure_one()
        self._check_admin()
        if self.sudo().key and self.status == "active" and not self.is_entitled():
            self._heartbeat_guarded()
            return False
        token = self.sudo().device_token
        if self.status != "pending" or not token:
            return False
        code, body = self._post(LINK_PREFIX + "/poll", {"device_token": token})
        status = body.get("status")
        if status == "linked" and body.get("key"):
            self.sudo().write(
                {
                    "key": body["key"],
                    "status": "active",
                    "connected_user_id": self.env.user.id,
                    "connected_on": fields.Datetime.now(),
                }
            )
            self._clear_pairing()
            self._heartbeat_guarded()
            return False
        if status in ("pending", "too_soon"):
            return self._notify(
                _("Not approved yet. Approve it on the Pantalytics page first, then check again.")
            )
        if code >= 500 or not status:
            return self._notify(
                _(
                    "Pantalytics did not answer (HTTP %s). Try again in a minute; the code stays valid.",
                    code,
                ),
                "warning",
            )
        self._clear_pairing()
        if not self.sudo().key:
            self.status = "not_connected"
        return self._notify(
            _("This code is no longer valid. Press Connect to Pantalytics to get a new one."),
            "warning",
        )

    @api.model
    def accept_key(self, key):
        """The Pantalytics panel connected this Odoo itself."""
        self._check_admin()
        if not isinstance(key, str) or not key.startswith("mp_") or len(key) > 128:
            raise UserError(_("That is not a Pantalytics installation key."))
        link = self.current() or self.sudo().create({})
        link._clear_pairing()
        link.sudo().write(
            {
                "key": key,
                "status": "active",
                "plan": False,
                "valid_until": False,
                "message": False,
                "last_error": False,
                "connected_user_id": self.env.user.id,
                "connected_on": fields.Datetime.now(),
            }
        )
        link._heartbeat_guarded()
        return {"status": link.status, "last_error": link.last_error or ""}

    def collect_on_return(self):
        self.ensure_one()
        if not self.env.user.has_group("base.group_system"):
            return
        if self.status == "pending":
            try:
                self.action_check_approval()
            except UserError as error:
                self.last_error = str(error)

    def action_disconnect(self):
        self.ensure_one()
        self._check_admin()
        self._clear_pairing()
        self.sudo().write(
            {
                "status": "not_connected",
                "key": False,
                "plan": False,
                "latest_version": False,
                "valid_until": False,
                "message": False,
                "entitlement_json": False,
                "signature": False,
                "last_error": False,
                "connected_user_id": False,
                "connected_on": False,
            }
        )
        return True

    def _clear_pairing(self):
        self.sudo().write(
            {
                "user_code": False,
                "verify_url": False,
                "device_token": False,
                "pairing_expires_at": False,
            }
        )

    # ---- heartbeat -----------------------------------------------------

    @api.model
    def _cron_heartbeat(self):
        link = self.current()
        if link:
            link._heartbeat_guarded()

    def _heartbeat_guarded(self):
        try:
            with self.env.cr.savepoint():
                self._heartbeat()
        except Exception as error:  # noqa: BLE001 - recorded, never raised
            _logger.exception("[AI Pro] Heartbeat failed")
            self.sudo().write({"last_check": fields.Datetime.now(), "last_error": str(error)})

    def _report(self):
        """Counts only. The request model on the server is the boundary."""
        since = fields.Datetime.now() - timedelta(days=1)
        Run = self.env["pan_ai.run"].sudo()
        errors = Run._read_group(
            [("started_at", ">=", since), ("status", "=", "failed")], ["error"], ["__count"]
        )
        return {
            "db_uuid": self._db_uuid(),
            "module_version": self._module_version(),
            "odoo_version": release.major_version,
            "edition": "enterprise"
            if "ai" in self.env.registry._init_modules
            or "web_enterprise" in self.env.registry._init_modules
            else "community",
            "agents": self.env["pan_ai.agent"].sudo().search_count([]),
            "runs_24h": Run.search_count([("started_at", ">=", since)]),
            "errors": [
                {"code": (e or "unknown")[:64].split(":")[0], "count": c} for e, c in errors
            ][:20],
        }

    def _heartbeat(self):
        self.ensure_one()
        key = self.sudo().key
        if not key:
            return
        now = fields.Datetime.now()
        try:
            code, body = self._post(HEARTBEAT_PATH, self._report(), key=key)
        except UserError as error:
            self.sudo().write({"last_check": now, "last_error": str(error)})
            return
        if code == 403 and body.get("status") == "wrong_database":
            self._refused(
                now,
                _(
                    "This key was issued to another Odoo database. Disconnect, then Connect to Pantalytics."
                ),
            )
            return
        if code == 401:
            self._refused(now, _("Pantalytics no longer recognises this key."))
            return
        if code != 200:
            self.sudo().write(
                {"last_check": now, "last_error": _("Heartbeat failed (HTTP %s).", code)}
            )
            return
        payload = body.get("entitlement") or {}
        signature = body.get("signature") or ""
        problem = self._untrusted(payload, signature)
        if problem:
            _logger.warning("[AI Pro] Ignored an entitlement: %s", problem)
            self.sudo().write({"last_check": now, "last_error": problem})
            return
        status = payload.get("status")
        self.sudo().write(
            {
                "status": status if status in dict(STATUS_SELECTION) else "invalid",
                "plan": (payload.get("plan") or "")[:32] or False,
                "latest_version": (payload.get("latest_version") or "")[:32] or False,
                "valid_until": _naive_utc(payload.get("valid_until")),
                "message": payload.get("message") or False,
                "entitlement_json": json.dumps(payload, sort_keys=True),
                "signature": signature,
                "last_check": now,
                "last_error": False,
            }
        )

    def _refused(self, now, reason):
        _logger.warning("[AI Pro] %s", reason)
        self.sudo().write(
            {
                "status": "invalid",
                "last_check": now,
                "last_error": reason,
                "plan": False,
                "entitlement_json": False,
                "signature": False,
                "valid_until": False,
            }
        )

    def _untrusted(self, payload, signature):
        if not verify_signature(payload, signature, _public_key()):
            return _("The answer from Pantalytics was not signed with its key.")
        if payload.get("db_uuid") != self._db_uuid():
            return _("The answer from Pantalytics was meant for another Odoo.")
        return None

    # ---- plumbing ------------------------------------------------------

    def _post(self, path, payload, key=None):
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        try:
            response = requests.post(
                _server_url() + path, json=payload, headers=headers, timeout=TIMEOUT
            )
        except requests.RequestException as error:
            _logger.warning("[AI Pro] %s unreachable: %s", path, error)
            raise UserError(
                _(
                    "Could not reach Pantalytics. Check that this server can make outgoing HTTPS requests."
                )
            ) from error
        try:
            body = response.json()
        except ValueError:
            body = {}
        return response.status_code, body if isinstance(body, dict) else {}

    @api.model
    def _db_uuid(self):
        return params(self.env).get_str("database.uuid", "")

    @api.model
    def _module_version(self):
        module = self.env["ir.module.module"].sudo().search([("name", "=", "pan_ai_pro")], limit=1)
        return module.installed_version or ""

    def _notify(self, message, kind="info"):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"message": message, "type": kind},
        }
