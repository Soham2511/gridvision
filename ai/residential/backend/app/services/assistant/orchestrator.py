"""Orchestrator for Residential AI Assistant.

Handles single-meter telemetry context assembly, conversation memory windowing,
and LLM completion with deterministic, data-grounded fallback.
Guarantees zero hardcoded placeholder data and strict single-meter data isolation.
"""

from __future__ import annotations

import json
import logging
import math
import re
import time
from typing import Any

from app.config import BaseConfig
from app.providers.data_provider import BaseDataProvider
from app.providers.llm.base import BaseLLMProvider, LLMInferenceError
from app.services.assistant.dialogue_state import (
    resolve_dialogue_context,
)
from app.services.assistant.agent_factory import ResidentialAgentFactory
from app.services.assistant.context_builder import HouseholdContextBuilder
from app.services.assistant.prompts import build_system_prompt
from app.services.assistant.agentic_orchestrator import AgenticKnowledgeOrchestrator
from app.services.rag.retriever import HybridDocumentRetriever
from app.services.reference.resolver import ReferenceResolver
from app.infrastructure.database.connection import SessionLocal
from app.services.assistant.context_manager import ConversationContextManager
from app.services.assistant.intelligent_router import IntelligentRouter
from app.services.assistant.memory_contracts import PendingQuestion, ToolExecutionReference


logger = logging.getLogger("gridvision.services.assistant.residential")


def _is_provider_rate_limit_error(error: Exception) -> bool:
    """Recognize rate-limit errors across wrapped provider exception types."""
    current: BaseException | None = error
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if (
            getattr(current, "status_code", None) == 429
            or getattr(getattr(current, "response", None), "status_code", None) == 429
        ):
            return True
        message = str(current).lower()
        if any(
            marker in message
            for marker in ("rate_limit_exceeded", "rate limit reached", "error code: 429")
        ):
            return True
        current = current.__cause__ or current.__context__
    return False


