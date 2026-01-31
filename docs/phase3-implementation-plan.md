# Phase 3 Implementation Plan: PySide6 Desktop Application

**9 sprints, ~14.5 weeks total**

## Architecture

```
+----------------------------------------------------------------+
|                    PySide6 Main Window                          |
|  +----------+  +---------------+  +----------+  +-----------+  |
|  | Entity   |  | Knowledge     |  | Chat &   |  | Progress  |  |
|  | Browser  |  | Graph View    |  | Stream   |  | Sidebar   |  |
|  | (Dock)   |  | (Central)     |  | (Dock)   |  | (Dock)    |  |
|  +----------+  +---------------+  +----------+  +-----------+  |
|  +------------------------------------------------------------+ |
|  |              Option Comparison Panel (Dock)                 | |
|  +------------------------------------------------------------+ |
+----------------------------------------------------------------+
          |                    |                    |
     Event Bus           State Store          Signal/Slot
          |                    |                    |
+----------------------------------------------------------------+
|                    Application Layer                            |
|  SessionManager | StepController | ContextBuilder | ClaudeClient|
+----------------------------------------------------------------+
          |                    |                    |
+----------------------------------------------------------------+
|                 Enforcement Pipeline                            |
|  L1:SystemPrompt | L2:ConstrainedDecoding | L3:StrictToolUse   |
|  L4:PydanticValidation | L5:UIGating | L6:DriftDetection       |
|  L7:Bookkeeping                                                |
+----------------------------------------------------------------+
          |                    |                    |
+----------------------------------------------------------------+
|                    Engine Layer (Phase 2)                       |
|  DataManager | WorldGraph | ChunkPuller | OptionGenerator | ...|
+----------------------------------------------------------------+
```

---

## Sprint Summary

| Sprint | Name | Focus |
|--------|------|-------|
| 0 | Engine Hardening | Fix 6 critical + 10 high audit issues, thread safety, atomic writes, missing tests |
| 1 | Pydantic Migration | Migrate jsonschema -> Pydantic v2 for all 85 templates |
| 2 | App Scaffolding | PySide6 project structure, main window, docks, dark theme, event bus |
| 3 | Core UI Panels | Entity browser, progress sidebar, knowledge graph, chat panel |
| 4 | Claude Integration | Agent SDK streaming, MCP tools, system prompts, context injection |
| 5 | Enforcement Layer | 7-layer validation pipeline, drift detection, retry logic |
| 6 | Option Flow & Entity Management | Option comparison, entity CRUD, step navigation, sessions |
| 7 | Polish & UX | Animations, error states, loading indicators, first-run, keyboard shortcuts |
| 8 | Packaging & Distribution | PyInstaller, Inno Setup installer, update checker |

---

## Sprint 0: Engine Hardening

**Goal:** Fix all critical/high audit issues. Make engine thread-safe for desktop app.

### Tasks
- **0.1** Create `engine/utils.py` -- extract `_safe_read_json`, `_safe_write_json`, `_clean_schema_for_validation` from 16+ copies across all modules/hooks (M1, C1)
- **0.2** Implement atomic file writes -- temp-file-then-`os.replace()` for all JSON/JSONL writes (C1)
- **0.3** Add threading locks -- `EngineManager` singleton with `threading.RLock` per module, SQLite `check_same_thread=False` (C2, M2). Files: create `engine/engine_manager.py`, modify all 10 modules
- **0.4** Fix OptionGenerator eager init -- lazy-loaded properties for 5 subsystems (C5)
- **0.5** Fix graph_builder O(n) scan -- in-memory reverse index instead of re-reading all files (C6)
- **0.6** Replace `except Exception: pass` with `logging.exception()` everywhere (H1)
- **0.7** Fix SQL injection in `sqlite_sync.py` `advanced_query()` -- whitelist approach (H2)
- **0.8** Fix consistency_checker stale entity cache -- add invalidation (H3)
- **0.9** Fix backup_manager: unbound `tmp_path`, restore deletes before extract (H4, H5)
- **0.10** Write tests for backup_manager + error_recovery (30+ tests) (C3, C4)
- **0.11** Fix remaining HIGH: public `log_event()` (H6), redundant build_graph (H7), inject_step save_state (H8), session number caching (H9), substring matching (H10)
- **0.12** Replace hardcoded PROJECT_ROOT in all 6 hooks (M5)

