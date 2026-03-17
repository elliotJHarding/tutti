"""tutti orchestrate — launch an orchestrator Claude Code session."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import click

from tutti.cli.output import error, output, success
from tutti.config import ConfigError, TrustConfig, find_workspace_root, load_config


def _resolve_root(ctx: click.Context) -> Path:
    root = ctx.obj.get("workspace_root") if ctx.obj else None
    if root:
        return Path(root).resolve()
    return find_workspace_root()


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


def _build_prompt(ticket_key: str | None, root: Path) -> str:
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

    if ticket_key:
        parts.append("")
        parts.append(f"Focus this session on ticket {ticket_key}.")

    return "\n".join(parts)


@click.command()
@click.option("--ticket", "ticket_key", default=None, help="Focus on a specific ticket.")
@click.option("--dry-run", is_flag=True, help="Print the command without executing.")
@click.pass_context
def orchestrate(ctx: click.Context, ticket_key: str | None, dry_run: bool) -> None:
    """Launch an orchestrator Claude Code session."""
    try:
        root = _resolve_root(ctx)
        cfg = load_config(root)
    except ConfigError as exc:
        error(str(exc))
        ctx.exit(1)
        return

    # Verify claude is available.
    claude_bin = shutil.which("claude")
    if not claude_bin:
        error("'claude' CLI not found on PATH. Install Claude Code first.")
        ctx.exit(1)
        return

    allowed_tools = _build_allowed_tools(cfg.trust)
    prompt = _build_prompt(ticket_key, root)

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
