"""
app/widgets/relationship_editor.py -- Relationship editor widget.

Provides a proper UI for viewing, adding, and removing relationships on an
entity.  Replaces the raw JSON text area that was previously used as a
workaround in EntityForm.

Features:
- Table of current relationships (type, target entity name, remove button)
- Add-relationship row with entity search/autocomplete and type dropdown
- Validated relationship types
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

# Canonical relationship types used throughout the worldbuilding system.
RELATIONSHIP_TYPES: list[str] = [
    "parent_of",
    "child_of",
    "related_to",
    "part_of",
    "contains",
    "influences",
    "influenced_by",
    "conflicts_with",
    "allied_with",
]


def _display_rel_type(rel_type: str) -> str:
    """Convert a relationship type slug to a human-readable label."""
    return rel_type.replace("_", " ").title()


class _RelationshipRow(QWidget):
    """A single row representing one existing relationship."""

    remove_requested = Signal(int)  # row index

    def __init__(
        self,
        index: int,
        rel_type: str,
        target_id: str,
        target_name: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.index = index
        self.rel_type = rel_type
        self.target_id = target_id

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 1, 2, 1)
        layout.setSpacing(6)

        # Relationship type label
        type_label = QLabel(_display_rel_type(rel_type))
        type_label.setStyleSheet("color: #90CAF9; font-weight: bold;")
        type_label.setFixedWidth(110)
        layout.addWidget(type_label)

        # Arrow
        arrow_label = QLabel("->")
        arrow_label.setStyleSheet("color: #666;")
        arrow_label.setFixedWidth(20)
        layout.addWidget(arrow_label)

        # Target entity name
        display = target_name or target_id
        target_label = QLabel(display)
        target_label.setToolTip(f"Entity ID: {target_id}")
        target_label.setStyleSheet("color: #CCCCCC;")
        layout.addWidget(target_label, 1)

        # Remove button
        remove_btn = QPushButton("X")
        remove_btn.setFixedSize(22, 22)
        remove_btn.setStyleSheet(
            "QPushButton { color: #F44336; border: 1px solid #555; border-radius: 3px; }"
            "QPushButton:hover { background-color: #F44336; color: white; }"
        )
        remove_btn.setToolTip("Remove this relationship")
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self.index))
        layout.addWidget(remove_btn)


class RelationshipEditor(QWidget):
    """Widget for editing an entity's relationships.

    Displays a list of current relationships and an add-relationship row.

    Signals
    -------
    relationship_added(str, str)
        Emitted when the user adds a relationship.
        Payload is (relationship_type, target_entity_id).
    relationship_removed(int)
        Emitted when the user removes a relationship by index.
    changed()
        Emitted whenever the relationship list is modified.
    """

    relationship_added = Signal(str, str)   # rel_type, target_id
    relationship_removed = Signal(int)       # index in the list
    changed = Signal()

    def __init__(
        self,
        field_name: str = "relationships",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.field_name = field_name

        # Internal relationship data: list of dicts with at least
        # "relationship_type" and "target_id" keys.
        self._relationships: list[dict] = []

        # Entity catalog for autocomplete: {entity_id: display_name}
        self._entity_catalog: dict[str, str] = {}

        self._setup_ui()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        # Group box
        self._group = QGroupBox(self.field_name.replace("_", " ").title())
        group_layout = QVBoxLayout(self._group)
        group_layout.setContentsMargins(6, 10, 6, 6)
        group_layout.setSpacing(2)

        # Container for relationship rows
        self._rows_container = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(2)
        group_layout.addWidget(self._rows_container)

        # Empty state label
        self._empty_label = QLabel("No relationships yet.")
        self._empty_label.setStyleSheet("color: #666; font-style: italic; font-size: 11px;")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._rows_layout.addWidget(self._empty_label)

        # Separator
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #444;")
        group_layout.addWidget(sep)

        # Add-relationship row
        add_row = QHBoxLayout()
        add_row.setSpacing(6)

        # Relationship type dropdown
        self._type_combo = QComboBox()
        self._type_combo.setFixedWidth(140)
        for rel_type in RELATIONSHIP_TYPES:
            self._type_combo.addItem(_display_rel_type(rel_type), rel_type)
        add_row.addWidget(self._type_combo)

        # Target entity search input with autocomplete
        self._target_input = QLineEdit()
        self._target_input.setPlaceholderText("Search entity by name or ID...")
        self._target_input.returnPressed.connect(self._on_add_clicked)
        add_row.addWidget(self._target_input, 1)

        # Completer (populated when entity catalog is set)
        self._completer = QCompleter([], self)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._target_input.setCompleter(self._completer)

        # Add button
        self._add_btn = QPushButton("+ Add")
        self._add_btn.setFixedWidth(60)
        self._add_btn.setStyleSheet(
            "QPushButton { background-color: #1B5E20; padding: 4px; }"
            "QPushButton:hover { background-color: #2E7D32; }"
        )
        self._add_btn.clicked.connect(self._on_add_clicked)
        add_row.addWidget(self._add_btn)

        group_layout.addLayout(add_row)
        outer.addWidget(self._group)

    # ------------------------------------------------------------------
    # Entity catalog (for autocomplete)
    # ------------------------------------------------------------------

    def set_entity_catalog(self, catalog: dict[str, str]) -> None:
        """Set the available entities for autocomplete.

        Parameters
        ----------
        catalog : dict[str, str]
            Mapping of entity_id -> display_name.
        """
        self._entity_catalog = dict(catalog)
        # Build completion strings as "Name (entity-id)"
        completions = []
        for eid, name in catalog.items():
            completions.append(f"{name} ({eid})")
        self._completer.model().setStringList(completions)

    # ------------------------------------------------------------------
    # Data access
    # ------------------------------------------------------------------

    def set_relationships(self, relationships: list[dict]) -> None:
        """Load a list of relationship dicts into the editor.

        Each dict should have at minimum ``relationship_type`` and
        ``target_id`` keys.  Additional keys are preserved.
        """
        self._relationships = list(relationships) if relationships else []
        self._rebuild_rows()

    def get_relationships(self) -> list[dict]:
        """Return the current list of relationship dicts."""
        return list(self._relationships)

    def get_value(self) -> list[dict]:
        """Alias for get_relationships, for compatibility with EntityForm."""
        return self.get_relationships()

    # ------------------------------------------------------------------
    # Row management
    # ------------------------------------------------------------------

    def _rebuild_rows(self) -> None:
        """Clear and re-create all relationship row widgets."""
        # Remove existing row widgets
        while self._rows_layout.count() > 0:
            item = self._rows_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        if not self._relationships:
            self._empty_label = QLabel("No relationships yet.")
            self._empty_label.setStyleSheet(
                "color: #666; font-style: italic; font-size: 11px;"
            )
            self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._rows_layout.addWidget(self._empty_label)
            return

        for idx, rel in enumerate(self._relationships):
            rel_type = rel.get("relationship_type", "related_to")
            target_id = rel.get("target_id", "")
            target_name = self._entity_catalog.get(target_id, "")
            row = _RelationshipRow(idx, rel_type, target_id, target_name, self)
            row.remove_requested.connect(self._on_remove)
            self._rows_layout.addWidget(row)

    def _on_add_clicked(self) -> None:
        """Handle the Add button click."""
        rel_type = self._type_combo.currentData()
        raw_text = self._target_input.text().strip()

        if not raw_text:
            return

        # Parse target entity ID from the autocomplete format "Name (entity-id)"
        target_id = self._resolve_target(raw_text)
        if not target_id:
            return

        # Check for duplicate
        for rel in self._relationships:
            if rel.get("target_id") == target_id and rel.get("relationship_type") == rel_type:
                logger.debug("Duplicate relationship, skipping: %s -> %s", rel_type, target_id)
                return

        new_rel = {
            "relationship_type": rel_type,
            "target_id": target_id,
        }
        self._relationships.append(new_rel)
        self._rebuild_rows()

        # Clear input
        self._target_input.clear()

        self.relationship_added.emit(rel_type, target_id)
        self.changed.emit()

    def _on_remove(self, index: int) -> None:
        """Remove the relationship at *index*."""
        if 0 <= index < len(self._relationships):
            self._relationships.pop(index)
            self._rebuild_rows()
            self.relationship_removed.emit(index)
            self.changed.emit()

    def _resolve_target(self, text: str) -> str:
        """Resolve user input to an entity ID.

        Accepts:
        - "Name (entity-id)" format from autocomplete
        - A raw entity ID
        - An entity name (looked up in the catalog)
        """
        # Try "Name (entity-id)" format
        if "(" in text and text.endswith(")"):
            inner = text[text.rfind("(") + 1 : -1].strip()
            if inner in self._entity_catalog:
                return inner
            # It might still be a valid ID even if not in catalog
            return inner

        # Try direct entity ID match
        if text in self._entity_catalog:
            return text

        # Try name-to-id lookup
        for eid, name in self._entity_catalog.items():
            if name.lower() == text.lower():
                return eid

        # Last resort: treat the raw text as an entity ID
        # (could be a new / not-yet-indexed entity)
        return text
