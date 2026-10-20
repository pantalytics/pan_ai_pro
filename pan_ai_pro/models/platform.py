"""The platform's address and key, and the signature check: the pure
half of `license.py`, kept apart so the model file stays readable."""

import base64
import json
import logging
import os
from datetime import UTC, datetime
from urllib.parse import urlparse

from odoo import _
from odoo.exceptions import UserError

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


def _server_url():
    """Pantalytics, or the stand-in a browser check or CI names in the
    environment (scripts/browser/fake_platform.py). A stand-in is announced
    on every call so it can never pass unnoticed, and must be https unless
    it is this machine."""
    override = (os.environ.get(ENV_URL) or "").strip()
    if not override:
        return SERVER_URL
    parsed = urlparse(override)
    local = parsed.hostname in ("127.0.0.1", "localhost", "::1")
    if parsed.scheme not in ("http", "https") or (parsed.scheme == "http" and not local):
        raise UserError(
            _("%s must be an https URL (http only for this machine); it is %r.", ENV_URL, override)
        )
    _logger.warning("[AI Pro] the platform is %s, not Pantalytics (%s is set)", override, ENV_URL)
    return override.rstrip("/")


def _public_key():
    override = (os.environ.get(ENV_PUBLIC_KEY) or "").strip()
    if not override:
        return PUBLIC_KEY
    _logger.warning("[AI Pro] entitlements are checked against the key in %s", ENV_PUBLIC_KEY)
    return override


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
