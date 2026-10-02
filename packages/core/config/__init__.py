"""Configuration surface.

Two responsibilities, kept separate on purpose:

* :mod:`core.config.settings` -- *what* the application is configured to do.
* :mod:`core.config.secrets` -- *how* credentials are obtained without them ever
  appearing in a log, a config file or a repository.
"""

from core.config.secrets import (
    EnvSecretStore,
    InMemorySecretStore,
    SecretStore,
    get_secret_store,
    require_secret,
    reset_secret_store,
    set_secret_store,
)
from core.config.settings import (
    AuthMode,
    Environment,
    LogFormat,
    Settings,
    get_settings,
    reset_settings_cache,
)

__all__ = [
    "AuthMode",
    "EnvSecretStore",
    "Environment",
    "InMemorySecretStore",
    "LogFormat",
    "SecretStore",
    "Settings",
    "get_secret_store",
    "get_settings",
    "require_secret",
    "reset_secret_store",
    "reset_settings_cache",
    "set_secret_store",
]
