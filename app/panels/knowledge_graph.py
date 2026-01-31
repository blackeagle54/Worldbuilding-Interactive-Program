"""
app/panels/knowledge_graph.py -- Knowledge Graph visualization panel.

Interactive node-edge graph of entities and their relationships using
QGraphicsView/QGraphicsScene with NetworkX layout algorithms.

Features:
- EntityNode items (colored circles with labels)
- RelationshipEdge items (arrows with type labels)
- Zoom/pan via mouse wheel and drag
- Click-to-select emits entity_selected via EventBus
- Hover tooltips showing entity metadata
- Type filter toolbar
- Performance target: 100 nodes in <1s
"""

from __future__ import annotations

import logging
import math
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.services.event_bus import EventBus

logger = logging.getLogger(__name__)

# Type-to-color mapping
_TYPE_COLORS: dict[str, str] = {
    "god": "#E91E63",
    "species": "#9C27B0",
    "settlement": "#FF9800",
    "sovereign_power": "#F44336",
    "culture": "#3F51B5",
    "religion": "#00BCD4",
    "organization": "#009688",
    "armed_forces": "#795548",
    "magic_system": "#673AB7",
    "monster": "#FF5722",
    "undead": "#607D8B",
    "plant": "#4CAF50",
    "animal": "#8BC34A",
    "world_figure": "#FFC107",
    "item": "#CDDC39",
    "myth": "#E040FB",
    "planet": "#2196F3",
    "constellation": "#03A9F4",
}
_DEFAULT_COLOR = "#9E9E9E"

NODE_RADIUS = 20
LABEL_OFFSET = 24
SCALE_FACTOR = 300  # Scale NetworkX layout coordinates


class EntityNode(QGraphicsEllipseItem):
    """A circular node representing an entity in the graph."""

    def __init__(
        self,
        entity_id: str,
        name: str,
        entity_type: str,
        x: float,
        y: float,
        parent: QGraphicsItem | None = None,
    ):
        r = NODE_RADIUS
        super().__init__(-r, -r, 2 * r, 2 * r, parent)
        self.entity_id = entity_id
        self.entity_type = entity_type

        color_hex = _TYPE_COLORS.get(entity_type, _DEFAULT_COLOR)
        color = QColor(color_hex)
        self.setBrush(QBrush(color))
        self.setPen(QPen(color.darker(140), 2))

        self.setPos(x, y)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Tooltip
        display_type = entity_type.replace("_", " ").title()
        self.setToolTip(f"{name}\nType: {display_type}\nID: {entity_id}")

        # Label below node
        self._label = QGraphicsSimpleTextItem(name, self)
        self._label.setBrush(QBrush(QColor("#CCCCCC")))
        label_rect = self._label.boundingRect()
        self._label.setPos(-label_rect.width() / 2, LABEL_OFFSET)

    def set_highlight(self, on: bool) -> None:
        """Highlight or unhighlight this node."""
        if on:
            self.setPen(QPen(QColor("#FFFFFF"), 3))
        else:
            color = QColor(_TYPE_COLORS.get(self.entity_type, _DEFAULT_COLOR))
            self.setPen(QPen(color.darker(140), 2))


