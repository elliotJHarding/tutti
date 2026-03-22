"""Tests for the duct repo command group."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from duct.cli.main import cli


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


_GIT_ENV = {
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "t@t.com",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "t@t.com",
    "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/local/bin"),
}


def _init_workspace(root: Path) -> None:
    """Write a minimal config.yaml so find_workspace_root succeeds."""
    (root / "config.yaml").write_text("workspace:\n  root: .\n")


def _create_ticket_dir_with_workspace(root: Path, key: str, slug: str = "") -> Path:
    """Create ticket dir with orchestrator/ and .duct/workspace.json."""
    dirname = f"{key}-{slug}" if slug else f"{key}-{key.lower()}"
    ticket_dir = root / dirname
    (ticket_dir / "orchestrator").mkdir(parents=True)
    duct_dir = ticket_dir / ".duct"
    duct_dir.mkdir()
    (duct_dir / "workspace.json").write_text(
        json.dumps({"ticket_key": key, "created_at": "2024-01-01T00:00:00Z", "repos": []})
    )
    return ticket_dir


def _create_git_repo(path: Path, branch: str = "main") -> Path:
    """Create a real git repo with one commit."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, capture_output=True, env=_GIT_ENV)
    subprocess.run(["git", "checkout", "-b", branch], cwd=path, capture_output=True, env=_GIT_ENV)
    (path / "README.md").write_text("hello")
    subprocess.run(["git", "add", "."], cwd=path, capture_output=True, env=_GIT_ENV)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, capture_output=True, env=_GIT_ENV)
    return path


def _write_repo_path_config(root: Path, repos_dir: Path) -> None:
    """Add repoPaths to the workspace config.yaml."""
    config_path = root / "config.yaml"
    cfg_data = yaml.safe_load(config_path.read_text()) if config_path.exists() else {}
    cfg_data["repoPaths"] = [str(repos_dir)]
    config_path.write_text(yaml.dump(cfg_data))


def _add_repo_to_workspace_json(ticket_dir: Path, name: str, branch: str = "main", base_branch: str = "main") -> None:
    """Inject a repo entry directly into workspace.json."""
    ws_path = ticket_dir / ".duct" / "workspace.json"
    data = json.loads(ws_path.read_text()) if ws_path.exists() else {}
    repos = data.get("repos", [])
    repos.append({"name": name, "origin": "", "branch": branch, "base_branch": base_branch})
    data["repos"] = repos
    ws_path.write_text(json.dumps(data))


# ---------------------------------------------------------------------------
# repo add
# ---------------------------------------------------------------------------


