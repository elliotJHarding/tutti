"""tutti orchestrate — launch an orchestrator Claude Code session."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import click

from tutti.cli.output import error, output, spinner, success
from tutti.cli.resolve import complete_ticket_key, resolve_root
from tutti.config import ConfigError, TrustConfig, load_config


def _build_allowed_tools(trust: TrustConfig) -> list[str]:
    """Derive the --allowedTools list from the trust configuration."""
    # Base tools: always available (read-only filesystem access + writing artifacts).
    tools = ["Read", "Glob", "Grep", "Write", "Edit"]

    # If any action that requires shell access is auto or propose, add Bash.
    shell_actions = [
        trust.git_commit,
        trust.git_push,
        trust.pr_create,
        trust.pr_merge,
    ]
    if any(level in ("auto", "propose") for level in shell_actions):
        tools.append("Bash")

    return tools


def _trust_instructions(trust: TrustConfig) -> str:
    """Generate trust-level instructions for the orchestrator prompt."""
    lines: list[str] = []
    lines.append("## Trust Levels")
    lines.append("")
    lines.append("Your autonomy is governed by these trust settings:")
    lines.append("")

    actions = [
        ("Write artifacts", trust.write_artifact),
        ("Git commit", trust.git_commit),
        ("Git push", trust.git_push),
        ("Jira comments", trust.jira_comment),
        ("Jira transitions", trust.jira_transition),
        ("PR creation", trust.pr_create),
        ("PR merge", trust.pr_merge),
        ("Time logging", trust.time_log),
    ]

    for label, level in actions:
        if level == "auto":
            lines.append(f"- {label}: you may execute freely")
        elif level == "propose":
            lines.append(f"- {label}: propose the action and explain why, but do not execute")
        else:
            lines.append(f"- {label}: do not attempt this action")

    return "\n".join(lines)


def _build_prompt(ticket_key: str | None, root: Path, trust: TrustConfig) -> str:
    """Build the -p prompt for the orchestrator session."""
    parts: list[str] = []

    parts.append(
        "You are the tutti orchestrator. Your job is to review the state of "
        "active work in this workspace and take action to keep it moving."
    )
    parts.append("")
    parts.append("Start by reading PRIORITY.md to understand current focus, then "
                 "scan ticket directories to discover active work. For each ticket, "
                 "read the orchestrator/ directory to understand its state — sync "
                 "snapshots (TICKET.md, PULL_REQUESTS.md, CI.md, CLAUDE_SESSIONS.md, "
                 "WORKSPACE.md) and authored artifacts (BACKGROUND.md, AC.md, SPEC.md, "
                 "ORCHESTRATOR.md, etc.).")
    parts.append("")
    parts.append("See WORKFLOW.md for development lifecycle guidance.")

    parts.append("")
    parts.append(_trust_instructions(trust))

    if ticket_key:
        parts.append("")
        parts.append(f"Focus this session on ticket {ticket_key}.")

    return "\n".join(parts)


@click.command()
@click.option("--ticket", "ticket_key", default=None, help="Focus on a specific ticket.", shell_complete=complete_ticket_key)
@click.option("--dry-run", is_flag=True, help="Print the command without executing.")
@click.option("--sync", "pre_sync", is_flag=True, help="Run sync before launching orchestrator.")
@click.pass_context
def orchestrate(ctx: click.Context, ticket_key: str | None, dry_run: bool, pre_sync: bool) -> None:
    """Launch an orchestrator Claude Code session."""
    try:
        root = resolve_root(ctx)
        cfg = load_config(root)
    except ConfigError as exc:
        error(str(exc))
        ctx.exit(1)
        return

    # Optional pre-flight sync
    if pre_sync:
        from tutti.cli.sync_cmd import _build_all_sources, _report_result
        from tutti.sync.base import SyncCoordinator

        intervals = {
            "jira": cfg.sync_intervals.jira,
            "github": cfg.sync_intervals.github,
            "sessions": cfg.sync_intervals.sessions,
            "workspace": cfg.sync_intervals.workspace,
            "ci": cfg.sync_intervals.ci,
        }
        coordinator = SyncCoordinator(root, intervals)
        sources, skipped = _build_all_sources(cfg)

        with spinner("Pre-flight sync..."):
            results = coordinator.run(sources, force=False)

        if results:
            for r in results:
                _report_result(r)
        else:
            output("All sources up to date.")

    # Verify claude is available.
    claude_bin = shutil.which("claude")
    if not claude_bin:
        error("'claude' CLI not found on PATH. Install Claude Code first.")
        ctx.exit(1)
        return

    allowed_tools = _build_allowed_tools(cfg.trust)
    prompt = _build_prompt(ticket_key, root, cfg.trust)

    cmd = [
        claude_bin,
        "--add-dir", str(root),
        "-p", prompt,
        "--allowedTools", ",".join(allowed_tools),
    ]

    if dry_run:
        output(" ".join(cmd), data={"command": cmd})
        return

    success(f"Launching orchestrator session (tools: {', '.join(allowed_tools)})")

    try:
        subprocess.run(cmd, check=False)
    except KeyboardInterrupt:
        output("Orchestrator session interrupted.")
    except Exception as exc:
        error(f"Failed to launch orchestrator: {exc}")
        ctx.exit(1)
