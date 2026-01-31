"""
app/panels/entity_detail.py -- Entity Detail View.

Dialog/panel for viewing and editing a single entity with dynamic form,
per-field validation, status toggle, and related entities display.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.services.event_bus import EventBus
from app.widgets.entity_form import EntityForm

logger = logging.getLogger(__name__)


class EntityDetailView(QDialog):
    """Dialog for viewing and editing a single entity.

    Parameters
    ----------
    entity_id : str
        The entity ID (empty for new entity creation).
    template_id : str
        The template/schema ID.
    engine_manager : EngineManager
        For loading entity data and templates.
    enforcement : EnforcementService | None
        For validation on save.
    parent : QWidget | None
        Parent widget.
    """

    entity_saved = Signal(str)  # entity_id

    def __init__(
        self,
        entity_id: str = "",
        template_id: str = "",
        engine_manager: Any = None,
        enforcement: Any = None,
        entity_data: dict | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._entity_id = entity_id
        self._template_id = template_id
        self._engine = engine_manager
        self._enforcement = enforcement
        self._bus = EventBus.instance()

        self.setWindowTitle(
            f"Edit Entity: {entity_id}" if entity_id else "New Entity"
        )
        self.setMinimumSize(700, 500)
        self.resize(800, 600)

        self._setup_ui()
        self._load_entity(entity_data)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Header
        header = QHBoxLayout()

        self._title_label = QLabel("Entity")
        self._title_label.setStyleSheet("font-weight: bold; font-size: 16px;")
        header.addWidget(self._title_label)

        header.addStretch()

        # Status toggle
        header.addWidget(QLabel("Status:"))
        self._status_combo = QComboBox()
        self._status_combo.addItem("Draft", "draft")
        self._status_combo.addItem("Canon", "canon")
        header.addWidget(self._status_combo)

        layout.addLayout(header)

        # Splitter: form on left, sidebar on right
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Form
        self._form = EntityForm()
        self._form.save_requested.connect(self._on_save)
        self._form.cancelled.connect(self.reject)
        splitter.addWidget(self._form)

        # Sidebar
        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(4, 4, 4, 4)

        # Related entities
        related_group = QGroupBox("Related Entities")
        related_layout = QVBoxLayout(related_group)
        self._related_list = QListWidget()
        self._related_list.setMaximumHeight(200)
        related_layout.addWidget(self._related_list)
        sidebar_layout.addWidget(related_group)

        # Validation summary
        val_group = QGroupBox("Validation")
        val_layout = QVBoxLayout(val_group)
        self._validation_label = QLabel("Not yet validated")
        self._validation_label.setWordWrap(True)
        self._validation_label.setStyleSheet("font-size: 11px;")
        val_layout.addWidget(self._validation_label)
        sidebar_layout.addWidget(val_group)

        sidebar_layout.addStretch()
        splitter.addWidget(sidebar)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter, 1)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_entity(self, entity_data: dict | None = None) -> None:
        """Load entity data and template schema into the form."""
        schema = {}
        data = entity_data or {}

        # Load template schema
        if self._engine and self._template_id:
            try:
                schema = self._engine.with_lock(
                    "data_manager",
                    lambda d: d._get_template_schema(self._template_id),
                )
            except Exception:
                logger.debug("Could not load template: %s", self._template_id, exc_info=True)

        # Load existing entity data
        if self._engine and self._entity_id and not entity_data:
            try:
                data = self._engine.with_lock(
                    "data_manager",
                    lambda d: d.get_entity(self._entity_id),
                )
                # Set status
                status = data.get("_meta", {}).get("status", data.get("status", "draft"))
                idx = self._status_combo.findData(status)
                if idx >= 0:
                    self._status_combo.setCurrentIndex(idx)
            except Exception:
                logger.debug("Could not load entity: %s", self._entity_id, exc_info=True)

        # Update title
        name = data.get("name", data.get("title", self._entity_id or "New Entity"))
        self._title_label.setText(name)

        # Build entity catalog for relationship autocomplete
        self._load_entity_catalog()

        # Load form
        if schema:
            self._form.load_schema(schema, data)
        elif data:
            # No schema but have data -- create minimal schema from data keys
            auto_schema = {
                "properties": {k: {"type": "string"} for k in data if not k.startswith("_")},
                "required": [],
            }
            self._form.load_schema(auto_schema, data)

        # Push the entity catalog into the form's relationship editors
        self._form.set_entity_catalog(self._entity_catalog)

        # Load related entities
        self._load_related()

    def _load_entity_catalog(self) -> None:
        """Build a mapping of entity_id -> display_name for autocomplete."""
        self._entity_catalog: dict[str, str] = {}

        if not self._engine:
            return

        try:
            entities = self._engine.with_lock(
                "data_manager",
                lambda d: d.list_entities(),
            )
            for entry in entities:
                eid = entry.get("id", "")
                name = entry.get("name", eid)
                if eid:
                    self._entity_catalog[eid] = name
        except Exception:
            logger.debug("Could not load entity catalog", exc_info=True)

    def _load_related(self) -> None:
        """Load related entities into the sidebar."""
        self._related_list.clear()

        if not self._engine or not self._entity_id:
            self._related_list.addItem("(Save entity to see relationships)")
            return

        try:
            xrefs = self._engine.with_lock(
                "data_manager",
                lambda d: d.get_cross_references(self._entity_id),
            )
            refs = xrefs.get("references", [])
            ref_by = xrefs.get("referenced_by", [])

            if not refs and not ref_by:
                self._related_list.addItem("(No relationships)")
                return

            for ref in refs:
                name = ref.get("name", ref.get("id", "?"))
                rel = ref.get("relationship", "references")
                self._related_list.addItem(f"-> {name} ({rel})")

            for ref in ref_by:
                name = ref.get("name", ref.get("id", "?"))
                rel = ref.get("relationship", "referenced by")
                self._related_list.addItem(f"<- {name} ({rel})")

        except Exception:
            self._related_list.addItem("(Could not load relationships)")

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _on_save(self, form_data: dict) -> None:
        """Handle form save request."""
        if not self._enforcement:
            self._save_direct(form_data)
            return

        # Validate through enforcement pipeline
        data = dict(form_data)
        template_id = data.pop("$id", self._template_id)
        result, saved_id = self._enforcement.validate_and_save_entity(
            data, template_id, self._entity_id or None,
        )

        if result.passed and saved_id:
            self._entity_id = saved_id
            self._validation_label.setText("Validation passed. Entity saved.")
            self._validation_label.setStyleSheet("color: #4CAF50; font-size: 11px;")

            # Apply field-level validation (warnings)
            field_errors = {}
            for issue in result.warnings:
                if issue.field:
                    field_errors[issue.field] = issue.message
            self._form.set_validation_results(field_errors)

            self.entity_saved.emit(saved_id)
            self._bus.status_message.emit(f"Saved: {data.get('name', saved_id)}")
            self.accept()
        else:
            # Show validation errors
            error_text = result.format_human()
            self._validation_label.setText(error_text)
            self._validation_label.setStyleSheet("color: #F44336; font-size: 11px;")

            # Apply field-level highlighting
            field_errors = {}
            for issue in result.errors:
                if issue.field:
                    field_errors[issue.field] = issue.message
            for issue in result.warnings:
                if issue.field and issue.field not in field_errors:
                    field_errors[issue.field] = issue.message
            self._form.set_validation_results(field_errors)

    def _save_direct(self, form_data: dict) -> None:
        """Save without enforcement (fallback)."""
        if not self._engine:
            return

        try:
            data = dict(form_data)
            template_id = data.pop("$id", self._template_id)

            if self._entity_id:
                self._engine.with_lock(
                    "data_manager",
                    lambda d: d.update_entity(self._entity_id, data),
                )
                saved_id = self._entity_id
                self._bus.entity_updated.emit(saved_id)
            else:
                saved_id = self._engine.with_lock(
                    "data_manager",
                    lambda d: d.create_entity(template_id, data),
                )
                self._bus.entity_created.emit(saved_id)

            self.entity_saved.emit(saved_id)
            self.accept()

        except Exception as e:
            QMessageBox.warning(self, "Save Failed", str(e))
