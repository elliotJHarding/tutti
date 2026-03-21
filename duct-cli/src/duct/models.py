"""Domain models for duct."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Comment:
    """A Jira issue comment."""

    author: str
    created: str  # ISO 8601
    body: str


@dataclass(frozen=True)
class Ticket:
    """A Jira issue."""

    key: str
    summary: str
    status: str
    category: str
    priority: str
    issue_type: str
    assignee: str
    url: str
    description: str = ""
    epic_key: str | None = None
    sprint: str | None = None
    fix_versions: list[str] = field(default_factory=list)
    components: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    transitions: list[str] = field(default_factory=list)
    comments: list[Comment] = field(default_factory=list)
    linked_issues: list[str] = field(default_factory=list)
    subtasks: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Reviewer:
    """A pull request reviewer."""

    login: str
    state: str


@dataclass(frozen=True)
class PRComment:
    """A pull request comment."""

    author: str
    created_at: str  # ISO 8601
    body: str
    path: str | None = None
    line: int | None = None
    diff_hunk: str | None = None


@dataclass(frozen=True)
class ReviewThread:
    """A pull request review thread (inline code comment thread)."""

    is_resolved: bool
    comments: list[PRComment] = field(default_factory=list)


@dataclass(frozen=True)
class PullRequest:
    """A GitHub pull request."""

    number: int
    title: str
    repo: str
    state: str  # "open" | "closed" | "merged"
    author: str
    is_draft: bool
    review_status: str
    ci_status: str
    url: str
    created_at: str  # ISO 8601
    updated_at: str  # ISO 8601
    branch: str = ""
    base_branch: str = ""
    body: str = ""
    reviewers: list[Reviewer] = field(default_factory=list)
    comments: list[PRComment] = field(default_factory=list)
    review_threads: list[ReviewThread] = field(default_factory=list)


@dataclass
class RepoEntry:
    """A git repo tracked in a ticket workspace."""

    name: str
    origin: str
    branch: str
    base_branch: str = "main"


@dataclass
class Workspace:
    """Metadata for a ticket workspace, stored in .duct/workspace.json."""

    ticket_key: str
    created_at: str
    branch_type: str = "feature"
    default_branch: str = ""
    priority: int = 0
    repos: list[RepoEntry] = field(default_factory=list)
    path: str | None = None  # runtime only, not serialized


@dataclass(frozen=True)
class SyncResult:
    """Result of a sync operation."""

    source: str
    tickets_synced: int
    duration_seconds: float
    errors: list[str] = field(default_factory=list)
