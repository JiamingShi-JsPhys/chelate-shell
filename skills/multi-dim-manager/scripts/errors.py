"""Domain-specific error types for the experiment manager."""


class ManagerError(Exception):
    """Base class for all expected, user-facing failures."""


class ConfigError(ManagerError):
    """Raised when a config file is missing, malformed, or unsupported."""


class PluginError(ManagerError):
    """Raised when the user compute plugin cannot be launched or misbehaves."""


class RollbackError(ManagerError):
    """Raised when a requested rollback cannot be performed."""
