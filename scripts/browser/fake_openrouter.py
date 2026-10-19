"""An OpenAI-compatible stand-in for openrouter.ai, for a browser check and
CI: streams one tool call (search_records on res.partner) on the first
request of a conversation and a short markdown answer on the next, token
by token, with `usage` and a `cost` like OpenRouter's.

    python fake_openrouter.py 8091

Point the Odoo under test at it with PAN_AI_PRO_OPENROUTER_BASE_URL
(read by runtime/agent.py only when set; production never sets it).
"""

import json
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8091
ANSWER = "There are **{n}** contacts. The first one is {name}.\n\n| Name |\n|---|\n| {name} |"


def sse(obj):
    return f"data: {json.dumps(obj)}\n\n".encode()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        messages = body.get("messages", [])
        had_tool = any(m.get("role") == "tool" for m in messages)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        base = {
            "id": "fake",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": body.get("model", "fake"),
        }
        if not had_tool and any(
            t["function"]["name"] == "search_records" for t in body.get("tools", [])
        ):
            args = json.dumps(
                {"model": "res.partner", "domain": [], "fields": ["name"], "limit": 5}
            )
            self.wfile.write(
                sse(
                    {
                        **base,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {
                                    "role": "assistant",
                                    "tool_calls": [
                                        {
                                            "index": 0,
                                            "id": "call_1",
                                            "type": "function",
                                            "function": {"name": "search_records", "arguments": ""},
                                        }
                                    ],
                                },
                                "finish_reason": None,
                            }
                        ],
                    }
                )
            )
            for i in range(0, len(args), 12):
                self.wfile.write(
                    sse(
                        {
                            **base,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {
                                        "tool_calls": [
                                            {
                                                "index": 0,
                                                "function": {"arguments": args[i : i + 12]},
                                            }
                                        ]
                                    },
                                    "finish_reason": None,
                                }
                            ],
                        }
                    )
                )
                self.wfile.flush()
            self.wfile.write(
                sse(
                    {
                        **base,
                        "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
                        "usage": {
                            "prompt_tokens": 120,
                            "completion_tokens": 20,
                            "total_tokens": 140,
                            "cost": 0.0004,
                        },
                    }
                )
            )
        else:
            n, name = 0, "nobody"
            for m in messages:
                if m.get("role") == "tool":
                    try:
                        data = json.loads(m["content"])
                        n = data.get("count", 0)
                        name = (data.get("records") or [{}])[0].get("name", name)
                    except Exception:  # noqa: BLE001 - a stub
                        pass
            text = ANSWER.format(n=n, name=name)
            self.wfile.write(
                sse(
                    {
                        **base,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"role": "assistant", "content": ""},
                                "finish_reason": None,
                            }
                        ],
                    }
                )
            )
            for tok in text.split(" "):
                self.wfile.write(
                    sse(
                        {
                            **base,
                            "choices": [
                                {"index": 0, "delta": {"content": tok + " "}, "finish_reason": None}
                            ],
                        }
                    )
                )
                self.wfile.flush()
                time.sleep(0.02)
            self.wfile.write(
                sse(
                    {
                        **base,
                        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                        "usage": {
                            "prompt_tokens": 200,
                            "completion_tokens": 40,
                            "total_tokens": 240,
                            "cost": 0.0009,
                        },
                    }
                )
            )
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


if __name__ == "__main__":
    print(f"fake openrouter on :{PORT}", flush=True)
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
