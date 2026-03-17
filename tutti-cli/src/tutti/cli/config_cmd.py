"""tutti config — view or edit workspace configuration."""

from __future__ import annotations

from pathlib import Path

import click
import yaml

from tutti.cli.output import error, output
from tutti.config import ConfigError, find_workspace_root, load_config


def _resolve_root(ctx: click.Context) -> Path:
    root = ctx.obj.get("workspace_root") if ctx.obj else None
    if root:
        return Path(root).resolve()
    return find_workspace_root()


@click.group(invoke_without_command=True)
@click.pass_context
def config(ctx: click.Context) -> None:
    """View or edit workspace configuration."""
    if ctx.invoked_subcommand is not None:
        return

    try:
        root = _resolve_root(ctx)
        cfg = load_config(root)
    except ConfigError as exc:
        error(str(exc))
        ctx.exit(1)
        return

    # Display current config
    data = {
        "root": str(cfg.root),
        "jira_domain": cfg.jira_domain,
        "jira_jql": cfg.jira_jql,
        "repo_paths": [str(p) for p in cfg.repo_paths],
    }

    json_mode = ctx.obj.get("json", False) if ctx.obj else False
    if json_mode:
        import json
        import sys

        json.dump(data, sys.stdout)
        sys.stdout.write("\n")
    else:
        output(yaml.dump(data, default_flow_style=False, sort_keys=False))


@config.command("set")
@click.argument("key")
@click.argument("value")
@click.pass_context
def config_set(ctx: click.Context, key: str, value: str) -> None:
    """Set a configuration value."""
    output("Not yet implemented.")
