"""Placeholder graph so LangGraph Studio (`langgraph dev`) works before M3.

Replaced by the real orchestrator at roadmap 3.1 — keep the module path and
`graph` symbol stable; langgraph.json points here.
"""

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, MessagesState, StateGraph


def respond(state: MessagesState) -> dict[str, list[AIMessage]]:
    return {
        "messages": [AIMessage(content="The Scenery orchestrator arrives at roadmap item 3.1. 🤘")]
    }


builder = StateGraph(MessagesState)
builder.add_node("respond", respond)
builder.add_edge(START, "respond")
builder.add_edge("respond", END)

graph = builder.compile()
