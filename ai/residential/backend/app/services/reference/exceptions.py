"""Exceptions for the Reference Data and Document Knowledge Infrastructure."""

from __future__ import annotations


class ReferenceInfrastructureError(Exception):
    """Base exception for all reference and document infrastructure errors."""
    pass


class SSRFSecurityError(ReferenceInfrastructureError, ValueError):
    """Raised when an outbound URL fetch violates SSRF or DNS security policies."""
    pass


class DocumentValidationError(ReferenceInfrastructureError, ValueError):
    """Raised when a document violates file type, signature, or size constraints."""
    pass


class DownloadSizeExceededError(DocumentValidationError):
    """Raised when a downloaded or uploaded file exceeds the configured maximum byte limit."""
    pass


class DuplicateDocumentError(ReferenceInfrastructureError, ValueError):
    """Raised when attempting to ingest a document whose content SHA-256 is already registered."""
    def __init__(self, message: str, existing_source_id: str | None = None, checksum: str | None = None) -> None:
        super().__init__(message)
        self.existing_source_id = existing_source_id
        self.checksum = checksum


class ExtractionError(ReferenceInfrastructureError, ValueError):
    """Raised when structural extraction of a document fails or encounters malformed content."""
    pass


# Resolver Exception Hierarchy
class ReferenceResolutionError(ReferenceInfrastructureError):
    """Base exception for deterministic reference resolution failures."""
    pass


class MissingReferenceError(ReferenceResolutionError):
    """Raised when category + identifier is not found in the reference repository."""

    def __init__(
        self,
        message: str | None = None,
        parameter_key: str | None = None,
        jurisdiction: str | None = None,
    ) -> None:
        if not message:
            message = f"Reference not found: {parameter_key} in {jurisdiction}"
        super().__init__(message)
        self.parameter_key = parameter_key
        self.jurisdiction = jurisdiction


ReferenceNotFoundError = MissingReferenceError


class UnapprovedReferenceError(ReferenceResolutionError):
    """Raised when matching reference exists but has not been approved (draft/pending_review/rejected)."""

    def __init__(
        self,
        message: str | None = None,
        parameter_key: str | None = None,
        status: str | None = None,
    ) -> None:
        if not message:
            message = f"Candidate reference for '{parameter_key}' is in status '{status or 'draft'}'"
        super().__init__(message)
        self.parameter_key = parameter_key
        self.status = status


class ExpiredReferenceError(ReferenceResolutionError):
    """Raised when matching reference exists but effective_date is outside [effective_from, effective_to]."""

    def __init__(
        self,
        message: str | None = None,
        parameter_key: str | None = None,
        effective_from: any = None,
        effective_to: any = None,
        query_date: any = None,
    ) -> None:
        if not message:
            message = f"Reference for '{parameter_key}' is expired (effective_to: {effective_to}, queried: {query_date})"
        super().__init__(message)
        self.parameter_key = parameter_key
        self.effective_from = effective_from
        self.effective_to = effective_to
        self.query_date = query_date


class OutOfJurisdictionError(ReferenceResolutionError):
    """Raised when matching reference exists but cannot satisfy requested jurisdiction or DISCOM."""

    def __init__(
        self,
        message: str | None = None,
        parameter_key: str | None = None,
        jurisdiction: str | None = None,
        region: str | None = None,
    ) -> None:
        if not message:
            message = f"No reference available for jurisdiction '{jurisdiction}' (region: '{region}')"
        super().__init__(message)
        self.parameter_key = parameter_key
        self.jurisdiction = jurisdiction
        self.region = region


class AmbiguousReferenceError(ReferenceResolutionError):
    """Raised when multiple conflicting approved records match with equal precedence without a deterministic tiebreaker."""

    def __init__(
        self,
        message: str | None = None,
        parameter_key: str | None = None,
        candidates: any = None,
    ) -> None:
        if not message:
            message = f"Ambiguous match: multiple records with equal precedence for '{parameter_key}'"
        super().__init__(message)
        self.parameter_key = parameter_key
        self.candidates = candidates


# Backward compatibility alias
InvalidDocumentError = DocumentValidationError