**Done when:** All 182 existing tests pass + 30 new tests, zero `except Exception: pass`, thread safety tests pass, atomic write tests pass

---

## Sprint 1: Pydantic Migration

**Goal:** Replace jsonschema with Pydantic v2. Enables Anthropic constrained decoding.

### Tasks
- **1.1** Design base models: `WorldEntity`, `EntityOption` with shared fields + custom validators. Files: `engine/models/base.py`
- **1.2** Generate Pydantic models from 85 JSON schemas, one module per entity type. Files: `engine/models/entities/`
- **1.3** Add worldbuilding validators: name uniqueness, cross-ref validation, range checks, canon claim extraction
- **1.4** Migrate DataManager to `model_validate()` instead of `jsonschema.validate()`
- **1.5** Migrate ConsistencyChecker Layer 1 to Pydantic
- **1.6** Migrate ErrorRecoveryManager to Pydantic
- **1.7** Remove jsonschema dependency, add pydantic>=2.0

**Done when:** All entity types have Pydantic models, `model_json_schema()` matches originals, jsonschema no longer imported, 40+ new model tests

**Depends on:** Sprint 0

---

## Sprint 2: App Scaffolding

**Goal:** PySide6 app launches with themed window and empty dock panels.

### Tasks
- **2.1** Create project structure under `app/` (panels/, widgets/, models/, services/, theme/, resources/)
- **2.2** MainWindow with 4 QDockWidgets, view menu, layout save/restore via QSettings
- **2.3** Dark theme via qt-material (`dark_teal.xml`) + custom QSS overrides
- **2.4** EventBus singleton: entity_selected, entity_created, step_changed, generation_started/finished, claude_token, error_occurred
- **2.5** StateStore wrapping state.json with auto-save, change signals, thread safety
- **2.6** Entry point: QApplication, theme, EngineManager init, shutdown sequence, exception hook

**Done when:** `python -m app.main` shows themed window with 4 docks, layout persists across restarts

**Depends on:** Sprint 0

---

## Sprint 3: Core UI Panels

**Goal:** All 4 panels display real data from the engine.

### Tasks
- **3.1** Entity Browser: QSortFilterProxyModel, search/filter, type/status dropdown, custom delegate, right-click menu
- **3.2** Progress Sidebar: 52 steps with phase grouping, lock/active/complete icons, click to navigate, completion percentages
- **3.3** Knowledge Graph: custom QGraphicsView with EntityNode, RelationshipEdge, zoom/pan, NetworkX layout, click-to-select, hover tooltips, type filtering
- **3.4** Chat Panel (basic): message bubbles, markdown rendering, streaming simulation (mock), typing indicator
- **3.5** Wire all panels to EventBus + engine: entity selection syncs across panels, step changes update data

**Done when:** All panels show live data, cross-panel selection works, graph renders 100 nodes in <1s

**Depends on:** Sprint 0, Sprint 2

---

## Sprint 4: Claude Integration

**Goal:** Chat panel streams real Claude responses. Custom tools expose engine to Claude.

### Tasks
- **4.1** AgentWorker (QThread): async bridge to Agent SDK, token_received/tool_call/finished/error signals, cancellation support
- **4.2** SubprocessWorker fallback: `claude -p --output-format stream-json`, same signal interface (Windows SDK hang mitigation)
- **4.3** ClaudeClient facade: SDK-first → subprocess fallback → offline mode, auth checking, status reporting
- **4.4** MCP tools: get_canon_context, generate_options, validate_entity, query_knowledge_graph, get_step_guidance, search_entities
- **4.5** PromptBuilder: step-specific system prompts with role, constraints, anti-drift instructions, versioned templates
- **4.6** ContextBuilder: three-layer guidance injection, knowledge graph neighbors, recent decisions, token budget management
- **4.7** Wire streaming to chat panel with tool call display, error handling, stop button

**Done when:** Real Claude streaming works, MCP tools callable, subprocess fallback works, offline mode functions

**Depends on:** Sprint 1, Sprint 2, Sprint 3

---

## Sprint 5: Enforcement Layer

**Goal:** 7-layer validation pipeline between Claude output and world data.

