"""
app/main_window.py -- Main application window.

Hosts the 4 dock panels (entity browser, knowledge graph, chat, progress),
a menu bar with View toggles, and status bar.  Layout is saved/restored
across sessions via QSettings.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QDockWidget,
    QMainWindow,
    QStatusBar,
    QWidget,
)

from app.panels.chat_panel import ChatPanel
from app.panels.entity_browser import EntityBrowserPanel
from app.panels.knowledge_graph import KnowledgeGraphPanel
from app.panels.progress_sidebar import ProgressSidebarPanel
from app.services.event_bus import EventBus

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

        # Central widget -- the knowledge graph fills the center
        self._graph_panel = KnowledgeGraphPanel()
        self.setCentralWidget(self._graph_panel)

        # Create dock panels
        self._entity_dock = self._create_dock(
            "Entity Browser", EntityBrowserPanel(), Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self._progress_dock = self._create_dock(
            "Progress", ProgressSidebarPanel(), Qt.DockWidgetArea.RightDockWidgetArea
        )
        self._chat_dock = self._create_dock(
            "Chat", ChatPanel(), Qt.DockWidgetArea.BottomDockWidgetArea
        )

        # Menu bar
        self._build_menus()

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Ready")

        # Connect EventBus status messages
        bus = EventBus.instance()
        bus.status_message.connect(self._on_status_message)
        bus.error_occurred.connect(self._on_error)

        # Restore layout from previous session
        self._restore_layout()

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
        # Remove and re-add all docks
        for dock in [self._entity_dock, self._progress_dock, self._chat_dock]:
            self.removeDockWidget(dock)

        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._entity_dock)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._progress_dock)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._chat_dock)

        for dock in [self._entity_dock, self._progress_dock, self._chat_dock]:
            dock.setVisible(True)

        self._status_bar.showMessage("Layout reset to default", 3000)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_status_message(self, message: str) -> None:
        self._status_bar.showMessage(message, 5000)

    def _on_error(self, message: str) -> None:
        self._status_bar.showMessage(f"Error: {message}", 10000)

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
