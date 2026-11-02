"""Store original uploads outside the database."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from app.core.config import Settings
from app.core.errors import AppError
from app.core.logging import logger


class FileStore:
    """Write and delete upload bytes under the configured directory."""

    def __init__(self, settings: Settings) -> None:
        self._root = Path(settings.upload_dir).resolve()

    def save(self, user_id: UUID, document_id: UUID, data: bytes) -> Path:
        """Persist bytes at a path that does not include the original filename."""
        directory = self._root / str(user_id)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / str(document_id)
        path.write_bytes(data)
        return path

    def read(self, storage_path: str) -> bytes:
        """Read a previously stored file, rejecting paths outside the root."""
        path = self._resolve(storage_path)
        return path.read_bytes()

    def delete(self, storage_path: str) -> None:
        """Remove a stored file if it is still present."""
        if not storage_path:
            return
        try:
            path = self._resolve(storage_path)
        except AppError:
            logger.warning("refused to delete a path outside the upload directory")
            return
        path.unlink(missing_ok=True)

    def _resolve(self, storage_path: str) -> Path:
        path = Path(storage_path).resolve()
        if self._root != path and self._root not in path.parents:
            raise AppError("Invalid document storage path", code="invalid_storage", status_code=500)
        return path
