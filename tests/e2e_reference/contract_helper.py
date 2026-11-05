"""Contract helper and interface dynamic resolver for GridVision E2E Reference Data testing.

This helper isolates tests from internal implementation file naming nuances,
allowing tests to be written purely against the public interface contracts defined in
PROJECT.md, TEST_INFRA.md, and ORIGINAL_REQUEST.md.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, Callable, Dict, Optional, Type

logger = logging.getLogger("gridvision.tests.contract_helper")


def _safe_import(module_path: str, class_names: list[str]) -> dict[str, Any]:
    """Attempt importing symbols from a module without raising ImportError."""
    result = {name: None for name in class_names}
    try:
        mod = importlib.import_module(module_path)
        for name in class_names:
            if hasattr(mod, name):
                result[name] = getattr(mod, name)
    except Exception as e:
        logger.debug("Safe import failed for %s: %s", module_path, e)
    return result


# Storage Abstraction
_storage_base = _safe_import("app.infrastructure.storage.base", ["BaseDocumentStorage"])
BaseDocumentStorage = _storage_base["BaseDocumentStorage"]

_storage_local = _safe_import(
    "app.infrastructure.storage.local",
    ["LocalFileSystemStorageAdapter", "LocalStorageAdapter"],
)
LocalFileSystemStorageAdapter = (
    _storage_local["LocalFileSystemStorageAdapter"]
    or _storage_local["LocalStorageAdapter"]
)

# Security
_security = _safe_import(
    "app.services.reference.security",
    ["SSRFSafeFetcher", "DocumentValidator", "SSRFProtectionError", "SSRFSecurityError", "InvalidDocumentError"],
)
SSRFSafeFetcher = _security["SSRFSafeFetcher"]
DocumentValidator = _security["DocumentValidator"]

# Ingestion & Extraction
_doc_service = _safe_import(
    "app.services.reference.document_service",
    ["DocumentService", "SourceRegistryService"],
)
DocumentService = _doc_service["DocumentService"] or _doc_service["SourceRegistryService"]

_extractor = _safe_import(
    "app.services.reference.extractor",
    ["StructureAwareExtractor", "DocumentExtractor"],
)
StructureAwareExtractor = _extractor["StructureAwareExtractor"] or _extractor["DocumentExtractor"]

# Relational Database Models & Connection
_db_conn = _safe_import(
    "app.infrastructure.database.connection",
    ["get_db_session", "SessionLocal", "engine", "init_db"],
)
get_db_session = _db_conn["get_db_session"]
SessionLocal = _db_conn["SessionLocal"]
db_engine = _db_conn["engine"]
init_db = _db_conn["init_db"]

_models = _safe_import(
    "app.infrastructure.database.models.reference",
    [
        "Base",
        "SourceModel",
        "SourceDocumentRecord",
        "DocumentArtifactModel",
        "DocumentArtifactRecord",
        "ReferenceParameterModel",
        "CandidateReferenceModel",
        "ApprovedReferenceModel",
        "ApprovedReferenceRecord",
        "ReferenceAuditLogModel",
    ],
)
Base = _models["Base"]
SourceModel = _models["SourceModel"] or _models["SourceDocumentRecord"]
DocumentArtifactModel = _models["DocumentArtifactModel"] or _models["DocumentArtifactRecord"]
ReferenceParameterModel = _models["ReferenceParameterModel"]
CandidateReferenceModel = _models["CandidateReferenceModel"]
ApprovedReferenceModel = _models["ApprovedReferenceModel"] or _models["ApprovedReferenceRecord"]
ReferenceAuditLogModel = _models["ReferenceAuditLogModel"]

# Candidate Lifecycle & Schemas
_lifecycle = _safe_import(
    "app.services.reference.lifecycle",
    [
        "CandidateReferenceSchema",
        "CandidateLifecycleService",
        "ReviewWorkflowService",
        "EnergyUnitEnum",
    ],
)
CandidateReferenceSchema = _lifecycle["CandidateReferenceSchema"]
CandidateLifecycleService = (
    _lifecycle["CandidateLifecycleService"] or _lifecycle["ReviewWorkflowService"]
)
EnergyUnitEnum = _lifecycle["EnergyUnitEnum"]

# ReferenceResolver
_resolver = _safe_import(
    "app.services.reference.resolver",
    [
        "ReferenceResolver",
        "ReferenceResolutionContext",
        "ResolvedReference",
    ],
)
ReferenceResolver = _resolver["ReferenceResolver"]
ReferenceResolutionContext = _resolver["ReferenceResolutionContext"]
ResolvedReference = _resolver["ResolvedReference"]

# Exceptions
_exceptions = _safe_import(
    "app.services.reference.exceptions",
    [
        "ReferenceResolutionError",
        "MissingReferenceError",
        "ReferenceNotFoundError",
        "UnapprovedReferenceError",
        "ExpiredReferenceError",
        "OutOfJurisdictionError",
        "AmbiguousReferenceError",
        "SSRFSecurityError",
        "InvalidDocumentError",
        "DocumentValidationError",
        "DuplicateDocumentError",
    ],
)
class MockReferenceResolutionError(Exception): pass
class MockMissingReferenceError(MockReferenceResolutionError): pass
class MockUnapprovedReferenceError(MockReferenceResolutionError): pass
class MockExpiredReferenceError(MockReferenceResolutionError): pass
class MockOutOfJurisdictionError(MockReferenceResolutionError): pass
class MockAmbiguousReferenceError(MockReferenceResolutionError): pass
class MockSSRFSecurityError(Exception): pass
class MockInvalidDocumentError(Exception): pass
class MockDuplicateDocumentError(Exception): pass

ReferenceResolutionError = _exceptions["ReferenceResolutionError"] or MockReferenceResolutionError
MissingReferenceError = (
    _exceptions["MissingReferenceError"]
    or _exceptions["ReferenceNotFoundError"]
    or MockMissingReferenceError
)
UnapprovedReferenceError = _exceptions["UnapprovedReferenceError"] or MockUnapprovedReferenceError
ExpiredReferenceError = _exceptions["ExpiredReferenceError"] or MockExpiredReferenceError
OutOfJurisdictionError = _exceptions["OutOfJurisdictionError"] or MockOutOfJurisdictionError
AmbiguousReferenceError = _exceptions["AmbiguousReferenceError"] or MockAmbiguousReferenceError
SSRFSecurityError = (
    _exceptions["SSRFSecurityError"]
    or _security["SSRFSecurityError"]
    or _security["SSRFProtectionError"]
    or MockSSRFSecurityError
)
DocumentValidationError = _exceptions["DocumentValidationError"] or MockInvalidDocumentError
InvalidDocumentError = (
    _exceptions["InvalidDocumentError"]
    or _exceptions["DocumentValidationError"]
    or _security["InvalidDocumentError"]
    or MockInvalidDocumentError
)
DuplicateDocumentError = _exceptions["DuplicateDocumentError"] or MockDuplicateDocumentError

# Existing Domain Engines (Already present in backend/app)
try:
    from app.domain.residential.appliance_engine import ApplianceLifecycleCostEngine
except ImportError:
    ApplianceLifecycleCostEngine = None

try:
    from app.domain.residential.building_engine import BuildingEnergyPlanningEngine
except ImportError:
    BuildingEnergyPlanningEngine = None

try:
    from app.domain.residential import reference_data
except ImportError:
    reference_data = None


# Storage Contract Helper Invokers
def invoke_save_original(storage: Any, source_id: str, filename: str, content: bytes) -> str:
    """Invoke save_original / store_original polymorphically."""
    if hasattr(storage, "save_original"):
        return storage.save_original(source_id=source_id, filename=filename, content=content)
    if hasattr(storage, "store_original"):
        # check parameter names
        try:
            return storage.store_original(source_id=source_id, filename=filename, content=content)
        except TypeError:
            return storage.store_original(content, f"{source_id}/{filename}", "application/octet-stream")
    raise AttributeError("Storage adapter has neither save_original nor store_original")


def invoke_get_original(storage: Any, path_or_key: str) -> bytes:
    """Invoke get_original / retrieve_original polymorphically."""
    if hasattr(storage, "get_original"):
        return storage.get_original(path_or_key)
    if hasattr(storage, "retrieve_original"):
        return storage.retrieve_original(path_or_key)
    raise AttributeError("Storage adapter has neither get_original nor retrieve_original")


def invoke_save_extracted(storage: Any, source_id: str, structure: dict) -> str:
    """Invoke save_extracted / store_extracted polymorphically."""
    if hasattr(storage, "save_extracted"):
        return storage.save_extracted(source_id=source_id, structure=structure)
    if hasattr(storage, "store_extracted"):
        try:
            return storage.store_extracted(source_id=source_id, structure=structure)
        except TypeError:
            return storage.store_extracted(structure, f"{source_id}/extracted_structure.json")
    raise AttributeError("Storage adapter has neither save_extracted nor store_extracted")


def invoke_get_extracted(storage: Any, path_or_key: str) -> dict:
    """Invoke get_extracted / retrieve_extracted polymorphically."""
    if hasattr(storage, "get_extracted"):
        return storage.get_extracted(path_or_key)
    if hasattr(storage, "retrieve_extracted"):
        return storage.retrieve_extracted(path_or_key)
    raise AttributeError("Storage adapter has neither get_extracted nor retrieve_extracted")


def invoke_validate_url(fetcher: Any, url: str) -> bool:
    """Check if URL is safe or raises SSRF security error."""
    if hasattr(fetcher, "is_safe_url"):
        return fetcher.is_safe_url(url)
    if hasattr(fetcher, "validate_url"):
        return fetcher.validate_url(url)
    if hasattr(fetcher, "fetch"):
        fetcher.fetch(url)
        return True
    return False


def invoke_resolve(
    resolver: Any,
    parameter_key: str,
    jurisdiction: str = "IN",
    effective_date: Any = None,
    applicability: Optional[dict] = None,
    specifications: Optional[dict] = None,
    category: Optional[str] = None,
    region: Optional[str] = None,
) -> Any:
    """Invoke ReferenceResolver.resolve polymorphically either with context or kwargs."""
    if hasattr(resolver, "resolve"):
        # Check if resolver takes ReferenceResolutionContext
        if ReferenceResolutionContext is not None:
            try:
                ctx = ReferenceResolutionContext(
                    category=category or "appliance",
                    identifier=parameter_key,
                    jurisdiction=jurisdiction,
                    region_or_discom=region,
                    effective_date=effective_date,
                    specifications=specifications or {},
                    applicability_conditions=applicability or {},
                )
                return resolver.resolve(ctx)
            except Exception:
                pass
        # Fallback to direct kwargs
        return resolver.resolve(
            parameter_key=parameter_key,
            jurisdiction=jurisdiction,
            effective_date=effective_date,
            applicability=applicability,
        )
    raise AttributeError("Resolver has no resolve method")
