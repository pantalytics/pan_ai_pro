import asyncio, json, time
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessagesTypeAdapter, ToolReturnPart, PartDeltaEvent, PartStartEvent, TextPart, TextPartDelta, FunctionToolCallEvent, FunctionToolResultEvent
from pydantic_ai.models.function import FunctionModel, DeltaToolCall
from pydantic_core import to_jsonable_python

K = 5
async def stream_fn(messages, info):
    done = sum(1 for m in messages for p in getattr(m, "parts", []) if isinstance(p, ToolReturnPart))
    if done < K:
        yield {0: DeltaToolCall(name="step", json_args=json.dumps({"n": done + 1}), tool_call_id=f"c{done+1}")}
        return
    for tok in ["All ", "five ", "steps ", "done."]:
        yield tok

def build():
    agent = Agent(FunctionModel(stream_function=stream_fn))
    @agent.tool_plain
    def step(n: int) -> str:
        """one step"""
        return f"step {n} ok"
    return agent

async def run_slice(history, prompt, budget_rounds):
    """Run until budget rounds of tool calls were made or the run ends. Returns (messages, done, events)."""
    agent = build()
    rounds = 0; events = []
    async with agent.iter(prompt, message_history=history or None) as run:
        async for node in run:
            if Agent.is_model_request_node(node):
                if rounds >= budget_rounds:
                    # clean boundary: the last tool returns are already in the history
                    # the request this node carries (the tool returns) is not in the history yet
                    return to_jsonable_python(list(run.all_messages()) + [node.request]), False, events
                async with node.stream(run.ctx) as s:
                    async for ev in s:
                        if isinstance(ev, PartDeltaEvent) and isinstance(ev.delta, TextPartDelta): events.append(("delta", ev.delta.content_delta))
                        elif isinstance(ev, PartStartEvent) and isinstance(ev.part, TextPart) and ev.part.content: events.append(("delta", ev.part.content))
            elif Agent.is_call_tools_node(node):
                async with node.stream(run.ctx) as s:
                    async for ev in s:
                        if isinstance(ev, FunctionToolCallEvent): events.append(("tool_call", ev.part.tool_name))
                        elif isinstance(ev, FunctionToolResultEvent): events.append(("tool_result", str(ev.part.content)))
                rounds += 1
            elif Agent.is_end_node(node):
                return to_jsonable_python(run.all_messages()), True, events
    return to_jsonable_python(run.all_messages()), True, events

async def main():
    history = None; prompt = "do the steps"; slices = 0
    while True:
        slices += 1
        hist_msgs = ModelMessagesTypeAdapter.validate_python(history) if history else None
        history, done, events = await run_slice(hist_msgs, prompt, budget_rounds=2)
        prompt = None
        print(f"slice {slices}: done={done} events={events} messages={len(history)}")
        if done: break
    assert slices == 3, slices
    text = "".join(e[1] for e in events if e[0]=="delta")
    assert text == "All five steps done.", text
    print("OK: 3 slices, resumed from history each time, final text:", text)
asyncio.run(main())
