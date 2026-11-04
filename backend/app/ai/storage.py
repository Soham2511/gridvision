"""Opaque, private local artifact storage with explicit root configuration."""

from __future__ import annotations

import os
import re
import secrets
from pathlib import Path


class PrivateStorageError(RuntimeError):
    pass


class PrivateFileStore:
    _ARTIFACT_ID = re.compile(r"^[a-f0-9]{32}$")

    def __init__(
        self,
        root: str | Path,
        *,
        forbidden_roots: tuple[str | Path, ...] = (),
        max_bytes: int = 25_000_000,
    ) -> None:
        candidate = Path(root).expanduser().absolute()
        if candidate.is_symlink():
            raise ValueError("Private storage root cannot be a symlink.")
        self.root = candidate.resolve()
        self.max_bytes = max(1, int(max_bytes))
        for forbidden in forbidden_roots:
            forbidden_path = Path(forbidden).expanduser().resolve()
            if (
                self.root == forbidden_path
                or forbidden_path in self.root.parents
                or self.root in forbidden_path.parents
            ):
                raise ValueError("Private storage cannot be inside a protected data or static directory.")

    def initialize(self) -> None:
        try:
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
            if self.root.is_symlink():
                raise PrivateStorageError("Private storage root cannot be a symlink.")
            if os.name == "posix":
                os.chmod(self.root, 0o700)
        except OSError as exc:
            raise PrivateStorageError("Unable to initialize private artifact storage.") from exc

    def store(self, content: bytes) -> str:
        if not isinstance(content, bytes):
            raise TypeError("Private artifacts must be bytes.")
        if len(content) > self.max_bytes:
            raise PrivateStorageError("Artifact exceeds the configured size limit.")
        artifact_id = secrets.token_hex(16)
        target = self.root / artifact_id
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(target, flags, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
        except OSError as exc:
            raise PrivateStorageError("Unable to store the private artifact.") from exc
        return artifact_id

    def read(self, artifact_id: str) -> bytes:
        if not self._ARTIFACT_ID.fullmatch(artifact_id):
            raise PrivateStorageError("Invalid artifact identifier.")
        target = self.root / artifact_id
        try:
            if target.is_symlink() or target.resolve().parent != self.root or not target.is_file():
                raise PrivateStorageError("Artifact path is not a private regular file.")
            return target.read_bytes()
        except OSError as exc:
            raise PrivateStorageError("Private artifact is unavailable.") from exc

