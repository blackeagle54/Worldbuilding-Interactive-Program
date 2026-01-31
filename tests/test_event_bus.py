"""
Tests for app/services/event_bus.py -- EventBus singleton and signals.
"""

import threading
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QCoreApplication

from app.services.event_bus import EventBus


@pytest.fixture(autouse=True)
def _reset_event_bus():
    """Ensure each test starts with a fresh EventBus."""
    EventBus.reset()
    yield
    EventBus.reset()


@pytest.fixture()
def _ensure_qapp():
    """Make sure a QCoreApplication exists for signal/slot machinery."""
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    yield app


# ------------------------------------------------------------------
# Singleton tests
# ------------------------------------------------------------------


class TestSingletonPattern:
    def test_instance_returns_same_object(self, _ensure_qapp):
        bus1 = EventBus.instance()
        bus2 = EventBus.instance()
        assert bus1 is bus2

    def test_reset_clears_instance(self, _ensure_qapp):
        bus1 = EventBus.instance()
        EventBus.reset()
        bus2 = EventBus.instance()
        assert bus1 is not bus2

    def test_instance_returns_eventbus_type(self, _ensure_qapp):
        bus = EventBus.instance()
        assert isinstance(bus, EventBus)

    def test_thread_safe_creation(self, _ensure_qapp):
        """Multiple threads racing to create the instance should all get the same object."""
        results = []
        barrier = threading.Barrier(4)

        def _grab():
            barrier.wait()
            results.append(id(EventBus.instance()))

        threads = [threading.Thread(target=_grab) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(set(results)) == 1, "All threads should get the same instance"


# ------------------------------------------------------------------
# Signal tests
# ------------------------------------------------------------------


class TestSignals:
    def test_entity_selected_signal(self, _ensure_qapp):
        bus = EventBus.instance()
        receiver = MagicMock()
        bus.entity_selected.connect(receiver)
        bus.entity_selected.emit("entity-001")
        receiver.assert_called_once_with("entity-001")

    def test_entity_created_signal(self, _ensure_qapp):
        bus = EventBus.instance()
        receiver = MagicMock()
        bus.entity_created.connect(receiver)
        bus.entity_created.emit("entity-002")
        receiver.assert_called_once_with("entity-002")

    def test_entity_updated_signal(self, _ensure_qapp):
        bus = EventBus.instance()
        receiver = MagicMock()
        bus.entity_updated.connect(receiver)
        bus.entity_updated.emit("entity-003")
        receiver.assert_called_once_with("entity-003")

    def test_entity_deleted_signal(self, _ensure_qapp):
        bus = EventBus.instance()
        receiver = MagicMock()
        bus.entity_deleted.connect(receiver)
        bus.entity_deleted.emit("entity-004")
        receiver.assert_called_once_with("entity-004")

    def test_step_changed_signal(self, _ensure_qapp):
        bus = EventBus.instance()
        receiver = MagicMock()
        bus.step_changed.connect(receiver)
        bus.step_changed.emit(7)
        receiver.assert_called_once_with(7)

    def test_generation_started_and_finished(self, _ensure_qapp):
        bus = EventBus.instance()
        started = MagicMock()
        finished = MagicMock()
        bus.generation_started.connect(started)
        bus.generation_finished.connect(finished)

        bus.generation_started.emit("god-profile")
        bus.generation_finished.emit("god-profile")

        started.assert_called_once_with("god-profile")
        finished.assert_called_once_with("god-profile")

    def test_claude_token_signal(self, _ensure_qapp):
        bus = EventBus.instance()
        receiver = MagicMock()
        bus.claude_token.connect(receiver)
        bus.claude_token.emit("hello")
        receiver.assert_called_once_with("hello")

    def test_error_occurred_signal(self, _ensure_qapp):
        bus = EventBus.instance()
        receiver = MagicMock()
        bus.error_occurred.connect(receiver)
        bus.error_occurred.emit("Something went wrong")
        receiver.assert_called_once_with("Something went wrong")

    def test_status_message_signal(self, _ensure_qapp):
        bus = EventBus.instance()
        receiver = MagicMock()
        bus.status_message.connect(receiver)
        bus.status_message.emit("Step 7: Create Individual God Profiles")
        receiver.assert_called_once_with("Step 7: Create Individual God Profiles")

    def test_multiple_receivers(self, _ensure_qapp):
        bus = EventBus.instance()
        r1 = MagicMock()
        r2 = MagicMock()
        bus.entity_selected.connect(r1)
        bus.entity_selected.connect(r2)
        bus.entity_selected.emit("test-id")
        r1.assert_called_once_with("test-id")
        r2.assert_called_once_with("test-id")
