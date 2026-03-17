"""Tests for the CI sync source (stub)."""

from __future__ import annotations

from pathlib import Path

from tutti.markdown import generate_frontmatter, parse_frontmatter
from tutti.sync.ci import CISync

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_ticket_dir(root: Path, key: str, slug: str) -> Path:
    """Create a minimal ticket directory structure under *root*."""
    ticket_dir = root / f"{key}-{slug}"
    ticket_dir.mkdir(parents=True)
    (ticket_dir / "orchestrator").mkdir()
    return ticket_dir


def _write_pr_md(ticket_dir: Path, body: str) -> None:
    """Write a PULL_REQUESTS.md with frontmatter into the orchestrator dir."""
    fm = generate_frontmatter(source="sync", synced_at="2026-03-16T00:00:00Z")
    content = fm + "\n" + body
    (ticket_dir / "orchestrator" / "PULL_REQUESTS.md").write_text(content)


# ---------------------------------------------------------------------------
# No PULL_REQUESTS.md -> no output
# ---------------------------------------------------------------------------


class TestNoPullRequestsMd:
    def test_no_pr_md_produces_no_output(self, tmp_workspace: Path):
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
# Extracts CI status from PULL_REQUESTS.md and writes CI.md
# ---------------------------------------------------------------------------


class TestCISyncExtraction:
    def test_extracts_single_pr_ci_status(self, tmp_workspace: Path):
        ticket_dir = _make_ticket_dir(tmp_workspace, "PROJ-200", "auth-feature")
        _write_pr_md(ticket_dir, "\n".join([
            "## #42 Add OAuth2 login",
            "",
            "- **Author**: alice",
            "- **CI**: passing",
            "- **State**: open",
        ]))

        ci = CISync()
        result = ci.sync(tmp_workspace)

        assert result.tickets_synced == 1
        assert result.errors == []

        ci_md = ticket_dir / "orchestrator" / "CI.md"
        assert ci_md.exists()

        content = ci_md.read_text()
        assert "## 42 Add OAuth2 login" in content
        assert "- **Status**: passing" in content

    def test_extracts_multiple_pr_ci_statuses(self, tmp_workspace: Path):
        ticket_dir = _make_ticket_dir(tmp_workspace, "PROJ-300", "multi-pr")
        _write_pr_md(ticket_dir, "\n".join([
            "## #10 First PR",
            "",
            "- **CI**: passing",
            "",
            "## #11 Second PR",
            "",
            "- **CI**: failing",
        ]))

        ci = CISync()
        result = ci.sync(tmp_workspace)

        assert result.tickets_synced == 1

        content = (ticket_dir / "orchestrator" / "CI.md").read_text()
        assert "- **Status**: passing" in content
        assert "- **Status**: failing" in content

    def test_skips_pr_without_ci_line(self, tmp_workspace: Path):
        ticket_dir = _make_ticket_dir(tmp_workspace, "PROJ-400", "no-ci-line")
        _write_pr_md(ticket_dir, "\n".join([
            "## #50 Some PR",
            "",
            "- **Author**: bob",
            "- **State**: open",
        ]))

        ci = CISync()
        result = ci.sync(tmp_workspace)

        # No CI entries extracted, so no CI.md written and tickets_synced == 0.
        assert result.tickets_synced == 0
        assert not (ticket_dir / "orchestrator" / "CI.md").exists()


# ---------------------------------------------------------------------------
# CI.md format validation
# ---------------------------------------------------------------------------


class TestCIMdFormat:
    def test_frontmatter_present(self, tmp_workspace: Path):
        ticket_dir = _make_ticket_dir(tmp_workspace, "PROJ-500", "fm-check")
        _write_pr_md(ticket_dir, "\n".join([
            "## #1 Test PR",
            "",
            "- **CI**: passing",
        ]))

        CISync().sync(tmp_workspace)

        content = (ticket_dir / "orchestrator" / "CI.md").read_text()
        meta, body = parse_frontmatter(content)

        assert meta["source"] == "sync"
        assert "syncedAt" in meta

    def test_heading_structure(self, tmp_workspace: Path):
        ticket_dir = _make_ticket_dir(tmp_workspace, "PROJ-600", "heading-check")
        _write_pr_md(ticket_dir, "\n".join([
            "## #7 Feature branch",
            "",
            "- **CI**: pending",
        ]))

        CISync().sync(tmp_workspace)

        content = (ticket_dir / "orchestrator" / "CI.md").read_text()
        assert "# CI Status" in content
        assert "## 7 Feature branch" in content
        assert "- **Status**: pending" in content

    def test_duration_is_positive(self, tmp_workspace: Path):
        _make_ticket_dir(tmp_workspace, "PROJ-700", "duration")

        result = CISync().sync(tmp_workspace)
        assert result.duration_seconds >= 0
