"""Classify a user question and dispatch it to an existing GridVision assistant."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
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

A date by itself does not identify a domain. If the question gives no usable
domain signal and prior context does not resolve it, select clarify. Do not
answer the user's question or invent facts.
"""

ANOMALY_INTENT = re.compile(
    r"\b(anomal(?:y|ies)|outage|voltage|power quality|root cause|"
    r"rectification|anomaly detection)\b",
    re.IGNORECASE,
)
GOVERNMENT_INTENT = re.compile(
    r"\b(government|grid(?:s)?|redistribution|energy demand|demand forecast|"
    r"historical demand|surplus|deficit|transmission loss(?:es)?|grid transfer)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class AssistantRoute:
    assistant: str
    reason: str


def route_query(
    query: str,
    *,
    model: str | None = None,
    ollama_url: str | None = None,
    prior_context: str | None = None,
    default_assistant: str | None = None,
) -> AssistantRoute:
    """Route clear intents directly and use Ollama for ambiguous requests."""
    if not query.strip():
        raise ValueError("Please enter a non-empty question.")
    if default_assistant not in {None, "anomaly", "government", "clarify"}:
        raise ValueError("default_assistant must be a supported assistant route.")

    # Route explicit domain requests without spending time on a second model
    # call. The Government page also supplies its persona as the safe default
    # for ordinary questions that do not mention either domain explicitly.
    anomaly_intent = ANOMALY_INTENT.search(query)
    government_intent = GOVERNMENT_INTENT.search(query)
    if anomaly_intent and not government_intent:
        return AssistantRoute(
            "anomaly", "The question explicitly asks about power anomalies."
        )
    if government_intent and not anomaly_intent:
        return AssistantRoute(
            "government", "The question explicitly asks about government-grid data."
        )
    if default_assistant is not None:
        if anomaly_intent:
            return AssistantRoute(
                "anomaly", "The question explicitly asks about power anomalies."
            )
        return AssistantRoute(
            default_assistant, "Using the Government page's configured default route."
        )

    model = model or os.getenv("GRIDVISION_ROUTER_MODEL", "qwen3:8b")
    ollama_url = (
        ollama_url
        or os.getenv("GRIDVISION_ROUTER_OLLAMA_URL")
        or os.getenv("GRIDVISION_ANOMALY_OLLAMA_BASE_URL")
        or os.getenv("OLLAMA_HOST", "http://localhost:11434")
    ).rstrip("/")
    # Long README and examples pasted into every request made local routing
    # needlessly slow (the previous prompt timed out after 120 seconds). Keep
    # routing inputs compact; the policy and representative intents are already
    # stated in the system prompt.
    user_payload = {
        "user_question": query[:4000],
        "prior_context": (prior_context or "")[-1500:],
    }
    payload = json.dumps(
        {
            "model": model,
            "stream": False,
            "think": False,
            "format": ROUTE_SCHEMA,
            "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 128},
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
        with urllib.request.urlopen(request, timeout=60) as response:
            body = json.loads(response.read().decode("utf-8"))
        result_text = body.get("message", {}).get("content")
        result = json.loads(result_text) if isinstance(result_text, str) else None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        reason = "timed out" if isinstance(exc, TimeoutError) else "failed"
        raise RuntimeError(
            f"Ollama query routing {reason} at {ollama_url} using model {model!r}: {exc}"
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
