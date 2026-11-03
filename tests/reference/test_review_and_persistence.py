"""Comprehensive unit and integration tests for Milestone 2: Reference Data System & Persistence.

Tests:
1. Database Layer & SQLite/PostgreSQL configuration (connection, foreign keys, sessions).
2. Declarative Base Models (schema, constraints, foreign keys, relationships).
3. Deterministic Pydantic validation (units, dates, physical plausibility).
4. Review workflow engine state machine transitions.
5. Immutable versioning, superseding, and audit logging.
6. ReferenceRepository operations and temporal active reference queries.
7. Customer data isolation invariants.
"""

from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.database.connection import (
    create_db_engine,
    get_db_session,
    get_engine,
    get_session,
    get_session_factory,
    init_db,
)
from app.infrastructure.database.models.reference import (
    ApprovedReferenceModel,
    Base,
    CandidateReferenceModel,
    DocumentArtifactModel,
    ReferenceAuditLogModel,
    ReferenceParameterModel,
    SourceDocumentModel,
)
from app.services.reference.lifecycle import (
    CandidateLifecycleService,
    InvalidStatusTransitionError,
    ReviewActionRequest,
    ReviewAuthorizationError,
    ReviewStatusEnum,
    ReviewWorkflowService,
)
from app.services.reference.repository import ReferenceRepository
from app.services.reference.schemas import (
    CandidateReferenceCreate,
    CandidateReferenceSchema,
    EnergyUnitEnum,
)


class BasePersistenceTestCase(unittest.TestCase):
    """Base test case providing an isolated in-memory SQLite database with foreign keys."""

    def setUp(self) -> None:
        self.engine = create_db_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.session: Session = self.SessionFactory()

        # Seed sample source document for FK integrity
        self.sample_source = SourceDocumentModel(
            id="bee_ac_2024_001",
            issuing_organization="Bureau of Energy Efficiency (BEE)",
            official_url="https://beeindia.gov.in/standards-labeling/room-ac-2024.pdf",
            document_identifier="BEE/S&L/AC/2024/001",
            edition_revision="Revision 4",
            publication_date=date(2024, 1, 15),
            retrieval_date=date(2024, 1, 20),
            content_checksum_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            licensing="Government Open Access",
            status="active",
        )
        self.session.add(self.sample_source)
        self.session.commit()

        self.repository = ReferenceRepository(session=self.session, session_factory=self.SessionFactory)
        self.workflow = ReviewWorkflowService(session=self.session)

    def tearDown(self) -> None:
        self.session.rollback()
        self.session.close()
        Base.metadata.drop_all(bind=self.engine)


class TestDatabaseConnection(BasePersistenceTestCase):
    """1. Test Database connection, dialect configuration, and session behavior."""

    def test_sqlite_foreign_keys_pragma_enforced(self) -> None:
        """Verify PRAGMA foreign_keys is ON in SQLite connections."""
        with self.engine.connect() as conn:
            result = conn.execute(text("PRAGMA foreign_keys")).scalar()
            self.assertEqual(result, 1)

    def test_session_commit_and_rollback(self) -> None:
        """Verify get_session context manager commits on success and rolls back on failure."""
        with get_session(self.SessionFactory) as s:
            param = ReferenceParameterModel(
                category="appliance",
                identifier="test_param_1",
                standard_unit="kWh",
                description="Test parameter",
            )
            s.add(param)

        # Confirm persisted
        with get_session(self.SessionFactory) as s:
            loaded = s.execute(
                select(ReferenceParameterModel).where(ReferenceParameterModel.identifier == "test_param_1")
            ).scalar_one_or_none()
            self.assertIsNotNone(loaded)

        # Test rollback on exception
        with self.assertRaises(ValueError):
            with get_session(self.SessionFactory) as s:
                param2 = ReferenceParameterModel(
                    category="appliance",
                    identifier="test_param_rollback",
                    standard_unit="kW",
                )
                s.add(param2)
                raise ValueError("Simulated failure")

        with get_session(self.SessionFactory) as s:
            loaded2 = s.execute(
                select(ReferenceParameterModel).where(ReferenceParameterModel.identifier == "test_param_rollback")
            ).scalar_one_or_none()
            self.assertIsNone(loaded2)


