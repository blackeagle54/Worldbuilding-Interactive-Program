"""
app/panels/progress_sidebar.py -- Progress Sidebar dock panel.

Displays the 52-step progression with phase grouping, completion status,
and step navigation.  Clicking a step emits step_changed via EventBus
and updates the StateStore.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.event_bus import EventBus
from app.services.state_store import StateStore

logger = logging.getLogger(__name__)

# Phase definitions: (phase_key, display_name, step_range_start, step_range_end)
PHASES = [
    ("foundation", "Foundation", 1, 5),
    ("cosmology", "Cosmology", 6, 11),
    ("land", "The Land", 12, 15),
    ("life", "Life", 16, 24),
    ("civilization", "Civilization", 25, 30),
    ("society", "Society", 31, 34),
    ("supernatural", "The Supernatural", 35, 39),
    ("history", "History & Legend", 40, 42),
    ("language", "Language & Names", 43, 45),
    ("travel", "Travel & Scale", 46, 48),
    ("finishing", "Finishing Touches", 49, 50),
    ("integration", "Integration", 51, 52),
]

# All 52 steps -- step_number: title
STEPS = {
    1: "Define Your World Building Scope and Strategy",
    2: "Learn and Practice the Rule of Three",
    3: "Establish Your Naming Philosophy",
    4: "Set Your World Building Goals",
    5: "Set Up Your File Organization",
    6: "Design Your Pantheon Structure",
    7: "Create Individual God Profiles",
    8: "Write Creation and End-of-World Myths",
    9: "Write Additional Myths",
    10: "Define Your Planet",
    11: "Create Constellations",
    12: "Design Your Continent Shape and Position",
    13: "Place Mountains and Determine Rain Shadows",
    14: "Place Rivers, Lakes, and Water Features",
    15: "Place Forests, Grasslands, Deserts, and Wetlands",
    16: "Decide on Species Strategy",
    17: "Define Species Habitats and Core Traits",
    18: "Design Species Appearance and Senses",
    19: "Write Species World Views",
    20: "Define Species Society, Language, and Customs",
    21: "Map Species Relationships",
    22: "Create Plants and Animals (Purpose-Driven)",
    23: "Create Monsters",
    24: "Create Undead (If Applicable)",
    25: "Create Sovereign Powers (Nations)",
    26: "Define Cultures for Each Sovereign Power",
    27: "Design Cultural Details",
    28: "Plan Cultural Clashes",
    29: "Create Settlements",
    30: "Create a Settlement Master Spreadsheet",
    31: "Create Religions",
    32: "Create Organizations",
    33: "Create Armed Forces",
    34: "Design Societal Systems",
    35: "Decide Supernatural Prevalence",
    36: "Define Supernatural Elements",
    37: "Design Your Magic System(s)",
    38: "Create Spells and Magic Training",
    39: "Create Significant Items",
    40: "Create Your Time System",
    41: "Write World History",
    42: "Create World Figures",
    43: "Decide Your Language Approach",
    44: "Establish Naming Conventions by Culture",
    45: "Name Everything",
    46: "Calculate Land Travel Times",
    47: "Calculate Sea Travel Times",
    48: "Define Space Travel (If Applicable)",
    49: "Create Places of Interest",
    50: "Draw Maps",
    51: "Review and Cross-Reference All Files",
    52: "Establish a Review Cycle",
}

# Unicode characters for step status icons
_ICON_COMPLETE = "\u2713"    # check mark
_ICON_ACTIVE = "\u25B6"     # right-pointing triangle
_ICON_LOCKED = "\U0001F512"  # lock
_ICON_AVAILABLE = "\u25CB"   # white circle

# Colors
_COLOR_COMPLETE = QColor("#4CAF50")  # green
_COLOR_ACTIVE = QColor("#2196F3")    # blue
_COLOR_AVAILABLE = QColor("#FFC107")  # amber
_COLOR_LOCKED = QColor("#666666")    # gray


class ProgressSidebarPanel(QWidget):
    """52-step progression tracker with phase grouping."""

    advance_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._store: StateStore | None = None
        self._session_mgr = None
        self._bus = EventBus.instance()
        self._phase_items: dict[str, QTreeWidgetItem] = {}
        self._step_items: dict[int, QTreeWidgetItem] = {}
        self._setup_ui()
        self._connect_signals()

    def set_state_store(self, store: StateStore) -> None:
        """Inject the StateStore after construction."""
        self._store = store
        store.step_changed.connect(self._on_external_step_changed)
        self.refresh()

    def set_session_manager(self, session_mgr) -> None:
        """Inject the SessionManager for step advancement."""
        self._session_mgr = session_mgr

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Overall progress bar
        progress_row = QHBoxLayout()
        self._overall_label = QLabel("Overall:")
        self._overall_label.setStyleSheet("font-weight: bold; font-size: 11px;")
        progress_row.addWidget(self._overall_label)

        self._overall_progress = QProgressBar()
        self._overall_progress.setMaximum(52)
        self._overall_progress.setValue(0)
        self._overall_progress.setTextVisible(True)
        self._overall_progress.setFormat("%v / 52 (%p%)")
        self._overall_progress.setMaximumHeight(16)
        progress_row.addWidget(self._overall_progress, 1)

        layout.addLayout(progress_row)

        # Tree widget -- compact for sidebar use
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(12)
        self._tree.setAnimated(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setStyleSheet("""
            QTreeWidget {
                font-size: 12px;
            }
            QTreeWidget::item {
                padding: 1px 2px;
                min-height: 20px;
            }
        """)

        self._build_tree()
        layout.addWidget(self._tree, 1)

        # Advance button -- compact
        self._advance_btn = QPushButton("Advance to Next Step")
        self._advance_btn.setStyleSheet(
            "background-color: #2a4a5e; padding: 4px 8px; font-weight: bold; "
            "font-size: 12px; border-radius: 6px;"
        )
        self._advance_btn.clicked.connect(self._on_advance)
        layout.addWidget(self._advance_btn)

    def _build_tree(self) -> None:
        """Populate the tree with phases and steps."""
        self._tree.clear()
        self._phase_items.clear()
        self._step_items.clear()

        bold_font = QFont()
        bold_font.setBold(True)

        for phase_key, phase_name, start, end in PHASES:
            phase_item = QTreeWidgetItem(self._tree)
            phase_item.setText(0, f"{phase_name}  (Steps {start}-{end})")
            phase_item.setFont(0, bold_font)
            phase_item.setData(0, Qt.ItemDataRole.UserRole, phase_key)
            phase_item.setExpanded(False)
            self._phase_items[phase_key] = phase_item

            for step_num in range(start, end + 1):
                step_item = QTreeWidgetItem(phase_item)
                title = STEPS.get(step_num, f"Step {step_num}")
                step_item.setText(0, f"  {_ICON_AVAILABLE}  {step_num}. {title}")
                step_item.setData(0, Qt.ItemDataRole.UserRole, step_num)
                step_item.setToolTip(
                    0,
                    f"Step {step_num}: {title}\n"
                    f"Phase: {phase_name}\n"
                    f"Click to navigate to this step"
                )
                self._step_items[step_num] = step_item

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.itemDoubleClicked.connect(self._on_item_clicked)

    def _on_advance(self) -> None:
        """Handle Advance button click."""
        if self._session_mgr:
            self._session_mgr.advance_step()
        else:
            self.advance_requested.emit()

    def _on_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        """Handle click on a step (not a phase header)."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(data, int):
            step_num = data
            if self._store:
                self._store.set_current_step(step_num)
            self._bus.step_changed.emit(step_num)
            self._bus.status_message.emit(
                f"Step {step_num}: {STEPS.get(step_num, '')}"
            )
            self._update_step_display()

    def _on_external_step_changed(self, step: int) -> None:
        """React to step changes from other panels."""
        self._update_step_display()
        # Expand the phase containing this step and scroll to it
        if step in self._step_items:
            item = self._step_items[step]
            parent = item.parent()
            if parent:
                parent.setExpanded(True)
            self._tree.scrollToItem(item)

            # Briefly flash/highlight the new step with bold font
            bold_font = QFont()
            bold_font.setBold(True)
            bold_font.setPointSize(bold_font.pointSize() + 1)
            item.setFont(0, bold_font)
            item.setBackground(0, QBrush(QColor("#1565C0")))

            def _revert_highlight(item_ref=item, step_ref=step):
                normal_font = QFont()
                normal_font.setBold(False)
                item_ref.setFont(0, normal_font)
                item_ref.setBackground(0, QBrush(QColor("transparent")))

            QTimer.singleShot(1000, _revert_highlight)

    # ------------------------------------------------------------------
    # Display update
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Refresh all step statuses from the StateStore."""
        self._update_step_display()

    def _update_step_display(self) -> None:
        """Update icons and colors for all steps based on current state."""
        if self._store is None:
            return

        completed = set(self._store.completed_steps)
        in_progress = set(self._store.in_progress_steps)
        current = self._store.current_step

        self._overall_progress.setValue(len(completed))

        for step_num, item in self._step_items.items():
            title = STEPS.get(step_num, f"Step {step_num}")

            if step_num in completed:
                icon = _ICON_COMPLETE
                color = _COLOR_COMPLETE
            elif step_num == current or step_num in in_progress:
                icon = _ICON_ACTIVE
                color = _COLOR_ACTIVE
            else:
                icon = _ICON_AVAILABLE
                color = _COLOR_AVAILABLE

            item.setText(0, f"  {icon}  {step_num}. {title}")
            item.setForeground(0, QBrush(color))

        # Update phase completion percentages
        for phase_key, phase_name, start, end in PHASES:
            phase_item = self._phase_items.get(phase_key)
            if phase_item is None:
                continue

            total = end - start + 1
            done = sum(1 for s in range(start, end + 1) if s in completed)

            if done == total:
                pct_text = "  [Complete]"
                phase_item.setForeground(0, QBrush(_COLOR_COMPLETE))
            elif done > 0:
                pct_text = f"  [{done}/{total}]"
                phase_item.setForeground(0, QBrush(_COLOR_ACTIVE))
            else:
                pct_text = f"  [0/{total}]"
                phase_item.setForeground(0, QBrush(_COLOR_AVAILABLE))

            phase_item.setText(
                0, f"{phase_name}  (Steps {start}-{end}){pct_text}"
            )

            # Auto-expand phase that contains current step
            if start <= current <= end:
                phase_item.setExpanded(True)
