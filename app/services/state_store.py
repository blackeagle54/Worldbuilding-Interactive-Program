"""
app/services/state_store.py -- Thread-safe state store wrapping state.json.

Provides reactive access to the world state with Qt signals emitted on
every change.  The store is the single point of truth for UI-visible state;
panels read from it rather than loading state.json directly.

Thread safety is provided via a QMutex so worker threads can safely read
state while the main thread updates it.

Usage::

    from app.services.state_store import StateStore

    store = StateStore.instance(project_root)
    store.step_changed.connect(on_step_change)

    step = store.current_step
    store.set_current_step(5)
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

from engine.utils import safe_read_json, safe_write_json

logger = logging.getLogger(__name__)


class StateStore(QObject):
    """Reactive wrapper around user-world/state.json.

    Signals
    -------
    step_changed(int)
        Emitted when current_step changes.
    entity_index_changed()
        Emitted when the entity_index is modified.
    state_saved()
        Emitted after state.json is successfully written to disk.
    state_loaded()
        Emitted after state.json is loaded/reloaded from disk.
    """

    step_changed = Signal(int)
    entity_index_changed = Signal()
    state_saved = Signal()
    state_loaded = Signal()

    _instance: StateStore | None = None
    _singleton_lock = threading.Lock()

    def __init__(self, project_root: str, parent: QObject | None = None):
        super().__init__(parent)
        self._project_root = project_root
        self._state_path = os.path.join(project_root, "user-world", "state.json")
        self._lock = threading.RLock()
        self._dirty = False

        # Load initial state
        self._state: dict = self._load()

        # Auto-save timer (every 30 seconds if dirty)
        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.setInterval(30_000)
        self._auto_save_timer.timeout.connect(self._auto_save)
        self._auto_save_timer.start()

    @classmethod
    def instance(cls, project_root: str = "") -> StateStore:
        """Return the singleton StateStore instance."""
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    if not project_root:
                        raise RuntimeError("StateStore.instance() requires project_root on first call.")
                    cls._instance = cls(project_root)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for testing)."""
        with cls._singleton_lock:
            if cls._instance is not None:
                cls._instance._auto_save_timer.stop()
                cls._instance.deleteLater()
            cls._instance = None

    # ------------------------------------------------------------------
    # State access (thread-safe reads)
    # ------------------------------------------------------------------

    @property
    def current_step(self) -> int:
        with self._lock:
            return self._state.get("current_step", 1)

    @property
    def current_phase(self) -> str:
        with self._lock:
            return self._state.get("current_phase", "foundation")

    @property
    def completed_steps(self) -> list[int]:
        with self._lock:
            return list(self._state.get("completed_steps", []))

    @property
    def in_progress_steps(self) -> list[int]:
        with self._lock:
            return list(self._state.get("in_progress_steps", []))

    @property
    def entity_index(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._state.get("entity_index", {}))

    @property
    def entity_count(self) -> int:
        with self._lock:
            return len(self._state.get("entity_index", {}))

    def get(self, key: str, default: Any = None) -> Any:
        """Get an arbitrary state key."""
        with self._lock:
            return self._state.get(key, default)

    # ------------------------------------------------------------------
    # State mutations (emit signals)
    # ------------------------------------------------------------------

    def set_current_step(self, step: int) -> None:
        """Update the current step and emit step_changed."""
        with self._lock:
            if self._state.get("current_step") == step:
                return
            self._state["current_step"] = step
            self._dirty = True
        self.step_changed.emit(step)

    def set_current_phase(self, phase: str) -> None:
        """Update the current phase."""
        with self._lock:
            self._state["current_phase"] = phase
            self._dirty = True

    def add_completed_step(self, step: int) -> None:
        """Mark a step as completed."""
        with self._lock:
            completed = self._state.setdefault("completed_steps", [])
            if step not in completed:
                completed.append(step)
                completed.sort()
            # Remove from in_progress
            in_progress = self._state.get("in_progress_steps", [])
            if step in in_progress:
                in_progress.remove(step)
            self._dirty = True

    def update_entity_index(self, entity_id: str, meta: dict) -> None:
        """Add or update an entity in the index."""
        with self._lock:
            index = self._state.setdefault("entity_index", {})
            index[entity_id] = meta
            self._dirty = True
        self.entity_index_changed.emit()

    def remove_entity_from_index(self, entity_id: str) -> None:
        """Remove an entity from the index."""
        with self._lock:
            index = self._state.get("entity_index", {})
            if entity_id in index:
                del index[entity_id]
                self._dirty = True
        self.entity_index_changed.emit()

    def set(self, key: str, value: Any) -> None:
        """Set an arbitrary state key."""
        with self._lock:
            self._state[key] = value
            self._dirty = True

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> None:
        """Write current state to disk immediately."""
        with self._lock:
            data = dict(self._state)
            self._dirty = False

        try:
            safe_write_json(self._state_path, data)
            self.state_saved.emit()
        except Exception:
            logger.exception("Failed to save state.json")
            with self._lock:
                self._dirty = True  # Retry next auto-save

    def reload(self) -> None:
        """Re-read state.json from disk (discarding in-memory changes)."""
        with self._lock:
            self._state = self._load()
            self._dirty = False
        self.state_loaded.emit()

    def _load(self) -> dict:
        """Load state.json with sensible defaults."""
        default = {
            "current_step": 1,
            "current_phase": "foundation",
            "completed_steps": [],
            "in_progress_steps": [],
            "entity_index": {},
        }
        state = safe_read_json(self._state_path, default=default)
        if not isinstance(state, dict):
            return default
        return state

    def _auto_save(self) -> None:
        """Called by the auto-save timer. Only writes if dirty."""
        if self._dirty:
            self.save()

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Stop auto-save and flush any pending changes."""
        self._auto_save_timer.stop()
        if self._dirty:
            self.save()
