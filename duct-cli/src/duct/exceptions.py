"""Exception hierarchy for duct."""


class DuctError(Exception):
    """Base exception for all duct errors."""


class ConfigError(DuctError):
    """Configuration loading or validation error."""


class AuthError(DuctError):
    """Missing or invalid authentication credentials."""


class SyncError(DuctError):
    """Error during data sync from an external source."""


class WorkspaceError(DuctError):
    """Error related to workspace operations."""
