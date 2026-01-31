# Research: Interactive Knowledge Graph Visualization in PySide6

**Date:** 2026-01-30
**Purpose:** Evaluate approaches for visualizing the WorldGraph (NetworkX DiGraph) as an
interactive node editor in PySide6. Covers the QGraphicsView framework, existing libraries,
layout algorithms, custom rendering, and performance considerations.

---

## Table of Contents

1. [QGraphicsView Fundamentals](#1-qgraphicsview-fundamentals)
2. [Existing Node Editor Libraries for PySide6](#2-existing-node-editor-libraries-for-pyside6)
3. [NetworkX to Qt Visualization](#3-networkx-to-qt-visualization)
4. [Custom Node Rendering](#4-custom-node-rendering)
5. [Edge Rendering](#5-edge-rendering)
6. [Interactive Features](#6-interactive-features)
7. [Performance](#7-performance)
8. [Recommendation for This Project](#8-recommendation-for-this-project)
9. [Sources](#9-sources)

---

## 1. QGraphicsView Fundamentals

### Architecture: Scene / View / Item

The Qt Graphics View framework is a three-layer architecture for 2D vector graphics:

| Layer | Class | Role |
|---|---|---|
| **Model** | `QGraphicsScene` | Container for all items. Manages spatial indexing (BSP tree), event propagation, item selection state, and focus. Has its own coordinate system (scene coordinates). |
| **View** | `QGraphicsView` | A `QWidget` that renders a scene (or a portion of it) into a scrollable viewport. Handles coordinate mapping between scene and viewport. Supports affine transforms (zoom, rotate, pan). Multiple views can share one scene. |
| **Item** | `QGraphicsItem` | Individual drawable element. Has its own local coordinate system. Supports mouse events, hover, drag, tooltips, selection, and parent-child nesting. Subclass to create custom visuals. |

### Coordinate Systems

There are three coordinate spaces:

- **Item coordinates** -- local to each `QGraphicsItem`. The `paint()` method works in this space. `boundingRect()` must return a rectangle in item coordinates.
- **Scene coordinates** -- the global 2D surface. Items are positioned in scene coordinates via `setPos()`. Scene coordinates are the "world space" of the graph.
- **View (viewport) coordinates** -- pixel coordinates of the `QGraphicsView` widget. Mouse events arrive in view coordinates and must be mapped to scene/item coordinates.

Key mapping functions:

```python
# View -> Scene
scene_point = view.mapToScene(view_point)

# Scene -> View
view_point = view.mapFromScene(scene_point)

# Item -> Scene
scene_point = item.mapToScene(item_point)
```

### Zoom and Pan

Zoom is implemented via the view's affine transformation matrix. Pan is either
scroll-bar based (automatic) or via `ScrollHandDrag` mode.

```python
class ZoomableGraphView(QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self._zoom_level = 0

        # Zoom anchors to cursor position
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        self.setResizeAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )

        # Middle-click or left-click drag to pan
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)

    def wheelEvent(self, event):
        """Zoom in/out on scroll wheel."""
        zoom_in_factor = 1.25
        zoom_out_factor = 1 / zoom_in_factor

        if event.angleDelta().y() > 0:
            factor = zoom_in_factor
            self._zoom_level += 1
        else:
            factor = zoom_out_factor
            self._zoom_level -= 1

        # Clamp zoom range
        if -10 <= self._zoom_level <= 20:
            self.scale(factor, factor)
        else:
            # Undo the level change if clamped
            if event.angleDelta().y() > 0:
                self._zoom_level -= 1
            else:
                self._zoom_level += 1

    def fit_all(self):
        """Reset zoom to fit entire scene in viewport."""
        self.fitInView(
            self.sceneRect(),
            Qt.AspectRatioMode.KeepAspectRatio
        )
        self._zoom_level = 0
```

### Scene Setup Pattern

```python
scene = QGraphicsScene()
scene.setSceneRect(-2000, -2000, 4000, 4000)  # large workspace

view = ZoomableGraphView(scene)
view.setRenderHint(QPainter.RenderHint.Antialiasing)
view.setViewportUpdateMode(
    QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate
)
```

---

## 2. Existing Node Editor Libraries for PySide6

### 2a. NodeGraphQt (original)

| Field | Detail |
|---|---|
| **GitHub** | [jchanvfx/NodeGraphQt](https://github.com/jchanvfx/NodeGraphQt) |
| **Stars** | ~1,600 |
| **Last Release** | v0.6.43 (September 2025) |
| **License** | MIT |
| **PySide6** | Partial -- originally built for PySide2/Qt.py. Issue #423 tracks PySide6 support. Community PRs exist but the original repo still depends on Qt.py. |
| **Features** | Full node graph UI: zoom/pan, node creation/deletion, connection pipes (straight, curved, angled), undo/redo, properties panel, node search palette, serialization, custom widgets in nodes, backdrop nodes, group nodes. |
| **Limitations** | Designed for dataflow-style node editors (shader graphs, VFX pipelines), not knowledge graphs. Heavyweight for simple visualization. PySide6 support requires forks or patches. |

### 2b. NodeGraphQt-PySide6 (C3RV1 fork)

| Field | Detail |
|---|---|
| **GitHub** | [C3RV1/NodeGraphQt-PySide6](https://github.com/C3RV1/NodeGraphQt-PySide6) |
| **Stars** | ~20 |
| **License** | MIT (inherited) |
| **PySide6** | Yes -- direct port. |
| **Limitations** | May lag behind the original repo's feature updates. Small maintainer base. |

### 2c. OdenGraphQt

| Field | Detail |
|---|---|
| **GitHub** | [hueyyeng/OdenGraphQt](https://github.com/hueyyeng/OdenGraphQt) |
| **Stars** | ~10 |
| **Last Release** | Available on PyPI as `OdenGraphQt` |
| **License** | MIT (inherited from NodeGraphQt) |
| **PySide6** | Yes -- PySide6 and PyQt6 compatibility merged. |
| **Features** | Same as NodeGraphQt core with PySide6/PyQt6 compatibility. Includes example scripts (`basic_example.py`, `accept_reject_example.py`). |
| **Limitations** | Very small community. Documentation defers to original NodeGraphQt docs. Unclear long-term maintenance. |

### 2d. qtpynodeeditor

| Field | Detail |
|---|---|
| **GitHub** | [klauer/qtpynodeeditor](https://github.com/klauer/qtpynodeeditor) |
| **Stars** | ~235 |
| **Last Release** | v0.3.3 (December 2024) |
| **License** | BSD-3-Clause |
| **PySide6** | Yes -- via qtpy abstraction layer. Install with `pip install qtpynodeeditor[pyside6]`. |
| **Features** | Pure Python port of the C++ NodeEditor library. Dataflow model with typed ports, automatic connection validation, style customization, serialization. |
| **Limitations** | Dataflow-oriented (input/output ports on every node). Not well suited for knowledge-graph visualization where edges represent arbitrary named relationships rather than data ports. Modest activity. |

### 2e. SpatialNode

| Field | Detail |
|---|---|
| **GitHub** | [SpatialGraphics/SpatialNode](https://github.com/SpatialGraphics/SpatialNode) |
| **Stars** | ~9 |
| **Last Commit** | March 2024 |
| **License** | MIT |
| **PySide6** | Yes -- built exclusively for PySide6. |
| **Features** | Pure Python rewrite of the C++ nodeeditor. Model-View architecture (`AbstractGraphModel`). Dataflow support via `DataFlowGraphModel`. Headless mode. |
| **Limitations** | Very new, very few stars, uncertain maintenance. Only 27 commits total. Dataflow-oriented. |

### 2f. nodegraph-pyqt

| Field | Detail |
|---|---|
| **GitHub** | [dsideb/nodegraph-pyqt](https://github.com/dsideb/nodegraph-pyqt) |
| **Stars** | ~35 |
| **License** | MIT |
| **PySide6** | No -- PyQt5 only, stale. |
| **Notes** | Intended for DAG visualization with NetworkX integration. Interesting conceptually but unmaintained. |

### Summary Table

| Library | Stars | PySide6 | Last Active | Best For |
|---|---|---|---|---|
| NodeGraphQt | ~1,600 | Via forks | Sep 2025 | Full node editors (VFX) |
| OdenGraphQt | ~10 | Native | 2024 | Drop-in NodeGraphQt+PySide6 |
| qtpynodeeditor | ~235 | Via qtpy | Dec 2024 | Dataflow editors |
| SpatialNode | ~9 | Native | Mar 2024 | Experimental dataflow |
| Custom (recommended) | -- | -- | -- | Knowledge graphs |

**Verdict:** None of these libraries are well suited for a worldbuilding knowledge graph.
They are all designed for dataflow/pipeline editors (nodes have typed input/output ports).
Our use case -- entities as simple labeled nodes with named relationship edges -- is
fundamentally different. **A custom QGraphicsView implementation is recommended**, using
the official Qt NetworkX viewer example as a starting point.

---

## 3. NetworkX to Qt Visualization

### The Official Qt for Python NetworkX Example

Qt provides an official example that demonstrates exactly this integration:
[Networkx viewer Example](https://doc.qt.io/qtforpython-6/examples/example_external_networkx.html).

The pattern is:

1. Build or receive a `nx.DiGraph` (we already have `WorldGraph.graph`).
2. Use a NetworkX layout function to compute `{node_id: (x, y)}` positions.
3. Scale the positions (NetworkX layouts return values in roughly [0,1] or [-1,1] range).
4. Create `QGraphicsItem` subclasses for nodes and edges.
5. Add them to a `QGraphicsScene`.
6. Position nodes using `item.setPos(x, y)`.
7. Edges read positions from their source/dest nodes and update when nodes move.

### NetworkX Layout Algorithms

NetworkX provides these built-in layouts (all return `dict[node, ndarray]`):

| Layout | Function | Best For |
|---|---|---|
| **Spring (Fruchterman-Reingold)** | `nx.spring_layout(G)` | General-purpose. Force-directed. Good default for knowledge graphs. |
| **Kamada-Kawai** | `nx.kamada_kawai_layout(G)` | Higher quality than spring for small-medium graphs. Slower. |
| **Circular** | `nx.circular_layout(G)` | Places all nodes in a circle. Good for overview of small graphs. |
| **Shell** | `nx.shell_layout(G, nlist=...)` | Concentric circles. Could group by entity_type per ring. |
| **Spectral** | `nx.spectral_layout(G)` | Uses graph eigenvalues. Can reveal cluster structure. |
| **Multipartite** | `nx.multipartite_layout(G, subset_key=...)` | Nodes arranged in columns by a partition attribute. Perfect for grouping by entity_type. |
| **Spiral** | `nx.spiral_layout(G)` | Spiral arrangement. Aesthetic for timelines. |
| **Planar** | `nx.planar_layout(G)` | No crossing edges (only works for planar graphs). |
| **Random** | `nx.random_layout(G)` | Testing only. |

For our worldbuilding tool, the best defaults are:
- **spring_layout** -- general exploration
- **kamada_kawai_layout** -- cleaner results for < 100 nodes
- **multipartite_layout** with `subset_key="entity_type"` -- to see gods in one column,
  settlements in another, species in another, etc.

### Mapping NetworkX Coordinates to QGraphicsScene

NetworkX layouts return positions normalized roughly to [-1, 1]. We need to scale them
to scene coordinates:

```python
import networkx as nx
from PySide6.QtCore import QPointF

GRAPH_SCALE = 400  # pixels of spacing between nodes

def compute_layout(graph: nx.DiGraph, algorithm: str = "spring") -> dict:
    """Compute node positions using a NetworkX layout algorithm.

    Returns dict of {node_id: QPointF} in scene coordinates.
    """
    layout_funcs = {
        "spring": lambda g: nx.spring_layout(g, k=2.0, iterations=50),
        "kamada_kawai": nx.kamada_kawai_layout,
        "circular": nx.circular_layout,
        "shell": nx.shell_layout,
        "spectral": nx.spectral_layout,
        "multipartite": lambda g: nx.multipartite_layout(
            g, subset_key="entity_type"
        ),
    }

    func = layout_funcs.get(algorithm, nx.spring_layout)
    positions = func(graph)

    return {
        node: QPointF(x * GRAPH_SCALE, y * GRAPH_SCALE)
        for node, (x, y) in positions.items()
    }
```

### Animated Layout Transitions

The official Qt example uses `QPropertyAnimation` to smoothly animate nodes
between layouts. This requires nodes to inherit `QGraphicsObject` (which
provides the `pos` property for animation):

```python
from PySide6.QtCore import (
    QParallelAnimationGroup, QPropertyAnimation, QEasingCurve
)

def animate_to_layout(nodes_map, positions, duration=800):
    """Animate all nodes to new positions."""
    group = QParallelAnimationGroup()
    for node_id, target_pos in positions.items():
        item = nodes_map.get(node_id)
        if item is None:
            continue
        anim = QPropertyAnimation(item, b"pos")
        anim.setDuration(duration)
        anim.setEndValue(target_pos)
        anim.setEasingCurve(QEasingCurve.Type.OutExpo)
        group.addAnimation(anim)
    group.start()
    return group  # caller must keep a reference to prevent GC
```

### Integrating with WorldGraph

Our `WorldGraph` in `engine/graph_builder.py` stores node attributes we can use directly:

```python
# Node attributes available in WorldGraph.graph:
#   entity_type  -- "gods", "settlements", "species", etc.
#   name         -- display name
#   status       -- "draft" or "canon"
#   file_path    -- path to entity JSON file
#   step_created -- progression step number

# Edge attributes:
#   relationship_type -- "worships", "rules", "pantheon", etc.
#   source_field      -- schema field that created this edge

# For multipartite layout, we need to set the subset_key:
for node, attrs in world_graph.graph.nodes(data=True):
    # nx.multipartite_layout reads "subset" by default
    attrs["subset"] = attrs.get("entity_type", "unknown")
```

---

## 4. Custom Node Rendering

### Entity Node Item

For our worldbuilding tool, each node should display:
- Entity name (primary label)
- Entity type (subtitle or icon)
- Status indicator (draft vs canon)
- Color coded by category

```python
from PySide6.QtCore import QRectF, Qt, QPointF
from PySide6.QtGui import (
    QBrush, QColor, QFont, QPainter, QPen, QFontMetrics
)
from PySide6.QtWidgets import (
    QGraphicsObject, QGraphicsItem, QStyleOptionGraphicsItem, QWidget
)


# Color palette by entity type
ENTITY_COLORS = {
    "gods":          "#8B5CF6",  # purple
    "pantheons":     "#6D28D9",  # deep purple
    "species":       "#10B981",  # emerald
    "settlements":   "#F59E0B",  # amber
    "regions":       "#EF4444",  # red
    "factions":      "#3B82F6",  # blue
    "characters":    "#EC4899",  # pink
    "artifacts":     "#F97316",  # orange
    "events":        "#14B8A6",  # teal
}
DEFAULT_COLOR = "#6B7280"  # gray


class EntityNode(QGraphicsObject):
    """A visual node representing a worldbuilding entity.

    Inherits QGraphicsObject (not plain QGraphicsItem) so that
    QPropertyAnimation can animate the 'pos' property for layout
    transitions.
    """

    NODE_WIDTH = 160
    NODE_HEIGHT = 60
    CORNER_RADIUS = 8

    def __init__(
        self,
        entity_id: str,
        name: str,
        entity_type: str = "",
        status: str = "draft",
        parent=None,
    ):
        super().__init__(parent)
        self.entity_id = entity_id
        self._name = name
        self._entity_type = entity_type
        self._status = status
        self._edges: list = []

        self._color = QColor(
            ENTITY_COLORS.get(entity_type, DEFAULT_COLOR)
        )

        # Flags for interactivity
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )

        # Enable hover events for tooltips / highlighting
        self.setAcceptHoverEvents(True)

        # Tooltip
        self.setToolTip(
            f"{name}\nType: {entity_type}\nStatus: {status}"
        )

        # Caching for performance
        self.setCacheMode(
            QGraphicsItem.CacheMode.DeviceCoordinateCache
        )

    def boundingRect(self) -> QRectF:
        # Small padding for selection outline
        pad = 2
        return QRectF(
            -pad, -pad,
            self.NODE_WIDTH + 2 * pad,
            self.NODE_HEIGHT + 2 * pad,
        )

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget = None,
    ):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(0, 0, self.NODE_WIDTH, self.NODE_HEIGHT)

        # --- Background fill ---
        bg_color = QColor(self._color)
        if self._status == "draft":
            bg_color.setAlpha(180)  # semi-transparent for drafts
        painter.setBrush(QBrush(bg_color))

        # --- Border ---
        if self.isSelected():
            pen = QPen(QColor("#FFFFFF"), 3)
        else:
            pen = QPen(bg_color.darker(140), 1.5)
        painter.setPen(pen)

        painter.drawRoundedRect(
            rect, self.CORNER_RADIUS, self.CORNER_RADIUS
        )

        # --- Status indicator dot ---
        status_color = (
            QColor("#22C55E") if self._status == "canon"
            else QColor("#FACC15")
        )
        painter.setBrush(QBrush(status_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(
            QPointF(self.NODE_WIDTH - 12, 12), 5, 5
        )

        # --- Entity name (primary label) ---
        painter.setPen(QPen(QColor("#FFFFFF")))
        name_font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        painter.setFont(name_font)
        name_rect = QRectF(8, 6, self.NODE_WIDTH - 24, 24)
        painter.drawText(
            name_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self._name,
        )

        # --- Entity type (subtitle) ---
        painter.setPen(QPen(QColor(255, 255, 255, 160)))
        type_font = QFont("Segoe UI", 8)
        painter.setFont(type_font)
        type_rect = QRectF(8, 32, self.NODE_WIDTH - 16, 20)
        painter.drawText(
            type_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self._entity_type.replace("_", " ").title(),
        )

    def add_edge(self, edge):
        self._edges.append(edge)

    def itemChange(self, change, value):
        """Notify connected edges when the node moves."""
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for edge in self._edges:
                edge.adjust()
        return super().itemChange(change, value)

    def center_pos(self) -> QPointF:
        """Return the center of the node in scene coordinates."""
        return self.pos() + QPointF(
            self.NODE_WIDTH / 2, self.NODE_HEIGHT / 2
        )

    # --- Hover effects ---
    def hoverEnterEvent(self, event):
        self._color = self._color.lighter(120)
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._color = QColor(
            ENTITY_COLORS.get(self._entity_type, DEFAULT_COLOR)
        )
        self.update()
        super().hoverLeaveEvent(event)
```

### Key Design Decisions

- **QGraphicsObject vs QGraphicsItem:** We use `QGraphicsObject` because it inherits
  `QObject`, which is required for `QPropertyAnimation` to animate the `pos` property.
  Plain `QGraphicsItem` does not support Qt properties.

- **ItemSendsGeometryChanges:** Must be set for `itemChange()` to fire when the node
  is moved. Without this flag, edges will not follow the node during drag.

- **DeviceCoordinateCache:** Caches the painted result as a pixmap in device coordinates.
  Good for nodes whose appearance rarely changes. If you need to animate the node's
  paint (e.g., pulsing), switch to `ItemCoordinateCache` or `NoCache` during animation.

---

## 5. Edge Rendering

### Straight-Line Edges with Arrowheads

The simplest approach from the official Qt example. Edges are drawn as straight
`QLineF` segments with a triangular arrowhead at the destination end.

```python
import math
from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem


class RelationshipEdge(QGraphicsItem):
    """A directed edge between two EntityNode items.

    Draws a line from source to destination with an arrowhead
    indicating direction.
    """

    ARROW_SIZE = 12
    THICKNESS = 1.5

    def __init__(self, source, dest, relationship_type="", parent=None):
        super().__init__(parent)
        self._source = source
        self._dest = dest
        self._relationship_type = relationship_type
        self._color = QColor("#94A3B8")  # slate-400

        self._line = QLineF()
        self.setZValue(-1)  # draw edges behind nodes

        # Register with nodes so they can notify us on move
        source.add_edge(self)
        dest.add_edge(self)

        self.setToolTip(relationship_type or "related")
        self.adjust()

    def adjust(self):
        """Recalculate the line from source center to dest center."""
        self.prepareGeometryChange()
        self._line = QLineF(
            self._source.center_pos(),
            self._dest.center_pos(),
        )

    def boundingRect(self) -> QRectF:
        extra = self.THICKNESS + self.ARROW_SIZE
        return (
            QRectF(self._line.p1(), self._line.p2())
            .normalized()
            .adjusted(-extra, -extra, extra, extra)
        )

    def paint(self, painter, option, widget=None):
        if self._line.length() == 0:
            return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pen = QPen(
            self._color, self.THICKNESS,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
        painter.setPen(pen)
        painter.drawLine(self._line)

        # --- Arrowhead ---
        angle = math.atan2(
            -self._line.dy(), self._line.dx()
        )
        dest_center = self._line.p2()

        arrow_p1 = dest_center + QPointF(
            math.sin(angle + math.pi / 3) * self.ARROW_SIZE,
            math.cos(angle + math.pi / 3) * self.ARROW_SIZE,
        )
        arrow_p2 = dest_center + QPointF(
            math.sin(angle + math.pi - math.pi / 3) * self.ARROW_SIZE,
            math.cos(angle + math.pi - math.pi / 3) * self.ARROW_SIZE,
        )

        arrow = QPolygonF([dest_center, arrow_p1, arrow_p2])
        painter.setBrush(QBrush(self._color))
        painter.drawPolygon(arrow)

        # --- Edge label (relationship type) ---
        if self._relationship_type:
            mid = self._line.center()
            painter.setPen(QPen(QColor("#CBD5E1")))
            font = painter.font()
            font.setPointSize(7)
            painter.setFont(font)
            painter.drawText(
                mid + QPointF(4, -4),
                self._relationship_type,
            )
```

### Bezier Curved Edges

For a more polished look, especially when there are many edges between nearby nodes,
use `QPainterPath` with cubic Bezier curves:

```python
from PySide6.QtGui import QPainterPath
from PySide6.QtWidgets import QGraphicsPathItem


class CurvedEdge(QGraphicsPathItem):
    """A curved directed edge using cubic Bezier curves."""

    ARROW_SIZE = 12

    def __init__(self, source, dest, relationship_type="", parent=None):
        super().__init__(parent)
        self._source = source
        self._dest = dest
        self._relationship_type = relationship_type

        self.setPen(QPen(QColor("#94A3B8"), 1.5))
        self.setZValue(-1)

        source.add_edge(self)
        dest.add_edge(self)
        self.adjust()

    def adjust(self):
        """Rebuild the Bezier path between source and dest."""
        start = self._source.center_pos()
        end = self._dest.center_pos()

        # Control points offset horizontally for a nice curve
        dx = abs(end.x() - start.x()) * 0.5
        dy = (end.y() - start.y()) * 0.1

        ctrl1 = QPointF(start.x() + dx, start.y() + dy)
        ctrl2 = QPointF(end.x() - dx, end.y() - dy)

        path = QPainterPath()
        path.moveTo(start)
        path.cubicTo(ctrl1, ctrl2, end)
        self.setPath(path)

    def paint(self, painter, option, widget=None):
        # Draw the curve
        super().paint(painter, option, widget)

        # Draw arrowhead at the end of the curve
        path = self.path()
        if path.isEmpty():
            return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Get the angle at the endpoint for arrowhead rotation
        end_point = path.pointAtPercent(1.0)
        angle_degrees = path.angleAtPercent(1.0)
        angle_rad = math.radians(angle_degrees)

        # Compute arrowhead triangle
        arrow_p1 = end_point + QPointF(
            math.cos(angle_rad + math.pi / 6) * self.ARROW_SIZE,
            -math.sin(angle_rad + math.pi / 6) * self.ARROW_SIZE,
        )
        arrow_p2 = end_point + QPointF(
            math.cos(angle_rad - math.pi / 6) * self.ARROW_SIZE,
            -math.sin(angle_rad - math.pi / 6) * self.ARROW_SIZE,
        )

        arrow = QPolygonF([end_point, arrow_p1, arrow_p2])
        painter.setBrush(QBrush(QColor("#94A3B8")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(arrow)
```

### QPainterPath Key Methods for Edge Drawing

| Method | Purpose |
|---|---|
| `moveTo(start)` | Set the starting point |
| `cubicTo(ctrl1, ctrl2, end)` | Draw a cubic Bezier curve (4-point) |
| `quadTo(ctrl, end)` | Draw a quadratic Bezier curve (3-point) |
| `pointAtPercent(t)` | Get coordinates at fraction `t` along the path |
| `angleAtPercent(t)` | Get tangent angle (degrees) at fraction `t` |
| `length()` | Total path length |

### Straight vs Curved: When to Use Each

- **Straight lines:** Simpler, faster rendering, clearer for small graphs. Good default.
- **Curved lines:** Better visual separation when multiple edges are close together.
  Essential when there are bidirectional edges between the same pair of nodes (draw one
  curving up, one curving down). More expensive to render.

---

## 6. Interactive Features

### Click to Select / Inspect Entity

With `ItemIsSelectable` set, clicking a node toggles its `isSelected()` state.
Connect to scene signals to react:

```python
scene.selectionChanged.connect(on_selection_changed)

def on_selection_changed():
    selected = scene.selectedItems()
    if selected and isinstance(selected[0], EntityNode):
        node = selected[0]
        # Emit signal or call inspector panel with node.entity_id
        show_entity_inspector(node.entity_id)
```

### Drag to Rearrange

Already handled by `ItemIsMovable`. Nodes can be freely dragged. Edges update
automatically via `itemChange` -> `edge.adjust()`.

### Right-Click Context Menu

Override `contextMenuEvent` on the node item:

```python
from PySide6.QtWidgets import QMenu

class EntityNode(QGraphicsObject):
    # ... (existing code) ...

    def contextMenuEvent(self, event):
        menu = QMenu()
        menu.addAction("Open Entity", lambda: open_entity(self.entity_id))
        menu.addAction("Show Connections", lambda: highlight_connections(self))
        menu.addAction("Center on This", lambda: center_view_on(self))
        menu.addSeparator()
        menu.addAction("Hide Node", lambda: self.setVisible(False))
        menu.exec(event.screenPos())
```

For right-clicking on empty space (no node), handle it at the view level:

```python
class GraphView(QGraphicsView):
    def contextMenuEvent(self, event):
        item = self.itemAt(event.pos())
        if item is None:
            # Empty space menu
            menu = QMenu()
            menu.addAction("Fit All", self.fit_all)
            menu.addAction("Reset Layout", self.reset_layout)
            menu.exec(event.globalPos())
        else:
            # Let the item handle its own context menu
            super().contextMenuEvent(event)
```

### Hover Tooltips

Two approaches:

1. **Simple:** Call `item.setToolTip("text")` -- Qt handles the rest automatically.
2. **Rich:** Override `hoverEnterEvent` / `hoverLeaveEvent` for custom behavior
   (highlight node, show info panel, etc.), as shown in the EntityNode code above.

### Search-to-Highlight

```python
def search_and_highlight(scene, nodes_map, query: str):
    """Find nodes matching query and highlight them."""
    # Clear previous selection
    scene.clearSelection()

    query_lower = query.lower()
    matches = []
    for node_id, item in nodes_map.items():
        if query_lower in item._name.lower():
            item.setSelected(True)
            matches.append(item)
        else:
            item.setOpacity(0.3)  # dim non-matching

    # Center view on first match
    if matches:
        view = scene.views()[0]
        view.centerOn(matches[0])

    return matches

def clear_search(scene, nodes_map):
    """Restore all nodes to full opacity."""
    scene.clearSelection()
    for item in nodes_map.values():
        item.setOpacity(1.0)
```

### Handling Large Graphs (100+ Nodes)

For a worldbuilding tool, 100-500 nodes is a realistic range. Strategies:

**Culling / Viewport Clipping:**
QGraphicsView automatically handles this. The BSP tree spatial index in QGraphicsScene
means only items within the visible viewport are painted. No custom culling is needed
for this scale.

**Level-of-Detail (LOD):**
Override `paint()` to simplify rendering when zoomed out:

```python
def paint(self, painter, option, widget=None):
    # option.levelOfDetailFromTransform gives zoom level
    lod = option.levelOfDetailFromTransform(painter.worldTransform())

    if lod < 0.4:
        # Zoomed out: just draw a colored circle
        painter.setBrush(QBrush(self._color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, 20, 20)
    elif lod < 0.7:
        # Medium zoom: rectangle with name only
        painter.setBrush(QBrush(self._color))
        painter.drawRoundedRect(...)
        painter.drawText(name_rect, ..., self._name)
    else:
        # Full detail rendering
        self._paint_full(painter, option, widget)
```

**Clustering / Grouping:**
For very large graphs, collapse related nodes into a cluster node:

```python
# Use WorldGraph.get_entity_cluster() to find communities
# Replace a cluster of nodes with a single "group" node
# Double-click to expand the group
```

**Filtering:**
Let users filter by entity type, status, or progression step to reduce visible nodes:

```python
def filter_by_type(nodes_map, visible_types: set):
    for node_id, item in nodes_map.items():
        item.setVisible(item._entity_type in visible_types)
```

---

## 7. Performance

### QGraphicsView Performance Profile

QGraphicsView uses a BSP (Binary Space Partitioning) tree for spatial indexing. This means:

- **Item lookup** (e.g., `itemAt(pos)`, collision detection) is O(log n).
- **Painting** only processes items intersecting the visible viewport.
- With hundreds of items, QGraphicsView performs well out of the box.
- Performance issues typically appear at **10,000+ items** or with expensive `paint()` methods.

For our use case (100-500 nodes, 200-1000 edges), QGraphicsView will be fast without
special optimization.

### Item-Level Caching

```python
# Cache the painted result as a pixmap
item.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)
# Good for: items that rarely change appearance
# Tradeoff: uses more memory, stale if item appearance changes frequently

item.setCacheMode(QGraphicsItem.CacheMode.ItemCoordinateCache)
# Good for: items that change position but not appearance
# Regenerates cache when zoom level changes
```

**Recommendation:** Use `DeviceCoordinateCache` for nodes (they change appearance only
on select/hover) and `NoCache` for edges (they need to repaint when nodes move).

### View-Level Optimizations

```python
view = QGraphicsView(scene)

# Cache the background (static gradient or grid)
view.setCacheMode(
    QGraphicsView.CacheModeFlag.CacheBackground
)

# Only update the bounding rect of changed items (not the whole viewport)
view.setViewportUpdateMode(
    QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate
)

# Optimization flags
view.setOptimizationFlag(
    QGraphicsView.OptimizationFlag.DontSavePainterState, True
)
view.setOptimizationFlag(
    QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing, True
)
```

### Paint Method Best Practices

- **Avoid SVG rendering** in `paint()`. Use `QPainter` primitives (drawRect, drawEllipse, drawText).
- **Minimize pen/brush changes.** Group draws that use the same pen.
- **Use `QGraphicsItem.ItemFlag.ItemDoesntPropagateOpacityToChildren`** if child items do not need parent opacity.
- **Use `prepareGeometryChange()`** before modifying bounding rect, not after.

### When Performance Becomes a Problem

| Node Count | Expected Performance | Action |
|---|---|---|
| < 200 | Excellent | No optimization needed |
| 200 - 500 | Good | Enable DeviceCoordinateCache on nodes |
| 500 - 2000 | May lag on pan/zoom | Add LOD rendering, filter aggressively |
| 2000+ | Will lag | Cluster/collapse nodes, consider OpenGL viewport |

For OpenGL acceleration (extreme case):

```python
from PySide6.QtOpenGLWidgets import QOpenGLWidget
view.setViewport(QOpenGLWidget())
```

---

## 8. Recommendation for This Project

### Approach: Custom QGraphicsView Implementation

Based on this research, the recommended approach is:

1. **Do NOT use an existing node editor library.** NodeGraphQt, qtpynodeeditor, and
   SpatialNode are all designed for dataflow editors (nodes with input/output ports).
   Our use case is fundamentally different: entities as simple labeled nodes with
   named relationship edges.

2. **Build a custom implementation** using the official Qt NetworkX viewer example as
   a foundation. This gives us full control over:
   - How entity nodes look (color-coded by type, status indicators)
   - How relationship edges look (labeled, directed)
   - Integration with our existing `WorldGraph` class
   - Custom interaction patterns (inspect entity, highlight connections)

3. **Architecture:**
   - `EntityNode(QGraphicsObject)` -- custom node rendering with entity metadata
   - `RelationshipEdge(QGraphicsItem)` -- directed edge with arrowhead and label
   - `WorldGraphScene(QGraphicsScene)` -- manages the scene, builds from `WorldGraph.graph`
   - `WorldGraphView(QGraphicsView)` -- zoom/pan, context menus, search
   - Layout switcher using NetworkX layout algorithms

4. **Estimated effort:** 400-600 lines of code for the core visualization. The official
   Qt example is ~200 lines and handles the basic pattern; our version adds entity-specific
   rendering, relationship labels, filtering, LOD, and search.

5. **Layout defaults:**
   - Primary: `spring_layout` with `k=2.0` for spacing
   - Alternative: `multipartite_layout` grouped by entity_type
   - User-switchable via dropdown (as in the Qt example)

---

## 9. Sources

### Official Documentation
- [QGraphicsView -- Qt for Python](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QGraphicsView.html)
- [QGraphicsScene -- Qt for Python](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QGraphicsScene.html)
- [QGraphicsItem -- Qt for Python](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QGraphicsItem.html)
- [Graphics View Framework -- Qt for Python](https://doc.qt.io/qtforpython-6/overviews/qtwidgets-graphicsview.html)
- [NetworkX Viewer Example -- Qt for Python](https://doc.qt.io/qtforpython-6/examples/example_external_networkx.html)
- [NetworkX Drawing Documentation](https://networkx.org/documentation/stable/reference/drawing.html)

### Tutorials
- [PythonGUIs -- QGraphics Vector Graphics in PySide6](https://www.pythonguis.com/tutorials/pyside6-qgraphics-vector-graphics/)
- [PenguinTutor -- QGraphicsView and QGraphicsScene in PySide6](https://www.penguintutor.com/programming/pyside6-qgraphicsscene)
- [SpinnCode -- QGraphicsView and QGraphicsScene Tutorial](https://spinncode.com/designs/GA6lFpb6)
- [RipTutorial -- Pan, Zoom, and Rotate with QGraphicsView](https://riptutorial.com/qt/example/24869/pan--zoom--and-rotate-with-qgraphicsview)
- [Qt Wiki -- Smooth Zoom in QGraphicsView](https://wiki.qt.io/Smooth_Zoom_In_QGraphicsView)

### Libraries Evaluated
- [NodeGraphQt (jchanvfx)](https://github.com/jchanvfx/NodeGraphQt) -- 1,600 stars, MIT
- [NodeGraphQt-PySide6 (C3RV1)](https://github.com/C3RV1/NodeGraphQt-PySide6) -- PySide6 port
- [OdenGraphQt (hueyyeng)](https://github.com/hueyyeng/OdenGraphQt) -- PySide6 fork, MIT
- [qtpynodeeditor (klauer)](https://github.com/klauer/qtpynodeeditor) -- 235 stars, BSD-3
- [SpatialNode](https://github.com/SpatialGraphics/SpatialNode) -- 9 stars, MIT, PySide6
- [nodegraph-pyqt (dsideb)](https://github.com/dsideb/nodegraph-pyqt) -- DAG viz with NetworkX

### Performance Resources
- [Qt Forum -- How to Optimize QGraphicsView Performance](https://forum.qt.io/topic/140557/how-to-optimize-qgraphicsview-performance)
- [Qt Forum -- QGraphicsView Performance with Lots of Items](https://forum.qt.io/topic/6793/qgraphicsview-performance-with-lots-of-items)
- [Runebook -- Improving Qt Graphics Performance: Caching, Culling, and More](https://runebook.dev/en/articles/qt/qgraphicsview/cacheMode-prop)

### QPainterPath / Edge Drawing
- [QPainterPath -- Qt for Python](https://doc.qt.io/qtforpython-6/PySide6/QtGui/QPainterPath.html)
- [Qt Forum -- Drawing a Bezier Curve in QGraphicsScene](https://forum.qt.io/topic/34114/drawing-a-bezier-curve-in-qgraphicsscene-solved)
- [Qt Forum -- Draggable Bezier Curve Points with QPainterPath](https://forum.qt.io/topic/51449/draggable-bezier-curve-points-with-qpainterpath-in-qgraphicsview/)
