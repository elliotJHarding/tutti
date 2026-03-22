"""Tests for the CI sync source."""

from __future__ import annotations

from pathlib import Path

from duct.markdown import generate_frontmatter, parse_frontmatter
from duct.sync.ci import CISync


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_ticket_dir(root: Path, key: str, slug: str) -> Path:
    """Create a minimal ticket directory structure under *root*."""
    ticket_dir = root / f"{key}-{slug}"
    ticket_dir.mkdir(parents=True)
    (ticket_dir / "orchestrator").mkdir()
    return ticket_dir


def _write_pr_file(
    ticket_dir: Path,
    number: int,
    repo: str,
    ci_status: str,
    pr_title: str = "Fix the thing",
) -> None:
    """Write a per-PR markdown file in the new prs/ format."""
    prs_dir = ticket_dir / "orchestrator" / "prs"
    prs_dir.mkdir(exist_ok=True)
    fm = generate_frontmatter(source="sync", synced_at="2026-03-16T00:00:00Z")
    body = "\n".join([
        f"# PR #{number}: {pr_title}",
        f"**Repo:** acme/{repo}",
        "**Branch:** feature/PROJ-200-thing → main",
        f"**CI:** {ci_status}",
        "**Author:** @alice",
        f"**URL:** https://github.com/acme/{repo}/pull/{number}",
        "",
        "## Description",
        "_No description._",
    ])
    (prs_dir / f"PR-{number}-{repo}.md").write_text(fm + "\n" + body)


# ---------------------------------------------------------------------------
# No prs/ dir → no output
# ---------------------------------------------------------------------------


class TestNoPrsDir:
    def test_no_prs_dir_produces_no_output(self, tmp_workspace: Path):
        _make_ticket_dir(tmp_workspace, "PROJ-100", "some-ticket")

        ci = CISync()
        result = ci.sync(tmp_workspace)

        assert result.source == "ci"
        assert result.tickets_synced == 0
        assert result.errors == []

        ci_md = tmp_workspace / "PROJ-100-some-ticket" / "orchestrator" / "CI.md"
        assert not ci_md.exists()

    def test_empty_workspace(self, tmp_workspace: Path):
        ci = CISync()
        result = ci.sync(tmp_workspace)

        assert result.tickets_synced == 0
        assert result.errors == []


# ---------------------------------------------------------------------------
# Extracts CI status from prs/ and writes CI.md
# ---------------------------------------------------------------------------


class TestCISyncExtraction:
    def test_extracts_single_pr_ci_status(self, tmp_workspace: Path):
        ticket_dir = _make_ticket_dir(tmp_workspace, "PROJ-200", "auth-feature")
        _write_pr_file(ticket_dir, 42, "backend", "passing", "Add OAuth2 login")

        ci = CISync()
        result = ci.sync(tmp_workspace)

        assert result.tickets_synced == 1
        assert result.errors == []

        ci_md = ticket_dir / "orchestrator" / "CI.md"
        assert ci_md.exists()

        content = ci_md.read_text()
        assert "Add OAuth2 login" in content
        assert "- **Status**: passing" in content

    def test_extracts_multiple_pr_ci_statuses(self, tmp_workspace: Path):
        ticket_dir = _make_ticket_dir(tmp_workspace, "PROJ-300", "multi-pr")
        _write_pr_file(ticket_dir, 10, "backend", "passing", "First PR")
        _write_pr_file(ticket_dir, 11, "frontend", "failing", "Second PR")

        ci = CISync()
        result = ci.sync(tmp_workspace)

        assert result.tickets_synced == 1

        content = (ticket_dir / "orchestrator" / "CI.md").read_text()
        assert "- **Status**: passing" in content
        assert "- **Status**: failing" in content

    def test_skips_pr_without_ci_line(self, tmp_workspace: Path):
        ticket_dir = _make_ticket_dir(tmp_workspace, "PROJ-400", "no-ci-line")
        prs_dir = ticket_dir / "orchestrator" / "prs"
        prs_dir.mkdir()
        # Write a PR file without a CI line
        (prs_dir / "PR-50-backend.md").write_text(
            generate_frontmatter(source="sync", synced_at="2026-03-16T00:00:00Z")
            + "\n# PR #50: Some PR\n**Author:** @bob\n"
        )

        ci = CISync()
        result = ci.sync(tmp_workspace)

        assert result.tickets_synced == 0
        assert not (ticket_dir / "orchestrator" / "CI.md").exists()


# ---------------------------------------------------------------------------
# CI.md format validation
# ---------------------------------------------------------------------------


class TestCIMdFormat:
    def test_frontmatter_present(self, tmp_workspace: Path):
        ticket_dir = _make_ticket_dir(tmp_workspace, "PROJ-500", "fm-check")
        _write_pr_file(ticket_dir, 1, "backend", "passing", "Test PR")

        CISync().sync(tmp_workspace)

        content = (ticket_dir / "orchestrator" / "CI.md").read_text()
        meta, _ = parse_frontmatter(content)

        assert meta["source"] == "sync"
        assert "syncedAt" in meta

    def test_heading_structure(self, tmp_workspace: Path):
        ticket_dir = _make_ticket_dir(tmp_workspace, "PROJ-600", "heading-check")
        _write_pr_file(ticket_dir, 7, "backend", "pending", "Feature branch")

        CISync().sync(tmp_workspace)

        content = (ticket_dir / "orchestrator" / "CI.md").read_text()
        assert "# CI Status" in content
        assert "Feature branch" in content
        assert "- **Status**: pending" in content

    def test_duration_is_positive(self, tmp_workspace: Path):
        _make_ticket_dir(tmp_workspace, "PROJ-700", "duration")

        result = CISync().sync(tmp_workspace)
        assert result.duration_seconds >= 0
