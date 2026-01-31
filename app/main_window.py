"""
app/main_window.py -- Main application window.

Hosts the 4 dock panels (entity browser, knowledge graph, chat, progress),
a menu bar with View toggles, and status bar.  Layout is saved/restored
across sessions via QSettings.  Cross-panel sync is wired through EventBus.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QDockWidget,
    QMainWindow,
    QStatusBar,
    QWidget,
)

from app.panels.chat_panel import ChatPanel
from app.panels.entity_browser import EntityBrowserPanel
from app.panels.knowledge_graph import KnowledgeGraphPanel
from app.panels.option_comparison import OptionComparisonPanel
from app.panels.progress_sidebar import ProgressSidebarPanel
from app.services.agent_worker import AgentWorker
from app.services.claude_client import ClaudeClient
from app.services.enforcement import EnforcementService
from app.services.event_bus import EventBus
from app.services.session_manager import SessionManager
from app.services.state_store import StateStore
from app.widgets.toast import ToastManager

logger = logging.getLogger(__name__)

_ORG_NAME = "WorldbuildingApp"
_APP_NAME = "WorldbuildingInteractiveProgram"


class MainWindow(QMainWindow):
    """Main application window with dockable panels.

    Layout
    ------
    Default arrangement::

        +----------+------------------+----------+
        | Entity   |                  | Progress |
        | Browser  |  Knowledge Graph | Sidebar  |
        | (Left)   |  (Center)        | (Right)  |
        |          |                  |          |
        +----------+------------------+----------+
        |            Chat Panel                  |
        |            (Bottom)                    |
        +-----------------------------------------+
    """

    def __init__(self, project_root: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._project_root = project_root
        self._settings = QSettings(_ORG_NAME, _APP_NAME)

        self.setWindowTitle("Worldbuilding Interactive Program")
        self.setMinimumSize(1024, 768)

        # Create panel instances
        self._graph_panel = KnowledgeGraphPanel()
        self._entity_panel = EntityBrowserPanel()
        self._progress_panel = ProgressSidebarPanel()
        self._chat_panel = ChatPanel()
        self._option_panel = OptionComparisonPanel()

        # Central widget -- the knowledge graph fills the center
        self.setCentralWidget(self._graph_panel)

        # Create dock panels
        self._entity_dock = self._create_dock(
            "Entity Browser", self._entity_panel, Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self._progress_dock = self._create_dock(
            "Progress", self._progress_panel, Qt.DockWidgetArea.RightDockWidgetArea
        )
        self._chat_dock = self._create_dock(
            "Chat", self._chat_panel, Qt.DockWidgetArea.BottomDockWidgetArea
        )
        self._option_dock = self._create_dock(
            "Options", self._option_panel, Qt.DockWidgetArea.BottomDockWidgetArea
        )
        # Tab the options dock behind the chat dock by default
        self.tabifyDockWidget(self._chat_dock, self._option_dock)

        # Menu bar
        self._build_menus()

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Ready")

        # Toast notification manager
        self._toast = ToastManager(self)

        # Connect EventBus status messages
        self._bus = bus = EventBus.instance()
        bus.status_message.connect(self._on_status_message)
        bus.error_occurred.connect(self._on_error)

        # Cross-panel entity selection sync
        bus.entity_selected.connect(self._on_entity_selected)

        # Rebuild system prompt when step changes
        bus.step_changed.connect(lambda _: self._update_system_prompt())

        # Option selection -> open entity form with selected data
        self._option_panel.option_selected.connect(self._on_option_selected)

        # Keyboard shortcuts
        self._setup_shortcuts()

        # Restore layout from previous session
        self._restore_layout()

    # ------------------------------------------------------------------
    # Engine / state injection
    # ------------------------------------------------------------------

    def inject_engine(self, engine_manager: Any) -> None:
        """Wire the engine into panels that need it."""
        self._engine = engine_manager
        self._entity_panel.set_engine(engine_manager)
        self._graph_panel.set_engine(engine_manager)

    def inject_state_store(self, store: StateStore) -> None:
        """Wire the state store into panels that need it."""
        self._progress_panel.set_state_store(store)

    def inject_enforcement(self, enforcement: EnforcementService) -> None:
        """Wire the enforcement service for validation and bookkeeping."""
        self._enforcement = enforcement
        self._option_panel.set_enforcement(enforcement)

    def inject_session_manager(self, session_mgr: SessionManager) -> None:
        """Wire the session manager for auto-save and step advancement."""
        self._session_mgr = session_mgr
        self._progress_panel.set_session_manager(session_mgr)

    def inject_claude(self, client: ClaudeClient) -> None:
        """Wire the Claude client into the chat panel."""
        self._claude_client = client
        self._agent_worker = AgentWorker(client, parent=self)
        self._chat_panel.set_worker(self._agent_worker)

        # Show backend status
        backend_name = client.backend.name.lower()
        if client.is_online:
            self._chat_panel.set_backend_label(f"Claude: {backend_name}")
        else:
            self._chat_panel.set_backend_label("Claude: offline")

        # Build initial system prompt
        self._update_system_prompt()

    def _update_system_prompt(self) -> None:
        """Rebuild the system prompt from current step context."""
        if not hasattr(self, "_engine") or self._engine is None:
            return
        if not hasattr(self, "_claude_client"):
            return

        try:
            from app.services.context_builder import build_context
            from app.services.state_store import StateStore

            store = StateStore.instance()
            step = store.current_step

            context = build_context(self._engine, step)
            self._chat_panel.set_system_prompt(context["system_prompt"])
            self._claude_client.set_current_step(step)

            # Update enforcement service step
            if hasattr(self, "_enforcement") and self._enforcement:
                self._enforcement.set_current_step(step)
        except Exception:
            logger.debug("Failed to build system prompt", exc_info=True)

    # ------------------------------------------------------------------
    # Dock creation helper
    # ------------------------------------------------------------------

    def _create_dock(
        self,
        title: str,
        widget: QWidget,
        area: Qt.DockWidgetArea,
    ) -> QDockWidget:
        """Create a dock widget and add it to the window."""
        dock = QDockWidget(title, self)
        dock.setObjectName(f"dock_{title.lower().replace(' ', '_')}")
        dock.setWidget(widget)
        dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.BottomDockWidgetArea
            | Qt.DockWidgetArea.TopDockWidgetArea
        )
        self.addDockWidget(area, dock)
        return dock

    # ------------------------------------------------------------------
    # Menu bar
    # ------------------------------------------------------------------

    def _build_menus(self) -> None:
        """Build the menu bar with View toggles and layout actions."""
        menubar = self.menuBar()

        # --- View menu ---
        view_menu = menubar.addMenu("&View")

        # Dock toggle actions
        view_menu.addAction(self._entity_dock.toggleViewAction())
        view_menu.addAction(self._progress_dock.toggleViewAction())
        view_menu.addAction(self._chat_dock.toggleViewAction())
        view_menu.addAction(self._option_dock.toggleViewAction())

        view_menu.addSeparator()

        # Reset layout
        reset_action = QAction("Reset Layout", self)
        reset_action.triggered.connect(self._reset_layout)
        view_menu.addAction(reset_action)

        # --- Help menu ---
        help_menu = menubar.addMenu("&Help")

        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    # ------------------------------------------------------------------
    # Keyboard shortcuts
    # ------------------------------------------------------------------

    def _setup_shortcuts(self) -> None:
        """Register application-wide keyboard shortcuts."""
        # Ctrl+F -- focus entity search
        search_action = QAction("Search Entities", self)
        search_action.setShortcut(QKeySequence("Ctrl+F"))
        search_action.triggered.connect(self._focus_entity_search)
        self.addAction(search_action)

        # Ctrl+G -- focus chat input (to type a generate prompt)
        chat_action = QAction("Focus Chat", self)
        chat_action.setShortcut(QKeySequence("Ctrl+G"))
        chat_action.triggered.connect(self._focus_chat)
        self.addAction(chat_action)

        # Ctrl+S -- trigger save (state store)
        save_action = QAction("Save", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self._save_state)
        self.addAction(save_action)

        # Escape -- cancel streaming if active
        esc_action = QAction("Cancel", self)
        esc_action.setShortcut(QKeySequence("Escape"))
        esc_action.triggered.connect(self._on_escape)
        self.addAction(esc_action)

    def _focus_entity_search(self) -> None:
        self._entity_dock.setVisible(True)
        self._entity_dock.raise_()
        self._entity_panel.focus_search()

    def _focus_chat(self) -> None:
        self._chat_dock.setVisible(True)
        self._chat_dock.raise_()
        self._chat_panel.focus_input()

    def _save_state(self) -> None:
        try:
            store = StateStore.instance()
            store.save()
            self._status_bar.showMessage("Saved", 3000)
        except Exception:
            logger.debug("Manual save failed", exc_info=True)

    def _on_escape(self) -> None:
        if hasattr(self, "_agent_worker") and self._agent_worker:
            self._agent_worker.cancel()

    # ------------------------------------------------------------------
    # Layout save / restore
    # ------------------------------------------------------------------

    def _save_layout(self) -> None:
        """Persist window geometry and dock layout to QSettings."""
        self._settings.setValue("geometry", self.saveGeometry())
        self._settings.setValue("windowState", self.saveState())

    def _restore_layout(self) -> None:
        """Restore window geometry and dock layout from QSettings."""
        geometry = self._settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)

        state = self._settings.value("windowState")
        if state:
            self.restoreState(state)

    def _reset_layout(self) -> None:
        """Reset all docks to their default positions."""
        all_docks = [self._entity_dock, self._progress_dock, self._chat_dock, self._option_dock]
        for dock in all_docks:
            self.removeDockWidget(dock)

        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._entity_dock)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._progress_dock)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._chat_dock)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._option_dock)
        self.tabifyDockWidget(self._chat_dock, self._option_dock)

        for dock in all_docks:
            dock.setVisible(True)

        self._status_bar.showMessage("Layout reset to default", 3000)

    # ------------------------------------------------------------------
    # Cross-panel sync
    # ------------------------------------------------------------------

    def _on_entity_selected(self, entity_id: str) -> None:
        """Sync entity selection across all panels."""
        self._entity_panel.select_entity(entity_id)
        self._graph_panel.select_entity(entity_id)

    def open_entity_detail(self, entity_id: str, template_id: str = "") -> None:
        """Open the entity detail dialog for a given entity."""
        from app.panels.entity_detail import EntityDetailView
        dialog = EntityDetailView(
            entity_id=entity_id,
            template_id=template_id,
            engine_manager=getattr(self, "_engine", None),
            enforcement=getattr(self, "_enforcement", None),
            parent=self,
        )
        dialog.entity_saved.connect(lambda eid: self._bus.entity_updated.emit(eid))
        dialog.exec()

    def _on_option_selected(self, option_id: str, option_data: dict) -> None:
        """Handle an option being selected from the comparison panel."""
        template_data = option_data.get("template_data", {})
        template_id = template_data.get("$id", "")
        # Merge option title/description into template data
        if "name" not in template_data and option_data.get("title"):
            template_data["name"] = option_data["title"]
        if "description" not in template_data and option_data.get("description"):
            template_data["description"] = option_data["description"]
        self.open_new_entity(template_id, template_data)

    def open_new_entity(self, template_id: str, entity_data: dict | None = None) -> None:
        """Open the entity detail dialog for creating a new entity."""
        from app.panels.entity_detail import EntityDetailView
        dialog = EntityDetailView(
            entity_id="",
            template_id=template_id,
            engine_manager=getattr(self, "_engine", None),
            enforcement=getattr(self, "_enforcement", None),
            entity_data=entity_data,
            parent=self,
        )
        dialog.entity_saved.connect(lambda eid: self._bus.entity_created.emit(eid))
        dialog.exec()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_status_message(self, message: str) -> None:
        self._status_bar.showMessage(message, 5000)
        self._toast.show_info(message)

    def _on_error(self, message: str) -> None:
        self._status_bar.showMessage(f"Error: {message}", 10000)
        self._toast.show_error(message)

    def _show_about(self) -> None:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.about(
            self,
            "Worldbuilding Interactive Program",
            "A guided worldbuilding tool powered by Claude.\n\n"
            "Based on 'The Complete Art of World Building'\n"
            "by Randy Ellefson.\n\n"
            "Phase 3: Desktop Application",
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:
        """Save layout and clean up on close."""
        self._save_layout()
        logger.info("Main window closing, layout saved")
        super().closeEvent(event)
