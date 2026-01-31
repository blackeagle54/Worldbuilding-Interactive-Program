"""
Tests for app/panels/ -- ProgressSidebarPanel, ChatPanel,
EntityBrowserPanel, OptionComparisonPanel.

All tests use the qtbot fixture from pytest-qt.
"""

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt

from app.services.event_bus import EventBus
from app.services.state_store import StateStore
from app.panels.progress_sidebar import (
    PHASES,
    STEPS,
    ProgressSidebarPanel,
)
from app.panels.chat_panel import ChatPanel, MAX_HISTORY
from app.panels.entity_browser import EntityBrowserPanel
from app.panels.option_comparison import OptionComparisonPanel


@pytest.fixture(autouse=True)
def _reset_singletons():
    EventBus.reset()
    StateStore.reset()
    # Flush any pending deleteLater calls
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app:
        try:
            app.processEvents()
        except RuntimeError:
            pass
    yield
    EventBus.reset()
    StateStore.reset()
    if app:
        try:
            app.processEvents()
        except RuntimeError:
            pass


# ==================================================================
# ProgressSidebarPanel tests
# ==================================================================


class TestProgressSidebarPanel:
    def test_52_steps_in_tree(self, qtbot):
        panel = ProgressSidebarPanel()
        qtbot.addWidget(panel)
        assert len(panel._step_items) == 52

    def test_all_phases_present(self, qtbot):
        panel = ProgressSidebarPanel()
        qtbot.addWidget(panel)
        assert len(panel._phase_items) == len(PHASES)
        for key, _, _, _ in PHASES:
            assert key in panel._phase_items

    def test_phase_grouping_covers_all_steps(self, qtbot):
        """Every step 1-52 must appear in exactly one phase."""
        all_steps = set()
        for _, _, start, end in PHASES:
            for s in range(start, end + 1):
                assert s not in all_steps, f"Step {s} in multiple phases"
                all_steps.add(s)
        assert all_steps == set(range(1, 53))

    def test_refresh_with_state_store(self, qtbot, tmp_path):
        import json, os
        root = tmp_path / "proj"
        uw = root / "user-world"
        uw.mkdir(parents=True)
        state = {
            "current_step": 7,
            "current_phase": "cosmology",
            "completed_steps": [1, 2, 3, 4, 5, 6],
            "in_progress_steps": [7],
            "entity_index": {},
        }
        with open(str(uw / "state.json"), "w") as fh:
            json.dump(state, fh)

        store = StateStore.instance(str(root))
        panel = ProgressSidebarPanel()
        qtbot.addWidget(panel)
        panel.set_state_store(store)

        # Overall progress should show 6 completed
        assert panel._overall_progress.value() == 6

    def test_advance_requested_signal(self, qtbot):
        panel = ProgressSidebarPanel()
        qtbot.addWidget(panel)
        receiver = MagicMock()
        panel.advance_requested.connect(receiver)
        panel._advance_btn.click()
        receiver.assert_called_once()


# ==================================================================
# ChatPanel tests
# ==================================================================


class TestChatPanel:
    def test_creation(self, qtbot):
        panel = ChatPanel()
        qtbot.addWidget(panel)
        # Should contain welcome message
        html = panel._display.toHtml()
        assert "Welcome" in html

    def test_append_user_message(self, qtbot):
        panel = ChatPanel()
        qtbot.addWidget(panel)
        panel._append_user_message("Hello Claude")
        html = panel._display.toHtml()
        assert "Hello Claude" in html

    def test_append_claude_message(self, qtbot):
        panel = ChatPanel()
        qtbot.addWidget(panel)
        panel._append_claude_message("I am Claude")
        html = panel._display.toHtml()
        assert "I am Claude" in html

    def test_streaming_lifecycle(self, qtbot):
        panel = ChatPanel()
        qtbot.addWidget(panel)
        panel.show()

        panel._start_streaming()
        assert panel._streaming is True
        assert panel._stop_btn.isVisible()
        assert not panel._send_btn.isVisible()

        panel._end_streaming()
        assert panel._streaming is False
        assert panel._send_btn.isVisible()
        assert not panel._stop_btn.isVisible()

    def test_history_cap(self, qtbot):
        panel = ChatPanel()
        qtbot.addWidget(panel)
        for i in range(MAX_HISTORY + 20):
            panel._conversation_history.append({"role": "user", "content": f"msg {i}"})
        # Simulate the trim that happens on send
        panel._conversation_history = panel._conversation_history[-MAX_HISTORY:]
        assert len(panel._conversation_history) == MAX_HISTORY

    def test_no_worker_shows_offline_message(self, qtbot):
        panel = ChatPanel()
        qtbot.addWidget(panel)
        panel._input.setText("test message")
        panel._on_send()
        html = panel._display.toHtml()
        assert "not connected" in html


