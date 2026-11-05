"""Interactive terminal entry point for the Commercial AI workflow."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, TextIO
from uuid import uuid4

from dotenv import load_dotenv

from ai.commercial.config.settings import CommercialSettings
from ai.commercial.graph import (
    CommercialWorkflow,
    WorkflowExecutionError,
    build_commercial_graph,
)
from ai.commercial.agents.planner import GroqPlanner, GroqPlannerError
from ai.commercial.schemas.communication import CommercialConversationMessage

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _print_trace(events: list[dict[str, Any]], *, file: TextIO) -> None:
    if not events:
        return
    print("Workflow trace:", file=file)
    for event in events:
        message = f" - {event['message']}" if event.get("message") else ""
        print(
            f"  {event['node_id']}: {event['status']} "
            f"({event['duration_ms']:.1f} ms){message}",
            file=file,
        )


def run_chat(workflow: CommercialWorkflow) -> None:
    """Run a line-oriented chat session using a compiled Commercial workflow."""
    conversation_history: list[CommercialConversationMessage] = []
    while True:
        try:
            user_goal = input("You: ").strip()
        except KeyboardInterrupt:
            print("\nChat interrupted.")
            return
        except EOFError:
            print()
            return

        if user_goal.lower() in {"exit", "quit"}:
            return
        if not user_goal:
            continue

        print(
            "Working... Press Ctrl+C to cancel the current request.",
            file=sys.stderr,
            flush=True,
        )
        try:
            result = workflow.invoke(
                {
                    "request_id": str(uuid4()),
                    "factory_id": "automotive-parts-demo",
                    "user_goal": user_goal,
                    "conversation_history": conversation_history[-8:],
                }
            )
        except KeyboardInterrupt:
            print("\nRequest cancelled.", file=sys.stderr)
            return
        except WorkflowExecutionError as exc:
            logger.exception(
                "Commercial workflow failed at node %s",
                exc.failed_node,
            )
            print(
                f"Workflow failed at {exc.failed_node} ({exc.error_type}).",
                file=sys.stderr,
            )
            _print_trace(exc.execution_trace, file=sys.stderr)
            continue
        except Exception:
            logger.exception("Commercial workflow failed")
            print(
                "Workflow failed; see the terminal traceback above.",
                file=sys.stderr,
            )
            continue

        response = result["final_response"]
        print(f"\nAssistant: {response['summary']}")
        for finding in response.get("findings", []):
            print(f"- {finding}")
        conversation_history = [
            *conversation_history,
            CommercialConversationMessage(role="user", content=user_goal),
            CommercialConversationMessage(
                role="assistant",
                content=str(response["summary"])[:2000],
            ),
        ][-8:]
        if response.get("errors"):
            print("Workflow notes:")
            for error in response["errors"]:
                print(f"- {error}")
        _print_trace(result.get("execution_trace", []), file=sys.stderr)
        print()


def check_groq_connection(settings: CommercialSettings) -> int:
    """Make one minimal real planner request without starting Flask or RAG."""
    planner = GroqPlanner(
        api_key_file=settings.groq_api_key_file,
        base_url=settings.groq_base_url,
        model=settings.groq_model,
        timeout_seconds=settings.groq_timeout_seconds,
    )
    print(f"Groq endpoint: {planner.endpoint_url}")
    print(f"Groq model: {settings.groq_model}")
    print(f"API key file: {settings.groq_api_key_file} (value hidden)")
    try:
        specialists = planner.select_specialists(
            "Which specialist handles factory maintenance documents?"
        )
    except GroqPlannerError as exc:
        print(f"Groq connection check failed: {exc}", file=sys.stderr)
        return 1
    print("Groq connection check passed.")
    print(f"Planner selected: {', '.join(specialists)}")
    return 0


def main() -> None:
    """Load local settings and run either a Groq check or terminal chat."""
    parser = argparse.ArgumentParser(description="Commercial AI terminal tools.")
    parser.add_argument(
        "--check-groq",
        action="store_true",
        help="Test the configured Groq key, model, and planner request; do not start chat.",
    )
    arguments = parser.parse_args()
    load_dotenv(PROJECT_ROOT / ".env")
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
        force=True,
    )
    settings = CommercialSettings.from_env()
    if arguments.check_groq:
        raise SystemExit(check_groq_connection(settings))
    workflow = build_commercial_graph(settings=settings)
    print("Commercial AI terminal chat. Type 'exit' or 'quit' to leave.")
    run_chat(workflow)


if __name__ == "__main__":
    main()