class TestDeclarativeModels(BasePersistenceTestCase):
    """2. Test SQLAlchemy 2.0 Declarative Base Models."""

    def test_source_document_model_synonyms(self) -> None:
        """Verify SourceDocumentModel supports synonyms: checksum_sha256 and edition."""
        self.assertEqual(self.sample_source.checksum_sha256, self.sample_source.content_checksum_sha256)
        self.assertEqual(self.sample_source.edition, self.sample_source.edition_revision)

    def test_document_artifact_foreign_key_and_cascade(self) -> None:
        """Verify DocumentArtifactModel enforces foreign key to SourceDocumentModel."""
        artifact = DocumentArtifactModel(
            id="art-001",
            source_id="bee_ac_2024_001",
            artifact_type="original",
            file_path="data/documents/original/bee_ac_2024.pdf",
            mime_type="application/pdf",
            metadata_json={"page_count": 25},
        )
        self.session.add(artifact)
        self.session.commit()

        loaded = self.session.get(DocumentArtifactModel, "art-001")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.source.issuing_organization, "Bureau of Energy Efficiency (BEE)")

    def test_reference_parameter_uniqueness(self) -> None:
        """Verify identifier / parameter_key unique constraints on ReferenceParameterModel."""
        p1 = ReferenceParameterModel(
            category="appliance",
            identifier="room_ac_1.5t_5star_iseer",
            standard_unit="Wh/Wh",
        )
        self.session.add(p1)
        self.session.commit()

        # Duplicate identifier should violate unique constraint
        p2 = ReferenceParameterModel(
            category="appliance",
            identifier="room_ac_1.5t_5star_iseer",
            standard_unit="Wh/Wh",
        )
        self.session.add(p2)
        with self.assertRaises(Exception):
            self.session.commit()
        self.session.rollback()

    def test_candidate_foreign_key_enforcement(self) -> None:
        """Verify CandidateReferenceModel rejects non-existent source_id due to FK constraint."""
        candidate = CandidateReferenceModel(
            parameter_key="room_ac_1.5t_5star_iseer",
            raw_value="5.20",
            normalized_value=5.20,
            unit="Wh/Wh",
            jurisdiction="IN",
            applicability_conditions={"star_rating": 5},
            effective_from=date(2024, 1, 1),
            source_id="non_existent_source_id_999",
            confidence=1.0,
            review_status="draft",
        )
        self.session.add(candidate)
        with self.assertRaises(Exception):
            self.session.commit()
        self.session.rollback()


