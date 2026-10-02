"""Route modules.

Each module owns one router. Phase 1 has only health; phase 3 adds ``question`` and phase 4
``admin``. Keeping them separate rather than in one file is what makes the eventual
permission model reviewable -- the admin router is the one that needs a role check on every
route, and it should be possible to confirm that by reading one file.
"""

from api.routes import health

__all__ = ["health"]
