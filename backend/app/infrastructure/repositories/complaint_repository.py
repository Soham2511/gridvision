"""Repository implementation for persisting and querying Complaint aggregates."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.complaints.entities import (
    Complaint,
    ComplaintStatus,
    CustomerSegment,
    SeverityLevel,
    SeverityResult,
    StatusTransition,
    ValidationOutcome,
    ValidationResult,
)
from app.infrastructure.database.connection import get_engine, get_session
from app.infrastructure.database.models.complaint import ComplaintModel
from app.infrastructure.database.models.reference import Base

logger = logging.getLogger("gridvision.infrastructure.repositories.complaints")


class ComplaintRepository:
    """SQLAlchemy-backed repository for the Complaint domain model."""

    def __init__(self, engine=None) -> None:
        self.engine = engine or get_engine()
        self.ensure_tables()

    def ensure_tables(self) -> None:
        """Ensure the complaint database tables are created."""
        Base.metadata.create_all(bind=self.engine)
        try:
            self.seed_demo_complaints()
        except Exception as e:
            logger.warning("Could not auto-seed demo complaints: %s", e)

    def seed_demo_complaints(self) -> None:
        """Seed sample complaints across personas if table is empty or sparsely populated."""
        with get_session() as session:
            count = len(session.scalars(select(ComplaintModel.id)).all())
            if count >= 6:
                return

            samples = [
                ComplaintModel(
                    id="CMP-20261104-101",
                    customer_id="2254213",
                    meter_id="METER-2254213",
                    customer_segment="RESIDENTIAL",
                    category_id="power_supply_interruption",
                    category_label="Power Supply Interruption / Outage",
                    title="Unscheduled blackout on residential feeder line 4",
                    description="Sudden power cut affecting our entire block since 18:30 without prior utility maintenance advisory.",
                    status="REGISTERED",
                    validation_outcome="PLAUSIBLE",
                    severity_score=0.78,
                    severity_level="High",
                    category_data={"duration_hours": 3.5, "affected_area": "North Block Sector 7"},
                    status_history=[
                        {"from_status": "SUBMITTED", "to_status": "REGISTERED", "timestamp": "2026-11-04T18:45:00+00:00", "note": "Verified by smart meter telemetry"}
                    ],
                    created_at=datetime.fromisoformat("2026-11-04T18:30:00+00:00"),
                    updated_at=datetime.fromisoformat("2026-11-04T18:45:00+00:00"),
                ),
                ComplaintModel(
                    id="CMP-20261103-102",
                    customer_id="293861",
                    meter_id="METER-293861",
                    customer_segment="RESIDENTIAL",
                    category_id="smart_meter_malfunction",
                    category_label="Smart Meter Malfunction",
                    title="Meter display frozen at 14.8 kWh with error code E-04",
                    description="Digital LCD screen is unresponsive and not registering consumption increments for 48 hours.",
                    status="RESOLVED",
                    validation_outcome="PLAUSIBLE",
                    severity_score=0.52,
                    severity_level="Medium",
                    category_data={"error_code": "E-04"},
                    status_history=[
                        {"from_status": "SUBMITTED", "to_status": "REGISTERED", "timestamp": "2026-11-03T10:00:00+00:00", "note": "Validated meter diagnostic"},
                        {"from_status": "REGISTERED", "to_status": "RESOLVED", "timestamp": "2026-11-04T14:20:00+00:00", "note": "Field technician recalibrated and reset meter communications module."}
                    ],
                    created_at=datetime.fromisoformat("2026-11-03T09:30:00+00:00"),
                    updated_at=datetime.fromisoformat("2026-11-04T14:20:00+00:00"),
                ),
                ComplaintModel(
                    id="CMP-20261104-103",
                    customer_id="537421",
                    meter_id="METER-537421",
                    customer_segment="RESIDENTIAL",
                    category_id="voltage_fluctuation",
                    category_label="Voltage Fluctuation & Surges",
                    title="Severe voltage drop below 180V damaging domestic electronics",
                    description="Line voltage measured between 172V and 188V causing heat pump tripping and inverter cutoffs.",
                    status="REGISTERED",
                    validation_outcome="PLAUSIBLE",
                    severity_score=0.88,
                    severity_level="Critical",
                    category_data={"observed_voltage": 175, "duration_minutes": 120},
                    status_history=[
                        {"from_status": "SUBMITTED", "to_status": "REGISTERED", "timestamp": "2026-11-04T20:10:00+00:00", "note": "Substation tap changer voltage anomaly confirmed"}
                    ],
                    created_at=datetime.fromisoformat("2026-11-04T19:50:00+00:00"),
                    updated_at=datetime.fromisoformat("2026-11-04T20:10:00+00:00"),
                ),
                ComplaintModel(
                    id="CMP-20261104-201",
                    customer_id="Panther_office_1",
                    meter_id="COMM_MTR_PANTHER_1",
                    customer_segment="COMMERCIAL",
                    category_id="tariff_billing_discrepancy",
                    category_label="Tariff & Billing Discrepancy",
                    title="Peak demand penalty tariff applied during off-peak weekend hours",
                    description="Commercial bill reflects maximum demand tariff charge on Sunday 03:00 AM when facility was closed.",
                    status="REGISTERED",
                    validation_outcome="PLAUSIBLE",
                    severity_score=0.60,
                    severity_level="Medium",
                    category_data={"disputed_amount_inr": 24500, "billing_period": "Oct 2026"},
                    status_history=[
                        {"from_status": "SUBMITTED", "to_status": "REGISTERED", "timestamp": "2026-11-04T11:30:00+00:00", "note": "Awaiting utility tariff auditing review"}
                    ],
                    created_at=datetime.fromisoformat("2026-11-04T11:00:00+00:00"),
                    updated_at=datetime.fromisoformat("2026-11-04T11:30:00+00:00"),
                ),
                ComplaintModel(
                    id="CMP-20261102-202",
                    customer_id="Bear_hospital_1",
                    meter_id="COMM_MTR_BEAR_1",
                    customer_segment="COMMERCIAL",
                    category_id="safety_fire_hazard",
                    category_label="Safety & Electrical Fire Hazard",
                    title="Secondary transformer sparking and heavy smoke in emergency bay substation",
                    description="Thermal imaging detected overheated bushing connection with sparking. Fire department notified.",
                    status="RESOLVED",
                    validation_outcome="PLAUSIBLE",
                    severity_score=0.96,
                    severity_level="Critical",
                    category_data={"facility_type": "Hospital Emergency Care", "hazard_type": "Sparking Bushing"},
                    status_history=[
                        {"from_status": "SUBMITTED", "to_status": "REGISTERED", "timestamp": "2026-11-02T04:15:00+00:00", "note": "Safety override priority 1"},
                        {"from_status": "REGISTERED", "to_status": "RESOLVED", "timestamp": "2026-11-02T08:30:00+00:00", "note": "Emergency response team replaced damaged bushing and certified insulation."}
                    ],
                    created_at=datetime.fromisoformat("2026-11-02T04:00:00+00:00"),
                    updated_at=datetime.fromisoformat("2026-11-02T08:30:00+00:00"),
                ),
                ComplaintModel(
                    id="CMP-20261101-301",
                    customer_id="GOV_DIST_NORTH_3",
                    meter_id="GRID_FEEDER_3A",
                    customer_segment="GOVERNMENT",
                    category_id="infrastructure_damage",
                    category_label="Grid Infrastructure & Streetlighting",
                    title="High-wind storm damaged distribution pole cross-arm and sagging line",
                    description="11kV feeder line cross-arm cracked, causing conductor sag over municipal ring road.",
                    status="REJECTED",
                    validation_outcome="INVALID",
                    severity_score=0.30,
                    severity_level="Low",
                    category_data={"asset_id": "POLE_NORTH_311"},
                    status_history=[
                        {"from_status": "SUBMITTED", "to_status": "REJECTED", "timestamp": "2026-11-01T15:00:00+00:00", "note": "Inspected on site by utility patrol: line belongs to private telecom fiber operator, not grid infrastructure."}
                    ],
                    created_at=datetime.fromisoformat("2026-11-01T14:00:00+00:00"),
                    updated_at=datetime.fromisoformat("2026-11-01T15:00:00+00:00"),
                ),
            ]
            for s in samples:
                session.merge(s)
            session.commit()

    def _to_entity(self, row: ComplaintModel) -> Complaint:
        """Convert ORM row to domain entity."""
        validation_res = None
        if row.validation_payload:
            try:
                validation_res = ValidationResult.model_validate(row.validation_payload)
            except Exception as e:
                logger.warning("Failed to deserialize validation payload: %s", e)

        severity_res = None
        if row.scoring_payload:
            try:
                severity_res = SeverityResult.model_validate(row.scoring_payload)
            except Exception as e:
                logger.warning("Failed to deserialize scoring payload: %s", e)
        if not severity_res and row.severity_level and row.severity_score is not None:
            try:
                severity_res = SeverityResult(
                    severity_score=float(row.severity_score),
                    severity_level=SeverityLevel(row.severity_level),
                    scoring_rationale="Severity assessed from incident telemetry",
                    factor_breakdown={
                        "safety_risk": 0.5,
                        "disruption_extent": 0.5,
                        "duration_factor": 0.5,
                        "recurrence_factor": 0.5,
                        "essential_services_impact": 0.5,
                        "safety_override_applied": False,
                    },
                    benchmark_version="1.0",
                    scored_at=row.created_at.isoformat() if row.created_at else datetime.now(timezone.utc).isoformat(),
                )
            except Exception:
                pass

        history = []
        if row.status_history:
            for item in row.status_history:
                try:
                    history.append(StatusTransition.model_validate(item))
                except Exception:
                    pass

        return Complaint(
            id=row.id,
            customer_id=row.customer_id,
            meter_id=row.meter_id,
            customer_segment=CustomerSegment(row.customer_segment),
            category_id=row.category_id,
            category_label=row.category_label,
            title=row.title,
            description=row.description,
            category_data=row.category_data or {},
            status=ComplaintStatus(row.status),
            validation_result=validation_res,
            severity_result=severity_res,
            status_history=history,
            customer_care_escalation=row.customer_care_escalation,
            registration_metadata=row.registration_payload,
            created_at=row.created_at.isoformat() if row.created_at else datetime.now(timezone.utc).isoformat(),
            updated_at=row.updated_at.isoformat() if row.updated_at else datetime.now(timezone.utc).isoformat(),
        )

    def save(self, complaint: Complaint) -> Complaint:
        """Save a new complaint or update an existing complaint record."""
        with get_session() as session:
            existing = session.get(ComplaintModel, complaint.id)

            val_dict = complaint.validation_result.model_dump() if complaint.validation_result else None
            score_dict = complaint.severity_result.model_dump() if complaint.severity_result else None
            history_list = [h.model_dump() for h in complaint.status_history]

            if existing:
                existing.status = complaint.status.value
                existing.validation_outcome = complaint.validation_result.outcome.value if complaint.validation_result else None
                existing.severity_score = complaint.severity_result.severity_score if complaint.severity_result else None
                existing.severity_level = complaint.severity_result.severity_level.value if complaint.severity_result else None
                existing.category_data = complaint.category_data
                existing.validation_payload = val_dict
                existing.scoring_payload = score_dict
                existing.registration_payload = complaint.registration_metadata
                existing.status_history = history_list
                existing.customer_care_escalation = complaint.customer_care_escalation
                existing.updated_at = datetime.now(timezone.utc)
            else:
                new_row = ComplaintModel(
                    id=complaint.id,
                    customer_id=complaint.customer_id,
                    meter_id=complaint.meter_id,
                    customer_segment=complaint.customer_segment.value,
                    category_id=complaint.category_id,
                    category_label=complaint.category_label,
                    title=complaint.title,
                    description=complaint.description,
                    status=complaint.status.value,
                    validation_outcome=complaint.validation_result.outcome.value if complaint.validation_result else None,
                    severity_score=complaint.severity_result.severity_score if complaint.severity_result else None,
                    severity_level=complaint.severity_result.severity_level.value if complaint.severity_result else None,
                    category_data=complaint.category_data,
                    validation_payload=val_dict,
                    scoring_payload=score_dict,
                    registration_payload=complaint.registration_metadata,
                    status_history=history_list,
                    customer_care_escalation=complaint.customer_care_escalation,
                    created_at=datetime.fromisoformat(complaint.created_at) if complaint.created_at else datetime.now(timezone.utc),
                    updated_at=datetime.fromisoformat(complaint.updated_at) if complaint.updated_at else datetime.now(timezone.utc),
                )
                session.add(new_row)

        return complaint

    def get_by_id(self, complaint_id: str) -> Optional[Complaint]:
        """Retrieve a complaint by ID."""
        with get_session() as session:
            row = session.get(ComplaintModel, complaint_id)
            if not row:
                return None
            return self._to_entity(row)

    def list_by_customer(
        self,
        customer_id: str,
        status_filter: Optional[str] = None,
    ) -> List[Complaint]:
        """List all complaints belonging to a customer, optionally filtered by status."""
        with get_session() as session:
            clean_id = str(customer_id).strip()
            clean_num = clean_id.replace("METER-", "").replace("usr-", "")
            
            stmt = select(ComplaintModel).where(
                (ComplaintModel.customer_id == clean_id)
                | (ComplaintModel.customer_id == clean_num)
                | (ComplaintModel.customer_id == f"METER-{clean_num}")
                | (ComplaintModel.customer_id == f"usr-{clean_num}")
                | (ComplaintModel.meter_id == clean_id)
                | (ComplaintModel.meter_id == clean_num)
                | (ComplaintModel.meter_id == f"METER-{clean_num}")
            )

            if status_filter and status_filter.strip().upper() != "ALL":
                sf = status_filter.strip().upper()
                if sf in ("PENDING", "REGISTERED"):
                    stmt = stmt.where(ComplaintModel.status.in_([
                        ComplaintStatus.REGISTERED.value,
                        ComplaintStatus.SUBMITTED.value,
                        ComplaintStatus.VALIDATING.value,
                        ComplaintStatus.SCORING.value,
                    ]))
                elif sf in ("RESOLVED",):
                    stmt = stmt.where(ComplaintModel.status == ComplaintStatus.RESOLVED.value)
                elif sf in ("REJECTED", "INVALID"):
                    stmt = stmt.where(ComplaintModel.status.in_([
                        ComplaintStatus.REJECTED.value,
                        ComplaintStatus.INVALID.value,
                    ]))

            stmt = stmt.order_by(ComplaintModel.created_at.desc())
            rows = session.scalars(stmt).all()
            return [self._to_entity(r) for r in rows]

    def list_all(
        self,
        segment: Optional[str] = None,
        status_filter: Optional[str] = None,
        category: Optional[str] = None,
    ) -> List[Complaint]:
        """List all complaints with optional filtering by segment, status, or category."""
        with get_session() as session:
            stmt = select(ComplaintModel)

            if segment and segment.strip().upper() != "ALL":
                seg = segment.strip().upper()
                if seg in ("HOUSEHOLD", "RESIDENTIAL"):
                    stmt = stmt.where(ComplaintModel.customer_segment == "RESIDENTIAL")
                elif seg in ("COMMERCIAL", "COMMERCIAL_BUILDING"):
                    stmt = stmt.where(ComplaintModel.customer_segment == "COMMERCIAL")
                elif seg in ("GOVERNMENT", "UTILITY"):
                    stmt = stmt.where(ComplaintModel.customer_segment == "GOVERNMENT")

            if status_filter and status_filter.strip().upper() != "ALL":
                sf = status_filter.strip().upper()
                if sf in ("PENDING", "REGISTERED"):
                    stmt = stmt.where(ComplaintModel.status.in_([ComplaintStatus.REGISTERED.value, ComplaintStatus.SUBMITTED.value, ComplaintStatus.VALIDATING.value]))
                elif sf in ("RESOLVED",):
                    stmt = stmt.where(ComplaintModel.status == ComplaintStatus.RESOLVED.value)
                elif sf in ("REJECTED", "INVALID"):
                    stmt = stmt.where(ComplaintModel.status.in_([ComplaintStatus.INVALID.value, ComplaintStatus.REJECTED.value]))
                else:
                    stmt = stmt.where(ComplaintModel.status == sf)

            if category and category.strip().lower() != "all":
                cat = category.strip().lower()
                stmt = stmt.where(ComplaintModel.category_id.ilike(f"%{cat}%"))

            stmt = stmt.order_by(ComplaintModel.created_at.desc())
            rows = session.scalars(stmt).all()
            return [self._to_entity(r) for r in rows]

    def update_status(
        self,
        complaint_id: str,
        new_status: str,
        note: Optional[str] = None,
    ) -> Optional[Complaint]:
        """Update complaint status and append to status history."""
        with get_session() as session:
            existing = session.get(ComplaintModel, complaint_id)
            if not existing:
                return None

            st_val = new_status.strip().upper()
            if st_val == "PENDING":
                st_val = ComplaintStatus.REGISTERED.value
            elif st_val == "REJECTED":
                st_val = ComplaintStatus.REJECTED.value
            elif st_val == "RESOLVED":
                st_val = ComplaintStatus.RESOLVED.value

            history = list(existing.status_history or [])
            history.append({
                "from_status": existing.status,
                "to_status": st_val,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "note": note or f"Status changed to {st_val}",
            })
            existing.status = st_val
            existing.status_history = history
            existing.updated_at = datetime.now(timezone.utc)
            session.commit()
            return self._to_entity(existing)

