"""Exception hierarchy for tutti."""


class TuttiError(Exception):
    """Base exception for all tutti errors."""


class ConfigError(TuttiError):
    """Configuration loading or validation error."""


class AuthError(TuttiError):
    """Missing or invalid authentication credentials."""


class SyncError(TuttiError):
    """Error during data sync from an external source."""


class WorkspaceError(TuttiError):
    """Error related to workspace operations."""
