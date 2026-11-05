"""Evidence-grounded, structured Rectification Agent for anomaly diagnostics."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.schemas.rectification_schema import (
    EventCoordinates,
    EventDetails,
    GuidanceCitation,
    RectificationReportPayload,
    SeverityInfo,
)

logger = logging.getLogger("gridvision.rectification.agent")


class RectificationAgent:
    """Generates structured anomaly diagnosis and actionable rectification plans."""

    @classmethod
    def generate_rectification_payload(
        cls,
        event: dict[str, Any],
        run: dict[str, Any] | None = None,
        *,
        persona: str = "household",
        entity_id: str | int | None = None,
        customer_email: str | None = None,
    ) -> RectificationReportPayload:
        """Create a validated, structured RectificationReportPayload from an event."""
        run_data = run or {}
        event_id = str(event.get("event_id") or event.get("id") or "EVT_UNKNOWN")
        run_id = str(
            event.get("run_id")
            or run_data.get("analysis_id")
            or run_data.get("run_id")
            or "RUN_SYNTHETIC"
        )
        
        dominant_type = str(
            event.get("dominant_anomaly_type")
            or (event.get("anomaly_types")[0] if event.get("anomaly_types") else "anomaly")
        ).lower()
        
        anomaly_types = [
            str(t).lower()
            for t in (event.get("anomaly_types") or [dominant_type])
        ]
        if dominant_type not in anomaly_types:
            anomaly_types.insert(0, dominant_type)

        # Calculate severity
        max_score = event.get("max_anomaly_score")
        mean_score = event.get("mean_anomaly_score")
        score = float(max_score if max_score is not None else (mean_score if mean_score is not None else 0.5))
        score = max(0.0, min(1.0, score))
        
        if score >= 0.75:
            severity_level = "CRITICAL"
        elif score >= 0.60:
            severity_level = "HIGH"
        elif score >= 0.40:
            severity_level = "MEDIUM"
        else:
            severity_level = "LOW"

        severity = SeverityInfo(
            score=round(score, 3),
            level=severity_level,
            mean_score=round(float(mean_score), 3) if mean_score is not None else None,
            max_score=round(float(max_score), 3) if max_score is not None else None,
        )

        # Resolve entity / customer
        customer_ids = event.get("customer_ids") or []
        resolved_customer_id: str | int | None = entity_id
        if resolved_customer_id is None and customer_ids:
            resolved_customer_id = customer_ids[0]

        normalized_persona = (persona or "household").lower()
        if normalized_persona not in {"household", "commercial", "government"}:
            normalized_persona = "household"

        if normalized_persona == "household":
            customer_name = (
                f"Residential Consumer (Meter #{resolved_customer_id})"
                if resolved_customer_id
                else "Residential Consumer"
            )
        elif normalized_persona == "commercial":
            customer_name = (
                f"Commercial Facility (Building #{resolved_customer_id})"
                if resolved_customer_id
                else "Commercial Facility"
            )
        else:
            customer_name = (
                f"Regional Grid Sector #{resolved_customer_id}"
                if resolved_customer_id
                else "State Grid Transmission Authority"
            )

        # Event timing & details
        start_time = str(event.get("event_start") or datetime.now(timezone.utc).isoformat())
        end_time = str(event.get("event_end") or start_time)
        duration_hours = float(event.get("event_duration", 3600.0)) / 3600.0

        lat = event.get("latitude_center")
        lon = event.get("longitude_center")
        coords = None
        if lat is not None and lon is not None:
            try:
                coords = EventCoordinates(latitude=float(lat), longitude=float(lon))
            except (ValueError, TypeError):
                coords = None

        details = EventDetails(
            scope=str(event.get("event_scope") or "SINGLE_CUSTOMER"),
            start_time=start_time,
            end_time=end_time,
            duration_hours=round(duration_hours, 2),
            affected_customer_count=max(1, int(event.get("affected_customer_count") or len(customer_ids) or 1)),
            coordinates=coords,
        )

        # Evidence-grounded probable causes based on detected patterns
        probable_causes = []
        if any("spike" in t for t in anomaly_types):
            probable_causes.append(
                "Short-lived load surge, switching transient, or inrush current from large motor/induction equipment startup."
            )
        if any("drop" in t for t in anomaly_types):
            probable_causes.append(
                "Feeder phase imbalance, sudden equipment load rejection, or localized supply curtailment."
            )
        if any("flatline" in t or "zero" in t for t in anomaly_types):
            probable_causes.append(
                "Repeated or null measurements caused by metering communication dropouts, gateway freeze, or physical power interruption."
            )
        if not probable_causes:
            probable_causes.append(
                f"Detector signature {dominant_type} deviates from historical baseline consumption and power factor norms."
            )
        probable_causes.append(
            "Distribution circuit voltage unbalance or transient line impedance fluctuation during observation window."
        )

        # Corrective actions
        corrective_actions = [
            "Verify physical interval telemetry against adjacent feeder phases to validate reading authenticity.",
            "Inspect distribution transformer tap positions, circuit breakers, and protection relay trip records.",
        ]
        if normalized_persona == "household":
            corrective_actions.append(
                "Advise resident not to tamper with or open electrical panelboard; request licensed utility field technician inspection."
            )
            corrective_actions.append(
                "Isolate heavy residential induction loads (geysers, heat pumps, compressors) until voltage stabilization is verified."
            )
        else:
            corrective_actions.append(
                "Review substation capacitor bank switching sequence and verify industrial power factor correction status."
            )
            corrective_actions.append(
                "Check variable frequency drives and automated building management telemetry for harmonic resonance flags."
            )

        # Preventive recommendations
        preventive_recommendations = [
            "Install automated power quality monitoring and transient surge arresters on main incoming feeder panels.",
            "Schedule quarterly thermographic infrared imaging of transformer bushings, switchgear terminals, and busbars.",
            "Configure gateway alarms for recurring phase voltage fluctuations exceeding standard ±5% statutory thresholds.",
            "Stagger operational scheduling of high-capacity induction motors to avoid concurrent grid demand spikes.",
        ]

        # Citations
        citations = [
            GuidanceCitation(
                title="IEEE Std 1159: Recommended Practice for Monitoring Electric Power Quality",
                publisher="IEEE Standards Association",
                clause="Section 4.3 - Voltage Sags, Swells, and Transients Classification",
            ),
            GuidanceCitation(
                title="CEA Technical Standards for Connectivity to the Distributed Grid",
                publisher="Central Electricity Authority",
                clause="Regulation 6 - Protection System & Quality of Supply",
            ),
        ]

        limitations = [
            "This report is generated from verified detector signatures and approved engineering standards.",
            "Identified probable causes represent physical model signatures rather than intrusive destructive fault evidence.",
            "Always follow qualified utility safety protocols and certified electrical codes prior to manual intervention.",
        ]

        payload = RectificationReportPayload(
            event_id=event_id,
            run_id=run_id,
            persona=normalized_persona,  # type: ignore[arg-type]
            customer_id=str(resolved_customer_id) if resolved_customer_id is not None else None,
            customer_name=customer_name,
            customer_email=customer_email,
            company_name="GridVision Energy Intelligence",
            anomaly_type=dominant_type,
            dominant_anomaly_type=dominant_type,
            anomaly_types=anomaly_types,
            severity=severity,
            event_details=details,
            probable_causes=probable_causes,
            corrective_actions=corrective_actions,
            preventive_recommendations=preventive_recommendations,
            guidance_citations=citations,
            limitations=limitations,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

        logger.info(
            "rectification_payload_generated",
            extra={
                "event": {
                    "event_id": event_id,
                    "run_id": run_id,
                    "persona": normalized_persona,
                    "anomaly_type": dominant_type,
                    "severity_level": severity.level,
                    "severity_score": severity.score,
                }
            },
        )
        return payload

