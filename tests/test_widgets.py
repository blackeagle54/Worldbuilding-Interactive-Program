"""
Tests for app/widgets/ -- FieldWidget, EntityForm, OptionCard, LoadingOverlay,
SpinnerLabel, Toast.

All tests requiring a visible widget use the qtbot fixture from pytest-qt.
"""

from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QLineEdit, QPlainTextEdit, QWidget

from app.services.event_bus import EventBus
from app.widgets.entity_form import EntityForm, FieldWidget
from app.widgets.loading_overlay import LoadingOverlay, SpinnerLabel
from app.widgets.option_card import OptionCard
from app.widgets.toast import Toast, ToastSeverity


@pytest.fixture(autouse=True)
def _reset_event_bus():
    EventBus.reset()
    yield
    EventBus.reset()


# ==================================================================
# FieldWidget tests
# ==================================================================


class TestFieldWidget:
    def test_string_field_creates_line_edit(self, qtbot):
        schema = {"type": "string"}
        fw = FieldWidget("name", schema, value="hello")
        qtbot.addWidget(fw)
        assert isinstance(fw._input, QLineEdit)
        assert fw.get_value() == "hello"

    def test_enum_field_creates_combobox(self, qtbot):
        schema = {"type": "string", "enum": ["good", "neutral", "evil"]}
        fw = FieldWidget("alignment", schema, value="neutral")
        qtbot.addWidget(fw)
        assert isinstance(fw._input, QComboBox)
        assert fw.get_value() == "neutral"

    def test_array_field_creates_plaintextedit(self, qtbot):
        schema = {"type": "array"}
        fw = FieldWidget("tags", schema, value=["fire", "ice"])
        qtbot.addWidget(fw)
        assert isinstance(fw._input, QPlainTextEdit)
        result = fw.get_value()
        assert isinstance(result, list)
        assert "fire" in result
        assert "ice" in result

    def test_set_value_string(self, qtbot):
        schema = {"type": "string"}
        fw = FieldWidget("name", schema)
        qtbot.addWidget(fw)
        fw.set_value("Thor")
        assert fw.get_value() == "Thor"

    def test_set_value_array(self, qtbot):
        schema = {"type": "array"}
        fw = FieldWidget("tags", schema)
        qtbot.addWidget(fw)
        fw.set_value(["a", "b"])
        assert fw.get_value() == ["a", "b"]

    def test_set_validation_error(self, qtbot):
        schema = {"type": "string"}
        fw = FieldWidget("name", schema)
        qtbot.addWidget(fw)
        fw.set_validation(error="Required field")
        assert fw._indicator.text() == "X"
        assert fw._indicator.toolTip() == "Required field"

    def test_set_validation_warning(self, qtbot):
        schema = {"type": "string"}
        fw = FieldWidget("name", schema)
        qtbot.addWidget(fw)
        fw.set_validation(warning="Might conflict")
        assert fw._indicator.text() == "!"
        assert fw._indicator.toolTip() == "Might conflict"

    def test_clear_validation(self, qtbot):
        schema = {"type": "string"}
        fw = FieldWidget("name", schema)
        qtbot.addWidget(fw)
        fw.set_validation(error="bad")
        fw.clear_validation()
        assert fw._indicator.text() == ""

    def test_changed_signal_emitted(self, qtbot):
        schema = {"type": "string"}
        fw = FieldWidget("name", schema)
        qtbot.addWidget(fw)
        receiver = MagicMock()
        fw.changed.connect(receiver)
        fw._input.setText("new value")
        assert receiver.called


# ==================================================================
# EntityForm tests
# ==================================================================

