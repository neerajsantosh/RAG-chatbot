from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ConfigVersion:
    """A versioned configuration snapshot."""
    version_id: str
    config: dict[str, Any]
    activated_by: str | None = None
    activated_at: str = ""
    is_active: bool = False
    description: str = ""


class ConfigStore:
    """Versioned prompt and retrieval configuration: stage, activate, roll back."""

    def __init__(self) -> None:
        self._versions: list[ConfigVersion] = []
        self._current_version: Optional[ConfigVersion] = None
        self._version_counter: int = 0

    def current(self) -> dict[str, Any]:
        """The active configuration, including its version."""
        if self._current_version is None:
            return {}
        return self._current_version.config

    def stage(self, config: dict[str, Any]) -> str:
        """Store a new version without activating it. Returns the version id."""
        self._version_counter += 1
        version_id = f"v{self._version_counter}"
        version = ConfigVersion(
            version_id=version_id,
            config=config,
            is_active=False,
        )
        self._versions.append(version)
        return version_id

    def activate(self, version_id: str, *, actor: str) -> None:
        """Activate a stored version. Returns the restored version id."""
        # Deactivate current
        if self._current_version is not None:
            self._current_version.is_active = False
        # Activate requested
        for version in self._versions:
            if version.version_id == version_id:
                version.is_active = True
                version.activated_by = actor
                version.activated_at = self._now()
                self._current_version = version
                break
        else:
            raise ValueError(f"Version {version_id} not found")

    def rollback(self, *, actor: str) -> str:
        """Restore the previous active version. Returns the restored version id."""
        if self._current_version is None:
            raise ValueError("No current version to rollback from")

        # Find the previous version (the one before current)
        current_idx = next(
            (i for i, v in enumerate(self._versions) if v.version_id == self._current_version.version_id),
            None,
        )
        if current_idx is not None and current_idx > 0:
            previous_version = self._versions[current_idx - 1]
            return self.activate(version_id=previous_version.version_id, actor=actor)
        else:
            # No previous version, deactivate current
            self._current_version.is_active = False
            self._current_version = None
            return self._current_version.version_id if self._current_version else ""

    def _now(self) -> str:
        import datetime
        return datetime.datetime.utcnow().isoformat() + "Z"