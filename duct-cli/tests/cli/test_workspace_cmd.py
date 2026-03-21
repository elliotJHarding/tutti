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
