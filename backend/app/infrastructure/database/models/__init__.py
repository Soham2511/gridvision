"""Database models package."""

from app import _extend_residential_package_path

_extend_residential_package_path(__path__, "infrastructure/database/models")

from app.infrastructure.database.models.reference import (
    ApprovedReferenceModel,
    ApprovedReferenceRecord,
    Base,
    CandidateReferenceModel,
    DocumentArtifactModel,
    DocumentArtifactRecord,
    ReferenceAuditLogModel,
    ReferenceParameterModel,
    SourceDocumentModel,
    SourceDocumentRecord,
    SourceModel,
)
from app.infrastructure.database.models.rag import (
    DocumentChunkModel,
    RAGQueryAuditModel,
)
from app.infrastructure.database.models.complaint import ComplaintModel
from app.infrastructure.database.models.conversation_memory import (
    ConversationMessageModel,
    ConversationSessionModel,
    CustomerMemoryModel,
    ToolExecutionModel,
)
from app.infrastructure.database.models.user import (
    Meter,
    User,
    UserSession,
    user_meters,
)

__all__ = [
    "Base",
    "SourceDocumentModel",
    "SourceModel",
    "SourceDocumentRecord",
    "DocumentArtifactModel",
    "DocumentArtifactRecord",
    "ReferenceParameterModel",
    "CandidateReferenceModel",
    "ApprovedReferenceModel",
    "ApprovedReferenceRecord",
    "ReferenceAuditLogModel",
    "DocumentChunkModel",
    "RAGQueryAuditModel",
    "ComplaintModel",
    "CustomerMemoryModel",
    "ConversationSessionModel",
    "ConversationMessageModel",
    "ToolExecutionModel",
    "User",
    "Meter",
    "UserSession",
    "user_meters",
]
