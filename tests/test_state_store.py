"""
Tests for app/services/state_store.py -- StateStore singleton, state CRUD, persistence.
"""

import json
import os
import threading
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QCoreApplication

from app.services.state_store import StateStore


@pytest.fixture(autouse=True)
def _reset_state_store():
    """Ensure each test starts with a fresh StateStore singleton."""
    StateStore.reset()
    yield
    StateStore.reset()


@pytest.fixture()
def _ensure_qapp():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    yield app


def _make_state_dir(tmp_path):
    """Create a minimal state directory and return the project root."""
    root = tmp_path / "project"
    user_world = root / "user-world"
    user_world.mkdir(parents=True)
    state = {
        "current_step": 3,
        "current_phase": "foundation",
        "completed_steps": [1, 2],
        "in_progress_steps": [3],
        "entity_index": {},
    }
    with open(str(user_world / "state.json"), "w", encoding="utf-8") as fh:
        json.dump(state, fh)
    return str(root)


# ------------------------------------------------------------------
# Singleton tests
# ------------------------------------------------------------------


class TestSingleton:
    def test_instance_returns_same_object(self, tmp_path, _ensure_qapp):
        root = _make_state_dir(tmp_path)
        store1 = StateStore.instance(root)
        store2 = StateStore.instance()
        assert store1 is store2

    def test_reset_clears_instance(self, tmp_path, _ensure_qapp):
        root = _make_state_dir(tmp_path)
        store1 = StateStore.instance(root)
        StateStore.reset()
        store2 = StateStore.instance(root)
        assert store1 is not store2

    def test_instance_requires_project_root_on_first_call(self, _ensure_qapp):
        with pytest.raises(RuntimeError, match="requires project_root"):
            StateStore.instance()


# ------------------------------------------------------------------
# State reads
# ------------------------------------------------------------------


class TestStateReads:
    def test_current_step(self, tmp_path, _ensure_qapp):
        root = _make_state_dir(tmp_path)
        store = StateStore.instance(root)
        assert store.current_step == 3

    def test_current_phase(self, tmp_path, _ensure_qapp):
        root = _make_state_dir(tmp_path)
        store = StateStore.instance(root)
        assert store.current_phase == "foundation"

    def test_completed_steps(self, tmp_path, _ensure_qapp):
        root = _make_state_dir(tmp_path)
        store = StateStore.instance(root)
        assert store.completed_steps == [1, 2]

    def test_entity_index_initially_empty(self, tmp_path, _ensure_qapp):
        root = _make_state_dir(tmp_path)
        store = StateStore.instance(root)
        assert store.entity_index == {}


# ------------------------------------------------------------------
# State mutations with signal verification
# ------------------------------------------------------------------


class TestStateMutations:
    def test_set_current_step_emits_signal(self, tmp_path, _ensure_qapp):
        root = _make_state_dir(tmp_path)
        store = StateStore.instance(root)
        receiver = MagicMock()
        store.step_changed.connect(receiver)
        store.set_current_step(5)
        receiver.assert_called_once_with(5)
        assert store.current_step == 5

    def test_set_current_step_noop_if_same(self, tmp_path, _ensure_qapp):
        root = _make_state_dir(tmp_path)
        store = StateStore.instance(root)
        receiver = MagicMock()
        store.step_changed.connect(receiver)
        store.set_current_step(3)  # already 3
        receiver.assert_not_called()

    def test_add_completed_step(self, tmp_path, _ensure_qapp):
        root = _make_state_dir(tmp_path)
        store = StateStore.instance(root)
        store.add_completed_step(3)
        assert 3 in store.completed_steps
        # Should also be removed from in_progress
        assert 3 not in store.in_progress_steps

    def test_update_entity_index_emits_signal(self, tmp_path, _ensure_qapp):
        root = _make_state_dir(tmp_path)
        store = StateStore.instance(root)
        receiver = MagicMock()
        store.entity_index_changed.connect(receiver)
        store.update_entity_index("god-001", {"name": "Thor", "status": "draft"})
        receiver.assert_called_once()
        assert "god-001" in store.entity_index
        assert store.entity_index["god-001"]["name"] == "Thor"

    def test_remove_entity_from_index(self, tmp_path, _ensure_qapp):
        root = _make_state_dir(tmp_path)
        store = StateStore.instance(root)
        store.update_entity_index("god-001", {"name": "Thor"})
        store.remove_entity_from_index("god-001")
        assert "god-001" not in store.entity_index

    def test_entity_count(self, tmp_path, _ensure_qapp):
        root = _make_state_dir(tmp_path)
        store = StateStore.instance(root)
        assert store.entity_count == 0
        store.update_entity_index("a", {"name": "A"})
        store.update_entity_index("b", {"name": "B"})
        assert store.entity_count == 2


# ------------------------------------------------------------------
# Persistence
# ------------------------------------------------------------------


class TestPersistence:
    def test_save_writes_to_disk(self, tmp_path, _ensure_qapp):
        root = _make_state_dir(tmp_path)
        store = StateStore.instance(root)
        store.set_current_step(10)
        store.save()

        with open(os.path.join(root, "user-world", "state.json"), "r") as fh:
            data = json.load(fh)
        assert data["current_step"] == 10

    def test_reload_restores_from_disk(self, tmp_path, _ensure_qapp):
        root = _make_state_dir(tmp_path)
        store = StateStore.instance(root)

        # Mutate in memory
        store.set_current_step(20)

        # Reload from disk (which still has 3)
        store.reload()
        assert store.current_step == 3

    def test_reload_emits_state_loaded(self, tmp_path, _ensure_qapp):
        root = _make_state_dir(tmp_path)
        store = StateStore.instance(root)
        receiver = MagicMock()
        store.state_loaded.connect(receiver)
        store.reload()
        receiver.assert_called_once()
