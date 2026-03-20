"""CI status sync source (stub) for duct."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

from duct.markdown import atomic_write, generate_frontmatter, parse_frontmatter
from duct.models import SyncResult
from duct.workspace import enumerate_ticket_dirs, orchestrator_dir


class CISync:
    """Stub sync source for CI/build status.

    Currently extracts CI information from PULL_REQUESTS.md if it exists.
    Future: direct GitHub Actions API integration.
    """

    name = "ci"

    def sync(self, root: Path) -> SyncResult:
        start = time.time()
        errors: list[str] = []
        synced = 0

        for key, ticket_dir in enumerate_ticket_dirs(root):
            orch = orchestrator_dir(ticket_dir)
            pr_md = orch / "PULL_REQUESTS.md"

            if not pr_md.exists():
                continue

            try:
                ci_info = self._extract_ci_from_prs(pr_md)
                if ci_info:
                    self._write_ci_md(ci_info, ticket_dir)
                    synced += 1
            except Exception as exc:
                errors.append(f"{key}: {exc}")

        return SyncResult(
            source=self.name,
            tickets_synced=synced,
            duration_seconds=time.time() - start,
            errors=errors,
        )

    def _extract_ci_from_prs(self, pr_md: Path) -> list[dict]:
        """Extract CI status lines from PULL_REQUESTS.md."""
        content = pr_md.read_text()
        _, body = parse_frontmatter(content)

        ci_entries: list[dict] = []
        current_pr = ""

        for line in body.splitlines():
            if line.startswith("## #"):
                current_pr = line.lstrip("# ").strip()
            elif line.startswith("- **CI**:"):
                status = line.split(":", 1)[1].strip()
                ci_entries.append({"pr": current_pr, "status": status})

        return ci_entries

    def _write_ci_md(self, ci_entries: list[dict], ticket_dir: Path) -> None:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        parts: list[str] = []

        parts.append(generate_frontmatter(source="sync", synced_at=now))
        parts.append("")
        parts.append("# CI Status")
        parts.append("")

        for entry in ci_entries:
            parts.append(f"## {entry['pr']}")
            parts.append("")
            parts.append(f"- **Status**: {entry['status']}")
            parts.append("")

        content = "\n".join(parts)
        orch = orchestrator_dir(ticket_dir)
        atomic_write(orch / "CI.md", content)
