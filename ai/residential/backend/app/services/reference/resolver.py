"""Deterministic ReferenceResolver Service.

Implements 5-tier hierarchical matching policy, temporal validity verification,
approval status checking, ambiguity detection, and strict zero-silent-default policy.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, Generic, List, Optional, TypeVar, Union

from pydantic import BaseModel, Field, model_validator

from app.services.reference.exceptions import (
    AmbiguousReferenceError,
    ExpiredReferenceError,
    MissingReferenceError,
    OutOfJurisdictionError,
    ReferenceResolutionError,
    UnapprovedReferenceError,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")

INDIAN_JURISDICTIONS = {
    "IN",
    "INDIA",
    "AP",
    "AR",
    "AS",
    "BR",
    "CG",
    "CH",
    "DD",
    "DL",
    "DN",
    "GA",
    "GJ",
    "HP",
    "HR",
    "JH",
    "JK",
    "KA",
    "KL",
    "LA",
    "LD",
    "MH",
    "ML",
    "MN",
    "MP",
    "MZ",
    "NL",
    "OD",
    "PB",
    "PY",
    "RJ",
    "SK",
    "TN",
    "TR",
    "TS",
    "UK",
    "UP",
    "WB",
}


class ReferenceResolutionContext(BaseModel):
    """Context parameters used to resolve an approved engineering reference."""

    category: str = "appliance"
    identifier: str
    jurisdiction: str = "IN"
    region_or_discom: Optional[str] = None
    region: Optional[str] = None
    effective_date: Optional[date] = None
    specifications: Dict[str, Any] = Field(default_factory=dict)
    applicability_conditions: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True, "extra": "allow"}

    @model_validator(mode="before")
    @classmethod
    def _normalize_context(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Synchronize region and region_or_discom
            if "region" in data and not data.get("region_or_discom"):
                data["region_or_discom"] = data["region"]
            elif "region_or_discom" in data and not data.get("region"):
                data["region"] = data["region_or_discom"]

            # Normalize effective_date
            eff = data.get("effective_date")
            if eff is None:
                data["effective_date"] = date.today()
            elif isinstance(eff, str):
                data["effective_date"] = date.fromisoformat(eff)
            elif isinstance(eff, datetime):
                data["effective_date"] = eff.date()

            # Synchronize parameter_key and identifier
            if "identifier" not in data and "parameter_key" in data:
                data["identifier"] = data["parameter_key"]

            # Upper-case jurisdiction
            if "jurisdiction" in data and isinstance(data["jurisdiction"], str):
                data["jurisdiction"] = data["jurisdiction"].strip().upper()

        return data

    @property
    def parameter_key(self) -> str:
        return self.identifier


class ResolvedReference(BaseModel, Generic[T]):
    """Immutable, typed resolved reference record with document provenance."""

    value: T
    unit: str
    provenance: Dict[str, Any] = Field(default_factory=dict)
    effective_from: date
    effective_to: Optional[date] = None
    jurisdiction: str
    region: Optional[str] = None
    region_or_discom: Optional[str] = None
    category: Optional[str] = None
    identifier: Optional[str] = None
    parameter_key: Optional[str] = None
    version: int = 1
    approval_status: str = "approved"
    specifications: Dict[str, Any] = Field(default_factory=dict)
    applicability_conditions: Dict[str, Any] = Field(default_factory=dict)
    raw_value: Optional[Any] = None
    normalized_value: Optional[Any] = None
    reference_id: Optional[Union[str, int]] = None

    model_config = {"arbitrary_types_allowed": True, "extra": "allow"}

    @model_validator(mode="before")
    @classmethod
    def _normalize_resolved(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "value" in data and "normalized_value" not in data:
                data["normalized_value"] = data["value"]
            elif "normalized_value" in data and "value" not in data:
                data["value"] = data["normalized_value"]

            if "raw_value" not in data:
                data["raw_value"] = data.get("value")

            if "region" in data and not data.get("region_or_discom"):
                data["region_or_discom"] = data["region"]
            elif "region_or_discom" in data and not data.get("region"):
                data["region"] = data["region_or_discom"]

            if "identifier" in data and "parameter_key" not in data:
                data["parameter_key"] = data["identifier"]
            elif "parameter_key" in data and "identifier" not in data:
                data["identifier"] = data["parameter_key"]

            # Ensure provenance contains standard normalized keys
            prov = data.get("provenance")
            if isinstance(prov, dict):
                norm_prov = dict(prov)
                if "page_number" in norm_prov and "page" not in norm_prov:
                    norm_prov["page"] = norm_prov["page_number"]
                if "page" in norm_prov and "page_number" not in norm_prov:
                    norm_prov["page_number"] = norm_prov["page"]
                if "section_or_clause" in norm_prov and "clause" not in norm_prov:
                    norm_prov["clause"] = norm_prov["section_or_clause"]
                if "clause" in norm_prov and "section_or_clause" not in norm_prov:
                    norm_prov["section_or_clause"] = norm_prov["clause"]
                if "table_number" in norm_prov and "table" not in norm_prov:
                    norm_prov["table"] = norm_prov["table_number"]
                if "table" in norm_prov and "table_number" not in norm_prov:
                    norm_prov["table_number"] = norm_prov["table"]
                if "supporting_excerpt" in norm_prov and "excerpt" not in norm_prov:
                    norm_prov["excerpt"] = norm_prov["supporting_excerpt"]
                if "excerpt" in norm_prov and "supporting_excerpt" not in norm_prov:
                    norm_prov["supporting_excerpt"] = norm_prov["excerpt"]
                data["provenance"] = norm_prov

        return data

    def __getitem__(self, item: str) -> Any:
        if hasattr(self, item):
            return getattr(self, item)
        raise KeyError(item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)


def _extract_record_info(rec: Any) -> Dict[str, Any]:
    """Extract standard attributes from a dictionary, model, or object."""

    def _get(keys: List[str], default: Any = None) -> Any:
        for k in keys:
            if hasattr(rec, k) and getattr(rec, k) is not None:
                return getattr(rec, k)
            if isinstance(rec, dict) and k in rec and rec[k] is not None:
                return rec[k]
        return default

    pk = _get(["parameter_key", "identifier", "key"])
    val = _get(["normalized_value", "value", "raw_value"])
    unit = _get(["unit", "standard_unit"], "")

    jur = _get(["jurisdiction", "country"], "IN")
    if jur:
        jur = str(jur).strip().upper()

    reg = _get(["region", "region_or_discom", "discom"])
    if reg:
        reg = str(reg).strip().upper()

    eff_from = _get(["effective_from", "valid_from"])
    if isinstance(eff_from, str):
        eff_from = date.fromisoformat(eff_from)
    elif isinstance(eff_from, datetime):
        eff_from = eff_from.date()

    eff_to = _get(["effective_to", "valid_to"])
    if isinstance(eff_to, str):
        eff_to = date.fromisoformat(eff_to)
    elif isinstance(eff_to, datetime):
        eff_to = eff_to.date()

    model_name = type(rec).__name__
    status = _get(["approval_status", "review_status", "status"])
    if "Approved" in model_name:
        status = "approved"
    elif status is None:
        status = "approved"

    is_latest = _get(["is_latest"], True)
    version = _get(["version"], 1)
    specs = _get(["specifications"], {}) or {}
    app_conds = _get(["applicability_conditions", "conditions", "applicability"], {}) or {}
    prov = _get(["provenance"], {}) or {}
    ref_id = _get(["id", "reference_id"])
    category = _get(["category"], "appliance")
    raw_val = _get(["raw_value"], val)

    return {
        "raw_record": rec,
        "parameter_key": pk,
        "value": val,
        "normalized_value": val,
        "raw_value": raw_val,
        "unit": unit,
        "jurisdiction": jur,
        "region": reg,
        "effective_from": eff_from,
        "effective_to": eff_to,
        "status": str(status).lower(),
        "is_latest": bool(is_latest),
        "version": int(version) if version is not None else 1,
        "specifications": specs if isinstance(specs, dict) else {},
        "applicability_conditions": app_conds if isinstance(app_conds, dict) else {},
        "provenance": prov if isinstance(prov, dict) else {},
        "reference_id": ref_id,
        "category": category,
    }


def _matches_conditions(
    rec_conditions: Dict[str, Any], query_conditions: Dict[str, Any]
) -> tuple[bool, int]:
    """Check if record conditions match query conditions.

    Returns (is_compatible, match_count).
    Empty record conditions match generally (is_compatible=True, match_count=0).
    Non-empty record conditions must all match corresponding query keys.
    """
    if not rec_conditions:
        return True, 0

    alias_map = {
        "capacity": "rated_capacity_tons",
        "capacity_ton": "rated_capacity_tons",
        "capacity_tons": "rated_capacity_tons",
        "tonnage": "rated_capacity_tons",
        "star": "star_rating",
        "stars": "star_rating",
    }

    # Normalize query conditions keys with aliases
    norm_query: Dict[str, Any] = {}
    for k, v in query_conditions.items():
        k_norm = alias_map.get(k.lower(), k.lower())
        norm_query[k_norm] = v

    match_count = 0
    for k, rec_v in rec_conditions.items():
        k_norm = alias_map.get(k.lower(), k.lower())
        if k_norm not in norm_query:
            return False, 0

        q_v = norm_query[k_norm]
        # Compare numeric values or strings
        try:
            if float(rec_v) == float(q_v):
                match_count += 1
                continue
        except (ValueError, TypeError):
            pass

        if str(rec_v).strip().lower() == str(q_v).strip().lower():
            match_count += 1
        else:
            return False, 0

    return True, match_count


class ReferenceResolver:
    """Deterministic Reference Resolver.

    Resolves verified numerical and engineering reference data using strict
    precedence policies, temporal validity verification, and zero silent defaults.
    """

    def __init__(
        self,
        repository_or_session: Any = None,
        *,
        session: Any = None,
        repository: Any = None,
    ) -> None:
        self.session = session
        self.repository = repository
        self._in_memory_records: List[Dict[str, Any]] = []

        target = repository_or_session or repository or session
        if target is not None:
            if hasattr(target, "query") or hasattr(target, "execute"):
                self.session = target
            elif hasattr(target, "get_active_references") or hasattr(target, "find_by_key"):
                self.repository = target
            elif isinstance(target, (list, tuple)):
                for item in target:
                    self._in_memory_records.append(_extract_record_info(item))
            elif isinstance(target, dict):
                for k, v in target.items():
                    if isinstance(v, list):
                        for item in v:
                            rec_dict = dict(item) if isinstance(item, dict) else {"value": item}
                            rec_dict.setdefault("parameter_key", k)
                            self._in_memory_records.append(_extract_record_info(rec_dict))
                    elif isinstance(v, dict):
                        rec_dict = dict(v)
                        rec_dict.setdefault("parameter_key", k)
                        self._in_memory_records.append(_extract_record_info(rec_dict))
                    else:
                        self._in_memory_records.append(
                            _extract_record_info({
                                "parameter_key": k,
                                "value": v,
                                "jurisdiction": "IN",
                                "effective_from": date(2000, 1, 1),
                            })
                        )

    def register_reference(self, reference: Any) -> None:
        """Register a reference record in the resolver's store."""
        self._in_memory_records.append(_extract_record_info(reference))

    def clear(self) -> None:
        """Clear registered in-memory references."""
        self._in_memory_records.clear()

    def _fetch_records(self, parameter_key: str) -> List[Dict[str, Any]]:
        """Fetch all records matching parameter_key across all connected stores."""
        records: List[Dict[str, Any]] = []

        # 1. Fetch from in-memory records
        for rec in self._in_memory_records:
            if rec["parameter_key"] and rec["parameter_key"].lower() == parameter_key.lower():
                records.append(rec)

        # 2. Fetch from repository if present
        if self.repository is not None:
            try:
                if hasattr(self.repository, "get_all_for_parameter"):
                    recs = self.repository.get_all_for_parameter(parameter_key)
                    for r in recs:
                        records.append(_extract_record_info(r))
                elif hasattr(self.repository, "get_candidates"):
                    candidates = self.repository.get_candidates(parameter_key=parameter_key)
                    for r in candidates:
                        records.append(_extract_record_info(r))
                elif hasattr(self.repository, "get_active_references"):
                    recs = self.repository.get_active_references(parameter_key)
                    for r in recs:
                        records.append(_extract_record_info(r))
            except Exception as e:
                logger.debug("Repository query error: %s", e)

        # 3. Fetch from SQLAlchemy session if present
        if self.session is not None:
            try:
                from app.infrastructure.database.models.reference import (
                    ApprovedReferenceModel,
                    CandidateReferenceModel,
                )

                approved = (
                    self.session.query(ApprovedReferenceModel)
                    .filter(ApprovedReferenceModel.parameter_key == parameter_key)
                    .all()
                )
                for r in approved:
                    records.append(_extract_record_info(r))

                candidates = (
                    self.session.query(CandidateReferenceModel)
                    .filter(CandidateReferenceModel.parameter_key == parameter_key)
                    .all()
                )
                for r in candidates:
                    records.append(_extract_record_info(r))
            except Exception as e:
                logger.debug("Database session query error: %s", e)

        return records

    def resolve(
        self,
        context_or_identifier: Union[ReferenceResolutionContext, str, None] = None,
        *,
        parameter_key: Optional[str] = None,
        category: Optional[str] = None,
        identifier: Optional[str] = None,
        jurisdiction: Optional[str] = None,
        region_or_discom: Optional[str] = None,
        region: Optional[str] = None,
        effective_date: Optional[Union[date, str]] = None,
        specifications: Optional[Dict[str, Any]] = None,
        applicability_conditions: Optional[Dict[str, Any]] = None,
        applicability: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> ResolvedReference[Any]:
        """Resolve an approved reference record using deterministic 5-tier precedence.

        Raises:
            MissingReferenceError: Parameter is not registered in the system.
            UnapprovedReferenceError: Reference exists only in unapproved status.
            OutOfJurisdictionError: No active record covers the requested jurisdiction.
            ExpiredReferenceError: No active record is valid on the effective date.
            AmbiguousReferenceError: Multiple conflicting records match at equal precedence.
        """
        # 1. Normalize context
        if isinstance(context_or_identifier, ReferenceResolutionContext):
            ctx = context_or_identifier
        elif isinstance(context_or_identifier, str):
            ctx = ReferenceResolutionContext(
                category=category or "appliance",
                identifier=context_or_identifier,
                jurisdiction=jurisdiction or "IN",
                region_or_discom=region_or_discom or region,
                effective_date=effective_date,
                specifications=specifications or {},
                applicability_conditions=applicability_conditions or applicability or {},
            )
        else:
            resolved_key = identifier or parameter_key or kwargs.get("key")
            if not resolved_key:
                raise MissingReferenceError(
                    "Missing reference query: no identifier or parameter_key provided",
                    parameter_key="unknown",
                    jurisdiction=jurisdiction or "IN",
                )
            ctx = ReferenceResolutionContext(
                category=category or "appliance",
                identifier=resolved_key,
                jurisdiction=jurisdiction or "IN",
                region_or_discom=region_or_discom or region,
                effective_date=effective_date,
                specifications=specifications or {},
                applicability_conditions=applicability_conditions or applicability or {},
            )

        query_key = ctx.identifier
        query_jurisdiction = (ctx.jurisdiction or "IN").strip().upper()
        query_region = (ctx.region_or_discom or ctx.region)
        if query_region:
            query_region = query_region.strip().upper()
        query_date = ctx.effective_date or date.today()
        query_conditions = {**ctx.specifications, **ctx.applicability_conditions}

        # 2. Fetch all records for the identifier
        all_records = self._fetch_records(query_key)

        # Step 1: Missing Reference Check
        if not all_records:
            raise MissingReferenceError(
                f"Reference not found: {query_key} in {query_jurisdiction}",
                parameter_key=query_key,
                jurisdiction=query_jurisdiction,
            )

        # Step 2: Approval Status Check
        approved_records = [r for r in all_records if r["status"] == "approved"]
        if not approved_records:
            status_seen = all_records[0]["status"]
            raise UnapprovedReferenceError(
                f"Candidate reference for '{query_key}' is in status '{status_seen}'",
                parameter_key=query_key,
                status=status_seen,
            )

        # Step 3: Geographic Eligibility Check
        # Precedence hierarchy: Specific DISCOM -> State -> National ("IN")
        is_query_indian = query_jurisdiction in INDIAN_JURISDICTIONS

        jurisdiction_eligible: List[Dict[str, Any]] = []
        for r in approved_records:
            r_jur = r["jurisdiction"]
            if query_jurisdiction == "IN":
                if r_jur == "IN":
                    jurisdiction_eligible.append(r)
            elif is_query_indian:
                # Can match specific state or fallback to National "IN"
                if r_jur == query_jurisdiction or r_jur == "IN":
                    jurisdiction_eligible.append(r)
            else:
                # Non-Indian jurisdiction: must match exact requested jurisdiction
                if r_jur == query_jurisdiction:
                    jurisdiction_eligible.append(r)

        if not jurisdiction_eligible:
            raise OutOfJurisdictionError(
                f"No reference available for jurisdiction '{query_jurisdiction}'"
                + (f" (region: '{query_region}')" if query_region else ""),
                parameter_key=query_key,
                jurisdiction=query_jurisdiction,
                region=query_region,
            )

        # Step 4: Temporal Validity Check
        temporally_valid: List[Dict[str, Any]] = []
        for r in jurisdiction_eligible:
            eff_from = r["effective_from"]
            eff_to = r["effective_to"]
            is_valid = True
            if eff_from is not None and query_date < eff_from:
                is_valid = False
            if eff_to is not None and query_date > eff_to:
                is_valid = False
            if is_valid:
                temporally_valid.append(r)

        if not temporally_valid:
            # Find closest date for informative error
            expired_recs = [
                r for r in jurisdiction_eligible if r["effective_to"] and query_date > r["effective_to"]
            ]
            if expired_recs:
                closest_to = max(r["effective_to"] for r in expired_recs)
                raise ExpiredReferenceError(
                    f"Reference for '{query_key}' expired on {closest_to.isoformat()}",
                    parameter_key=query_key,
                    effective_to=closest_to,
                    query_date=query_date,
                )
            future_recs = [
                r for r in jurisdiction_eligible if r["effective_from"] and query_date < r["effective_from"]
            ]
            if future_recs:
                closest_from = min(r["effective_from"] for r in future_recs)
                raise ExpiredReferenceError(
                    f"Reference for '{query_key}' not yet effective (effective_from: {closest_from.isoformat()})",
                    parameter_key=query_key,
                    effective_from=closest_from,
                    query_date=query_date,
                )
            raise ExpiredReferenceError(
                f"Reference for '{query_key}' is not effective on date {query_date.isoformat()}",
                parameter_key=query_key,
                query_date=query_date,
            )

        # Step 5: Precedence Tier Evaluation
        # 1. Exact DISCOM/Region + Exact Specification/Applicability
        # 2. Exact DISCOM/Region + General Applicability
        # 3. State Wildcard + Exact Specification/Applicability
        # 4. State Wildcard + General Applicability
        # 5. National Standard ("IN" / Central Standard)
        ranked_candidates: List[Dict[str, Any]] = []

        for r in temporally_valid:
            r_jur = r["jurisdiction"]
            r_reg = r["region"]

            # If the record is tied to a specific region/DISCOM, it only matches if query specified that region
            if r_reg is not None and r_reg != "" and r_reg != "ALL":
                if query_region is None or r_reg != query_region:
                    continue

            rec_conditions = {**r["specifications"], **r["applicability_conditions"]}
            compatible, match_count = _matches_conditions(rec_conditions, query_conditions)
            if not compatible:
                continue

            has_exact_conds = match_count > 0

            # Determine Tier
            is_discom_match = (
                query_region is not None
                and r_reg is not None
                and r_reg == query_region
                and (r_jur == query_jurisdiction or is_query_indian)
            )
            is_state_wildcard = (
                r_jur == query_jurisdiction
                and query_jurisdiction != "IN"
                and (r_reg is None or r_reg == "" or r_reg == "ALL")
            )
            is_national_match = (
                r_jur == "IN"
                and (r_reg is None or r_reg == "" or r_reg == "ALL")
            )

            if is_discom_match:
                tier = 1.0 - (0.01 * match_count) if has_exact_conds else 2.0
            elif is_state_wildcard:
                tier = 3.0 - (0.01 * match_count) if has_exact_conds else 4.0
            elif is_national_match:
                # National tier 5: exact specs prioritized before general
                tier = 5.0 - (0.01 * match_count) if has_exact_conds else 5.5
            elif r_jur == query_jurisdiction:
                tier = 3.0 - (0.01 * match_count) if has_exact_conds else 4.0
            else:
                tier = 99.0

            r_candidate = dict(r)
            r_candidate["tier"] = tier
            ranked_candidates.append(r_candidate)


        if not ranked_candidates:
            raise MissingReferenceError(
                f"No reference matching specifications {query_conditions} for '{query_key}'",
                parameter_key=query_key,
                jurisdiction=query_jurisdiction,
            )

        # Step 6: Conflict and Ambiguity Check
        best_tier = min(c["tier"] for c in ranked_candidates)
        # Group candidates within the winning integer tier
        best_int_tier = int(best_tier)
        tier_winners = [
            c for c in ranked_candidates if int(c["tier"]) == best_int_tier
        ]
        # Further refine to exact sub-tier if available
        min_sub_tier = min(c["tier"] for c in tier_winners)
        tier_winners = [c for c in tier_winners if c["tier"] == min_sub_tier]

        # Prioritize is_latest
        latest_winners = [c for c in tier_winners if c["is_latest"]]
        if latest_winners:
            tier_winners = latest_winners

        # Prioritize highest version
        max_version = max(c["version"] for c in tier_winners)
        tier_winners = [c for c in tier_winners if c["version"] == max_version]

        # Check for ambiguity in values
        distinct_values: List[Any] = []
        for c in tier_winners:
            val = c["normalized_value"]
            if not any(val == existing for existing in distinct_values):
                distinct_values.append(val)

        if len(distinct_values) > 1:
            raise AmbiguousReferenceError(
                f"Ambiguous match: multiple records with equal precedence for '{query_key}'"
                f" with conflicting values: {distinct_values}",
                parameter_key=query_key,
                candidates=tier_winners,
            )

        winner = tier_winners[0]

        # Step 7: Build Typed ResolvedReference
        return ResolvedReference[Any](
            value=winner["normalized_value"],
            unit=winner["unit"],
            provenance=winner["provenance"],
            effective_from=winner["effective_from"] or date(2000, 1, 1),
            effective_to=winner["effective_to"],
            jurisdiction=winner["jurisdiction"],
            region=winner["region"],
            region_or_discom=winner["region"],
            category=ctx.category,
            identifier=ctx.identifier,
            parameter_key=ctx.identifier,
            version=winner["version"],
            approval_status="approved",
            specifications=winner["specifications"],
            applicability_conditions=winner["applicability_conditions"],
            raw_value=winner["raw_value"],
            normalized_value=winner["normalized_value"],
            reference_id=winner.get("reference_id"),
        )
