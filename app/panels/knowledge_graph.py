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
import random
import time
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QMouseEvent,
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
from app.widgets.relationship_type_dialog import RelationshipTypeDialog

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
    """QGraphicsView with zoom/pan and Shift+drag-to-connect support.

    When the user holds Shift and drags from one EntityNode to another,
    a temporary rubber-band line is drawn.  On release over a different
    EntityNode the ``drag_connect_requested`` callback is invoked with
    the source and target nodes so the parent panel can open the
    relationship type picker.
    """

    def __init__(self, scene: QGraphicsScene, parent: QWidget | None = None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self._zoom = 0

        # Drag-to-connect state
        self._drag_source_node: EntityNode | None = None
        self._drag_line: QGraphicsLineItem | None = None
        self._is_connecting = False

        # Callback set by KnowledgeGraphPanel
        self.drag_connect_requested = None  # callable(source: EntityNode, target: EntityNode)

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

    # ------------------------------------------------------------------
    # Shift+drag-to-connect
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Intercept Shift+click on an EntityNode to start a connection drag."""
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            scene_pos = self.mapToScene(event.pos())
            item = self.scene().itemAt(scene_pos, self.transform())
            # Walk up parent chain in case we hit the label child
            source_node = self._find_entity_node(item)
            if source_node is not None:
                self._is_connecting = True
                self._drag_source_node = source_node
                # Create a temporary line from the node center
                pen = QPen(QColor("#FFD54F"), 2, Qt.PenStyle.DashLine)
                start = source_node.pos()
                self._drag_line = self.scene().addLine(
                    start.x(), start.y(), start.x(), start.y(), pen,
                )
                self._drag_line.setZValue(10)
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Update the rubber-band line while dragging."""
        if self._is_connecting and self._drag_line and self._drag_source_node:
            scene_pos = self.mapToScene(event.pos())
            start = self._drag_source_node.pos()
            self._drag_line.setLine(start.x(), start.y(), scene_pos.x(), scene_pos.y())
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Finish a connection drag -- check if we landed on a target node."""
        if self._is_connecting:
            # Clean up drag line
            if self._drag_line:
                self.scene().removeItem(self._drag_line)
                self._drag_line = None

            # Find the target node at release position
            scene_pos = self.mapToScene(event.pos())
            item = self.scene().itemAt(scene_pos, self.transform())
            target_node = self._find_entity_node(item)

            if (
                target_node is not None
                and target_node is not self._drag_source_node
                and self._drag_source_node is not None
                and self.drag_connect_requested is not None
            ):
                self.drag_connect_requested(self._drag_source_node, target_node)

            self._is_connecting = False
            self._drag_source_node = None
            event.accept()
            return

        super().mouseReleaseEvent(event)

    @staticmethod
    def _find_entity_node(item) -> EntityNode | None:
        """Walk up the QGraphicsItem parent chain to find an EntityNode."""
        while item is not None:
            if isinstance(item, EntityNode):
                return item
            item = item.parentItem()
        return None


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

        # Run layout benchmark in debug/dev mode
        if logger.isEnabledFor(logging.DEBUG):
            self._benchmark_layout(100)
            self._benchmark_layout(500)

    def _benchmark_layout(self, n: int) -> None:
        """Benchmark NetworkX spring_layout with *n* fake nodes and random edges.

        Creates a synthetic graph, times the layout computation, and logs the
        result.  Target: 100 nodes in <1 s.
        """
        try:
            import networkx as nx
        except ImportError:
            logger.debug("NetworkX not available -- skipping benchmark")
            return

        rng = random.Random(0)
        G = nx.Graph()
        G.add_nodes_from(range(n))
        # Add ~2*n random edges to make the graph reasonably connected
        for _ in range(2 * n):
            u, v = rng.randint(0, n - 1), rng.randint(0, n - 1)
            if u != v:
                G.add_edge(u, v)

        start = time.perf_counter()
        nx.spring_layout(G, scale=SCALE_FACTOR, seed=42)
        elapsed = time.perf_counter() - start
        logger.debug(
            "spring_layout benchmark: %d nodes, %d edges -> %.3f s",
            n, G.number_of_edges(), elapsed,
        )

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
        self._view.drag_connect_requested = self._on_drag_connect
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

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(100)
        self._refresh_timer.timeout.connect(self.refresh)

        self._bus.entity_created.connect(lambda _: self._schedule_refresh())
        self._bus.entity_updated.connect(lambda _: self._schedule_refresh())
        self._bus.entity_deleted.connect(lambda _: self._schedule_refresh())
        self._bus.relationship_created.connect(lambda *_: self._schedule_refresh())
        self._bus.relationship_removed.connect(lambda *_: self._schedule_refresh())

    # ------------------------------------------------------------------
    # Graph building
    # ------------------------------------------------------------------

    def _schedule_refresh(self) -> None:
        """Debounce refresh calls with a 100ms timer."""
        self._refresh_timer.start()

    def refresh(self) -> None:
        """Rebuild the graph from the engine's WorldGraph."""
        if self._engine is None:
            return

        try:
            graph = self._engine.with_lock("world_graph", lambda g: g.graph)
        except Exception:
            logger.exception("Failed to access WorldGraph")
            return

        self._scene.clear()
        self._selected_node = None
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

    def _on_drag_connect(self, source: EntityNode, target: EntityNode) -> None:
        """Handle drag-to-connect: show the relationship type picker and
        create the relationship via the engine if confirmed."""
        # Look up display names from node tooltips or IDs
        source_name = source.entity_id
        target_name = target.entity_id
        # Try to extract the name from the tooltip ("Name\nType: ...\nID: ...")
        src_tip = source.toolTip()
        tgt_tip = target.toolTip()
        if src_tip:
            source_name = src_tip.split("\n")[0]
        if tgt_tip:
            target_name = tgt_tip.split("\n")[0]

        dialog = RelationshipTypeDialog(source_name, target_name, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return

        rel_type = dialog.selected_type()
        if not rel_type:
            return

        # Create the relationship via the engine
        if self._engine:
            try:
                # Add the edge to the world graph
                self._engine.with_lock(
                    "world_graph",
                    lambda g: g.add_relationship(
                        source.entity_id, target.entity_id, rel_type,
                    ),
                )

                # Also persist the relationship on the source entity's data
                try:
                    entity_data = self._engine.with_lock(
                        "data_manager",
                        lambda d: d.get_entity(source.entity_id),
                    )
                    relationships = entity_data.get("relationships", [])
                    new_rel = {
                        "relationship_type": rel_type,
                        "target_id": target.entity_id,
                    }
                    # Avoid duplicates
                    if new_rel not in relationships:
                        relationships.append(new_rel)
                        self._engine.with_lock(
                            "data_manager",
                            lambda d: d.update_entity(
                                source.entity_id, {"relationships": relationships},
                            ),
                        )
                except Exception:
                    logger.debug(
                        "Could not persist relationship on entity data",
                        exc_info=True,
                    )

                # Notify the rest of the application
                self._bus.relationship_created.emit(
                    source.entity_id, target.entity_id, rel_type,
                )
                self._bus.status_message.emit(
                    f"Created: {source_name} --[{rel_type}]--> {target_name}"
                )

                # Refresh the graph to show the new edge
                self._schedule_refresh()

            except Exception:
                logger.exception("Failed to create relationship via drag-connect")
                self._bus.error_occurred.emit(
                    f"Failed to create relationship between "
                    f"{source_name} and {target_name}."
                )

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