class RelationshipEdge(QGraphicsPathItem):
    """A directed edge (arrow) between two entity nodes."""

    def __init__(
        self,
        source: EntityNode,
        target: EntityNode,
        relationship_type: str = "",
        parent: QGraphicsItem | None = None,
    ):
        super().__init__(parent)
        self.source = source
        self.target = target
        self.relationship_type = relationship_type

        self.setPen(QPen(QColor("#555555"), 1.5))
        self.setZValue(-1)  # Draw edges behind nodes

        if relationship_type:
            self.setToolTip(relationship_type)

        self._update_path()

    def _update_path(self) -> None:
        """Recalculate the edge path with an arrowhead."""
        src = self.source.pos()
        tgt = self.target.pos()

        dx = tgt.x() - src.x()
        dy = tgt.y() - src.y()
        length = math.sqrt(dx * dx + dy * dy)
        if length < 0.001:
            return

        # Shorten to stop at node boundary
        ratio_src = NODE_RADIUS / length
        ratio_tgt = NODE_RADIUS / length
        start = QPointF(src.x() + dx * ratio_src, src.y() + dy * ratio_src)
        end = QPointF(tgt.x() - dx * ratio_tgt, tgt.y() - dy * ratio_tgt)

        path = QPainterPath()
        path.moveTo(start)
        path.lineTo(end)

        # Arrowhead
        arrow_size = 8
        angle = math.atan2(dy, dx)
        p1 = QPointF(
            end.x() - arrow_size * math.cos(angle - math.pi / 6),
            end.y() - arrow_size * math.sin(angle - math.pi / 6),
        )
        p2 = QPointF(
            end.x() - arrow_size * math.cos(angle + math.pi / 6),
            end.y() - arrow_size * math.sin(angle + math.pi / 6),
        )
        path.moveTo(end)
        path.lineTo(p1)
        path.moveTo(end)
        path.lineTo(p2)

        self.setPath(path)


