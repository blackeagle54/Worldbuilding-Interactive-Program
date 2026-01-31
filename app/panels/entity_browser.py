"""
app/panels/entity_browser.py -- Entity Browser dock panel.

Searchable, filterable table of all entities in the world.
Supports text search, type/status dropdown filters, right-click context menu,
and emits entity_selected via EventBus when an entity is clicked.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import (
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
    QTimer,
)
from PySide6.QtGui import QAction, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app.services.event_bus import EventBus
from app.widgets.loading_overlay import LoadingOverlay

logger = logging.getLogger(__name__)

# Column indices
COL_NAME = 0
COL_TYPE = 1
COL_STATUS = 2

# Custom role for storing entity ID in model items
ENTITY_ID_ROLE = Qt.ItemDataRole.UserRole + 1


class EntityFilterProxy(QSortFilterProxyModel):
    """Proxy that filters by text search, entity type, and status."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._type_filter: str = ""
        self._status_filter: str = ""
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setFilterKeyColumn(-1)  # Search all columns

    def set_type_filter(self, entity_type: str) -> None:
        self._type_filter = entity_type
        self.invalidateFilter()

    def set_status_filter(self, status: str) -> None:
        self._status_filter = status
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model = self.sourceModel()
        if model is None:
            return True

        # Text search filter (from QSortFilterProxyModel)
        if not super().filterAcceptsRow(source_row, source_parent):
            return False

        # Type filter
        if self._type_filter:
            type_idx = model.index(source_row, COL_TYPE, source_parent)
            if model.data(type_idx) != self._type_filter:
                return False

        # Status filter
        if self._status_filter:
            status_idx = model.index(source_row, COL_STATUS, source_parent)
            if model.data(status_idx) != self._status_filter:
                return False

        return True


