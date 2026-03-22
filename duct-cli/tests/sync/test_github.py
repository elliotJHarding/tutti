"""Tests for the GitHub sync source."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from duct.exceptions import AuthError, SyncError
from duct.models import PRComment, PullRequest, ReviewThread, Reviewer
from duct.sync.github import _GRAPHQL_URL, GitHubSync

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture
def graphql_response() -> dict:
    return json.loads((FIXTURES / "github_graphql_response.json").read_text())


def _batched_response(single_search_data: dict, count: int = 3) -> dict:
    """Convert a single-search response into a batched aliased response.

    The batched GraphQL query uses aliases s0, s1, ... instead of a single 'search' key.
    """
    search = single_search_data["data"]["search"]
    return {"data": {f"s{i}": search for i in range(count)}}


@pytest.fixture
def gh() -> GitHubSync:
    return GitHubSync(token="fake-token", github_username="alice")


def _make_ticket_dir(workspace: Path, key: str, slug: str) -> Path:
    """Helper to create a ticket directory with an orchestrator subdirectory."""
    d = workspace / f"{key}-{slug}"
    d.mkdir(parents=True)
    (d / "orchestrator").mkdir()
    return d


# ---------------------------------------------------------------------------
# Construction / auth validation
# ---------------------------------------------------------------------------


class TestGitHubSyncInit:
    def test_missing_token_raises(self):
        with pytest.raises(AuthError, match="GH_TOKEN"):
            GitHubSync(token="")

    def test_valid_construction(self, gh: GitHubSync):
        assert gh.name == "github"

    def test_username_optional(self):
        sync = GitHubSync(token="tok")
        assert sync._username is None


# ---------------------------------------------------------------------------
# _parse_pr_node
# ---------------------------------------------------------------------------


class TestParsePrNode:
    def test_open_pr(self, gh: GitHubSync, graphql_response: dict):
        node = graphql_response["data"]["search"]["nodes"][0]
        pr = gh._parse_pr_node(node)

        assert pr.number == 42
        assert pr.title == "ERSC-1278: Fix authentication middleware"
        assert pr.repo == "acme/backend"
        assert pr.state == "open"
        assert pr.author == "alice"
        assert pr.is_draft is False
        assert pr.url == "https://github.com/acme/backend/pull/42"
        assert pr.created_at == "2026-03-10T10:00:00Z"
        assert pr.updated_at == "2026-03-15T14:30:00Z"
        assert pr.branch == "feature/ERSC-1278-fix-auth"
        assert pr.base_branch == "main"
        assert pr.body == "Fixes the authentication token expiry bug."
        assert pr.ci_status == "passing"
        assert pr.review_status == "APPROVED"

    def test_merged_pr(self, gh: GitHubSync, graphql_response: dict):
        node = graphql_response["data"]["search"]["nodes"][1]
        pr = gh._parse_pr_node(node)

        assert pr.state == "merged"
        assert pr.number == 99
        assert pr.review_status == "APPROVED"
        assert pr.ci_status == "passing"

    def test_draft_pr(self, gh: GitHubSync, graphql_response: dict):
        node = graphql_response["data"]["search"]["nodes"][2]
        pr = gh._parse_pr_node(node)

        assert pr.is_draft is True
        assert pr.review_status == "pending"
        assert pr.ci_status == "unknown"

    def test_reviewers_extracted(self, gh: GitHubSync, graphql_response: dict):
        node = graphql_response["data"]["search"]["nodes"][0]
        pr = gh._parse_pr_node(node)

        assert len(pr.reviewers) == 1
        assert pr.reviewers[0].login == "bob"
        # Last review state wins
        assert pr.reviewers[0].state == "APPROVED"

    def test_general_comments_extracted(self, gh: GitHubSync, graphql_response: dict):
        node = graphql_response["data"]["search"]["nodes"][0]
        pr = gh._parse_pr_node(node)

        # Only PR-level comments (not review thread comments)
        assert len(pr.comments) == 1
        assert pr.comments[0].author == "charlie"
        assert "Looks good" in pr.comments[0].body
        assert pr.comments[0].path is None

    def test_review_threads_extracted(self, gh: GitHubSync, graphql_response: dict):
        node = graphql_response["data"]["search"]["nodes"][0]
        pr = gh._parse_pr_node(node)

        assert len(pr.review_threads) == 1
        thread = pr.review_threads[0]
        assert thread.is_resolved is False
        assert len(thread.comments) == 1
        c = thread.comments[0]
        assert c.author == "bob"
        assert c.path == "src/auth/middleware.py"
        assert c.line == 45
        assert c.diff_hunk is not None
        assert "timeout" in c.diff_hunk


# ---------------------------------------------------------------------------
# _derive_review_status
# ---------------------------------------------------------------------------


class TestDeriveReviewStatus:
    def test_no_reviews(self, gh: GitHubSync):
        assert gh._derive_review_status([]) == "pending"

    def test_approved(self, gh: GitHubSync):
        reviews = [{"state": "APPROVED", "author": {"login": "bob"}}]
        assert gh._derive_review_status(reviews) == "APPROVED"

    def test_changes_requested(self, gh: GitHubSync):
        reviews = [{"state": "CHANGES_REQUESTED", "author": {"login": "bob"}}]
        assert gh._derive_review_status(reviews) == "CHANGES_REQUESTED"

    def test_last_state_per_reviewer_wins(self, gh: GitHubSync):
        # bob went from CHANGES_REQUESTED → APPROVED; last state wins
        reviews = [
            {"state": "CHANGES_REQUESTED", "author": {"login": "bob"}},
            {"state": "APPROVED", "author": {"login": "bob"}},
        ]
        assert gh._derive_review_status(reviews) == "APPROVED"

    def test_changes_requested_wins_across_reviewers(self, gh: GitHubSync):
        # One reviewer approved, another requested changes
        reviews = [
            {"state": "APPROVED", "author": {"login": "alice"}},
            {"state": "CHANGES_REQUESTED", "author": {"login": "bob"}},
        ]
        assert gh._derive_review_status(reviews) == "CHANGES_REQUESTED"

    def test_dismissed_ignored(self, gh: GitHubSync):
        reviews = [{"state": "DISMISSED", "author": {"login": "bob"}}]
        assert gh._derive_review_status(reviews) == "pending"

    def test_commented_only_is_pending(self, gh: GitHubSync):
        reviews = [{"state": "COMMENTED", "author": {"login": "bob"}}]
        assert gh._derive_review_status(reviews) == "pending"


# ---------------------------------------------------------------------------
# _match_ticket_keys
# ---------------------------------------------------------------------------


class TestMatchTicketKeys:
    def test_matches_from_title(self, gh: GitHubSync):
        pr = PullRequest(
            number=1, title="ERSC-1278: Fix bug", repo="acme/backend",
            state="open", author="alice", is_draft=False,
            review_status="pending", ci_status="unknown",
            url="", created_at="", updated_at="", branch="main",
        )
        known = {"ERSC-1278", "PROJ-100"}
        assert gh._match_ticket_keys(pr, known) == {"ERSC-1278"}

    def test_matches_from_branch(self, gh: GitHubSync):
        pr = PullRequest(
            number=1, title="Fix some bug", repo="acme/backend",
            state="open", author="alice", is_draft=False,
            review_status="pending", ci_status="unknown",
            url="", created_at="", updated_at="",
            branch="feature/PROJ-100-fix-bug",
        )
        known = {"PROJ-100", "ERSC-1278"}
        assert gh._match_ticket_keys(pr, known) == {"PROJ-100"}

    def test_matches_from_both(self, gh: GitHubSync):
        pr = PullRequest(
            number=1, title="ERSC-1278: Fix bug", repo="acme/backend",
            state="open", author="alice", is_draft=False,
            review_status="pending", ci_status="unknown",
            url="", created_at="", updated_at="",
            branch="feature/PROJ-100-related",
        )
        known = {"ERSC-1278", "PROJ-100"}
        assert gh._match_ticket_keys(pr, known) == {"ERSC-1278", "PROJ-100"}

    def test_no_match(self, gh: GitHubSync):
        pr = PullRequest(
            number=1, title="Random fix", repo="acme/backend",
            state="open", author="alice", is_draft=False,
            review_status="pending", ci_status="unknown",
            url="", created_at="", updated_at="", branch="main",
        )
        known = {"ERSC-1278"}
        assert gh._match_ticket_keys(pr, known) == set()

    def test_unknown_key_not_returned(self, gh: GitHubSync):
        pr = PullRequest(
            number=1, title="UNKNOWN-999: Something", repo="acme/backend",
            state="open", author="alice", is_draft=False,
            review_status="pending", ci_status="unknown",
            url="", created_at="", updated_at="", branch="main",
        )
        known = {"ERSC-1278"}
        assert gh._match_ticket_keys(pr, known) == set()


# ---------------------------------------------------------------------------
# _write_pr_files / _render_pr_md
# ---------------------------------------------------------------------------


def _make_pr(
    number: int = 42,
    title: str = "ERSC-1278: Fix auth",
    repo: str = "acme/backend",
    **kwargs,
) -> PullRequest:
    defaults = dict(
        state="open", author="alice", is_draft=False,
        review_status="APPROVED", ci_status="passing",
        url=f"https://github.com/{repo}/pull/{number}",
        created_at="2026-03-10T10:00:00Z",
        updated_at="2026-03-15T14:30:00Z",
        branch="feature/ERSC-1278-fix-auth",
        base_branch="main",
        body="Fixes the auth bug.",
    )
    defaults.update(kwargs)
    return PullRequest(number=number, title=title, repo=repo, **defaults)


class TestWritePrFiles:
    def test_creates_file_per_pr(self, gh: GitHubSync, tmp_path: Path):
        ticket_dir = tmp_path / "ERSC-1278-fix-auth"
        ticket_dir.mkdir()
        (ticket_dir / "orchestrator").mkdir()

        prs = [_make_pr(42, repo="acme/backend"), _make_pr(7, repo="acme/frontend")]
        gh._write_pr_files(prs, ticket_dir)

        prs_dir = ticket_dir / "orchestrator" / "prs"
        assert prs_dir.is_dir()
        assert (prs_dir / "PR-42-backend.md").exists()
        assert (prs_dir / "PR-7-frontend.md").exists()

    def test_render_pr_md_format(self, gh: GitHubSync, tmp_path: Path):
        ticket_dir = tmp_path / "ERSC-1278-fix-auth"
        ticket_dir.mkdir()
        (ticket_dir / "orchestrator").mkdir()

        pr = _make_pr(
            42,
            reviewers=[Reviewer(login="bob", state="APPROVED")],
            review_threads=[
                ReviewThread(
                    is_resolved=False,
                    comments=[PRComment(
                        author="bob",
                        created_at="2026-03-13T11:00:00Z",
                        body="Consider using a constant here.",
                        path="src/auth/middleware.py",
                        line=45,
                        diff_hunk="@@ -43 +43 @@\n-    timeout = 30\n+    timeout = TOKEN_TIMEOUT",
                    )],
                )
            ],
            comments=[PRComment(
                author="charlie",
                created_at="2026-03-12T09:00:00Z",
                body="Looks good overall.",
            )],
        )
        gh._write_pr_files([pr], ticket_dir)

        content = (ticket_dir / "orchestrator" / "prs" / "PR-42-backend.md").read_text()

        # Frontmatter
        assert content.startswith("---\n")
        assert "source: sync" in content

        # Title and metadata
        assert "# PR #42: ERSC-1278: Fix auth" in content
        assert "**Branch:** feature/ERSC-1278-fix-auth → main" in content
        assert "**CI:** passing" in content
        assert "**Author:** @alice" in content
        assert "https://github.com/acme/backend/pull/42" in content

        # Description
        assert "## Description" in content
        assert "Fixes the auth bug." in content

        # Reviewers
        assert "## Reviewers" in content
        assert "@bob: APPROVED" in content

        # Outstanding review comments
        assert "## Outstanding Review Comments" in content
        assert "`src/auth/middleware.py:45`" in content
        assert "Consider using a constant here." in content
        assert "TOKEN_TIMEOUT" in content  # diff hunk content

        # General comments
        assert "## General Comments" in content
        assert "Looks good overall." in content

    def test_draft_indicator(self, gh: GitHubSync, tmp_path: Path):
        ticket_dir = tmp_path / "ERSC-100-task"
        ticket_dir.mkdir()
        (ticket_dir / "orchestrator").mkdir()

        pr = _make_pr(7, repo="acme/frontend", is_draft=True, title="WIP experiment")
        gh._write_pr_files([pr], ticket_dir)

        content = (ticket_dir / "orchestrator" / "prs" / "PR-7-frontend.md").read_text()
        assert "[Draft]" in content

    def test_no_description_fallback(self, gh: GitHubSync, tmp_path: Path):
        ticket_dir = tmp_path / "ERSC-100-task"
        ticket_dir.mkdir()
        (ticket_dir / "orchestrator").mkdir()

        pr = _make_pr(1, repo="acme/backend", body="")
        gh._write_pr_files([pr], ticket_dir)

        content = (ticket_dir / "orchestrator" / "prs" / "PR-1-backend.md").read_text()
        assert "_No description._" in content

    def test_resolved_threads_hidden(self, gh: GitHubSync, tmp_path: Path):
        ticket_dir = tmp_path / "ERSC-100-task"
        ticket_dir.mkdir()
        (ticket_dir / "orchestrator").mkdir()

        pr = _make_pr(
            1, repo="acme/backend",
            review_threads=[
                ReviewThread(is_resolved=True, comments=[
                    PRComment(author="bob", created_at="2026-03-10T00:00:00Z",
                              body="Old comment.", path="file.py", line=1),
                ]),
                ReviewThread(is_resolved=False, comments=[
                    PRComment(author="alice", created_at="2026-03-11T00:00:00Z",
                              body="Still open.", path="file.py", line=2),
                ]),
            ],
        )
        gh._write_pr_files([pr], ticket_dir)

        content = (ticket_dir / "orchestrator" / "prs" / "PR-1-backend.md").read_text()
        assert "Still open." in content
        assert "Old comment." not in content
        assert "1 resolved thread" in content


# ---------------------------------------------------------------------------
# _graphql_search (HTTP mocking)
# ---------------------------------------------------------------------------


class TestGraphqlSearch:
    def test_single_page(self, gh: GitHubSync, httpx_mock, graphql_response: dict):
        httpx_mock.add_response(
            url=_GRAPHQL_URL,
            json=graphql_response,
        )

        prs = gh._graphql_search("type:pr author:alice")
        assert len(prs) == 3
        assert prs[0].number == 42
        assert prs[1].number == 99
        assert prs[2].number == 7

    def test_pagination(self, gh: GitHubSync, httpx_mock):
        page1 = {
            "data": {
                "search": {
                    "pageInfo": {"hasNextPage": True, "endCursor": "cursor1"},
                    "nodes": [
                        {
                            "number": 1,
                            "title": "First PR",
                            "state": "OPEN",
                            "isDraft": False,
                            "url": "https://github.com/acme/repo/pull/1",
                            "createdAt": "2026-03-01T00:00:00Z",
                            "updatedAt": "2026-03-01T00:00:00Z",
                            "mergedAt": None,
                            "headRefName": "feature/first",
                            "repository": {"nameWithOwner": "acme/repo"},
                            "author": {"login": "alice"},
                            "reviews": {"nodes": []},
                            "reviewRequests": {"nodes": []},
                            "commits": {"nodes": []},
                            "comments": {"nodes": []},
                            "reviewThreads": {"nodes": []},
                        }
                    ],
                }
            }
        }
        page2 = {
            "data": {
                "search": {
                    "pageInfo": {"hasNextPage": False, "endCursor": "cursor2"},
                    "nodes": [
                        {
                            "number": 2,
                            "title": "Second PR",
                            "state": "OPEN",
                            "isDraft": False,
                            "url": "https://github.com/acme/repo/pull/2",
                            "createdAt": "2026-03-02T00:00:00Z",
                            "updatedAt": "2026-03-02T00:00:00Z",
                            "mergedAt": None,
                            "headRefName": "feature/second",
                            "repository": {"nameWithOwner": "acme/repo"},
                            "author": {"login": "alice"},
                            "reviews": {"nodes": []},
                            "reviewRequests": {"nodes": []},
                            "commits": {"nodes": []},
                            "comments": {"nodes": []},
                            "reviewThreads": {"nodes": []},
                        }
                    ],
                }
            }
        }

        httpx_mock.add_response(url=_GRAPHQL_URL, json=page1)
        httpx_mock.add_response(url=_GRAPHQL_URL, json=page2)

        prs = gh._graphql_search("type:pr author:alice")
        assert len(prs) == 2
        assert prs[0].number == 1
        assert prs[1].number == 2

    def test_auth_failure_raises(self, gh: GitHubSync, httpx_mock):
        httpx_mock.add_response(url=_GRAPHQL_URL, status_code=401, text="Unauthorized")

        with pytest.raises(AuthError, match="401"):
            gh._graphql_search("type:pr author:alice")

    def test_server_error_raises(self, gh: GitHubSync, httpx_mock):
        httpx_mock.add_response(url=_GRAPHQL_URL, status_code=500, text="Server Error")

        with pytest.raises(SyncError, match="500"):
            gh._graphql_search("type:pr author:alice")

    def test_graphql_errors_raises(self, gh: GitHubSync, httpx_mock):
        httpx_mock.add_response(
            url=_GRAPHQL_URL,
            json={"errors": [{"message": "Bad query"}]},
        )

        with pytest.raises(SyncError, match="GraphQL errors"):
            gh._graphql_search("type:pr author:alice")

    def test_skips_empty_nodes(self, gh: GitHubSync, httpx_mock):
        response = {
            "data": {
                "search": {
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": [None, {}, {"number": 10, "title": "Valid",
                        "state": "OPEN", "isDraft": False,
                        "url": "https://github.com/a/b/pull/10",
                        "createdAt": "2026-03-01T00:00:00Z",
                        "updatedAt": "2026-03-01T00:00:00Z",
                        "mergedAt": None, "headRefName": "main",
                        "repository": {"nameWithOwner": "a/b"},
                        "author": {"login": "alice"},
                        "reviews": {"nodes": []},
                        "reviewRequests": {"nodes": []},
                        "commits": {"nodes": []},
                        "comments": {"nodes": []},
                        "reviewThreads": {"nodes": []},
                    }],
                }
            }
        }
        httpx_mock.add_response(url=_GRAPHQL_URL, json=response)

        prs = gh._graphql_search("type:pr author:alice")
        assert len(prs) == 1
        assert prs[0].number == 10


# ---------------------------------------------------------------------------
# Full sync cycle
# ---------------------------------------------------------------------------


class TestFullSync:
    def test_sync_writes_pr_files(
        self, gh: GitHubSync, httpx_mock, graphql_response: dict, tmp_workspace: Path,
    ):
        # Create ticket directory that matches PR #42 (ERSC-1278 in title and branch)
        _make_ticket_dir(tmp_workspace, "ERSC-1278", "fix-auth")

        # Single batched request returns all 3 query results
        httpx_mock.add_response(url=_GRAPHQL_URL, json=_batched_response(graphql_response))

        result = gh.sync(tmp_workspace)

        assert result.source == "github"
        assert result.tickets_synced == 1
        assert result.errors == []
        assert result.duration_seconds > 0

        prs_dir = tmp_workspace / "ERSC-1278-fix-auth" / "orchestrator" / "prs"
        assert prs_dir.is_dir()
        # PR #42 is in acme/backend → PR-42-backend.md
        assert (prs_dir / "PR-42-backend.md").exists()
        # PR #7 also matches ERSC-1278 via branch name (acme/frontend → PR-7-frontend.md)
        assert (prs_dir / "PR-7-frontend.md").exists()

    def test_sync_no_ticket_dirs(self, gh: GitHubSync, tmp_workspace: Path):
        result = gh.sync(tmp_workspace)
        assert result.tickets_synced == 0
        assert result.errors == []

    def test_sync_no_matching_prs(
        self, gh: GitHubSync, httpx_mock, tmp_workspace: Path,
    ):
        _make_ticket_dir(tmp_workspace, "NOMATCH-999", "unrelated")

        empty_response = {
            "data": {
                "search": {
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": [],
                }
            }
        }
        httpx_mock.add_response(url=_GRAPHQL_URL, json=_batched_response(empty_response))

        result = gh.sync(tmp_workspace)
        assert result.tickets_synced == 0
        assert result.errors == []

    def test_sync_auth_failure(
        self, gh: GitHubSync, httpx_mock, tmp_workspace: Path,
    ):
        _make_ticket_dir(tmp_workspace, "ERSC-1278", "fix-auth")

        httpx_mock.add_response(url=_GRAPHQL_URL, status_code=401, text="Unauthorized")

        result = gh.sync(tmp_workspace)
        assert result.tickets_synced == 0
        assert len(result.errors) == 1
        assert "401" in result.errors[0]

    def test_sync_deduplicates_prs(
        self, gh: GitHubSync, httpx_mock, graphql_response: dict, tmp_workspace: Path,
    ):
        _make_ticket_dir(tmp_workspace, "ERSC-1278", "fix-auth")

        # All 3 aliases return the same PRs -- dedup should prevent duplicates
        httpx_mock.add_response(url=_GRAPHQL_URL, json=_batched_response(graphql_response))

        result = gh.sync(tmp_workspace)
        assert result.tickets_synced == 1

        prs_dir = tmp_workspace / "ERSC-1278-fix-auth" / "orchestrator" / "prs"
        # Only one file per PR number+repo, despite duplicate results across queries
        assert len(list(prs_dir.glob("PR-42-*.md"))) == 1
