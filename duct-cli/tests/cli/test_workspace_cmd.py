"""Tests for the duct workspace command."""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from duct.cli.main import cli
from duct.cli.workspace_cmd import discover_repos, find_repo, list_branches
from duct.config import WorkspaceConfig


def _init_workspace(runner: CliRunner, root: Path) -> None:
    """Run duct init to set up config.yaml in the workspace root."""
    runner.invoke(cli, ["--workspace-root", str(root), "init"])


def _create_ticket_dir(root: Path, key: str, slug: str = "") -> Path:
    """Manually create a ticket directory with orchestrator subdir."""
    dirname = f"{key}-{slug}" if slug else f"{key}-{key.lower()}"
    ticket_dir = root / dirname
    (ticket_dir / "orchestrator").mkdir(parents=True)
    return ticket_dir


def _create_repo(base: Path, name: str) -> Path:
    """Create a fake git repo directory."""
    repo = base / name
    repo.mkdir(parents=True, exist_ok=True)
    (repo / ".git").mkdir()
    return repo


# ---------------------------------------------------------------------------
# Repo discovery tests
# ---------------------------------------------------------------------------


def test_discover_repos_flat(tmp_path: Path) -> None:
    """discover_repos finds repos at the top level of repoPaths."""
    _create_repo(tmp_path, "ice-claims")
    _create_repo(tmp_path, "ice-gateway")

    cfg = WorkspaceConfig(repo_paths=[tmp_path])
    repos = discover_repos(cfg)

    names = [name for name, _ in repos]
    assert "ice-claims" in names
    assert "ice-gateway" in names


def test_discover_repos_nested(tmp_path: Path) -> None:
    """discover_repos finds repos nested under organizing directories."""
    _create_repo(tmp_path / "claims", "ice-claims")
    _create_repo(tmp_path / "esb", "ers-claims-feature")
    _create_repo(tmp_path / "contract", "ice-claims-model")

    cfg = WorkspaceConfig(repo_paths=[tmp_path])
    repos = discover_repos(cfg)

    names = [name for name, _ in repos]
    assert "ice-claims" in names
    assert "ers-claims-feature" in names
    assert "ice-claims-model" in names


def test_discover_repos_skips_dotdirs(tmp_path: Path) -> None:
    """discover_repos ignores directories starting with a dot."""
    _create_repo(tmp_path / ".hidden", "secret-repo")
    _create_repo(tmp_path, "visible-repo")

    cfg = WorkspaceConfig(repo_paths=[tmp_path])
    repos = discover_repos(cfg)

    names = [name for name, _ in repos]
    assert "visible-repo" in names
    assert "secret-repo" not in names


def test_discover_repos_skips_worktrees(tmp_path: Path) -> None:
    """discover_repos ignores worktrees (where .git is a file, not a directory)."""
    _create_repo(tmp_path, "real-repo")
    # Simulate a worktree: .git is a file pointing to the main repo
    worktree = tmp_path / "worktree-repo"
    worktree.mkdir()
    (worktree / ".git").write_text("gitdir: /some/path/to/.git/worktrees/wt")

    cfg = WorkspaceConfig(repo_paths=[tmp_path])
    repos = discover_repos(cfg)

    names = [name for name, _ in repos]
    assert "real-repo" in names
    assert "worktree-repo" not in names


def test_discover_repos_does_not_descend_into_repos(tmp_path: Path) -> None:
    """discover_repos stops descending once it finds a .git directory."""
    parent = _create_repo(tmp_path, "parent-repo")
    # Create a nested dir inside the repo — should not be found as a separate repo
    nested = parent / "packages" / "sub-repo"
    nested.mkdir(parents=True)
    (nested / ".git").mkdir()

    cfg = WorkspaceConfig(repo_paths=[tmp_path])
    repos = discover_repos(cfg)

    names = [name for name, _ in repos]
    assert "parent-repo" in names
    assert "sub-repo" not in names


