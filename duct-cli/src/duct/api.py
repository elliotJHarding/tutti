"""Public API surface for duct library consumers."""

from duct.config import (
    WorkspaceConfig,
    find_workspace_root,
    gh_token,
    jira_email,
    jira_token,
    load_config,
    save_config,
)
from duct.exceptions import AuthError, ConfigError, SyncError, DuctError, WorkspaceError
from duct.models import Comment, PRComment, PullRequest, Reviewer, SyncResult, Ticket
from duct.workspace import (
    archive_ticket,
    ensure_epic_link,
    ensure_ticket_dir,
    enumerate_ticket_dirs,
    orchestrator_dir,
    resolve_ticket_dir,
    restore_ticket,
    slug,
    ticket_dir_name,
)

__all__ = [
    "AuthError",
    "Comment",
    "ConfigError",
    "PRComment",
    "PullRequest",
    "Reviewer",
    "SyncError",
    "SyncResult",
    "Ticket",
    "DuctError",
    "WorkspaceConfig",
    "WorkspaceError",
    "archive_ticket",
    "ensure_epic_link",
    "ensure_ticket_dir",
    "enumerate_ticket_dirs",
    "find_workspace_root",
    "gh_token",
    "jira_email",
    "jira_token",
    "load_config",
    "orchestrator_dir",
    "resolve_ticket_dir",
    "restore_ticket",
    "save_config",
    "slug",
    "ticket_dir_name",
]
