# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""The model hosts: who answers a model row, and with which key.

Constants, never settings. Settings keeps one key per host; each model row
says which host answers it, so agents on OpenRouter and on EUrouter live
side by side. EUrouter speaks OpenRouter's dialect (the `reasoning` object,
`usage.cost`) and routes to EU-hosted providers only, so the runtime builds
both with one model class. A host's address can be pointed at a stand-in
(scripts/browser/fake_openrouter.py) by an environment variable on the
server, for a browser check or CI; the log says so on every run.
"""

import os
from collections import namedtuple

from .compat import params

Host = namedtuple("Host", "label base_url key env site")

HOSTS = {
    "openrouter": Host(
        "OpenRouter",
        "https://openrouter.ai/api/v1",
        "pan_ai.openrouter_key",
        "PAN_AI_PRO_OPENROUTER_BASE_URL",
        "openrouter.ai",
    ),
    "eurouter": Host(
        "EUrouter",
        "https://api.eurouter.ai/api/v1",
        "pan_ai.eurouter_key",
        "PAN_AI_PRO_EUROUTER_BASE_URL",
        "eurouter.ai",
    ),
}
HOST_SELECTION = [(code, host.label) for code, host in HOSTS.items()]


def host_of(model_row):
    return HOSTS[model_row.host or "openrouter"]


def stand_in(host):
    """The stand-in's address when the server names one, else ''."""
    return os.environ.get(host.env, "").strip()


def keyed(env):
    """The codes of the hosts with a key saved."""
    return [code for code, host in HOSTS.items() if params(env).get_str(host.key, "")]
