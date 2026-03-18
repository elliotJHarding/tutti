"""CLI entry point for tutti."""

import importlib

import click

COMMANDS = {
    "archive": "tutti.cli.archive_cmd:archive",
    "config": "tutti.cli.config_cmd:config",
    "doctor": "tutti.cli.doctor_cmd:doctor",
    "init": "tutti.cli.init_cmd:init",
    "orchestrate": "tutti.cli.orchestrate_cmd:orchestrate",
    "priority": "tutti.cli.priority_cmd:priority",
    "session": "tutti.cli.session_cmd:session",
    "status": "tutti.cli.status_cmd:status",
    "sync": "tutti.cli.sync_cmd:sync",
    "ticket": "tutti.cli.ticket_cmd:ticket",
    "workspace": "tutti.cli.workspace_cmd:workspace",
}

_COMPLETION_SCRIPTS = {
    "bash": 'eval "$(_TUTTI_COMPLETE=bash_source tutti)"',
    "zsh": 'eval "$(_TUTTI_COMPLETE=zsh_source tutti)"',
    "fish": '_TUTTI_COMPLETE=fish_source tutti | source',
}


@click.command()
@click.argument("shell", type=click.Choice(["bash", "zsh", "fish"]))
def completion(shell: str) -> None:
    """Print shell completion activation script.

    Add the output to your shell profile to enable tab completion:

        tutti completion zsh >> ~/.zshrc
    """
    click.echo(_COMPLETION_SCRIPTS[shell])


class LazyGroup(click.Group):
    """A click.Group that defers command imports until they are needed.

    During tab completion, only list_commands() is called (returning plain
    strings), so none of the heavy command modules are imported. When an
    actual command is invoked, get_command() imports just that one module.
    """

    def list_commands(self, ctx):
        return sorted(COMMANDS.keys()) + ["completion"]

    def get_command(self, ctx, cmd_name):
        if cmd_name == "completion":
            return completion
        if cmd_name not in COMMANDS:
            return None
        module_path, attr = COMMANDS[cmd_name].rsplit(":", 1)
        mod = importlib.import_module(module_path)
        return getattr(mod, attr)


@click.group(cls=LazyGroup)
@click.option("--json", "json_output", is_flag=True, help="Output as JSON.")
@click.option("--debug", is_flag=True, help="Show debug information.")
@click.option(
    "--workspace-root",
    type=click.Path(),
    default=None,
    help="Override workspace root directory.",
)
@click.pass_context
def cli(ctx: click.Context, json_output: bool, debug: bool, workspace_root: str | None) -> None:
    """tutti — Developer workflow orchestration."""
    ctx.ensure_object(dict)
    ctx.obj["json"] = json_output
    ctx.obj["debug"] = debug
    ctx.obj["workspace_root"] = workspace_root
