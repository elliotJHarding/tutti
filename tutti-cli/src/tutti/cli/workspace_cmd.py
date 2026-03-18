"""tutti workspace -- manage ticket workspaces."""

from __future__ import annotations

import subprocess
from pathlib import Path

import click

from tutti.cli.output import Col, error, output, success, table
from tutti.cli.resolve import complete_ticket_key, resolve_root
from tutti.config import ConfigError, load_config
from tutti.workspace import enumerate_ticket_dirs, resolve_ticket_dir


@click.group()
@click.pass_context
def workspace(ctx: click.Context) -> None:
    """Manage ticket workspaces."""
    pass


@workspace.command("add-repo")
@click.argument("key", shell_complete=complete_ticket_key)
@click.argument("repo_name")
@click.option("--branch", default=None, help="Branch name for worktree.")
@click.pass_context
def workspace_add_repo(
    ctx: click.Context, key: str, repo_name: str, branch: str | None
) -> None:
    """Add a repo worktree to a ticket workspace."""
    try:
        root = resolve_root(ctx)
        cfg = load_config(root)
    except ConfigError as exc:
        error(str(exc))
        ctx.exit(1)
        return

    ticket_dir = resolve_ticket_dir(root, key)
    if not ticket_dir:
        error(f"No workspace found for {key}. Run 'tutti sync --force' to create ticket directories.")
        ctx.exit(1)
        return

    # Search for repo in configured repo_paths
    repo_path = None
    available_repos: list[str] = []
    for search_path in cfg.repo_paths:
        if not search_path.is_dir():
            continue
        candidate = search_path / repo_name
        if candidate.is_dir() and (candidate / ".git").exists():
            repo_path = candidate
            break
        # Collect available repos for error message
        for child in search_path.iterdir():
            if child.is_dir() and (child / ".git").exists():
                available_repos.append(child.name)

    if not repo_path:
        msg = f"Repository '{repo_name}' not found in configured repoPaths."
        if available_repos:
            msg += f" Available repos: {', '.join(sorted(set(available_repos)))}"
        error(msg)
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
        root = resolve_root(ctx)
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

    columns: list[str | Col] = [
        "Key",
        Col("Artifacts", justify="right"),
        Col("Repos", justify="right"),
        Col("Path", max_width=50),
    ]
    table("Workspace Status", columns, rows, data=data_list)


@workspace.command("path")
@click.argument("key", shell_complete=complete_ticket_key)
@click.pass_context
def workspace_path(ctx: click.Context, key: str) -> None:
    """Print the workspace path for a ticket. Useful for shell integration:
    cd $(tutti workspace path KEY)
    """
    try:
        root = resolve_root(ctx)
    except ConfigError as exc:
        error(str(exc))
        ctx.exit(1)
        return

    ticket_dir = resolve_ticket_dir(root, key)
    if not ticket_dir:
        error(f"No workspace found for {key}.")
        ctx.exit(1)
        return

    # Print raw path (no formatting) for shell consumption
    if ctx.obj and ctx.obj.get("json"):
        output("", data={"key": key, "path": str(ticket_dir)})
    else:
        click.echo(str(ticket_dir))