def test_discover_repos_respects_max_depth(tmp_path: Path) -> None:
    """discover_repos does not scan past max_depth."""
    _create_repo(tmp_path / "a" / "b" / "c" / "d", "deep-repo")

    cfg = WorkspaceConfig(repo_paths=[tmp_path])

    shallow = discover_repos(cfg, max_depth=2)
    assert not any(name == "deep-repo" for name, _ in shallow)

    deep = discover_repos(cfg, max_depth=5)
    assert any(name == "deep-repo" for name, _ in deep)


def test_find_repo_found(tmp_path: Path) -> None:
    repo = _create_repo(tmp_path / "claims", "ice-claims")
    cfg = WorkspaceConfig(repo_paths=[tmp_path])

    result = find_repo(cfg, "ice-claims")
    assert result == repo


def test_find_repo_not_found(tmp_path: Path) -> None:
    cfg = WorkspaceConfig(repo_paths=[tmp_path])
    assert find_repo(cfg, "nonexistent") is None


# ---------------------------------------------------------------------------
# workspace status tests
# ---------------------------------------------------------------------------


def test_workspace_status_empty(tmp_path: Path) -> None:
    """workspace status with no tickets should report nothing found."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    result = runner.invoke(cli, ["--workspace-root", str(tmp_path), "workspace", "status"])

    assert result.exit_code == 0, result.output
    assert "No tickets found" in result.output


def test_workspace_status_shows_tickets(tmp_path: Path) -> None:
    """workspace status should list tickets found in the workspace."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    _create_ticket_dir(tmp_path, "PROJ-10")
    _create_ticket_dir(tmp_path, "PROJ-20")

    result = runner.invoke(cli, ["--workspace-root", str(tmp_path), "workspace", "status"])

    assert result.exit_code == 0, result.output
    assert "PROJ-10" in result.output
    assert "PROJ-20" in result.output


def test_workspace_status_json(tmp_path: Path) -> None:
    """workspace status --json should produce parseable JSON output."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    _create_ticket_dir(tmp_path, "PROJ-50")

    result = runner.invoke(
        cli, ["--json", "--workspace-root", str(tmp_path), "workspace", "status"]
    )

    assert result.exit_code == 0, result.output
    data = json.loads(result.output.strip())
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["key"] == "PROJ-50"


def test_workspace_path_found(tmp_path: Path) -> None:
    """workspace path KEY should print the ticket directory path."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    ticket_dir = _create_ticket_dir(tmp_path, "PROJ-99", "some-feature")

    result = runner.invoke(
        cli, ["--workspace-root", str(tmp_path), "workspace", "path", "PROJ-99"]
    )

    assert result.exit_code == 0, result.output
    assert str(ticket_dir) in result.output.strip()


def test_workspace_path_not_found(tmp_path: Path) -> None:
    """workspace path KEY should fail when no matching directory exists."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    result = runner.invoke(
        cli, ["--workspace-root", str(tmp_path), "workspace", "path", "NOPE-1"]
    )

    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# workspace priority tests
# ---------------------------------------------------------------------------


def _create_ticket_dir_with_workspace(root: Path, key: str, slug: str = "") -> Path:
    """Create a ticket directory with a minimal workspace.json."""
    dirname = f"{key}-{slug}" if slug else f"{key}-{key.lower()}"
    ticket_dir = root / dirname
    (ticket_dir / "orchestrator").mkdir(parents=True)
    duct_dir = ticket_dir / ".duct"
    duct_dir.mkdir()
    (duct_dir / "workspace.json").write_text(
        json.dumps({"ticket_key": key, "created_at": "2024-01-01T00:00:00Z"})
    )
    return ticket_dir


def test_workspace_priority_sets_value(tmp_path: Path) -> None:
    """workspace priority KEY VALUE should write priority to workspace.json."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)
    ticket_dir = _create_ticket_dir_with_workspace(tmp_path, "PROJ-10", "my-feature")

    result = runner.invoke(
        cli, ["--workspace-root", str(tmp_path), "workspace", "priority", "PROJ-10", "42"]
    )

    assert result.exit_code == 0, result.output
    assert "42" in result.output
    data = json.loads((ticket_dir / ".duct" / "workspace.json").read_text())
    assert data["priority"] == 42


