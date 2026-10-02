"""HTTP API.

Phase 1 exposes health, readiness and version. The question endpoint arrives in phase 3,
once there is retrieval to answer with -- but the seams it needs (principal binding, error
mapping, span recording, redaction) are all in place now, because retrofitting them after
the first endpoints exist is how a codebase ends up with two error-handling conventions.
"""

from api.app import API_TITLE, create_app

__all__ = ["API_TITLE", "create_app"]
