"""Tests for tutti orchestrate command."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from tutti.cli.main import cli
from tutti.cli.orchestrate_cmd import _build_prompt, _format_stream_event
from tutti.config import TrustConfig, WorkspaceConfig, save_config


def _init_workspace(root: Path) -> None:
    cfg = WorkspaceConfig(root=root)
    save_config(cfg, root)


class TestOrchestrate:
    def test_dry_run_shows_command(self, tmp_path: Path) -> None:
        _init_workspace(tmp_path)
        runner = CliRunner()
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            result = runner.invoke(
                cli,
                ["--workspace-root", str(tmp_path), "orchestrate", "--dry-run"],
            )
        assert result.exit_code == 0
        assert "/usr/local/bin/claude" in result.output
        assert "--add-dir" in result.output

    def test_dry_run_with_ticket(self, tmp_path: Path) -> None:
        _init_workspace(tmp_path)
        runner = CliRunner()
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            result = runner.invoke(
                cli,
                [
                    "--workspace-root", str(tmp_path),
                    "orchestrate", "--ticket", "ERSC-1278", "--dry-run",
                ],
            )
        assert result.exit_code == 0
        assert "ERSC-1278" in result.output

    def test_missing_claude_binary(self, tmp_path: Path) -> None:
        _init_workspace(tmp_path)
        runner = CliRunner()
        with patch("shutil.which", return_value=None):
            result = runner.invoke(
                cli,
                ["--workspace-root", str(tmp_path), "orchestrate"],
            )
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_allowed_tools_default(self, tmp_path: Path) -> None:
        """Default trust config includes Bash (git_commit=propose)."""
        _init_workspace(tmp_path)
        runner = CliRunner()
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            result = runner.invoke(
                cli,
                ["--workspace-root", str(tmp_path), "orchestrate", "--dry-run"],
            )
        assert "Bash" in result.output

    def test_allowed_tools_deny_all(self, tmp_path: Path) -> None:
        """When all shell actions are deny, Bash is excluded."""
        cfg = WorkspaceConfig(
            root=tmp_path,
            trust=TrustConfig(
                git_commit="deny",
                git_push="deny",
                pr_create="deny",
                pr_merge="deny",
            ),
        )
        save_config(cfg, tmp_path)

        runner = CliRunner()
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            result = runner.invoke(
                cli,
                ["--workspace-root", str(tmp_path), "orchestrate", "--dry-run"],
            )
        assert "Bash" not in result.output
        assert "Read" in result.output

    def test_dry_run_verbose_adds_stream_json(self, tmp_path: Path) -> None:
        _init_workspace(tmp_path)
        runner = CliRunner()
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            result = runner.invoke(
                cli,
                ["--workspace-root", str(tmp_path), "orchestrate", "--dry-run", "--verbose"],
            )
        assert result.exit_code == 0
        assert "--verbose" in result.output
        assert "--output-format" in result.output
        assert "stream-json" in result.output

    def test_dry_run_without_verbose_no_stream_json(self, tmp_path: Path) -> None:
        _init_workspace(tmp_path)
        runner = CliRunner()
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            result = runner.invoke(
                cli,
                ["--workspace-root", str(tmp_path), "orchestrate", "--dry-run"],
            )
        assert result.exit_code == 0
        assert "stream-json" not in result.output

    def test_json_dry_run(self, tmp_path: Path) -> None:
        _init_workspace(tmp_path)
        runner = CliRunner()
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            result = runner.invoke(
                cli,
                [
                    "--json",
                    "--workspace-root", str(tmp_path),
                    "orchestrate", "--dry-run",
                ],
            )
        assert result.exit_code == 0
        assert '"command"' in result.output


class TestPromptContent:
    def test_prompt_includes_sync_boundary(self, tmp_path: Path) -> None:
        trust = TrustConfig()
        prompt = _build_prompt(None, tmp_path, trust)
        assert "tutti sync" in prompt
        assert "do not create it manually" in prompt
        assert ".archive/" in prompt

    def test_prompt_includes_priority_format_guidance(self, tmp_path: Path) -> None:
        trust = TrustConfig()
        prompt = _build_prompt(None, tmp_path, trust)
        assert "maintain PRIORITY.md" in prompt
        assert "markdown list item" in prompt
        assert "ticket key" in prompt


class TestStreamFormatting:
    def test_init_event(self) -> None:
        event = json.dumps({"type": "system", "subtype": "init", "model": "opus-4"})
        result = _format_stream_event(event)
        assert result is not None
        assert "model=opus-4" in result

    def test_tool_use_event(self) -> None:
        event = json.dumps({
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Read", "input": {"file_path": "src/foo.py"}},
                ],
            },
        })
        result = _format_stream_event(event)
        assert result is not None
        assert "Read" in result
        assert "src/foo.py" in result

    def test_text_event(self) -> None:
        event = json.dumps({
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "Analyzing the ticket..."},
                ],
            },
        })
        result = _format_stream_event(event)
        assert result is not None
        assert "Analyzing the ticket" in result

    def test_result_event(self) -> None:
        event = json.dumps({
            "type": "result",
            "duration_seconds": 12.3,
            "cost_usd": 0.04,
            "num_turns": 4,
        })
        result = _format_stream_event(event)
        assert result is not None
        assert "4 turns" in result
        assert "12.3s" in result
        assert "$0.04" in result

    def test_skips_unknown_event(self) -> None:
        event = json.dumps({"type": "content_block_delta"})
        assert _format_stream_event(event) is None

    def test_invalid_json(self) -> None:
        assert _format_stream_event("not json{") is None

    def test_long_text_truncated(self) -> None:
        long_text = "x" * 300
        event = json.dumps({
            "type": "assistant",
            "message": {
                "content": [{"type": "text", "text": long_text}],
            },
        })
        result = _format_stream_event(event)
        assert result is not None
        assert "..." in result
        assert len(result) < 300
