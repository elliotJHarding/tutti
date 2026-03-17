"""tutti workspace -- manage ticket workspaces."""

from __future__ import annotations

import subprocess
from pathlib import Path

import click

from tutti.cli.output import error, output, success, table
from tutti.config import ConfigError, find_workspace_root, load_config
from tutti.workspace import ensure_ticket_dir, enumerate_ticket_dirs, resolve_ticket_dir


def _resolve_root(ctx: click.Context) -> Path:
    root = ctx.obj.get("workspace_root") if ctx.obj else None
    if root:
        return Path(root).resolve()
    return find_workspace_root()


@click.group()
@click.pass_context
def workspace(ctx: click.Context) -> None:
    """Manage ticket workspaces."""
    pass


@workspace.command("create")
@click.argument("key")
@click.option("--summary", default="", help="Ticket summary for directory name.")
@click.option("--epic", default=None, help="Epic key to nest under.")
@click.option("--epic-summary", default=None, help="Epic summary for directory name.")
@click.pass_context
def workspace_create(
    ctx: click.Context,
    key: str,
    summary: str,
    epic: str | None,
    epic_summary: str | None,
) -> None:
    """Create a workspace for a ticket."""
    try:
        root = _resolve_root(ctx)
    except ConfigError as exc:
        error(str(exc))
        ctx.exit(1)
        return

    ticket_dir = ensure_ticket_dir(
        root, key, summary or key, epic_key=epic, epic_summary=epic_summary
    )
    success(f"Workspace created at {ticket_dir}")


@workspace.command("add-repo")
@click.argument("key")
@click.argument("repo_name")
@click.option("--branch", default=None, help="Branch name for worktree.")
@click.pass_context
def workspace_add_repo(
    ctx: click.Context, key: str, repo_name: str, branch: str | None
) -> None:
    """Add a repo worktree to a ticket workspace."""
    try:
        root = _resolve_root(ctx)
        cfg = load_config(root)
    except ConfigError as exc:
        error(str(exc))
        ctx.exit(1)
        return

    ticket_dir = resolve_ticket_dir(root, key)
    if not ticket_dir:
        error(f"No workspace found for {key}. Run 'tutti workspace create {key}' first.")
        ctx.exit(1)
        return

    # Search for repo in configured repo_paths
    repo_path = None
    for search_path in cfg.repo_paths:
        candidate = search_path / repo_name
        if candidate.is_dir() and (candidate / ".git").exists():
            repo_path = candidate
            break

    if not repo_path:
        error(
            f"Repository '{repo_name}' not found in configured repoPaths: "
            f"{[str(p) for p in cfg.repo_paths]}"
        )
        ctx.exit(1)
        return

    # Create worktree
    worktree_path = ticket_dir / repo_name
    branch_name = branch or f"{key.lower()}"

    try:
        result = subprocess.run(
            ["git", "worktree", "add", str(worktree_path), "-b", branch_name],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            # Try without -b (branch may already exist)
            result = subprocess.run(
                ["git", "worktree", "add", str(worktree_path), branch_name],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                error(f"Failed to create worktree: {result.stderr}")
                ctx.exit(1)
                return

        success(f"Added worktree for {repo_name} at {worktree_path} (branch: {branch_name})")
    except Exception as exc:
        error(f"Failed to create worktree: {exc}")
        ctx.exit(1)


@workspace.command("status")
@click.pass_context
def workspace_status(ctx: click.Context) -> None:
    """Show workspace health across all tickets."""
    try:
        root = _resolve_root(ctx)
    except ConfigError as exc:
        error(str(exc))
        ctx.exit(1)
        return

    tickets = enumerate_ticket_dirs(root)
    if not tickets:
        output("No tickets found in workspace.")
        return

    rows = []
    data_list = []
    for key, path in tickets:
        orch = path / "orchestrator"
        artifacts = []
        if orch.is_dir():
            artifacts = [f.name for f in sorted(orch.iterdir()) if f.is_file()]

        repos = [
            d.name
            for d in sorted(path.iterdir())
            if d.is_dir() and d.name != "orchestrator" and (d / ".git").exists()
        ]

        rows.append([key, str(len(artifacts)), str(len(repos)), str(path)])
        data_list.append({
            "key": key,
            "artifacts": artifacts,
            "repos": repos,
            "path": str(path),
        })

    table("Workspace Status", ["Key", "Artifacts", "Repos", "Path"], rows, data=data_list)
