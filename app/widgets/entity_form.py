"""
app/widgets/entity_form.py -- Dynamic entity form widget.

Generates a form from a JSON schema / template definition, with per-field
validation indicators.  Supports strings, enums, arrays-of-strings,
arrays-of-objects (relationships), and booleans.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class FieldWidget(QWidget):
    """A single form field with label, input, and validation indicator."""

    changed = Signal()

    def __init__(
        self,
        field_name: str,
        schema: dict,
        value: Any = None,
        required: bool = False,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.field_name = field_name
        self._schema = schema
        self._required = required

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Build the appropriate input widget
        field_type = schema.get("type", "string")
        enum_values = schema.get("enum")

        if enum_values:
            self._input = QComboBox()
            self._input.addItem("(none)", "")
            for val in enum_values:
                display = str(val).replace("_", " ").title()
                self._input.addItem(display, val)
            if value:
                idx = self._input.findData(value)
                if idx >= 0:
                    self._input.setCurrentIndex(idx)
            self._input.currentIndexChanged.connect(lambda: self.changed.emit())

        elif field_type == "array":
            # Array of strings -- use multi-line text (comma separated)
            self._input = QPlainTextEdit()
            self._input.setMaximumHeight(60)
            self._input.setPlaceholderText("Comma-separated values...")
            if isinstance(value, list):
                self._input.setPlainText(", ".join(str(v) for v in value))
            self._input.textChanged.connect(self.changed.emit)

        elif field_type == "string" and len(schema.get("description", "")) > 50:
            # Long description fields get multi-line
            self._input = QPlainTextEdit()
            self._input.setMaximumHeight(80)
            if value:
                self._input.setPlainText(str(value))
            self._input.textChanged.connect(self.changed.emit)

        else:
            # Default: single-line text
            self._input = QLineEdit()
            if value:
                self._input.setText(str(value))
            desc = schema.get("description", "")
            if desc:
                self._input.setPlaceholderText(desc[:60])
            self._input.textChanged.connect(lambda: self.changed.emit())

        layout.addWidget(self._input, 1)

        # Validation indicator
        self._indicator = QLabel("")
        self._indicator.setFixedWidth(20)
        self._indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._indicator)

    def get_value(self) -> Any:
        """Get the current field value."""
        if isinstance(self._input, QComboBox):
            return self._input.currentData() or ""
        elif isinstance(self._input, QPlainTextEdit):
            text = self._input.toPlainText().strip()
            if self._schema.get("type") == "array":
                return [v.strip() for v in text.split(",") if v.strip()]
            return text
        else:
            return self._input.text().strip()

    def set_value(self, value: Any) -> None:
        """Set the field value."""
        if isinstance(self._input, QComboBox):
            idx = self._input.findData(value)
            if idx >= 0:
                self._input.setCurrentIndex(idx)
        elif isinstance(self._input, QPlainTextEdit):
            if isinstance(value, list):
                self._input.setPlainText(", ".join(str(v) for v in value))
            else:
                self._input.setPlainText(str(value or ""))
        else:
            self._input.setText(str(value or ""))

    def set_validation(self, error: str = "", warning: str = "") -> None:
        """Set the validation indicator."""
        if error:
            self._indicator.setText("X")
            self._indicator.setStyleSheet("color: #F44336; font-weight: bold;")
            self._indicator.setToolTip(error)
        elif warning:
            self._indicator.setText("!")
            self._indicator.setStyleSheet("color: #FFC107; font-weight: bold;")
            self._indicator.setToolTip(warning)
        else:
            self._indicator.setText("")
            self._indicator.setToolTip("")

    def clear_validation(self) -> None:
        self.set_validation()


class EntityForm(QWidget):
    """Dynamic form for editing an entity.

    Generates fields from a JSON schema template.

    Signals
    -------
    save_requested(dict)
        Emitted when user clicks Save.  Payload is the form data.
    cancelled()
        Emitted when user clicks Cancel.
    """

    save_requested = Signal(dict)
    cancelled = Signal()

    def __init__(
        self,
        template_schema: dict | None = None,
        entity_data: dict | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._schema = template_schema or {}
        self._entity_data = entity_data or {}
        self._fields: dict[str, FieldWidget] = {}
        self._setup_ui()

        if template_schema:
            self.load_schema(template_schema, entity_data)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # Scrollable form area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)

        self._form_widget = QWidget()
        self._form_layout = QFormLayout(self._form_widget)
        self._form_layout.setSpacing(6)
        self._form_layout.setContentsMargins(8, 8, 8, 8)

        self._scroll.setWidget(self._form_widget)
        outer.addWidget(self._scroll, 1)

        # Status row
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #888; font-size: 11px;")
        outer.addWidget(self._status_label)

        # Button row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self.cancelled.emit)
        btn_row.addWidget(self._cancel_btn)

        btn_row.addStretch()

        self._save_btn = QPushButton("Save Entity")
        self._save_btn.setStyleSheet(
            "background-color: #2E7D32; padding: 6px 20px; font-weight: bold;"
        )
        self._save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self._save_btn)

        outer.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Schema loading
    # ------------------------------------------------------------------

    def load_schema(
        self,
        schema: dict,
        entity_data: dict | None = None,
    ) -> None:
        """Build form fields from a JSON schema."""
        self._schema = schema
        self._entity_data = entity_data or {}

        # Clear existing fields
        for fw in self._fields.values():
            self._form_layout.removeRow(fw)
        self._fields.clear()

        properties = schema.get("properties", {})
        required_fields = set(schema.get("required", []))

        # Skip internal/meta fields
        skip_fields = {"$id", "$schema", "type", "title", "description",
                       "step", "phase", "source_chapter", "_meta",
                       "canon_claims", "x-cross-references"}

        for field_name, field_schema in properties.items():
            if field_name in skip_fields:
                continue

            # Handle nested objects (like relationships) as a group
            if field_schema.get("type") == "array" and field_schema.get("items", {}).get("type") == "object":
                self._add_relationship_group(field_name, field_schema, entity_data)
                continue

            is_required = field_name in required_fields
            value = (entity_data or {}).get(field_name)

            display_name = field_name.replace("_", " ").title()
            if is_required:
                display_name += " *"

            fw = FieldWidget(field_name, field_schema, value, is_required)
            self._form_layout.addRow(display_name, fw)
            self._fields[field_name] = fw

        self._update_status()

    def _add_relationship_group(
        self, field_name: str, field_schema: dict, entity_data: dict | None
    ) -> None:
        """Add a simple text area for relationship arrays."""
        display_name = field_name.replace("_", " ").title()

        # For now, serialize as text. Sprint 7 will add proper relationship editing.
        group_schema = {"type": "string", "description": f"{display_name} (JSON array)"}
        value = (entity_data or {}).get(field_name)

        if isinstance(value, list):
            import json
            text_value = json.dumps(value, indent=2)
        else:
            text_value = ""

        fw = FieldWidget(field_name, group_schema, text_value,
                         field_name in set(self._schema.get("required", [])))
        self._form_layout.addRow(f"{display_name}:", fw)
        self._fields[field_name] = fw

    # ------------------------------------------------------------------
    # Data access
    # ------------------------------------------------------------------

    def get_data(self) -> dict:
        """Collect all form field values into a dict."""
        data = {}
        for name, fw in self._fields.items():
            val = fw.get_value()
            if val or val == 0 or val is False:
                # Try to parse JSON for relationship fields
                if isinstance(val, str) and val.startswith("["):
                    import json
                    try:
                        val = json.loads(val)
                    except json.JSONDecodeError:
                        pass
                data[name] = val

        # Preserve template ID if present
        template_id = self._schema.get("$id", "")
        if template_id:
            data["$id"] = template_id

        return data

    def set_validation_results(self, error_fields: dict[str, str]) -> None:
        """Apply per-field validation indicators.

        Parameters
        ----------
        error_fields : dict[str, str]
            Mapping of field_name -> error message.
        """
        # Clear all first
        for fw in self._fields.values():
            fw.clear_validation()

        # Set errors
        for field_name, message in error_fields.items():
            if field_name in self._fields:
                self._fields[field_name].set_validation(error=message)

    def _update_status(self) -> None:
        filled = sum(1 for fw in self._fields.values() if fw.get_value())
        total = len(self._fields)
        self._status_label.setText(f"{filled}/{total} fields filled")

    def _on_save(self) -> None:
        data = self.get_data()
        self.save_requested.emit(data)