class ResidentialAssistantOrchestrator:
    """Orchestrates grounded conversational AI for a single household meter."""

    def __init__(
        self,
        data_provider: BaseDataProvider,
        llm_provider: BaseLLMProvider | None = None,
        tariff_rate: float = 10.0,
        authorized_meters: list[str] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 800,
        agent_factory: ResidentialAgentFactory | None = None,
        prediction_service: Any = None,
    ) -> None:
        self.data_provider = data_provider
        self.llm_provider = llm_provider
        self.tariff_rate = tariff_rate
        self.authorized_meters = (
            [m.upper().strip() for m in authorized_meters if m.strip()]
            if authorized_meters
            else None
        )
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.prediction_service = prediction_service
        self.context_builder = HouseholdContextBuilder(
            data_provider, tariff_rate=tariff_rate
        )
        if agent_factory is not None:
            self.agent_factory = agent_factory
        elif llm_provider is None or type(llm_provider).__name__ in ("OllamaLLMAdapter", "GroqLLMAdapter"):
            provider_name = (
                "groq" if type(llm_provider).__name__ == "GroqLLMAdapter" else "ollama"
            )
            self.agent_factory = ResidentialAgentFactory(
                temperature=temperature,
                max_tokens=max_tokens,
                model_name=getattr(llm_provider, "effective_model", None),
                base_url=(
                    getattr(llm_provider, "effective_base_url", None)
                    if provider_name == "ollama"
                    else None
                ),
                api_key=(
                    getattr(llm_provider, "effective_api_key", None)
                    if provider_name == "groq"
                    else None
                ),
                provider=provider_name,
                groq_base_url=(
                    getattr(llm_provider, "effective_base_url", None)
                    if provider_name == "groq"
                    else None
                ),
            )
        else:
            self.agent_factory = None

        try:
            self.retriever = HybridDocumentRetriever(session_factory=SessionLocal)
            self.resolver = ReferenceResolver()
            self.agentic_orchestrator = AgenticKnowledgeOrchestrator(
                retriever=self.retriever,
                resolver=self.resolver,
                context_builder=self.context_builder,
                prediction_service=prediction_service,
                tariff_rate=tariff_rate,
                llm_provider=llm_provider,
            )
        except Exception as e:
            logger.warning("Could not initialize AgenticKnowledgeOrchestrator: %s", e)
            self.agentic_orchestrator = None

        self.context_manager = ConversationContextManager()
        self.router = IntelligentRouter()


    def _synthesize_grounded_response_with_llm(
        self,
        prompt: str,
        schema_data: dict[str, Any],
        meter_id: str,
        customer_name: str,
    ) -> str | None:
        """Have the LLM formulate a natural, cohesive response grounded strictly on verified schema data."""
        if not self.llm_provider or not self.llm_provider.is_available():
            return None

        system_instruction = (
            f"You are GridVision's AI Energy Assistant for smart meter {meter_id} ({customer_name}).\n"
            f"Directly answer the user's specific query in a clear, conversational, and helpful manner.\n\n"
            f"CRITICAL GROUNDING DIRECTIVES:\n"
            f"1. You must answer ALL aspects of the user's prompt (e.g., if the user asks for current bill AND prediction for next month, address both clearly).\n"
            f"2. Every number, date, rate, and metric MUST be derived strictly from the verified data schema below. Do not invent any numbers.\n"
            f"3. Do NOT output robotic ASCII tables, rigid template placeholders, or boilerplate disclaimers.\n"
            f"4. Format currency cleanly as ₹ and electrical energy as kWh.\n"
            f"5. If 'queried_historical_telemetry' is in the schema, this represents GROUND TRUTH HISTORICAL RECORDS queried directly from the smart meter database. Clearly present the actual recorded kWh usage and bill as verified telemetry, and do NOT refer to it as a prediction or estimate.\n\n"
            f"--- VERIFIED DATA SCHEMA ---\n"
            f"{json.dumps(schema_data, indent=2, default=str)}"
        )

        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt},
        ]
        try:
            return self.llm_provider.generate_chat_completion(
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
        except Exception as exc:
            logger.warning("LLM schema synthesis failed: %s", exc)
            return None

    @staticmethod
    def _format_verified_billing_context(context: dict[str, Any]) -> str | None:
        """Format an accrued charge from recorded cycle usage when generation is unavailable."""
        billing = context.get("billingCycleStatus") or {}
        identity = context.get("householdIdentity") or {}
        provenance = context.get("dataProvenance") or {}
        cycle_kwh = billing.get("actualCycleKwhSoFar")
        tariff = identity.get("tariffRateInrPerKwh")

        try:
            cycle_kwh = float(cycle_kwh)
            tariff = float(tariff)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(cycle_kwh) or not math.isfinite(tariff):
            return None

        recorded_date = billing.get("lastRecordedDate") or provenance.get(
            "lastRecordedDate"
        )
        date_text = f" through **{recorded_date}**" if recorded_date else ""
        accrued_charge = cycle_kwh * tariff
        return (
            f"Recorded usage for this billing cycle is **{cycle_kwh:.1f} kWh**"
            f"{date_text}. At the verified tariff of **₹{tariff:.2f}/kWh**, "
            f"the accrued energy charge is **₹{accrued_charge:,.2f}**. "
            "This is based on the latest recorded meter data, not a live reading "
            "or an official invoice."
        )

    def _calculate_adaptive_timeout(self, prompt: str) -> float:
        """Calculate dynamic timeout: generous for complex/lengthy queries, baseline for short queries.

        Uses agent_factory configured timeouts (60s base / 75s complex for Ollama) rather
        than hardcoded low caps that caused premature fallback with qwen3:8b inference times.
        """
        p_len = len(prompt.strip())
        is_complex = p_len > 120
        base = getattr(self.agent_factory, "timeout", BaseConfig.ASSISTANT_TIMEOUT_SECONDS) if self.agent_factory else BaseConfig.ASSISTANT_TIMEOUT_SECONDS
        complex_timeout = getattr(self.agent_factory, "complex_timeout", getattr(BaseConfig, "ASSISTANT_COMPLEX_TIMEOUT_SECONDS", 75.0)) if self.agent_factory else getattr(BaseConfig, "ASSISTANT_COMPLEX_TIMEOUT_SECONDS", 75.0)
        if is_complex or p_len > 250:
            return complex_timeout
        return base

    def answer_query(
        self,
        prompt: str,
        entity_id: str | None = None,
        history: list[dict[str, Any]] | None = None,
        user_id: str | None = None,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute single-meter conversational query."""
        request_start_time = time.time()
        clean_id = (entity_id or "").strip()
        if not clean_id:
            logger.warning("Rejected conversational assistant query: meter entity_id was not provided.")
            return {
                "answer": (
                    "Authorization error: No smart meter identifier was provided. "
                    "Please select your authorized household meter to view your consumption details."
                ),
                "persona": "household",
                "entityId": None,
                "customerName": "Unspecified Customer",
                "status": "unauthorized",
                "isLlmGenerated": False,
            }

        num_part = clean_id.replace("METER-", "").replace("meter-", "")
        meter_id = f"METER-{num_part}"
        customer_name = f"Resident-{num_part}"

        # 1. Server-side validation against authorized meters
        if self.authorized_meters is not None:
            is_authorized = any(
                m in (meter_id.upper(), clean_id.upper(), num_part)
                for m in self.authorized_meters
            )
            if not is_authorized:
                logger.warning(
                    "Access denied: meter '%s' is not in authorized residential meters set %s",
                    clean_id,
                    self.authorized_meters,
                )
                return {
                    "answer": (
                        f"Access denied: Smart meter `{meter_id}` is not authorized for your user profile. "
                        "You cannot access telemetry belonging to another customer."
                    ),
                    "persona": "household",
                    "entityId": meter_id,
                    "customerName": customer_name,
                    "status": "unauthorized",
                    "isLlmGenerated": False,
                }

        # 2. Assemble verified household context (ONLY for this authorized meter)
        context = self.context_builder.build_context(meter_id, prompt_intent=prompt)

        # If meter does not exist in dataset, refuse to invent data
        if not context:
            return {
                "answer": (
                    f"Smart meter `{meter_id}` was not found in the verified dataset. "
                    "No readings or billing records could be retrieved for this ID."
                ),
                "persona": "household",
                "entityId": meter_id,
                "customerName": customer_name,
                "status": "not_found",
                "isLlmGenerated": False,
            }

        context_json = self.context_builder.format_as_prompt_block(context)
        last_recorded = context["billingCycleStatus"].get("lastRecordedDate") or "recent record"

        # 3. Build system prompt with strict grounding, temporal binding, and data isolation directives
        system_prompt = build_system_prompt(
            customer_name=customer_name,
            meter_id=meter_id,
            context_json=context_json,
            tariff_rate=context["householdIdentity"]["tariffRateInrPerKwh"],
            last_recorded_date=last_recorded,
        )

        # Active user prompt is preserved at full fidelity (never truncated)
        clean_user_prompt = prompt.strip()

        # Resolve trusted customer identity for memory isolation
        auth_user_id = (user_id or "").strip() or f"usr-{num_part}"

        # Context manager assembles the 7 layers of context
        turn_ctx = self.context_manager.assemble_context(
            user_id=auth_user_id,
            meter_id=meter_id,
            customer_name=customer_name,
            tariff_rate=context["householdIdentity"]["tariffRateInrPerKwh"],
            prompt=clean_user_prompt,
            history=history,
            conversation_id=conversation_id,
        )
        resolved_state = turn_ctx.resolved_state
        classified_intent = self.router.classify_intent(
            prompt=resolved_state.effective_prompt or clean_user_prompt,
            llm_provider=self.llm_provider,
            history=turn_ctx.recent_messages,
        )
        routing_plan = self.router.create_routing_plan(
            prompt=clean_user_prompt,
            resolved_state=resolved_state,
            active_state=turn_ctx.active_state,
            classified_intent=classified_intent,
        )
        if routing_plan.primary_intent == "classification_unavailable":
            return {
                "answer": (
                    "I couldn't confidently route this request with the residential assistant, "
                    "so I did not call a data tool or create an estimate. No unverified answer was generated; please try again."
                ),
                "persona": "household",
                "entityId": meter_id,
                "customerName": customer_name,
                "conversationId": turn_ctx.conversation_id,
                "status": "error",
                "isLlmGenerated": False,
            }
        effective_prompt = routing_plan.effective_prompt
        tool_scope = routing_plan.resolved_tool_scope
        is_continuation = routing_plan.is_continuation

        # Grounding block with verified customer profile, persistent memories, active state, and summaries
        enriched_system_prompt = system_prompt + "\n\n" + turn_ctx.grounding_system_block

        # 4. Assemble chat message history (compacted recent turns)
        messages: list[dict[str, str]] = [
            {"role": "system", "content": enriched_system_prompt}
        ]
        compacted_history = turn_ctx.recent_messages
        messages.extend(compacted_history)
        messages.append({"role": "user", "content": effective_prompt})

        # 5. Attempt Autonomous LangChain Tool-Calling Agent first
        answer = None
        is_llm_generated = False
        rate_limit_encountered = False
        required_tool_execution_failed = False
        direct_rag_intents = {
            "regulatory_standards_rag",
            "electricity_knowledge_rag",
        }

        if (
            tool_scope != "context_only"
            and self.agent_factory
            and (
                self.agent_factory.custom_chat_model is not None
                or self.agent_factory.is_available()
            )
        ):
            try:
                effective_timeout = self._calculate_adaptive_timeout(effective_prompt)

                agent_messages = self.agent_factory.sanitize_history_and_prompt(
                    prompt=effective_prompt,
                    history=compacted_history,
                )
                model_candidates = self.agent_factory.groq_model_candidates() or [None]
                fallback_api_keys = self.agent_factory.groq_fallback_api_keys()
                model_api_candidates = [
                    (model_override, api_key_override)
                    for model_override in model_candidates
                    for api_key_override in (None, *fallback_api_keys)
                ]
                res = None
                for candidate_index, (model_override, api_key_override) in enumerate(
                    model_api_candidates
                ):
                    try:
                        agent = self.agent_factory.create_agent_for_household(
                            meter_id=meter_id,
                            system_prompt=enriched_system_prompt,
                            prediction_service=self.prediction_service,
                            tariff_rate=self.tariff_rate,
                            include_knowledge_tools=True,
                            retriever=getattr(self, "retriever", None),
                            resolver=getattr(self, "resolver", None),
                            tool_scope=tool_scope,
                            recommended_tools=routing_plan.recommended_tools,
                            routed_tool_arguments=routing_plan.routed_tool_arguments,
                            requires_tool_execution=routing_plan.requires_tool_execution,
                            timeout=effective_timeout,
                            model_override=model_override,
                            api_key_override=api_key_override,
                        )
                        res = agent.invoke({"messages": agent_messages})
                        break
                    except Exception as exc:
                        is_rate_limited = _is_provider_rate_limit_error(exc)
                        rate_limit_encountered = is_rate_limited
                        has_fallback = candidate_index + 1 < len(model_api_candidates)
                        if not is_rate_limited or not has_fallback:
                            raise
                        next_model, next_api_key = model_api_candidates[candidate_index + 1]
                        logger.warning(
                            "Groq tool-calling request was rate limited; retrying "
                            "with model '%s' and %s.",
                            next_model or self.agent_factory.model_name,
                            "the secondary API key" if next_api_key else "the primary API key",
                        )
                if res and "messages" in res and res["messages"]:
                    tool_messages = [
                        message for message in res["messages"]
                        if getattr(message, "type", None) == "tool"
                    ]
                    completed_tool_names = {
                        getattr(message, "name", None) for message in tool_messages
                    }
                    if routing_plan.requires_tool_execution:
                        expected_tool_ran = (
                            bool(completed_tool_names.intersection(routing_plan.recommended_tools))
                            if routing_plan.recommended_tools
                            else bool(completed_tool_names)
                        )
                        if not expected_tool_ran:
                            raise RuntimeError(
                                "The required routed tool did not execute before the model answered."
                            )
                        for tool_message in tool_messages:
                            try:
                                tool_result = json.loads(str(tool_message.content))
                            except (TypeError, ValueError):
                                continue
                            if isinstance(tool_result, dict) and (
                                tool_result.get("error")
                                or str(tool_result.get("status", "")).lower()
                                in {"error", "failed", "unavailable"}
                            ):
                                raise RuntimeError(
                                    "A required residential tool returned an error; its result cannot be replaced with an estimate."
                                )
                    last_msg = res["messages"][-1]
                    raw_ans = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
                    if isinstance(raw_ans, list):
                        raw_ans = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in raw_ans)
                    if raw_ans and isinstance(raw_ans, str) and raw_ans.strip():
                        answer = raw_ans.strip()
                        is_llm_generated = True
            except Exception as exc:
                required_tool_execution_failed = routing_plan.requires_tool_execution
                logger.warning(
                    "LangChain tool-calling agent failed or timed out: %s",
                    exc,
                )
        elif (
            routing_plan.requires_tool_execution
            and not routing_plan.primary_intent.startswith("answer_")
        ):
            required_tool_execution_failed = True
            logger.warning(
                "Required tool route '%s' was skipped because the assistant model is unavailable.",
                routing_plan.primary_intent,
            )

        # 6. Direct LLM completion fallback (ONLY if not rate-limited and within budget)
        time_elapsed = time.time() - request_start_time
        max_budget = getattr(BaseConfig, "ASSISTANT_COMPLEX_TIMEOUT_SECONDS", 75.0)
        if (
            not answer
            and routing_plan.primary_intent != "current_billing_summary"
            and not routing_plan.requires_tool_execution
            and (
                tool_scope != "context_only"
                or routing_plan.primary_intent
                in {
                    "current_billing_summary",
                    "conversation_continuation",
                    "general_chat",
                    "irrelevant",
                }
            )
            and not rate_limit_encountered
            and time_elapsed < max_budget
            and self.llm_provider
            and self.llm_provider.is_available()
            and (
                tool_scope != "context_only"
                or routing_plan.primary_intent
                in {
                    "current_billing_summary",
                    "conversation_continuation",
                    "general_chat",
                    "irrelevant",
                }
            )
        ):
            try:
                answer = self.llm_provider.generate_chat_completion(
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )
                if answer and answer.strip():
                    is_llm_generated = True
            except LLMInferenceError as exc:
                logger.warning("LLM inference unavailable, using verified context fallback: %s", exc)
            except Exception as exc:
                logger.error("Unexpected error during LLM generation: %s", exc)

        if (
            routing_plan.primary_intent == "current_billing_summary"
            and tool_scope == "context_only"
        ):
            answer = answer or self._format_verified_billing_context(context)

        # 7. Specialized Multi-Knowledge Orchestrator (for dedicated house planning, appliance analysis, or standards)
        time_elapsed = time.time() - request_start_time
        contract = None
        is_knowledge_mode = routing_plan.primary_intent in direct_rag_intents
        if (
            (not answer)
            and is_knowledge_mode
            and (time_elapsed < max_budget)
            and (self.agentic_orchestrator is not None)
        ):
            try:
                contract = self.agentic_orchestrator.process_query(
                    prompt=effective_prompt,
                    meter_id=meter_id,
                    customer_name=customer_name,
                    history=history,
                    explicit_mode=resolved_state.resolved_mode if is_continuation else None,
                    classified_intent=routing_plan.primary_intent,
                )
            except Exception as e:
                logger.warning("AgenticKnowledgeOrchestrator failed: %s", e)

        if contract is not None:
            citations_data = [c.model_dump() for c in contract.citations]
            provenance_data = contract.provenance.model_dump()
            ans_text = contract.answer

            # Track pending question in active state if assistant asks the customer for required information
            ans_low = ans_text.lower()
            if any(q in ans_low for q in ["which city", "property located", "what city is your property"]):
                turn_ctx.active_state.awaiting_user_response = True
                turn_ctx.active_state.pending_question = PendingQuestion(
                    field="location_city",
                    question="Which city is your property located in?",
                    expected_response_type="string",
                    workflow="house_planning",
                )
                self.context_manager.repository.update_session_state(
                    conversation_id=turn_ctx.conversation_id,
                    user_id=turn_ctx.user_id,
                    active_state=turn_ctx.active_state,
                )
            elif any(q in ans_low for q in ["how many bedrooms", "how many rooms do you need"]):
                turn_ctx.active_state.awaiting_user_response = True
                turn_ctx.active_state.pending_question = PendingQuestion(
                    field="bedrooms_count",
                    question="How many bedrooms do you have?",
                    expected_response_type="integer",
                    workflow="house_planning",
                )
                self.context_manager.repository.update_session_state(
                    conversation_id=turn_ctx.conversation_id,
                    user_id=turn_ctx.user_id,
                    active_state=turn_ctx.active_state,
                )

            gen_title = None
            try:
                self.context_manager.repository.save_message(
                    conversation_id=turn_ctx.conversation_id,
                    user_id=turn_ctx.user_id,
                    role="user",
                    content=clean_user_prompt,
                    mode=contract.mode,
                )
                self.context_manager.repository.save_message(
                    conversation_id=turn_ctx.conversation_id,
                    user_id=turn_ctx.user_id,
                    role="assistant",
                    content=ans_text,
                    mode=contract.mode,
                )
                # Auto-generate meaningful conversation title on initial interaction
                gen_title = self.context_manager.repository.auto_generate_session_title(
                    conversation_id=turn_ctx.conversation_id,
                    user_id=turn_ctx.user_id,
                    first_user_message=clean_user_prompt,
                    first_assistant_message=ans_text,
                )
            except Exception as exc:
                logger.warning("Could not persist conversation messages: %s", exc)

            return {
                "answer": contract.answer,
                "content": contract.answer,
                "persona": "household",
                "entityId": meter_id,
                "customerName": customer_name,
                "conversationId": turn_ctx.conversation_id,
                "conversationTitle": gen_title or "New Chat",
                "status": contract.status,
                "isLlmGenerated": False,
                "mode": contract.mode,
                "citations": citations_data,
                "provenance": provenance_data,
                "assumptions": contract.assumptions,
                "limitations": contract.limitations,
                "missing_information": contract.missing_information,
                "structured_data": contract.structured_data,
            }

        # 8. Schema-grounded response synthesis (ALWAYS formulated by LLM if available)
        if not answer:
            if routing_plan.requires_tool_execution:
                required_tool_execution_failed = True
                if rate_limit_encountered:
                    answer = (
                        "The assistant's model provider is currently rate-limited, and I "
                        "could not complete a verified tool lookup. No unverified answer "
                        "was generated; please retry shortly."
                    )
                else:
                    answer = (
                        "I couldn't complete the required verified data lookup because "
                        "the assistant model or selected energy tool did not finish "
                        "successfully. No unverified answer was generated; please try again."
                    )
            else:
                required_tool_execution_failed = True
                answer = (
                    "The residential language model could not produce a verified response. "
                    "No estimate was substituted; please try again."
                )

        is_relevant = classified_intent != "irrelevant"
        final_mode = (
            resolved_state.resolved_mode
            if is_continuation and resolved_state.resolved_mode
            else ("general_chat" if is_relevant else "irrelevant")
        )
        relevance_val = "relevant" if is_relevant else "irrelevant"
        status_val = "error" if required_tool_execution_failed else "success"

        if answer:
            answer = re.sub(r"Before[\s\u202f]+vs\.?[\s\u202f]+After", "Before vs. After", answer, flags=re.IGNORECASE)

        # Track pending question in active state if assistant asks the customer for required information
        ans_low = (answer or "").lower()
        if any(q in ans_low for q in ["which city", "property located", "what city is your property"]):
            turn_ctx.active_state.awaiting_user_response = True
            turn_ctx.active_state.pending_question = PendingQuestion(
                field="location_city",
                question="Which city is your property located in?",
                expected_response_type="string",
                workflow="house_planning",
            )
            self.context_manager.repository.update_session_state(
                conversation_id=turn_ctx.conversation_id,
                user_id=turn_ctx.user_id,
                active_state=turn_ctx.active_state,
            )
        elif any(q in ans_low for q in ["how many bedrooms", "how many rooms do you need"]):
            turn_ctx.active_state.awaiting_user_response = True
            turn_ctx.active_state.pending_question = PendingQuestion(
                field="bedrooms_count",
                question="How many bedrooms do you have?",
                expected_response_type="integer",
                workflow="house_planning",
            )
            self.context_manager.repository.update_session_state(
                conversation_id=turn_ctx.conversation_id,
                user_id=turn_ctx.user_id,
                active_state=turn_ctx.active_state,
            )

        gen_title = None
        try:
            self.context_manager.repository.save_message(
                conversation_id=turn_ctx.conversation_id,
                user_id=turn_ctx.user_id,
                role="user",
                content=clean_user_prompt,
                mode=final_mode,
            )
            self.context_manager.repository.save_message(
                conversation_id=turn_ctx.conversation_id,
                user_id=turn_ctx.user_id,
                role="assistant",
                content=answer or "",
                mode=final_mode,
            )
            # Auto-generate meaningful conversation title on initial interaction
            gen_title = self.context_manager.repository.auto_generate_session_title(
                conversation_id=turn_ctx.conversation_id,
                user_id=turn_ctx.user_id,
                first_user_message=clean_user_prompt,
                first_assistant_message=answer,
            )
        except Exception as exc:
            logger.warning("Could not persist conversation messages: %s", exc)

        return {
            "answer": answer,
            "content": answer,
            "persona": "household",
            "entityId": meter_id,
            "customerName": customer_name,
            "conversationId": turn_ctx.conversation_id,
            "conversationTitle": gen_title or "New Chat",
            "status": status_val,
            "relevance": relevance_val,
            "isLlmGenerated": is_llm_generated,
            "mode": final_mode,
            "citations": [],
            "provenance": {
                "knowledge_sources_used": ["household_telemetry"] if is_relevant else ["domain_scope_guard"],
                "structured_references": [],
                "calculations": [],
            },
            "assumptions": [],
            "limitations": [] if is_relevant else ["Out-of-scope query: Question does not relate to residential electricity, billing, or appliance standards."],
            "missing_information": [],
            "structured_data": None,
        }
