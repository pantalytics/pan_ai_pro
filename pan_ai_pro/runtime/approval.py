# Copyright 2025-2026 Pantalytics B.V. All rights reserved.
# SPDX-License-Identifier: Elastic-2.0
"""Approval: what a call waiting for it would do, in words a person can
judge, and what the person decided (docs/plans/ai-colleague.md, section 8,
rules A1, A2 and A8).

Odoo has no undo, so the approval card shows the effect, not the call:
'Change Lead "Acme": Expected revenue: 0 → 25,000'. Labels and current
values are read as the run's user when the call is proposed, and a change
to an existing record keeps its `write_date`, so an Allow given after the
record changed does not run (`stale`). A tool we cannot read the effect of
(a server action, an MCP tool) keeps its name and arguments.
"""

import json
import logging

from pydantic_ai import DeferredToolResults, ToolDenied

from odoo.exceptions import AccessError, MissingError

_logger = logging.getLogger(__name__)

ARROW = "→"
MAX_FIELDS = 12
MAX_VALUE = 80


def describe(run, pending):
    """`pending` with an `effect` (and, for a change, the record and its
    `write_date`) on every call we can read. Never raises: a call we cannot
    describe keeps its arguments."""
    env = run.env(user=run.user_id)
    tools = run.thread_id.agent_id.toolset_ids.tool_ids
    for call in pending:
        row = tools.filtered(lambda t, name=call["name"]: t.name == name)[:1]
        if row.source != "builtin" or row.builtin not in ("create_record", "write_record"):
            continue
        try:
            call.update(_effect(env, row.builtin, json.loads(call["args"] or "{}")))
        except (AccessError, MissingError, KeyError, TypeError, ValueError) as error:
            _logger.info("[AI Pro] run %s: no effect for %s: %s", run.id, call["name"], error)
    return pending


STALE = (
    "Not run: the record changed after you proposed this. "
    "Read it again and propose the change again."
)


def deferred(run):
    """The person's decisions for the next slice: true, false, or "stale"
    (allowed, but the record changed since, so it is refused with a reason
    the model can act on)."""
    if not run.deferred_results:
        return None
    decided = json.loads(run.deferred_results).get("approvals", {})
    return DeferredToolResults(
        approvals={
            cid: ToolDenied(STALE) if ok == "stale" else bool(ok) for cid, ok in decided.items()
        }
    )


def stale(env, call):
    """Did the record change after the call was proposed?"""
    if not call.get("stamp"):
        return False
    record = env[call["model"]].sudo().browse(call["res_id"]).exists()
    return not record or str(record.write_date) != call["stamp"]


def _effect(env, builtin, args):
    Model = env[args["model"]]
    values = args.get("values") or {}
    names = [name for name in values if name in Model._fields][:MAX_FIELDS]
    if builtin == "create_record":
        changes = [f"{_label(Model, n)}: {_show(Model, n, values[n])}" for n in names]
        return {"effect": f"Create {Model._description}: " + "; ".join(changes)}
    record = Model.browse(int(args["id"])).exists()
    if not record:
        raise MissingError(f"{args['model']} {args['id']}")
    record.check_access("read")
    changes = [
        f"{_label(Model, n)}: {_show(Model, n, record[n])} {ARROW} {_show(Model, n, values[n])}"
        for n in names
    ]
    return {
        "effect": f'Change {Model._description} "{record.display_name}": ' + "; ".join(changes),
        "model": record._name,
        "res_id": record.id,
        "stamp": str(record.write_date),
    }


def _label(Model, name):
    return Model._fields[name].get_description(Model.env)["string"]


def _show(Model, name, value):
    """One value as a person reads it: a record's name, a selection's label."""
    field = Model._fields[name]
    if field.type == "many2one":
        if hasattr(value, "_name"):
            return value.display_name or "-"
        target = Model.env[field.comodel_name].browse(value).exists() if value else None
        return target.display_name if target else "-"
    if field.type in ("one2many", "many2many"):
        if hasattr(value, "_name"):
            return ", ".join(value.mapped("display_name"))[:MAX_VALUE] or "-"
        return f"{len(value or [])} change(s)"
    if field.type == "selection":
        labels = dict(field._description_selection(Model.env))
        return labels.get(value, value) or "-"
    if field.type == "boolean":
        return "Yes" if value else "No"
    if value in (False, None, ""):
        return "-"
    return str(value)[:MAX_VALUE]