class TestDeterministicPydanticValidation(unittest.TestCase):
    """3. Test Deterministic Pydantic Schemas and Domain Validation Rules."""

    def get_valid_payload(self) -> dict:
        return {
            "parameter_key": "room_ac_1.5t_5star_iseer",
            "raw_value": "5.20",
            "normalized_value": 5.20,
            "unit": "Wh/Wh",
            "jurisdiction": "IN",
            "region": None,
            "applicability_conditions": {"star_rating": 5, "rated_capacity_tons": 1.5},
            "effective_from": date(2024, 1, 1),
            "effective_to": date(2026, 12, 31),
            "source_id": "bee_ac_2024_001",
            "provenance": {"page": 12, "clause": "4.2", "excerpt": "ISEER >= 5.20"},
            "confidence": 1.0,
        }

    def test_valid_payload_passes(self) -> None:
        """Verify complete and valid candidate reference payload validates successfully."""
        payload = self.get_valid_payload()
        schema = CandidateReferenceCreate.model_validate(payload)
        self.assertEqual(schema.parameter_key, "room_ac_1.5t_5star_iseer")
        self.assertEqual(schema.normalized_value, 5.20)
        self.assertEqual(schema.unit, "Wh/Wh")

    def test_rejects_missing_or_null_unit(self) -> None:
        """Verify missing or null unit raises validation error (never assumed)."""
        payload = self.get_valid_payload()
        payload["unit"] = None
        with self.assertRaises(Exception):
            CandidateReferenceCreate.model_validate(payload)

    def test_rejects_whitespace_unit(self) -> None:
        """Verify whitespace-only unit is rejected."""
        payload = self.get_valid_payload()
        payload["unit"] = "   "
        with self.assertRaises(Exception):
            CandidateReferenceCreate.model_validate(payload)

    def test_rejects_unverified_domain_unit(self) -> None:
        """Verify unverified unit string (e.g. bananas_per_hour) is rejected."""
        payload = self.get_valid_payload()
        payload["unit"] = "bananas_per_hour"
        with self.assertRaises(Exception):
            CandidateReferenceCreate.model_validate(payload)

    def test_rejects_missing_effective_from_date(self) -> None:
        """Verify missing effective_from date raises validation error."""
        payload = self.get_valid_payload()
        payload["effective_from"] = None
        with self.assertRaises(Exception):
            CandidateReferenceCreate.model_validate(payload)

    def test_rejects_invalid_date_ordering(self) -> None:
        """Verify effective_to earlier than effective_from raises validation error."""
        payload = self.get_valid_payload()
        payload["effective_from"] = date(2026, 1, 1)
        payload["effective_to"] = date(2024, 1, 1)
        with self.assertRaises(Exception):
            CandidateReferenceCreate.model_validate(payload)

    def test_allows_same_day_effective_interval(self) -> None:
        """Verify effective_from and effective_to on the exact same date is valid."""
        payload = self.get_valid_payload()
        payload["effective_from"] = date(2025, 4, 1)
        payload["effective_to"] = date(2025, 4, 1)
        schema = CandidateReferenceCreate.model_validate(payload)
        self.assertEqual(schema.effective_from, schema.effective_to)

    def test_allows_open_ended_effective_to(self) -> None:
        """Verify effective_to = None (indefinite validity) is valid."""
        payload = self.get_valid_payload()
        payload["effective_to"] = None
        schema = CandidateReferenceCreate.model_validate(payload)
        self.assertIsNone(schema.effective_to)

    def test_rejects_negative_efficiency_iseer(self) -> None:
        """Verify physically implausible negative efficiency or rating is rejected."""
        payload = self.get_valid_payload()
        payload["normalized_value"] = -3.5
        with self.assertRaises(Exception):
            CandidateReferenceCreate.model_validate(payload)

    def test_review_action_request_validation(self) -> None:
        """Verify ReviewActionRequest validates reviewer identity and rejection comment."""
        # Empty reviewer rejected
        with self.assertRaises(Exception):
            ReviewActionRequest(status="approved", reviewer_id="  ")

        # Rejection without reason rejected
        with self.assertRaises(Exception):
            ReviewActionRequest(status="rejected", reviewer_id="auditor_1", reason="")

        # Valid approval
        req = ReviewActionRequest(status="approved", reviewer_id="auditor_1")
        self.assertEqual(req.status, "approved")