_SIMPLE_SCHEMA = {
    "$id": "test-template",
    "properties": {
        "name": {"type": "string"},
        "alignment": {"type": "string", "enum": ["good", "neutral", "evil"]},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["name"],
}


class TestEntityForm:
    def test_load_schema_creates_fields(self, qtbot):
        form = EntityForm()
        qtbot.addWidget(form)
        form.load_schema(_SIMPLE_SCHEMA)
        assert "name" in form._fields
        assert "alignment" in form._fields
        assert "tags" in form._fields

    def test_get_data_returns_populated_values(self, qtbot):
        entity_data = {"name": "Thorin", "alignment": "neutral", "tags": ["storms"]}
        form = EntityForm(_SIMPLE_SCHEMA, entity_data)
        qtbot.addWidget(form)
        data = form.get_data()
        assert data["name"] == "Thorin"
        assert data["$id"] == "test-template"

    def test_set_validation_results(self, qtbot):
        form = EntityForm(_SIMPLE_SCHEMA, {"name": ""})
        qtbot.addWidget(form)
        form.set_validation_results({"name": "Name is required"})
        assert form._fields["name"]._indicator.text() == "X"
        # Other fields should be clear
        assert form._fields["alignment"]._indicator.text() == ""

    def test_save_requested_signal(self, qtbot):
        form = EntityForm(_SIMPLE_SCHEMA, {"name": "Test"})
        qtbot.addWidget(form)
        receiver = MagicMock()
        form.save_requested.connect(receiver)
        form._save_btn.click()
        assert receiver.called
        emitted_data = receiver.call_args[0][0]
        assert "name" in emitted_data

    def test_cancelled_signal(self, qtbot):
        form = EntityForm()
        qtbot.addWidget(form)
        receiver = MagicMock()
        form.cancelled.connect(receiver)
        form._cancel_btn.click()
        receiver.assert_called_once()


# ==================================================================
# OptionCard tests
# ==================================================================


class TestOptionCard:
    def test_creation(self, qtbot):
        card = OptionCard(
            option_id="opt-1",
            title="Storm Domain",
            description="A god of storms.",
        )
        qtbot.addWidget(card)
        assert card.option_id == "opt-1"

    def test_selected_signal(self, qtbot):
        card = OptionCard(
            option_id="opt-2",
            title="Fire Domain",
            description="A god of fire.",
        )
        qtbot.addWidget(card)
        receiver = MagicMock()
        card.selected.connect(receiver)
        card._select_btn.click()
        receiver.assert_called_once_with("opt-2")

    def test_set_selected_visual(self, qtbot):
        card = OptionCard(
            option_id="opt-3",
            title="Ice Domain",
            description="A god of ice.",
        )
        qtbot.addWidget(card)
        card.set_selected(True)
        assert "1565C0" in card.styleSheet()
        card.set_selected(False)
        assert card.styleSheet() == ""


# ==================================================================
# LoadingOverlay tests
# ==================================================================


class TestLoadingOverlay:
    def test_show_and_hide(self, qtbot):
        parent = QWidget()
        parent.resize(400, 300)
        qtbot.addWidget(parent)
        parent.show()
        overlay = LoadingOverlay(parent)
        assert not overlay.isVisible()
        overlay.show_loading("Loading...")
        assert overlay.isVisible()
        assert "Loading..." in overlay._label.text()
        overlay.hide_loading()
        assert not overlay.isVisible()

    def test_spinner_cycles(self, qtbot):
        parent = QWidget()
        parent.resize(400, 300)
        qtbot.addWidget(parent)
        overlay = LoadingOverlay(parent)
        overlay.show_loading("Working")
        first_text = overlay._label.text()
        overlay._tick()
        second_text = overlay._label.text()
        # The spinner character should have changed
        assert first_text != second_text
        overlay.hide_loading()


# ==================================================================
# SpinnerLabel tests
# ==================================================================


class TestSpinnerLabel:
    def test_start_makes_visible(self, qtbot):
        spinner = SpinnerLabel()
        qtbot.addWidget(spinner)
        spinner.start("Generating")
        assert spinner.isVisible()
        assert "Generating" in spinner.text()

    def test_stop_hides(self, qtbot):
        spinner = SpinnerLabel()
        qtbot.addWidget(spinner)
        spinner.start("Working")
        spinner.stop()
        assert not spinner.isVisible()
        assert spinner.text() == ""


# ==================================================================
# Toast tests
# ==================================================================


class TestToast:
    def test_toast_creation_info(self, qtbot):
        toast = Toast("Hello", ToastSeverity.INFO)
        qtbot.addWidget(toast)
        assert toast.text() == "Hello"
        assert "2196F3" in toast.styleSheet()  # blue border for info

    def test_toast_creation_error(self, qtbot):
        toast = Toast("Oops", ToastSeverity.ERROR)
        qtbot.addWidget(toast)
        assert toast.text() == "Oops"
        assert "F44336" in toast.styleSheet()  # red border for error

    def test_toast_severity_stored(self, qtbot):
        toast = Toast("warn", ToastSeverity.WARNING)
        qtbot.addWidget(toast)
        assert toast._severity == ToastSeverity.WARNING