class TestRepoAdd:
    def test_creates_worktree(self, tmp_path: Path) -> None:
        """repo add creates a git worktree in the ticket dir."""
        runner = CliRunner()
        _init_workspace(tmp_path)

        ticket_dir = _create_ticket_dir_with_workspace(tmp_path, "ERSC-100", "my-ticket")
        repos_dir = tmp_path / "repos"
        repo_path = _create_git_repo(repos_dir / "my-repo")
        _write_repo_path_config(tmp_path, repos_dir)

        result = runner.invoke(
            cli,
            [
                "--workspace-root", str(tmp_path),
                "repo", "add", "my-repo", "main",
                "--workspace", "ERSC-100",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "Added worktree" in result.output
        assert (ticket_dir / "my-repo").is_dir()

    def test_persists_to_workspace_json(self, tmp_path: Path) -> None:
        """repo add writes the repo entry into workspace.json."""
        runner = CliRunner()
        _init_workspace(tmp_path)

        ticket_dir = _create_ticket_dir_with_workspace(tmp_path, "ERSC-101", "my-ticket")
        repos_dir = tmp_path / "repos"
        _create_git_repo(repos_dir / "my-repo")
        _write_repo_path_config(tmp_path, repos_dir)

        runner.invoke(
            cli,
            [
                "--workspace-root", str(tmp_path),
                "repo", "add", "my-repo", "main",
                "--workspace", "ERSC-101",
            ],
        )

        data = json.loads((ticket_dir / ".duct" / "workspace.json").read_text())
        repo_names = [r["name"] for r in data.get("repos", [])]
        assert "my-repo" in repo_names

    def test_branch_override(self, tmp_path: Path) -> None:
        """--branch overrides the auto-generated feature branch name."""
        runner = CliRunner()
        _init_workspace(tmp_path)

        _create_ticket_dir_with_workspace(tmp_path, "ERSC-102", "my-ticket")
        repos_dir = tmp_path / "repos"
        _create_git_repo(repos_dir / "my-repo")
        _write_repo_path_config(tmp_path, repos_dir)

        result = runner.invoke(
            cli,
            [
                "--workspace-root", str(tmp_path),
                "repo", "add", "my-repo", "main",
                "--workspace", "ERSC-102",
                "--branch", "my-custom-branch",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "my-custom-branch" in result.output

    def test_repo_not_found(self, tmp_path: Path) -> None:
        """repo add with an unknown repo name should fail."""
        runner = CliRunner()
        _init_workspace(tmp_path)

        _create_ticket_dir_with_workspace(tmp_path, "ERSC-103", "my-ticket")
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir(parents=True)
        _write_repo_path_config(tmp_path, repos_dir)

        result = runner.invoke(
            cli,
            [
                "--workspace-root", str(tmp_path),
                "repo", "add", "nonexistent-repo", "main",
                "--workspace", "ERSC-103",
            ],
        )

        assert result.exit_code != 0
        assert "nonexistent-repo" in result.output

    def test_no_workspace_errors(self, tmp_path: Path) -> None:
        """repo add with no -w and not inside a workspace dir should error."""
        runner = CliRunner()
        _init_workspace(tmp_path)

        result = runner.invoke(
            cli,
            ["--workspace-root", str(tmp_path), "repo", "add", "my-repo", "main"],
        )

        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# repo list
# ---------------------------------------------------------------------------


class TestRepoList:
    def test_empty_repos(self, tmp_path: Path) -> None:
        """repo list with no repos registered shows helpful message."""
        runner = CliRunner()
        _init_workspace(tmp_path)
        _create_ticket_dir_with_workspace(tmp_path, "ERSC-200", "my-ticket")

        result = runner.invoke(
            cli,
            ["--workspace-root", str(tmp_path), "repo", "list", "--workspace", "ERSC-200"],
        )

        assert result.exit_code == 0, result.output
        assert "No repos added" in result.output

    def test_missing_worktree_shows_missing(self, tmp_path: Path) -> None:
        """repo list shows 'missing' when a registered worktree doesn't exist on disk."""
        runner = CliRunner()
        _init_workspace(tmp_path)
        ticket_dir = _create_ticket_dir_with_workspace(tmp_path, "ERSC-201", "my-ticket")
        _add_repo_to_workspace_json(ticket_dir, "ghost-repo", branch="feature/ERSC-201-my-ticket")

        result = runner.invoke(
            cli,
            ["--workspace-root", str(tmp_path), "repo", "list", "--workspace", "ERSC-201"],
        )

        assert result.exit_code == 0, result.output
        assert "ghost-repo" in result.output
        assert "missing" in result.output

    def test_shows_clean_worktree(self, tmp_path: Path) -> None:
        """repo list shows 'clean' for a worktree with no git changes."""
        runner = CliRunner()
        _init_workspace(tmp_path)
        ticket_dir = _create_ticket_dir_with_workspace(tmp_path, "ERSC-202", "my-ticket")
        _add_repo_to_workspace_json(ticket_dir, "clean-repo", branch="feature/ERSC-202-my-ticket")

        # Create the worktree dir so it's found
        wt = ticket_dir / "clean-repo"
        wt.mkdir()

        with patch("duct.cli.repo_cmd._run") as mock_run:
            mock_run.return_value = (0, "", "")  # empty git status --porcelain

            result = runner.invoke(
                cli,
                ["--workspace-root", str(tmp_path), "repo", "list", "--workspace", "ERSC-202"],
            )

        assert result.exit_code == 0, result.output
        assert "clean" in result.output

    def test_shows_dirty_worktree(self, tmp_path: Path) -> None:
        """repo list shows change count for a dirty worktree."""
        runner = CliRunner()
        _init_workspace(tmp_path)
        ticket_dir = _create_ticket_dir_with_workspace(tmp_path, "ERSC-203", "my-ticket")
        _add_repo_to_workspace_json(ticket_dir, "dirty-repo", branch="feature/ERSC-203-my-ticket")

        wt = ticket_dir / "dirty-repo"
        wt.mkdir()

        with patch("duct.cli.repo_cmd._run") as mock_run:
            mock_run.return_value = (0, " M file.py\n?? new.txt\n", "")

            result = runner.invoke(
                cli,
                ["--workspace-root", str(tmp_path), "repo", "list", "--workspace", "ERSC-203"],
            )

        assert result.exit_code == 0, result.output
        assert "changes" in result.output


# ---------------------------------------------------------------------------
# repo remove
# ---------------------------------------------------------------------------


class TestRepoRemove:
    def test_removes_from_workspace_json(self, tmp_path: Path) -> None:
        """repo remove REPO removes the entry from workspace.json."""
        runner = CliRunner()
        _init_workspace(tmp_path)
        ticket_dir = _create_ticket_dir_with_workspace(tmp_path, "ERSC-300", "my-ticket")
        _add_repo_to_workspace_json(ticket_dir, "my-repo")

        result = runner.invoke(
            cli,
            ["--workspace-root", str(tmp_path), "repo", "remove", "my-repo", "--workspace", "ERSC-300"],
            input="y\n",
        )

        assert result.exit_code == 0, result.output
        assert "Removed" in result.output
        data = json.loads((ticket_dir / ".duct" / "workspace.json").read_text())
        repo_names = [r["name"] for r in data.get("repos", [])]
        assert "my-repo" not in repo_names

    def test_not_registered_errors(self, tmp_path: Path) -> None:
        """repo remove with an unregistered repo name should fail."""
        runner = CliRunner()
        _init_workspace(tmp_path)
        _create_ticket_dir_with_workspace(tmp_path, "ERSC-301", "my-ticket")

        result = runner.invoke(
            cli,
            [
                "--workspace-root", str(tmp_path),
                "repo", "remove", "not-there", "--workspace", "ERSC-301",
            ],
        )

        assert result.exit_code != 0
        assert "not-there" in result.output

    def test_aborted_leaves_json_intact(self, tmp_path: Path) -> None:
        """Declining the confirm prompt leaves workspace.json unchanged."""
        runner = CliRunner()
        _init_workspace(tmp_path)
        ticket_dir = _create_ticket_dir_with_workspace(tmp_path, "ERSC-302", "my-ticket")
        _add_repo_to_workspace_json(ticket_dir, "keep-repo")

        result = runner.invoke(
            cli,
            ["--workspace-root", str(tmp_path), "repo", "remove", "keep-repo", "--workspace", "ERSC-302"],
            input="n\n",
        )

        assert result.exit_code == 0, result.output
        data = json.loads((ticket_dir / ".duct" / "workspace.json").read_text())
        repo_names = [r["name"] for r in data.get("repos", [])]
        assert "keep-repo" in repo_names


# ---------------------------------------------------------------------------
# repo pr
# ---------------------------------------------------------------------------


class TestRepoPr:
    def test_no_repos_errors(self, tmp_path: Path) -> None:
        """repo pr with no repos registered should fail."""
        runner = CliRunner()
        _init_workspace(tmp_path)
        _create_ticket_dir_with_workspace(tmp_path, "ERSC-400", "my-ticket")

        result = runner.invoke(
            cli,
            ["--workspace-root", str(tmp_path), "repo", "pr", "--workspace", "ERSC-400"],
        )

        assert result.exit_code != 0
        assert "No repos" in result.output

    def test_missing_worktree_warns_and_skips(self, tmp_path: Path) -> None:
        """repo pr warns and skips repos whose worktree directory is missing."""
        runner = CliRunner()
        _init_workspace(tmp_path)
        ticket_dir = _create_ticket_dir_with_workspace(tmp_path, "ERSC-401", "my-ticket")
        _add_repo_to_workspace_json(ticket_dir, "ghost-repo", branch="feature/ERSC-401-my-ticket")

        result = runner.invoke(
            cli,
            ["--workspace-root", str(tmp_path), "repo", "pr", "--workspace", "ERSC-401"],
        )

        # Should not error — just warn
        assert "ghost-repo" in result.output

    def test_pushes_and_creates_pr(self, tmp_path: Path) -> None:
        """repo pr pushes branch and calls gh pr create when no PR exists."""
        runner = CliRunner()
        _init_workspace(tmp_path)
        ticket_dir = _create_ticket_dir_with_workspace(tmp_path, "ERSC-402", "my-ticket")
        _add_repo_to_workspace_json(
            ticket_dir, "my-repo",
            branch="feature/ERSC-402-my-ticket",
            base_branch="main",
        )

        # Create a stub worktree dir so the path exists
        wt = ticket_dir / "my-repo"
        wt.mkdir()

        calls: list[tuple] = []

        def fake_run(cmd, cwd, **kwargs):
            calls.append((cmd, cwd))
            if "status" in cmd:
                return (0, "", "")     # no changes → skip commit
            if "push" in cmd:
                return (0, "", "")
            if "view" in cmd:
                return (1, "", "")     # no existing PR
            if "create" in cmd:
                return (0, "https://github.com/org/repo/pull/1", "")
            return (0, "", "")

        with patch("duct.cli.repo_cmd._run", side_effect=fake_run), \
             patch("shutil.which", return_value="/usr/bin/gh"):
            result = runner.invoke(
                cli,
                ["--workspace-root", str(tmp_path), "repo", "pr", "--workspace", "ERSC-402"],
            )

        assert result.exit_code == 0, result.output
        push_calls = [c for c in calls if "push" in c[0]]
        assert push_calls, "Expected at least one push call"
        pr_create_calls = [c for c in calls if "create" in c[0]]
        assert pr_create_calls, "Expected gh pr create call"
