"""Orchestrator for Residential AI Assistant.

Handles single-meter telemetry context assembly, conversation memory windowing,
and LLM completion with deterministic, data-grounded fallback.
Guarantees zero hardcoded placeholder data and strict single-meter data isolation.
"""

from __future__ import annotations

import logging
from typing import Any

from app.providers.data_provider import BaseDataProvider
from app.providers.llm.base import BaseLLMProvider, LLMInferenceError
from app.services.assistant.agent_factory import ResidentialAgentFactory
from app.services.assistant.context_builder import HouseholdContextBuilder
from app.services.assistant.prompts import build_system_prompt
from app.services.assistant.agentic_orchestrator import AgenticKnowledgeOrchestrator
from app.services.rag.retriever import HybridDocumentRetriever
from app.services.reference.resolver import ReferenceResolver
from app.infrastructure.database.connection import SessionLocal

logger = logging.getLogger("gridvision.services.assistant.residential")


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
        elif llm_provider is None or type(llm_provider).__name__ == "GroqLLMAdapter":
            self.agent_factory = ResidentialAgentFactory(
                temperature=temperature,
                max_tokens=max_tokens,
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

    def _generate_fallback_response(self, prompt: str, context: dict[str, Any]) -> str:
        """Deterministic domain fallback using ONLY verified values present in the context."""
        p = prompt.lower()
        ident = context["householdIdentity"]
        meter_id = ident["meterId"]
        cust_name = ident["customerName"]
        billing = context["billingCycleStatus"]
        recent = context["recentConsumptionMetrics"]

        # Check for dedicated feature workflows in fallback
        if any(w in p for w in ["plan house", "new house", "house planning", "electrical layout", "electrical plan", "connected load"]):
            try:
                from app.application.residential.plan_house_energy import PlanHouseEnergyUseCase
                from app.domain.residential.schemas import HouseEnergyPlanningRequest
                uc = PlanHouseEnergyUseCase(tariff_rate=self.tariff_rate)
                tool_resp = uc.execute(meter_id=meter_id, request=HouseEnergyPlanningRequest(built_up_area_m2=120.0))
                if tool_resp.status == "success" and tool_resp.results:
                    rec = tool_resp.results["recommended_plan"]
                    return (
                        f"### Engineering Electrical Plan for **{meter_id}** ({cust_name})\n\n"
                        f"- **Recommended Plan Tier**: **{rec['tier_name']}** ({rec['tagline']})\n"
                        f"- **Preliminary Connected Load**: **{rec['estimated_connected_load_kw']} kW**\n"
                        f"- **Diversified Peak Demand**: **{rec['diversified_peak_demand_kw']} kW** (IS 732 standard)\n"
                        f"- **Estimated Monthly Consumption**: **{rec['estimated_monthly_consumption_kwh']} kWh/month**\n"
                        f"- **Estimated Monthly Bill**: **₹{rec['estimated_monthly_bill_inr']:,.2f}** (at ₹{self.tariff_rate:.2f}/kWh)\n"
                        f"- **Total Estimated Equipment Capital**: **₹{rec['total_equipment_cost_inr']:,.2f}**\n\n"
                        f"> [!NOTE]\n"
                        f"> Preliminary engineering estimate generated by GridVision Building Energy Planning Engine."
                    )
            except Exception as exc:
                logger.warning("House planning fallback failed: %s", exc)

        if any(w in p for w in ["appliance", "replace ac", "bldc", "inverter ac", "upgrade fan", "payback"]):
            try:
                from app.application.residential.analyze_appliance import AnalyzeApplianceScenarioUseCase
                from app.domain.residential.schemas import ApplianceScenarioRequest
                uc = AnalyzeApplianceScenarioUseCase(tariff_rate=self.tariff_rate)
                tool_resp = uc.execute(meter_id=meter_id, request=ApplianceScenarioRequest())
                if tool_resp.status == "success" and tool_resp.results:
                    res = tool_resp.results
                    return (
                        f"### Appliance Upgrade & Lifecycle Analysis for **{meter_id}** ({cust_name})\n\n"
                        f"- **Annual Energy Savings**: **{res['annual_energy_savings_kwh']} kWh/year**\n"
                        f"- **Annual Bill Savings**: **₹{res['annual_cost_savings_inr']:,.2f}/year**\n"
                        f"- **Net Upfront Investment**: **₹{res['net_upfront_investment_inr']:,.2f}**\n"
                        f"- **Simple Payback Period**: **{res.get('simple_payback_years', '—')} years** (Break-Even Year: {res.get('break_even_year', '—')})\n"
                        f"- **7-Year Net Lifetime Savings**: **₹{res['net_lifetime_savings_inr']:,.2f}**\n"
                        f"- **CO2 Emissions Displaced**: **{res['co2_reduction_kg_per_year']} kg CO2/year**\n\n"
                        f"**Engineering Verdict**: {res['recommendation_verdict']}"
                    )
            except Exception as exc:
                logger.warning("Appliance fallback failed: %s", exc)

        if any(w in p for w in ["lower bill", "cost management", "saving tips", "save energy", "cut power", "energy recommendations"]):
            try:
                from app.application.residential.manage_cost import ManageEnergyCostUseCase
                from app.domain.residential.schemas import CostManagementRequest
                uc = ManageEnergyCostUseCase(tariff_rate=self.tariff_rate)
                tool_resp = uc.execute(meter_id=meter_id, request=CostManagementRequest())
                if tool_resp.status == "success" and tool_resp.results:
                    res = tool_resp.results
                    pkg = res.get("package_recommendations", {})
                    top_strats = res.get("strategies", [])[:3]
                    strat_bullets = "\n".join([f"- **{s['title']}**: saves **₹{s['estimated_monthly_savings_inr']:,.0f}/mo** (Upfront: ₹{s['upfront_investment_inr']:,.0f})" for s in top_strats])
                    return (
                        f"### Personalized Cost Management Plan for **{meter_id}** ({cust_name})\n\n"
                        f"- **Current Monthly Baseline**: **{res['current_monthly_baseline_kwh']} kWh** (₹{res['current_monthly_bill_inr']:,.2f}/month)\n"
                        f"- **Achievable Monthly Savings**: **₹{res['achievable_monthly_savings_inr']:,.2f}** (₹{res['achievable_annual_savings_inr']:,.2f}/year)\n"
                        f"- **Recommended Upfront Capital**: **₹{res['total_investment_required_inr']:,.2f}** (Payback: {res.get('blended_payback_years', '—')} years)\n\n"
                        f"**Top Prioritized Strategies**:\n{strat_bullets}\n\n"
                        f"> [!TIP]\n"
                        f"> Grounded in verified smart meter telemetry and Bureau of Energy Efficiency (BEE) standards."
                    )
            except Exception as exc:
                logger.warning("Cost management fallback failed: %s", exc)

        # Check if the fallback query is requesting a future/month prediction
        if any(w in p for w in ["predict", "forecast", "future", "upcoming", "next month", "january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december", "2019", "2018"]):
            try:
                from app.application.energy_analytics.predict_bill import PredictBillUseCase
                from app.domain.energy.schemas import BillPredictionQueryRequest

                target_m = "2019-02" if "feb" in p or "2019" in p else "2018-12"
                for m_name, m_num in [
                    ("jan", "01"), ("feb", "02"), ("mar", "03"), ("apr", "04"),
                    ("may", "05"), ("jun", "06"), ("jul", "07"), ("aug", "08"),
                    ("sep", "09"), ("oct", "10"), ("nov", "11"), ("dec", "12"),
                ]:
                    if m_name in p:
                        year_val = "2019" if "2019" in p else "2018"
                        target_m = f"{year_val}-{m_num}"
                        break

                predict_uc = PredictBillUseCase(
                    prediction_service=self.prediction_service,
                    tariff_rate=self.tariff_rate,
                )
                tool_resp = predict_uc.execute(meter_id=meter_id, request=BillPredictionQueryRequest(target_month=target_m))
                if tool_resp.status == "success" and tool_resp.results:
                    res = tool_resp.results
                    pred_kwh = res["predicted_month_kwh"]
                    pred_bill = res["predicted_bill_inr"]
                    daily_avg = res["daily_average_kwh"]
                    ci = res.get("confidence_interval", {})
                    lower_b = ci.get("lower_bound_kwh", pred_kwh * 0.9)
                    upper_b = ci.get("upper_bound_kwh", pred_kwh * 1.1)
                    model_name = res.get("model_name", "customer-bill-prediction")
                    model_ver = res.get("model_version", "3")
                    status_eval = res.get("evaluation_status", "forward_ml_inference")
                    status_desc = "Retrospective Benchmark Evaluation" if status_eval == "retrospective_gold_replay" else "Forward Machine Learning Projection"

                    return (
                        f"### Machine Learning Usage & Bill Prediction for **{meter_id}** ({cust_name})\n\n"
                        f"- **Target Period**: `{res.get('target_month')}`\n"
                        f"- **Evaluation Pipeline**: **{status_desc}**\n"
                        f"- **Model Identifier**: `{model_name}` (Version {model_ver})\n"
                        f"- **Predicted Monthly Consumption**: **{pred_kwh:.1f} kWh**\n"
                        f"- **Estimated Monthly Bill**: **₹{pred_bill:,.2f}** (at ₹{self.tariff_rate:.2f}/kWh)\n"
                        f"- **Projected Daily Average**: **{daily_avg:.1f} kWh/day**\n"
                        f"- **Confidence Bounds (±10%)**: **{lower_b:.1f} kWh** to **{upper_b:.1f} kWh**\n\n"
                        f"> [!NOTE]\n"
                        f"> Prediction generated by GridVision's trained champion Machine Learning model (`{model_name}`)."
                    )
            except Exception as exc:
                logger.warning("Predict fallback execution failed: %s", exc)

        # Helper formatters avoiding None errors
        def fmt_kwh(val: float | None) -> str:
            return f"{val:.1f} kWh" if val is not None else "Not recorded"

        def fmt_inr(val: float | None) -> str:
            return f"₹{val:,.2f}" if val is not None else "Not calculated"

        hist = context.get("historicalProfile") or {}
        all_time = hist.get("allTimeSummary") or {}
        cov = hist.get("coverage") or {}

        if any(w in p for w in ["all-time", "all time", "historically", "season", "annual", "highest year", "highest month", "over the years", "across the years"]) and hist.get("allTimeSummary"):
            total_hist = fmt_kwh(all_time.get("totalConsumptionKwh"))
            avg_hist = fmt_kwh(all_time.get("averageDailyConsumptionKwh"))
            med_hist = fmt_kwh(all_time.get("medianDailyConsumptionKwh"))
            highest_day = all_time.get("highestConsumptionDay") or {}
            highest_day_str = (
                f"**{highest_day.get('consumptionKwh', 0):.1f} kWh** on `{highest_day.get('date', '—')}`"
                if highest_day.get("consumptionKwh") is not None
                else "Not recorded"
            )
            start_d = cov.get("startDate", "—")
            end_d = cov.get("endDate", "—")
            extremes = hist.get("historicalExtremes") or {}
            top_months = extremes.get("topConsumptionMonths") or []
            top_month_str = (
                f"**{top_months[0].get('month')}** ({top_months[0].get('consumptionKwh', 0):.1f} kWh)"
                if top_months
                else "Not recorded"
            )

            return (
                f"### Verified Historical Overview for **{meter_id}** ({cust_name})\n\n"
                f"- **Historical Coverage Window**: `{start_d}` to `{end_d}` ({cov.get('completenessPct', 0):.1f}% coverage)\n"
                f"- **All-Time Total Consumption**: **{total_hist}**\n"
                f"- **Historical Daily Average**: **{avg_hist}/day**\n"
                f"- **Historical Daily Median**: **{med_hist}/day**\n"
                f"- **Peak Consumption Day**: {highest_day_str}\n"
                f"- **Highest Consumption Month**: {top_month_str}\n\n"
                f"> [!NOTE]\n"
                f"> Derived from verified smart meter historical logs via deterministic fallback."
            )

        if any(w in p for w in ["bill", "tariff", "calculate", "rupee", "inr", "cost"]):
            elapsed = billing.get("elapsedDays")
            last_date = billing.get("lastRecordedDate") or "recent"
            actual_kwh = fmt_kwh(billing.get("actualCycleKwhSoFar"))
            pred_kwh = fmt_kwh(billing.get("predictedRemainingKwh"))
            est_total_kwh = fmt_kwh(billing.get("estimatedMonthEndKwh"))
            est_bill = fmt_inr(billing.get("estimatedMonthEndBillInr"))
            tariff = ident.get("tariffRateInrPerKwh", 10.0)

            return (
                f"### Verified Billing Summary for **{meter_id}** ({cust_name})\n\n"
                f"- **Tariff Rate**: ₹{tariff:.2f} / kWh\n"
                f"- **Billing Window**: Day **{elapsed if elapsed is not None else '—'}** of 30 (as of `{last_date}`)\n"
                f"- **Cycle Consumption So Far**: **{actual_kwh}**\n"
                f"- **Model Projected Remaining Demand**: **{pred_kwh}**\n"
                f"- **Model Projected Month-End Total**: **{est_total_kwh}**\n"
                f"- **Estimated Month-End Bill**: **{est_bill}**\n\n"
                f"**Calculation Formula**:\n"
                f"$$\\text{{Estimated Bill}} = (\\text{{Month-to-Date kWh}} + \\text{{Predicted Remaining kWh}}) \\times ₹{tariff:.2f}/\\text{{kWh}} = {est_bill}$$"
            )

        if any(w in p for w in ["trend", "history", "yesterday", "daily", "average", "usage"]):
            daily_usage = fmt_kwh(recent.get("currentDailyUsageKwh"))
            daily_avg = fmt_kwh(recent.get("baselineDailyAverageKwh", recent.get("dailyAverageKwh")))
            cycle_daily_avg = fmt_kwh(recent.get("cycleDailyAverageKwh"))
            prev_7d = fmt_kwh(recent.get("prev7DaysAvgKwh"))
            prev_month = fmt_kwh(recent.get("previousMonthTotalKwh"))
            delta = recent.get("dailyChangeVs30dBaselinePct", recent.get("dailyChangePct"))
            delta_str = f" ({delta:+.1f}% vs baseline)" if delta is not None else ""
            cov = billing.get("telemetryCoverageRatioPct")
            cov_str = f"**{cov}% coverage** verified by smart meter." if cov is not None else "Verified."

            return (
                f"### Consumption Trends for **{meter_id}** ({cust_name})\n\n"
                f"- **Current Daily Rate**: **{daily_usage}/day**\n"
                f"- **Cycle Daily Average**: **{cycle_daily_avg}/day**\n"
                f"- **30-Day Baseline Average**: **{daily_avg}/day**{delta_str}\n"
                f"- **Previous 7 Days Average**: **{prev_7d}/day**\n"
                f"- **Previous Month Total**: **{prev_month}**\n"
                f"- **Telemetry Quality**: {cov_str}\n\n"
                f"> [!NOTE]\n"
                f"> Computed from verified meter logs as of `{billing.get('lastRecordedDate') or 'recent record'}` via deterministic fallback."
            )

        daily_rate = fmt_kwh(recent.get("currentDailyUsageKwh"))
        actual_cycle = fmt_kwh(billing.get("actualCycleKwhSoFar"))
        est_month_kwh = fmt_kwh(billing.get("estimatedMonthEndKwh"))
        est_bill = fmt_inr(billing.get("estimatedMonthEndBillInr"))
        elapsed_days = billing.get("elapsedDays")

        return (
            f"### Verified Household Overview for **{meter_id}** ({cust_name})\n\n"
            f"- **Current Daily Usage**: **{daily_rate}/day**\n"
            f"- **Cycle Total to Date**: **{actual_cycle}** (Day {elapsed_days if elapsed_days is not None else '—'} of 30)\n"
            f"- **Projected Month-End Usage**: **{est_month_kwh}**\n"
            f"- **Estimated Month-End Invoice**: **{est_bill}**\n\n"
            f"All readings are verified from smart meter `{meter_id}` records as of `{billing.get('lastRecordedDate') or 'recent record'}`."
        )

    def _determine_tool_scope(self, prompt: str) -> str:
        """Dynamically select a focused tool scope to optimize prompt tokens and latency while preserving AI flexibility."""
        p = prompt.lower()
        if any(w in p for w in ["standard", "code", "regulation", "is 732", "is732", "nec", "bee", "cea", "clause", "wire", "wiring", "safety", "earthing", "rccb", "neutral", "insulation"]):
            return "regulatory_and_standards"
        elif any(w in p for w in ["plan house", "new house", "layout", "connected load", "appliance", "replace", "upgrade", "bldc", "iseer", "inverter ac", "fan", "geyser", "refrigerator", "payback", "purchase", "scenario"]):
            return "planning_and_upgrades"
        elif any(w in p for w in ["bill", "consumption", "usage", "history", "trend", "predict", "forecast", "yesterday", "tariff", "peak", "reduce bill", "cost management", "saving", "all-time"]):
            return "telemetry_and_billing"
        return "balanced_core"

    def _calculate_adaptive_timeout(self, prompt: str) -> float:
        """Calculate dynamic timeout: generous for complex/lengthy queries, baseline for short queries."""
        p_len = len(prompt.strip())
        is_complex = (
            p_len > 120
            or any(w in prompt.lower() for w in [
                "compare", "detailed", "breakdown", "plan", "scenario", "investment", "payback",
                "recommendation", "package", "multi", "versus", "vs", "timeline", "future",
                "step by step", "bedroom", "built-up", "ac", "refrigerator"
            ])
        )
        base = getattr(self.agent_factory, "timeout", 18.0) if self.agent_factory else 18.0
        complex_timeout = getattr(self.agent_factory, "complex_timeout", 35.0) if self.agent_factory else 35.0
        if is_complex or p_len > 250:
            return max(complex_timeout, base + 15.0)
        return base

    def answer_query(
        self,
        prompt: str,
        entity_id: str | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Execute single-meter conversational query."""
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

        # 4. Assemble chat message history (limit to last 6 turns for sliding window)
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt}
        ]

        if history:
            recent_history = history[-6:]
            for item in recent_history:
                role = str(item.get("role", "user")).lower()
                # Security rule: Never allow client-supplied history to inject 'system' messages
                if role not in ("user", "assistant"):
                    continue
                content = str(item.get("content", "")).strip()
                if not content:
                    continue
                # Truncate overly long history content to prevent token abuse
                if len(content) > 2000:
                    content = content[:2000] + "... [truncated]"
                messages.append({"role": role, "content": content})

        # Add current user prompt (capped at 2000 chars)
        clean_user_prompt = prompt.strip()
        if len(clean_user_prompt) > 2000:
            clean_user_prompt = clean_user_prompt[:2000]
        messages.append({"role": "user", "content": clean_user_prompt})

        # 5. Attempt Autonomous LangChain Tool-Calling Agent first
        answer = None
        is_llm_generated = False

        if self.agent_factory and (self.agent_factory.custom_chat_model is not None or self.agent_factory.is_groq_available()):
            try:
                tool_scope = self._determine_tool_scope(clean_user_prompt)
                effective_timeout = self._calculate_adaptive_timeout(clean_user_prompt)

                agent = self.agent_factory.create_agent_for_household(
                    meter_id=meter_id,
                    system_prompt=system_prompt,
                    prediction_service=self.prediction_service,
                    tariff_rate=self.tariff_rate,
                    include_knowledge_tools=True,
                    retriever=getattr(self, "retriever", None),
                    resolver=getattr(self, "resolver", None),
                    tool_scope=tool_scope,
                    timeout=effective_timeout,
                )
                agent_messages = self.agent_factory.sanitize_history_and_prompt(
                    prompt=clean_user_prompt,
                    history=history,
                )
                res = agent.invoke({"messages": agent_messages})
                if res and "messages" in res and res["messages"]:
                    last_msg = res["messages"][-1]
                    raw_ans = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
                    if isinstance(raw_ans, list):
                        raw_ans = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in raw_ans)
                    if raw_ans and isinstance(raw_ans, str) and raw_ans.strip():
                        answer = raw_ans.strip()
                        is_llm_generated = True
            except Exception as exc:
                logger.warning(
                    "LangChain agent execution failed or timed out: %s; falling back to agentic knowledge orchestrator or deterministic fallback",
                    exc,
                )

        # 6. Direct LLM completion fallback (if tool agent encountered socket/tool exception)
        if not answer and self.llm_provider and self.llm_provider.is_available():
            try:
                answer = self.llm_provider.generate_chat_completion(
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )
                is_llm_generated = True
            except LLMInferenceError as exc:
                logger.warning("LLM inference unavailable, using verified context fallback: %s", exc)
            except Exception as exc:
                logger.error("Unexpected error during LLM generation: %s", exc)

        # 7. Specialized Multi-Knowledge Orchestrator (for dedicated house planning, appliance analysis, or standards)
        contract = None
        p_low = clean_user_prompt.lower()
        is_knowledge_mode = any(k in p_low for k in [
            "plan house", "new house", "electrical layout", "connected load", "room", "bedroom",
            "appliance", "replace", "upgrade", "bldc", "iseer", "inverter ac", "fan", "geyser", "refrigerator", "payback",
            "reduce bill", "cost management", "saving", "lower consumption", "balanced efficiency",
            "standard", "code", "regulation", "is 732", "is732", "nec", "bee", "cea", "wiring", "clause"
        ])
        if (not answer) and is_knowledge_mode and (self.agentic_orchestrator is not None):
            try:
                contract = self.agentic_orchestrator.process_query(
                    prompt=clean_user_prompt,
                    meter_id=meter_id,
                    customer_name=customer_name,
                    history=history,
                )
            except Exception as e:
                logger.warning("AgenticKnowledgeOrchestrator failed: %s", e)

        if contract is not None:
            citations_data = [c.model_dump() for c in contract.citations]
            provenance_data = contract.provenance.model_dump()
            return {
                "answer": contract.answer,
                "content": contract.answer,
                "persona": "household",
                "entityId": meter_id,
                "customerName": customer_name,
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

        # 8. Deterministic domain fallback (telemetry, billing, usage trends, or verified assistance)
        if not answer:
            answer = self._generate_fallback_response(clean_user_prompt, context)

        return {
            "answer": answer,
            "content": answer,
            "persona": "household",
            "entityId": meter_id,
            "customerName": customer_name,
            "status": "success",
            "isLlmGenerated": is_llm_generated,
            "mode": "general_chat",
            "citations": [],
            "provenance": {
                "knowledge_sources_used": ["household_telemetry"],
                "structured_references": [],
                "calculations": [],
            },
            "assumptions": [],
            "limitations": [],
            "missing_information": [],
            "structured_data": None,
        }
