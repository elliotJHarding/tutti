"""CLI entry point for tutti."""

import click

from tutti.cli.archive_cmd import archive
from tutti.cli.config_cmd import config
from tutti.cli.init_cmd import init
from tutti.cli.orchestrate_cmd import orchestrate
from tutti.cli.priority_cmd import priority
from tutti.cli.sync_cmd import sync
from tutti.cli.ticket_cmd import ticket
from tutti.cli.workspace_cmd import workspace


@click.group()
@click.option("--json", "json_output", is_flag=True, help="Output as JSON.")
@click.option(
    "--workspace-root",
    type=click.Path(),
    default=None,
    help="Override workspace root directory.",
)
@click.pass_context
def cli(ctx: click.Context, json_output: bool, workspace_root: str | None) -> None:
    """tutti — Developer workflow orchestration."""
    ctx.ensure_object(dict)
    ctx.obj["json"] = json_output
    ctx.obj["workspace_root"] = workspace_root


cli.add_command(init)
cli.add_command(sync)
cli.add_command(config)
cli.add_command(ticket)
cli.add_command(archive)
cli.add_command(workspace)
cli.add_command(priority)
cli.add_command(orchestrate)
