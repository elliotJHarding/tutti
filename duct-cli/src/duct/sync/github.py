"""GitHub GraphQL sync source for duct."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from duct.exceptions import AuthError, SyncError
from duct.markdown import TICKET_KEY_PATTERN, atomic_write, generate_frontmatter
from duct.models import PRComment, PullRequest, Reviewer, SyncResult
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
        repository { nameWithOwner }
        author { login }
        reviews(last: 10) {
          nodes { state author { login } }
        }
        reviewRequests(first: 10) {
          nodes { requestedReviewer { ... on User { login } } }
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
        reviewThreads(last: 20) {
          nodes {
            comments(first: 1) {
              nodes {
                author { login }
                body
                createdAt
                path
                line
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

    def sync(self, root: Path) -> SyncResult:
        start = time.time()
        errors: list[str] = []

        ticket_keys = {key for key, _ in enumerate_ticket_dirs(root)}
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

        # Write PULL_REQUESTS.md for each ticket that has PRs
        synced = 0
        for key, prs in ticket_prs.items():
            if not prs:
                continue
            ticket_dirs = [(k, p) for k, p in enumerate_ticket_dirs(root) if k == key]
            if not ticket_dirs:
                continue
            _, ticket_path = ticket_dirs[0]
            try:
                self._write_pull_requests_md(prs, ticket_path)
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

        # Build reviewer map (last review per author wins)
        reviewer_map: dict[str, str] = {}
        for r in reviews:
            login = r.get("author", {}).get("login", "")
            if login:
                reviewer_map[login] = r.get("state", "")
        reviewers = [Reviewer(login=lg, state=st) for lg, st in reviewer_map.items()]

        # Collect comments from both regular comments and review threads
        comments: list[PRComment] = []
        for c in node.get("comments", {}).get("nodes", []):
            if c and c.get("body"):
                comments.append(PRComment(
                    author=c.get("author", {}).get("login", "unknown"),
                    created_at=c.get("createdAt", ""),
                    body=c.get("body", ""),
                ))
        for thread in node.get("reviewThreads", {}).get("nodes", []):
            thread_comments = thread.get("comments", {}).get("nodes", [])
            for c in thread_comments:
                if c and c.get("body"):
                    comments.append(PRComment(
                        author=c.get("author", {}).get("login", "unknown"),
                        created_at=c.get("createdAt", ""),
                        body=c.get("body", ""),
                        path=c.get("path"),
                        line=c.get("line"),
                    ))

        return PullRequest(
            number=node["number"],
            title=node.get("title", ""),
            repo=node.get("repository", {}).get("nameWithOwner", ""),
            state=state,
            author=node.get("author", {}).get("login", "unknown"),
            is_draft=node.get("isDraft", False),
            review_status=review_status,
            ci_status=ci_status,
            url=node.get("url", ""),
            created_at=node.get("createdAt", ""),
            updated_at=node.get("updatedAt", ""),
            branch=node.get("headRefName", ""),
            reviewers=reviewers,
            comments=comments,
        )

    def _derive_review_status(self, reviews: list[dict]) -> str:
        """Derive the overall review status from a list of review nodes."""
        if not reviews:
            return "pending"
        for review in reversed(reviews):
            state = review.get("state", "")
            if state in ("APPROVED", "CHANGES_REQUESTED"):
                return state
        return "pending"

    def _match_ticket_keys(self, pr: PullRequest, known_keys: set[str]) -> set[str]:
        """Extract ticket keys from PR title and branch name."""
        text = f"{pr.title} {pr.branch}"
        matches = set(TICKET_KEY_PATTERN.findall(text))
        return matches & known_keys

    def _write_pull_requests_md(self, prs: list[PullRequest], ticket_dir: Path) -> None:
        """Write PULL_REQUESTS.md into the orchestrator directory for a ticket."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        parts: list[str] = []

        parts.append(generate_frontmatter(source="sync", synced_at=now))
        parts.append("")
        parts.append("# Pull Requests")
        parts.append("")

        for pr in prs:
            draft = " (DRAFT)" if pr.is_draft else ""
            parts.append(f"## #{pr.number} - {pr.title}{draft}")
            parts.append("")
            parts.append(f"- **Repo**: {pr.repo}")
            parts.append(f"- **State**: {pr.state}")
            parts.append(f"- **Author**: @{pr.author}")
            parts.append(f"- **Review**: {pr.review_status}")
            parts.append(f"- **CI**: {pr.ci_status}")
            parts.append(f"- **Created**: {pr.created_at}")
            parts.append(f"- **Updated**: {pr.updated_at}")
            parts.append(f"- [View on GitHub]({pr.url})")
            parts.append("")

            if pr.reviewers:
                parts.append("### Reviewers")
                parts.append("")
                for r in pr.reviewers:
                    parts.append(f"- @{r.login}: {r.state}")
                parts.append("")

            review_comments = [c for c in pr.comments if c.path]
            if review_comments:
                parts.append("### Outstanding Comments")
                parts.append("")
                for c in review_comments:
                    loc = f"`{c.path}:{c.line}`" if c.line else f"`{c.path}`"
                    parts.append(f"> **@{c.author}** on {loc} ({c.created_at})")
                    for line in c.body.splitlines():
                        parts.append(f"> {line}")
                    parts.append("")

        content = "\n".join(parts)
        orch = orchestrator_dir(ticket_dir)
        atomic_write(orch / "PULL_REQUESTS.md", content)
