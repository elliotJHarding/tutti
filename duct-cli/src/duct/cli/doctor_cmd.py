"""duct doctor — validate the full prerequisite chain."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from pathlib import Path

import click

from duct.cli.output import error, get_json_mode, output, section, success, warn
from duct.cli.resolve import resolve_root


def _check(label: str, ok: bool, detail: str = "") -> bool:
    """Print a pass/fail check and return the result."""
    if ok:
        output(f"  [green]OK[/green]  {label}" + (f" ({detail})" if detail else ""))
    else:
        output(f"  [red]FAIL[/red]  {label}" + (f" -- {detail}" if detail else ""))
    return ok


def _suggest(label: str, fix_cmd: str, apply_fn: Callable[[], None] | None = None) -> bool:
    """Suggest a fix for a failed check. Returns True if fix was applied."""
    if get_json_mode():
        output("", data={"suggestion": label, "fix": fix_cmd})
        return False
    output(f"  [yellow]FIX[/yellow]  {label}")
    output(f"         [dim]{fix_cmd}[/dim]")
    if apply_fn and click.confirm("         Apply this fix?", default=False):
        apply_fn()
        output(f"  [green]OK[/green]  {label} (applied)")
        return True
    return False


@click.command()
@click.pass_context
def doctor(ctx: click.Context) -> None:
    """Validate workspace configuration, credentials, and prerequisites."""
    all_ok = True

    # 1. Workspace root
    section("Workspace")
    try:
        root = resolve_root(ctx)
        all_ok &= _check("config.yaml found", True, str(root / "config.yaml"))
    except Exception as exc:
        _check("config.yaml found", False, str(exc))
        error("Cannot continue without a workspace. Run 'duct init' first.")
        ctx.exit(1)
        return

    # 2. Config parsing
    try:
        from duct.config import load_config
        cfg = load_config(root)
        all_ok &= _check("config.yaml parses", True)
    except Exception as exc:
        _check("config.yaml parses", False, str(exc))
        all_ok = False
        cfg = None

    # 3. Required config fields
    if cfg:
        all_ok &= _check("jira.domain set", bool(cfg.jira_domain), cfg.jira_domain or "empty")
        jql_detail = cfg.jira_jql[:60] if cfg.jira_jql else "empty"
        all_ok &= _check("jira.jql set", bool(cfg.jira_jql), jql_detail)

    # 4. Workspace files
    all_ok &= _check("PRIORITY.md exists", (root / "PRIORITY.md").exists())
    all_ok &= _check("WORKFLOW.md exists", (root / "WORKFLOW.md").exists())

    # 5. Environment variables / auth
    section("Authentication")

    jira_email = os.environ.get("JIRA_EMAIL", "")
    all_ok &= _check("JIRA_EMAIL set", bool(jira_email), jira_email if jira_email else "not set")

    jira_token = os.environ.get("JIRA_TOKEN", "")
    all_ok &= _check("JIRA_TOKEN set", bool(jira_token), "***" if jira_token else "not set")

    # GitHub token (check env vars + gh CLI)
    gh_token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if gh_token:
        all_ok &= _check("GitHub token", True, "from environment")
    elif shutil.which("gh"):
        import subprocess
        try:
            result = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                all_ok &= _check("GitHub token", True, "from gh auth")
            else:
                _check("GitHub token", False, "gh auth not logged in")
                all_ok = False
        except Exception:
            _check("GitHub token", False, "gh auth check failed")
            all_ok = False
    else:
        _check("GitHub token", False, "no GH_TOKEN, GITHUB_TOKEN, or gh CLI")
        all_ok = False

    # 6. API reachability
    section("API Reachability")

    if cfg and cfg.jira_domain and jira_email and jira_token:
        try:
            import base64

            import httpx
            credentials = base64.b64encode(f"{jira_email}:{jira_token}".encode()).decode()
            response = httpx.get(
                f"https://{cfg.jira_domain}/rest/api/3/myself",
                headers={"Authorization": f"Basic {credentials}", "Accept": "application/json"},
                timeout=10,
            )
            if response.status_code == 200:
                user = response.json().get("displayName", "unknown")
                all_ok &= _check("Jira API reachable", True, f"authenticated as {user}")
            else:
                _check("Jira API reachable", False, f"HTTP {response.status_code}")
                all_ok = False
        except Exception as exc:
            _check("Jira API reachable", False, str(exc))
            all_ok = False
    else:
        _check("Jira API reachable", False, "missing domain or credentials")
        all_ok = False

    if gh_token or shutil.which("gh"):
        try:
            import httpx
            token = gh_token
            if not token:
                import subprocess
                result = subprocess.run(
                    ["gh", "auth", "token"],
                    capture_output=True, text=True, timeout=5,
                )
                token = result.stdout.strip()
            response = httpx.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                timeout=10,
            )
            if response.status_code == 200:
                user = response.json().get("login", "unknown")
                all_ok &= _check("GitHub API reachable", True, f"authenticated as {user}")
            else:
                _check("GitHub API reachable", False, f"HTTP {response.status_code}")
                all_ok = False
        except Exception as exc:
            _check("GitHub API reachable", False, str(exc))
            all_ok = False
    else:
        _check("GitHub API reachable", False, "no token available")
        all_ok = False

    # 7. Tools on PATH
    section("Tools")

    all_ok &= _check("claude CLI on PATH", bool(shutil.which("claude")))
    all_ok &= _check("git on PATH", bool(shutil.which("git")))
    _check("gh CLI on PATH", bool(shutil.which("gh")))  # not fatal

    # 8. Repo paths
    if cfg:
        section("Repo Paths")
        for rp in cfg.repo_paths:
            all_ok &= _check(f"{rp}", rp.is_dir(), "exists" if rp.is_dir() else "not found")

    # 9. Shell completion
    section("Shell Integration")

    shell = os.environ.get("SHELL", "")
    if "zsh" in shell:
        shell_name, rc_path = "zsh", Path.home() / ".zshrc"
        activation = 'autoload -Uz compinit && compinit -C 2>/dev/null; eval "$(_DUCT_COMPLETE=zsh_source duct)"'
    elif "bash" in shell:
        shell_name, rc_path = "bash", Path.home() / ".bashrc"
        activation = 'eval "$(_DUCT_COMPLETE=bash_source duct)"'
    elif "fish" in shell:
        shell_name, rc_path = "fish", Path.home() / ".config" / "fish" / "config.fish"
        activation = '_DUCT_COMPLETE=fish_source duct | source'
    else:
        shell_name, rc_path, activation = None, None, None

    if shell_name and rc_path:
        rc_content = rc_path.read_text() if rc_path.exists() else ""
        has_completion = "_DUCT_COMPLETE" in rc_content
        all_ok &= _check(f"shell completion ({shell_name})", has_completion)
        if not has_completion:
            def apply_fix(path=rc_path, line=activation):
                with open(path, "a") as f:
                    f.write(f"\n{line}\n")
            _suggest(
                f"Add tab completion to {rc_path.name}",
                f"echo '{activation}' >> {rc_path}",
                apply_fn=apply_fix,
            )
    else:
        _check("shell completion", False, "unknown shell")
        all_ok = False

    # Summary
    output("")
    if all_ok:
        success("All checks passed.")
    else:
        warn("Some checks failed. Fix the issues above and re-run 'duct doctor'.")
        ctx.exit(1)
