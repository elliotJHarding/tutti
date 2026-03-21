"""CLI entry point for duct."""

import importlib

import click

COMMANDS = {
    "add-repo": "duct.cli.workspace_cmd:add_repo",
    "archive": "duct.cli.archive_cmd:archive",
    "config": "duct.cli.config_cmd:config",
    "doctor": "duct.cli.doctor_cmd:doctor",
    "init": "duct.cli.init_cmd:init",
    "orchestrate": "duct.cli.orchestrate_cmd:orchestrate",
    "session": "duct.cli.session_cmd:session",
    "status": "duct.cli.status_cmd:status",
    "sync": "duct.cli.sync_cmd:sync",
    "ticket": "duct.cli.ticket_cmd:ticket",
    "workspace": "duct.cli.workspace_cmd:workspace",
}

_COMPLETION_SCRIPTS = {
    "bash": 'eval "$(_DUCT_COMPLETE=bash_source duct)"',
    "zsh": 'eval "$(_DUCT_COMPLETE=zsh_source duct)"',
    "fish": '_DUCT_COMPLETE=fish_source duct | source',
}


@click.command()
@click.argument("shell", type=click.Choice(["bash", "zsh", "fish"]))
def completion(shell: str) -> None:
    """Print shell completion activation script.

    Add the output to your shell profile to enable tab completion:

        duct completion zsh >> ~/.zshrc
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
    """duct — Developer workflow orchestration."""
    ctx.ensure_object(dict)
    ctx.obj["json"] = json_output
    ctx.obj["debug"] = debug
    ctx.obj["workspace_root"] = workspace_root