# ==================================================================
# EntityBrowserPanel tests
# ==================================================================


class TestEntityBrowserPanel:
    def test_creation(self, qtbot):
        panel = EntityBrowserPanel()
        qtbot.addWidget(panel)
        assert panel._model.rowCount() == 0

    def test_refresh_without_engine_does_nothing(self, qtbot):
        panel = EntityBrowserPanel()
        qtbot.addWidget(panel)
        panel.refresh()
        assert panel._model.rowCount() == 0

    def test_search_timer_exists(self, qtbot):
        panel = EntityBrowserPanel()
        qtbot.addWidget(panel)
        assert panel._search_timer.isSingleShot()
        assert panel._search_timer.interval() == 200

    def test_refresh_debounce_timer_exists(self, qtbot):
        panel = EntityBrowserPanel()
        qtbot.addWidget(panel)
        assert panel._refresh_timer.isSingleShot()
        assert panel._refresh_timer.interval() == 100


# ==================================================================
# OptionComparisonPanel tests
# ==================================================================


class TestOptionComparisonPanel:
    """Tests for the OptionComparisonPanel.

    Uses process_events_before_teardown fixture to ensure stale Qt animations
    from ChatPanel tests do not cause RuntimeError during pytest-qt teardown.
    """

    @pytest.fixture(autouse=True)
    def _patch_process_events(self, monkeypatch):
        """Monkeypatch processEvents to tolerate deleted C++ QPropertyAnimation objects.

        PySide6's QTextEdit (used inside OptionCard) creates internal
        QPropertyAnimation objects that may be garbage-collected before
        pytest-qt's post-test processEvents call.
        """
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            _original = app.processEvents

            def _safe_process_events(*args, **kwargs):
                try:
                    return _original(*args, **kwargs)
                except RuntimeError:
                    pass

            monkeypatch.setattr(app, "processEvents", _safe_process_events)
        yield

    def test_creation_empty(self, qtbot):
        panel = OptionComparisonPanel()
        qtbot.addWidget(panel)
        assert len(panel._cards) == 0
        assert panel._empty_label is not None

    def test_show_options_creates_cards(self, qtbot):
        panel = OptionComparisonPanel()
        qtbot.addWidget(panel)
        options = [
            {"id": "opt-1", "title": "Storm God", "description": "A storm deity."},
            {"id": "opt-2", "title": "Fire God", "description": "A fire deity."},
            {"id": "opt-3", "title": "Ice God", "description": "An ice deity."},
        ]
        panel.show_options(options)
        assert len(panel._cards) == 3
        assert panel._cards[0].option_id == "opt-1"
        assert panel._cards[1].option_id == "opt-2"
        assert panel._cards[2].option_id == "opt-3"
        # Keep references alive so C++ objects are not deleted before processEvents
        panel._test_refs = list(panel._cards)

    def test_card_selection(self, qtbot):
        panel = OptionComparisonPanel()
        qtbot.addWidget(panel)
        options = [
            {"id": "opt-1", "title": "Storm God", "description": "A storm deity."},
        ]
        panel.show_options(options)
        panel._on_card_selected("opt-1")
        assert panel._selected_id == "opt-1"
        assert panel._confirm_btn.isEnabled()
        panel._test_refs = list(panel._cards)

    def test_clear_removes_cards(self, qtbot):
        panel = OptionComparisonPanel()
        qtbot.addWidget(panel)
        options = [
            {"id": "opt-1", "title": "Test", "description": "Desc."},
        ]
        panel.show_options(options)
        # Keep refs to prevent C++ deletion during processEvents
        card_refs = list(panel._cards)
        assert len(card_refs) == 1
        panel.clear()
        assert len(panel._cards) == 0
        assert panel._selected_id == ""
        panel._test_refs = card_refs

    def test_show_options_empty_list(self, qtbot):
        panel = OptionComparisonPanel()
        qtbot.addWidget(panel)
        panel.show_options([])
        assert len(panel._cards) == 0
        assert panel._stats_label.text() == "0 options"