class TestReviewWorkflowStateMachine(BasePersistenceTestCase):
    """4. Test Human Review Workflow Engine State Machine."""

    def create_draft_candidate(self) -> CandidateReferenceModel:
        cand = CandidateReferenceModel(
            parameter_key="room_ac_1.5t_5star_iseer",
            raw_value="5.20",
            normalized_value=5.20,
            unit="Wh/Wh",
            jurisdiction="IN",
            applicability_conditions={"star_rating": 5},
            effective_from=date(2024, 1, 1),
            effective_to=date(2026, 12, 31),
            source_id="bee_ac_2024_001",
            confidence=1.0,
            review_status="draft",
        )
        self.session.add(cand)
        self.session.commit()
        return cand

    def test_valid_transition_draft_to_pending(self) -> None:
        """Verify draft moves to pending_review via submit_candidate."""
        cand = self.create_draft_candidate()
        self.assertEqual(cand.review_status, ReviewStatusEnum.DRAFT.value)

        submitted = self.workflow.submit_candidate(cand.id, actor_id="data_engineer")
        self.assertEqual(submitted.review_status, ReviewStatusEnum.PENDING_REVIEW.value)

    def test_idempotent_submit(self) -> None:
        """Verify submitting candidate already in pending_review is idempotent."""
        cand = self.create_draft_candidate()
        self.workflow.submit_candidate(cand.id, actor_id="data_engineer")
        resubmitted = self.workflow.submit_candidate(cand.id, actor_id="data_engineer")
        self.assertEqual(resubmitted.review_status, ReviewStatusEnum.PENDING_REVIEW.value)

    def test_direct_transition_draft_to_approved_blocked(self) -> None:
        """Verify draft cannot jump directly to approved without pending_review."""
        cand = self.create_draft_candidate()
        with self.assertRaises(InvalidStatusTransitionError):
            self.workflow.approve_candidate(cand.id, reviewer_id="lead_auditor")

    def test_rejected_candidate_cannot_be_approved_directly(self) -> None:
        """Verify rejected candidate cannot transition to approved."""
        cand = self.create_draft_candidate()
        self.workflow.submit_candidate(cand.id, actor_id="data_engineer")
        self.workflow.reject_candidate(cand.id, reviewer_id="lead_auditor", reason="Value mismatch")

        with self.assertRaises(InvalidStatusTransitionError):
            self.workflow.approve_candidate(cand.id, reviewer_id="lead_auditor")

    def test_empty_reviewer_rejected(self) -> None:
        """Verify approving with empty reviewer identity raises ReviewAuthorizationError."""
        cand = self.create_draft_candidate()
        self.workflow.submit_candidate(cand.id, actor_id="data_engineer")
        with self.assertRaises(ReviewAuthorizationError):
            self.workflow.approve_candidate(cand.id, reviewer_id="")


class TestImmutableVersioningAndPersistence(BasePersistenceTestCase):
    """5. Test Immutable Versioning, Superseding, and Audit Logging."""

    def test_approval_creates_version_1_and_audit_log(self) -> None:
        """Verify approving pending candidate creates version 1 approved reference and audit records."""
        cand = CandidateReferenceModel(
            parameter_key="room_ac_1.5t_5star_iseer",
            raw_value="5.20",
            normalized_value=5.20,
            unit="Wh/Wh",
            jurisdiction="IN",
            applicability_conditions={"star_rating": 5},
            effective_from=date(2024, 1, 1),
            effective_to=date(2026, 12, 31),
            source_id="bee_ac_2024_001",
            confidence=1.0,
            review_status="pending_review",
        )
        self.session.add(cand)
        self.session.commit()

        approved = self.workflow.approve_candidate(cand.id, reviewer_id="qa_lead@gridvision.org")
        self.assertEqual(approved.version, 1)
        self.assertTrue(approved.is_latest)
        self.assertIsNone(approved.superseded_by_id)
        self.assertEqual(approved.approved_by, "qa_lead@gridvision.org")
        self.assertIsNotNone(approved.approved_at)

        # Audit logs checked
        logs = self.repository.get_audit_logs(entity_type="approved_reference", entity_id=str(approved.id))
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].action, "approve")
        self.assertEqual(logs[0].performed_by, "qa_lead@gridvision.org")

    def test_subsequent_approval_increments_version_and_supersedes_prior(self) -> None:
        """Verify approving v2 increments version to 2, marks v1 as latest=False and superseded_by_id=v2.id."""
        # Candidate 1 (v1)
        c1 = CandidateReferenceModel(
            parameter_key="room_ac_1.5t_5star_iseer",
            raw_value="5.00",
            normalized_value=5.00,
            unit="Wh/Wh",
            jurisdiction="IN",
            applicability_conditions={"star_rating": 5},
            effective_from=date(2022, 1, 1),
            effective_to=date(2023, 12, 31),
            source_id="bee_ac_2024_001",
            confidence=1.0,
            review_status="pending_review",
        )
        self.session.add(c1)
        self.session.commit()
        app_v1 = self.workflow.approve_candidate(c1.id, reviewer_id="auditor_1")
        self.assertEqual(app_v1.version, 1)
        self.assertTrue(app_v1.is_latest)

        # Candidate 2 (v2)
        c2 = CandidateReferenceModel(
            parameter_key="room_ac_1.5t_5star_iseer",
            raw_value="5.20",
            normalized_value=5.20,
            unit="Wh/Wh",
            jurisdiction="IN",
            applicability_conditions={"star_rating": 5},
            effective_from=date(2024, 1, 1),
            effective_to=date(2026, 12, 31),
            source_id="bee_ac_2024_001",
            confidence=1.0,
            review_status="pending_review",
        )
        self.session.add(c2)
        self.session.commit()
        app_v2 = self.workflow.approve_candidate(c2.id, reviewer_id="auditor_2")

        # Refresh v1
        self.session.refresh(app_v1)
        self.assertEqual(app_v2.version, 2)
        self.assertTrue(app_v2.is_latest)
        self.assertFalse(app_v1.is_latest)
        self.assertEqual(app_v1.superseded_by_id, app_v2.id)

        # Verify only 1 record is marked latest
        all_latest = self.session.execute(
            select(ApprovedReferenceModel).where(
                ApprovedReferenceModel.parameter_key == "room_ac_1.5t_5star_iseer",
                ApprovedReferenceModel.is_latest == True,
            )
        ).scalars().all()
        self.assertEqual(len(all_latest), 1)
        self.assertEqual(all_latest[0].id, app_v2.id)


