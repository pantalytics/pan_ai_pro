"""The Odoo toolset: `pan_ai.tool` rows as Pydantic AI tools over the run
user's `env`. ACLs and record rules apply because the env is the user's; an
AccessError is returned to the model as the tool's error, never caught into
a wider path. No `sudo`, no second cursor, no path outside `env`.
"""

import json
import logging
from datetime import datetime, timedelta

from pydantic_ai import RunContext, Tool
from pydantic_ai.toolsets import FunctionToolset
from pydantic_core import to_jsonable_python

from odoo import fields
from odoo.exceptions import AccessError, MissingError, UserError, ValidationError
from odoo.fields import Domain
from odoo.tools import html2plaintext

from .deps import OdooDeps

_logger = logging.getLogger(__name__)

MAX_LIMIT = 200
MAX_FIELDS = 80
RESULT_CHARS = 60000

# ---- schemas --------------------------------------------------------------

S_MODEL = {"type": "string", "description": "Technical model name, like res.partner or sale.order"}
S_FIELDS = {"type": "array", "items": {"type": "string"}, "description": "Field names to read"}
S_DOMAIN = {
    "type": "array",
    "description": 'Odoo domain, a list of [field, operator, value] triplets, like [["state", "=", "sale"]]',
    "items": {},
}
S_VALUES = {
    "type": "object",
    "description": "Field values, by field name",
    "additionalProperties": True,
}

SCHEMAS = {
    "describe_model": {"type": "object", "properties": {"model": S_MODEL}, "required": ["model"]},
    "search_records": {
        "type": "object",
        "properties": {
            "model": S_MODEL,
            "domain": S_DOMAIN,
            "fields": S_FIELDS,
            "limit": {"type": "integer", "description": "At most 200", "default": 20},
            "order": {"type": "string", "description": "Like 'date desc'", "default": ""},
        },
        "required": ["model", "domain", "fields"],
    },
    "read_records": {
        "type": "object",
        "properties": {
            "model": S_MODEL,
            "ids": {"type": "array", "items": {"type": "integer"}},
            "fields": S_FIELDS,
        },
        "required": ["model", "ids", "fields"],
    },
    "read_group": {
        "type": "object",
        "properties": {
            "model": S_MODEL,
            "domain": S_DOMAIN,
            "groupby": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Fields to group by, like ['partner_id'] or ['date_order:month']",
            },
            "aggregates": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Like ['__count', 'amount_total:sum']",
            },
        },
        "required": ["model", "domain", "groupby", "aggregates"],
    },
    "create_record": {
        "type": "object",
        "properties": {"model": S_MODEL, "values": S_VALUES},
        "required": ["model", "values"],
    },
    "write_record": {
        "type": "object",
        "properties": {"model": S_MODEL, "id": {"type": "integer"}, "values": S_VALUES},
        "required": ["model", "id", "values"],
    },
    "open_record": {
        "type": "object",
        "properties": {
            "model": S_MODEL,
            "id": {"type": "integer", "description": "One record to open; omit for a list"},
            "domain": {**S_DOMAIN, "description": "The list's filter, when opening a list"},
            "name": {"type": "string", "description": "A title for the list"},
        },
        "required": ["model"],
    },
    "today": {"type": "object", "properties": {}},
}


# ---- guards ---------------------------------------------------------------


def _model(ctx: RunContext[OdooDeps], name, tool_row):
    env = ctx.deps.env
    if name not in env:
        raise UserError(f"There is no model named {name}.")
    allowed = tool_row.model_ids.mapped("model")
    if allowed and name not in allowed:
        raise UserError(f"This tool may only touch {', '.join(allowed)}.")
    return env[name]


def _domain(value):
    return Domain(value if isinstance(value, list) else [])


def _clip(value):
    text = json.dumps(to_jsonable_python(value), ensure_ascii=False, default=str)
    if len(text) > RESULT_CHARS:
        return {"truncated": True, "text": text[:RESULT_CHARS]}
    return value


def _fields_of(Model, names):
    names = [n for n in names if n in Model._fields][:MAX_FIELDS]
    return names or ["display_name"]


# ---- the built-ins --------------------------------------------------------


def describe_model(ctx, tool_row, model):
    Model = _model(ctx, model, tool_row)
    Model.check_access("read")
    out = []
    for name, f in list(Model._fields.items())[:400]:
        if (
            name.startswith("_")
            or f.type in ("binary",)
            or not f.store
            and f.type in ("one2many", "many2many")
        ):
            continue
        row = {"name": name, "type": f.type, "label": f.string}
        if f.required:
            row["required"] = True
        if f.comodel_name:
            row["relation"] = f.comodel_name
        if f.type == "selection":
            try:
                row["selection"] = [k for k, _v in f.get_description(ctx.deps.env)["selection"]][
                    :30
                ]
            except Exception:  # noqa: BLE001 - a selection we cannot list is still a selection
                pass
        out.append(row)
    return {"model": model, "description": Model._description, "fields": out[: MAX_FIELDS * 2]}


def search_records(ctx, tool_row, model, domain, fields_, limit=20, order=""):
    Model = _model(ctx, model, tool_row)
    limit = max(1, min(int(limit or 20), MAX_LIMIT))
    rows = Model.search_read(
        _domain(domain), _fields_of(Model, fields_), limit=limit, order=order or None
    )
    return _clip({"count": len(rows), "records": rows})


