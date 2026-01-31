# PySide6 UI/UX Patterns Research for Worldbuilding Tool

> **Purpose:** Research report covering modern UI/UX patterns, libraries, and implementation strategies for building a polished, inviting PySide6 desktop application aimed at non-technical creative users.
>
> **Date:** 2026-01-30

---

## Table of Contents

1. [Dark Theme Implementation](#1-dark-theme-implementation)
2. [Card-Based Layouts](#2-card-based-layouts)
3. [Streaming Chat Panel](#3-streaming-chat-panel)
4. [Entity Browser with Search](#4-entity-browser-with-search)
5. [Comparison / Option Selection UI](#5-comparison--option-selection-ui)
6. [Progress / Navigation](#6-progress--navigation)
7. [Icons and Visual Assets](#7-icons-and-visual-assets)
8. [Responsive Layouts](#8-responsive-layouts)
9. [Animations and Polish](#9-animations-and-polish)

---

## 1. Dark Theme Implementation

A dark theme is essential for a creative tool -- it reduces eye strain during long sessions, makes colorful content pop, and immediately signals "modern application" to users. Below is a comparison of the five major approaches.

### 1.1 PyQtDarkTheme (qdarktheme)

**Repository:** https://github.com/5yutan5/PyQtDarkTheme
**License:** MIT
**Install:** `pip install pyqtdarktheme`

**Setup:**
```python
import qdarktheme
from PySide6.QtWidgets import QApplication

app = QApplication([])
qdarktheme.setup_theme("dark")
# Or with a custom accent color:
qdarktheme.setup_theme("dark", custom_colors={"primary": "#D0BCFF"})
```

| Criterion | Rating | Notes |
|-----------|--------|-------|
| **Ease of use** | Excellent | One-liner setup. Simplest of all options. |
| **Customizability** | Moderate | Accent color, corner shape (rounded/sharp). Limited beyond that. |
| **Maintenance** | Warning | Original repo by 5yutan5 is **stale/unmaintained** since mid-2023. Community forks exist (e.g., `bauripalash/PyQtDarkTheme-fork`, `kevinjohncutler/omnipose-theme`). |
| **Visual quality** | Good | Flat Material-inspired look. Clean and modern. SVG icons derived from Material Design. |

**Verdict:** Best for rapid prototyping. The maintenance risk is real -- if a PySide6 update breaks something, fixes depend on community forks. Consider vendoring the generated QSS if adopting this.

---

### 1.2 Qt-Material

**Repository:** https://github.com/UN-GCPDS/qt-material
**PyPI:** https://pypi.org/project/qt-material/
**License:** BSD
**Install:** `pip install qt-material`

**Setup:**
```python
from PySide6.QtWidgets import QApplication, QMainWindow
from qt_material import apply_stylesheet, list_themes

app = QApplication([])
window = QMainWindow()

# List available themes
print(list_themes())
# ['dark_amber.xml', 'dark_blue.xml', 'dark_cyan.xml', 'dark_lightgreen.xml',
#  'dark_pink.xml', 'dark_purple.xml', 'dark_red.xml', 'dark_teal.xml',
#  'dark_yellow.xml', 'light_amber.xml', ...]

apply_stylesheet(app, theme='dark_teal.xml')

# Runtime theme switching via QtStyleTools mixin:
from qt_material import QtStyleTools

class MyWindow(QMainWindow, QtStyleTools):
    def __init__(self):
        super().__init__()
        # self.apply_stylesheet() available at runtime

# Custom overrides:
apply_stylesheet(app, theme='dark_teal.xml', extra={
    'density_scale': '-1',      # Compact mode
    'font_family': 'Inter',
    'font_size': '14px',
})
```

| Criterion | Rating | Notes |
|-----------|--------|-------|
| **Ease of use** | Very good | One function call. Multiple built-in themes to choose from. |
| **Customizability** | Excellent | Full Material Design parameter control: colors, fonts, density, button styles. Can export to standalone QSS/RCC. XML-based theme definitions are easy to modify. |
| **Maintenance** | Active | Actively maintained by UN-GCPDS group. Regular updates. |
| **Visual quality** | Very good | Faithful Material Design aesthetic. Cohesive look across all widgets. |

**Verdict:** The strongest all-around choice. Active maintenance, extensive theming, and a familiar Material Design language that creative users will recognize from web/mobile apps. **Recommended as primary theme library.**

---

### 1.3 QtModernRedux

**PyPI:** https://pypi.org/project/QtModernRedux6/
**License:** MIT
**Install:** `pip install QtModernRedux6`

**Setup:**
```python
import qtmodernredux
from PySide6.QtWidgets import QApplication, QMainWindow

app = QApplication([])
window = QMainWindow()
window.setWindowTitle("My App")

# Wrap the window in the modern frame
modern_window = qtmodernredux.wrap(window, theme="dark")
modern_window.show()
```

| Criterion | Rating | Notes |
|-----------|--------|-------|
| **Ease of use** | Good | Simple `wrap()` call, but it replaces the native title bar which can cause edge cases. |
| **Customizability** | Moderate | Custom title bar with widgets in the title bar area. Theme colors configurable. |
| **Maintenance** | Moderate | Updated for PySide6/Qt6. Smaller community than qt-material. |
| **Visual quality** | Very good | Consistent look across Mac, Windows, Ubuntu. High-DPI/Retina support. The no-title-bar mode looks genuinely modern. |

**Verdict:** Interesting for its custom title bar ("frameless window") approach. The wrapped window looks distinctly modern, but the title bar replacement introduces platform-specific complexity (window dragging, snapping, minimize/maximize behavior). Best used if you specifically want the frameless look.

---

### 1.4 BreezeStyleSheets

**Repository:** https://github.com/Alexhuszagh/BreezeStyleSheets
**License:** MIT
**Install:** Clone and build, or use pre-built dist files.

**Setup:**
```python
# After building with: python configure.py --styles=dark --resource breeze_pyside6.py
# Or using pre-built resources:

from PySide6.QtWidgets import QApplication
import breeze_pyside6  # compiled resource module

app = QApplication([])

# Apply dark theme
file = QFile(":/dark/stylesheet.qss")
file.open(QFile.ReadOnly | QFile.Text)
stream = QTextStream(file)
app.setStyleSheet(stream.readAll())
```

| Criterion | Rating | Notes |
|-----------|--------|-------|
| **Ease of use** | Moderate | Requires a build step (`configure.py`) to compile resources for PySide6. Not as simple as pip install + one-liner. |
| **Customizability** | Excellent | Extension system for adding custom rules. Theme files are fully editable. Supports custom icon packs. Integrates with Qt Advanced Docking System. |
| **Maintenance** | Good | Actively maintained fork of QDarkStyleSheet. Comprehensive widget coverage including esoteric widgets like QCalendarWidget. |
| **Visual quality** | Very good | KDE Breeze aesthetic -- clean, professional, slightly more "desktop-native" feeling than Material. Beautiful on Linux, good everywhere. |

**Verdict:** Best choice if you want a desktop-native aesthetic rather than web/mobile Material Design. The build step is a minor inconvenience. Excellent widget coverage means fewer visual glitches with unusual widgets.

---

### 1.5 Custom QSS (Qt Style Sheets)

**Approach:** Write your own `.qss` file from scratch or adapt a base.

**Setup:**
```python
from PySide6.QtWidgets import QApplication

app = QApplication([])

# Load from file
with open("style.qss", "r") as f:
    app.setStyleSheet(f.read())

# Or inline
app.setStyleSheet("""
    QMainWindow {
        background-color: #1e1e2e;
    }
    QWidget {
        color: #cdd6f4;
        font-family: 'Segoe UI', 'Inter', sans-serif;
        font-size: 14px;
    }
    QPushButton {
        background-color: #45475a;
        border: 1px solid #585b70;
        border-radius: 6px;
        padding: 8px 16px;
        color: #cdd6f4;
    }
    QPushButton:hover {
        background-color: #585b70;
        border-color: #7f849c;
    }
    QPushButton:pressed {
        background-color: #313244;
    }
    QPushButton:disabled {
        background-color: #313244;
        color: #585b70;
    }
    QLineEdit, QTextEdit, QPlainTextEdit {
        background-color: #313244;
        border: 1px solid #45475a;
        border-radius: 6px;
        padding: 6px;
        selection-background-color: #89b4fa;
        selection-color: #1e1e2e;
    }
    QLineEdit:focus, QTextEdit:focus {
        border-color: #89b4fa;
    }
    QScrollBar:vertical {
        background: #1e1e2e;
        width: 10px;
        border-radius: 5px;
    }
    QScrollBar::handle:vertical {
        background: #45475a;
        border-radius: 5px;
        min-height: 30px;
    }
    QScrollBar::handle:vertical:hover {
        background: #585b70;
    }
""")
```

| Criterion | Rating | Notes |
|-----------|--------|-------|
| **Ease of use** | Low | Must style every widget type manually. Easy to miss edge cases. |
| **Customizability** | Maximum | Total control over every pixel. |
| **Maintenance** | Self-maintained | You own it entirely. No dependency risk, but also no community fixes. |
| **Visual quality** | Varies | As good as your design skills. Can achieve exactly what you want. |

**Verdict:** Best used as a supplement to a base theme library. Start with qt-material or BreezeStyleSheets, then layer custom QSS overrides for your specific card components, chat bubbles, and other custom widgets.

---

### Theme Recommendation

**Primary:** `qt-material` with `dark_teal.xml` or `dark_purple.xml` as the base (teal and purple both work well for creative/fantasy applications).

**Supplemental:** Custom QSS overrides for application-specific components (cards, chat bubbles, stepper widget).

**Fallback:** If qt-material introduces issues with specific widgets, BreezeStyleSheets is the most comprehensive alternative.

---

## 2. Card-Based Layouts

Cards are the fundamental UI pattern for this application -- entity summaries, option comparisons, and step overviews all use card-style presentation. Cards communicate "this is a discrete, self-contained piece of content" in a way that feels natural to users familiar with web and mobile apps.

### 2.1 Basic Card Widget

```python
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QLabel, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor


class Card(QFrame):
    """A styled card widget with rounded corners and drop shadow."""

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            QFrame#card {
                background-color: #2d2d3f;
                border: 1px solid #3d3d5c;
                border-radius: 12px;
                padding: 16px;
            }
            QFrame#card:hover {
                border-color: #6c6c9a;
                background-color: #33334a;
            }
        """)

        # Drop shadow for depth
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 60))
        self.setGraphicsEffect(shadow)

        # Layout
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 16, 16, 16)
        self._layout.setSpacing(8)

        if title:
            title_label = QLabel(title)
            title_label.setStyleSheet("""
                font-size: 16px;
                font-weight: bold;
                color: #e0e0ff;
                padding-bottom: 4px;
            """)
            self._layout.addWidget(title_label)

    def add_widget(self, widget):
        self._layout.addWidget(widget)

    def add_text(self, text: str):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet("color: #b0b0d0; font-size: 13px;")
        self._layout.addWidget(label)
```

### 2.2 Important Note on QGraphicsDropShadowEffect

Each `QGraphicsDropShadowEffect` instance can only be applied to **one widget**. You must create a new effect instance for every card. A helper factory is recommended:

```python
def make_shadow(parent=None, blur=20, offset_y=4, opacity=60):
    shadow = QGraphicsDropShadowEffect(parent)
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, offset_y)
    shadow.setColor(QColor(0, 0, 0, opacity))
    return shadow
```

### 2.3 Grid of Cards (Side-by-Side Comparison)

```python
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QScrollArea


class CardGrid(QWidget):
    """Horizontal row of cards for side-by-side comparison."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setSpacing(16)
        self._layout.setContentsMargins(16, 16, 16, 16)

    def add_card(self, card: Card):
        self._layout.addWidget(card)


class ScrollableCardList(QWidget):
    """Vertical scrollable list of cards."""

    def __init__(self, parent=None):
        super().__init__(parent)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
        """)

        container = QWidget()
        self._card_layout = QVBoxLayout(container)
        self._card_layout.setSpacing(12)
        self._card_layout.setContentsMargins(8, 8, 8, 8)
        self._card_layout.addStretch()  # Push cards to top

        scroll.setWidget(container)
        outer_layout.addWidget(scroll)

    def add_card(self, card: Card):
        # Insert before the stretch
        count = self._card_layout.count()
        self._card_layout.insertWidget(count - 1, card)
```

### 2.4 Entity Summary Card

```python
class EntityCard(Card):
    """Card showing an entity summary with type indicator and status."""

    def __init__(self, name: str, entity_type: str, description: str,
                 status: str = "draft", parent=None):
        super().__init__(parent=parent)

        # Type color coding
        type_colors = {
            "god": "#f4a261",
            "species": "#2a9d8f",
            "settlement": "#e76f51",
            "culture": "#264653",
            "artifact": "#e9c46a",
        }
        color = type_colors.get(entity_type.lower(), "#888888")

        # Header with colored type indicator
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        type_badge = QLabel(entity_type.upper())
        type_badge.setStyleSheet(f"""
            background-color: {color};
            color: #1e1e2e;
            border-radius: 4px;
            padding: 2px 8px;
            font-size: 10px;
            font-weight: bold;
        """)
        type_badge.setFixedHeight(20)

        name_label = QLabel(name)
        name_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #e0e0ff;")

        status_label = QLabel(f"  {status}")
        status_color = "#4ade80" if status == "canon" else "#fbbf24"
        status_label.setStyleSheet(f"color: {status_color}; font-size: 11px;")

        header_layout.addWidget(type_badge)
        header_layout.addWidget(name_label)
        header_layout.addStretch()
        header_layout.addWidget(status_label)

        self.add_widget(header)

        desc_label = QLabel(description)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #b0b0d0; font-size: 13px; padding-top: 4px;")
        self.add_widget(desc_label)
```

### 2.5 Visual Design Principles for Cards

- **Border radius:** 8-12px for a modern feel. Avoid sharp corners (feels dated) or excessive rounding (feels toy-like).
- **Shadow:** Subtle. `blurRadius: 15-25`, `offset: (0, 2-4)`, `color: rgba(0,0,0,40-60)`. Heavy shadows look like 2012 skeuomorphism.
- **Padding:** 16px internal padding minimum. Cards need breathing room.
- **Spacing:** 12-16px between cards in a grid.
- **Hover effect:** Lighten the background by ~5% and brighten the border. Subtle enough to notice, not dramatic enough to distract.
- **Max width:** Cards in a comparison row should have equal widths. Use `QHBoxLayout` with equal stretch factors, or set `setMinimumWidth()` / `setMaximumWidth()`.

---

## 3. Streaming Chat Panel

The chat panel is the primary interaction surface. It needs to handle streaming tokens from Claude, render markdown, and feel responsive even during long responses.

### 3.1 Architecture Overview

```
ChatPanel (QWidget)
  +-- QScrollArea
  |     +-- message_container (QWidget with QVBoxLayout)
  |           +-- MessageBubble (user)
  |           +-- MessageBubble (assistant, streaming)
  |           +-- MessageBubble (user)
  |           +-- ...
  +-- InputArea (QWidget)
        +-- QTextEdit (multi-line input)
        +-- QPushButton (send)
```

### 3.2 Message Bubble Widget

```python
from PySide6.QtWidgets import QTextBrowser, QVBoxLayout, QWidget, QLabel, QHBoxLayout
from PySide6.QtCore import Qt, QTimer


class MessageBubble(QWidget):
    """A single chat message with role indicator and content."""

    def __init__(self, role: str = "user", parent=None):
        super().__init__(parent)
        self.role = role
        self._accumulated_text = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        # Role label
        role_label = QLabel("You" if role == "user" else "Claude")
        role_color = "#89b4fa" if role == "user" else "#a6e3a1"
        role_label.setStyleSheet(f"""
            color: {role_color};
            font-weight: bold;
            font-size: 12px;
            padding-bottom: 2px;
        """)
        layout.addWidget(role_label)

        # Content area using QTextBrowser for markdown/HTML rendering
        self.content = QTextBrowser()
        self.content.setOpenExternalLinks(True)
        self.content.setStyleSheet("""
            QTextBrowser {
                background-color: transparent;
                border: none;
                color: #cdd6f4;
                font-size: 14px;
                selection-background-color: #585b70;
            }
        """)
        # Disable scrollbar on individual messages -- the parent scrolls
        self.content.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        layout.addWidget(self.content)

        # Style the bubble background based on role
        bg_color = "#313244" if role == "user" else "#2a2a3e"
        self.setStyleSheet(f"""
            MessageBubble {{
                background-color: {bg_color};
                border-radius: 10px;
                margin: 4px {'48px 4px 12px' if role == 'user' else '12px 4px 48px'};
            }}
        """)

    def set_markdown(self, text: str):
        """Set the full message content as markdown."""
        self._accumulated_text = text
        self.content.document().setMarkdown(text)
        self._adjust_height()

    def append_token(self, token: str):
        """Append a streaming token and re-render markdown."""
        self._accumulated_text += token
        self.content.document().setMarkdown(self._accumulated_text)
        self._adjust_height()

    def _adjust_height(self):
        """Resize the text browser to fit content (no internal scrollbar)."""
        doc_height = self.content.document().size().height()
        self.content.setFixedHeight(int(doc_height) + 10)
```

### 3.3 Chat Panel with Auto-Scroll

```python
class ChatPanel(QWidget):
    """Full chat panel with message list and input area."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Scrollable message area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; }")

        self.message_container = QWidget()
        self.message_layout = QVBoxLayout(self.message_container)
        self.message_layout.setAlignment(Qt.AlignTop)
        self.message_layout.setSpacing(4)
        self.message_layout.addStretch()

        self.scroll_area.setWidget(self.message_container)
        layout.addWidget(self.scroll_area, stretch=1)

        # Input area
        input_area = QWidget()
        input_layout = QHBoxLayout(input_area)
        input_layout.setContentsMargins(12, 8, 12, 8)

        self.input_field = QTextEdit()
        self.input_field.setPlaceholderText("Type your message...")
        self.input_field.setMaximumHeight(80)
        self.input_field.setStyleSheet("""
            QTextEdit {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 8px;
                padding: 8px;
                color: #cdd6f4;
                font-size: 14px;
            }
            QTextEdit:focus { border-color: #89b4fa; }
        """)
        input_layout.addWidget(self.input_field)

        self.send_btn = QPushButton("Send")
        self.send_btn.setFixedWidth(70)
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #89b4fa;
                color: #1e1e2e;
                border-radius: 8px;
                font-weight: bold;
                padding: 8px;
            }
            QPushButton:hover { background-color: #74a8fc; }
            QPushButton:pressed { background-color: #5b9bfc; }
        """)
        input_layout.addWidget(self.send_btn)

        layout.addWidget(input_area)

        self._current_assistant_bubble = None

    def add_user_message(self, text: str):
        bubble = MessageBubble(role="user")
        bubble.set_markdown(text)
        self._insert_bubble(bubble)

    def start_assistant_message(self):
        """Begin a new assistant message for streaming."""
        bubble = MessageBubble(role="assistant")
        self._current_assistant_bubble = bubble
        self._insert_bubble(bubble)
        return bubble

    def stream_token(self, token: str):
        """Append a token to the current assistant message."""
        if self._current_assistant_bubble:
            self._current_assistant_bubble.append_token(token)
            self._scroll_to_bottom()

    def _insert_bubble(self, bubble):
        count = self.message_layout.count()
        self.message_layout.insertWidget(count - 1, bubble)  # Before stretch
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        """Auto-scroll to the latest message."""
        QTimer.singleShot(10, lambda: self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        ))
```

### 3.4 Markdown Rendering Options

| Approach | Pros | Cons |
|----------|------|------|
| **QTextDocument.setMarkdown()** (built-in) | No dependencies. Fast. Supports GitHub Flavored Markdown basics (bold, italic, headers, lists, code blocks, links). | Limited: no syntax highlighting in code blocks. Some advanced markdown may not render. |
| **QTextBrowser.setHtml()** with `markdown` library | Full control over HTML. Can use `python-markdown` with extensions (code highlighting via `codehilite`, tables, etc.). | Extra dependency. Must convert markdown->HTML yourself on each token. |
| **QMarkdownView** (QWebEngineView-based) | Full markdown rendering including LaTeX, syntax highlighting. | Heavy dependency (QtWebEngine). Overkill for chat. Harder to style consistently. |

**Recommendation:** Use `QTextDocument.setMarkdown()` for the main chat. It handles the markdown that Claude typically produces (headers, bold, italic, lists, code blocks) and requires zero dependencies. If code syntax highlighting becomes important later, add `python-markdown` with `codehilite` and switch to `setHtml()`.

### 3.5 Streaming Performance Considerations

- **Do not call `setMarkdown()` on every single token.** Batch tokens and update every 50-100ms using a `QTimer`:

```python
class StreamBuffer:
    """Batches streaming tokens to avoid excessive re-renders."""

    def __init__(self, bubble: MessageBubble, interval_ms: int = 50):
        self._bubble = bubble
        self._buffer = ""
        self._timer = QTimer()
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._flush)

    def add_token(self, token: str):
        self._buffer += token
        if not self._timer.isActive():
            self._timer.start()

    def _flush(self):
        if self._buffer:
            self._bubble.append_token(self._buffer)
            self._buffer = ""
        else:
            self._timer.stop()

    def finish(self):
        self._timer.stop()
        self._flush()
```

---

## 4. Entity Browser with Search

The entity browser is the primary navigation tool for the world the user is building. It must support real-time search filtering, category grouping, status indicators, and rich item display.

### 4.1 Architecture

```
EntityBrowser (QWidget)
  +-- QLineEdit (search bar with icon)
  +-- QTreeView
        +-- EntitySortFilterProxy (QSortFilterProxyModel)
              +-- EntityModel (QStandardItemModel or custom QAbstractItemModel)
        +-- EntityDelegate (QStyledItemDelegate)
```

### 4.2 Data Model

```python
from PySide6.QtGui import QStandardItemModel, QStandardItem, QColor, QFont
from PySide6.QtCore import Qt


class EntityModel(QStandardItemModel):
    """Hierarchical model: Category -> Entities."""

    # Custom roles for entity data
    EntityTypeRole = Qt.UserRole + 1
    StatusRole = Qt.UserRole + 2
    DescriptionRole = Qt.UserRole + 3
    EntityIdRole = Qt.UserRole + 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHorizontalHeaderLabels(["World Entities"])
        self._categories = {}

    def add_entity(self, entity_type: str, name: str, description: str,
                   status: str = "draft", entity_id: str = ""):
        # Get or create category
        if entity_type not in self._categories:
            cat_item = QStandardItem(entity_type.title())
            cat_item.setFlags(Qt.ItemIsEnabled)  # Not selectable
            cat_item.setFont(QFont("", -1, QFont.Bold))
            self.appendRow(cat_item)
            self._categories[entity_type] = cat_item

        # Create entity item
        item = QStandardItem(name)
        item.setData(entity_type, self.EntityTypeRole)
        item.setData(status, self.StatusRole)
        item.setData(description, self.DescriptionRole)
        item.setData(entity_id, self.EntityIdRole)

        self._categories[entity_type].appendRow(item)
```

### 4.3 Filter Proxy for Hierarchical Search

```python
from PySide6.QtCore import QSortFilterProxyModel, QModelIndex


class EntityFilterProxy(QSortFilterProxyModel):
    """Proxy that shows matching entities AND their parent categories.

    Key behavior: if a child matches the filter, show its parent category.
    If a category name matches, show all its children.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRecursiveFilteringEnabled(True)  # Qt 5.10+: show parents of matches
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        index = self.sourceModel().index(source_row, 0, source_parent)
        text = self.sourceModel().data(index, Qt.DisplayRole) or ""
        description = self.sourceModel().data(
            index, EntityModel.DescriptionRole
        ) or ""
        entity_type = self.sourceModel().data(
            index, EntityModel.EntityTypeRole
        ) or ""

        pattern = self.filterRegularExpression().pattern()
        if not pattern:
            return True

        # Match against name, description, and type
        import re
        regex = re.compile(pattern, re.IGNORECASE)
        return bool(
            regex.search(text)
            or regex.search(description)
            or regex.search(entity_type)
        )
```

### 4.4 Custom Delegate for Rich List Items

```python
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle
from PySide6.QtGui import (
    QTextDocument, QAbstractTextDocumentLayout, QPainter, QColor
)
from PySide6.QtCore import QSize, QRectF


class EntityDelegate(QStyledItemDelegate):
    """Rich delegate showing entity name, type badge, status, and description."""

    TYPE_COLORS = {
        "god": "#f4a261",
        "species": "#2a9d8f",
        "settlement": "#e76f51",
        "culture": "#264653",
        "artifact": "#e9c46a",
        "region": "#7209b7",
        "event": "#f72585",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._doc = QTextDocument()

    def paint(self, painter: QPainter, option: QStyleOptionViewItem,
              index: QModelIndex):
        # For category headers, use default painting
        entity_type = index.data(EntityModel.EntityTypeRole)
        if not entity_type:
            super().paint(painter, option, index)
            return

        options = QStyleOptionViewItem(option)
        self.initStyleOption(options, index)
        painter.save()

        name = index.data(Qt.DisplayRole)
        status = index.data(EntityModel.StatusRole) or "draft"
        description = index.data(EntityModel.DescriptionRole) or ""
        color = self.TYPE_COLORS.get(entity_type, "#888888")
        status_color = "#4ade80" if status == "canon" else "#fbbf24"

        # Build rich HTML for the item
        html = f"""
        <div style="padding: 4px;">
            <span style="font-weight: bold; font-size: 13px; color: #e0e0ff;">
                {name}
            </span>
            <span style="background-color: {color}; color: #1e1e2e;
                         border-radius: 3px; padding: 1px 6px;
                         font-size: 10px; font-weight: bold;">
                {entity_type.upper()}
            </span>
            <span style="color: {status_color}; font-size: 10px;">
                {status}
            </span>
            <br/>
            <span style="color: #8888aa; font-size: 11px;">
                {description[:80]}{'...' if len(description) > 80 else ''}
            </span>
        </div>
        """

        self._doc.setHtml(html)
        self._doc.setTextWidth(options.rect.width())

        # Draw background/selection
        options.text = ""
        options.widget.style().drawControl(
            QStyle.ControlElement.CE_ItemViewItem, options, painter
        )

        # Draw rich text
        painter.translate(options.rect.left(), options.rect.top())
        clip = QRectF(0, 0, options.rect.width(), options.rect.height())
        painter.setClipRect(clip)
        ctx = QAbstractTextDocumentLayout.PaintContext()
        ctx.clip = clip
        self._doc.documentLayout().draw(painter, ctx)

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        entity_type = index.data(EntityModel.EntityTypeRole)
        if not entity_type:
            return super().sizeHint(option, index)

        options = QStyleOptionViewItem(option)
        self.initStyleOption(options, index)
        self._doc.setHtml(f"<div style='padding:4px;'><b>Name</b><br/><span>Description text</span></div>")
        self._doc.setTextWidth(options.rect.width() if options.rect.width() > 0 else 250)
        return QSize(int(self._doc.idealWidth()), int(self._doc.size().height()) + 8)
```

### 4.5 Wiring It Together

```python
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLineEdit, QTreeView


class EntityBrowser(QWidget):
    """Complete entity browser with search and categorized tree."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Search bar
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search entities...")
        self.search_bar.setClearButtonEnabled(True)
        self.search_bar.setStyleSheet("""
            QLineEdit {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 14px;
                color: #cdd6f4;
            }
            QLineEdit:focus { border-color: #89b4fa; }
        """)
        layout.addWidget(self.search_bar)

        # Tree view
        self.tree = QTreeView()
        self.tree.setHeaderHidden(True)
        self.tree.setAnimated(True)
        self.tree.setIndentation(20)
        self.tree.setStyleSheet("""
            QTreeView {
                background-color: #1e1e2e;
                border: none;
                outline: none;
            }
            QTreeView::item {
                padding: 4px;
                border-radius: 6px;
            }
            QTreeView::item:hover {
                background-color: #313244;
            }
            QTreeView::item:selected {
                background-color: #45475a;
            }
        """)

        # Model and proxy
        self.model = EntityModel()
        self.proxy = EntityFilterProxy()
        self.proxy.setSourceModel(self.model)
        self.tree.setModel(self.proxy)

        # Delegate
        self.delegate = EntityDelegate()
        self.tree.setItemDelegate(self.delegate)

        layout.addWidget(self.tree)

        # Connect search to filter
        self.search_bar.textChanged.connect(self._on_search)

    def _on_search(self, text: str):
        self.proxy.setFilterRegularExpression(text)
        if text:
            self.tree.expandAll()
```

---

## 5. Comparison / Option Selection UI

When Claude generates 2-4 worldbuilding options, they need to be presented side-by-side for easy comparison and selection. This is one of the most important interaction patterns in the application.

### 5.1 Option Card

```python
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGraphicsDropShadowEffect, QSizePolicy
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor


class OptionCard(QFrame):
    """A selectable card displaying one worldbuilding option."""

    selected = Signal(int)  # Emits option index when selected

    def __init__(self, index: int, title: str, content: str, parent=None):
        super().__init__(parent)
        self.index = index
        self._is_selected = False
        self.setObjectName(f"optionCard_{index}")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self._update_style()

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(0, 0, 0, 50))
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # Option number
        number_label = QLabel(f"Option {index + 1}")
        number_label.setStyleSheet("""
            color: #89b4fa; font-size: 11px; font-weight: bold;
            text-transform: uppercase; letter-spacing: 1px;
        """)
        layout.addWidget(number_label)

        # Title
        title_label = QLabel(title)
        title_label.setWordWrap(True)
        title_label.setStyleSheet(
            "color: #e0e0ff; font-size: 15px; font-weight: bold;"
        )
        layout.addWidget(title_label)

        # Content (rendered as rich text)
        content_label = QLabel(content)
        content_label.setWordWrap(True)
        content_label.setStyleSheet("color: #b0b0d0; font-size: 13px;")
        layout.addWidget(content_label, stretch=1)

        # Select button
        self.select_btn = QPushButton("Pick This One")
        self.select_btn.setStyleSheet("""
            QPushButton {
                background-color: #45475a;
                color: #cdd6f4;
                border: 1px solid #585b70;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #585b70;
            }
        """)
        self.select_btn.clicked.connect(lambda: self.selected.emit(self.index))
        layout.addWidget(self.select_btn)

    def set_selected(self, selected: bool):
        self._is_selected = selected
        self._update_style()
        if selected:
            self.select_btn.setText("Selected")
            self.select_btn.setStyleSheet("""
                QPushButton {
                    background-color: #89b4fa;
                    color: #1e1e2e;
                    border: none;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-weight: bold;
                }
            """)
        else:
            self.select_btn.setText("Pick This One")
            self.select_btn.setStyleSheet("""
                QPushButton {
                    background-color: #45475a;
                    color: #cdd6f4;
                    border: 1px solid #585b70;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #585b70; }
            """)

    def _update_style(self):
        if self._is_selected:
            self.setStyleSheet(f"""
                QFrame#{self.objectName()} {{
                    background-color: #2a2a4a;
                    border: 2px solid #89b4fa;
                    border-radius: 12px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QFrame#{self.objectName()} {{
                    background-color: #2d2d3f;
                    border: 1px solid #3d3d5c;
                    border-radius: 12px;
                }}
                QFrame#{self.objectName()}:hover {{
                    border-color: #6c6c9a;
                    background-color: #33334a;
                }}
            """)

    def mousePressEvent(self, event):
        self.selected.emit(self.index)
        super().mousePressEvent(event)
```

### 5.2 Option Comparison Panel

```python
class OptionComparisonPanel(QWidget):
    """Panel showing 2-4 options side-by-side with action buttons."""

    option_selected = Signal(int)
    combine_requested = Signal()
    regenerate_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards = []
        self._selected_index = -1

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(16)

        # Instruction label
        instruction = QLabel("Choose the option that best fits your vision:")
        instruction.setStyleSheet(
            "color: #a0a0c0; font-size: 14px; padding-bottom: 8px;"
        )
        main_layout.addWidget(instruction)

        # Card row
        self.card_row = QHBoxLayout()
        self.card_row.setSpacing(16)
        main_layout.addLayout(self.card_row, stretch=1)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.addStretch()

        self.combine_btn = QPushButton("Combine Elements")
        self.combine_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #89b4fa;
                border: 1px solid #89b4fa;
                border-radius: 6px;
                padding: 10px 20px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #89b4fa22; }
        """)
        self.combine_btn.clicked.connect(self.combine_requested.emit)
        btn_row.addWidget(self.combine_btn)

        self.regenerate_btn = QPushButton("Generate New Options")
        self.regenerate_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #f9e2af;
                border: 1px solid #f9e2af;
                border-radius: 6px;
                padding: 10px 20px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #f9e2af22; }
        """)
        self.regenerate_btn.clicked.connect(self.regenerate_requested.emit)
        btn_row.addWidget(self.regenerate_btn)

        btn_row.addStretch()
        main_layout.addLayout(btn_row)

    def set_options(self, options: list[dict]):
        """Set options. Each dict has 'title' and 'content' keys."""
        # Clear existing cards
        for card in self._cards:
            card.deleteLater()
        self._cards.clear()
        self._selected_index = -1

        for i, opt in enumerate(options):
            card = OptionCard(i, opt["title"], opt["content"])
            card.selected.connect(self._on_card_selected)
            self.card_row.addWidget(card)
            self._cards.append(card)

    def _on_card_selected(self, index: int):
        self._selected_index = index
        for card in self._cards:
            card.set_selected(card.index == index)
        self.option_selected.emit(index)
```

---

## 6. Progress / Navigation

The worldbuilding tool has a 52-step progression through 12 phases. Users need to see where they are, where they have been, and what is coming. This is a custom widget since Qt does not provide a built-in stepper.

### 6.1 Phase/Step Data Structure

```python
from dataclasses import dataclass


@dataclass
class Step:
    id: str
    name: str
    phase: str
    status: str = "upcoming"  # "completed", "current", "upcoming"


PHASES = [
    {"name": "Foundation", "icon": "mdi6.earth", "steps": [
        "cosmology", "fundamental_forces", "world_geography", "time_system"
    ]},
    {"name": "Peoples", "icon": "mdi6.account-group", "steps": [
        "species_origins", "species_culture", "species_relations"
    ]},
    # ... etc
]
```

### 6.2 Custom Stepper/Progress Sidebar Widget

```python
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QFrame
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QPainter, QColor, QPen, QFont


class StepItem(QWidget):
    """Individual step in the progress sidebar."""

    clicked = Signal(str)  # Emits step_id

    STATUS_COLORS = {
        "completed": "#4ade80",
        "current": "#89b4fa",
        "upcoming": "#45475a",
    }

    def __init__(self, step_id: str, name: str, status: str = "upcoming",
                 parent=None):
        super().__init__(parent)
        self.step_id = step_id
        self.status = status
        self.setFixedHeight(36)
        self.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 4, 12, 4)
        layout.setSpacing(8)

        # Status dot
        self.dot = QLabel()
        self.dot.setFixedSize(10, 10)
        self._update_dot()
        layout.addWidget(self.dot)

        # Step name
        self.name_label = QLabel(name)
        self._update_label()
        layout.addWidget(self.name_label)
        layout.addStretch()

    def set_status(self, status: str):
        self.status = status
        self._update_dot()
        self._update_label()

    def _update_dot(self):
        color = self.STATUS_COLORS[self.status]
        if self.status == "current":
            # Larger, glowing dot for current step
            self.dot.setFixedSize(12, 12)
            self.dot.setStyleSheet(f"""
                background-color: {color};
                border-radius: 6px;
                border: 2px solid {color};
            """)
        elif self.status == "completed":
            self.dot.setFixedSize(10, 10)
            self.dot.setStyleSheet(f"""
                background-color: {color};
                border-radius: 5px;
            """)
        else:
            self.dot.setFixedSize(10, 10)
            self.dot.setStyleSheet(f"""
                background-color: transparent;
                border: 2px solid {color};
                border-radius: 5px;
            """)

    def _update_label(self):
        if self.status == "current":
            self.name_label.setStyleSheet(
                "color: #89b4fa; font-weight: bold; font-size: 13px;"
            )
        elif self.status == "completed":
            self.name_label.setStyleSheet(
                "color: #a0a0c0; font-size: 13px;"
            )
        else:
            self.name_label.setStyleSheet(
                "color: #585b70; font-size: 13px;"
            )

    def mousePressEvent(self, event):
        self.clicked.emit(self.step_id)
        super().mousePressEvent(event)


class PhaseGroup(QWidget):
    """A collapsible phase header with its child steps."""

    step_clicked = Signal(str)

    def __init__(self, phase_name: str, phase_number: int, parent=None):
        super().__init__(parent)
        self.phase_name = phase_name
        self._steps = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Phase header
        self.header = QLabel(f"  Phase {phase_number}: {phase_name}")
        self.header.setFixedHeight(32)
        self.header.setStyleSheet("""
            color: #cdd6f4;
            font-weight: bold;
            font-size: 12px;
            padding: 4px 8px;
            background-color: #25253a;
            border-radius: 4px;
        """)
        layout.addWidget(self.header)

        self.steps_container = QWidget()
        self.steps_layout = QVBoxLayout(self.steps_container)
        self.steps_layout.setContentsMargins(0, 0, 0, 0)
        self.steps_layout.setSpacing(0)
        layout.addWidget(self.steps_container)

    def add_step(self, step: StepItem):
        step.clicked.connect(self.step_clicked.emit)
        self.steps_layout.addWidget(step)
        self._steps.append(step)

    @property
    def completion_ratio(self) -> float:
        if not self._steps:
            return 0.0
        completed = sum(1 for s in self._steps if s.status == "completed")
        return completed / len(self._steps)


class ProgressSidebar(QWidget):
    """Full sidebar showing all phases and steps."""

    step_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(260)
        self.setStyleSheet("""
            ProgressSidebar {
                background-color: #1a1a2e;
                border-right: 1px solid #2d2d3f;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 16, 8, 16)
        layout.setSpacing(4)

        # Title
        title = QLabel("World Building Progress")
        title.setStyleSheet("""
            color: #e0e0ff; font-size: 14px; font-weight: bold;
            padding: 8px; padding-bottom: 16px;
        """)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Overall progress bar
        self.progress_label = QLabel("0 / 52 steps completed")
        self.progress_label.setStyleSheet(
            "color: #8888aa; font-size: 11px; padding: 0 8px 8px;"
        )
        self.progress_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.progress_label)

        # Scrollable phase list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QWidget()
        self.phases_layout = QVBoxLayout(container)
        self.phases_layout.setSpacing(8)
        self.phases_layout.addStretch()

        scroll.setWidget(container)
        layout.addWidget(scroll)

        self._phase_groups = []

    def add_phase(self, phase_group: PhaseGroup):
        phase_group.step_clicked.connect(self.step_clicked.emit)
        count = self.phases_layout.count()
        self.phases_layout.insertWidget(count - 1, phase_group)
        self._phase_groups.append(phase_group)
```

### 6.3 Visual Design Notes for the Stepper

- **Vertical sidebar** is preferred over horizontal stepper because 52 steps do not fit horizontally.
- **Phase grouping** is essential -- without it, 52 steps is an overwhelming wall of text.
- **Color coding:** Completed = green dot (filled), Current = blue dot (larger, glowing), Upcoming = gray ring (hollow). This is a universally understood visual language.
- **Connecting lines** between dots (drawn in `paintEvent`) reinforce the linear progression. Use a thin vertical line (1-2px, #45475a) running down the left side of the step list, passing through each dot.
- **Collapse/expand** on phase groups helps manage visual complexity. Let users collapse completed phases.
- **Progress summary** at the top ("12 / 52 steps completed") gives immediate orientation.

---

## 7. Icons and Visual Assets

### 7.1 QtAwesome (Recommended Primary Icon Library)

**Repository:** https://github.com/spyder-ide/qtawesome
**License:** MIT
**Install:** `pip install qtawesome`

QtAwesome bundles multiple icon fonts and provides a simple Python API:

```python
import qtawesome as qta
from PySide6.QtWidgets import QPushButton, QAction

# Basic icon
icon = qta.icon("mdi6.sword-cross")  # Material Design Icons 6.x
button = QPushButton(icon, "Battle")

# Colored icon
icon = qta.icon("mdi6.earth", color="#2a9d8f")

# Animated icon (for loading spinners)
spin_icon = qta.icon("mdi6.loading", animation=qta.Spin(button))

# Stacked icons
icon = qta.icon("mdi6.shield", "mdi6.star",
                 options=[
                     {"color": "#45475a", "scale_factor": 1.0},
                     {"color": "#f4a261", "scale_factor": 0.5},
                 ])

# Use in QAction
action = QAction(qta.icon("mdi6.content-save"), "Save", parent)

# Use in tree/list items
item = QStandardItem(qta.icon("mdi6.account-group"), "Species")
```

**Available icon sets in QtAwesome:**

| Prefix | Set | Count | Style |
|--------|-----|-------|-------|
| `fa5s`, `fa5b` | Font Awesome 5 (Solid, Brands) | ~1600 | Classic web icons |
| `mdi6` | Material Design Icons 6.x | ~7000 | Modern, comprehensive |
| `ph` | Phosphor Icons | ~4470 | Clean, minimal |
| `ri` | Remix Icon | ~2271 | Modern, balanced |
| `msc` | Microsoft Codicons | ~569 | VS Code style |

**Tip:** Run `qta-browser` from the command line to launch a visual icon browser where you can search and preview all available icons.

### 7.2 qt-material-icons (Alternative)

**Repository:** https://github.com/beatreichenbach/qt-material-icons
**Install:** `pip install qt-material-icons`

Provides Google's Material Symbols directly:

```python
from qt_material_icons import MaterialIcon

icon = MaterialIcon("search")
icon = MaterialIcon("castle", color=QColor("#f4a261"))
```

### 7.3 SVG Icons in PySide6

For custom icons or when using downloaded SVG files (e.g., from https://fonts.google.com/icons):

```python
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import QSize

# Direct SVG loading (simplest)
icon = QIcon("path/to/icon.svg")

# SVG with custom size rendering
renderer = QSvgRenderer("path/to/icon.svg")
pixmap = QPixmap(QSize(24, 24))
pixmap.fill(Qt.transparent)
painter = QPainter(pixmap)
renderer.render(painter)
painter.end()
icon = QIcon(pixmap)

# Tip: Place SVGs before PNGs in QIcon to ensure the SVG engine is selected
icon = QIcon()
icon.addFile("icon.svg")  # Add SVG first
icon.addFile("icon@2x.png")  # Fallback
```

### 7.4 Color-Coding Entity Types

Establish a consistent color palette for entity types and use it everywhere -- tree view icons, card badges, sidebar indicators:

```python
ENTITY_TYPE_COLORS = {
    "god":         {"bg": "#f4a261", "fg": "#1e1e2e", "icon": "mdi6.weather-sunny"},
    "species":     {"bg": "#2a9d8f", "fg": "#ffffff", "icon": "mdi6.paw"},
    "settlement":  {"bg": "#e76f51", "fg": "#ffffff", "icon": "mdi6.city"},
    "culture":     {"bg": "#264653", "fg": "#ffffff", "icon": "mdi6.account-group"},
    "artifact":    {"bg": "#e9c46a", "fg": "#1e1e2e", "icon": "mdi6.diamond-stone"},
    "region":      {"bg": "#7209b7", "fg": "#ffffff", "icon": "mdi6.map"},
    "event":       {"bg": "#f72585", "fg": "#ffffff", "icon": "mdi6.calendar-star"},
    "magic_system":{"bg": "#4361ee", "fg": "#ffffff", "icon": "mdi6.auto-fix"},
    "language":    {"bg": "#4cc9f0", "fg": "#1e1e2e", "icon": "mdi6.translate"},
    "religion":    {"bg": "#b5179e", "fg": "#ffffff", "icon": "mdi6.candelabra"},
}

def get_entity_icon(entity_type: str) -> QIcon:
    """Get a colored icon for an entity type."""
    config = ENTITY_TYPE_COLORS.get(entity_type, {})
    icon_name = config.get("icon", "mdi6.help-circle")
    color = config.get("bg", "#888888")
    return qta.icon(icon_name, color=color)
```

---

## 8. Responsive Layouts

### 8.1 Main Window Layout with QSplitter

The application's main layout uses nested splitters to create resizable panels:

```python
from PySide6.QtWidgets import QMainWindow, QSplitter
from PySide6.QtCore import Qt, QSettings


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Worldbuilding Tool")
        self.setMinimumSize(1024, 640)

        # Main horizontal splitter: sidebar | center | right panel
        self.main_splitter = QSplitter(Qt.Horizontal)

        # Left: Progress sidebar (fixed width, but allow some resize)
        self.progress_sidebar = ProgressSidebar()
        self.main_splitter.addWidget(self.progress_sidebar)

        # Center: Vertical splitter for chat + options
        self.center_splitter = QSplitter(Qt.Vertical)
        self.chat_panel = ChatPanel()
        self.option_panel = OptionComparisonPanel()
        self.center_splitter.addWidget(self.chat_panel)
        self.center_splitter.addWidget(self.option_panel)
        self.center_splitter.setSizes([500, 300])
        self.main_splitter.addWidget(self.center_splitter)

        # Right: Entity browser
        self.entity_browser = EntityBrowser()
        self.main_splitter.addWidget(self.entity_browser)

        # Set initial proportions
        self.main_splitter.setSizes([260, 600, 320])

        # Set minimum widths
        self.progress_sidebar.setMinimumWidth(200)
        self.entity_browser.setMinimumWidth(250)

        # Prevent sidebar from being collapsed to zero
        self.main_splitter.setCollapsible(0, False)

        self.setCentralWidget(self.main_splitter)

        # Restore saved layout
        self._restore_layout()

    def _restore_layout(self):
        settings = QSettings("WorldbuildingTool", "MainWindow")

        # Window geometry
        geometry = settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)

        # Splitter states
        main_state = settings.value("mainSplitter")
        if main_state:
            self.main_splitter.restoreState(main_state)

        center_state = settings.value("centerSplitter")
        if center_state:
            self.center_splitter.restoreState(center_state)

    def closeEvent(self, event):
        """Save layout state on close."""
        settings = QSettings("WorldbuildingTool", "MainWindow")
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("mainSplitter", self.main_splitter.saveState())
        settings.setValue("centerSplitter", self.center_splitter.saveState())
        super().closeEvent(event)
```

### 8.2 Key QSplitter Tips

- **`setSizes()`** takes a list of pixel widths. These are proportional starting sizes.
- **`setCollapsible(index, False)`** prevents a panel from being dragged to zero width.
- **`setStretchFactor(index, factor)`** controls how extra space is distributed when the window is resized. Set the center panel's stretch factor higher than sidebars.
- **`saveState()` / `restoreState()`** with `QSettings` persists panel sizes between sessions. Always pair them.
- **Handle styling:** The splitter handle (drag bar) can be styled:

```css
QSplitter::handle {
    background-color: #2d2d3f;
    width: 2px;
}
QSplitter::handle:hover {
    background-color: #89b4fa;
}
```

### 8.3 Handling Window Resize Gracefully

- Set `minimumSize` on the main window (1024x640 is a reasonable minimum).
- Set `minimumWidth` on panels that have critical content (sidebar: 200px, entity browser: 250px).
- Use `QSizePolicy.Expanding` on the center panel so it absorbs extra space.
- Test at common screen sizes: 1366x768, 1920x1080, 2560x1440, and scaled HiDPI.

### 8.4 Alternative: Qt Advanced Docking System

For more advanced layout needs (detachable panels, tabbed docking, floating windows):

**Repository:** https://github.com/githubuser0xFFFF/Qt-Advanced-Docking-System
**Install:** `pip install PyQtAds` (PySide6 bindings available)

This is overkill for initial development but worth considering if users request detachable panels.

---

## 9. Animations and Polish

Animations make the difference between "functional" and "polished." They should be subtle, fast, and purposeful -- never gratuitous.

### 9.1 QPropertyAnimation Basics

```python
from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QPoint, QRect
from PySide6.QtWidgets import QWidget


def fade_in(widget: QWidget, duration: int = 300):
    """Smoothly fade a widget from invisible to visible."""
    widget.setWindowOpacity(0.0)
    widget.show()
    anim = QPropertyAnimation(widget, b"windowOpacity")
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    anim.start()
    return anim  # Must keep reference alive


def slide_in_from_right(widget: QWidget, duration: int = 350):
    """Slide a widget in from the right edge."""
    start_pos = widget.pos() + QPoint(widget.width(), 0)
    end_pos = widget.pos()

    anim = QPropertyAnimation(widget, b"pos")
    anim.setDuration(duration)
    anim.setStartValue(start_pos)
    anim.setEndValue(end_pos)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    anim.start()
    return anim
```

### 9.2 Animated Card Hover Effect

Since QSS `:hover` pseudo-states cannot animate smoothly, use `enterEvent`/`leaveEvent` with `QPropertyAnimation` for smooth hover effects:

```python
from PySide6.QtCore import QPropertyAnimation, QEasingCurve, Property
from PySide6.QtGui import QColor


class AnimatedCard(Card):
    """Card with smooth hover animation."""

    def __init__(self, title="", parent=None):
        super().__init__(title, parent)
        self._hover_progress = 0.0  # 0.0 = normal, 1.0 = fully hovered
        self._anim = QPropertyAnimation(self, b"hover_progress")
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.InOutQuad)

    def get_hover_progress(self):
        return self._hover_progress

    def set_hover_progress(self, value):
        self._hover_progress = value
        # Interpolate background color
        base = QColor("#2d2d3f")
        hover = QColor("#33334a")
        r = base.red() + (hover.red() - base.red()) * value
        g = base.green() + (hover.green() - base.green()) * value
        b = base.blue() + (hover.blue() - base.blue()) * value
        color = QColor(int(r), int(g), int(b))
        self.setStyleSheet(f"""
            QFrame#card {{
                background-color: {color.name()};
                border: 1px solid {'#6c6c9a' if value > 0.5 else '#3d3d5c'};
                border-radius: 12px;
                padding: 16px;
            }}
        """)

    hover_progress = Property(float, get_hover_progress, set_hover_progress)

    def enterEvent(self, event):
        self._anim.stop()
        self._anim.setStartValue(self._hover_progress)
        self._anim.setEndValue(1.0)
        self._anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._anim.stop()
        self._anim.setStartValue(self._hover_progress)
        self._anim.setEndValue(0.0)
        self._anim.start()
        super().leaveEvent(event)
```

### 9.3 Loading Spinner for Async Operations

Using QtAwesome's built-in animation support:

```python
import qtawesome as qta
from PySide6.QtWidgets import QLabel, QPushButton


class LoadingSpinner(QLabel):
    """Animated spinning icon for loading states."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(32, 32)
        self._spin_icon = qta.icon(
            "mdi6.loading",
            animation=qta.Spin(self, interval=10, step=5),
            color="#89b4fa",
        )
        self.setPixmap(self._spin_icon.pixmap(32, 32))

    def start(self):
        self.show()

    def stop(self):
        self.hide()
```

For a custom spinner without QtAwesome:

```python
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPainter, QColor, QPen
import math


class SpinnerWidget(QWidget):
    """Custom spinning dots loading indicator."""

    def __init__(self, parent=None, dot_count=8, dot_size=4, radius=12):
        super().__init__(parent)
        self.dot_count = dot_count
        self.dot_size = dot_size
        self.radius = radius
        self._angle = 0
        self.setFixedSize(radius * 2 + dot_size * 2, radius * 2 + dot_size * 2)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self._timer.setInterval(80)

    def start(self):
        self.show()
        self._timer.start()

    def stop(self):
        self._timer.stop()
        self.hide()

    def _rotate(self):
        self._angle = (self._angle + 1) % self.dot_count
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        center_x = self.width() / 2
        center_y = self.height() / 2

        for i in range(self.dot_count):
            angle = 2 * math.pi * i / self.dot_count
            x = center_x + self.radius * math.cos(angle)
            y = center_y + self.radius * math.sin(angle)

            # Fade dots based on distance from active dot
            distance = (self._angle - i) % self.dot_count
            opacity = max(0.15, 1.0 - (distance / self.dot_count))

            color = QColor("#89b4fa")
            color.setAlphaF(opacity)
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(int(x - self.dot_size / 2),
                                int(y - self.dot_size / 2),
                                self.dot_size, self.dot_size)
```

### 9.4 Smooth Panel Transitions

When switching between views (e.g., from chat to option selection):

```python
from PySide6.QtWidgets import QStackedWidget
from PySide6.QtCore import QPropertyAnimation, QEasingCurve


class AnimatedStackedWidget(QStackedWidget):
    """QStackedWidget with fade transition between pages."""

    def setCurrentIndex(self, index):
        if index == self.currentIndex():
            return

        # Fade out current
        current = self.currentWidget()
        next_widget = self.widget(index)

        if current and next_widget:
            # Use opacity animation
            self._fade_out = QPropertyAnimation(current, b"windowOpacity")
            self._fade_out.setDuration(150)
            self._fade_out.setStartValue(1.0)
            self._fade_out.setEndValue(0.0)
            self._fade_out.setEasingCurve(QEasingCurve.InQuad)

            self._fade_in = QPropertyAnimation(next_widget, b"windowOpacity")
            self._fade_in.setDuration(150)
            self._fade_in.setStartValue(0.0)
            self._fade_in.setEndValue(1.0)
            self._fade_in.setEasingCurve(QEasingCurve.OutQuad)

            def on_fade_out_done():
                super(AnimatedStackedWidget, self).setCurrentIndex(index)
                self._fade_in.start()

            self._fade_out.finished.connect(on_fade_out_done)
            self._fade_out.start()
        else:
            super().setCurrentIndex(index)
```

### 9.5 Animation Guidelines

- **Duration:** 150-300ms for UI transitions. Never exceed 500ms for direct interactions.
- **Easing:** `OutCubic` for entrances (fast start, gentle stop). `InOutQuad` for hover state changes. `InCubic` for exits.
- **Purpose:** Every animation should serve a purpose -- showing spatial relationships, providing feedback, or smoothing jarring transitions. If an animation does not serve the user, remove it.
- **Performance:** Avoid animating large widgets or complex repaints. If an animation causes visible stuttering, simplify it or shorten it.
- **Accessibility:** Consider providing a "reduce motion" setting that disables non-essential animations.

---

## Appendix A: Recommended Visual Reference Projects

These open-source PySide6 projects demonstrate modern UI design worth studying:

1. **PyDracula** (https://github.com/Wanderson-Magalhaes/Modern_GUI_PyDracula_PySide6_or_PyQt6) -- Modern sidebar navigation, custom title bar, dark theme, animated menus. The most popular modern PySide6 UI template on GitHub.

2. **PySide6 Cheatsheet** (https://github.com/Tevres/PySide6-cheatsheet) -- Clean, modern examples of common widget patterns with good styling.

3. **Qt-Material Examples** (https://github.com/UN-GCPDS/qt-material) -- The qt-material repo includes example screenshots of every built-in theme applied to standard Qt widgets.

---

## Appendix B: Typography Recommendations

For a creative tool, typography matters. Qt inherits the system font by default, but you can set a better one:

```python
from PySide6.QtGui import QFontDatabase, QFont

# Load a custom font (Inter is an excellent UI font)
font_id = QFontDatabase.addApplicationFont(":/fonts/Inter-Regular.ttf")
QFontDatabase.addApplicationFont(":/fonts/Inter-Bold.ttf")

# Set as application default
app.setFont(QFont("Inter", 13))
```

**Recommended fonts:**
- **Inter** -- Modern, clean, excellent readability. Free. Designed specifically for screens.
- **Segoe UI** -- Already present on Windows. Good fallback.
- **SF Pro** -- Already present on macOS. Good fallback.

**Font sizing guidelines:**
- Body text: 13-14px
- Secondary/description text: 11-12px
- Card titles: 15-16px
- Section headers: 18-20px
- Phase group headers: 12px bold uppercase

---

## Appendix C: Color Palette (Catppuccin Mocha-Inspired)

The code examples throughout this document use a consistent palette inspired by Catppuccin Mocha, which is warm, accessible, and creative-feeling:

| Token | Hex | Usage |
|-------|-----|-------|
| Base | `#1e1e2e` | Main background |
| Mantle | `#1a1a2e` | Sidebar background |
| Surface 0 | `#313244` | Input fields, card alternate |
| Surface 1 | `#45475a` | Borders, subtle elements |
| Surface 2 | `#585b70` | Hover borders |
| Overlay 0 | `#6c6c9a` | Hover highlights |
| Text | `#cdd6f4` | Primary text |
| Subtext | `#b0b0d0` | Secondary text |
| Lavender | `#89b4fa` | Accent, links, current step |
| Green | `#4ade80` | Success, completed, canon status |
| Yellow | `#fbbf24` | Warning, draft status |
| Peach | `#f4a261` | Entity type: god |
| Teal | `#2a9d8f` | Entity type: species |
| Red | `#e76f51` | Entity type: settlement |

This palette works well with both `qt-material` (as custom overrides) and custom QSS.

---

## Sources

### Dark Themes
- [PyQtDarkTheme - GitHub](https://github.com/5yutan5/PyQtDarkTheme)
- [PyQtDarkTheme Documentation](https://pyqtdarktheme.readthedocs.io/en/stable/how_to_use.html)
- [qt-material - PyPI](https://pypi.org/project/qt-material/)
- [qt-material - GitHub](https://github.com/UN-GCPDS/qt-material)
- [QtModernRedux6 - PyPI](https://pypi.org/project/QtModernRedux6/)
- [BreezeStyleSheets - GitHub](https://github.com/Alexhuszagh/BreezeStyleSheets)
- [QDarkStyleSheet - GitHub](https://github.com/ColinDuquesnoy/QDarkStyleSheet)

### Cards and Layouts
- [QFrame - Qt for Python Docs](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QFrame.html)
- [QGraphicsDropShadowEffect - Qt Docs](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QGraphicsDropShadowEffect.html)
- [PyDracula Modern GUI - GitHub](https://github.com/Wanderson-Magalhaes/Modern_GUI_PyDracula_PySide6_or_PyQt6)
- [PySide6 Cheatsheet - GitHub](https://github.com/Tevres/PySide6-cheatsheet)

### Chat and Markdown
- [QTextBrowser - Qt Docs](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QTextBrowser.html)
- [QTextDocument - Qt Docs](https://doc.qt.io/qtforpython-6/PySide6/QtGui/QTextDocument.html)
- [QMarkdownView - GitHub](https://github.com/hellojudger/QMarkdownView)
- [WebEngine Markdown Editor Example - Qt Docs](https://doc.qt.io/qtforpython-6/examples/example_webenginewidgets_markdowneditor.html)

### Entity Browser
- [QSortFilterProxyModel - Qt Docs](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QSortFilterProxyModel.html)
- [QStyledItemDelegate - Qt Docs](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QStyledItemDelegate.html)
- [Star Delegate Example - Qt Docs](https://doc.qt.io/qtforpython-6/examples/example_widgets_itemviews_stardelegate.html)
- [QTreeView Custom Filter Models - Blog](https://gaganpreet.in/blog/2013/07/04/qtreeview-and-custom-filter-models/)

### Icons
- [QtAwesome - GitHub](https://github.com/spyder-ide/qtawesome)
- [QtAwesome Usage Docs](https://qtawesome.readthedocs.io/en/latest/usage.html)
- [qt-material-icons - GitHub](https://github.com/beatreichenbach/qt-material-icons)
- [Material Icons Guide - Google](https://developers.google.com/fonts/docs/material_icons)

### Layouts and Splitters
- [QSplitter - Qt Docs](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QSplitter.html)
- [Qt Advanced Docking System - GitHub](https://github.com/githubuser0xFFFF/Qt-Advanced-Docking-System)

### Animations
- [QPropertyAnimation - Qt Docs](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QPropertyAnimation.html)
- [Animating PySide6 Widgets - PythonGUIs](https://www.pythonguis.com/tutorials/pyside6-animated-widgets/)
- [PySide6 Tutorial - PythonGUIs](https://www.pythonguis.com/pyside6-tutorial/)
