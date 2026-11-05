"""Classify a user question and dispatch it to an existing GridVision assistant."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ANOMALY_EXAMPLES = PROJECT_ROOT / "ai" / "anamoly" / "demo_queries.txt"
GOVT_EXAMPLES = (
    PROJECT_ROOT
    / "ai"
    / "Govt_interpretion+redistribution_plan"
    / "docs"
    / "QUERY_EXAMPLES.md"
)

ROUTE_SCHEMA = {
    "type": "object",
    "properties": {
        "assistant": {"type": "string", "enum": ["anomaly", "government", "clarify"]},
        "reason": {"type": "string"},
    },
    "required": ["assistant", "reason"],
    "additionalProperties": False,
}

ROUTER_SYSTEM_PROMPT = """You are the domain router for GridVision. Select which existing assistant
should handle the user's request. Return only JSON matching the supplied schema.

Choose anomaly for anomaly detection, saved anomaly runs/events, customer impact,
outages, voltage/power quality events, root cause or rectification, anomaly model
execution, anomaly exports, and anomaly safety or general knowledge.

Choose government for the 2018 government-grid demand dataset, predicted or
historical government demand, grid IDs, redistribution plans, synthetic supply,
surplus/deficit, grid-to-grid transfers, transmission losses, and government
forecast CSV or image outputs.

Use examples as routing guidance only. A date by itself does not identify a
domain. If the question gives no usable domain signal and prior context does not
resolve it, select clarify. Do not answer the user's question or invent facts.
"""


@dataclass(frozen=True)
class AssistantRoute:
    assistant: str
    reason: str


def _example_context() -> str:
    sections: list[str] = []
    for label, path in (
        ("Anomaly assistant examples", ANOMALY_EXAMPLES),
        ("Government assistant examples", GOVT_EXAMPLES),
    ):
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            content = ""
        if content:
            sections.append(f"{label}:\n{content[:5000]}")
    return "\n\n".join(sections)


def route_query(
    query: str,
    *,
    model: str | None = None,
    ollama_url: str | None = None,
    prior_context: str | None = None,
) -> AssistantRoute:
    """Use local Ollama to choose the assistant, grounded in both query guides."""
    if not query.strip():
        raise ValueError("Please enter a non-empty question.")
    model = model or os.getenv("GRIDVISION_ROUTER_MODEL", "qwen3:8b")
    ollama_url = (
        ollama_url
        or os.getenv("GRIDVISION_ROUTER_OLLAMA_URL")
        or os.getenv("GRIDVISION_ANOMALY_OLLAMA_BASE_URL")
        or os.getenv("OLLAMA_HOST", "http://localhost:11434")
    ).rstrip("/")
    user_payload = {
        "user_question": query,
        "prior_context": prior_context or "",
        "query_examples_and_documentation": _example_context(),
    }
    payload = json.dumps(
        {
            "model": model,
            "stream": False,
            "format": ROUTE_SCHEMA,
            "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{ollama_url}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = json.loads(response.read().decode("utf-8"))
        result_text = body.get("message", {}).get("content")
        result = json.loads(result_text) if isinstance(result_text, str) else None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Ollama query routing failed at {ollama_url}. Check that Ollama is running "
            f"and model {model!r} is available."
        ) from exc
    if not isinstance(result, dict) or result.get("assistant") not in {
        "anomaly",
        "government",
        "clarify",
    } or not isinstance(result.get("reason"), str):
        raise RuntimeError("Ollama returned an invalid assistant route.")
    return AssistantRoute(result["assistant"], result["reason"].strip())


def _ask_anomaly(
    query: str,
    *,
    persona: str,
    conversation_id: str | None,
) -> str:
    # backend/app imports use `app` as their package name.
    backend_dir = str(PROJECT_ROOT / "backend")
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
    try:
        from app import create_app
    except ImportError as exc:
        raise RuntimeError(
            "The anomaly assistant requires the backend dependencies. Install the "
            "project requirements before using this route."
        ) from exc
    application = create_app()
    with application.app_context():
        service = application.extensions["assistant_service"]
        result = service.answer_query(
            query,
            persona=persona,
            conversation_id=conversation_id,
        )
    return str(result["answer"])


def dispatch_query(
    query: str,
    *,
    route: AssistantRoute,
    persona: str = "government",
    conversation_id: str | None = None,
) -> str:
    """Dispatch the classified request to the selected existing assistant."""
    if route.assistant == "clarify":
        return (
            "Should I answer this as a question about anomaly events and power quality, "
            "or about government-grid demand and redistribution plans?"
        )
    if route.assistant == "anomaly":
        return _ask_anomaly(
            query,
            persona=persona,
            conversation_id=conversation_id,
        )
    government_module = importlib.import_module(
        "ai.Govt_interpretion+redistribution_plan.assistant.assistant"
    )
    result = government_module.handle_user_query(query, provider="ollama")
    return result.text


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Route a question to the GridVision anomaly or government assistant."
    )
    parser.add_argument("--query", help="Ask one question, then exit.")
    parser.add_argument("--router-model", help="Ollama model used for domain routing.")
    parser.add_argument("--ollama-url", help="Ollama base URL for the router.")
    parser.add_argument("--persona", default="government")
    parser.add_argument("--conversation-id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    query = args.query
    if query is None:
        print("GridVision assistant router. Enter 'exit' to quit.")
        while True:
            try:
                query = input("\nYou: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            if query.lower() in {"exit", "quit"}:
                return 0
            if not query:
                continue
            try:
                selected = route_query(query, model=args.router_model, ollama_url=args.ollama_url)
                answer = dispatch_query(
                    query,
                    route=selected,
                    persona=args.persona,
                    conversation_id=args.conversation_id,
                )
            except (RuntimeError, ValueError, OSError) as exc:
                print(f"Router error: {exc}", file=sys.stderr)
                continue
            print(f"\nAssistant ({selected.assistant}): {answer}")
        
    try:
        selected = route_query(query, model=args.router_model, ollama_url=args.ollama_url)
        print(f"Route: {selected.assistant} — {selected.reason}")
        print(
            dispatch_query(
                query,
                route=selected,
                persona=args.persona,
                conversation_id=args.conversation_id,
            )
        )
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"Router error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
