"""Spike S4: does langgraph-checkpoint-mysql persist/resume across processes?

Run twice per mode — each invocation is a separate process, so a passing
'second' phase proves working memory genuinely round-trips through MySQL:

    python3 checkpoint_test.py sync first
    python3 checkpoint_test.py sync second
    python3 checkpoint_test.py async first
    python3 checkpoint_test.py async second
"""

import asyncio
import operator
import sys
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

DSN = "mysql://root@localhost:3306/scenery_spike"


def thread(mode: str) -> dict:
    return {"configurable": {"thread_id": f"spike-s4-{mode}"}}


class State(TypedDict):
    notes: Annotated[list[str], operator.add]
    turns: int


def respond(state: State) -> dict:
    n = state.get("turns", 0) + 1
    return {"notes": [f"note from turn {n}"], "turns": n}


def build():
    g = StateGraph(State)
    g.add_node("respond", respond)
    g.add_edge(START, "respond")
    g.add_edge("respond", END)
    return g


def check(phase: str, result: dict) -> None:
    expected_turns = 1 if phase == "first" else 2
    ok_turns = result["turns"] == expected_turns
    ok_notes = len(result["notes"]) == expected_turns
    ok_resume = phase == "first" or result["notes"][0] == "note from turn 1"
    print(f"{'PASS' if ok_turns else 'FAIL'}  turns == {expected_turns} (got {result['turns']})")
    print(f"{'PASS' if ok_notes else 'FAIL'}  {expected_turns} note(s) accumulated (got {len(result['notes'])})")
    if phase == "second":
        print(f"{'PASS' if ok_resume else 'FAIL'}  turn-1 note resumed from MySQL: {result['notes'][:1]}")
    if not (ok_turns and ok_notes and ok_resume):
        sys.exit(1)


def run_sync(phase: str) -> None:
    from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver

    with PyMySQLSaver.from_conn_string(DSN) as saver:
        saver.setup()
        graph = build().compile(checkpointer=saver)
        result = graph.invoke({"notes": []}, thread("sync"))
        check(phase, result)


async def run_async(phase: str) -> None:
    from langgraph.checkpoint.mysql.aio import AIOMySQLSaver

    async with AIOMySQLSaver.from_conn_string(DSN) as saver:
        await saver.setup()
        graph = build().compile(checkpointer=saver)
        result = await graph.ainvoke({"notes": []}, thread("async"))
        check(phase, result)


if __name__ == "__main__":
    mode, phase = sys.argv[1], sys.argv[2]
    print(f"--- {mode} / {phase} (fresh process) ---")
    if mode == "sync":
        run_sync(phase)
    else:
        asyncio.run(run_async(phase))
