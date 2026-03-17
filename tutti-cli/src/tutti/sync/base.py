"""Sync framework: SyncSource protocol and SyncCoordinator."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Protocol, runtime_checkable

import yaml

from tutti.models import SyncResult


@runtime_checkable
class SyncSource(Protocol):
    """Protocol that all sync sources implement."""

    @property
    def name(self) -> str:
        """Unique identifier for this source (e.g. 'jira', 'github')."""
        ...

    def sync(self, root: Path) -> SyncResult:
        """Run a sync cycle, writing snapshot files under root."""
        ...


class SyncCoordinator:
    """Tracks staleness per source and orchestrates sync runs."""

    def __init__(self, root: Path, intervals: dict[str, int] | None = None):
        self._root = root
        self._intervals = intervals or {}
        self._state_path = root / ".sync_state.yaml"

    def _load_state(self) -> dict[str, float]:
        if self._state_path.exists():
            raw = yaml.safe_load(self._state_path.read_text()) or {}
            return {k: float(v) for k, v in raw.items()}
        return {}

    def _save_state(self, state: dict[str, float]) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(yaml.dump(state, default_flow_style=False))

    def is_stale(self, source_name: str) -> bool:
        state = self._load_state()
        last_sync = state.get(source_name, 0.0)
        interval = self._intervals.get(source_name, 0)
        return (time.time() - last_sync) >= interval

    def run(self, sources: list[SyncSource], force: bool = False) -> list[SyncResult]:
        results = []
        state = self._load_state()
        for source in sources:
            if not force and not self.is_stale(source.name):
                continue
            result = source.sync(self._root)
            results.append(result)
            if not result.errors:
                state[source.name] = time.time()
        self._save_state(state)
        return results