def read_records(ctx, tool_row, model, ids, fields_):
    Model = _model(ctx, model, tool_row)
    records = Model.browse([int(i) for i in ids][:MAX_LIMIT]).exists()
    return _clip({"records": records.read(_fields_of(Model, fields_))})


def read_group(ctx, tool_row, model, domain, groupby, aggregates):
    Model = _model(ctx, model, tool_row)
    groups = Model._read_group(_domain(domain), groupby[:3], aggregates[:5] or ["__count"])
    out = []
    for row in groups:
        keys = row[: len(groupby[:3])]
        vals = row[len(groupby[:3]) :]
        out.append(
            {
                "group": [k.display_name if hasattr(k, "display_name") else k for k in keys],
                "values": dict(zip(aggregates[:5] or ["__count"], vals, strict=False)),
            }
        )
    return _clip({"groups": out[:MAX_LIMIT]})


def create_record(ctx, tool_row, model, values):
    Model = _model(ctx, model, tool_row)
    record = Model.create(values)
    return {"id": record.id, "display_name": record.display_name}


def write_record(ctx, tool_row, model, id, values):  # noqa: A002 - the model's own name for it
    Model = _model(ctx, model, tool_row)
    record = Model.browse(int(id)).exists()
    if not record:
        raise MissingError(f"{model} {id} does not exist.")
    record.write(values)
    return {"id": record.id, "display_name": record.display_name, "updated": list(values)}


def open_record(ctx, tool_row, model, id=None, domain=None, name=None):  # noqa: A002
    Model = _model(ctx, model, tool_row)
    Model.check_access("read")
    action = {"model": model}
    if id:
        record = Model.browse(int(id)).exists()
        if not record:
            raise MissingError(f"{model} {id} does not exist.")
        action.update({"id": record.id, "name": record.display_name})
    else:
        action.update({"domain": domain or [], "name": name or Model._description})
    ctx.deps.ui_actions.append(action)
    return {"opened": action}


def today(ctx, tool_row):
    user = ctx.deps.user
    now = fields.Datetime.context_timestamp(user, datetime.utcnow())
    day = now.date()
    return {
        "now": now.isoformat(timespec="minutes"),
        "today": day.isoformat(),
        "weekday": day.strftime("%A"),
        "week_start": (day - timedelta(days=day.weekday())).isoformat(),
        "month_start": day.replace(day=1).isoformat(),
        "year_start": day.replace(month=1, day=1).isoformat(),
        "timezone": user.tz or "UTC",
    }


BUILTINS = {
    "describe_model": describe_model,
    "search_records": search_records,
    "read_records": read_records,
    "read_group": read_group,
    "create_record": create_record,
    "write_record": write_record,
    "open_record": open_record,
    "today": today,
}


def run_server_action(ctx, tool_row, **args):
    deps = ctx.deps
    action = tool_row.action_id.with_env(deps.env)
    context = {"pan_ai_args": args}
    if deps.record is not None and deps.record._name == action.model_name:
        context.update(
            {
                "active_model": deps.record._name,
                "active_id": deps.record.id,
                "active_ids": deps.record.ids,
            }
        )
    result = action.with_context(**context).run()
    return _clip(
        {
            "result": result
            if isinstance(result, dict | list | str | int | float | bool)
            else bool(result)
        }
    )


# ---- rows to tools --------------------------------------------------------


def _function(tool_row, env):
    """The async function behind one row. Async so it runs in the slice's
    thread, on the slice's cursor; Pydantic AI would put a sync function on
    another thread."""
    builtin = BUILTINS.get(tool_row.builtin) if tool_row.source == "builtin" else None
    row = tool_row.with_env(env)

    async def call(ctx: RunContext[OdooDeps], **args):
        if "fields" in args:
            args["fields_"] = args.pop("fields")
        try:
            if builtin:
                result = builtin(ctx, row, **args)
            else:
                result = run_server_action(ctx, row, **args)
            ctx.deps.run.log_tool({"tool": row.name, "args": args, "ok": True})
            return result
        except (
            AccessError,
            MissingError,
            UserError,
            ValidationError,
            ValueError,
            KeyError,
            TypeError,
        ) as error:
            message = html2plaintext(str(error))
            ctx.deps.run.log_tool(
                {"tool": row.name, "args": args, "ok": False, "error": message[:500]}
            )
            return {"error": message[:2000]}

    call.__name__ = tool_row.name
    return call


def build_toolset(toolset_record, env):
    tools = []
    for row in toolset_record.tool_ids.filtered("active"):
        if row.source == "builtin":
            schema = SCHEMAS[row.builtin]
        else:
            schema = json.loads(
                row.parameters_json_schema or '{"type": "object", "properties": {}}'
            )
        tool = Tool.from_schema(
            _function(row, env),
            name=row.name,
            description=row.description,
            json_schema=schema,
            takes_ctx=True,
        )
        tool.requires_approval = row.asks_approval()
        tools.append(tool)
    return FunctionToolset(tools, id=f"toolset-{toolset_record.id}")
