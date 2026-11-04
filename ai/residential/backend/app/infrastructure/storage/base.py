"""Base Document Storage Abstraction for GridVision Reference Data Infrastructure.

Defines the abstract interface BaseDocumentStorage for persisting and retrieving
original source documents and structure-aware extracted artifacts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseDocumentStorage(ABC):
    """Abstract interface for document knowledge storage."""

    @abstractmethod
    def save_original(self, source_id: str, filename: str, content: bytes) -> str:
        """Store original document intact, returning the relative storage path/key.

        Args:
            source_id: Unique identifier for the document source.
            filename: Original name of the document file.
            content: Raw byte content of the document.

        Returns:
            Relative storage path or key where the original file is persisted.
        """
        pass

    @abstractmethod
    def get_original(self, file_path: str) -> bytes:
        """Retrieve original document content as bytes.

        Args:
            file_path: Relative storage path or key returned by save_original.

        Returns:
            Raw byte content of the stored original document.
        """
        pass

    @abstractmethod
    def save_extracted(self, source_id: str, structure: dict) -> str:
        """Store extracted structural representation (JSON), returning storage path/key.

        Args:
            source_id: Unique identifier for the document source.
            structure: Extracted structure dictionary conforming to interface contract.

        Returns:
            Relative storage path or key where the extracted representation is persisted.
        """
        pass

    @abstractmethod
    def get_extracted(self, file_path: str) -> dict:
        """Retrieve extracted structural representation as a dictionary.

        Args:
            file_path: Relative storage path or key returned by save_extracted.

        Returns:
            Extracted document structure dictionary.
        """
        pass

    @abstractmethod
    def delete(self, file_path: str) -> bool:
        """Delete document artifact by storage path.

        Args:
            file_path: Relative storage path or key to delete.

        Returns:
            True if file existed and was deleted, False if file did not exist.
        """
        pass

    @abstractmethod
    def exists(self, file_path: str) -> bool:
        """Check whether a document artifact exists at storage path.

        Args:
            file_path: Relative storage path or key to check.

        Returns:
            True if file exists, False otherwise.
        """
        pass
