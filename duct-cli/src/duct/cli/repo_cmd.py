"""duct repo — manage git worktrees in a ticket workspace."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import click

from duct.cli.output import error, output, success, warn
from duct.cli.resolve import resolve_root, resolve_ticket_key, workspace_option
from duct.cli.workspace_cmd import _fuzzy_select, discover_repos, find_repo, list_branches
from duct.config import ConfigError, load_config
from duct.models import RepoEntry
from duct.workspace import load_workspace, resolve_ticket_dir, save_workspace


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(cmd: list[str], cwd: Path, check: bool = False) -> tuple[int, str, str]:
    """Run a subprocess and return (returncode, stdout, stderr)."""
    result = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=30,
    )
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
    return result.returncode, result.stdout, result.stderr


def _branch_exists_local(repo_path: Path, branch: str) -> bool:
    rc, _, _ = _run(["git", "rev-parse", "--verify", branch], repo_path)
    return rc == 0


def _branch_exists_remote(repo_path: Path, branch: str) -> bool:
    rc, out, _ = _run(["git", "ls-remote", "--heads", "origin", branch], repo_path)
    return rc == 0 and bool(out.strip())


def _get_default_remote_branch(repo_path: Path) -> str:
    rc, out, _ = _run(["git", "remote", "show", "origin"], repo_path)
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("HEAD branch:"):
            return line.split(":", 1)[1].strip()
    return "main"


def _require_workspace(ctx: click.Context, workspace_key: str | None) -> tuple[Path, Path, str]:
    """Resolve root, ticket_dir, and key — exit on failure."""
    try:
        root = resolve_root(ctx)
    except ConfigError as exc:
        error(str(exc))
        ctx.exit(1)
        raise SystemExit(1)

    key = resolve_ticket_key(ctx, workspace_key)
    if not key:
        error("No workspace specified. Provide --workspace KEY or run from a workspace directory.")
        ctx.exit(1)
        raise SystemExit(1)

    ticket_dir = resolve_ticket_dir(root, key)
    if not ticket_dir:
        error(f"No workspace found for {key}. Run 'duct sync' or 'duct workspace new {key}' first.")
        ctx.exit(1)
        raise SystemExit(1)

    return root, ticket_dir, key


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------


@click.group()
@click.pass_context
def repo(ctx: click.Context) -> None:
    """Manage git worktrees in a ticket workspace."""
    pass


# ---------------------------------------------------------------------------
# repo add
# ---------------------------------------------------------------------------


@repo.command("add")
@click.argument("repo_name", required=False)
@click.argument("basebranch", required=False)
@click.option("--branch", "-b", default=None, help="Override branch name.")
@workspace_option()
@click.pass_context
def repo_add(
    ctx: click.Context,
    repo_name: str | None,
    basebranch: str | None,
    branch: str | None,
    workspace_key: str | None,
) -> None:
    """Add a git worktree to the workspace."""
    try:
        root = resolve_root(ctx)
        cfg = load_config(root)
    except ConfigError as exc:
        error(str(exc))
        ctx.exit(1)
        return

    key = resolve_ticket_key(ctx, workspace_key)
    if not key:
        error("No workspace specified. Provide --workspace KEY or run from a workspace directory.")
        ctx.exit(1)
        return

    ticket_dir = resolve_ticket_dir(root, key)
    if not ticket_dir:
        error(f"No workspace found for {key}. Run 'duct sync' or 'duct workspace new {key}' first.")
        ctx.exit(1)
        return

    # Resolve repo interactively if missing
    repos = discover_repos(cfg)
    repo_names = [name for name, _ in repos]

    if not repo_name:
        if not repos:
            error("No git repositories found in configured repoPaths.")
            ctx.exit(1)
            return
        repo_name = _fuzzy_select("Repository", repo_names)
        if not repo_name:
            ctx.exit(1)
            return

    repo_path = find_repo(cfg, repo_name)
    if not repo_path:
        msg = f"Repository '{repo_name}' not found."
        if repo_names:
            msg += f"\nAvailable repos: {', '.join(repo_names)}"
        error(msg)
        ctx.exit(1)
        return

    # Resolve base branch interactively if missing
    if not basebranch:
        branches = list_branches(repo_path)
        if not branches:
            error(f"No branches found in {repo_path}.")
            ctx.exit(1)
            return
        basebranch = _fuzzy_select("Base branch", branches)
        if not basebranch:
            ctx.exit(1)
            return

    # Determine feature branch
    if branch:
        feature_branch = branch
    else:
        from duct.workspace import branch_name, read_issue_type
        summary_slug = ticket_dir.name[len(key) + 1:]
        issue_type = read_issue_type(ticket_dir)
        feature_branch = branch_name(key, summary_slug, issue_type)

    worktree_path = ticket_dir / repo_name

    # Create worktree
    rc, _, stderr = _run(
        ["git", "worktree", "add", str(worktree_path), "-b", feature_branch, basebranch, "--no-track"],
        repo_path,
    )
    if rc != 0:
        # Branch may already exist — try without -b
        rc, _, stderr = _run(
            ["git", "worktree", "add", str(worktree_path), feature_branch],
            repo_path,
        )
        if rc != 0:
            error(f"Failed to create worktree: {stderr}")
            ctx.exit(1)
            return

    if cfg.sandbox.enabled:
        from duct.sandbox import write_settings
        write_settings(worktree_path, cfg.sandbox)

    # Persist to workspace.json
    try:
        rc2, out, _ = _run(["git", "remote", "get-url", "origin"], repo_path)
        origin_url = out.strip() if rc2 == 0 else ""
    except Exception:
        origin_url = ""

    try:
        ws = load_workspace(ticket_dir)
        if repo_name not in {r.name for r in ws.repos}:
            ws.repos.append(RepoEntry(
                name=repo_name,
                origin=origin_url,
                branch=feature_branch,
                base_branch=basebranch,
            ))
            save_workspace(ws)
    except Exception:
        pass

    success(
        f"Added worktree for {repo_name} at {worktree_path} "
        f"(branch: {feature_branch} from {basebranch})"
    )


# ---------------------------------------------------------------------------
# repo list
# ---------------------------------------------------------------------------


@repo.command("list")
@workspace_option()
@click.pass_context
def repo_list(ctx: click.Context, workspace_key: str | None) -> None:
    """List repos in the current workspace."""
    try:
        root = resolve_root(ctx)
    except ConfigError as exc:
        error(str(exc))
        ctx.exit(1)
        return

    key = resolve_ticket_key(ctx, workspace_key)
    if not key:
        error("No workspace specified. Provide --workspace KEY or run from a workspace directory.")
        ctx.exit(1)
        return

    ticket_dir = resolve_ticket_dir(root, key)
    if not ticket_dir:
        error(f"No workspace found for {key}.")
        ctx.exit(1)
        return

    ws = load_workspace(ticket_dir)

    output(f"\n[bold]{ws.ticket_key}[/bold] repos:\n")
    if not ws.repos:
        output("  [dim]No repos added yet. Run: duct repo add[/dim]")
        return

    for r in ws.repos:
        wt_path = ticket_dir / r.name
        if not wt_path.exists():
            status_str = "[dim]missing[/dim]"
        else:
            rc, out, _ = _run(["git", "status", "--porcelain"], wt_path)
            changed = [line for line in out.strip().splitlines() if line.strip()]
            if not changed:
                status_str = "[green]clean[/green]"
            else:
                status_str = f"[yellow]{len(changed)} changes[/yellow]"
        output(f"  [cyan]{r.name}[/cyan]   branch: {r.branch}   {status_str}")


# ---------------------------------------------------------------------------
# repo remove
# ---------------------------------------------------------------------------


@repo.command("remove")
@click.argument("repo_name")
@workspace_option()
@click.pass_context
def repo_remove(ctx: click.Context, repo_name: str, workspace_key: str | None) -> None:
    """Remove a worktree and unregister it from the workspace."""
    try:
        root = resolve_root(ctx)
    except ConfigError as exc:
        error(str(exc))
        ctx.exit(1)
        return

    key = resolve_ticket_key(ctx, workspace_key)
    if not key:
        error("No workspace specified. Provide --workspace KEY or run from a workspace directory.")
        ctx.exit(1)
        return

    ticket_dir = resolve_ticket_dir(root, key)
    if not ticket_dir:
        error(f"No workspace found for {key}.")
        ctx.exit(1)
        return

    ws = load_workspace(ticket_dir)
    if not any(r.name == repo_name for r in ws.repos):
        error(f"{repo_name!r} is not registered in workspace {key}.")
        ctx.exit(1)
        return

    if not click.confirm(f"Remove worktree {repo_name!r} from {key}?"):
        return

    worktree_path = ticket_dir / repo_name
    if worktree_path.exists():
        # Find the repo root to call git worktree remove from there
        rc, out, _ = _run(["git", "rev-parse", "--git-common-dir"], worktree_path)
        if rc == 0 and out.strip():
            repo_root = Path(out.strip()).parent
            _run(["git", "worktree", "remove", "--force", str(worktree_path)], repo_root)
        else:
            # Fallback: remove the directory directly
            import shutil as _shutil
            _shutil.rmtree(worktree_path, ignore_errors=True)

    ws.repos = [r for r in ws.repos if r.name != repo_name]
    save_workspace(ws)
    success(f"Removed {repo_name} from {key}")


# ---------------------------------------------------------------------------
# repo pr
# ---------------------------------------------------------------------------


@repo.command("pr")
@workspace_option()
@click.pass_context
def repo_pr(ctx: click.Context, workspace_key: str | None) -> None:
    """Commit, push, and raise a PR for all repos in this workspace.

    Uses Claude to write the commit message when available.
    """
    try:
        root = resolve_root(ctx)
    except ConfigError as exc:
        error(str(exc))
        ctx.exit(1)
        return

    key = resolve_ticket_key(ctx, workspace_key)
    if not key:
        error("No workspace specified. Provide --workspace KEY or run from a workspace directory.")
        ctx.exit(1)
        return

    ticket_dir = resolve_ticket_dir(root, key)
    if not ticket_dir:
        error(f"No workspace found for {key}.")
        ctx.exit(1)
        return

    ws = load_workspace(ticket_dir)
    if not ws.repos:
        error("No repos in this workspace. Run 'duct repo add' first.")
        ctx.exit(1)
        return

    for r in ws.repos:
        wt_path = ticket_dir / r.name
        if not wt_path.exists():
            warn(f"Worktree {r.name} not found, skipping.")
            continue

        output(f"\n[bold]{r.name}[/bold]")

        # Stage and commit if there are changes
        rc, out, _ = _run(["git", "status", "--porcelain"], wt_path)
        if out.strip():
            output(f"  [dim]Staging changes…[/dim]")
            _run(["git", "add", "-A"], wt_path)

            # Generate commit message with claude if available
            claude_bin = shutil.which("claude")
            if claude_bin:
                rc2, msg, _ = _run(
                    [
                        claude_bin, "-p",
                        "Write a concise git commit message (one line) for the staged changes. "
                        "Output only the commit message, nothing else.",
                        "--output-format", "text",
                    ],
                    wt_path,
                )
                commit_msg = msg.strip() if rc2 == 0 and msg.strip() else f"{key}: update"
            else:
                commit_msg = f"{key}: update"

            rc, _, stderr = _run(["git", "commit", "-m", commit_msg], wt_path)
            if rc != 0:
                error(f"  Commit failed: {stderr}")
                continue
            output(f"  [dim]Committed: {commit_msg}[/dim]")

        # Push
        output(f"  [dim]Pushing {r.branch}…[/dim]")
        rc, _, stderr = _run(["git", "push", "-u", "origin", r.branch], wt_path)
        if rc != 0:
            error(f"  Push failed: {stderr}")
            continue

        # Raise PR if gh is available
        gh_bin = shutil.which("gh")
        if gh_bin:
            rc, _, _ = _run(
                [gh_bin, "pr", "view", "--head", r.branch, "--json", "number"],
                wt_path,
            )
            if rc == 0:
                output(f"  [dim]PR already exists for {r.name}[/dim]")
            else:
                pr_title = f"{key}: {r.branch.split('/')[-1].replace('-', ' ')}"
                rc, _, stderr = _run(
                    [gh_bin, "pr", "create", "--title", pr_title, "--base", r.base_branch, "--fill"],
                    wt_path,
                )
                if rc == 0:
                    success(f"  PR raised for {r.name}")
                else:
                    error(f"  PR creation failed: {stderr}")
        else:
            warn("  gh CLI not found — cannot raise PR automatically.")
