"""tutti sync — run sync sources."""

from __future__ import annotations

from pathlib import Path

import click

from tutti.cli.output import error, output, success
from tutti.config import (
    AuthError,
    ConfigError,
    find_workspace_root,
    gh_token,
    jira_email,
    jira_token,
    load_config,
)
from tutti.sync.base import SyncCoordinator


def _resolve_root(ctx: click.Context) -> Path:
    """Determine workspace root from context or by walking up the filesystem."""
    root = ctx.obj.get("workspace_root") if ctx.obj else None
    if root:
        return Path(root).resolve()
    return find_workspace_root()


def _build_all_sources(cfg):
    """Build all available sync sources, skipping those with missing auth."""
    sources = []

    # Jira
    try:
        from tutti.sync.jira import JiraSync

        sources.append(JiraSync(
            domain=cfg.jira_domain,
            email=jira_email(),
            token=jira_token(),
            jql=cfg.jira_jql,
        ))
    except AuthError:
        pass

    # GitHub
    try:
        from tutti.sync.github import GitHubSync

        sources.append(GitHubSync(token=gh_token()))
    except AuthError:
        pass

    # CI (no auth required)
    from tutti.sync.ci import CISync
    sources.append(CISync())

    # Sessions (no auth required)
    from tutti.sync.sessions import SessionSync
    sources.append(SessionSync())

    # Workspace (no auth required)
    from tutti.sync.workspace_sync import WorkspaceSync
    sources.append(WorkspaceSync())

    return sources


def _report_results(results):
    """Print sync results."""
    if not results:
        output("No sync sources ran (all up to date or none configured).")
        return
    for r in results:
        if r.errors:
            error(f"{r.source}: {', '.join(r.errors)}")
        else:
            success(f"{r.source}: synced {r.tickets_synced} tickets in {r.duration_seconds:.1f}s")


@click.group(invoke_without_command=True)
@click.option("--force", is_flag=True, help="Bypass staleness checks.")
@click.pass_context
def sync(ctx: click.Context, force: bool) -> None:
    """Run sync sources. Without a subcommand, runs all sources."""
    ctx.ensure_object(dict)
    ctx.obj["force"] = force

    if ctx.invoked_subcommand is not None:
        return

    try:
        root = _resolve_root(ctx)
        cfg = load_config(root)
    except ConfigError as exc:
        error(str(exc))
        ctx.exit(1)
        return

    intervals = {
        "jira": cfg.sync_intervals.jira,
        "github": cfg.sync_intervals.github,
        "sessions": cfg.sync_intervals.sessions,
        "workspace": cfg.sync_intervals.workspace,
        "ci": cfg.sync_intervals.ci,
    }
    coordinator = SyncCoordinator(root, intervals)
    sources = _build_all_sources(cfg)
    results = coordinator.run(sources, force=force)
    _report_results(results)


def _run_single_source(ctx, source_factory):
    """Helper to run a single sync source."""
    force = ctx.obj.get("force", False)
    try:
        root = _resolve_root(ctx)
        cfg = load_config(root)
    except ConfigError as exc:
        error(str(exc))
        ctx.exit(1)
        return

    try:
        source = source_factory(cfg)
    except AuthError as exc:
        error(str(exc))
        ctx.exit(1)
        return

    coordinator = SyncCoordinator(root, {source.name: 0})
    results = coordinator.run([source], force=force)
    _report_results(results)


@sync.command("jira")
@click.pass_context
def sync_jira(ctx: click.Context) -> None:
    """Sync Jira tickets."""
    from tutti.sync.jira import JiraSync

    def factory(cfg):
        return JiraSync(
            domain=cfg.jira_domain,
            email=jira_email(),
            token=jira_token(),
            jql=cfg.jira_jql,
        )

    _run_single_source(ctx, factory)


@sync.command("github")
@click.pass_context
def sync_github(ctx: click.Context) -> None:
    """Sync GitHub pull requests."""
    from tutti.sync.github import GitHubSync

    def factory(cfg):
        return GitHubSync(token=gh_token())

    _run_single_source(ctx, factory)


@sync.command("ci")
@click.pass_context
def sync_ci(ctx: click.Context) -> None:
    """Sync CI/build status."""
    from tutti.sync.ci import CISync

    def factory(_cfg):
        return CISync()

    _run_single_source(ctx, factory)


@sync.command("sessions")
@click.pass_context
def sync_sessions(ctx: click.Context) -> None:
    """Sync Claude session data."""
    from tutti.sync.sessions import SessionSync

    def factory(_cfg):
        return SessionSync()

    _run_single_source(ctx, factory)


@sync.command("workspace")
@click.pass_context
def sync_workspace(ctx: click.Context) -> None:
    """Sync local workspace state."""
    from tutti.sync.workspace_sync import WorkspaceSync

    def factory(_cfg):
        return WorkspaceSync()

    _run_single_source(ctx, factory)