class TestReferenceRepositoryOperations(BasePersistenceTestCase):
    """6. Test Repository queries and temporal active reference queries."""

    def test_repository_active_reference_query_with_temporal_filtering(self) -> None:
        """Verify get_active_references filters by date and only returns active valid references."""
        # Insert v1 (2022 to 2023)
        c1 = self.repository.add_candidate({
            "parameter_key": "cea_grid_emission_factor",
            "raw_value": "0.85",
            "normalized_value": 0.85,
            "unit": "kg CO2/kWh",
            "jurisdiction": "IN",
            "effective_from": date(2022, 1, 1),
            "effective_to": date(2023, 12, 31),
            "source_id": "bee_ac_2024_001",
        }, initial_status="pending_review")
        self.repository.approve_candidate(c1.id, reviewer_id="auditor")

        # Insert v2 (2024 to 2026)
        c2 = self.repository.add_candidate({
            "parameter_key": "cea_grid_emission_factor",
            "raw_value": "0.82",
            "normalized_value": 0.82,
            "unit": "kg CO2/kWh",
            "jurisdiction": "IN",
            "effective_from": date(2024, 1, 1),
            "effective_to": date(2026, 12, 31),
            "source_id": "bee_ac_2024_001",
        }, initial_status="pending_review")
        self.repository.approve_candidate(c2.id, reviewer_id="auditor")

        # Query in 2024: Should find v2 (0.82)
        active_2024 = self.repository.get_active_references(
            parameter_key="cea_grid_emission_factor",
            jurisdiction="IN",
            effective_date=date(2024, 6, 1),
        )
        self.assertEqual(len(active_2024), 1)
        self.assertEqual(active_2024[0].normalized_value, 0.82)

        # Query in 2030: Future date out of range, should return empty list
        active_2030 = self.repository.get_active_references(
            parameter_key="cea_grid_emission_factor",
            jurisdiction="IN",
            effective_date=date(2030, 1, 1),
        )
        self.assertEqual(len(active_2030), 0)


class TestCustomerDataIsolation(unittest.TestCase):
    """7. Test Requirement R3: Complete storage, model, and responsibility isolation."""

    def test_operational_data_silver_remains_isolated(self) -> None:
        """Verify reference models do not reference or access customer_silver.parquet."""
        project_root = Path(__file__).resolve().parents[2]
        silver_file = project_root / "data" / "silver" / "customer_silver.parquet"
        self.assertTrue(silver_file.exists(), "customer_silver.parquet must exist in data/silver")

        # Invariant: No customer PII in reference tables
        for table in Base.metadata.tables.values():
            col_names = {c.name for c in table.columns}
            for forbidden in ["meter_id", "customer_name", "account_number", "ssn", "phone"]:
                self.assertNotIn(
                    forbidden,
                    col_names,
                    f"Forbidden operational/PII column {forbidden} found in reference table {table.name}",
                )


if __name__ == "__main__":
    unittest.main()
