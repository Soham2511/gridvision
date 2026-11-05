"""Source Registry and Document Ingestion Service for GridVision Reference Infrastructure.

Orchestrates document acquisition (via URL or file upload), SSRF security validation,
magic byte verification, SHA-256 deduplication, storage of original artifacts, and
structure-aware extraction.
"""

from __future__ import annotations

import datetime
import logging
import re
import threading
import uuid
from typing import Any, Dict, List, Optional

from app.infrastructure.storage.base import BaseDocumentStorage
from app.infrastructure.storage.local import LocalFileSystemStorageAdapter
from app.services.reference.exceptions import (
    DocumentValidationError,
    DuplicateDocumentError,
    SSRFSecurityError,
)
from app.services.reference.extractor import StructureAwareExtractor
from app.services.reference.security import DocumentValidator, SSRFSafeFetcher

logger = logging.getLogger(__name__)


class DocumentService:
    """Manages document acquisition, validation, deduplication, storage, and extraction."""

    def __init__(
        self,
        storage: Optional[BaseDocumentStorage] = None,
        fetcher: Optional[SSRFSafeFetcher] = None,
        validator: Optional[DocumentValidator] = None,
        extractor: Optional[StructureAwareExtractor] = None,
    ) -> None:
        self.storage: BaseDocumentStorage = storage or LocalFileSystemStorageAdapter()
        self.fetcher: SSRFSafeFetcher = fetcher or SSRFSafeFetcher()
        self.validator: DocumentValidator = validator or DocumentValidator()
        self.extractor: StructureAwareExtractor = extractor or StructureAwareExtractor()

        # In-memory source registry for M1 metadata management (persisted to M2 DB later)
        self._sources: Dict[str, Dict[str, Any]] = {}
        # Mapping from SHA-256 checksum to source_id for duplicate detection
        self._checksum_index: Dict[str, str] = {}
        # Re-entrant lock guarding in-memory registries and ingestion critical sections
        self._lock = threading.RLock()

    def _generate_source_id(self, source_meta: Dict[str, Any]) -> str:
        """Generate a clean, sanitized source identifier."""
        provided = source_meta.get("source_id")
        if provided:
            # Sanitize to alphanumeric, hyphen, underscore
            clean = re.sub(r"[^A-Za-z0-9_\-]", "_", str(provided).strip())
            if clean:
                return clean

        org = re.sub(r"[^A-Za-z0-9]", "", str(source_meta.get("issuing_organization", "SRC")).upper()) or "SRC"
        doc_id = re.sub(r"[^A-Za-z0-9]", "_", str(source_meta.get("document_identifier", "")))
        short_uuid = uuid.uuid4().hex[:8]

        if doc_id:
            return f"{org}_{doc_id[:32]}_{short_uuid}"
        return f"{org}_{short_uuid}"

    def find_by_checksum(self, checksum: str) -> Optional[Dict[str, Any]]:
        """Find existing source record by SHA-256 checksum."""
        with self._lock:
            source_id = self._checksum_index.get(checksum.lower().strip())
            if source_id and source_id in self._sources:
                return self._sources[source_id]
            return None

    def get_source(self, source_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve source document metadata record by ID."""
        with self._lock:
            return self._sources.get(source_id)

    def list_sources(self) -> List[Dict[str, Any]]:
        """List all registered document source records."""
        with self._lock:
            return list(self._sources.values())

    def get_extracted_structure(self, source_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve the extracted structural AST for a source document."""
        source = self.get_source(source_id)
        if not source:
            return None
        extracted_path = source.get("extracted_file_path")
        if not extracted_path:
            return None
        return self.storage.get_extracted(extracted_path)

    def get_original_bytes(self, source_id: str) -> Optional[bytes]:
        """Retrieve original document bytes for a source document."""
        source = self.get_source(source_id)
        if not source:
            return None
        original_path = source.get("original_file_path")
        if not original_path:
            return None
        return self.storage.get_original(original_path)

    def acquire_from_file(
        self,
        source_meta: Dict[str, Any],
        filename: str,
        file_bytes: bytes,
        raise_on_duplicate: bool = True,
    ) -> Dict[str, Any]:
        """Ingest a document from uploaded file bytes.

        Args:
            source_meta: Metadata dictionary (issuing_org, identifier, dates, licensing, etc.).
            filename: Original filename.
            file_bytes: Raw content bytes.
            raise_on_duplicate: If True, raises DuplicateDocumentError if checksum matches an existing source.

        Returns:
            Registered source record with artifact storage paths and extraction summary.

        Raises:
            DocumentValidationError: If file violates signature or size constraints.
            DuplicateDocumentError: If duplicate document is detected and raise_on_duplicate is True.
        """
        # 1. Validate content and detect format & checksum
        val_res = self.validator.validate(file_bytes, filename=filename)
        checksum = val_res["checksum_sha256"]
        detected_format = val_res["format"]
        mime_type = val_res["mime_type"]
        file_size = val_res["file_size_bytes"]

        with self._lock:
            # 2. Duplicate Detection
            existing_source = self.find_by_checksum(checksum)
            if existing_source is not None:
                if raise_on_duplicate:
                    raise DuplicateDocumentError(
                        f"Duplicate document detected: Content with SHA-256 '{checksum}' already ingested as source '{existing_source['source_id']}'.",
                        existing_source_id=existing_source["source_id"],
                        checksum=checksum,
                    )
                logger.info("Duplicate document detected; returning existing record %s", existing_source["source_id"])
                return existing_source

            # 3. Determine source_id and clean filename
            source_id = self._generate_source_id(source_meta)
            clean_filename = re.sub(r"[^A-Za-z0-9_\-\.]", "_", filename).strip() or f"document.{detected_format}"

            # 4. Save original document to storage
            original_path = self.storage.save_original(source_id, clean_filename, file_bytes)
            extracted_path: Optional[str] = None

            try:
                # 5. Perform structure-aware extraction
                doc_ident = source_meta.get("document_identifier", clean_filename)
                extracted_data = self.extractor.extract(
                    content=file_bytes,
                    doc_format=detected_format,
                    source_id=source_id,
                    document_identifier=doc_ident,
                )

                # 6. Save extracted structure to storage
                extracted_path = self.storage.save_extracted(source_id, extracted_data)

                # 7. Build and register complete source record
                now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                record: Dict[str, Any] = {
                    "source_id": source_id,
                    "issuing_organization": source_meta.get("issuing_organization", "Unknown"),
                    "official_url": source_meta.get("official_url", ""),
                    "document_identifier": doc_ident,
                    "edition_revision": source_meta.get("edition_revision", "1.0"),
                    "publication_date": source_meta.get("publication_date", now_iso[:10]),
                    "retrieval_date": source_meta.get("retrieval_date", now_iso),
                    "content_checksum_sha256": checksum,
                    "licensing": source_meta.get("licensing", "Public Domain / Regulatory"),
                    "status": source_meta.get("status", "active"),
                    "original_file_path": original_path,
                    "extracted_file_path": extracted_path,
                    "file_size_bytes": file_size,
                    "mime_type": mime_type,
                    "format": detected_format,
                    "extraction_summary": {
                        "page_count": len(extracted_data.get("pages", [])),
                        "section_count": len(extracted_data.get("sections", [])),
                        "table_count": len(extracted_data.get("tables", [])),
                        "footnote_count": len(extracted_data.get("footnotes", [])),
                        "provenance_count": len(extracted_data.get("provenance_map", {})),
                    },
                }

                # Ghost checksum fix: remove old checksum index entry if updating existing source with changed content
                if source_id in self._sources:
                    old_checksum = self._sources[source_id].get("content_checksum_sha256")
                    if old_checksum and old_checksum != checksum:
                        self._checksum_index.pop(old_checksum, None)
                        logger.info(
                            "Purged stale checksum '%s' from index for updated source '%s'",
                            old_checksum,
                            source_id,
                        )

                self._sources[source_id] = record
                self._checksum_index[checksum] = source_id
                logger.info("Successfully ingested document '%s' (source_id: %s)", doc_ident, source_id)
                return record
            except Exception:
                logger.warning(
                    "Ingestion pipeline failed for source '%s'; rolling back stored artifacts",
                    source_id,
                )
                try:
                    self.storage.delete(original_path)
                except Exception as del_exc:
                    logger.error("Failed to delete original file during rollback: %s", del_exc)
                if extracted_path:
                    try:
                        self.storage.delete(extracted_path)
                    except Exception as del_exc:
                        logger.error("Failed to delete extracted file during rollback: %s", del_exc)
                raise

    def acquire_from_url(
        self,
        source_meta: Dict[str, Any],
        url: str,
        raise_on_duplicate: bool = True,
    ) -> Dict[str, Any]:
        """Fetch remote document via SSRF-safe fetcher and ingest.

        Args:
            source_meta: Metadata dictionary.
            url: Approved official remote URL.
            raise_on_duplicate: Whether to raise if identical content checksum is already present.

        Returns:
            Registered source record.

        Raises:
            SSRFSecurityError: If URL fails SSRF safety checks.
            DocumentValidationError: If content violates validation rules.
            DuplicateDocumentError: If duplicate checksum is detected.
        """
        # Fetch with SSRF protection
        content_bytes, headers = self.fetcher.fetch(url)

        # Derive filename from URL path if possible
        import urllib.parse
        parsed = urllib.parse.urlparse(url)
        path_filename = parsed.path.split("/")[-1]
        filename = path_filename or "remote_document.pdf"

        meta_with_url = dict(source_meta)
        meta_with_url["official_url"] = url

        try:
            return self.acquire_from_file(
                source_meta=meta_with_url,
                filename=filename,
                file_bytes=content_bytes,
                raise_on_duplicate=raise_on_duplicate,
            )
        except Exception:
            logger.error("Acquisition from URL failed for '%s'", url)
            raise

    def delete_source(self, source_id: str) -> bool:
        """Delete document artifacts and deregister source."""
        with self._lock:
            source = self.get_source(source_id)
            if not source:
                return False

            orig_path = source.get("original_file_path")
            ext_path = source.get("extracted_file_path")

            if orig_path:
                self.storage.delete(orig_path)
            if ext_path:
                self.storage.delete(ext_path)

            checksum = source.get("content_checksum_sha256")
            if checksum and checksum in self._checksum_index:
                del self._checksum_index[checksum]

            del self._sources[source_id]
            return True
