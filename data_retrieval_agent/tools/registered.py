"""GridVision tools implemented as adapters to existing business services."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel

from ..context import AuthenticatedRequestContext, Persona
from .base import (
    AnomalyOutput, BuildingOutput, ConsumerProfileOutput, CustomerSilverHistoryOutput, ForecastOutput,
    LatestCustomerSilverMonthOutput, LatestCommercialSilverMonthOutput,
    HistoryOutput, ModelMetadataOutput, RegionalOutput, SegmentationOutput,
    ToolDefinition, ToolError, ToolOutput, ToolRegistry,
)
from .schemas import (
    AnomalyInput, BuildingDetailsInput, ConsumerProfileInput, ForecastInput,
    CustomerSilverHistoryInput, HistoryInput, LatestCustomerSilverMonthInput, LatestCommercialSilverMonthInput, ModelMetadataInput, RegionalInformationInput, SegmentationInput,
)
from ..services.adapters import ServiceAdapters


class GridVisionTools:
    def __init__(self, services: dict[str, Any]):
        self.services = ServiceAdapters.from_mapping(services)

    def service(self, name: str):
        value = self.services.service(name)
        if value is None:
            raise ToolError("SOURCE_UNAVAILABLE", f"The {name} service is unavailable.", True)
        return value

    @staticmethod
    def entity(ctx: AuthenticatedRequestContext, kind: str, entity_id: str):
        if not ctx.allows_entity(kind, entity_id):
            raise ToolError("FORBIDDEN_ENTITY", "The requested entity is outside the user's authorized scope.")

    @staticmethod
    def output(name: str, data: dict, source_id: str, *, status: str = "ok", **source) -> ToolOutput:
        return ToolOutput(tool_name=name, status=status, data=data, source={"source_id": source_id, **source})

    def consumer_profile(self, args: ConsumerProfileInput, ctx: AuthenticatedRequestContext):
        if ctx.persona != Persona.RESIDENTIAL:
            raise ToolError("FORBIDDEN_PERSONA", "Consumer profiles require the residential persona.")
        entity_id = str(args.consumer_id)
        self.entity(ctx, "consumer", entity_id)
        profile = self.service("customer_bill_prediction_service").get_entity_profile(args.consumer_id)
        if profile is None:
            raise ToolError("NOT_FOUND", "Consumer profile was not found.")
        provenance = self.service("customer_bill_prediction_service").get_source_metadata("consumer_profile")
        return self.output("get_consumer_profile", profile, "customer_gold", record_type="consumer_profile", units="kWh", data_class="historical", provenance=provenance, is_live_telemetry=False)

    def history(self, args: HistoryInput, ctx: AuthenticatedRequestContext):
        if args.persona != ctx.persona.value:
            raise ToolError("FORBIDDEN_PERSONA", "The requested persona does not match authenticated identity.")
        entity = args.entity_id
        if args.persona == "residential":
            if args.time_range in {"30D", "90D"}:
                raise ToolError("INVALID_INPUT", "Residential history accepts monthly range 3M, 6M, 1Y, or ALL.")
            if entity:
                self.entity(ctx, "consumer", entity)
            elif not ctx.allows_entity("customer_cohort", "*"):
                raise ToolError("FORBIDDEN_ENTITY", "An authorized consumer or explicit customer cohort scope is required.")
            svc = self.service("customer_bill_prediction_service")
            result = svc.get_historical_gold_insights(args.time_range, int(entity) if entity else None)
            provenance, source = svc.get_source_metadata("historical_aggregate" if entity is None else "historical_gold_insights"), "customer_gold"
        elif args.persona == "commercial":
            if args.time_range in {"3M", "6M"}:
                raise ToolError("INVALID_INPUT", "Commercial history accepts 30D, 90D, 1Y, or ALL.")
            if entity:
                self.entity(ctx, "building", entity)
            elif not ctx.allows_entity("commercial_cohort", "*"):
                raise ToolError("FORBIDDEN_ENTITY", "An authorized building or explicit cohort scope is required.")
            svc = self.service("commercial_history_provider")
            result, provenance, source = svc.get_commercial_historical_insights(args.time_range, entity), svc.get_commercial_source_metadata(), "commercial_gold"
        else:
            if args.time_range in {"3M", "6M"}:
                raise ToolError("INVALID_INPUT", "Regional history accepts 30D, 90D, 1Y, or ALL.")
            if entity:
                self.entity(ctx, "region", entity)
            elif not (ctx.allows_entity("region", "*") or ctx.allows_entity("region", "system")):
                raise ToolError("FORBIDDEN_ENTITY", "A region or explicit system-wide scope is required.")
            svc = self.service("commercial_history_provider")
            result, provenance, source = svc.get_government_historical_insights(args.time_range, entity), svc.get_government_source_metadata(), "government_2018"
        return self.output("get_historical_consumption", result, source, record_type="historical_consumption", data_class="historical", provenance=provenance, is_live_telemetry=False)

    def customer_silver_history(self, args: CustomerSilverHistoryInput, ctx: AuthenticatedRequestContext):
        if ctx.persona != Persona.RESIDENTIAL:
            raise ToolError("FORBIDDEN_PERSONA", "Customer Silver history requires the household persona.")
        if args.entity_id is not None:
            self.entity(ctx, "consumer", str(args.entity_id))
        elif not ctx.allows_entity("customer_cohort", "*"):
            raise ToolError("FORBIDDEN_ENTITY", "An authorized consumer or household cohort scope is required.")
        service = self.service("customer_silver_history_service")
        data = (
            service.get_cohort_history(args.start_date, args.end_date)
            if args.entity_id is None
            else service.get_cohort_history(
                args.start_date, args.end_date, entity_id=args.entity_id
            )
        )
        return self.output(
            "get_household_silver_history", data, "customer_silver",
            record_type=("monthly_household_entity_consumption" if args.entity_id is not None else "monthly_household_cohort_consumption"), units="kWh",
            data_class="historical", provenance=service.get_source_metadata(),
            is_live_telemetry=False,
        )

    def latest_customer_silver_month(self, args: LatestCustomerSilverMonthInput, ctx: AuthenticatedRequestContext):
        if ctx.persona != Persona.RESIDENTIAL:
            raise ToolError("FORBIDDEN_PERSONA", "Customer Silver history requires the household persona.")
        if args.entity_id is not None:
            self.entity(ctx, "consumer", str(args.entity_id))
        elif not ctx.allows_entity("customer_cohort", "*"):
            raise ToolError("FORBIDDEN_ENTITY", "An authorized consumer or household cohort scope is required.")
        service = self.service("customer_silver_history_service")
        data = (
            service.get_latest_available_month()
            if args.entity_id is None
            else service.get_latest_available_month(entity_id=args.entity_id)
        )
        return self.output(
            "get_latest_household_silver_month", data, "customer_silver",
            record_type=("latest_month_household_entity_consumption" if args.entity_id is not None else "latest_month_household_cohort_consumption"), units="kWh",
            data_class="historical", provenance=service.get_source_metadata(),
            is_live_telemetry=False,
        )

    def latest_commercial_silver_month(self, args: LatestCommercialSilverMonthInput, ctx: AuthenticatedRequestContext):
        if ctx.persona != Persona.COMMERCIAL:
            raise ToolError("FORBIDDEN_PERSONA", "Commercial Silver history requires the commercial persona.")
        if args.entity_id is not None:
            self.entity(ctx, "building", args.entity_id)
        elif not ctx.allows_entity("commercial_cohort", "*"):
            raise ToolError("FORBIDDEN_ENTITY", "An authorized building or commercial cohort scope is required.")
        service = self.service("commercial_silver_history_service")
        data = service.get_latest_available_month(entity_id=args.entity_id)
        return self.output(
            "get_latest_commercial_silver_month", data, "commercial_silver",
            record_type=("latest_month_commercial_building_consumption" if args.entity_id is not None else "latest_month_commercial_cohort_consumption"),
            units="kWh", data_class="historical", provenance=service.get_source_metadata(),
            is_live_telemetry=False,
        )

    def building(self, args: BuildingDetailsInput, ctx: AuthenticatedRequestContext):
        if ctx.persona not in {Persona.COMMERCIAL, Persona.GOVERNMENT}:
            raise ToolError("FORBIDDEN_PERSONA", "Building details are unavailable to this persona.")
        self.entity(ctx, "building", args.building_id)
        provider = self.service("commercial_history_provider")
        row = next((item for item in provider.get_commercial_buildings() if str(item.get("buildingId")) == args.building_id), None)
        if row is None:
            raise ToolError("NOT_FOUND", "Commercial building was not found.")
        return self.output("get_building_details", row, "commercial_gold", record_type="commercial_building_profile", data_class="historical", provenance=provider.get_commercial_source_metadata(), is_live_telemetry=False)

    def regional(self, args: RegionalInformationInput, ctx: AuthenticatedRequestContext):
        if ctx.persona != Persona.GOVERNMENT:
            raise ToolError("FORBIDDEN_PERSONA", "Regional catalog access requires government persona.")
        provider = self.service("commercial_history_provider")
        rows = provider.get_regional_sites()
        permitted = ctx.entity_scopes.get("region", frozenset())
        if args.region_id:
            self.entity(ctx, "region", args.region_id)
            rows = [r for r in rows if str(r.get("siteId", r.get("grid_id", r.get("gridId", "")))) == args.region_id]
        elif "*" not in permitted and "system" not in permitted:
            rows = [r for r in rows if str(r.get("siteId", r.get("grid_id", r.get("gridId", "")))) in permitted]
        truncated = not args.region_id and len(rows) >= 100
        return self.output("get_regional_information", {"items": rows, "truncated": truncated, "limit": 100}, "government_2018", status="partial" if truncated else "ok", record_type="regional_grid_catalog", data_class="historical", provenance=provider.get_government_source_metadata(), is_live_telemetry=False)

    def forecast(self, args: ForecastInput, ctx: AuthenticatedRequestContext):
        if args.persona != ctx.persona.value:
            raise ToolError("FORBIDDEN_PERSONA", "Forecast persona does not match authenticated identity.")
        kind = {"residential": "consumer", "commercial": "building", "government": "region"}[args.persona]
        self.entity(ctx, kind, args.entity_id)
        if args.persona == "residential":
            svc = self.service("customer_bill_prediction_service")
            months = svc.get_entity_months(int(args.entity_id))
            if not months:
                raise ToolError("NOT_FOUND", "Consumer history was not found.")
            last = months[-1]
            result = svc.predict(int(args.entity_id), last["monthStart"], int(last["cutoffDay"]))
            source = "customer_gold"
        else:
            result = {"entity_id": args.entity_id, "horizon": self.service("model_provider").predict_horizon(args.persona, args.entity_id)}
            source = "commercial_gold" if args.persona == "commercial" else "government_2018"
        return self.output("get_energy_forecast", result, source, record_type="model_forecast", data_class="predicted", units="kWh", is_live_telemetry=False)

    def anomalies(self, args: AnomalyInput, ctx: AuthenticatedRequestContext):
        if ctx.persona == Persona.COMMERCIAL:
            raise ToolError("FORBIDDEN_PERSONA", "Synthetic consumer anomaly analysis is not available to the commercial persona.")
        for entity_id in args.consumer_ids:
            self.entity(ctx, "consumer", str(entity_id))
        result = self.service("anomaly_prediction_service").analyze(
            customer_ids=args.consumer_ids,
            start_date=date.fromisoformat(args.start_date),
            end_date=date.fromisoformat(args.end_date),
        )
        return self.output("get_anomaly_predictions", result, "anomaly_synthetic_2019", record_type="synthetic_model_findings", data_class="synthetic", provenance="synthetic_2019_normal.parquet", verified_fault_evidence=False, is_live_telemetry=False)

    def segmentation(self, args: SegmentationInput, ctx: AuthenticatedRequestContext):
        svc = self.service("government_segmentation_service")
        if args.scope == "consumer":
            if ctx.persona != Persona.RESIDENTIAL or args.consumer_id is None:
                raise ToolError("FORBIDDEN_PERSONA", "Consumer segmentation is restricted to an authorized residential consumer.")
            entity = str(args.consumer_id)
            self.entity(ctx, "consumer", entity)
            found = None
            page = 1
            while page <= 30 and found is None:
                rows, meta = svc.get_assignments(None, None, "coarse", None, page, 200)
                found = next((r for r in rows if str(r.get("OBJECTID")) == entity), None)
                if page * 200 >= int(meta.get("total", 0)):
                    break
                page += 1
            if found is None:
                raise ToolError("NOT_FOUND", "Consumer segmentation result was not found.")
            result, record_type = {"assignment": found}, "consumer_segmentation"
        elif args.scope == "distribution":
            if ctx.persona != Persona.GOVERNMENT:
                raise ToolError("FORBIDDEN_PERSONA", "Aggregate segmentation requires government persona.")
            if args.region_id:
                self.entity(ctx, "region", args.region_id)
                rows, _ = svc.get_regions("coarse", None, None, args.region_id, 1, 200)
                result, record_type = {"distribution": rows}, "regional_segmentation_distribution"
            elif ctx.allows_entity("region", "*") or ctx.allows_entity("region", "system"):
                result, record_type = {"distribution": svc.get_distribution()}, "segmentation_distribution"
            else:
                raise ToolError("FORBIDDEN_ENTITY", "A region or explicit system-wide scope is required.")
        else:
            if ctx.persona != Persona.GOVERNMENT or not args.region_id:
                raise ToolError("FORBIDDEN_PERSONA", "Regional segmentation needs an authorized government region.")
            self.entity(ctx, "region", args.region_id)
            rows, _ = svc.get_regions("coarse", None, None, args.region_id, 1, 200)
            result, record_type = {"regions": rows}, "regional_segmentation"
        return self.output("get_segmentation_results", result, "segmentation_2018", record_type=record_type, data_class="historical", provenance=svc.get_source_metadata(), is_live_telemetry=False)

    def metadata(self, args: ModelMetadataInput, ctx: AuthenticatedRequestContext):
        model = args.model_id
        if model == "anomaly-prediction":
            result, source = self.service("anomaly_prediction_service").get_model_metadata(), "anomaly_synthetic_2019"
        elif model == "government-customer-segmentation":
            result, source = self.service("government_segmentation_service").get_model_metadata(), "segmentation_2018"
        else:
            svc = self.service("customer_bill_prediction_service")
            catalog = svc.get_model_catalog()
            result = next((r for r in catalog if r.get("id") == model or r.get("modelId") == model), {"model_id": model, "status": "unavailable"})
            source = "customer_gold" if model == "customer-bill-prediction" else "commercial_gold" if model == "commercial-building-forecast" else "government_2018"
        return self.output("get_model_metadata", result, source, record_type="model_metadata", data_class="historical")


def build_tool_registry(services: dict[str, Any], approved_sources: set[str] | None = None) -> ToolRegistry:
    del approved_sources  # per-request source health is supplied to registry execution
    adapter, registry = GridVisionTools(services), ToolRegistry()
    rows = [
        ("get_household_silver_history", "Retrieve household cohort consumption from Silver observations for a bounded calendar window.", CustomerSilverHistoryInput, CustomerSilverHistoryOutput, "customer_silver", adapter.customer_silver_history),
        ("get_latest_household_silver_month", "Retrieve the latest calendar month present in Silver household observations.", LatestCustomerSilverMonthInput, LatestCustomerSilverMonthOutput, "customer_silver", adapter.latest_customer_silver_month),
        ("get_latest_commercial_silver_month", "Retrieve the latest calendar month present in Silver commercial building observations.", LatestCommercialSilverMonthInput, LatestCommercialSilverMonthOutput, "commercial_silver", adapter.latest_commercial_silver_month),
        ("get_consumer_profile", "Retrieve a residential consumer profile.", ConsumerProfileInput, ConsumerProfileOutput, "customer_gold", adapter.consumer_profile),
        ("get_historical_consumption", "Retrieve bounded historical energy consumption.", HistoryInput, HistoryOutput, None, adapter.history),
        ("get_building_details", "Retrieve an authorized commercial building profile.", BuildingDetailsInput, BuildingOutput, "commercial_gold", adapter.building),
        ("get_regional_information", "Retrieve authorized government grid information.", RegionalInformationInput, RegionalOutput, "government_2018", adapter.regional),
        ("get_energy_forecast", "Retrieve an existing trained model prediction.", ForecastInput, ForecastOutput, None, adapter.forecast),
        ("get_anomaly_predictions", "Retrieve synthetic anomaly findings, not verified faults.", AnomalyInput, AnomalyOutput, "anomaly_synthetic_2019", adapter.anomalies),
        ("get_segmentation_results", "Retrieve published segmentation outputs.", SegmentationInput, SegmentationOutput, "segmentation_2018", adapter.segmentation),
        ("get_model_metadata", "Retrieve metadata for an allow-listed model.", ModelMetadataInput, ModelMetadataOutput, None, adapter.metadata),
    ]
    for name, description, schema, output, source, handler in rows:
        registry.register(ToolDefinition(name, description, schema, output, name, source, handler))
    return registry
