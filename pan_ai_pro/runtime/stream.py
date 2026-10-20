"""Run events to the browser: batched over the bus into the agent's message.

`Streamer` collects Pydantic AI's events as small JSON dicts and sends them
as `pan_ai.run_event` on the channel's bus every ~100 ms (measured in S2:
first token 50 ms after the server sent it). Every flush commits, so the
browser sees the batch now, and writes the run's heartbeat behind the claim
fence, so a worker that lost its claim stops writing.
"""

import time

from markdown2 import markdown

from odoo.tools import html_sanitize

from ..compat import send_fields
from ..tools import commit

BATCH_SECONDS = 0.1


def render_markdown(text):
    """The final body: markdown to HTML, then Odoo's sanitizer (no scripts,
    no event handlers; links get rel and target from the window)."""
    html = markdown(
        text or "", extras=["tables", "fenced-code-blocks", "break-on-newline", "strike"]
    )
    return html_sanitize(html, sanitize_tags=True, sanitize_attributes=True, strip_classes=True)


class LostClaim(Exception):
    """Another worker holds this run now; stop without writing."""


class Streamer:
    """`token` is the slice's claim; None is a finish from outside a slice
    (Stop on a waiting run, the stuck cron), where there is no claim to hold."""

    def __init__(self, run, token):
        self.run = run
        self.env = run.env
        self.token = token
        self.channel = run.thread_id.channel_id.sudo() if run.thread_id.channel_id else None
        self.message_id = run.message_id.id if run.message_id else None
        self.batch = []
        self.last_flush = time.monotonic()
        # The answer so far, from the last persisted boundary (a slice end):
        # what a reclaimed slice continues from, never a dead worker's half.
        self.text = run.text or ""

    # ---- events --------------------------------------------------------

    def event(self, kind, **data):
        self.batch.append({"type": kind, **data})
        if kind == "delta":
            self.text += data["text"]
        now = time.monotonic()
        if kind != "delta" or now - self.last_flush >= BATCH_SECONDS:
            self.flush()
            self.last_flush = now

    def flush(self, final=False):
        if not self.batch and not final:
            return
        if self.token is not None and not self.run._holds(self.token):
            raise LostClaim()
        if self.channel and self.message_id:
            self.channel._bus_send(
                "pan_ai.run_event",
                {
                    "channel_id": self.channel.id,
                    "message_id": self.message_id,
                    "run_id": self.run.id,
                    "events": list(self.batch),
                    "sent_at": time.time(),
                    "final": final,
                },
            )
        self.batch.clear()
        # The commit delivers the bus row. The text lands on the run at the
        # slice's end (runtime/slices.py) and in finish(); the heartbeat is
        # the slice's clock task, so no row is rewritten ten times a second.
        if final:
            self.run.sudo().write({"text": self.text})
        commit(self.env)

    # ---- the end -------------------------------------------------------

    def finish(self, status, error=None, pending=None):
        """Write the final body once, tell the window, and commit."""
        text = self.text
        if status == "cancelled":
            text += "\n\n*Stopped.*"
        elif status == "failed":
            text += f"\n\n*{error}*"
        self.text = text
        if self.channel and self.message_id:
            message = self.env["mail.message"].sudo().browse(self.message_id)
            body = (
                render_markdown(text)
                if text.strip()
                else render_markdown("*No answer.*" if status != "interrupted" else "")
            )
            if status != "interrupted" or text.strip():
                message.write({"body": body})
                send_fields(self.channel, message, ["body"])
        self.batch.append(
            {"type": "run_finished", "status": status, "error": error, "pending": pending or []}
        )
        self.flush(final=True)


def finish_outside(run, status, error=None):
    """A run finished by a button or a cron, not by its slice: the message
    gets its final body and the window hears `run_finished`, so the card and
    Stop go away. `run._finish` has been called already."""
    Streamer(run.sudo(), None).finish(status, error=error)
