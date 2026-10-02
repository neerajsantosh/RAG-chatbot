"""ASGI entry point.

``uvicorn api.main:app`` loads the module-level ``app``. Kept as a two-line module so the
import path stays stable while everything interesting lives in :mod:`api.app`, where it can
be constructed with explicit settings.
"""

from __future__ import annotations

from api.app import create_app

app = create_app()
