# Desktop Framework Research for Worldbuilding Interactive Program

**Date:** January 30, 2026
**Purpose:** Evaluate Python desktop GUI frameworks for a standalone worldbuilding application
**Key Constraint:** Must integrate with Claude Agent SDK (async Python) via Claude Code CLI subscription

---

## Table of Contents

1. [Project Requirements Recap](#project-requirements-recap)
2. [Framework Deep Dives](#framework-deep-dives)
   - [PySide6 (Qt)](#1-pyside6--qt)
   - [Dear PyGui](#2-dear-pygui-bonus-contender)
   - [NiceGUI Native Mode (pywebview)](#3-nicegui-native-mode-pywebview)
   - [Flet (Flutter-based)](#4-flet-flutter-based)
   - [Electron + Python Backend](#5-electron--python-backend)
   - [Tauri + Python](#6-tauri--python)
   - [CustomTkinter](#7-customtkinter)
   - [Kivy / KivyMD](#8-kivy--kivymd)
3. [Scoring Matrix](#scoring-matrix)
4. [Top 3 Recommendations](#top-3-recommendations)
5. [Recommendation #1 Deep Dive: Code Examples](#recommendation-1-deep-dive-code-examples)
6. [Honest Trade-offs Summary](#honest-trade-offs-summary)
7. [Sources](#sources)

---

## Project Requirements Recap

| Requirement | Detail |
|---|---|
| **Window type** | Standalone desktop window (NOT a browser, NOT a web app) |
| **OS** | Windows (primary) |
| **Backend** | Python (10 engine modules already built), Claude Agent SDK (async) |
| **API keys** | None -- uses Claude Code CLI subscription |
| **Visual style** | Modern, professional, dark theme |
| **Key UI components** | Interactive knowledge graph, option comparison cards (2-4 side by side), entity browser with search, progression tracker, chat/streaming panel |
| **User** | Non-technical -- installation must be simple |

---

## Framework Deep Dives

### 1. PySide6 / Qt

**What it is:** PySide6 is the official Python binding for the Qt6 framework, maintained by The Qt Company. Qt is a mature C++ application framework with over 25 years of history. PySide6 is licensed under the LGPL, meaning you can use it in closed-source commercial applications for free without purchasing a license. PyQt6 is the alternative binding by Riverbank Computing, licensed under GPL (must open-source your code) or a commercial license. For this project, **PySide6 is the clear choice** over PyQt6.

**Native feel:** Excellent. Qt renders using platform-native APIs and its own high-quality widget toolkit. Applications look and feel like real desktop software -- toolbars, menus, status bars, dockable panels, splitters. Think applications like VLC, Calibre, Spyder IDE, Anki, and the Telegram Desktop client. These are all Qt applications.

**Visual quality / Dark theme:** Multiple polished dark theme libraries exist:
- **PyQtDarkTheme (qdarktheme):** Flat, modern dark theme. Supports accent color customization and corner shape tweaks. Works with PySide6 out of the box. One line of code: `qdarktheme.setup_theme("dark")`.
- **Qt-Material:** Material Design inspired stylesheet. Supports density scaling and runtime theme switching.
- **QtModernRedux:** Provides frameless/no-titlebar mode for ultra-modern looks. Consistent across platforms and DPI settings. Works with PyInstaller.
- **QDarkStyleSheet:** Classic dark stylesheet, most complete coverage, but Qt6 support is marked experimental.

Verdict: Getting a professional dark theme is **trivial**. One `pip install` and one line of code.

**Knowledge graph rendering:** This is where PySide6 truly shines.
- **QGraphicsView / QGraphicsScene / QGraphicsItem:** Qt's built-in 2D graphics framework. Supports zoom, pan, rotation, item selection, drag-and-drop, collision detection, and custom rendering. This is a full-featured 2D scene graph engine.
- **Official NetworkX Viewer Example:** Qt for Python provides an official example showing how to render a NetworkX directed graph inside QGraphicsView with custom Node and Edge classes, multiple layout algorithms (circular, planar, random), and animated transitions.
- **Dedicated node editor libraries:**
  - **SpatialNode:** A pure Python PySide6 dataflow node editor framework. Supports registering processing algorithms as nodes with Qt signals/slots for data propagation.
  - **NodeGraphQt-PySide6:** A node graph UI framework ported to PySide6.
  - **OdenGraphQt:** A node graph framework for PySide6/PyQt6, MIT licensed.
  - **qtpynodeeditor:** A pure Python port of NodeEditor supporting PySide6 via qtpy.
  - **qtPyGraphEdit:** A graphical node-edge graph editor in PySide6 with multipoint edges, spline routing, and directed/undirected edge support.
- **Qt's Elastic Nodes Example:** An official PySide6 example with physics-based interactive nodes connected by elastic edges.

Verdict: PySide6 has the **best** knowledge graph story of any framework. Multiple production-ready node editor libraries exist. You can build an interactive, zoomable, pannable knowledge graph without embedding any web view.

**Streaming text:** Standard approach uses `QPlainTextEdit` or `QTextEdit` with `appendPlainText()` or `insertPlainText()`. Updates are triggered via Qt's signal/slot mechanism from background threads using `QThread` + custom signals, or via `QTimer` polling. This is a solved problem -- Qt has been doing real-time text streaming for decades.

**Async support (critical for Claude Agent SDK):**
- **qasync:** The most popular solution. Replaces asyncio's event loop with one that integrates with Qt's event loop. Supports Python 3.8-3.13. Works with aiohttp, httpx, and other async networking libraries. Usage: `asyncio.run(main(app), loop_factory=QEventLoop)`.
- **PySide6.QtAsyncio:** Official Qt solution. Works for basic async but has a known limitation: network async events (DNS, sockets) are not implemented. This means it will **not** work with Claude Agent SDK's async streaming. Use qasync instead.
- **asyncslot / qtinter:** Newer alternatives rewritten from scratch based on qasync concepts.

Verdict: Async works well via **qasync**. The official QtAsyncio has networking limitations, so use the third-party qasync package. This is a well-trodden path.

**Card layouts:** Qt's layout system is extremely flexible. Use `QHBoxLayout` with `QFrame` or `QGroupBox` widgets styled via QSS (Qt Style Sheets, which use CSS-like syntax). Cards with rounded corners, shadows, borders, and rich content are straightforward.

**Search/filter:** Qt has `QListView`/`QTreeView` with `QSortFilterProxyModel` built in. This is industrial-strength filtering with regex support, multi-column sorting, and lazy loading for large datasets.

**Installation:** Package with PyInstaller into a standalone `.exe`. Use InstallForge or Inno Setup to create a Windows installer. User double-clicks the installer, clicks "Next" a few times, and gets a desktop shortcut.

**Bundle size:** A minimal PySide6 app packaged with PyInstaller is roughly **60-120 MB** depending on which Qt modules are included. Excluding unused modules (QtWebEngine, Qt3D, QtQuick) and using UPX compression can bring this down. The `pyside6-deploy` tool (which wraps Nuitka) can produce even smaller builds.

**Community/maturity:** Qt has been production-ready since 1995. PySide6 is maintained by The Qt Company itself. Massive community, extensive documentation, books (PySide6 book by Martin Fitzpatrick, 6th edition 2025), and thousands of StackOverflow answers. Real-world apps: VLC, Calibre, Anki, Spyder IDE, Telegram Desktop, QGIS, FreeCAD, Blender (partially), and many more.

**Python backend integration:** PySide6 is pure Python. Your 10 engine modules can be imported and called directly. No IPC, no HTTP server, no subprocess communication needed.

---

### 2. Dear PyGui (Bonus Contender)

**What it is:** Dear PyGui is a GPU-accelerated Python GUI framework built on top of Dear ImGui (C++). It uses an "immediate mode" rendering paradigm and renders via DirectX 11 (Windows), Metal (macOS), or OpenGL (Linux). Licensed under MIT.

**Native feel:** Mixed. Dear PyGui creates its own window and renders everything via GPU. It does NOT use OS-native widgets. The window itself is native, but the UI inside is custom-rendered. It looks more like a game engine editor (Unity, Unreal) than a traditional desktop app. For a worldbuilding tool, this aesthetic actually works well.

**Visual quality / Dark theme:** Dear PyGui ships with built-in dark themes ("Dark", "Dark 2", "Dark Grey", "Cherry", etc.). Custom themes are created with `dpg.theme()` and `dpg.add_theme_color()`. The default look is already dark and professional. No extra libraries needed.

**Knowledge graph rendering:** **This is Dear PyGui's killer feature.** It has a **built-in node editor** -- not a third-party library, but a first-class widget. You create nodes with `dpg.add_node()`, add attributes with `dpg.add_node_attribute()`, and connect them with `dpg.add_node_link()`. Nodes can contain any widget (inputs, plots, text, images). This is the exact same node editor paradigm used in Blender's shader editor or Unreal's Blueprint system. Real-world projects like Heron (visual process orchestrator) and Flux (flowfield visualization) use it.

**Streaming text:** Use `dpg.add_text(tag="output")` and update with `dpg.set_value("output", new_text)`. Since Dear PyGui is immediate-mode, updates are reflected on the next frame automatically.

**Async support:** Replace `dpg.start_dearpygui()` with a custom render loop:
```python
while dpg.is_dearpygui_running():
    dpg.render_dearpygui_frame()
    await asyncio.sleep(0)
```
The `dearpygui-async` PyPI package wraps this pattern. Works with asyncio.

**Card layouts:** Dear PyGui uses a flow-based layout system. You can create card-like groups using `dpg.add_group(horizontal=True)` with child windows or collapsing headers. It is less flexible than Qt's layout system for pixel-perfect card designs, but adequate.

**Search/filter:** You can build a search/filter UI with `dpg.add_input_text()` and `dpg.add_listbox()` or `dpg.add_table()`. No built-in proxy model like Qt -- you implement filtering in Python. Straightforward but manual.

**Installation:** Package with PyInstaller. Dear PyGui has minimal dependencies (just the GPU runtime).

**Bundle size:** Smaller than PySide6. A packaged Dear PyGui app is roughly **30-60 MB**.

**Community/maturity:** Smaller community than Qt but active. GitHub has 13k+ stars. Documentation was updated January 27, 2026. The framework is stable but receives fewer updates than PySide6. It lacks the breadth of Qt's ecosystem (no built-in SQL, no built-in web engine, no designer tool).

**Python backend integration:** Pure Python. Direct imports, no IPC needed.

**Honest downsides:**
- No visual designer tool (everything is code)
- Limited text rendering compared to Qt (no rich text, no HTML rendering)
- Smaller ecosystem for third-party widgets
- The "game engine editor" aesthetic may not suit all users
- Less mature accessibility support

---

### 3. NiceGUI Native Mode (pywebview)

**What it is:** NiceGUI is a Python web framework (built on FastAPI) that can run in "native mode" using pywebview. When you call `ui.run(native=True)`, it creates a native desktop window using pywebview that internally connects to a local FastAPI server via WebSocket. On Windows, it uses Edge WebView2 (Chromium-based) for rendering.

**Native feel:** Moderate. The window chrome (title bar, minimize/maximize/close buttons) is native Windows. But the content inside is rendered by a web browser engine. Users who look closely may notice browser-like behaviors (text selection, right-click context menus, scroll physics). It is NOT the same as Electron -- it is lighter, but it is still fundamentally a web page in a native wrapper.

**Visual quality / Dark theme:** Excellent, because you are writing HTML/CSS. You can use any CSS framework (Tailwind, Bootstrap) or custom CSS for a polished dark theme. NiceGUI provides built-in dark mode support. For visual polish, this is arguably the easiest path.

**Knowledge graph rendering:** You would use a JavaScript graph library (D3.js, vis.js, Cytoscape.js, Sigma.js) embedded in the NiceGUI page. This works well and these libraries are powerful. However, this means you ARE embedding a web view -- the entire app is a web view. The graph rendering itself would be excellent, but it violates the spirit of "native desktop app."

**Streaming text:** Trivial with NiceGUI's reactive model. Use `ui.markdown()` or `ui.label()` and update the content. Since it is web-based, you get smooth text rendering and animation for free.

**Async support:** NiceGUI is built on FastAPI, which is async-native. Excellent async support.

**Card layouts:** Use NiceGUI's `ui.card()` widget or raw HTML/CSS Flexbox/Grid. Easy.

**Search/filter:** Use NiceGUI's `ui.input()` with `on_change` callbacks and `ui.table()`. Easy.

**Installation:** This is where it gets complicated. You need Python installed, plus pywebview, plus Edge WebView2 runtime. Packaging with PyInstaller is possible but NiceGUI's own documentation notes that native mode packaging is "not well-tested." Users have reported issues with frozen/packaged native mode apps. The NiceGUI team has acknowledged they have **no automated tests for native mode**.

**Bundle size:** Moderate. The app itself is small but you need the Python runtime and NiceGUI's dependencies (FastAPI, Uvicorn, etc.). Roughly **80-150 MB** packaged.

**Community/maturity:** NiceGUI is actively maintained (latest release January 21, 2026). The web mode is mature and well-tested. The native mode is a secondary feature with known limitations:
- Only supports **one window** at a time
- Frameless windows cannot be minimized from the taskbar on Windows
- Some users report content not loading in native mode
- No automated tests for native mode exist
- Ubuntu users have encountered multiprocessing SemLock errors

**Python backend integration:** Direct Python imports. NiceGUI is Python-native.

**Honest downsides:**
- Native mode is a second-class citizen in NiceGUI
- Packaging for distribution is fragile
- It IS a web app in disguise -- if you wanted a web app, you would just use NiceGUI in browser mode
- pywebview on Windows has known issues: button interaction lag, frameless window quirks, loading failures on some machines, main thread freezing
- Edge WebView2 must be present on the user's system (usually is on Windows 10/11, but not guaranteed)

---

### 4. Flet (Flutter-based)

**What it is:** Flet lets you build desktop, web, and mobile apps in pure Python. Under the hood, it uses Flutter for rendering. Your Python code describes a tree of Flutter widgets, and Flet's runtime renders them. On desktop, it creates a native window with Flutter content.

**Native feel:** Good but not native-widget-based. Flet uses Flutter's Material Design widgets, which look modern and consistent but do NOT use OS-native controls. The window itself is native. The result looks like a polished mobile app running on desktop -- think Google's design language.

**Visual quality / Dark theme:** Flutter's Material Design includes a comprehensive dark theme out of the box. `ft.Theme(color_scheme=ft.ColorScheme(primary=ft.Colors.BLUE))` with `theme_mode=ft.ThemeMode.DARK`. Looks modern and polished with zero effort.

**Knowledge graph rendering:** This is Flet's weakness. Flet provides:
- Built-in charts: BarChart, LineChart, PieChart (based on fl_chart)
- MatplotlibChart: Embed Matplotlib plots
- Canvas: Low-level drawing with shapes (line, circle, arc, path, text) + GestureDetector for interaction

There is **no dedicated node graph widget** for Flet. You would need to build one from scratch using Canvas + GestureDetector for draggable nodes and drawn edges. This is significantly more work than using PySide6's existing node editor libraries or Dear PyGui's built-in node editor. The Canvas API is capable but building a full interactive knowledge graph with zoom, pan, click-to-select, drag-to-move, and edge routing from scratch is a major undertaking.

**Streaming text:** Use `ft.Text()` or `ft.Markdown()` and call `page.update()` to refresh. Works but Flet's update model is not truly reactive -- you must explicitly call `page.update()` after changes.

**Async support:** Flet supports async event handlers natively. You can use `async def` for event handlers and Flet will run them in its event loop. This should work with Claude Agent SDK.

**Card layouts:** `ft.Card()` is a built-in widget. Combine with `ft.Row()` for side-by-side cards. Easy and looks good.

**Search/filter:** `ft.TextField()` + `ft.ListView()` with filtering logic. Works but no built-in proxy model.

**Installation:** Flet provides `flet build windows` which produces a standalone Windows executable. However, this requires **Visual Studio 2022 with the "Desktop development with C++" workload** installed on the build machine. For a non-technical user, this means YOU must build it and distribute the exe.

**Bundle size:** Varies significantly:
- `flet pack` (PyInstaller wrapper): ~78 MB
- `flet build` (Flutter SDK): ~100+ MB
- Manual PyInstaller with `flet[desktop]`: ~17 MB (minimal)
- A `libmpv-2.dll` file (28 MB) is included by default for media playback, even if unused

**Community/maturity:** Flet is actively maintained (v0.80.4, January 2026). It is pre-1.0, meaning the API may still change. The community is growing but smaller than Qt's. It is a good framework for simpler apps but may lack the depth needed for complex applications.

**Python backend integration:** Direct Python imports.

**Honest downsides:**
- Pre-1.0: API instability is a risk
- No built-in node graph widget -- major gap for this project
- Building custom interactive graphics requires low-level Canvas work
- The `flet build` command requires Visual Studio 2022 C++ workload
- Performance concerns with large, frequently-updating UIs
- Material Design aesthetic may feel "mobile-first" on desktop

---

### 5. Electron + Python Backend

**What it is:** Electron wraps Chromium + Node.js to create desktop apps using HTML/CSS/JavaScript. VS Code, Discord, Slack, Notion, Figma desktop, and Spotify desktop are all Electron apps. The Python backend would run as a subprocess communicating via HTTP (Flask/FastAPI), WebSockets, ZeroRPC, or IPC.

**Native feel:** The window is native. The content is web-rendered. Electron apps are indistinguishable from native apps to most users because of the level of polish that Chromium rendering enables. VS Code and Discord prove that Electron can produce professional-quality desktop software.

**Visual quality / Dark theme:** Unlimited. You have the full power of HTML, CSS, React/Svelte/Vue, and every JavaScript library ever created. You could use D3.js, Three.js, vis.js, Cytoscape.js, or any graph visualization library. This is the most flexible option for visual quality.

**Knowledge graph rendering:** Exceptional. Libraries like Cytoscape.js, D3.js force layout, vis.js Network, Sigma.js, and React Flow provide production-ready interactive graph visualization with zoom, pan, click, drag, clustering, and animations. This is the gold standard for graph visualization.

**Streaming text:** Trivial with web technologies. Use a `<div>` with `overflow-y: scroll` and append text via JavaScript. Markdown rendering with libraries like marked.js or react-markdown.

**Async support:** The Python backend runs independently. Communication is via HTTP/WebSocket. The Python side can use asyncio freely. The JavaScript frontend handles its own async.

**Card layouts:** CSS Flexbox/Grid. Trivial.

**Search/filter:** React components, Svelte components, or vanilla JS. Thousands of pre-built solutions.

**Installation:** Electron Builder or Electron Forge produces a `.exe` installer. Users double-click to install, get a desktop shortcut. Professional and seamless.

**Bundle size:** This is the elephant in the room. Electron bundles Chromium, which adds **150-300 MB** to your app. A "Hello World" Electron app is ~150 MB. With Python bundled via PyInstaller, you are looking at **250-400 MB total**. Memory usage is also significant -- Electron apps typically consume **200-500 MB of RAM** at baseline, and can spike to 800 MB+ under load.

**Community/maturity:** Electron is extremely mature and widely used. Massive community, extensive documentation, and battle-tested in production by apps serving hundreds of millions of users.

**Python backend integration:** This is the pain point. You must:
1. Bundle Python as a subprocess (via PyInstaller or python-build-standalone)
2. Implement IPC between Electron (JavaScript) and Python (HTTP server, WebSocket, or child_process)
3. Handle process lifecycle (start Python when Electron starts, kill Python when Electron exits)
4. Maintain TWO languages (JavaScript + Python)
5. Debug across two runtimes

This is a **massive increase in complexity** compared to pure-Python frameworks.

**Honest downsides:**
- Two languages to maintain (JavaScript + Python)
- Complex IPC architecture
- 250-400 MB bundle size
- 200-500 MB RAM usage
- Significant development overhead for the frontend/backend bridge
- Overkill for a project where the developer is primarily a Python developer
- You would essentially be building two applications and gluing them together

**Verdict: Overkill.** If you were a JavaScript developer with an existing React frontend, Electron would be compelling. For a Python-first project, the complexity tax is not worth it.

---

### 6. Tauri + Python

**What it is:** Tauri is like Electron but uses the OS's native WebView (Edge WebView2 on Windows) instead of bundling Chromium. This makes apps much smaller (~5-10 MB vs ~150 MB). The backend is written in Rust. Python integration is achieved via:
- **PyTauri:** Tauri binding for Python through Pyo3. Community-driven, not officially endorsed by Tauri.
- **tauri-plugin-python:** A Tauri v2 plugin that uses RustPython or PyO3 to call Python from Rust.
- **Sidecar approach:** Run Python as a separate process (via PyInstaller) and communicate over HTTP.

**Native feel:** Good. Same as pywebview -- native window chrome with web content rendered by Edge WebView2.

**Visual quality / Dark theme:** Same as Electron -- full HTML/CSS/JavaScript.

**Knowledge graph rendering:** Same as Electron -- any JavaScript graph library works.

**Streaming text / Async / Cards / Search:** Same as Electron -- web technologies handle all of these well.

**Installation:** Tauri produces smaller installers (~5-10 MB for the app itself, plus Python runtime if bundled).

**Bundle size:** Much smaller than Electron. The Tauri shell is ~5-10 MB. But with Python bundled, total is ~60-100 MB.

**Community/maturity for Python integration:**
- **PyTauri:** "A fairly young project." Needs Rust compiler (unless using pytauri-wheel). Not officially endorsed by Tauri. Natively supports async Python (asyncio, trio, anyio). Inspired by FastAPI/Pydantic. Promising but unproven.
- **tauri-plugin-python:** "Hasn't been optimized yet for production binaries." RustPython doesn't support some built-in Python libraries. PyO3 mode requires libpython on the target platform.
- **Sidecar approach:** Most battle-tested but adds process management complexity.

**Honest downsides:**
- Python integration is immature and fragmented
- Multiple competing approaches, none fully production-ready
- Requires Rust knowledge for any customization beyond the basics
- PyTauri is community-driven with no official Tauri backing
- You still need JavaScript for the frontend
- Two or three languages to maintain (Python + JavaScript + possibly Rust)

**Verdict:** Interesting future technology but **not production-ready for Python backends** in January 2026. Check back in a year.

---

### 7. CustomTkinter

**What it is:** CustomTkinter is a modern-looking wrapper around Python's built-in Tkinter library. It provides updated widgets with rounded corners, dark/light mode support, and a more contemporary appearance. Created by Tom Schimansky.

**Native feel:** Moderate. CustomTkinter windows use OS-native window chrome. The widgets are custom-rendered on a Tkinter canvas, so they look better than raw Tkinter but are not truly native widgets. On Windows 10/11, it adapts to the system dark/light mode.

**Visual quality / Dark theme:** Built-in dark mode: `customtkinter.set_appearance_mode("dark")`. Looks modern for a Tkinter-based library, but still recognizably "Tkinter-ish." It cannot match the polish of Qt, Flutter, or web-based UIs. No shadows, no blur effects, limited animation support.

**Knowledge graph rendering:** This is a major weakness.
- **TkNodeSystem** exists but is self-described as "experimental" with "bugs which can appear randomly."
- The Tkinter Canvas can draw basic shapes but has no built-in scene graph, no zoom/pan framework, and no efficient hit testing for large numbers of items.
- NetworkX graphs can be rendered via Matplotlib embedded in a Tkinter canvas (FigureCanvasTkAgg), but this produces static images, not interactive node graphs.
- Building a custom interactive knowledge graph on the Tkinter Canvas would require enormous effort and would likely perform poorly with many nodes.

**Streaming text:** Use `CTkTextbox` and insert text. Works but basic.

**Async support:** Tkinter's event loop is NOT asyncio-compatible out of the box. You must use threading or a bridge like `tkinter.after()` for scheduling. Integrating with Claude Agent SDK's async streaming would require running asyncio in a separate thread with careful cross-thread communication. This is doable but awkward.

**Card layouts:** Use `CTkFrame` with `grid()` layout. You can create card-like frames, but rounded corners with shadows and rich content require significant custom work.

**Search/filter:** `CTkEntry` + manual list filtering. No built-in model/view architecture.

**Installation:** Package with PyInstaller. CustomTkinter is lightweight so bundle sizes are small (~20-40 MB).

**Bundle size:** Smallest of all options at ~20-40 MB.

**Community/maturity:** Active community, popular for beginners. But CustomTkinter is a one-person project (Tom Schimansky). It lacks the corporate backing and contributor base of Qt or Flutter. Suitable for simple to moderate applications, but stretched thin for complex UIs.

**Honest downsides:**
- No viable interactive knowledge graph solution
- Async integration is awkward
- Visual polish ceiling is lower than other options
- Layout system is less capable than Qt or web-based alternatives
- One-person project with sustainability concerns
- Not designed for complex, multi-panel applications

**Verdict:** CustomTkinter is excellent for simple tools and utilities. It is **not suitable** for this project's complexity (knowledge graphs, card comparisons, streaming panels, entity browsers).

---

### 8. Kivy / KivyMD

**What it is:** Kivy is an open-source Python framework for cross-platform applications, including mobile. It uses OpenGL ES 2.0 for rendering. KivyMD is an extension providing Material Design widgets.

**Native feel:** Poor on desktop. Kivy was designed for touch/mobile interfaces. On desktop, it feels like a mobile app running in a window. Scrollbars, right-click menus, keyboard shortcuts, and window management do not behave like desktop users expect. The UI uses a custom domain-specific language (KV language) for layout.

**Visual quality / Dark theme:** KivyMD provides Material Design dark themes: `self.theme_cls.theme_style = "Dark"`. Looks modern but mobile-oriented. The aesthetic is "Android app on desktop."

**Knowledge graph rendering:** Kivy's Canvas (OpenGL-based) is powerful for custom 2D rendering but there is no pre-built node graph widget. You would need to build one from scratch using Kivy's graphics instructions (Line, Ellipse, Color, etc.) and touch event handling. Kivy's touch-first model actually works well for drag-and-drop graphs, but the development effort is significant.

**Streaming text:** Kivy Labels and TextInput widgets can be updated programmatically. Works but not as smooth as Qt or web-based solutions.

**Async support:** Kivy has its own event loop based on Twisted. Integrating with asyncio requires `asyncio.ensure_future()` and careful coordination. The `kivy-asyncio-integration` package exists but is not widely used. This is an awkward fit for Claude Agent SDK.

**Card layouts:** KivyMD provides `MDCard` widgets. Combine with `MDBoxLayout` for horizontal arrangement. Adequate.

**Search/filter:** Manual implementation with TextInput and RecycleView. No built-in proxy filtering.

**Installation:** Package with PyInstaller or Buildozer. Bundle size is moderate (~50-80 MB).

**Community/maturity:** Kivy is mature (since 2011) but its community has been declining as developers shift to Flutter, Qt, and web-based frameworks. KivyMD is actively maintained but has a smaller contributor base. Kivy is best for mobile/touch apps, not desktop applications.

**Honest downsides:**
- Looks and feels like a mobile app on desktop
- Custom KV language adds learning overhead
- Async integration is awkward
- Declining community for desktop use cases
- No native desktop conventions (right-click menus, keyboard shortcuts, etc.)
- OpenGL dependency can cause issues on some Windows systems

**Verdict:** Kivy is designed for mobile-first applications. It is **not a good fit** for a desktop worldbuilding tool.

---

## Scoring Matrix

Scale: 1 (poor) to 5 (excellent)

| Criterion | PySide6 | Dear PyGui | NiceGUI Native | Flet | Electron+Python | Tauri+Python | CustomTkinter | Kivy |
|---|---|---|---|---|---|---|---|---|
| **1. Native feel** | 5 | 4 | 3 | 4 | 4 | 3 | 3 | 2 |
| **2. Visual quality** | 5 | 4 | 5 | 4 | 5 | 5 | 3 | 3 |
| **3. Knowledge graph** | 5 | 5 | 4* | 2 | 5* | 4* | 1 | 2 |
| **4. Streaming text** | 5 | 4 | 5 | 4 | 5 | 5 | 3 | 3 |
| **5. Async support** | 4 | 4 | 5 | 4 | 3 | 3 | 2 | 2 |
| **6. Card layouts** | 5 | 3 | 5 | 5 | 5 | 5 | 3 | 4 |
| **7. Search/filter** | 5 | 3 | 4 | 4 | 5 | 5 | 3 | 3 |
| **8. Install simplicity** | 4 | 4 | 2 | 3 | 5 | 3 | 4 | 3 |
| **9. Bundle size** | 3 | 4 | 3 | 3 | 1 | 3 | 5 | 3 |
| **10. Community/maturity** | 5 | 3 | 3 | 3 | 5 | 2 | 3 | 3 |
| **11. Real-world apps** | 5 | 3 | 2 | 2 | 5 | 2 | 2 | 3 |
| **12. Python integration** | 5 | 5 | 5 | 5 | 2 | 2 | 5 | 5 |
| **TOTAL** | **56** | **46** | **46** | **43** | **50** | **42** | **37** | **36** |

*Note: Scores marked with * for knowledge graph use web-based JS libraries (Cytoscape.js, D3.js, etc.), which are excellent but require web rendering.*

### Weighted Scores (priorities for THIS project)

Weighting: Knowledge graph (x3), Async support (x3), Visual quality (x2), Native feel (x2), Python integration (x2), Install simplicity (x2), others (x1).

| Framework | Weighted Total |
|---|---|
| **PySide6** | **97** |
| **Dear PyGui** | **79** |
| **NiceGUI Native** | **77** |
| **Electron+Python** | **76** |
| **Flet** | **67** |
| **Tauri+Python** | **64** |
| **CustomTkinter** | **55** |
| **Kivy** | **50** |

---

## Top 3 Recommendations

### Recommendation #1: PySide6 (Qt)

**Why it wins:**
- The ONLY framework with multiple production-ready, native interactive node graph libraries (SpatialNode, NodeGraphQt-PySide6, OdenGraphQt, qtpynodeeditor)
- Mature async integration via qasync that works with networking libraries (critical for Claude Agent SDK)
- One-line dark theme setup with qdarktheme
- The most mature Python desktop framework, backed by The Qt Company
- Direct Python integration -- your 10 engine modules just work
- Real-world proof: VLC, Calibre, Anki, Spyder, QGIS, FreeCAD all use Qt
- Professional installation path with PyInstaller + InstallForge
- LGPL licensed -- free for any use

**Why it might concern you:**
- Steeper learning curve than Flet or NiceGUI
- QSS styling is less flexible than CSS
- Qt documentation can be verbose and C++-oriented (though PySide6-specific docs are improving)
- Bundle size of ~80-120 MB (not the smallest, but reasonable)

**Bottom line:** PySide6 is the only framework that checks every box. It handles knowledge graphs natively, integrates with asyncio via qasync, looks professional with minimal effort, and has a 25+ year track record. The learning curve is the main cost, but it pays dividends in capability.

---

### Recommendation #2: Dear PyGui

**Why it is a strong second:**
- Built-in node editor is PERFECT for knowledge graphs -- no third-party library needed
- GPU-accelerated rendering means smooth performance even with complex UIs
- Dark theme is the default aesthetic
- Async integration works via custom render loop + dearpygui-async
- MIT licensed
- Smaller bundle size than PySide6
- The "game engine editor" look is actually a great fit for a worldbuilding tool

**Why it is #2 and not #1:**
- Smaller community and ecosystem
- No visual designer tool
- Limited text rendering (no rich text/HTML)
- The card layout and search/filter capabilities are less polished than Qt
- Less mature accessibility support
- Fewer third-party resources and tutorials
- If you need a feature that does not exist, you are on your own

**Bottom line:** If the node graph / knowledge graph is the absolute centerpiece of your application and you want it to feel like a creative tool (Blender, Unity), Dear PyGui is an excellent choice. The trade-off is a smaller ecosystem and less flexibility for traditional UI patterns (rich text, complex form layouts).

---

### Recommendation #3: Flet (with reservations)

**Why it makes the list:**
- Easiest to learn for a Python developer
- Beautiful Material Design dark theme out of the box
- Good async support
- Card layouts and basic UI elements are very easy to build
- Cross-platform by default

**Why it has serious reservations:**
- **No knowledge graph solution** -- you would need to build a custom node graph from scratch using Canvas primitives. This is weeks or months of work.
- Pre-1.0 with potential API changes
- Building for Windows requires Visual Studio 2022 C++ workload
- The "mobile app on desktop" aesthetic may not suit a worldbuilding tool

**Bottom line:** Flet would be the recommendation for a simpler application. The lack of a knowledge graph widget is a deal-breaker for this specific project unless you are willing to invest significant time building one from scratch.

---

## Recommendation #1 Deep Dive: Code Examples

### PySide6 Dark Theme Setup

```python
import sys
import qdarktheme
from PySide6.QtWidgets import QApplication, QMainWindow

class WorldbuildingApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Worldbuilding Interactive Program")
        self.setMinimumSize(1400, 900)

if __name__ == "__main__":
    app = QApplication(sys.argv)

    # One line for a professional dark theme
    qdarktheme.setup_theme(
        theme="dark",
        custom_colors={
            "[dark]": {
                "primary": "#8B5CF6",          # Purple accent
                "background": "#1a1a2e",       # Deep navy background
                "border": "#2d2d44",
            }
        }
    )

    window = WorldbuildingApp()
    window.show()
    sys.exit(app.exec())
```

### Interactive Knowledge Graph with QGraphicsView

```python
from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsEllipseItem,
    QGraphicsTextItem, QGraphicsLineItem, QGraphicsItem
)
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QBrush, QPen, QColor, QFont


class KnowledgeNode(QGraphicsEllipseItem):
    """A draggable, clickable node in the knowledge graph."""

    def __init__(self, name: str, category: str, x: float, y: float):
        super().__init__(-40, -40, 80, 80)
        self.setPos(x, y)
        self.name = name
        self.category = category
        self.edges = []

        # Visual style
        colors = {
            "character": QColor("#8B5CF6"),
            "location": QColor("#10B981"),
            "event": QColor("#F59E0B"),
            "faction": QColor("#EF4444"),
        }
        color = colors.get(category, QColor("#6B7280"))
        self.setBrush(QBrush(color))
        self.setPen(QPen(color.lighter(150), 2))

        # Label
        label = QGraphicsTextItem(name, self)
        label.setDefaultTextColor(QColor("white"))
        label.setFont(QFont("Segoe UI", 9, QFont.Bold))
        # Center the label
        rect = label.boundingRect()
        label.setPos(-rect.width() / 2, -rect.height() / 2)

        # Make draggable and selectable
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        self.setCacheMode(QGraphicsItem.DeviceCoordinateCache)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            for edge in self.edges:
                edge.update_position()
        return super().itemChange(change, value)


class KnowledgeEdge(QGraphicsLineItem):
    """An edge connecting two knowledge nodes."""

    def __init__(self, source: KnowledgeNode, target: KnowledgeNode,
                 relationship: str):
        super().__init__()
        self.source = source
        self.target = target
        self.relationship = relationship
        self.setPen(QPen(QColor("#4B5563"), 2))

        source.edges.append(self)
        target.edges.append(self)
        self.update_position()

    def update_position(self):
        self.setLine(
            self.source.pos().x(), self.source.pos().y(),
            self.target.pos().x(), self.target.pos().y()
        )


class KnowledgeGraphView(QGraphicsView):
    """Interactive knowledge graph with zoom and pan."""

    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        self.setRenderHints(
            self.renderHints()
            # Enable antialiasing for smooth edges
        )
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)

        # Dark background
        self.setStyleSheet("background-color: #0f0f23; border: none;")

    def add_node(self, name, category, x, y):
        node = KnowledgeNode(name, category, x, y)
        self.scene.addItem(node)
        return node

    def add_edge(self, source, target, relationship="related"):
        edge = KnowledgeEdge(source, target, relationship)
        self.scene.addItem(edge)
        return edge

    def wheelEvent(self, event):
        """Zoom with mouse wheel."""
        factor = 1.15
        if event.angleDelta().y() > 0:
            self.scale(factor, factor)
        else:
            self.scale(1 / factor, 1 / factor)
```

### Option Comparison Cards (Side-by-Side)

```python
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QFrame, QScrollArea
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


class ComparisonCard(QFrame):
    """A single option card for side-by-side comparison."""

    def __init__(self, title: str, description: str,
                 pros: list[str], cons: list[str],
                 score: float, selected: bool = False):
        super().__init__()
        self.setObjectName("comparisonCard")
        self.setStyleSheet("""
            #comparisonCard {
                background-color: #1e1e3a;
                border: 2px solid #2d2d44;
                border-radius: 12px;
                padding: 16px;
            }
            #comparisonCard:hover {
                border-color: #8B5CF6;
            }
            #comparisonCard[selected="true"] {
                border-color: #8B5CF6;
                background-color: #252547;
            }
        """)
        if selected:
            self.setProperty("selected", "true")

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Title
        title_label = QLabel(title)
        title_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        title_label.setStyleSheet("color: white;")
        layout.addWidget(title_label)

        # Description
        desc_label = QLabel(description)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #9CA3AF; font-size: 12px;")
        layout.addWidget(desc_label)

        # Score badge
        score_label = QLabel(f"Score: {score:.1f}/10")
        score_label.setStyleSheet("""
            background-color: #8B5CF6;
            color: white;
            padding: 4px 12px;
            border-radius: 8px;
            font-weight: bold;
        """)
        score_label.setFixedWidth(120)
        score_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(score_label)

        # Pros
        pros_header = QLabel("Strengths")
        pros_header.setStyleSheet(
            "color: #10B981; font-weight: bold; font-size: 12px;"
        )
        layout.addWidget(pros_header)
        for pro in pros:
            pro_label = QLabel(f"  + {pro}")
            pro_label.setStyleSheet("color: #6EE7B7; font-size: 11px;")
            pro_label.setWordWrap(True)
            layout.addWidget(pro_label)

        # Cons
        cons_header = QLabel("Weaknesses")
        cons_header.setStyleSheet(
            "color: #EF4444; font-weight: bold; font-size: 12px;"
        )
        layout.addWidget(cons_header)
        for con in cons:
            con_label = QLabel(f"  - {con}")
            con_label.setStyleSheet("color: #FCA5A5; font-size: 11px;")
            con_label.setWordWrap(True)
            layout.addWidget(con_label)

        layout.addStretch()


class ComparisonPanel(QScrollArea):
    """Panel showing 2-4 comparison cards side by side."""

    def __init__(self, options: list[dict]):
        super().__init__()
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet("background: transparent; border: none;")

        container = QWidget()
        h_layout = QHBoxLayout(container)
        h_layout.setSpacing(16)
        h_layout.setContentsMargins(16, 16, 16, 16)

        for i, opt in enumerate(options):
            card = ComparisonCard(
                title=opt["title"],
                description=opt["description"],
                pros=opt["pros"],
                cons=opt["cons"],
                score=opt["score"],
                selected=(i == 0),
            )
            h_layout.addWidget(card)

        self.setWidget(container)
```

### Streaming Chat Panel (for Claude Responses)

```python
import asyncio
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTextEdit, QLineEdit, QPushButton, QHBoxLayout
)
from PySide6.QtCore import Signal, QObject, Qt
from PySide6.QtGui import QFont, QTextCursor


class StreamSignals(QObject):
    """Signals for thread-safe UI updates from async code."""
    text_chunk = Signal(str)
    stream_finished = Signal()


class StreamingChatPanel(QWidget):
    """Chat panel that displays Claude's streaming responses."""

    def __init__(self):
        super().__init__()
        self.signals = StreamSignals()
        self.signals.text_chunk.connect(self._append_chunk)
        self.signals.stream_finished.connect(self._on_stream_finished)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Chat display
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setFont(QFont("Segoe UI", 11))
        self.chat_display.setStyleSheet("""
            QTextEdit {
                background-color: #12122a;
                color: #E5E7EB;
                border: none;
                padding: 16px;
                selection-background-color: #8B5CF6;
            }
        """)
        layout.addWidget(self.chat_display)

        # Input area
        input_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText(
            "Ask about your world..."
        )
        self.input_field.setFont(QFont("Segoe UI", 11))
        self.input_field.setStyleSheet("""
            QLineEdit {
                background-color: #1e1e3a;
                color: white;
                border: 2px solid #2d2d44;
                border-radius: 8px;
                padding: 10px 16px;
            }
            QLineEdit:focus {
                border-color: #8B5CF6;
            }
        """)
        self.input_field.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.input_field)

        self.send_btn = QPushButton("Send")
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #8B5CF6;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 24px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #7C3AED;
            }
            QPushButton:disabled {
                background-color: #4B5563;
            }
        """)
        self.send_btn.clicked.connect(self.send_message)
        input_layout.addWidget(self.send_btn)

        layout.addLayout(input_layout)

    def send_message(self):
        text = self.input_field.text().strip()
        if not text:
            return
        self.input_field.clear()
        self.input_field.setEnabled(False)
        self.send_btn.setEnabled(False)

        # Display user message
        self.chat_display.append(
            f'<p style="color: #8B5CF6; font-weight: bold;">You:</p>'
            f'<p style="color: #E5E7EB;">{text}</p>'
        )
        self.chat_display.append(
            '<p style="color: #8B5CF6; font-weight: bold;">Claude:</p>'
        )

        # Start async streaming (called from qasync event loop)
        asyncio.ensure_future(self._stream_response(text))

    async def _stream_response(self, prompt: str):
        """Stream Claude's response using the Agent SDK."""
        try:
            # Import and use Claude Agent SDK
            from claude_agent_sdk import query, ClaudeAgentOptions

            options = ClaudeAgentOptions(
                system_prompt="You are a worldbuilding assistant.",
                permission_mode="acceptEdits",
            )

            async for message in query(
                prompt=prompt,
                options=options,
            ):
                if hasattr(message, 'content'):
                    for block in message.content:
                        if hasattr(block, 'text'):
                            # Emit signal for thread-safe UI update
                            self.signals.text_chunk.emit(block.text)

        except Exception as e:
            self.signals.text_chunk.emit(f"\n[Error: {e}]")
        finally:
            self.signals.stream_finished.emit()

    def _append_chunk(self, text: str):
        """Append a text chunk to the chat display (main thread)."""
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text)
        self.chat_display.setTextCursor(cursor)
        self.chat_display.ensureCursorVisible()

    def _on_stream_finished(self):
        """Re-enable input after streaming completes."""
        self.chat_display.append("")  # Add spacing
        self.input_field.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.input_field.setFocus()
```

### Main Application with qasync

```python
import sys
import asyncio
import qdarktheme
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QSplitter, QTabWidget,
    QDockWidget, QStatusBar
)
from PySide6.QtCore import Qt
from qasync import QEventLoop

# Import your custom panels (from examples above)
# from knowledge_graph import KnowledgeGraphView
# from comparison_cards import ComparisonPanel
# from streaming_chat import StreamingChatPanel
# from entity_browser import EntityBrowser
# from progression_tracker import ProgressionTracker


class WorldbuildingApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Worldbuilding Interactive Program")
        self.setMinimumSize(1400, 900)

        # Central widget: Knowledge Graph
        self.graph_view = KnowledgeGraphView()
        self.setCentralWidget(self.graph_view)

        # Right dock: Chat panel
        chat_dock = QDockWidget("Claude Assistant", self)
        chat_dock.setWidget(StreamingChatPanel())
        self.addDockWidget(Qt.RightDockWidgetArea, chat_dock)

        # Left dock: Entity browser + Progression
        left_tabs = QTabWidget()
        left_tabs.addTab(EntityBrowser(), "Entities")
        left_tabs.addTab(ProgressionTracker(), "Progress")

        left_dock = QDockWidget("World Explorer", self)
        left_dock.setWidget(left_tabs)
        self.addDockWidget(Qt.LeftDockWidgetArea, left_dock)

        # Bottom dock: Comparison cards
        compare_dock = QDockWidget("Compare Options", self)
        compare_dock.setWidget(ComparisonPanel([]))
        self.addDockWidget(Qt.BottomDockWidgetArea, compare_dock)

        # Status bar
        self.statusBar().showMessage("Ready -- World: Untitled")


async def main():
    app = QApplication(sys.argv)
    qdarktheme.setup_theme("dark", custom_colors={
        "[dark]": {
            "primary": "#8B5CF6",
            "background": "#1a1a2e",
        }
    })

    window = WorldbuildingApp()
    window.show()

    # Keep the event loop running
    while True:
        await asyncio.sleep(0.01)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    qdarktheme.setup_theme("dark")
    window = WorldbuildingApp()
    window.show()

    with loop:
        loop.run_forever()
```

### Entity Browser with Search

```python
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLineEdit, QTreeView, QHeaderView
)
from PySide6.QtCore import (
    Qt, QSortFilterProxyModel, QAbstractItemModel,
    QModelIndex
)
from PySide6.QtGui import QStandardItemModel, QStandardItem, QFont, QColor


class EntityBrowser(QWidget):
    """Searchable, filterable entity browser."""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Search bar
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search entities...")
        self.search.setStyleSheet("""
            QLineEdit {
                background-color: #1e1e3a;
                color: white;
                border: 1px solid #2d2d44;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #8B5CF6;
            }
        """)
        layout.addWidget(self.search)

        # Entity model
        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(
            ["Name", "Type", "Status"]
        )

        # Proxy model for filtering
        self.proxy = QSortFilterProxyModel()
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterCaseSensitivity(
            Qt.CaseInsensitive
        )
        self.proxy.setRecursiveFilteringEnabled(True)
        self.proxy.setFilterKeyColumn(-1)  # Search all columns

        # Connect search to filter
        self.search.textChanged.connect(
            self.proxy.setFilterFixedString
        )

        # Tree view
        self.tree = QTreeView()
        self.tree.setModel(self.proxy)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSortingEnabled(True)
        self.tree.setStyleSheet("""
            QTreeView {
                background-color: #12122a;
                color: #E5E7EB;
                border: none;
                font-size: 12px;
            }
            QTreeView::item:selected {
                background-color: #8B5CF6;
            }
            QTreeView::item:hover {
                background-color: #252547;
            }
            QHeaderView::section {
                background-color: #1e1e3a;
                color: #9CA3AF;
                border: 1px solid #2d2d44;
                padding: 6px;
                font-weight: bold;
            }
        """)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        layout.addWidget(self.tree)

    def add_entity(self, name: str, entity_type: str,
                   status: str = "Draft"):
        """Add an entity to the browser."""
        type_colors = {
            "Character": QColor("#8B5CF6"),
            "Location": QColor("#10B981"),
            "Event": QColor("#F59E0B"),
            "Faction": QColor("#EF4444"),
            "Item": QColor("#3B82F6"),
        }
        name_item = QStandardItem(name)
        name_item.setForeground(
            type_colors.get(entity_type, QColor("#E5E7EB"))
        )
        type_item = QStandardItem(entity_type)
        status_item = QStandardItem(status)
        self.model.appendRow([name_item, type_item, status_item])
```

---

## Honest Trade-offs Summary

### PySide6 (Recommended)
| Advantage | Trade-off |
|---|---|
| Best knowledge graph ecosystem | Steeper learning curve than Flet/NiceGUI |
| 25+ years of Qt maturity | QSS is less expressive than CSS |
| LGPL -- free for any use | Bundle size ~80-120 MB |
| Direct Python integration | C++-oriented documentation can be frustrating |
| Industrial-strength widgets | More boilerplate than web-based frameworks |
| qasync works with Claude Agent SDK | qasync is third-party (not built into Qt) |

### Dear PyGui (Strong Alternative)
| Advantage | Trade-off |
|---|---|
| Built-in node editor | Smaller ecosystem -- fewer resources/tutorials |
| GPU-accelerated | No rich text / HTML rendering |
| Dark theme by default | No visual designer tool |
| Smaller bundle size | Less flexible layout system |
| MIT licensed | "Game engine" aesthetic may not suit all audiences |

### What Would Actually Happen If You Chose Each Option
- **PySide6:** You would spend 1-2 weeks learning Qt's widget system and signals/slots. After that, you would have a framework that can handle any UI requirement you throw at it for the lifetime of the project. You would never hit a wall.
- **Dear PyGui:** You would be productive in days. The node editor works immediately. But you might hit walls with rich text rendering for Claude responses or complex form layouts.
- **Flet:** You would be productive in hours for basic UI. Then you would spend weeks trying to build an interactive knowledge graph from scratch on Canvas. You might give up and embed a web view, at which point you should have just used NiceGUI.
- **NiceGUI:** You would build a beautiful UI quickly. Then you would spend days fighting pywebview packaging issues. Your users might report that the app does not load on their machines.
- **Electron:** You would build two applications (React + Python) and spend more time on the bridge between them than on actual features.
- **CustomTkinter / Kivy:** You would hit fundamental limitations within the first week and need to switch frameworks.

---

## Sources

### PySide6 / Qt
- [PyQtDarkTheme](https://github.com/5yutan5/PyQtDarkTheme) -- Flat dark theme for PySide/PyQt
- [Qt-Material](https://pypi.org/project/qt-material/) -- Material Design stylesheet
- [QtModernRedux](https://github.com/robertkist/qtmodernredux) -- Modern frameless window theme
- [Qt NetworkX Viewer Example](https://doc.qt.io/qtforpython-6/examples/example_external_networkx.html) -- Official graph visualization example
- [QGraphicsView Tutorial](https://www.pythonguis.com/tutorials/pyside6-qgraphics-vector-graphics/) -- Graphics framework tutorial
- [SpatialNode](https://github.com/SpatialGraphics/SpatialNode) -- Qt node editor framework for PySide6
- [NodeGraphQt-PySide6](https://github.com/C3RV1/NodeGraphQt-PySide6) -- Node graph framework for PySide6
- [OdenGraphQt](https://pypi.org/project/OdenGraphQt/) -- Node graph framework for PySide6/PyQt6
- [qtpynodeeditor](https://pypi.org/project/qtpynodeeditor/) -- Python port of NodeEditor
- [qtPyGraphEdit](https://github.com/ghillebrand/qtPyGraphEdit) -- Node-edge graph editor for PySide6
- [Qt Elastic Nodes Example](https://doc.qt.io/qtforpython-6/examples/example_widgets_graphicsview_elasticnodes.html) -- Physics-based node example
- [qasync](https://pypi.org/project/qasync/) -- asyncio integration for Qt
- [PySide6.QtAsyncio](https://doc.qt.io/qtforpython-6/PySide6/QtAsyncio/index.html) -- Official async module (limited networking)
- [PySide6 vs PyQt6](https://www.pythonguis.com/faq/pyqt6-vs-pyside6/) -- Licensing comparison
- [PySide6 Tutorial 2026](https://www.pythonguis.com/pyside6-tutorial/) -- Complete tutorial
- [PyInstaller PySide6 Packaging](https://www.pythonguis.com/tutorials/packaging-pyside6-applications-windows-pyinstaller-installforge/) -- Windows packaging guide
- [Which Python GUI Library 2026](https://www.pythonguis.com/faq/which-python-gui-library/) -- Framework comparison

### Dear PyGui
- [Dear PyGui Node Editor](https://dearpygui.readthedocs.io/en/latest/documentation/node-editor.html) -- Built-in node editor docs
- [Dear PyGui GitHub](https://github.com/hoffstadt/DearPyGui) -- Main repository
- [Dear PyGui Showcase](https://github.com/hoffstadt/DearPyGui/wiki/DEAR-PYGUI-SHOWCASE) -- Real-world projects
- [dearpygui-async](https://pypi.org/project/dearpygui-async/) -- Async helper package
- [Dear PyGui Themes](https://dearpygui.readthedocs.io/en/latest/documentation/themes.html) -- Theming documentation

### NiceGUI / pywebview
- [NiceGUI Native Mode](https://deepwiki.com/zauberzeug/nicegui/6.2-native-mode) -- Architecture documentation
- [NiceGUI PyPI](https://pypi.org/project/nicegui/) -- Latest release
- [pywebview GitHub](https://github.com/r0x0r/pywebview) -- Main repository
- [NiceGUI Hacker News Discussion](https://news.ycombinator.com/item?id=35386990) -- Community feedback

### Flet
- [Flet Official Site](https://flet.dev/) -- Framework homepage
- [Flet Canvas](https://flet.dev/blog/canvas/) -- Canvas drawing documentation
- [Flet Charts](https://flet.dev/docs/controls/charts/) -- Chart controls
- [Flet Windows Packaging](https://flet.dev/docs/publish/windows/) -- Windows distribution
- [Flet Bundle Size Issue](https://github.com/flet-dev/flet/issues/4620) -- Size reduction discussion

### Electron
- [Electron Python Example](https://github.com/fyears/electron-python-example) -- Architecture example
- [Electron Performance](https://www.electronjs.org/docs/latest/tutorial/performance) -- Official optimization guide
- [Electron Memory Overhead](https://seenaburns.com/debugging-electron-memory-usage/) -- Memory analysis
- [Electron vs Qt Memory](https://pkoretic.medium.com/quick-look-electron-vs-qt-qml-app-memory-usage-e8769008534f) -- Comparison

### Tauri + Python
- [PyTauri GitHub](https://github.com/pytauri/pytauri) -- Tauri binding for Python
- [tauri-plugin-python](https://github.com/marcomq/tauri-plugin-python) -- Tauri plugin for Python

### CustomTkinter
- [CustomTkinter GitHub](https://github.com/TomSchimansky/CustomTkinter) -- Main repository
- [TkNodeSystem](https://github.com/Akascape/TkNodeSystem) -- Experimental node system for Tkinter

### Kivy
- [KivyMD Theming](https://kivymd.readthedocs.io/en/latest/themes/theming/) -- Dark theme documentation
- [Kivy GitHub](https://github.com/kivy/kivy) -- Main repository

### General Comparisons
- [Best Python GUI Frameworks 2026](https://www.technource.com/blog/best-python-gui-frameworks-to-build-ai-applications/) -- AI application focus
- [Flet vs PySide6 Comparison](https://medium.com/@areejkam01/i-compared-pyside6-pyqt-kivy-flet-and-dearpygui-my-honest-2025-review-8c037118a777) -- Honest review
- [Modern Python GUIs 2026 Guide](https://eathealthy365.com/the-ultimate-guide-to-modern-python-gui-frameworks/) -- Definitive guide
- [Claude Agent SDK Python](https://platform.claude.com/docs/en/agent-sdk/python) -- SDK reference
- [Claude Agent SDK GitHub](https://github.com/anthropics/claude-agent-sdk-python) -- SDK repository
