"""LangChain tool registry and factory for residential energy assistant."""

from __future__ import annotations

import logging
from typing import Any, Optional
from langchain_core.tools import BaseTool

from app.application.energy_analytics.analyze_peaks import AnalyzePeaksUseCase
from app.application.energy_analytics.breakdown_consumption import (
    BreakdownConsumptionUseCase,
)
from app.application.energy_analytics.compare_periods import (
    ComparePeriodsUseCase,
)
from app.application.energy_analytics.generate_forecast import (
    GenerateForecastUseCase,
)
from app.application.energy_analytics.predict_bill import (
    PredictBillUseCase,
)
from app.application.energy_analytics.query_consumption import (
    QueryConsumptionUseCase,
)
from app.application.residential.analyze_appliance import AnalyzeApplianceScenarioUseCase
from app.application.residential.manage_cost import ManageEnergyCostUseCase
from app.application.residential.plan_house_energy import PlanHouseEnergyUseCase
from app.domain.energy.analytics_engine import EnergyAnalyticsEngine
from app.infrastructure.repositories.household_energy_repository import (
    BaseHouseholdEnergyRepository,
    HouseholdEnergyRepository,
)
from app.interfaces.assistant.tools.breakdown_tools import (
    GetConsumptionBreakdownTool,
)
from app.interfaces.assistant.tools.comparison_tools import (
    CompareConsumptionPeriodsTool,
)
from app.interfaces.assistant.tools.consumption_tools import (
    QueryConsumptionHistoryTool,
)
from app.interfaces.assistant.tools.customer_context_tools import (
    GetCustomerApplianceInventoryTool,
    GetCustomerPremisesProfileTool,
)
from app.interfaces.assistant.tools.forecast_tools import (
    ForecastConsumptionTool,
)
from app.interfaces.assistant.tools.peak_tools import (
    GetPeakConsumptionPeriodsTool,
)
from app.interfaces.assistant.tools.prediction_tools import (
    PredictUsageAndBillTool,
)
from app.interfaces.assistant.tools.rag_tools import (
    GetDocumentClauseTool,
    SearchRegulatoryDocumentsTool,
)
from app.interfaces.assistant.tools.residential_feature_tools import (
    AnalyzeApplianceScenarioTool,
    ManageEnergyCostTool,
    PlanHouseEnergyTool,
)
from app.interfaces.assistant.tools.structured_reference_tools import (
    LookupApplianceBenchmarkTool,
    LookupGridEmissionFactorTool,
    ResolveReferenceParameterTool,
)
from app.models.customer_bill_prediction.service import CustomerBillPredictionService
from app.services.rag.retriever import HybridDocumentRetriever
from app.services.reference.resolver import ReferenceResolver

logger = logging.getLogger("gridvision.interfaces.assistant.tools.registry")


