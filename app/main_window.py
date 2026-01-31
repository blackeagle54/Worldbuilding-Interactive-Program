"""
app/main_window.py -- Main application window.

Modern chat-centered layout using QSplitters instead of dock widgets.
Left sidebar: progress + entities. Center: chat (60-70%). Right sidebar: graph + options.
Sidebars are collapsible via toolbar toggle buttons.
Layout is saved/restored across sessions via QSettings.
Cross-panel sync is wired through EventBus.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QByteArray, QSettings, Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QMainWindow,
    QSplitter,
    QStatusBar,
    QToolBar,
    QToolButton,
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
    """Main application window with chat-centered splitter layout.

    Layout
    ------
    Default arrangement::

        +----------+-----------------------+----------+
        | Progress |                       | Graph    |
        | Sidebar  |                       | Panel    |
        |          |     Chat Panel        |          |
        +----------+   (center, 60-70%)    +----------+
        | Entity   |                       | Options  |
        | Browser  |                       | Panel    |
        | (left)   |                       | (right)  |
        +----------+-----------------------+----------+
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

        # Build the splitter-based layout
        self._build_layout()

        # Menu bar (slim)
        self._build_menus()

        # Toolbar with sidebar toggles
        self._build_toolbar()

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

        # Periodically save layout (in case of crash, layout is not lost)
        from PySide6.QtCore import QTimer
        self._layout_save_timer = QTimer(self)
        self._layout_save_timer.setInterval(60_000)  # every 60 seconds
        self._layout_save_timer.timeout.connect(self._save_layout)
        self._layout_save_timer.start()

    # ------------------------------------------------------------------
    # Layout construction
    # ------------------------------------------------------------------

    def _build_layout(self) -> None:
        """Build the three-column splitter layout with chat in center."""
        # Left sidebar: Progress on top, Entity Browser below
        self._left_sidebar = QWidget()
        self._left_sidebar.setObjectName("leftSidebar")
        self._left_sidebar.setMinimumWidth(200)

        self._left_splitter = QSplitter(Qt.Orientation.Vertical)
        self._left_splitter.setObjectName("leftSplitter")
        self._left_splitter.addWidget(self._progress_panel)
        self._left_splitter.addWidget(self._entity_panel)
        self._left_splitter.setSizes([300, 400])

        from PySide6.QtWidgets import QVBoxLayout
        left_layout = QVBoxLayout(self._left_sidebar)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        left_layout.addWidget(self._left_splitter)

        # Right sidebar: Knowledge Graph on top, Option Comparison below
        self._right_sidebar = QWidget()
        self._right_sidebar.setObjectName("rightSidebar")
        self._right_sidebar.setMinimumWidth(200)

        self._right_splitter = QSplitter(Qt.Orientation.Vertical)
        self._right_splitter.setObjectName("rightSplitter")
        self._right_splitter.addWidget(self._graph_panel)
        self._right_splitter.addWidget(self._option_panel)
        self._right_splitter.setSizes([400, 300])

        from PySide6.QtWidgets import QVBoxLayout as QVL
        right_layout = QVL(self._right_sidebar)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self._right_splitter)

        # Chat panel (center) -- min 400px width
        self._chat_panel.setMinimumWidth(400)

        # Main horizontal splitter
        self._main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._main_splitter.setObjectName("mainSplitter")
        self._main_splitter.addWidget(self._left_sidebar)
        self._main_splitter.addWidget(self._chat_panel)
        self._main_splitter.addWidget(self._right_sidebar)

        # Set stretch factors: sidebars don't stretch, chat does
        self._main_splitter.setStretchFactor(0, 0)  # left sidebar
        self._main_splitter.setStretchFactor(1, 1)  # chat (stretches)
        self._main_splitter.setStretchFactor(2, 0)  # right sidebar

        # Default sizes: 250 | ~remaining | 280
        self._main_splitter.setSizes([250, 700, 280])

        self.setCentralWidget(self._main_splitter)

    # ------------------------------------------------------------------
    # Toolbar with sidebar toggles
    # ------------------------------------------------------------------

    def _build_toolbar(self) -> None:
        """Build a slim toolbar with sidebar toggle buttons."""
        self._toolbar = QToolBar("Sidebar Toggles")
        self._toolbar.setObjectName("mainToolbar")
        self._toolbar.setMovable(False)
        self._toolbar.setFloatable(False)
        self._toolbar.setIconSize(self._toolbar.iconSize())

        # Left sidebar toggle
        self._left_toggle = QToolButton()
        self._left_toggle.setText("Left Panel")
        self._left_toggle.setCheckable(True)
        self._left_toggle.setChecked(True)
        self._left_toggle.setToolTip("Toggle left sidebar (Progress + Entities)")
        self._left_toggle.toggled.connect(self._toggle_left_sidebar)
        self._toolbar.addWidget(self._left_toggle)

        self._toolbar.addSeparator()

        # Right sidebar toggle
        self._right_toggle = QToolButton()
        self._right_toggle.setText("Right Panel")
        self._right_toggle.setCheckable(True)
        self._right_toggle.setChecked(True)
        self._right_toggle.setToolTip("Toggle right sidebar (Graph + Options)")
        self._right_toggle.toggled.connect(self._toggle_right_sidebar)
        self._toolbar.addWidget(self._right_toggle)

        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._toolbar)

    def _toggle_left_sidebar(self, visible: bool) -> None:
        """Show or hide the left sidebar."""
        self._left_sidebar.setVisible(visible)

    def _toggle_right_sidebar(self, visible: bool) -> None:
        """Show or hide the right sidebar."""
        self._right_sidebar.setVisible(visible)

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

        # Ensure system prompt is rebuilt before every message send
        self._chat_panel.set_pre_send_hook(self._update_system_prompt)

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

            # Pass rolling conversation summary so the system prompt
            # includes a SESSION MEMORY section with compressed history.
            summary = ""
            if hasattr(self._chat_panel, "conversation_summary"):
                summary = self._chat_panel.conversation_summary
            context = build_context(self._engine, step, conversation_summary=summary)
            self._chat_panel.set_system_prompt(context["system_prompt"])
            self._claude_client.set_current_step(step)

            # Log what context was built
            prompt_len = len(context.get("system_prompt", ""))
            entities = context.get("entities_summary", "")
            graph = context.get("graph_summary", "")
            refs = context.get("reference_content", [])
            guidance = context.get("step_guidance", "")
            decisions = context.get("recent_decisions", "")
            logger.info(
                "System prompt rebuilt: step=%d, prompt_len=%d, "
                "entities=%d chars, graph=%d chars, refs=%d sections, "
                "guidance=%d chars, decisions=%d chars",
                step, prompt_len,
                len(entities), len(graph), len(refs),
                len(guidance), len(decisions),
            )

            # Update enforcement service step
            if hasattr(self, "_enforcement") and self._enforcement:
                self._enforcement.set_current_step(step)
        except Exception:
            logger.warning("Failed to build system prompt", exc_info=True)

    # ------------------------------------------------------------------
    # Menu bar
    # ------------------------------------------------------------------

    def _build_menus(self) -> None:
        """Build the menu bar with View toggles and layout actions."""
        menubar = self.menuBar()

        # --- View menu ---
        view_menu = menubar.addMenu("&View")

        # Sidebar toggle actions
        left_action = QAction("Left Sidebar", self)
        left_action.setCheckable(True)
        left_action.setChecked(True)
        left_action.toggled.connect(self._on_menu_toggle_left)
        view_menu.addAction(left_action)
        self._menu_left_action = left_action

        right_action = QAction("Right Sidebar", self)
        right_action.setCheckable(True)
        right_action.setChecked(True)
        right_action.toggled.connect(self._on_menu_toggle_right)
        view_menu.addAction(right_action)
        self._menu_right_action = right_action

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

    def _on_menu_toggle_left(self, checked: bool) -> None:
        """Sync menu action with toolbar toggle for left sidebar."""
        self._left_toggle.setChecked(checked)

    def _on_menu_toggle_right(self, checked: bool) -> None:
        """Sync menu action with toolbar toggle for right sidebar."""
        self._right_toggle.setChecked(checked)

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
        # Make sure left sidebar is visible
        if not self._left_sidebar.isVisible():
            self._left_toggle.setChecked(True)
        self._entity_panel.focus_search()

    def _focus_chat(self) -> None:
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
        """Persist window geometry and splitter sizes to QSettings."""
        self._settings.setValue("geometry", self.saveGeometry())
        self._settings.setValue("mainSplitter", self._main_splitter.saveState())
        self._settings.setValue("leftSplitter", self._left_splitter.saveState())
        self._settings.setValue("rightSplitter", self._right_splitter.saveState())
        self._settings.setValue("leftVisible", self._left_sidebar.isVisible())
        self._settings.setValue("rightVisible", self._right_sidebar.isVisible())

    def _restore_layout(self) -> None:
        """Restore window geometry and splitter sizes from QSettings."""
        geometry = self._settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)

        main_state = self._settings.value("mainSplitter")
        if main_state and isinstance(main_state, QByteArray):
            self._main_splitter.restoreState(main_state)

        left_state = self._settings.value("leftSplitter")
        if left_state and isinstance(left_state, QByteArray):
            self._left_splitter.restoreState(left_state)

        right_state = self._settings.value("rightSplitter")
        if right_state and isinstance(right_state, QByteArray):
            self._right_splitter.restoreState(right_state)

        left_vis = self._settings.value("leftVisible", True)
        if isinstance(left_vis, str):
            left_vis = left_vis.lower() != "false"
        self._left_toggle.setChecked(bool(left_vis))

        right_vis = self._settings.value("rightVisible", True)
        if isinstance(right_vis, str):
            right_vis = right_vis.lower() != "false"
        self._right_toggle.setChecked(bool(right_vis))

    def _reset_layout(self) -> None:
        """Reset the layout to defaults."""
        self._main_splitter.setSizes([250, 700, 280])
        self._left_splitter.setSizes([300, 400])
        self._right_splitter.setSizes([400, 300])
        self._left_toggle.setChecked(True)
        self._right_toggle.setChecked(True)
        self._left_sidebar.setVisible(True)
        self._right_sidebar.setVisible(True)

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
        logger.error("UI error: %s", message)
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
