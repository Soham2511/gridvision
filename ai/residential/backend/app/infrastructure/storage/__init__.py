"""Storage infrastructure package for GridVision."""

from app.infrastructure.storage.base import BaseDocumentStorage
from app.infrastructure.storage.local import LocalFileSystemStorageAdapter

__all__ = ["BaseDocumentStorage", "LocalFileSystemStorageAdapter"]