def create_residential_tools(
    authorized_meter_id: str,
    repository: BaseHouseholdEnergyRepository | None = None,
    analytics_engine: EnergyAnalyticsEngine | None = None,
    prediction_service: CustomerBillPredictionService | None = None,
    tariff_rate: float = 10.0,
    include_knowledge_tools: bool = False,
    retriever: Optional[HybridDocumentRetriever] = None,
    resolver: Optional[ReferenceResolver] = None,
) -> list[BaseTool]:
    """Create and return the set of LangChain tools bound strictly to the authorized meter ID.

    The LLM has zero authority to supply or modify the meter ID; it is injected server-side.
    If include_knowledge_tools=True, adds Document RAG, Structured Reference, and Customer Context tools.
    """
    repo = repository or HouseholdEnergyRepository()
    engine = analytics_engine or EnergyAnalyticsEngine()

    # Analytics use cases
    query_uc = QueryConsumptionUseCase(repository=repo, analytics_engine=engine)
    compare_uc = ComparePeriodsUseCase(repository=repo, analytics_engine=engine)
    breakdown_uc = BreakdownConsumptionUseCase(repository=repo, analytics_engine=engine)
    peaks_uc = AnalyzePeaksUseCase(repository=repo, analytics_engine=engine)
    forecast_uc = GenerateForecastUseCase(
        repository=repo, analytics_engine=engine, tariff_rate=tariff_rate
    )
    predict_bill_uc = PredictBillUseCase(
        repository=repo,
        prediction_service=prediction_service,
        analytics_engine=engine,
        tariff_rate=tariff_rate,
    )

    # Dedicated feature use cases
    house_plan_uc = PlanHouseEnergyUseCase(repository=repo, tariff_rate=tariff_rate)
    appliance_uc = AnalyzeApplianceScenarioUseCase(repository=repo, tariff_rate=tariff_rate)
    cost_mgmt_uc = ManageEnergyCostUseCase(repository=repo, tariff_rate=tariff_rate)

    tools: list[BaseTool] = [
        QueryConsumptionHistoryTool(
            authorized_meter_id=authorized_meter_id,
            use_case=query_uc,
        ),
        CompareConsumptionPeriodsTool(
            authorized_meter_id=authorized_meter_id,
            use_case=compare_uc,
        ),
        GetConsumptionBreakdownTool(
            authorized_meter_id=authorized_meter_id,
            use_case=breakdown_uc,
        ),
        GetPeakConsumptionPeriodsTool(
            authorized_meter_id=authorized_meter_id,
            use_case=peaks_uc,
        ),
        ForecastConsumptionTool(
            authorized_meter_id=authorized_meter_id,
            use_case=forecast_uc,
        ),
        PredictUsageAndBillTool(
            authorized_meter_id=authorized_meter_id,
            use_case=predict_bill_uc,
        ),
        PlanHouseEnergyTool(
            authorized_meter_id=authorized_meter_id,
            use_case=house_plan_uc,
        ),
        AnalyzeApplianceScenarioTool(
            authorized_meter_id=authorized_meter_id,
            use_case=appliance_uc,
        ),
        ManageEnergyCostTool(
            authorized_meter_id=authorized_meter_id,
            use_case=cost_mgmt_uc,
        ),
    ]

    if include_knowledge_tools:
        # Customer operational context tools
        tools.append(GetCustomerPremisesProfileTool(authorized_meter_id=authorized_meter_id))
        tools.append(GetCustomerApplianceInventoryTool(authorized_meter_id=authorized_meter_id))

        # Structured Reference Tools
        tools.append(ResolveReferenceParameterTool(resolver=resolver))
        tools.append(LookupApplianceBenchmarkTool(resolver=resolver))
        tools.append(LookupGridEmissionFactorTool(resolver=resolver))

        # Document Knowledge (RAG) Tools
        if retriever is not None:
            tools.append(SearchRegulatoryDocumentsTool(retriever=retriever))
            tools.append(GetDocumentClauseTool(retriever=retriever))

    logger.info(
        "Registered %d residential LangChain tools for authorized meter '%s'",
        len(tools),
        authorized_meter_id,
    )
    return tools


def create_multi_knowledge_tools(
    authorized_meter_id: str,
    repository: BaseHouseholdEnergyRepository | None = None,
    analytics_engine: EnergyAnalyticsEngine | None = None,
    prediction_service: CustomerBillPredictionService | None = None,
    tariff_rate: float = 10.0,
    retriever: Optional[HybridDocumentRetriever] = None,
    resolver: Optional[ReferenceResolver] = None,
) -> list[BaseTool]:
    """Helper to return the complete multi-knowledge tool suite."""
    return create_residential_tools(
        authorized_meter_id=authorized_meter_id,
        repository=repository,
        analytics_engine=analytics_engine,
        prediction_service=prediction_service,
        tariff_rate=tariff_rate,
        include_knowledge_tools=True,
        retriever=retriever,
        resolver=resolver,
    )
