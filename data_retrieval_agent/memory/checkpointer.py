"""Process-local LangGraph checkpointer."""

def create_checkpointer():
    try:
        from langgraph.checkpoint.memory import InMemorySaver
    except ImportError as exc:
        raise RuntimeError("LangGraph is required for session memory.") from exc
    return InMemorySaver()