class EntityBrowserPanel(QWidget):
    """Searchable entity list panel with filtering and context menu."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._engine = None  # Set via set_engine()
        self._bus = EventBus.instance()
        self._setup_ui()
        self._connect_signals()

    def set_engine(self, engine_manager: Any) -> None:
        """Inject the EngineManager after construction."""
        self._engine = engine_manager
        self.refresh()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Search bar
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search entities...")
        self._search.setClearButtonEnabled(True)
        layout.addWidget(self._search)

        # Filter row
        filter_row = QHBoxLayout()
        filter_row.setSpacing(4)

        filter_row.addWidget(QLabel("Type:"))
        self._type_combo = QComboBox()
        self._type_combo.addItem("All", "")
        self._type_combo.setMinimumWidth(100)
        filter_row.addWidget(self._type_combo)

        filter_row.addWidget(QLabel("Status:"))
        self._status_combo = QComboBox()
        self._status_combo.addItem("All", "")
        self._status_combo.addItem("Draft", "draft")
        self._status_combo.addItem("Canon", "canon")
        self._status_combo.setMinimumWidth(80)
        filter_row.addWidget(self._status_combo)

        filter_row.addStretch()

        # Entity count label
        self._count_label = QLabel("0 entities")
        self._count_label.setStyleSheet("color: #888; font-size: 11px;")
        filter_row.addWidget(self._count_label)

        layout.addLayout(filter_row)

        # Model
        self._model = QStandardItemModel(0, 3, self)
        self._model.setHorizontalHeaderLabels(["Name", "Type", "Status"])

        # Proxy
        self._proxy = EntityFilterProxy(self)
        self._proxy.setSourceModel(self._model)
        self._proxy.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

        # Table view
        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)

        # Column sizing
        header = self._table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_TYPE, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeMode.ResizeToContents)

        layout.addWidget(self._table, 1)

        # Loading overlay
        self._loading = LoadingOverlay(self._table)

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        # Search with debounce
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)
        self._search_timer.timeout.connect(self._apply_search)
        self._search.textChanged.connect(lambda _: self._search_timer.start())

        # Filter combos
        self._type_combo.currentIndexChanged.connect(self._on_type_filter_changed)
        self._status_combo.currentIndexChanged.connect(self._on_status_filter_changed)

        # Selection
        self._table.clicked.connect(self._on_row_clicked)

        # Context menu
        self._table.customContextMenuRequested.connect(self._on_context_menu)

        # EventBus -- react to external changes
        self._bus.entity_created.connect(lambda _: self.refresh())
        self._bus.entity_updated.connect(lambda _: self.refresh())
        self._bus.entity_deleted.connect(lambda _: self.refresh())

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Reload the entity list from the engine."""
        if self._engine is None:
            return

        self._loading.show_loading("Loading entities...")
        try:
            dm = self._engine.data_manager
            entities = self._engine.with_lock("data_manager", lambda d: d.list_entities())
        except Exception:
            logger.exception("Failed to load entity list")
            self._loading.hide_loading()
            return

        self._model.removeRows(0, self._model.rowCount())

        # Track unique types for the filter combo
        entity_types: set[str] = set()

        for ent in entities:
            name_item = QStandardItem(ent.get("name", "(unnamed)"))
            name_item.setData(ent.get("id", ""), ENTITY_ID_ROLE)

            etype = ent.get("entity_type", "unknown")
            entity_types.add(etype)
            type_item = QStandardItem(etype)

            status = ent.get("status", "draft")
            status_item = QStandardItem(status)

            self._model.appendRow([name_item, type_item, status_item])

        # Update type filter combo (preserving current selection)
        current_type = self._type_combo.currentData()
        self._type_combo.blockSignals(True)
        self._type_combo.clear()
        self._type_combo.addItem("All", "")
        for t in sorted(entity_types):
            display = t.replace("_", " ").replace("-", " ").title()
            self._type_combo.addItem(display, t)
        # Restore selection
        idx = self._type_combo.findData(current_type)
        if idx >= 0:
            self._type_combo.setCurrentIndex(idx)
        self._type_combo.blockSignals(False)

        self._update_count_label()
        self._loading.hide_loading()

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _apply_search(self) -> None:
        text = self._search.text()
        self._proxy.setFilterFixedString(text)
        self._update_count_label()

    def _on_type_filter_changed(self, _index: int) -> None:
        self._proxy.set_type_filter(self._type_combo.currentData() or "")
        self._update_count_label()

    def _on_status_filter_changed(self, _index: int) -> None:
        self._proxy.set_status_filter(self._status_combo.currentData() or "")
        self._update_count_label()

    def _on_row_clicked(self, index: QModelIndex) -> None:
        source_index = self._proxy.mapToSource(index)
        name_item = self._model.item(source_index.row(), COL_NAME)
        if name_item:
            entity_id = name_item.data(ENTITY_ID_ROLE)
            if entity_id:
                self._bus.entity_selected.emit(entity_id)

    def _on_context_menu(self, position) -> None:
        index = self._table.indexAt(position)
        if not index.isValid():
            return

        source_index = self._proxy.mapToSource(index)
        name_item = self._model.item(source_index.row(), COL_NAME)
        if not name_item:
            return

        entity_id = name_item.data(ENTITY_ID_ROLE)
        entity_name = name_item.text()

        menu = QMenu(self)

        select_action = QAction(f"Select '{entity_name}'", self)
        select_action.triggered.connect(lambda: self._bus.entity_selected.emit(entity_id))
        menu.addAction(select_action)

        menu.addSeparator()

        set_canon = QAction("Set Status: Canon", self)
        set_canon.triggered.connect(lambda: self._set_status(entity_id, "canon"))
        menu.addAction(set_canon)

        set_draft = QAction("Set Status: Draft", self)
        set_draft.triggered.connect(lambda: self._set_status(entity_id, "draft"))
        menu.addAction(set_draft)

        menu.exec(self._table.viewport().mapToGlobal(position))

    def _set_status(self, entity_id: str, status: str) -> None:
        """Change entity status via the engine."""
        if self._engine is None:
            return
        try:
            self._engine.with_lock(
                "data_manager", lambda dm: dm.set_entity_status(entity_id, status)
            )
            self._bus.entity_updated.emit(entity_id)
            self._bus.status_message.emit(f"Set {entity_id} to {status}")
        except Exception as e:
            self._bus.error_occurred.emit(str(e))

    def _update_count_label(self) -> None:
        visible = self._proxy.rowCount()
        total = self._model.rowCount()
        if visible == total:
            self._count_label.setText(f"{total} entities")
        else:
            self._count_label.setText(f"{visible} / {total} entities")

    # ------------------------------------------------------------------
    # External selection (from other panels)
    # ------------------------------------------------------------------

    def select_entity(self, entity_id: str) -> None:
        """Highlight a specific entity row (called from other panels)."""
        for row in range(self._model.rowCount()):
            item = self._model.item(row, COL_NAME)
            if item and item.data(ENTITY_ID_ROLE) == entity_id:
                proxy_index = self._proxy.mapFromSource(item.index())
                if proxy_index.isValid():
                    self._table.selectRow(proxy_index.row())
                    self._table.scrollTo(proxy_index)
                break