### Tasks
- **5.1** ValidationPipeline: Pydantic schema → canon cross-refs → range checks → enum checks → drift detection → structured ValidationResult
- **5.2** DriftDetector: format drift (no tool_use), topic drift (future steps), canon drift (non-existent entities), scope drift
- **5.3** RetryManager: retry with Pydantic error feedback, escalating constraints, max 3 attempts, fallback to manual entry
- **5.4** Wire validation to option generation: generate → validate each option → display valid ones → retry if all fail
- **5.5** Wire validation to entity save: form data → full pipeline → save or show errors with field highlighting
- **5.6** Bookkeeping integration: log llm_call_made, validation_passed/failed, drift_detected, retry_attempted, user_decision events

**Done when:** All Claude output validated before display, drift detected and retried, manual fallback works, all events logged

**Depends on:** Sprint 1, Sprint 4

---

## Sprint 6: Option Flow & Entity Management

**Goal:** Complete user workflow: generate → compare → select → save → advance.

### Tasks
- **6.1** Option Comparison Panel: 2-4 cards side-by-side, select/combine/regenerate/custom buttons, validation badges
- **6.2** Entity Detail View: form with all fields, per-field validation indicators, revision history, status toggle, related entities
- **6.3** Step Navigation: guided workflow per step, completion checking, step advancement gating, "Advance" button
- **6.4** Session Management: engine init on launch, auto-save every 5 min, crash recovery, backup on session start
- **6.5** Relationship editing: add connections in detail view, drag-to-connect in graph, validated relationship types

**Done when:** Full step workflow works end-to-end, sessions auto-save and recover, relationships editable

**Depends on:** Sprint 3, 4, 5

---

## Sprint 7: Polish & UX

**Goal:** Professional, welcoming experience for non-technical users.

### Tasks
- **7.1** Loading indicators: skeleton states, progress bars, spinning indicators, disabled buttons during operations
- **7.2** Error states: toast notifications, error dialogs with recovery options, field-level validation display
- **7.3** Animations: card slide-in, step transitions, node appearance, smooth scroll, QPropertyAnimation
- **7.4** First-run experience: welcome dialog, prerequisite detection (Claude CLI, Node.js), initial setup, interactive tour
- **7.5** Responsive layout: min window 1024x768, graceful dock resizing, high-DPI support
- **7.6** Keyboard shortcuts: Ctrl+G generate, Ctrl+S save, Ctrl+F search, Esc cancel, tab order

**Done when:** No raw errors visible, loading states everywhere, first-run guides new users, 1024x768 works

**Depends on:** Sprint 6

---

## Sprint 8: Packaging & Distribution

**Goal:** Standalone Windows .exe installer.

### Tasks
- **8.1** PyInstaller spec: --onedir, data files, Qt module exclusions, hidden imports, UPX compression
- **8.2** Frozen-app paths: sys._MEIPASS detection, platformdirs for user data, first-run data copy
- **8.3** Bundle optimization: PySide6-Essentials, cleanup script, target <50 MB installer
- **8.4** Inno Setup script: LZMA2, per-user install, shortcuts, uninstaller, modern wizard
- **8.5** Prerequisite detection in installer/first-run
- **8.6** Build automation script: venv → install → test → build → cleanup → installer
- **8.7** Update checker: GitHub Releases API, non-intrusive notification bar

**Done when:** `build_release.py` produces working installer, installs without admin, data persists across updates

**Depends on:** All previous sprints

---

## Key Libraries
```
pydantic>=2.0
PySide6-Essentials>=6.7.0
qt-material>=2.14
qtawesome>=1.3.0
networkx>=3.0
claude-agent-sdk>=0.1.26
qasync>=0.27.0
platformdirs>=4.0
pyinstaller>=6.18.0  (dev)
pytest pytest-qt      (dev)
```

## Risk Mitigations
- **SDK Windows hang**: Subprocess fallback (Sprint 4.2)
- **SDK API changes**: Pin version, adapter in ClaudeClient
- **Graph performance 500+ nodes**: LOD rendering, viewport culling
- **PyInstaller antivirus false positives**: --onedir mode, eventual code signing
- **Data loss on upgrade**: Separate app/data dirs, migration scripts, auto-backup

## Verification
- All existing 182 tests pass after every sprint
- Each sprint adds its own tests (target 80% coverage)
- pytest-qt for UI widget testing
- MockClaudeClient for all Claude-dependent tests
- Full build pipeline tested at Sprint 8