class GraphView(QGraphicsView):
    """QGraphicsView with zoom/pan support."""

    def __init__(self, scene: QGraphicsScene, parent: QWidget | None = None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self._zoom = 0

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Zoom in/out with mouse wheel."""
        factor = 1.15
        if event.angleDelta().y() > 0:
            if self._zoom < 20:
                self.scale(factor, factor)
                self._zoom += 1
        else:
            if self._zoom > -20:
                self.scale(1 / factor, 1 / factor)
                self._zoom -= 1

    def fit_all(self) -> None:
        """Fit all items in view."""
        rect = self.scene().itemsBoundingRect()
        if not rect.isNull():
            rect.adjust(-50, -50, 50, 50)
            self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
            self._zoom = 0


class KnowledgeGraphPanel(QWidget):
    """Interactive knowledge graph visualization."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._engine = None
        self._bus = EventBus.instance()
        self._nodes: dict[str, EntityNode] = {}
        self._edges: list[RelationshipEdge] = []
        self._type_filters: dict[str, QCheckBox] = {}
        self._selected_node: EntityNode | None = None
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

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)

        toolbar.addWidget(QLabel("Graph"))

        self._fit_btn = QPushButton("Fit All")
        self._fit_btn.setMaximumWidth(60)
        toolbar.addWidget(self._fit_btn)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setMaximumWidth(70)
        toolbar.addWidget(self._refresh_btn)

        toolbar.addStretch()

        self._node_count_label = QLabel("0 nodes, 0 edges")
        self._node_count_label.setStyleSheet("color: #888; font-size: 11px;")
        toolbar.addWidget(self._node_count_label)

        layout.addLayout(toolbar)

        # Type filter bar (scrollable row of checkboxes)
        self._filter_scroll = QScrollArea()
        self._filter_scroll.setWidgetResizable(True)
        self._filter_scroll.setMaximumHeight(30)
        self._filter_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._filter_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._filter_widget = QWidget()
        self._filter_layout = QHBoxLayout(self._filter_widget)
        self._filter_layout.setContentsMargins(0, 0, 0, 0)
        self._filter_layout.setSpacing(8)
        self._filter_scroll.setWidget(self._filter_widget)
        layout.addWidget(self._filter_scroll)

        # Scene and view
        self._scene = QGraphicsScene(self)
        self._view = GraphView(self._scene)
        layout.addWidget(self._view, 1)

        # Empty state label (shown when no entities exist)
        self._empty_label = QLabel(
            "Knowledge Graph\n\n"
            "Create entities to see\n"
            "their relationships here."
        )
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: #666; font-style: italic; font-size: 13px;")
        layout.addWidget(self._empty_label)
        self._empty_label.setVisible(True)

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self._fit_btn.clicked.connect(self._on_fit)
        self._refresh_btn.clicked.connect(self.refresh)
        self._scene.selectionChanged.connect(self._on_selection_changed)

        self._bus.entity_created.connect(lambda _: self.refresh())
        self._bus.entity_updated.connect(lambda _: self.refresh())
        self._bus.entity_deleted.connect(lambda _: self.refresh())

    # ------------------------------------------------------------------
    # Graph building
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Rebuild the graph from the engine's WorldGraph."""
        if self._engine is None:
            return

        try:
            wg = self._engine.world_graph
            graph = self._engine.with_lock("world_graph", lambda g: g.graph)
        except Exception:
            logger.exception("Failed to access WorldGraph")
            return

        self._scene.clear()
        self._nodes.clear()
        self._edges.clear()

        if graph.number_of_nodes() == 0:
            self._empty_label.setVisible(True)
            self._view.setVisible(False)
            self._node_count_label.setText("0 nodes, 0 edges")
            return

        self._empty_label.setVisible(False)
        self._view.setVisible(True)

        # Compute layout using NetworkX
        try:
            import networkx as nx
            pos = nx.spring_layout(graph, scale=SCALE_FACTOR, seed=42)
        except Exception:
            logger.exception("NetworkX layout failed")
            return

        # Create nodes
        active_types: set[str] = set()
        for node_id, coords in pos.items():
            attrs = graph.nodes.get(node_id, {})
            name = attrs.get("name", node_id)
            entity_type = attrs.get("entity_type", "unknown")
            active_types.add(entity_type)

            x, y = coords[0], coords[1]
            node = EntityNode(node_id, name, entity_type, x, y)
            self._scene.addItem(node)
            self._nodes[node_id] = node

        # Create edges
        for source_id, target_id, edge_data in graph.edges(data=True):
            if source_id in self._nodes and target_id in self._nodes:
                rel_type = edge_data.get("relationship_type", "")
                edge = RelationshipEdge(
                    self._nodes[source_id],
                    self._nodes[target_id],
                    rel_type,
                )
                self._scene.addItem(edge)
                self._edges.append(edge)

        # Update type filters
        self._update_type_filters(active_types)

        # Stats
        self._node_count_label.setText(
            f"{len(self._nodes)} nodes, {len(self._edges)} edges"
        )

        # Fit to view after a brief delay (let scene settle)
        QTimer.singleShot(50, self._view.fit_all)

    def _update_type_filters(self, active_types: set[str]) -> None:
        """Rebuild the type filter checkboxes."""
        # Clear existing
        for cb in self._type_filters.values():
            self._filter_layout.removeWidget(cb)
            cb.deleteLater()
        self._type_filters.clear()

        for entity_type in sorted(active_types):
            display = entity_type.replace("_", " ").title()
            color = _TYPE_COLORS.get(entity_type, _DEFAULT_COLOR)
            cb = QCheckBox(display)
            cb.setChecked(True)
            cb.setStyleSheet(f"color: {color};")
            cb.toggled.connect(lambda checked, t=entity_type: self._on_type_toggled(t, checked))
            self._filter_layout.addWidget(cb)
            self._type_filters[entity_type] = cb

        self._filter_layout.addStretch()

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_fit(self) -> None:
        self._view.fit_all()

    def _on_selection_changed(self) -> None:
        """Handle node selection in the scene."""
        # Unhighlight previous
        if self._selected_node:
            self._selected_node.set_highlight(False)
            self._selected_node = None

        selected = self._scene.selectedItems()
        for item in selected:
            if isinstance(item, EntityNode):
                item.set_highlight(True)
                self._selected_node = item
                self._bus.entity_selected.emit(item.entity_id)
                break

    def _on_type_toggled(self, entity_type: str, visible: bool) -> None:
        """Show or hide all nodes of a given type."""
        for node in self._nodes.values():
            if node.entity_type == entity_type:
                node.setVisible(visible)
                # Also hide connected edges
                for edge in self._edges:
                    if edge.source is node or edge.target is node:
                        edge.setVisible(
                            edge.source.isVisible() and edge.target.isVisible()
                        )

    # ------------------------------------------------------------------
    # External selection
    # ------------------------------------------------------------------

    def select_entity(self, entity_id: str) -> None:
        """Highlight a specific node (called from other panels)."""
        if self._selected_node:
            self._selected_node.set_highlight(False)

        node = self._nodes.get(entity_id)
        if node:
            node.set_highlight(True)
            self._selected_node = node
            self._view.centerOn(node)