def test_workspace_priority_updates_value(tmp_path: Path) -> None:
    """workspace priority should overwrite a previously set priority."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)
    ticket_dir = _create_ticket_dir_with_workspace(tmp_path, "PROJ-20", "another-feature")

    runner.invoke(cli, ["--workspace-root", str(tmp_path), "workspace", "priority", "PROJ-20", "5"])
    runner.invoke(cli, ["--workspace-root", str(tmp_path), "workspace", "priority", "PROJ-20", "99"])

    data = json.loads((ticket_dir / ".duct" / "workspace.json").read_text())
    assert data["priority"] == 99


def test_workspace_priority_not_found(tmp_path: Path) -> None:
    """workspace priority should fail when the ticket does not exist."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    result = runner.invoke(
        cli, ["--workspace-root", str(tmp_path), "workspace", "priority", "NOPE-1", "10"]
    )

    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# add-repo tests (non-interactive, all args provided)
# ---------------------------------------------------------------------------


def test_add_repo_top_level_all_args(tmp_path: Path) -> None:
    """duct add-repo KEY REPO BASEBRANCH should create a worktree (top-level command)."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    ticket_dir = _create_ticket_dir(tmp_path, "ERSC-100", "some-ticket")
    repo_dir = _create_repo(tmp_path / "repos", "my-repo")

    # Initialize a real git repo so worktree add works
    subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=repo_dir, capture_output=True)
    (repo_dir / "README.md").write_text("hello")
    subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo_dir, capture_output=True,
        env={"GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t",
             "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t",
             "PATH": "/usr/bin:/bin:/usr/local/bin"},
    )

    # Write config with repo_paths pointing to our repos dir
    import yaml
    config_path = tmp_path / "config.yaml"
    cfg_data = yaml.safe_load(config_path.read_text()) if config_path.exists() else {}
    cfg_data["repoPaths"] = [str(tmp_path / "repos")]
    config_path.write_text(yaml.dump(cfg_data))

    result = runner.invoke(
        cli,
        ["--workspace-root", str(tmp_path), "add-repo", "ERSC-100", "my-repo", "main"],
    )

    assert result.exit_code == 0, result.output
    assert "Added worktree" in result.output
    assert (ticket_dir / "my-repo").exists()


def test_add_repo_workspace_alias(tmp_path: Path) -> None:
    """duct workspace add-repo should still work as an alias."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    ticket_dir = _create_ticket_dir(tmp_path, "ERSC-200", "alias-test")
    repo_dir = _create_repo(tmp_path / "repos", "alias-repo")

    subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "develop"], cwd=repo_dir, capture_output=True)
    (repo_dir / "README.md").write_text("hello")
    subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo_dir, capture_output=True,
        env={"GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t",
             "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t",
             "PATH": "/usr/bin:/bin:/usr/local/bin"},
    )

    import yaml
    config_path = tmp_path / "config.yaml"
    cfg_data = yaml.safe_load(config_path.read_text()) if config_path.exists() else {}
    cfg_data["repoPaths"] = [str(tmp_path / "repos")]
    config_path.write_text(yaml.dump(cfg_data))

    result = runner.invoke(
        cli,
        [
            "--workspace-root", str(tmp_path),
            "workspace", "add-repo", "ERSC-200", "alias-repo", "develop",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Added worktree" in result.output


def test_add_repo_no_track(tmp_path: Path) -> None:
    """Created worktree branch should have no upstream tracking."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    ticket_dir = _create_ticket_dir(tmp_path, "ERSC-300", "no-track")
    repo_dir = _create_repo(tmp_path / "repos", "track-repo")

    subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=repo_dir, capture_output=True)
    (repo_dir / "README.md").write_text("hello")
    subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo_dir, capture_output=True,
        env={"GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t",
             "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t",
             "PATH": "/usr/bin:/bin:/usr/local/bin"},
    )

    import yaml
    config_path = tmp_path / "config.yaml"
    cfg_data = yaml.safe_load(config_path.read_text()) if config_path.exists() else {}
    cfg_data["repoPaths"] = [str(tmp_path / "repos")]
    config_path.write_text(yaml.dump(cfg_data))

    runner.invoke(
        cli,
        ["--workspace-root", str(tmp_path), "add-repo", "ERSC-300", "track-repo", "main"],
    )

    worktree_path = ticket_dir / "track-repo"
    # Check that the branch has no upstream
    check = subprocess.run(
        ["git", "config", "--get", "branch.ersc-300.remote"],
        cwd=worktree_path,
        capture_output=True,
        text=True,
    )
    assert check.returncode != 0, "Branch should have no upstream tracking"


def test_add_repo_repo_not_found(tmp_path: Path) -> None:
    """add-repo with a bad repo name should give a helpful error."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    _create_ticket_dir(tmp_path, "ERSC-400", "bad-repo")
    _create_repo(tmp_path / "repos", "real-repo")

    import yaml
    config_path = tmp_path / "config.yaml"
    cfg_data = yaml.safe_load(config_path.read_text()) if config_path.exists() else {}
    cfg_data["repoPaths"] = [str(tmp_path / "repos")]
    config_path.write_text(yaml.dump(cfg_data))

    result = runner.invoke(
        cli,
        ["--workspace-root", str(tmp_path), "add-repo", "ERSC-400", "typo-repo", "main"],
    )

    assert result.exit_code != 0
    assert "typo-repo" in result.output
    assert "real-repo" in result.output


def test_add_repo_writes_sandbox_settings(tmp_path: Path) -> None:
    """add-repo should write .claude/settings.json in the new worktree."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    _create_ticket_dir(tmp_path, "ERSC-600", "sandbox-test")
    repo_dir = _create_repo(tmp_path / "repos", "sandbox-repo")

    subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=repo_dir, capture_output=True)
    (repo_dir / "README.md").write_text("hello")
    subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo_dir, capture_output=True,
        env={"GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t",
             "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t",
             "PATH": "/usr/bin:/bin:/usr/local/bin"},
    )

    import yaml
    config_path = tmp_path / "config.yaml"
    cfg_data = yaml.safe_load(config_path.read_text()) if config_path.exists() else {}
    cfg_data["repoPaths"] = [str(tmp_path / "repos")]
    config_path.write_text(yaml.dump(cfg_data))

    result = runner.invoke(
        cli,
        ["--workspace-root", str(tmp_path), "add-repo", "ERSC-600", "sandbox-repo", "main"],
    )

    assert result.exit_code == 0, result.output
    worktree_path = tmp_path / "ERSC-600-sandbox-test" / "sandbox-repo"
    settings = worktree_path / ".claude" / "settings.json"
    assert settings.exists()
    data = json.loads(settings.read_text())
    assert data["sandbox"]["enabled"] is True


def test_add_repo_branch_override(tmp_path: Path) -> None:
    """--branch should override the auto-generated feature branch name."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    _create_ticket_dir(tmp_path, "ERSC-500", "branch-override")
    repo_dir = _create_repo(tmp_path / "repos", "override-repo")

    subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=repo_dir, capture_output=True)
    (repo_dir / "README.md").write_text("hello")
    subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo_dir, capture_output=True,
        env={"GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t",
             "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t",
             "PATH": "/usr/bin:/bin:/usr/local/bin"},
    )

    import yaml
    config_path = tmp_path / "config.yaml"
    cfg_data = yaml.safe_load(config_path.read_text()) if config_path.exists() else {}
    cfg_data["repoPaths"] = [str(tmp_path / "repos")]
    config_path.write_text(yaml.dump(cfg_data))

    result = runner.invoke(
        cli,
        [
            "--workspace-root", str(tmp_path),
            "add-repo", "ERSC-500", "override-repo", "main",
            "--branch", "custom-branch-name",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "custom-branch-name" in result.output


# ---------------------------------------------------------------------------
# workspace new tests
# ---------------------------------------------------------------------------


def test_workspace_new_creates_dir(tmp_path: Path) -> None:
    """workspace new KEY should create a ticket directory when Jira is not configured."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    result = runner.invoke(
        cli, ["--workspace-root", str(tmp_path), "workspace", "new", "PROJ-42"]
    )

    assert result.exit_code == 0, result.output
    assert "PROJ-42" in result.output
    # Directory should exist under root
    dirs = [d.name for d in tmp_path.iterdir() if d.is_dir()]
    assert any("PROJ-42" in d for d in dirs)


def test_workspace_new_upcases_key(tmp_path: Path) -> None:
    """workspace new should uppercase the ticket key."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    result = runner.invoke(
        cli, ["--workspace-root", str(tmp_path), "workspace", "new", "proj-10"]
    )

    assert result.exit_code == 0, result.output
    dirs = [d.name for d in tmp_path.iterdir() if d.is_dir()]
    assert any("PROJ-10" in d for d in dirs)


def test_workspace_new_with_jira_success(tmp_path: Path) -> None:
    """workspace new should use JiraSync when Jira is configured."""
    import yaml
    from unittest.mock import MagicMock, patch
    from duct.models import SyncResult

    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    # Configure Jira domain
    config_path = tmp_path / "config.yaml"
    cfg_data = yaml.safe_load(config_path.read_text()) if config_path.exists() else {}
    cfg_data["jira"] = {"domain": "test.atlassian.net"}
    config_path.write_text(yaml.dump(cfg_data))

    def fake_sync(root, ticket_key=None):
        # Create the ticket dir as JiraSync would
        _create_ticket_dir(root, "PROJ-99", "my-ticket")
        return SyncResult(source="jira", tickets_synced=1, duration_seconds=0.1)

    with patch("duct.config.jira_email", return_value="user@example.com"), \
         patch("duct.config.jira_token", return_value="tok123"), \
         patch("duct.sync.jira.JiraSync.sync", fake_sync):
        result = runner.invoke(
            cli, ["--workspace-root", str(tmp_path), "workspace", "new", "PROJ-99"]
        )

    assert result.exit_code == 0, result.output
    assert "PROJ-99" in result.output


# ---------------------------------------------------------------------------
# workspace list tests
# ---------------------------------------------------------------------------


def _write_ticket_md(ticket_dir: Path, key: str, summary: str, status: str, category: str) -> None:
    orch = ticket_dir / "orchestrator"
    orch.mkdir(parents=True, exist_ok=True)
    (orch / "TICKET.md").write_text(
        f"# {key}: {summary}\n\n"
        f"| Field | Value |\n"
        f"|---|---|\n"
        f"| Status | {status} |\n"
        f"| Category | {category} |\n"
    )


def test_workspace_list_empty(tmp_path: Path) -> None:
    """workspace list with no ticket dirs reports nothing found."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    result = runner.invoke(cli, ["--workspace-root", str(tmp_path), "workspace", "list"])

    assert result.exit_code == 0, result.output
    assert "No ticket workspaces found" in result.output


def test_workspace_list_shows_keys(tmp_path: Path) -> None:
    """workspace list shows all ticket keys."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    _create_ticket_dir(tmp_path, "PROJ-10")
    _create_ticket_dir(tmp_path, "PROJ-20")

    result = runner.invoke(cli, ["--workspace-root", str(tmp_path), "workspace", "list"])

    assert result.exit_code == 0, result.output
    assert "PROJ-10" in result.output
    assert "PROJ-20" in result.output


def test_workspace_list_with_ticket_md(tmp_path: Path) -> None:
    """workspace list shows summary and status from TICKET.md."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    ticket_dir = _create_ticket_dir(tmp_path, "PROJ-30", "my-feature")
    _write_ticket_md(ticket_dir, "PROJ-30", "My Feature", "In Progress", "Active Development")

    result = runner.invoke(cli, ["--workspace-root", str(tmp_path), "workspace", "list"])

    assert result.exit_code == 0, result.output
    assert "PROJ-30" in result.output
    assert "My Feature" in result.output
    assert "In Progress" in result.output


def test_workspace_list_filter_category(tmp_path: Path) -> None:
    """workspace list --category filters to matching tickets only."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    t1 = _create_ticket_dir(tmp_path, "PROJ-10", "feature-a")
    t2 = _create_ticket_dir(tmp_path, "PROJ-20", "feature-b")
    _write_ticket_md(t1, "PROJ-10", "Feature A", "In Progress", "Active Development")
    _write_ticket_md(t2, "PROJ-20", "Feature B", "Done", "Released")

    result = runner.invoke(
        cli,
        ["--workspace-root", str(tmp_path), "workspace", "list", "--category", "Active Development"],
    )

    assert result.exit_code == 0, result.output
    assert "PROJ-10" in result.output
    assert "PROJ-20" not in result.output


def test_workspace_list_filter_status(tmp_path: Path) -> None:
    """workspace list --status filters to matching tickets only."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    t1 = _create_ticket_dir(tmp_path, "PROJ-10", "open-ticket")
    t2 = _create_ticket_dir(tmp_path, "PROJ-20", "done-ticket")
    _write_ticket_md(t1, "PROJ-10", "Open Ticket", "In Progress", "Active")
    _write_ticket_md(t2, "PROJ-20", "Done Ticket", "Done", "Released")

    result = runner.invoke(
        cli,
        ["--workspace-root", str(tmp_path), "workspace", "list", "--status", "Done"],
    )

    assert result.exit_code == 0, result.output
    assert "PROJ-20" in result.output
    assert "PROJ-10" not in result.output


def test_workspace_list_sort_key(tmp_path: Path) -> None:
    """workspace list --sort key returns keys in alphabetical order."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    _create_ticket_dir(tmp_path, "PROJ-30")
    _create_ticket_dir(tmp_path, "PROJ-10")
    _create_ticket_dir(tmp_path, "PROJ-20")

    result = runner.invoke(
        cli,
        ["--workspace-root", str(tmp_path), "workspace", "list", "--sort", "key"],
    )

    assert result.exit_code == 0, result.output
    pos_10 = result.output.index("PROJ-10")
    pos_20 = result.output.index("PROJ-20")
    pos_30 = result.output.index("PROJ-30")
    assert pos_10 < pos_20 < pos_30


# ---------------------------------------------------------------------------
# workspace archive tests
# ---------------------------------------------------------------------------


def test_workspace_archive_existing(tmp_path: Path) -> None:
    """workspace archive KEY moves the ticket to .archive/."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    ticket_dir = tmp_path / "PROJ-10-some-task"
    (ticket_dir / "orchestrator").mkdir(parents=True)

    result = runner.invoke(
        cli, ["--workspace-root", str(tmp_path), "workspace", "archive", "PROJ-10"]
    )

    assert result.exit_code == 0, result.output
    assert "Archived" in result.output
    assert (tmp_path / ".archive" / "PROJ-10-some-task").is_dir()
    assert not ticket_dir.exists()


def test_workspace_archive_missing(tmp_path: Path) -> None:
    """workspace archive with a key that doesn't exist should error."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    result = runner.invoke(
        cli, ["--workspace-root", str(tmp_path), "workspace", "archive", "NOPE-1"]
    )

    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_workspace_archive_no_key(tmp_path: Path) -> None:
    """workspace archive with no key and no CWD match should error."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    result = runner.invoke(
        cli, ["--workspace-root", str(tmp_path), "workspace", "archive"]
    )

    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# workspace restore tests
# ---------------------------------------------------------------------------


def test_workspace_restore_existing(tmp_path: Path) -> None:
    """workspace restore KEY moves the ticket from .archive/ back to root."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    archive_dir = tmp_path / ".archive" / "PROJ-10-old-task"
    (archive_dir / "orchestrator").mkdir(parents=True)

    result = runner.invoke(
        cli, ["--workspace-root", str(tmp_path), "workspace", "restore", "PROJ-10"]
    )

    assert result.exit_code == 0, result.output
    assert "Restored" in result.output
    assert (tmp_path / "PROJ-10-old-task").is_dir()
    assert not archive_dir.exists()


def test_workspace_restore_missing(tmp_path: Path) -> None:
    """workspace restore with a key not in archive should error."""
    runner = CliRunner()
    _init_workspace(runner, tmp_path)

    result = runner.invoke(
        cli, ["--workspace-root", str(tmp_path), "workspace", "restore", "NOPE-1"]
    )

    assert result.exit_code != 0
    assert "not found" in result.output.lower()
