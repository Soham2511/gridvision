"""Local File System Storage Adapter for Document Knowledge Infrastructure.

Implements BaseDocumentStorage using the local filesystem with path traversal protection,
directory structure enforcement, and strict separation between original documents and
extracted JSON representations.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict

from app.infrastructure.storage.base import BaseDocumentStorage

# Windows reserved DOS device names (case-insensitive, with or without file extension)
WINDOWS_RESERVED_DEVICE_NAMES: frozenset[str] = frozenset({
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
})


class LocalFileSystemStorageAdapter(BaseDocumentStorage):
    """Local filesystem adapter implementing BaseDocumentStorage.

    Stores original documents in `<base_dir>/original/<source_id>/<filename>` and
    extracted structural representations in `<base_dir>/extracted/<source_id>/extracted_structure.json`.
    """

    def __init__(self, base_dir: str | Path = "data/documents") -> None:
        """Initialize the storage adapter.

        Args:
            base_dir: Root directory for document storage. Defaults to 'data/documents'.
        """
        self.base_dir = Path(base_dir).resolve()
        self.original_dir = (self.base_dir / "original").resolve()
        self.extracted_dir = (self.base_dir / "extracted").resolve()

        # Ensure root subdirectories exist
        self.original_dir.mkdir(parents=True, exist_ok=True)
        self.extracted_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_identifier(self, identifier: str, param_name: str = "identifier") -> str:
        """Sanitize a path segment (source_id or filename) against traversal.

        Args:
            identifier: The string to sanitize.
            param_name: Parameter name for error messages.

        Returns:
            Sanitized identifier string.

        Raises:
            ValueError: If the identifier contains path traversal characters, illegal symbols,
                        Alternate Data Streams, or Windows DOS device names.
        """
        if not identifier or not isinstance(identifier, str):
            raise ValueError(f"{param_name} must be a non-empty string.")

        if "\x00" in identifier:
            raise ValueError(f"{param_name} contains forbidden null byte.")

        # Reject path separators and traversal tokens
        if "/" in identifier or "\\" in identifier or ".." in identifier:
            raise ValueError(
                f"Path traversal detected: {param_name} '{identifier}' contains invalid path elements."
            )

        # Explicitly reject colons (NTFS Alternate Data Streams / drive letters)
        if ":" in identifier:
            raise ValueError(
                f"Path traversal detected: {param_name} '{identifier}' contains forbidden colon character."
            )

        # Restrict characters strictly to alphanumeric, hyphen, underscore, period
        if not re.match(r"^[a-zA-Z0-9_.-]+$", identifier):
            raise ValueError(
                f"Invalid {param_name} '{identifier}': only alphanumeric, hyphen, underscore, and period characters are permitted."
            )

        # Disallow purely dot segments
        if identifier in (".", ".."):
            raise ValueError(f"{param_name} '{identifier}' is an invalid directory segment.")

        # Explicitly reject Windows DOS device names (CON, PRN, AUX, NUL, COM1-9, LPT1-9)
        stem = identifier.split(".")[0].upper()
        if stem in WINDOWS_RESERVED_DEVICE_NAMES:
            raise ValueError(
                f"Invalid {param_name} '{identifier}': Windows DOS device names are not permitted."
            )

        return identifier

    def _resolve_safe_path(self, file_path: str | Path) -> Path:
        """Resolve and validate a file path against path traversal.

        Ensures that the resolved path resides strictly inside `self.base_dir`.

        Args:
            file_path: Relative or absolute path to check.

        Returns:
            Resolved Path within base_dir.

        Raises:
            ValueError: If path traversal outside base_dir is detected.
        """
        if not file_path:
            raise ValueError("File path cannot be empty.")

        path_str = str(file_path)
        if "\x00" in path_str:
            raise ValueError("Path traversal detected: path contains null byte.")

        # Reject Alternate Data Streams (colon not part of a Windows drive letter)
        if ":" in path_str:
            is_drive_letter = (
                len(path_str) >= 2
                and path_str[1] == ":"
                and path_str[0].isalpha()
                and path_str.count(":") == 1
            )
            if not is_drive_letter:
                raise ValueError(
                    f"Path traversal detected: '{file_path}' contains forbidden colon or Alternate Data Stream."
                )

        p = Path(path_str)
        if p.is_absolute():
            resolved = p.resolve()
        else:
            resolved = (self.base_dir / p).resolve()

        # Enforce boundary: resolved path MUST be inside self.base_dir
        try:
            resolved.relative_to(self.base_dir)
        except ValueError:
            raise ValueError(
                f"Path traversal detected: '{file_path}' resolves outside base directory '{self.base_dir}'."
            )

        return resolved

    def save_original(self, source_id: str, filename: str, content: bytes) -> str:
        """Store original document intact.

        Args:
            source_id: Unique identifier for the document source.
            filename: Original filename.
            content: Raw byte content.

        Returns:
            Relative storage path e.g. 'original/<source_id>/<filename>'.
        """
        if not isinstance(content, (bytes, bytearray)):
            raise TypeError("Document content must be bytes.")

        clean_source_id = self._sanitize_identifier(source_id, "source_id")
        clean_filename = self._sanitize_identifier(filename, "filename")

        target_dir = self.original_dir / clean_source_id
        target_dir.mkdir(parents=True, exist_ok=True)

        target_file = target_dir / clean_filename
        # Extra traversal safety check
        safe_path = self._resolve_safe_path(target_file)
        safe_path.write_bytes(content)

        return f"original/{clean_source_id}/{clean_filename}"

    def get_original(self, file_path: str) -> bytes:
        """Retrieve original document bytes.

        Args:
            file_path: Storage path returned by save_original or relative to base_dir.

        Returns:
            Raw document bytes.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If path traversal is detected.
        """
        safe_path = self._resolve_safe_path(file_path)
        if not safe_path.exists() or not safe_path.is_file():
            raise FileNotFoundError(f"Original document not found: {file_path}")

        return safe_path.read_bytes()

    def save_extracted(self, source_id: str, structure: dict) -> str:
        """Store extracted structural representation (JSON).

        Args:
            source_id: Unique identifier for the document source.
            structure: Extracted structure dictionary.

        Returns:
            Relative storage path e.g. 'extracted/<source_id>/extracted_structure.json'.
        """
        if not isinstance(structure, dict):
            raise TypeError("Extracted structure must be a dictionary.")

        clean_source_id = self._sanitize_identifier(source_id, "source_id")
        target_dir = self.extracted_dir / clean_source_id
        target_dir.mkdir(parents=True, exist_ok=True)

        target_file = target_dir / "extracted_structure.json"
        safe_path = self._resolve_safe_path(target_file)

        serialized = json.dumps(structure, indent=2, ensure_ascii=False)
        safe_path.write_text(serialized, encoding="utf-8")

        return f"extracted/{clean_source_id}/extracted_structure.json"

    def get_extracted(self, file_path: str) -> dict:
        """Retrieve extracted structural representation.

        Args:
            file_path: Storage path returned by save_extracted or relative to base_dir.

        Returns:
            Extracted document structure dictionary.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If path traversal is detected or JSON is invalid.
        """
        safe_path = self._resolve_safe_path(file_path)
        if not safe_path.exists() or not safe_path.is_file():
            raise FileNotFoundError(f"Extracted document structure not found: {file_path}")

        content = safe_path.read_text(encoding="utf-8")
        return json.loads(content)

    def exists(self, file_path: str) -> bool:
        """Check whether a file exists at the given path safely.

        Args:
            file_path: Relative or absolute path to check.

        Returns:
            True if file exists and is inside base_dir, False otherwise.

        Raises:
            ValueError: If path traversal attempt is detected.
        """
        safe_path = self._resolve_safe_path(file_path)
        return safe_path.exists() and safe_path.is_file()

    def delete(self, file_path: str) -> bool:
        """Delete document artifact safely.

        Args:
            file_path: Storage path to delete.

        Returns:
            True if file was deleted, False if file did not exist.

        Raises:
            ValueError: If path traversal is detected.
        """
        safe_path = self._resolve_safe_path(file_path)
        if safe_path.exists() and safe_path.is_file():
            safe_path.unlink()
            return True
        return False
