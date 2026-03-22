"""GitHub GraphQL sync source for duct."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from duct.exceptions import AuthError, SyncError
from duct.markdown import TICKET_KEY_PATTERN, atomic_write, generate_frontmatter
from duct.models import PRComment, PullRequest, ReviewThread, Reviewer, SyncResult
from duct.workspace import enumerate_ticket_dirs, orchestrator_dir

_GRAPHQL_URL = "https://api.github.com/graphql"

_PR_FIELDS = """
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on PullRequest {
        number
        title
        state
        isDraft
        url
        createdAt
        updatedAt
        mergedAt
        headRefName
        baseRefName
        body
        repository { nameWithOwner name }
        author { login }
        reviews(last: 10) {
          nodes { state author { login } }
        }
        commits(last: 1) {
          nodes {
            commit {
              statusCheckRollup { state }
            }
          }
        }
        comments(last: 20) {
          nodes {
            author { login }
            body
            createdAt
          }
        }
        reviewThreads(last: 30) {
          nodes {
            isResolved
            comments(first: 10) {
              nodes {
                author { login }
                body
                createdAt
                path
                line
                originalLine
                diffHunk
              }
            }
          }
        }
      }
    }
"""

_PR_SEARCH_QUERY = """
query($query: String!, $cursor: String) {
  search(query: $query, type: ISSUE, first: 50, after: $cursor) {
""" + _PR_FIELDS + """
  }
}
"""

_LANG_MAP = {
    "py": "python", "ts": "typescript", "tsx": "typescript",
    "js": "javascript", "jsx": "javascript", "go": "go",
    "rb": "ruby", "java": "java", "cs": "csharp",
    "rs": "rust", "cpp": "cpp", "c": "c",
}


class GitHubSync:
    name = "github"

    def __init__(self, token: str, github_username: str | None = None):
        if not token:
            raise AuthError("GH_TOKEN is not set")
        self._token = token
        self._username = github_username
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def sync(self, root: Path, ticket_key: str | None = None) -> SyncResult:
        start = time.time()
        errors: list[str] = []

        ticket_keys = {key for key, _ in enumerate_ticket_dirs(root)}
        if ticket_key:
            ticket_keys &= {ticket_key}
        if not ticket_keys:
            return SyncResult(
                source=self.name, tickets_synced=0, duration_seconds=time.time() - start
            )

        try:
            all_prs = self._search_prs()
        except (AuthError, SyncError) as exc:
            return SyncResult(
                source=self.name,
                tickets_synced=0,
                duration_seconds=time.time() - start,
                errors=[str(exc)],
            )

        # Match PRs to tickets
        ticket_prs: dict[str, list[PullRequest]] = {k: [] for k in ticket_keys}
        for pr in all_prs:
            matched_keys = self._match_ticket_keys(pr, ticket_keys)
            for key in matched_keys:
                ticket_prs[key].append(pr)

        # Write per-PR files for each ticket that has PRs
        synced = 0
        for key, prs in ticket_prs.items():
            if not prs:
                continue
            ticket_dirs = [(k, p) for k, p in enumerate_ticket_dirs(root) if k == key]
            if not ticket_dirs:
                continue
            _, ticket_path = ticket_dirs[0]
            try:
                self._write_pr_files(prs, ticket_path)
                synced += 1
            except Exception as exc:
                errors.append(f"{key}: failed to write PR data - {exc}")

        return SyncResult(
            source=self.name,
            tickets_synced=synced,
            duration_seconds=time.time() - start,
            errors=errors,
        )

    def _search_prs(self) -> list[PullRequest]:
        """Search GitHub for PRs via batched GraphQL queries, deduplicate by repo#number."""
        if self._username:
            queries = [
                f"type:pr author:{self._username}",
                f"type:pr assignee:{self._username}",
                f"type:pr review-requested:{self._username}",
            ]
        else:
            queries = [
                "type:pr author:@me",
                "type:pr review-requested:@me",
            ]

        # Batch all queries into a single GraphQL request using aliases
        seen: dict[str, PullRequest] = {}
        prs_by_alias, needs_pagination = self._graphql_search_batched(queries)
        for alias_prs in prs_by_alias.values():
            for pr in alias_prs:
                dedup_key = f"{pr.repo}#{pr.number}"
                if dedup_key not in seen:
                    seen[dedup_key] = pr

        # Only paginate individually for queries that had more results
        for query in needs_pagination:
            for pr in self._graphql_search(query):
                dedup_key = f"{pr.repo}#{pr.number}"
                if dedup_key not in seen:
                    seen[dedup_key] = pr

        return list(seen.values())

    def _graphql_search_batched(
        self, queries: list[str]
    ) -> tuple[dict[str, list[PullRequest]], list[str]]:
        """Execute multiple search queries in a single GraphQL request using aliases.

        Returns (results_by_alias, queries_needing_pagination).
        """
        # Build a single query with aliased search fields
        parts = ["query("]
        params = []
        for i in range(len(queries)):
            params.append(f"$q{i}: String!")
        parts.append(", ".join(params))
        parts.append(") {")
        for i in range(len(queries)):
            parts.append(f"  s{i}: search(query: $q{i}, type: ISSUE, first: 50) {{")
            parts.append(_PR_FIELDS)
            parts.append("  }")
        parts.append("}")
        query_str = "\n".join(parts)

        variables = {f"q{i}": q for i, q in enumerate(queries)}

        response = httpx.post(
            _GRAPHQL_URL,
            headers=self._headers,
            json={"query": query_str, "variables": variables},
            timeout=30,
        )

        if response.status_code == 401:
            raise AuthError("GitHub authentication failed (401)")
        if response.status_code != 200:
            raise SyncError(f"GitHub API error: {response.status_code}")

        data = response.json()
        if "errors" in data:
            raise SyncError(f"GitHub GraphQL errors: {data['errors']}")

        results: dict[str, list[PullRequest]] = {}
        needs_pagination: list[str] = []

        for i, query in enumerate(queries):
            alias = f"s{i}"
            search = data.get("data", {}).get(alias, {})
            nodes = search.get("nodes", [])
            prs = []
            for node in nodes:
                if not node or "number" not in node:
                    continue
                prs.append(self._parse_pr_node(node))
            results[alias] = prs

            page_info = search.get("pageInfo", {})
            if page_info.get("hasNextPage"):
                needs_pagination.append(query)

        return results, needs_pagination

    def _graphql_search(self, query: str) -> list[PullRequest]:
        """Execute a paginated GraphQL search and return PullRequest models."""
        prs: list[PullRequest] = []
        cursor = None

        while True:
            variables: dict[str, str] = {"query": query}
            if cursor:
                variables["cursor"] = cursor

            response = httpx.post(
                _GRAPHQL_URL,
                headers=self._headers,
                json={"query": _PR_SEARCH_QUERY, "variables": variables},
                timeout=30,
            )

            if response.status_code == 401:
                raise AuthError("GitHub authentication failed (401)")
            if response.status_code != 200:
                raise SyncError(f"GitHub API error: {response.status_code}")

            data = response.json()
            if "errors" in data:
                raise SyncError(f"GitHub GraphQL errors: {data['errors']}")

            search = data.get("data", {}).get("search", {})
            nodes = search.get("nodes", [])

            for node in nodes:
                if not node or "number" not in node:
                    continue
                pr = self._parse_pr_node(node)
                prs.append(pr)

            page_info = search.get("pageInfo", {})
            if page_info.get("hasNextPage") and page_info.get("endCursor"):
                cursor = page_info["endCursor"]
            else:
                break

        return prs

    def _parse_pr_node(self, node: dict) -> PullRequest:
        """Parse a GraphQL PR node into a PullRequest model."""
        repo_obj = node.get("repository", {})
        repo_full = repo_obj.get("nameWithOwner", "")

        if node.get("mergedAt"):
            state = "merged"
        else:
            state = node.get("state", "OPEN").lower()

        reviews = node.get("reviews", {}).get("nodes", [])
        review_status = self._derive_review_status(reviews)

        commits = node.get("commits", {}).get("nodes", [])
        ci_status = "unknown"
        if commits:
            rollup = commits[-1].get("commit", {}).get("statusCheckRollup")
            if rollup:
                ci_state = rollup.get("state", "").lower()
                ci_status = (
                    {"success": "passing", "failure": "failing", "pending": "pending"}
                    .get(ci_state, ci_state)
                )

        # Build reviewer map (last non-dismissed review per author wins)
        reviewer_map: dict[str, str] = {}
        for r in reviews:
            login = r.get("author", {}).get("login", "")
            state_r = r.get("state", "")
            if login and state_r != "DISMISSED":
                reviewer_map[login] = state_r
        reviewers = [Reviewer(login=lg, state=st) for lg, st in reviewer_map.items()]

        # General PR-level comments
        comments: list[PRComment] = []
        for c in node.get("comments", {}).get("nodes", []):
            if c and c.get("body"):
                comments.append(PRComment(
                    author=c.get("author", {}).get("login", "unknown"),
                    created_at=c.get("createdAt", ""),
                    body=c.get("body", ""),
                ))

        # Review threads (inline code comments)
        review_threads: list[ReviewThread] = []
        for thread in node.get("reviewThreads", {}).get("nodes", []):
            is_resolved = thread.get("isResolved", False)
            thread_comments: list[PRComment] = []
            for c in thread.get("comments", {}).get("nodes", []):
                if c and c.get("body"):
                    thread_comments.append(PRComment(
                        author=c.get("author", {}).get("login", "unknown"),
                        created_at=c.get("createdAt", ""),
                        body=c.get("body", ""),
                        path=c.get("path"),
                        line=c.get("line") or c.get("originalLine"),
                        diff_hunk=c.get("diffHunk"),
                    ))
            review_threads.append(ReviewThread(
                is_resolved=is_resolved,
                comments=thread_comments,
            ))

        return PullRequest(
            number=node["number"],
            title=node.get("title", ""),
            repo=repo_full,
            state=state,
            author=node.get("author", {}).get("login", "unknown"),
            is_draft=node.get("isDraft", False),
            review_status=review_status,
            ci_status=ci_status,
            url=node.get("url", ""),
            created_at=node.get("createdAt", ""),
            updated_at=node.get("updatedAt", ""),
            branch=node.get("headRefName", ""),
            base_branch=node.get("baseRefName", ""),
            body=node.get("body") or "",
            reviewers=reviewers,
            comments=comments,
            review_threads=review_threads,
        )

    def _derive_review_status(self, reviews: list[dict]) -> str:
        """Derive overall review status using per-reviewer last-state tracking."""
        if not reviews:
            return "pending"
        reviewer_states: dict[str, str] = {}
        for review in reviews:
            login = review.get("author", {}).get("login", "")
            state = review.get("state", "")
            if login and state not in ("DISMISSED", "COMMENTED"):
                reviewer_states[login] = state
        if not reviewer_states:
            return "pending"
        states = set(reviewer_states.values())
        if "CHANGES_REQUESTED" in states:
            return "CHANGES_REQUESTED"
        if states == {"APPROVED"}:
            return "APPROVED"
        return "pending"

    def _match_ticket_keys(self, pr: PullRequest, known_keys: set[str]) -> set[str]:
        """Extract ticket keys from PR title and branch name."""
        text = f"{pr.title} {pr.branch}"
        matches = set(TICKET_KEY_PATTERN.findall(text))
        return matches & known_keys

    def _write_pr_files(self, prs: list[PullRequest], ticket_dir: Path) -> None:
        """Write orchestrator/prs/PR-{number}-{repo}.md for each PR."""
        prs_dir = orchestrator_dir(ticket_dir) / "prs"
        prs_dir.mkdir(exist_ok=True)

        for pr in prs:
            repo_short = pr.repo.split("/")[-1]
            filename = f"PR-{pr.number}-{repo_short}.md"
            content = self._render_pr_md(pr)
            atomic_write(prs_dir / filename, content)

    def _render_pr_md(self, pr: PullRequest) -> str:
        """Render a PR as markdown."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        lines = [
            generate_frontmatter(source="sync", synced_at=now),
            "",
            f"# PR #{pr.number}: {pr.title}",
            f"**Repo:** {pr.repo}",
            f"**Branch:** {pr.branch} → {pr.base_branch}",
            f"**Status:** {'[Draft] ' if pr.is_draft else ''}{pr.state.title()} | {pr.review_status.replace('_', ' ').title()}",
            f"**CI:** {pr.ci_status}",
            f"**Author:** @{pr.author}",
            f"**URL:** {pr.url}",
            f"**Updated:** {pr.updated_at[:10]}",
            "",
            "## Description",
            pr.body or "_No description._",
            "",
        ]

        # Reviewer summary
        if pr.reviewers:
            lines.append("## Reviewers")
            lines.append("")
            for r in pr.reviewers:
                lines.append(f"- @{r.login}: {r.state}")
            lines.append("")

        # Review threads (inline comments)
        unresolved = [t for t in pr.review_threads if not t.is_resolved]
        resolved_count = len(pr.review_threads) - len(unresolved)
        if unresolved:
            lines.append("## Outstanding Review Comments")
            lines.append("")
            for thread in unresolved:
                for i, c in enumerate(thread.comments):
                    author = c.author
                    created = (c.created_at or "")[:10]
                    body = (c.body or "").strip()
                    path = c.path or ""
                    line_num = c.line or ""
                    diff_hunk = (c.diff_hunk or "").strip()

                    if i == 0:
                        location = f"`{path}:{line_num}`" if line_num else f"`{path}`"
                        lines.append(f"### {location} — {author} ({created})")

                        if diff_hunk:
                            ext = path.rsplit(".", 1)[-1] if "." in path else ""
                            lang = _LANG_MAP.get(ext, "")
                            lines.append(f"```{lang}")
                            hunk_lines = diff_hunk.split("\n")
                            context = hunk_lines[-6:] if len(hunk_lines) > 6 else hunk_lines
                            lines.extend(context)
                            lines.append("```")

                        lines.append(f"> {body}")
                    else:
                        lines.append(f"**Reply — {author} ({created}):**")
                        lines.append(f"> {body}")
                    lines.append("")

                lines.append("---")
                lines.append("")

            if resolved_count:
                lines.append(f"<!-- {resolved_count} resolved thread(s) hidden -->")
                lines.append("")

        # General comments
        if pr.comments:
            lines.append("## General Comments")
            lines.append("")
            for c in pr.comments:
                author = c.author
                created = (c.created_at or "")[:10]
                body = (c.body or "").strip()
                lines.append(f"### {author} — {created}")
                lines.append(body)
                lines.append("")

        return "\n".join(lines)
