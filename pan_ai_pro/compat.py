# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""One module on Odoo 19 and 20: the few places where the two differ.

Everything else in the module is written against the API both versions
share. Anything that must branch on the version goes through here, so the
differences stay in one file and the day 19 is dropped this file goes.
"""

from odoo import release
from odoo.addons.mail.tools.discuss import Store

try:  # 20: odoo.api.ormcache and transaction.invalidate_ormcache()
    from odoo.api import ormcache
except ImportError:  # 19: odoo.tools.ormcache and registry.clear_cache()
    from odoo.tools import ormcache

MAJOR = release.version_info[0]

__all__ = ["ormcache", "params", "send_fields", "clear_ormcache"]


def clear_ormcache(env):
    """Drop every @ormcache answer, on every worker."""
    transaction = getattr(env, "transaction", None)
    if hasattr(transaction, "invalidate_ormcache"):
        transaction.invalidate_ormcache()
    else:
        env.registry.clear_cache()


class _Params:
    """`ir.config_parameter` with 20's typed getters on 19's get_param."""

    def __init__(self, env):
        self._icp = env["ir.config_parameter"].sudo()

    def get_str(self, key, default=""):
        value = self._icp.get_param(key, False)
        return default if value is False else str(value)

    def get_int(self, key, default=0):
        raw = self.get_str(key, "")
        try:
            return int(raw) if raw else default
        except ValueError:
            return default

    def get_bool(self, key, default=False):
        raw = self.get_str(key, "").strip().lower()
        return default if not raw else raw in ("1", "true", "yes", "on")

    def set_str(self, key, value):
        self._icp.set_param(key, value if value else False)

    def set_bool(self, key, value):
        self._icp.set_param(key, "True" if value else "False")

    def set_int(self, key, value):
        self._icp.set_param(key, str(int(value)))


def params(env):
    """The config parameters, with get_str/get_int/get_bool/set_* on both versions."""
    icp = env["ir.config_parameter"].sudo()
    return icp if hasattr(icp, "get_str") else _Params(env)


def send_fields(channel, record, fields):
    """Push `fields` of `record` to the browsers on `channel` over the bus.

    20's Store with a bus channel sends by itself; 19's waits for bus_send().
    """
    store = Store(bus_channel=channel)
    store.add(record, fields)
    if hasattr(store, "bus_send"):
        store.bus_send()
