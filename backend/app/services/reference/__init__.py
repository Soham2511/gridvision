"""Reference Data and Document Knowledge Services."""

from app.services.reference.document_service import DocumentService
from app.services.reference.exceptions import (
    AmbiguousReferenceError,
    DocumentValidationError,
    DownloadSizeExceededError,
    DuplicateDocumentError,
    ExpiredReferenceError,
    ExtractionError,
    MissingReferenceError,
    OutOfJurisdictionError,
    ReferenceInfrastructureError,
    ReferenceNotFoundError,
    ReferenceResolutionError,
    SSRFSecurityError,
    UnapprovedReferenceError,
)
from app.services.reference.extractor import StructureAwareExtractor
from app.services.reference.resolver import (
    ReferenceResolutionContext,
    ReferenceResolver,
    ResolvedReference,
)
from app.services.reference.lifecycle import (
    CandidateLifecycleService,
    ConflictDetectedError,
    InvalidStatusTransitionError,
    ReviewActionRequest,
    ReviewAuthorizationError,
    ReviewStatusEnum,
    ReviewWorkflowService,
)
from app.services.reference.repository import ReferenceRepository
from app.services.reference.schemas import (
    CandidateReferenceCreate,
    CandidateReferenceResponse,
    CandidateReferenceSchema,
    EnergyUnitEnum,
)
from app.services.reference.security import DocumentValidator, SSRFSafeFetcher

__all__ = [
    "DocumentService",
    "SSRFSafeFetcher",
    "DocumentValidator",
    "StructureAwareExtractor",
    "ReferenceResolver",
    "ReferenceResolutionContext",
    "ResolvedReference",
    "ReferenceRepository",
    "ReviewWorkflowService",
    "CandidateLifecycleService",
    "ReviewStatusEnum",
    "CandidateReferenceCreate",
    "CandidateReferenceSchema",
    "CandidateReferenceResponse",
    "ReviewActionRequest",
    "EnergyUnitEnum",
    "InvalidStatusTransitionError",
    "ReviewAuthorizationError",
    "ConflictDetectedError",
    "ReferenceInfrastructureError",
    "ReferenceResolutionError",
    "MissingReferenceError",
    "ReferenceNotFoundError",
    "UnapprovedReferenceError",
    "ExpiredReferenceError",
    "OutOfJurisdictionError",
    "AmbiguousReferenceError",
    "SSRFSecurityError",
    "DocumentValidationError",
    "DownloadSizeExceededError",
    "DuplicateDocumentError",
    "ExtractionError",
]

