# PySide6 Architecture Research for Worldbuilding Tool

> **Date:** January 2026
> **Purpose:** Architecture research for a multi-panel worldbuilding desktop application with knowledge graph, entity browser, chat/streaming panel, and card layouts.

---

## Table of Contents

1. [Application Structure Patterns](#1-application-structure-patterns)
2. [Model-View Architecture](#2-model-view-architecture)
3. [Signal/Slot Patterns](#3-signalslot-patterns)
4. [State Management](#4-state-management)
5. [Threading and Async](#5-threading-and-async)
6. [Project Layout](#6-project-layout)
7. [Testing](#7-testing)
8. [Recommendation Summary](#8-recommendation-summary)
9. [Sources](#9-sources)

---

## 1. Application Structure Patterns

### The Four Main Approaches

For a multi-panel application, PySide6 offers four layout strategies. Each has distinct tradeoffs.

#### 1.1 QMainWindow with QDockWidget (Recommended for this project)

`QMainWindow` provides a framework with a central widget surrounded by four dock areas (left, right, top, bottom). Each dock area can hold `QDockWidget` instances that the user can:

- **Float** (undock as independent windows)
- **Drag** to different dock areas
- **Tab-stack** on top of each other (built-in)
- **Resize** via splitter handles between docked widgets

This is the closest pattern to IDE-style layouts (VS Code, Qt Creator) and is the best fit for a tool with 4-5 panels that the user should be able to rearrange.

```python
from PySide6.QtWidgets import QMainWindow, QDockWidget, QTextEdit
from PySide6.QtCore import Qt


class WorldbuilderMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Worldbuilding Tool")

        # Central widget -- the primary workspace (e.g., knowledge graph)
        self.graph_view = KnowledgeGraphWidget()
        self.setCentralWidget(self.graph_view)

        # Entity Browser -- docked left
        self.entity_dock = QDockWidget("Entity Browser", self)
        self.entity_dock.setWidget(EntityBrowserWidget())
        self.entity_dock.setAllowedAreas(
            Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea
        )
        self.addDockWidget(Qt.LeftDockWidgetArea, self.entity_dock)

        # Chat/Streaming Panel -- docked right
        self.chat_dock = QDockWidget("Chat", self)
        self.chat_dock.setWidget(ChatStreamingWidget())
        self.addDockWidget(Qt.RightDockWidgetArea, self.chat_dock)

        # Card Layout Panel -- docked bottom
        self.card_dock = QDockWidget("Cards", self)
        self.card_dock.setWidget(CardLayoutWidget())
        self.addDockWidget(Qt.BottomDockWidgetArea, self.card_dock)

        # Enable nested docking for more flexible arrangements
        self.setDockNestingEnabled(True)

        # View menu to toggle panel visibility
        view_menu = self.menuBar().addMenu("View")
        view_menu.addAction(self.entity_dock.toggleViewAction())
        view_menu.addAction(self.chat_dock.toggleViewAction())
        view_menu.addAction(self.card_dock.toggleViewAction())
```

**Key API for saving/restoring layout:**

```python
def save_layout(self):
    """Save window geometry and dock layout to QSettings."""
    settings = QSettings("WorldbuilderOrg", "WorldbuilderApp")
    settings.setValue("geometry", self.saveGeometry())
    settings.setValue("windowState", self.saveState())

def restore_layout(self):
    """Restore window geometry and dock layout from QSettings."""
    settings = QSettings("WorldbuilderOrg", "WorldbuilderApp")
    geometry = settings.value("geometry")
    state = settings.value("windowState")
    if geometry:
        self.restoreGeometry(geometry)
    if state:
        self.restoreState(state)
```

#### 1.2 QSplitter (Nested)

`QSplitter` gives the user direct resize control via drag handles. Nesting splitters creates complex grid layouts. This is simpler to implement than dock widgets but does **not** support floating, drag-and-drop rearrangement, or tab stacking.

```python
from PySide6.QtWidgets import QSplitter
from PySide6.QtCore import Qt


class SplitterLayout(QSplitter):
    def __init__(self):
        super().__init__(Qt.Horizontal)

        # Left panel
        self.entity_browser = EntityBrowserWidget()
        self.addWidget(self.entity_browser)

        # Right side: vertical split between graph and bottom panels
        right_splitter = QSplitter(Qt.Vertical)

        # Top-right: horizontal split between graph and chat
        top_splitter = QSplitter(Qt.Horizontal)
        top_splitter.addWidget(KnowledgeGraphWidget())
        top_splitter.addWidget(ChatStreamingWidget())
        top_splitter.setSizes([600, 400])

        right_splitter.addWidget(top_splitter)
        right_splitter.addWidget(CardLayoutWidget())
        right_splitter.setSizes([500, 200])

        self.addWidget(right_splitter)
        self.setSizes([250, 750])
```

`QSplitter` supports `saveState()` / `restoreState()` for persisting user-set sizes.

**Best for:** Fixed panel arrangements where you want user-resizable areas but not drag rearrangement.

#### 1.3 QTabWidget

Presents panels as tabs -- only one visible at a time. Good for secondary content but loses the side-by-side view critical for a worldbuilding tool.

```python
from PySide6.QtWidgets import QTabWidget

tabs = QTabWidget()
tabs.addTab(KnowledgeGraphWidget(), "Knowledge Graph")
tabs.addTab(EntityBrowserWidget(), "Entities")
tabs.addTab(ChatStreamingWidget(), "Chat")
tabs.addTab(CardLayoutWidget(), "Cards")
tabs.setTabPosition(QTabWidget.South)
tabs.setMovable(True)  # User can reorder tabs
```

**Best for:** Situations where panels are used one at a time, or as a secondary navigation within a dock widget.

#### 1.4 QStackedWidget

Programmatic tab switching without visible tab bar. One widget visible at a time, switched by code (e.g., from a sidebar or menu selection). Useful for wizard-style flows or modal panel switching.

**Best for:** Internal implementation detail within a panel, not as the top-level layout.

#### 1.5 Qt Advanced Docking System (Third-Party)

For VS Code-level docking flexibility, the [Qt Advanced Docking System](https://github.com/githubuser0xFFFF/Qt-Advanced-Docking-System) (ADS) provides drag-and-drop tab reordering, split-anywhere behavior, and perspective management (named layouts). PySide6 bindings are available via PyPI:

```bash
pip install PySide6-QtAds
```

ADS uses standard `QSplitter` internally for resize separators, so it inherits that familiarity. It is LGPL-licensed and actively maintained.

**Consideration:** ADS adds a dependency but provides polish that would take significant effort to replicate. Worth evaluating if the built-in `QDockWidget` proves too limited.

### Recommendation for This Project

**Use `QMainWindow` with `QDockWidget` as the primary layout.** The knowledge graph panel serves as the central widget. Entity browser, chat panel, and card layout are dock widgets. This gives users the freedom to rearrange panels while the built-in `saveState`/`restoreState` handles layout persistence. If the built-in docking proves insufficient (e.g., users want to split dock areas freely), upgrade to Qt Advanced Docking System.

---

## 2. Model-View Architecture

Qt's Model/View framework separates data (Model) from presentation (View), with optional delegates for custom rendering and editing.

### 2.1 Choosing the Right Base Class

| Base Class | Use Case |
|---|---|
| `QAbstractListModel` | Flat lists (entity browser list) |
| `QAbstractTableModel` | Tabular data (entity attributes, card grids) |
| `QAbstractItemModel` | Hierarchical/tree data (category trees, knowledge graph hierarchy) |
| `QStandardItemModel` | Quick prototyping (not recommended for production -- less control) |

For the entity browser, `QAbstractListModel` or `QAbstractTableModel` is the right choice. For a hierarchical entity tree (entities grouped by category), use `QAbstractItemModel`.

### 2.2 Building an Entity List Model

```python
from PySide6.QtCore import QAbstractListModel, Qt, QModelIndex


class EntityListModel(QAbstractListModel):
    """Model backed by a list of entity dictionaries."""

    def __init__(self, entities=None, parent=None):
        super().__init__(parent)
        self._entities = entities or []

    def rowCount(self, parent=QModelIndex()):
        return len(self._entities)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._entities)):
            return None

        entity = self._entities[index.row()]

        if role == Qt.DisplayRole:
            return entity.get("name", "Unnamed")
        elif role == Qt.ToolTipRole:
            return entity.get("description", "")
        elif role == Qt.UserRole:
            # Return the full entity dict for programmatic access
            return entity
        return None

    def flags(self, index):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    # --- Mutation methods that properly notify views ---

    def add_entity(self, entity):
        row = len(self._entities)
        self.beginInsertRows(QModelIndex(), row, row)
        self._entities.append(entity)
        self.endInsertRows()

    def remove_entity(self, row):
        self.beginRemoveRows(QModelIndex(), row, row)
        del self._entities[row]
        self.endRemoveRows()

    def update_entity(self, row, entity):
        self._entities[row] = entity
        index = self.index(row)
        self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.UserRole])

    def get_entities(self):
        """Direct access to underlying data for serialization."""
        return self._entities
```

**Critical rule:** Always call `beginInsertRows`/`endInsertRows`, `beginRemoveRows`/`endRemoveRows`, or emit `dataChanged` when modifying data. Views rely on these signals to update.

### 2.3 Search and Filter with QSortFilterProxyModel

`QSortFilterProxyModel` sits between the source model and the view, providing filtering and sorting without modifying the source data.

```python
from PySide6.QtCore import QSortFilterProxyModel, Qt, QRegularExpression
from PySide6.QtWidgets import QLineEdit, QListView, QVBoxLayout, QWidget


class EntityBrowserWidget(QWidget):
    def __init__(self, entity_model, parent=None):
        super().__init__(parent)

        # Proxy model for filtering
        self.proxy_model = QSortFilterProxyModel(self)
        self.proxy_model.setSourceModel(entity_model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy_model.setFilterKeyColumn(-1)  # Search all columns

        # Search box
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search entities...")
        self.search_box.textChanged.connect(self._on_filter_changed)

        # List view
        self.list_view = QListView()
        self.list_view.setModel(self.proxy_model)

        layout = QVBoxLayout(self)
        layout.addWidget(self.search_box)
        layout.addWidget(self.list_view)

    def _on_filter_changed(self, text):
        # Use regex for flexible matching
        regex = QRegularExpression(
            text, QRegularExpression.CaseInsensitiveOption
        )
        self.proxy_model.setFilterRegularExpression(regex)
```

**Custom multi-field filtering** -- override `filterAcceptsRow` for searching across name, description, tags, etc.:

```python
class EntityFilterProxy(QSortFilterProxyModel):
    """Filter entities by name, type, and tags simultaneously."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._type_filter = None
        self._tag_filter = None

    def set_type_filter(self, entity_type):
        self._type_filter = entity_type
        self.invalidateFilter()

    def set_tag_filter(self, tag):
        self._tag_filter = tag
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()
        index = model.index(source_row, 0, source_parent)
        entity = model.data(index, Qt.UserRole)

        if not entity:
            return False

        # Text search (uses the built-in filter regexp)
        name = entity.get("name", "")
        if self.filterRegularExpression().pattern():
            if not self.filterRegularExpression().match(name).hasMatch():
                return False

        # Type filter
        if self._type_filter and entity.get("type") != self._type_filter:
            return False

        # Tag filter
        if self._tag_filter and self._tag_filter not in entity.get("tags", []):
            return False

        return True
```

### 2.4 Best Practices for Connecting Python Data to Qt Views

1. **Keep models as thin wrappers.** The model should reference your data, not own complex business logic. Business logic belongs in a service layer.
2. **Use `Qt.UserRole` and custom roles** to expose full data objects to delegates and slots, not just display strings.
3. **Emit signals precisely.** `dataChanged` should specify the exact roles that changed to avoid unnecessary re-renders.
4. **Thread safety:** `QAbstractItemModel` is NOT thread-safe. All model mutations must happen on the main thread. If background work produces data, use signals to marshal updates to the main thread.
5. **Consider `QIdentityProxyModel`** for adding computed columns or role transformations without touching the source model.

---

## 3. Signal/Slot Patterns

### 3.1 Core Mechanics

Signals and slots are Qt's inter-object communication mechanism. A signal is emitted when an event occurs; connected slots are called in response. The key advantage over callbacks is **decoupling** -- the emitter does not need to know who receives the signal.

```python
from PySide6.QtCore import QObject, Signal, Slot


class EntityService(QObject):
    entity_created = Signal(dict)
    entity_updated = Signal(str, dict)  # (entity_id, updated_data)
    entity_deleted = Signal(str)


class KnowledgeGraphWidget(QWidget):
    @Slot(dict)
    def on_entity_created(self, entity):
        self.add_node(entity)

    @Slot(str, dict)
    def on_entity_updated(self, entity_id, data):
        self.update_node(entity_id, data)
```

### 3.2 Direct Connections vs. Central Event Bus

#### Direct Connections

The simplest pattern -- widget A connects directly to widget B:

```python
# In the main window, wire up direct connections
self.entity_browser.entity_selected.connect(self.graph_view.highlight_entity)
self.entity_browser.entity_selected.connect(self.card_panel.show_entity)
self.chat_panel.entity_mentioned.connect(self.entity_browser.select_entity)
```

**Pros:** Explicit, easy to trace, type-safe.
**Cons:** The main window becomes a wiring hub. Adding a new panel requires modifying existing connection code. With 4-5 panels, this is still manageable.

#### Central Event Bus (Singleton Signal Hub)

For larger applications, a central event bus avoids direct references between widgets:

```python
from PySide6.QtCore import QObject, Signal


class EventBus(QObject):
    """Application-wide signal hub. Singleton."""

    # Entity events
    entity_selected = Signal(str)          # entity_id
    entity_created = Signal(dict)          # entity_data
    entity_updated = Signal(str, dict)     # entity_id, data
    entity_deleted = Signal(str)           # entity_id

    # Navigation events
    navigate_to_entity = Signal(str)       # entity_id
    panel_focus_requested = Signal(str)    # panel_name

    # Chat events
    streaming_started = Signal()
    streaming_token = Signal(str)
    streaming_finished = Signal(str)       # complete_response

    _instance = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


# In any widget -- no direct references needed:
class EntityBrowserWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.bus = EventBus.instance()
        self.list_view.clicked.connect(self._on_entity_clicked)

    def _on_entity_clicked(self, index):
        entity_id = index.data(Qt.UserRole)["id"]
        self.bus.entity_selected.emit(entity_id)


class KnowledgeGraphWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.bus = EventBus.instance()
        self.bus.entity_selected.connect(self.highlight_entity)
```

**Pros:** Fully decoupled. New panels just subscribe to existing signals. No central wiring code.
**Cons:** Harder to trace signal flow. Can become a "god object" if signals proliferate without discipline. Use for cross-cutting concerns (entity selection, navigation), not for internal widget plumbing.

### 3.3 Recommended Hybrid Approach

For a 4-5 panel application:

1. **Use an EventBus** for cross-panel communication (entity selection, navigation, state sync).
2. **Use direct connections** for parent-child widget communication within a panel.
3. **Use model signals** (`dataChanged`, `rowsInserted`) for data-driven updates.

### 3.4 Avoiding Spaghetti Connections

- **Rule of thumb:** If a signal crosses panel boundaries, route it through the EventBus. If it stays within a panel, connect directly.
- **Document signal contracts.** Each signal on the EventBus should have a docstring specifying its payload semantics.
- **Avoid lambda slots for anything non-trivial.** Named methods are easier to debug and disconnect.
- **Use `@Slot()` decorator** on receiver methods. This improves performance slightly (bypasses Python introspection) and documents intent.
- **Disconnect signals in `closeEvent` or destructors** if widgets are dynamically created/destroyed, to avoid dangling connections.

---

## 4. State Management

### 4.1 Architecture: Separating UI State from Application State

For a worldbuilding tool, state exists at three levels:

| Level | Examples | Storage |
|---|---|---|
| **Document State** | Entities, relationships, graph data | `state.json` (or project file) |
| **UI Preferences** | Window geometry, panel arrangement, font size | `QSettings` (platform-native) |
| **Session State** | Currently selected entity, scroll positions, expanded tree nodes | In-memory (optionally saved to QSettings) |

### 4.2 QSettings for User Preferences

`QSettings` uses platform-native storage (Windows Registry, macOS plist, Linux ini files). Use it for preferences, not document data.

```python
from PySide6.QtCore import QSettings


class AppSettings:
    """Centralized access to user preferences."""

    def __init__(self):
        self._settings = QSettings("WorldbuilderOrg", "WorldbuilderApp")

    # --- Window layout ---

    def save_window_state(self, main_window):
        self._settings.setValue("window/geometry", main_window.saveGeometry())
        self._settings.setValue("window/state", main_window.saveState())

    def restore_window_state(self, main_window):
        geom = self._settings.value("window/geometry")
        state = self._settings.value("window/state")
        if geom:
            main_window.restoreGeometry(geom)
        if state:
            main_window.restoreState(state)

    # --- User preferences ---

    @property
    def theme(self):
        return self._settings.value("appearance/theme", "dark")

    @theme.setter
    def theme(self, value):
        self._settings.setValue("appearance/theme", value)

    @property
    def auto_save_interval(self):
        return int(self._settings.value("editor/autoSaveInterval", 30))

    @auto_save_interval.setter
    def auto_save_interval(self, seconds):
        self._settings.setValue("editor/autoSaveInterval", seconds)

    @property
    def recent_files(self):
        return self._settings.value("files/recent", []) or []

    @recent_files.setter
    def recent_files(self, paths):
        self._settings.setValue("files/recent", paths)
```

### 4.3 Syncing UI State with state.json

For document state (entities, relationships, graph layout), use a dedicated state manager that reads/writes JSON and notifies the UI via signals:

```python
import json
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QTimer


class ProjectState(QObject):
    """Manages project document state with file-based persistence."""

    state_loaded = Signal(dict)
    state_changed = Signal()
    entity_changed = Signal(str)  # entity_id

    def __init__(self, state_path: Path, parent=None):
        super().__init__(parent)
        self._path = state_path
        self._data = {}
        self._dirty = False

        # Auto-save timer
        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.timeout.connect(self.save_if_dirty)
        self._auto_save_timer.start(30_000)  # 30 seconds

    def load(self):
        if self._path.exists():
            with open(self._path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        else:
            self._data = {"entities": {}, "relationships": [], "metadata": {}}
        self._dirty = False
        self.state_loaded.emit(self._data)

    def save(self):
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)
        self._dirty = False

    def save_if_dirty(self):
        if self._dirty:
            self.save()

    # --- Entity CRUD ---

    def get_entity(self, entity_id: str) -> dict:
        return self._data["entities"].get(entity_id)

    def set_entity(self, entity_id: str, entity_data: dict):
        self._data["entities"][entity_id] = entity_data
        self._dirty = True
        self.entity_changed.emit(entity_id)
        self.state_changed.emit()

    def delete_entity(self, entity_id: str):
        if entity_id in self._data["entities"]:
            del self._data["entities"][entity_id]
            self._dirty = True
            self.state_changed.emit()

    @property
    def entities(self) -> dict:
        return self._data.get("entities", {})

    @property
    def is_dirty(self) -> bool:
        return self._dirty
```

### 4.4 Connecting State to Models

The Qt model should reflect the `ProjectState`. When state changes, update the model:

```python
class EntityListModel(QAbstractListModel):
    def __init__(self, project_state: ProjectState, parent=None):
        super().__init__(parent)
        self._state = project_state
        self._entity_ids = []

        # React to state changes
        self._state.state_loaded.connect(self._on_state_loaded)
        self._state.state_changed.connect(self._refresh)

    def _on_state_loaded(self, data):
        self.beginResetModel()
        self._entity_ids = list(data.get("entities", {}).keys())
        self.endResetModel()

    def _refresh(self):
        new_ids = list(self._state.entities.keys())
        if new_ids != self._entity_ids:
            self.beginResetModel()
            self._entity_ids = new_ids
            self.endResetModel()
```

### 4.5 Undo/Redo with QUndoStack

For a worldbuilding tool, undo/redo is valuable. Qt provides `QUndoStack` and `QUndoCommand`:

```python
from PySide6.QtGui import QUndoCommand, QUndoStack


class UpdateEntityCommand(QUndoCommand):
    def __init__(self, state: ProjectState, entity_id: str,
                 old_data: dict, new_data: dict):
        super().__init__(f"Update {new_data.get('name', entity_id)}")
        self._state = state
        self._entity_id = entity_id
        self._old = old_data
        self._new = new_data

    def redo(self):
        self._state.set_entity(self._entity_id, self._new)

    def undo(self):
        self._state.set_entity(self._entity_id, self._old)


# Usage:
undo_stack = QUndoStack()
cmd = UpdateEntityCommand(project_state, "ent_001", old_data, new_data)
undo_stack.push(cmd)  # Calls redo() automatically
```

---

## 5. Threading and Async

### 5.1 The Problem

Qt's main thread runs the event loop that processes user input and repaints the UI. Any long-running work on this thread (network requests, file I/O, LLM API calls) freezes the interface. PySide6 offers several solutions.

### 5.2 QThread Worker Pattern (Recommended for Simple Tasks)

The "worker object" pattern is the most idiomatic Qt approach. Create a `QObject` with your work logic, move it to a `QThread`, and communicate via signals.

```python
from PySide6.QtCore import QObject, QThread, Signal, Slot


class FileLoadWorker(QObject):
    finished = Signal(dict)
    error = Signal(str)
    progress = Signal(int)

    def __init__(self, file_path):
        super().__init__()
        self._path = file_path

    @Slot()
    def run(self):
        try:
            import json
            with open(self._path, "r") as f:
                data = json.load(f)
            self.finished.emit(data)
        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    def load_project(self, path):
        self._thread = QThread()
        self._worker = FileLoadWorker(path)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_project_loaded)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)

        self._thread.start()

    def _on_project_loaded(self, data):
        # Safe -- this runs on the main thread via queued connection
        self.project_state.load_from_dict(data)
```

**Important:** Keep references to `QThread` and worker objects as instance attributes (`self._thread`, `self._worker`). Otherwise Python's garbage collector destroys them while the thread is still running.

### 5.3 QThreadPool + QRunnable (For Task Pools)

When you have many small tasks (e.g., loading multiple entity files), `QThreadPool` manages a pool of threads:

```python
from PySide6.QtCore import QRunnable, QThreadPool, Signal, QObject, Slot


class WorkerSignals(QObject):
    finished = Signal(object)
    error = Signal(str)


class EntityLoadTask(QRunnable):
    def __init__(self, entity_id, loader_fn):
        super().__init__()
        self.entity_id = entity_id
        self.loader_fn = loader_fn
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            result = self.loader_fn(self.entity_id)
            self.signals.finished.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))


# Submit multiple tasks
pool = QThreadPool.globalInstance()
for entity_id in entity_ids:
    task = EntityLoadTask(entity_id, load_entity_from_disk)
    task.signals.finished.connect(on_entity_loaded)
    pool.start(task)
```

### 5.4 asyncio Integration for Streaming Responses

For LLM streaming (token-by-token responses), `asyncio` is the natural fit since most LLM client libraries are async-native. There are three ways to integrate asyncio with Qt:

#### Option A: PySide6.QtAsyncio (Official, Recommended)

Available since PySide6 6.6.0. Replaces the asyncio event loop with one that runs inside Qt's event loop.

```python
import asyncio
import PySide6.QtAsyncio as QtAsyncio
from PySide6.QtWidgets import QApplication, QMainWindow


class ChatPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(
            lambda: asyncio.ensure_future(self.stream_response())
        )

        layout = QVBoxLayout(self)
        layout.addWidget(self.text_edit)
        layout.addWidget(self.send_button)

    async def stream_response(self):
        """Stream LLM tokens into the QTextEdit."""
        self.send_button.setEnabled(False)
        self.text_edit.clear()

        try:
            # Example with an async LLM client
            async for token in self.llm_client.stream("Describe a fantasy city"):
                # This runs on the main thread -- safe to update UI
                self.text_edit.moveCursor(QTextCursor.End)
                self.text_edit.insertPlainText(token)
                # Force UI repaint so user sees each token
                QApplication.processEvents()
        finally:
            self.send_button.setEnabled(True)


# Application entry point
if __name__ == "__main__":
    app = QApplication([])
    window = WorldbuilderMainWindow()
    window.show()
    # This replaces app.exec() -- runs both Qt and asyncio event loops
    QtAsyncio.run()
```

#### Option B: qasync (Third-Party, Mature)

The `qasync` library provides the `@asyncSlot()` decorator for cleaner integration:

```python
import asyncio
from qasync import QEventLoop, asyncSlot


class ChatPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.text_edit = QTextEdit()
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.on_send)

        layout = QVBoxLayout(self)
        layout.addWidget(self.text_edit)
        layout.addWidget(self.send_button)

    @asyncSlot()
    async def on_send(self):
        """Slot that handles async streaming."""
        self.send_button.setEnabled(False)
        try:
            async for token in self.llm_client.stream("Describe a fantasy city"):
                self.text_edit.moveCursor(QTextCursor.End)
                self.text_edit.insertPlainText(token)
        finally:
            self.send_button.setEnabled(True)


# Entry point with qasync
app = QApplication([])
loop = QEventLoop(app)
asyncio.set_event_loop(loop)
window = WorldbuilderMainWindow()
window.show()
with loop:
    loop.run_forever()
```

#### Option C: Background Thread + Signals (No asyncio in Main Thread)

If you prefer to keep asyncio completely separate from the Qt event loop:

```python
import asyncio
import threading
from PySide6.QtCore import QObject, Signal


class StreamingWorker(QObject):
    token_received = Signal(str)
    stream_finished = Signal(str)  # complete text
    stream_error = Signal(str)

    def __init__(self, prompt: str, llm_client):
        super().__init__()
        self._prompt = prompt
        self._client = llm_client

    def start(self):
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()

    def _run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._stream())
        finally:
            loop.close()

    async def _stream(self):
        full_text = ""
        try:
            async for token in self._client.stream(self._prompt):
                full_text += token
                # Signal is thread-safe via queued connection
                self.token_received.emit(token)
            self.stream_finished.emit(full_text)
        except Exception as e:
            self.stream_error.emit(str(e))


# In the chat panel:
class ChatPanel(QWidget):
    def start_streaming(self, prompt):
        self._worker = StreamingWorker(prompt, self.llm_client)
        self._worker.token_received.connect(self._append_token)
        self._worker.stream_finished.connect(self._on_stream_done)
        self._worker.start()

    def _append_token(self, token):
        self.text_edit.moveCursor(QTextCursor.End)
        self.text_edit.insertPlainText(token)
```

### 5.5 Comparison Table

| Approach | Complexity | asyncio Support | Best For |
|---|---|---|---|
| QThread + Worker | Low | No | Simple background tasks, file I/O |
| QThreadPool + QRunnable | Medium | No | Parallel tasks, batch operations |
| QtAsyncio | Low | Native | Streaming, async API clients |
| qasync | Low | Native | Streaming (more mature, better docs) |
| Background thread + signals | Medium | Isolated | When you want asyncio separated from Qt |

### 5.6 Recommendation

**Use `qasync` (or `PySide6.QtAsyncio` if on PySide6 >= 6.6) for the chat/streaming panel.** The `@asyncSlot` pattern maps directly to the "user clicks Send, tokens stream in" use case. For non-async background work (file loading, graph layout computation), use the QThread worker pattern.

---

## 6. Project Layout

### 6.1 Recommended Directory Structure

```
worldbuilding-tool/
├── pyproject.toml              # Project metadata, dependencies, build config
├── README.md
├── requirements.txt            # Or use pyproject.toml [project.dependencies]
│
├── src/
│   └── worldbuilder/
│       ├── __init__.py
│       ├── __main__.py         # Entry point: python -m worldbuilder
│       ├── app.py              # QApplication setup, event loop init
│       │
│       ├── core/               # Business logic -- NO Qt dependencies
│       │   ├── __init__.py
│       │   ├── entities.py     # Entity data classes, validation
│       │   ├── relationships.py
│       │   ├── graph.py        # Knowledge graph operations
│       │   ├── project.py      # Project file management
│       │   └── llm_client.py   # LLM API wrapper (async)
│       │
│       ├── models/             # Qt Models (bridge between core and views)
│       │   ├── __init__.py
│       │   ├── entity_model.py
│       │   ├── relationship_model.py
│       │   └── filter_proxies.py
│       │
│       ├── views/              # Qt Widgets -- UI only
│       │   ├── __init__.py
│       │   ├── main_window.py
│       │   ├── graph_panel.py
│       │   ├── entity_browser.py
│       │   ├── chat_panel.py
│       │   ├── card_layout.py
│       │   └── dialogs/
│       │       ├── __init__.py
│       │       ├── entity_editor.py
│       │       └── settings_dialog.py
│       │
│       ├── widgets/            # Reusable custom widgets
│       │   ├── __init__.py
│       │   ├── search_bar.py
│       │   ├── tag_editor.py
│       │   └── streaming_text.py
│       │
│       ├── services/           # Application services (state, events)
│       │   ├── __init__.py
│       │   ├── event_bus.py
│       │   ├── state_manager.py
│       │   ├── settings.py
│       │   └── undo_manager.py
│       │
│       └── resources/          # Static assets
│           ├── icons/
│           ├── styles/
│           │   ├── dark.qss
│           │   └── light.qss
│           └── resources.qrc   # Qt resource file (optional)
│
├── tests/
│   ├── conftest.py             # Shared fixtures (qtbot, mock state)
│   ├── test_core/
│   │   ├── test_entities.py
│   │   └── test_graph.py
│   ├── test_models/
│   │   └── test_entity_model.py
│   └── test_views/
│       └── test_entity_browser.py
│
└── docs/
    └── architecture.md
```

### 6.2 Key Principles

**Separation of concerns by directory:**

- `core/` -- Pure Python. No Qt imports. Testable without a running QApplication. Contains data structures, algorithms, API clients.
- `models/` -- Qt Models that wrap `core/` data for use with Qt views. Depends on `core/` and `PySide6.QtCore`.
- `views/` -- Qt Widgets. Depends on `models/` and `PySide6.QtWidgets`. Should contain minimal logic -- delegate to services.
- `services/` -- Application-level concerns: event bus, state management, settings. These are `QObject` subclasses that coordinate between views and core.
- `widgets/` -- Small, reusable UI components (a search bar, a tag editor). These do NOT depend on the specific application domain.

**Dependency flow:**

```
views/ --> models/ --> core/
  |           |
  v           v
services/ (event bus, state)
```

Views depend on models and services. Models depend on core. Core depends on nothing (pure Python). Services bridge everything.

### 6.3 Entry Point

```python
# src/worldbuilder/__main__.py
import sys
from PySide6.QtWidgets import QApplication
from worldbuilder.app import create_app

def main():
    app = QApplication(sys.argv)
    window = create_app()
    window.show()

    # If using qasync:
    # import asyncio
    # from qasync import QEventLoop
    # loop = QEventLoop(app)
    # asyncio.set_event_loop(loop)
    # with loop:
    #     loop.run_forever()

    # If using QtAsyncio:
    # import PySide6.QtAsyncio as QtAsyncio
    # QtAsyncio.run()

    # Standard (no async):
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
```

```python
# src/worldbuilder/app.py
from worldbuilder.services.event_bus import EventBus
from worldbuilder.services.state_manager import ProjectState
from worldbuilder.services.settings import AppSettings
from worldbuilder.models.entity_model import EntityListModel
from worldbuilder.views.main_window import WorldbuilderMainWindow


def create_app():
    """Wire up application dependencies and return the main window."""
    settings = AppSettings()
    event_bus = EventBus.instance()

    # Load or create project state
    project_state = ProjectState(settings.last_project_path)
    project_state.load()

    # Create models
    entity_model = EntityListModel(project_state)

    # Create main window with dependencies
    window = WorldbuilderMainWindow(
        project_state=project_state,
        entity_model=entity_model,
        settings=settings,
    )
    settings.restore_window_state(window)

    return window
```

### 6.4 Resource Management

**QSS Stylesheets** -- load from files at startup:

```python
from pathlib import Path

def load_stylesheet(theme="dark"):
    style_path = Path(__file__).parent / "resources" / "styles" / f"{theme}.qss"
    if style_path.exists():
        return style_path.read_text()
    return ""

# In app setup:
app.setStyleSheet(load_stylesheet("dark"))
```

**Icons** -- use Qt's resource system or load from paths:

```python
from PySide6.QtGui import QIcon
from pathlib import Path

ICON_DIR = Path(__file__).parent / "resources" / "icons"

def get_icon(name: str) -> QIcon:
    path = ICON_DIR / f"{name}.svg"
    return QIcon(str(path))
```

---

## 7. Testing

### 7.1 pytest-qt Setup

[pytest-qt](https://github.com/pytest-dev/pytest-qt) is the standard testing plugin for PySide6 applications. Install it alongside PySide6:

```bash
pip install pytest pytest-qt
```

Configure it for PySide6 in `pytest.ini` or `pyproject.toml`:

```toml
# pyproject.toml
[tool.pytest.ini_options]
qt_api = "pyside6"
```

### 7.2 Testing Widgets

The `qtbot` fixture creates a `QApplication` automatically and provides methods for simulating user interaction.

```python
import pytest
from PySide6.QtCore import Qt
from worldbuilder.views.entity_browser import EntityBrowserWidget
from worldbuilder.models.entity_model import EntityListModel


@pytest.fixture
def entity_model():
    """Create a model with test data."""
    model = EntityListModel()
    model.add_entity({"id": "1", "name": "Gondor", "type": "kingdom"})
    model.add_entity({"id": "2", "name": "Mordor", "type": "kingdom"})
    model.add_entity({"id": "3", "name": "Gandalf", "type": "character"})
    return model


@pytest.fixture
def browser(qtbot, entity_model):
    widget = EntityBrowserWidget(entity_model)
    qtbot.addWidget(widget)  # Ensures cleanup
    widget.show()
    return widget


def test_entity_browser_shows_all_entities(browser, entity_model):
    """All entities should be visible initially."""
    assert browser.list_view.model().rowCount() == 3


def test_search_filters_entities(browser, qtbot):
    """Typing in the search box should filter the list."""
    qtbot.keyClicks(browser.search_box, "Gon")
    assert browser.list_view.model().rowCount() == 1


def test_click_entity_emits_signal(browser, qtbot, entity_model):
    """Clicking an entity should emit entity_selected."""
    with qtbot.waitSignal(browser.entity_selected, timeout=1000) as blocker:
        index = browser.list_view.model().index(0, 0)
        rect = browser.list_view.visualRect(index)
        qtbot.mouseClick(
            browser.list_view.viewport(),
            Qt.LeftButton,
            pos=rect.center()
        )
    assert blocker.args[0] == "1"  # entity_id
```

### 7.3 Testing Signals

```python
def test_entity_model_emits_data_changed(entity_model, qtbot):
    """Updating an entity should emit dataChanged."""
    with qtbot.waitSignal(entity_model.dataChanged, timeout=1000):
        entity_model.update_entity(0, {"id": "1", "name": "Gondor Updated"})


def test_event_bus_entity_selected(qtbot):
    """EventBus should propagate entity_selected."""
    bus = EventBus.instance()
    with qtbot.waitSignal(bus.entity_selected, timeout=1000) as blocker:
        bus.entity_selected.emit("ent_42")
    assert blocker.args[0] == "ent_42"
```

### 7.4 Testing Core Logic (No Qt Required)

The `core/` layer has no Qt dependencies and can be tested with plain pytest:

```python
from worldbuilder.core.entities import Entity, validate_entity


def test_entity_validation():
    entity = Entity(name="Gondor", entity_type="kingdom")
    assert validate_entity(entity) is True


def test_entity_validation_rejects_empty_name():
    with pytest.raises(ValueError):
        validate_entity(Entity(name="", entity_type="kingdom"))
```

### 7.5 Testing Async Operations

For testing async code with pytest-qt, use `pytest-asyncio` alongside it:

```python
import pytest
import asyncio


@pytest.mark.asyncio
async def test_streaming_response():
    """Test LLM streaming without Qt."""
    tokens = []
    async for token in mock_llm_client.stream("test prompt"):
        tokens.append(token)
    assert len(tokens) > 0
    assert "".join(tokens) == "Hello world"
```

For testing async Qt integration, use `qtbot.waitSignal` with the signals your streaming worker emits:

```python
def test_streaming_worker_emits_tokens(qtbot):
    worker = StreamingWorker("test", mock_client)
    received_tokens = []

    worker.token_received.connect(received_tokens.append)

    with qtbot.waitSignal(worker.stream_finished, timeout=5000):
        worker.start()

    assert len(received_tokens) > 0
```

### 7.6 Headless CI Testing

pytest-qt runs without a display server by default -- widgets are instantiated but not rendered on screen. For CI environments (GitHub Actions, etc.), no special configuration is needed on most platforms. On Linux, install `xvfb` or use `QT_QPA_PLATFORM=offscreen`:

```yaml
# GitHub Actions
- name: Run tests
  env:
    QT_QPA_PLATFORM: offscreen
  run: pytest tests/
```

---

## 8. Recommendation Summary

| Concern | Recommendation |
|---|---|
| **Layout** | `QMainWindow` + `QDockWidget`. Knowledge graph as central widget, other panels as docks. Upgrade to Qt ADS if needed. |
| **Models** | `QAbstractListModel` for entity browser. `QSortFilterProxyModel` for search/filter. Keep models thin. |
| **Signals** | Hybrid: EventBus singleton for cross-panel signals, direct connections within panels. |
| **State** | `ProjectState` class for document data (state.json). `QSettings` via `AppSettings` for UI preferences. `QUndoStack` for undo/redo. |
| **Async/Threading** | `qasync` or `QtAsyncio` for LLM streaming. QThread worker for file I/O. |
| **Project layout** | `src/` layout with `core/`, `models/`, `views/`, `services/`, `widgets/`, `resources/` packages. |
| **Testing** | pytest-qt for widget tests. Plain pytest for core logic. pytest-asyncio for async tests. |

---

## 9. Sources

### Official Documentation
- [PySide6 QMainWindow](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QMainWindow.html)
- [PySide6 QDockWidget](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QDockWidget.html)
- [PySide6 QSplitter](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QSplitter.html)
- [PySide6 QAbstractItemModel](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QAbstractItemModel.html)
- [PySide6 QSortFilterProxyModel](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QSortFilterProxyModel.html)
- [PySide6 QSettings](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QSettings.html)
- [PySide6 QThread](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QThread.html)
- [PySide6.QtAsyncio](https://doc.qt.io/qtforpython-6/PySide6/QtAsyncio/index.html)
- [Qt Signals & Slots Overview](https://doc.qt.io/qtforpython-6/tutorials/basictutorial/signals_and_slots.html)
- [Qt for Python Async Minimal Example](https://doc.qt.io/qtforpython-6/examples/example_async_minimal.html)
- [Qt for Python Thread Signals Example](https://doc.qt.io/qtforpython-6/examples/example_widgets_thread_signals.html)

### Tutorials and Guides
- [PythonGUIs -- PySide6 Tutorial (2026)](https://www.pythonguis.com/pyside6-tutorial/)
- [PythonGUIs -- PySide6 ModelView Architecture](https://www.pythonguis.com/tutorials/pyside6-modelview-architecture/)
- [PythonGUIs -- PySide6 Signals, Slots and Events](https://www.pythonguis.com/tutorials/pyside6-signals-slots-events/)
- [PythonGUIs -- Multithreading PySide6 with QThreadPool](https://www.pythonguis.com/tutorials/multithreading-pyside6-applications-qthreadpool/)
- [PythonGUIs -- QSettings Usage](https://www.pythonguis.com/faq/qsettings-usage/)
- [Real Python -- Use PyQt's QThread to Prevent Freezing GUIs](https://realpython.com/python-pyqt-qthread/)
- [Real Python -- Python Application Layouts](https://realpython.com/python-application-layouts/)
- [How to use QThread correctly](https://www.haccks.com/posts/how-to-use-qthread-correctly-p1/)
- [Filtering a QTableView with QSortFilterProxyModel](https://dmnfarrell.github.io/python/filtering-proxymodel-pyqt)

### Libraries and Tools
- [qasync -- asyncio + Qt integration](https://github.com/CabbageDevelopment/qasync)
- [Qt Advanced Docking System](https://github.com/githubuser0xFFFF/Qt-Advanced-Docking-System)
- [PySide6-QtAds on PyPI](https://pypi.org/project/PySide6-QtAds/)
- [pytest-qt](https://github.com/pytest-dev/pytest-qt)
- [pytest-qt documentation](https://pytest-qt.readthedocs.io/en/latest/intro.html)
- [pyside-settings-manager](https://github.com/danicc097/pyside-settings-manager)
- [asyncslot](https://pypi.org/project/asyncslot/)

### Reference Projects
- [PyFlowGraph -- Visual node-based scripting editor (PySide6)](https://github.com/bhowiebkr/PyFlowGraph)
- [NodeGraphQt-PySide6 -- Node graph framework](https://github.com/C3RV1/NodeGraphQt-PySide6)
- [SpatialNode -- Qt Node Editor for PySide6](https://github.com/SpatialGraphics/SpatialNode)
- [qtPyGraphEdit -- Graph editor in PySide6](https://github.com/ghillebrand/qtPyGraphEdit)
- [PySide6 Project Template](https://github.com/trin94/PySide6-project-template)
- [Modern GUI PyDracula (PySide6)](https://github.com/Wanderson-Magalhaes/Modern_GUI_PyDracula_PySide6_or_PyQt6)
- [PythonGUIs examples](https://github.com/pythonguis/pythonguis-examples)
