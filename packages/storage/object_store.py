from __future__ import annotations


class ObjectStore:
    """Store raw and parsed bytes, versioned and immutable."""

    async def store(self, key: str, data: bytes) -> None:
        """Store raw or parsed bytes."""
        raise NotImplementedError

    async def retrieve(self, key: str) -> bytes:
        """Retrieve stored bytes."""
        raise NotImplementedError