# duct Development

duct is a Python CLI (`duct-cli/`) that syncs Jira and GitHub data into a ticket-centric folder structure and provides an AI orchestrator (Claude Code session) that reviews workspace state and produces artifacts. The `duct-cli/.claude/CLAUDE.md` file is a template written into user workspaces by `duct init` — it is not for development use.

## Running Tests

Tests must be run from the `duct-cli/` directory using the venv pytest:

```bash
cd duct-cli
.venv/bin/pytest tests/ -x -q
```
