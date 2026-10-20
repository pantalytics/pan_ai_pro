"""`OdooDeps`: what every tool gets through `RunContext.deps`.

`env` is the run user's environment on the slice's cursor: the caller, or
the agent's dedicated user. Nothing else reaches a tool; in particular no
`sudo` and no second cursor.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class OdooDeps:
    env: Any
    user: Any
    run: Any
    thread: Any
    record: Any = None
    # The slice's claim token: a tool's heartbeat checks it before writing.
    token: Any = None
    # Things a tool asks the window to do (open a record); the streamer
    # drains them after each tool call.
    ui_actions: list = field(default_factory=list)
