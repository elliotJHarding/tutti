"""CI status sync source (stub) for duct."""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from pathlib import Path

from duct.markdown import atomic_write, generate_frontmatter, parse_frontmatter
from duct.models import SyncResult
from duct.workspace import enumerate_ticket_dirs, orchestrator_dir


class CISync:
    """Stub sync source for CI/build status.

    Extracts CI information from per-PR markdown files in orchestrator/prs/.
    Future: direct GitHub Actions API integration.
    """

    name = "ci"

    def sync(self, root: Path, ticket_key: str | None = None) -> SyncResult:
        start = time.time()
        errors: list[str] = []
        synced = 0

        for key, ticket_dir in enumerate_ticket_dirs(root):
            if ticket_key and key != ticket_key:
                continue
            orch = orchestrator_dir(ticket_dir)
            prs_dir = orch / "prs"

            if not prs_dir.is_dir():
                continue

            pr_files = sorted(prs_dir.glob("PR-*.md"))
            if not pr_files:
                continue

            try:
                ci_info = []
                for pr_file in pr_files:
                    entry = self._extract_ci_from_pr_file(pr_file)
                    if entry:
                        ci_info.append(entry)
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

    def _extract_ci_from_pr_file(self, pr_file: Path) -> dict | None:
        """Extract PR title and CI status from a single PR markdown file."""
        content = pr_file.read_text()
        _, body = parse_frontmatter(content)

        pr_title = ""
        ci_status = ""
        for line in body.splitlines():
            m = re.match(r"^# PR #(\d+): (.+)$", line)
            if m:
                pr_title = f"#{m.group(1)} {m.group(2)}"
            m2 = re.match(r"^\*\*CI:\*\* (.+)$", line)
            if m2:
                ci_status = m2.group(1).strip()

        if not ci_status:
            return None
        return {"pr": pr_title, "status": ci_status}

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
