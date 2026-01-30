# Worldbuilding Interactive Program -- Comprehensive Project Audit

**Generated:** 2026-01-30
**Scope:** Full codebase audit of all engine modules, hooks, templates, configuration, and data structures.

---

## Table of Contents

1. [Complete Module Inventory](#1-complete-module-inventory)
2. [Data Flow Map](#2-data-flow-map)
3. [Integration Points](#3-integration-points)
4. [File I/O Map](#4-file-io-map)
5. [External Dependencies](#5-external-dependencies)
6. [Hook Architecture](#6-hook-architecture)
7. [State Management](#7-state-management)
8. [What a UI Needs to Do](#8-what-a-ui-needs-to-do)

---

## 1. Complete Module Inventory

### 1.1 Engine Modules (10 files, `engine/`)

| Module | Class | Lines | Purpose | External Deps |
|---|---|---|---|---|
| `data_manager.py` | `DataManager` | ~1838 | Entity CRUD, schema validation, ID generation, canon claims extraction, prose generation (14 entity-specific builders + generic fallback) | `jsonschema` |
| `bookkeeper.py` | `BookkeepingManager` | ~834 | Event-sourced decision/session tracking. Append-only JSONL events as source of truth, derived JSON indexes, Markdown session summaries | None (stdlib) |
| `graph_builder.py` | `WorldGraph` | ~671 | NetworkX in-memory directed knowledge graph. Neighbor queries, path finding, community detection, orphan detection | `networkx` |
| `chunk_puller.py` | `ChunkPuller` | ~1313 | Three-layer guidance generator: (1) book quotes from source-text.txt, (2) reference DB extracts with fair rotation, (3) actionable template/field info. Contains hardcoded step dependencies and guided questions for all 52 steps | None (stdlib) |
| `fair_representation.py` | `FairRepresentationManager` | ~253 | Balanced rotation of 16 reference databases (10 mythologies + 6 authors). Selects 4 mythologies + 3 authors per step by lowest usage count | None (stdlib) |
| `option_generator.py` | `OptionGenerator` | ~1036 | Divergent-convergent option pipeline. Assembles context for Claude (does NOT call LLM itself). 8 raw ideas -> filter to 2-4 options with anti-repetition, canon consistency, diversity scoring. Tracks option history and concept bank | None (stdlib) |
| `sqlite_sync.py` | `SQLiteSyncEngine` | ~803 | JSON-to-SQLite mirror with FTS5 full-text search. Tables: entities, cross_references, canon_claims, entity_search | None (stdlib sqlite3) |
| `consistency_checker.py` | `ConsistencyChecker` | ~1444 | Three-layer validation: Layer 1 (JSON Schema via jsonschema), Layer 2 (rule-based cross-reference checks), Layer 3 (semantic/LLM-prepared contradiction detection) | `jsonschema` |
| `backup_manager.py` | `BackupManager` | ~838 | ZIP backup system for user-world/. Create, list, compare, restore, entity-level restore, auto-cleanup (keep last 10) | None (stdlib) |
| `error_recovery.py` | `ErrorRecoveryManager` | ~1875 | Health checks across 6 subsystems (JSON, schema, SQLite, graph, state, bookkeeping). Auto-repair, entity rollback, crash recovery. All error messages human-friendly | `jsonschema` (lazy) |

**Total engine code:** ~11,905 lines across 10 modules.

### 1.2 Engine Data Files (3 files, `engine/`)

| File | Purpose | Size |
|---|---|---|
| `template_registry.json` | Master list of all 85 templates with metadata: id, file path, step, phase, entity_type, folder, minimum_count, cross_references | ~85 entries |
| `reference_index.json` | Maps 16 reference databases to tagged sections with relevant_steps. Used by ChunkPuller and FairRepresentation | 16 databases, ~200+ sections |
| `source_index.json` | Maps 52 progression steps to line ranges in source-text.txt (8,677 lines total across 3 volumes) | 52 entries |

### 1.3 Hook Scripts (6 files, `hooks/`)

| File | Hook Type | Trigger | Purpose |
|---|---|---|---|
| `session_start.py` | SessionStart | Session begins | Initializes SQLite (full_sync), WorldGraph (build_graph), BookkeepingManager (start_session). Prints session summary |
| `inject_step_context.py` | UserPromptSubmit | Every user prompt | Injects condensed guidance (ChunkPuller), featured sources (FairRepresentation), relevant entities (SQLite), pending contradictions (Bookkeeper) |
| `validate_writes.py` | PostToolUse | After tool use | Watches writes to user-world/entities/. Runs ConsistencyChecker, syncs to SQLite, updates WorldGraph, logs to Bookkeeper |
| `check_completion.py` | PostToolUse | After tool use | Checks step completion requirements, shows progress bar or congratulatory message, suggests next step |
| `save_checkpoint.py` | PreCompact | Before compaction | Saves checkpoint JSON with full state snapshot, entity summaries, records checkpoint event |
| `end_session.py` | SessionEnd | Session ends | Ends bookkeeper session, closes SQLite, prints final statistics |

### 1.4 Templates (85 JSON files across 12 phase directories)

| Phase | Directory | Templates | Steps |
|---|---|---|---|
| 01 Foundation | `phase01-foundation/` | 4 | 1-4 |
| 02 Cosmology | `phase02-cosmology/` | 5 | 5-10 |
| 03 The Land | `phase03-land/` | 3 | 11-16 |
| 04 Life | `phase04-life/` | 8 | 17-22 |
| 05 Civilization | `phase05-civilization/` | 6 | 23-30 |
| 06 Society | `phase06-society/` | 21 | 31-37 |
| 07 The Supernatural | `phase07-supernatural/` | 13 | 38-41 |
| 08 History & Legend | `phase08-history/` | 4 | 42-45 |
| 09 Language & Names | `phase09-language/` | 7 | 46-47 |
| 10 Travel & Scale | `phase10-travel/` | 7 | 48-49 |
| 11 Finishing Touches | `phase11-finishing/` | 5 | 50-51 |
| 12 Integration | `phase12-integration/` | 2 | 52 |
| **Total** | | **85** | **52 steps** |

### 1.5 Reference Databases (16 Markdown files)

| Category | Databases | Location |
|---|---|---|
| Mythologies (10) | greek, roman, norse, celtic, chinese, japanese, native-american, mesopotamian, hindu, biblical | `reference-databases/mythologies/` |
| Authors (6) | tolkien, martin, rothfuss, berg, lovecraft, jordan | `reference-databases/authors/` |

### 1.6 Test Suite (8 test files + conftest, `tests/`)

| File | Tests For |
|---|---|
| `test_data_manager.py` | DataManager |
| `test_bookkeeper.py` | BookkeepingManager |
| `test_graph_builder.py` | WorldGraph |
| `test_chunk_puller.py` | ChunkPuller |
| `test_fair_representation.py` | FairRepresentationManager |
| `test_option_generator.py` | OptionGenerator |
| `test_sqlite_sync.py` | SQLiteSyncEngine |
| `test_consistency_checker.py` | ConsistencyChecker |
| `conftest.py` | Shared fixtures (temp dirs, sample data) |

**Reported:** 182 tests, all passing.

### 1.7 Configuration Files

| File | Purpose |
|---|---|
| `.claude/settings.json` | Hook configuration -- maps 5 hook types to 6 script commands |
| `.claude/rules/worldbuilding-rules.md` | Session rules: hook behavior, option generation, fair representation, consistency, communication |
| `.claude/rules/agent-rules.md` | Agent rules: use Opus agents, non-technical user, no external APIs |
| `.claude/rules/commit-rules.md` | Git rules: auto-commit, descriptive messages, update progress/decisions |
| `CLAUDE.md` | Master project documentation with directory structure, module descriptions, design decisions, dependencies |

### 1.8 Documentation & Analysis Files

| File | Purpose |
|---|---|
| `source-text.txt` | Full text of "The Complete Art of World Building" (8,677 lines, read-only) |
| `progression-map.md` | 52-step progression across 12 phases with dependencies |
| `phase2-plan.md` | Original architecture plan |
| `phase2-plan-revised.md` | Revised architecture plan (post-research) |
| `volume1-analysis.md` | Volume 1 chapter dissection |
| `volume2-analysis.md` | Volume 2 chapter dissection |
| `volume3-analysis.md` | Volume 3 chapter dissection |
| `docs/decisions.md` | Decision log |
| `docs/progress.md` | Progress tracker |
| `docs/phase3-research.md` | Phase 3 research |
| `docs/claude-code-integration-research.md` | Claude Code integration research |
| `memory-research.md` | Memory system research |
| `rlm-research.md` | RLM research |
| `orchestration-research.md` | Orchestration research |
| `retrieval-research.md` | Retrieval at scale research |
| `bookkeeping-research.md` | Bookkeeping system research |
| `scale-gaps-research.md` | Scale gaps analysis |
| `consistency-research.md` | Consistency system research |

---

## 2. Data Flow Map

### 2.1 Core Data Flow (Entity Lifecycle)

```
User Decision
     |
     v
OptionGenerator.generate_options()
     |  reads: state.json, entity files, option-history.jsonl, concept-bank.json
     |  uses: ChunkPuller (guidance), FairRepresentation (DB rotation),
     |        WorldGraph (relationships), DataManager (existing entities)
     |  output: 2-4 complete options with context
     |
     v
User Chooses Option
     |
     v
DataManager.create_entity() or .update_entity()
     |  generates: entity ID (slug + 4-hex)
     |  validates: JSON schema (jsonschema Draft202012)
     |  extracts: canon_claims from entity fields
     |  generates: prose paragraph from structured data
     |  writes: user-world/entities/<type>/<id>.json
     |  updates: user-world/state.json (entity_index)
     |  writes: bookkeeping/revisions/snapshots/<id>_<timestamp>.json
     |
     v
validate_writes.py hook (PostToolUse)
     |  runs: ConsistencyChecker.check_entity()
     |    Layer 1: JSON Schema validation
     |    Layer 2: Rule-based cross-reference checks
     |    Layer 3: Semantic contradiction detection (prepared for sub-agent)
     |  syncs: SQLiteSyncEngine.sync_entity()
     |  updates: WorldGraph.add_entity() + .add_relationship()
     |  logs: BookkeepingManager.record_entity_created() or .record_entity_revised()
     |
     v
Entity stored in JSON, indexed in SQLite, linked in Graph, logged in Bookkeeping
```

### 2.2 Session Lifecycle

```
Session Start (hook: session_start.py)
     |  SQLiteSyncEngine.full_sync()     -- rebuilds SQLite from all JSON entities
     |  WorldGraph.build_graph()         -- rebuilds in-memory graph from JSON entities
     |  BookkeepingManager.start_session() -- opens JSONL session, generates session ID
     |
     v
Every User Prompt (hook: inject_step_context.py)
     |  ChunkPuller.pull_condensed()     -- three-layer guidance for current step
     |  FairRepresentation.select_featured() -- 4 myths + 3 authors for this step
     |  SQLiteSyncEngine.search()        -- relevant existing entities
     |  BookkeepingManager.get_contradictions() -- pending contradictions
     |  Output: context injected into Claude's prompt
     |
     v
After Tool Use (hooks: validate_writes.py, check_completion.py)
     |  validate_writes: entity validation + sync pipeline (see above)
     |  check_completion: step requirement checking + progress display
     |
     v
Before Compaction (hook: save_checkpoint.py)
     |  Saves: checkpoint JSON with state snapshot, entity summaries
     |  Records: checkpoint_saved event in bookkeeping
     |  Prints: summary for post-compaction context continuity
     |
     v
Session End (hook: end_session.py)
     |  BookkeepingManager.end_session() -- writes session summary markdown
     |  SQLiteSyncEngine.close()         -- closes SQLite connection
     |  Prints: session statistics (entities, steps, types)
```

### 2.3 Guidance Generation Flow (Three Layers)

```
ChunkPuller.pull_guidance(step_number)
     |
     +-- Layer 1: Book Quotes
     |   reads: engine/source_index.json -> line ranges
     |   reads: source-text.txt -> extracts relevant paragraphs
     |   output: direct quotes from Ellefson's book
     |
     +-- Layer 2: Reference Database Extracts
     |   reads: engine/reference_index.json -> relevant sections per step
     |   reads: reference-databases/mythologies/*.md
     |   reads: reference-databases/authors/*.md
     |   uses: FairRepresentation for which DBs to feature
     |   output: synthesized examples from mythologies + authors
     |
     +-- Layer 3: Actionable Template Info
         reads: engine/template_registry.json -> templates for this step
         reads: templates/phase*/*.json -> schema fields and descriptions
         reads: user-world/state.json -> existing entities for context
         includes: guided questions from _GUIDED_QUESTIONS dict
         output: what needs to be created, field descriptions, existing canon context
```

### 2.4 Option Generation Flow (Divergent-Convergent)

```
OptionGenerator.generate_options(step_number, num_options=3)
     |
     +-- Phase 1: Context Assembly
     |   ChunkPuller.pull_guidance()      -- three-layer guidance
     |   FairRepresentation.select_option_sources() -- per-option DB combos
     |   WorldGraph.get_most_connected()   -- key entities
     |   DataManager.list_entities()       -- existing canon
     |   option-history.jsonl              -- previously used themes
     |   concept-bank.json                 -- random creative injection words
     |
     +-- Phase 2: Divergent (8 raw ideas)
     |   Produces 6-8 raw concept seeds using different mythological/authorial
     |   inspiration combos, random concept-bank words, and anti-repetition filters
     |
     +-- Phase 3: Convergent (filter to 2-4)
     |   Scores: diversity, canon consistency, anti-repetition
     |   Filters: removes duplicates, ensures variety
     |
     +-- Phase 4: Flesh Out
         Each surviving option gets full context:
         - Which mythologies/authors inspired it
         - How it fits existing canon
         - Template fields it would fill
         - Potential cross-references
         Output: complete options dict ready for Claude to present
```

---

## 3. Integration Points

### 3.1 Module Dependencies (Who Instantiates Whom)

```
OptionGenerator
  +-- DataManager
  +-- WorldGraph
  +-- ChunkPuller
  +-- FairRepresentationManager
  +-- BookkeepingManager

ConsistencyChecker
  (standalone, reads entity/template files directly)

ErrorRecoveryManager
  +-- DataManager (lazy)
  +-- SQLiteSyncEngine (lazy)
  +-- WorldGraph (lazy)
  +-- BookkeepingManager (lazy)
  +-- ConsistencyChecker (lazy -- for schema checks)

BackupManager
  (standalone, reads/writes user-world/ and backups/)

SQLiteSyncEngine
  (standalone, reads entity JSON files)
```

### 3.2 Hook-to-Engine Integration

| Hook | Engine Modules Used |
|---|---|
| `session_start.py` | SQLiteSyncEngine, WorldGraph, BookkeepingManager |
| `inject_step_context.py` | ChunkPuller, FairRepresentationManager, SQLiteSyncEngine, BookkeepingManager |
| `validate_writes.py` | ConsistencyChecker, SQLiteSyncEngine, WorldGraph, BookkeepingManager |
| `check_completion.py` | ChunkPuller (step info, dependencies) |
| `save_checkpoint.py` | BookkeepingManager |
| `end_session.py` | BookkeepingManager, SQLiteSyncEngine |

### 3.3 Cross-Module Communication

All modules communicate through **shared file paths** rather than in-process references. There is no singleton registry or dependency injection container. Each hook script instantiates the engine classes it needs independently. This means:

- **SQLite is rebuilt from scratch** every session start (not persisted between sessions as authoritative)
- **WorldGraph is rebuilt from scratch** every session start
- **Bookkeeping events are append-only** -- each module can write events independently
- **state.json is the central coordination point** -- multiple modules read/write it

### 3.4 Shared Constants

- `PROJECT_ROOT = "C:/Worldbuilding-Interactive-Program"` -- hardcoded in every hook script
- Phase names defined in: `chunk_puller.py` (`_PHASE_NAMES` dict), `template_registry.json` (phase field)
- Step dependencies defined in: `chunk_puller.py` (`_STEP_DEPENDENCIES` dict)
- Mythology/author lists defined in: `fair_representation.py` (`MYTHOLOGIES`, `AUTHORS` constants)

---

## 4. File I/O Map

### 4.1 Reads

| Module/Hook | Files Read |
|---|---|
| `DataManager` | `user-world/state.json`, `engine/template_registry.json`, `templates/**/*.json`, `user-world/entities/**/*.json` |
| `BookkeepingManager` | `bookkeeping/events/*.jsonl`, `bookkeeping/indexes/*.json`, `bookkeeping/sessions/*.md` |
| `WorldGraph` | `user-world/entities/**/*.json`, `templates/**/*.json` |
| `ChunkPuller` | `engine/source_index.json`, `engine/reference_index.json`, `engine/template_registry.json`, `source-text.txt`, `reference-databases/**/*.md`, `user-world/state.json` |
| `FairRepresentation` | `user-world/state.json` (reference_usage_counts) |
| `OptionGenerator` | `generation/option-history.jsonl`, `generation/concept-bank.json`, `user-world/state.json` |
| `SQLiteSyncEngine` | `user-world/entities/**/*.json` (during full_sync) |
| `ConsistencyChecker` | `user-world/entities/**/*.json`, `engine/template_registry.json`, `templates/**/*.json` |
| `BackupManager` | `user-world/**`, `backups/*.zip` |
| `ErrorRecoveryManager` | All of the above (delegates to other modules) |
| `session_start.py` | `user-world/state.json` |
| `inject_step_context.py` | `user-world/state.json` |
| `validate_writes.py` | `user-world/state.json` |
| `check_completion.py` | `user-world/state.json`, `engine/template_registry.json` |
| `save_checkpoint.py` | `user-world/state.json` |
| `end_session.py` | `user-world/state.json` |

### 4.2 Writes

| Module/Hook | Files Written |
|---|---|
| `DataManager` | `user-world/entities/<type>/<id>.json`, `user-world/state.json`, `bookkeeping/revisions/snapshots/<id>_<timestamp>.json` |
| `BookkeepingManager` | `bookkeeping/events/events-YYYY-MM.jsonl` (append), `bookkeeping/indexes/*.json` (rebuild), `bookkeeping/sessions/session-*.md` |
| `FairRepresentation` | `user-world/state.json` (reference_usage_counts field) |
| `OptionGenerator` | `generation/option-history.jsonl` (append) |
| `SQLiteSyncEngine` | `runtime/worldbuilding.db` (derived, rebuildable) |
| `BackupManager` | `backups/backup-<timestamp>.zip` |
| `save_checkpoint.py` | `bookkeeping/sessions/checkpoint-<timestamp>.json`, `bookkeeping/sessions/state-snapshot-<timestamp>.json` |

### 4.3 File Categories by Mutability

| Category | Mutability | Source of Truth? | Examples |
|---|---|---|---|
| Source text | Read-only | N/A | `source-text.txt` |
| Reference databases | Read-only | N/A | `reference-databases/**/*.md` |
| Templates | Read-only | N/A | `templates/**/*.json` |
| Engine indexes | Read-only | N/A | `engine/template_registry.json`, `reference_index.json`, `source_index.json` |
| Entity JSON files | Read-write | **YES** (primary) | `user-world/entities/**/*.json` |
| State file | Read-write | **YES** (primary) | `user-world/state.json` |
| Bookkeeping events | Append-only | **YES** (primary) | `bookkeeping/events/*.jsonl` |
| Bookkeeping indexes | Derived (rebuildable) | No | `bookkeeping/indexes/*.json` |
| Session summaries | Write-once | Archive | `bookkeeping/sessions/*.md` |
| SQLite database | Derived (rebuildable) | No | `runtime/worldbuilding.db` |
| NetworkX graph | In-memory only | No | (not persisted) |
| Option history | Append-only | **YES** | `generation/option-history.jsonl` |
| Backups | Write-once | Archive | `backups/*.zip` |

---

## 5. External Dependencies

### 5.1 Required Python Packages

| Package | Version | Used By | Purpose |
|---|---|---|---|
| `jsonschema` | (any) | `data_manager.py`, `consistency_checker.py`, `error_recovery.py` | JSON Schema Draft202012 validation of entity data against templates |
| `networkx` | (any) | `graph_builder.py` | In-memory directed knowledge graph for entity relationships |
| `pytest` | (any) | `tests/` | Test runner (dev only) |

### 5.2 Python Standard Library Usage

All modules rely heavily on stdlib. Key stdlib modules used:

- `json` -- all modules (entity serialization)
- `os` / `pathlib` -- all modules (file I/O)
- `sqlite3` -- `sqlite_sync.py` (FTS5 search)
- `datetime` -- most modules (timestamps)
- `re` -- `data_manager.py`, `chunk_puller.py`, `consistency_checker.py` (pattern matching)
- `copy` -- `data_manager.py` (deep copy of entity data)
- `secrets` -- `data_manager.py` (hex token for entity IDs)
- `unicodedata` -- `data_manager.py` (slug generation)
- `shutil` -- `backup_manager.py`, `error_recovery.py` (file copying)
- `zipfile` -- `backup_manager.py` (backup archives)
- `tempfile` -- `backup_manager.py`, `error_recovery.py` (safe writes)
- `glob` -- `bookkeeper.py`, `error_recovery.py` (file discovery)
- `random` -- `fair_representation.py`, `option_generator.py` (shuffling)
- `collections.Counter` -- `consistency_checker.py` (counting)

### 5.3 Import Style

Both `jsonschema` and `networkx` use a **try/except ImportError** pattern at module level (or inside functions for lazy imports), providing a human-friendly error message if not installed. No `requirements.txt` file exists in the repository.

### 5.4 External Services

**None.** The system is fully offline. No API calls, no cloud services, no Docker, no external databases. Claude Code itself serves as the LLM backend for semantic checks (Layer 3 consistency) via sub-agents.

---

## 6. Hook Architecture

### 6.1 Configuration

Hooks are configured in `.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      { "command": "python C:/Worldbuilding-Interactive-Program/hooks/session_start.py" }
    ],
    "UserPromptSubmit": [
      { "command": "python C:/Worldbuilding-Interactive-Program/hooks/inject_step_context.py" }
    ],
    "PostToolUse": [
      { "command": "python C:/Worldbuilding-Interactive-Program/hooks/validate_writes.py" },
      { "command": "python C:/Worldbuilding-Interactive-Program/hooks/check_completion.py" }
    ],
    "PreCompact": [
      { "command": "python C:/Worldbuilding-Interactive-Program/hooks/save_checkpoint.py" }
    ],
    "SessionEnd": [
      { "command": "python C:/Worldbuilding-Interactive-Program/hooks/end_session.py" }
    ]
  }
}
```

### 6.2 Hook Execution Model

- All hooks are **Python scripts** executed as subprocesses by Claude Code
- Each hook runs independently (no shared in-process state between hooks)
- Each hook instantiates its own engine objects (no singleton pattern)
- All hooks hardcode `PROJECT_ROOT = "C:/Worldbuilding-Interactive-Program"` and add it to `sys.path`
- All hooks wrap `main()` in `try/except Exception` to avoid crashing Claude Code
- Output is via `print()` statements -- Claude Code captures stdout

### 6.3 Hook Lifecycle Timing

```
[Session Start]
  1. session_start.py
     - Full SQLite sync (reads all entity JSON files, rebuilds DB)
     - Full graph build (reads all entity JSON files, builds NetworkX graph)
     - Bookkeeper session start (opens JSONL log)
     - Prints: session ID, step, entity count, phase name

[Every User Message]
  2. inject_step_context.py
     - Injects condensed guidance for current step
     - Shows featured mythologies/authors
     - Lists relevant existing entities
     - Shows pending contradictions

[After Every Tool Use]
  3. validate_writes.py
     - Only activates if an entity file was written
     - Runs three-layer consistency check
     - Syncs entity to SQLite
     - Updates knowledge graph
     - Logs creation/revision to bookkeeper
  4. check_completion.py
     - Checks if current step requirements are met
     - Shows progress bar or completion message
     - Suggests next step if complete

[Before Context Compaction]
  5. save_checkpoint.py
     - Saves full state checkpoint
     - Records entity summaries
     - Prints context for post-compaction continuity

[Session End]
  6. end_session.py
     - Ends bookkeeper session (writes markdown summary)
     - Closes SQLite connection
     - Prints final statistics
```

### 6.4 Performance Characteristics

- `session_start.py` is the heaviest hook (full SQLite sync + graph build), but only runs once
- `inject_step_context.py` runs on every user message -- reads state.json, runs SQLite queries, reads chunk_puller guidance
- `validate_writes.py` runs after every tool use but short-circuits if no entity file was written
- `check_completion.py` is lightweight (reads state.json + template registry)

---

## 7. State Management

### 7.1 Primary State File: `user-world/state.json`

This is the central coordination point. Its structure:

```json
{
  "current_step": 1,
  "current_phase": "foundation",
  "completed_steps": [],
  "entity_index": {
    "<entity-id>": {
      "name": "...",
      "entity_type": "god|species|settlement|...",
      "template_id": "...",
      "status": "draft|canon",
      "file_path": "user-world/entities/<type>/<id>.json",
      "created_at": "ISO timestamp",
      "updated_at": "ISO timestamp"
    }
  },
  "reference_usage_counts": {
    "mythologies": { "greek": 0, "roman": 0, ... },
    "authors": { "tolkien": 0, "martin": 0, ... }
  }
}
```

### 7.2 Entity Status Lifecycle

```
draft  -->  canon
  |           |
  +--- (can be revised at any point) ---+
  |           |
  +--- (can be rolled back via backup) ---+
```

- **draft**: Entity exists but is not yet confirmed as part of the world
- **canon**: Entity is confirmed and must be respected by all future options and entities

### 7.3 Event-Sourced Bookkeeping

The bookkeeping system maintains an append-only event log as the authoritative history. Event types:

| Event Type | When |
|---|---|
| `session_started` | Session begins |
| `session_ended` | Session ends |
| `decision_made` | User chooses from options |
| `draft_created` | New entity created |
| `status_changed` | Entity promoted to canon or reverted to draft |
| `entity_revised` | Entity updated |
| `cross_reference_created` | Relationship between entities established |
| `contradiction_found` | Contradiction detected |
| `contradiction_resolved` | Contradiction fixed |
| `step_status_changed` | Step completed or status updated |
| `checkpoint_saved` | Pre-compaction checkpoint created |

Derived indexes (rebuildable from events):
- `bookkeeping/indexes/decisions.json` -- all decisions by step
- `bookkeeping/indexes/progression.json` -- step completion status
- `bookkeeping/indexes/entity-registry.json` -- entity creation/status history
- `bookkeeping/indexes/cross-references.json` -- all relationships
- `bookkeeping/indexes/contradictions.json` -- open/resolved contradictions

### 7.4 Revision History

- Every entity update creates a snapshot: `bookkeeping/revisions/snapshots/<id>_<timestamp>.json`
- Revisions indexed in: `bookkeeping/revisions/revisions-by-entity.json`
- Can be rolled back via `ErrorRecoveryManager.rollback_entity(entity_id, version_timestamp)`

### 7.5 State Rebuild Capability

The system is designed so that derived state can be rebuilt from primary sources:

| Derived Store | Rebuilt From | Rebuild Method |
|---|---|---|
| SQLite (`runtime/worldbuilding.db`) | Entity JSON files | `SQLiteSyncEngine.full_sync()` |
| NetworkX graph | Entity JSON files | `WorldGraph.build_graph()` |
| Bookkeeping indexes | Event JSONL files | `BookkeepingManager.rebuild_indexes()` |
| Bookkeeping revision index | Snapshot files | `BookkeepingManager.rebuild_indexes()` |

---

## 8. What a UI Needs to Do

### 8.1 Core Responsibilities

A UI for this system would need to handle these key workflows:

#### A. Session Management
- Start a session (trigger `session_start.py` equivalent: SQLite sync, graph build, bookkeeper start)
- End a session (trigger `end_session.py` equivalent: bookkeeper end, SQLite close, statistics)
- Display session statistics (session ID, current step, entity counts)

#### B. Step Navigation
- Display current step number and phase name
- Show three-layer guidance for the current step:
  - Book quotes (Layer 1)
  - Reference database extracts (Layer 2)
  - Template/field info with guided questions (Layer 3)
- Show step completion progress (progress bar, remaining requirements)
- Allow advancing to next step (update `current_step` in state.json)
- Show step dependencies (which steps must be completed first)

#### C. Option Generation and Selection (Most Important)
- Trigger option generation for the current step (`OptionGenerator.generate_options()`)
- Display 2-4 complete options with:
  - Full option description
  - Which mythologies/authors inspired each option
  - How each option fits existing canon
  - What cross-references it would create
- Allow user to: pick one, combine elements, request new options, go fully custom
- Record the choice (`OptionGenerator.record_choice()` + `BookkeepingManager.record_decision()`)

#### D. Entity Management
- Create entities (`DataManager.create_entity()`)
- View/edit entities (`DataManager.get_entity()`, `.update_entity()`)
- List entities with filtering by type, status, step (`DataManager.list_entities()`, `SQLiteSyncEngine.query_by_type/step/status()`)
- Search entities full-text (`SQLiteSyncEngine.search()`)
- Set entity status draft/canon (`DataManager.set_entity_status()`)
- Display entity prose paragraph alongside structured data
- Show entity relationships from the knowledge graph (`WorldGraph.get_related_entities()`)

#### E. Consistency and Validation
- Run validation on entity save (`ConsistencyChecker.check_entity()`)
- Display validation results in human-friendly format (`ConsistencyChecker.format_human_message()`)
- Show pending contradictions (`BookkeepingManager.get_contradictions()`)
- Allow contradiction resolution (`BookkeepingManager.resolve_contradiction()`)

#### F. Knowledge Graph Visualization
- Display entity relationship graph (`WorldGraph`)
- Show neighbors, clusters, paths between entities
- Highlight orphan entities (no relationships)
- Show most-connected entities

#### G. History and Decisions
- Display decision log (`BookkeepingManager.get_decisions()`)
- Display entity revision history (`BookkeepingManager.get_entity_history()`)
- Allow entity rollback to previous version (`ErrorRecoveryManager.rollback_entity()`)
- Display session summaries (`BookkeepingManager.get_session_summaries()`)

#### H. Backup and Recovery
- Create manual backups (`BackupManager.create_backup()`)
- List and compare backups (`BackupManager.list_backups()`, `.compare_backup()`)
- Restore full backup or single entity (`BackupManager.restore_backup()`, `.restore_entity()`)
- Run health check (`ErrorRecoveryManager.check_health()`)
- Run auto-repair (`ErrorRecoveryManager.repair_all()`)

### 8.2 API Surface Required

A UI would need to call these engine classes:

| Engine Class | Key Methods for UI |
|---|---|
| `DataManager` | `create_entity()`, `update_entity()`, `get_entity()`, `list_entities()`, `search_entities()`, `set_entity_status()`, `validate_entity()`, `generate_prose()` |
| `BookkeepingManager` | `start_session()`, `end_session()`, `record_decision()`, `get_decisions()`, `get_entity_history()`, `get_contradictions()`, `resolve_contradiction()`, `get_session_summaries()` |
| `WorldGraph` | `build_graph()`, `get_related_entities()`, `get_neighbors()`, `find_path()`, `get_orphans()`, `get_most_connected()`, `get_stats()` |
| `ChunkPuller` | `pull_guidance()`, `pull_condensed()`, `get_step_dependencies()` |
| `FairRepresentationManager` | `select_featured()`, `get_usage_stats()` |
| `OptionGenerator` | `generate_options()`, `record_choice()`, `get_option_history()` |
| `SQLiteSyncEngine` | `full_sync()`, `search()`, `query_by_type()`, `query_by_step()`, `query_by_status()`, `get_stats()` |
| `ConsistencyChecker` | `check_entity()`, `format_human_message()` |
| `BackupManager` | `create_backup()`, `list_backups()`, `compare_backup()`, `restore_backup()`, `restore_entity()` |
| `ErrorRecoveryManager` | `check_health()`, `repair_all()`, `recover_entity()`, `rollback_entity()`, `generate_health_report()` |

### 8.3 Data the UI Must Display

| Data Point | Source | Update Frequency |
|---|---|---|
| Current step + phase | `state.json` | Per step advance |
| Step guidance (3 layers) | `ChunkPuller` | Per step |
| Featured mythologies/authors | `FairRepresentation` | Per step |
| Options (2-4) | `OptionGenerator` | Per decision point |
| Entity list | `state.json` entity_index | Per entity create/update |
| Entity detail + prose | Entity JSON file | Per entity view |
| Entity relationships | `WorldGraph` | Per entity view |
| Validation results | `ConsistencyChecker` | Per entity save |
| Step progress | Template registry minimum_counts vs entity_index | Per entity create |
| Contradictions | `BookkeepingManager` | Per validation |
| Decision history | `BookkeepingManager` | Per decision |
| Session statistics | `SQLiteSyncEngine.get_stats()` | Per session |
| Health status | `ErrorRecoveryManager` | On demand |

### 8.4 Key Architectural Notes for UI Development

1. **No REST API exists yet.** All engine modules are Python classes that must be instantiated in-process or wrapped with an API layer.

2. **The LLM is not embedded.** The option generator assembles context but does NOT call an LLM. In the current Claude Code setup, Claude itself reads the assembled context and generates options. A standalone UI would need its own LLM integration (Anthropic API or similar) for option generation and semantic consistency checks.

3. **Hardcoded paths.** All hooks and some modules hardcode `C:/Worldbuilding-Interactive-Program` as the project root. A UI would need to make this configurable.

4. **No authentication.** This is a single-user local tool. No user accounts, no permissions.

5. **Graph is in-memory only.** The NetworkX graph is rebuilt every session. For a persistent UI, you would either rebuild on startup or persist the graph.

6. **SQLite is runtime-only.** The SQLite DB is rebuilt from JSON files each session. A persistent UI could keep it running but must handle sync on entity changes.

7. **Fair representation state is in state.json.** The usage counters persist across sessions via state.json, not via a separate config.

8. **Option history is append-only JSONL.** The UI would need to read this file to show previously generated options and avoid repetition.

---

## Appendix A: Directory Structure Summary

```
C:\Worldbuilding-Interactive-Program\
|-- .claude/
|   |-- settings.json              (hook configuration)
|   |-- rules/
|       |-- agent-rules.md
|       |-- commit-rules.md
|       |-- worldbuilding-rules.md
|
|-- backups/                        (empty -- no backups yet)
|
|-- bookkeeping/
|   |-- events/                     (append-only JSONL logs)
|   |-- indexes/                    (derived JSON indexes)
|   |-- revisions/                  (entity revision history)
|   |-- sessions/                   (session summary markdowns)
|   |-- snapshots/                  (periodic full-state snapshots)
|
|-- docs/
|   |-- decisions.md
|   |-- progress.md
|   |-- phase3-research.md
|   |-- claude-code-integration-research.md
|   |-- project-audit.md           (this file)
|
|-- engine/                         (10 Python modules + 3 JSON indexes)
|-- generation/                     (option-history.jsonl + concept-bank.json)
|-- hooks/                          (6 Python hook scripts)
|-- reference-databases/
|   |-- mythologies/                (10 markdown files)
|   |-- authors/                    (6 markdown files)
|
|-- runtime/                        (SQLite DB -- derived, .gitignored)
|
|-- templates/
|   |-- phase01-foundation/         (4 templates)
|   |-- phase02-cosmology/          (5 templates)
|   |-- phase03-land/               (3 templates)
|   |-- phase04-life/               (8 templates)
|   |-- phase05-civilization/       (6 templates)
|   |-- phase06-society/            (21 templates)
|   |-- phase07-supernatural/       (13 templates)
|   |-- phase08-history/            (4 templates)
|   |-- phase09-language/           (7 templates)
|   |-- phase10-travel/             (7 templates)
|   |-- phase11-finishing/          (5 templates)
|   |-- phase12-integration/        (2 templates)
|
|-- tests/                          (8 test files + conftest.py)
|
|-- user-world/
|   |-- state.json
|   |-- entities/                   (entity JSON files by type)
|   |-- worksheets/
|   |-- registries/
|   |-- timelines/
|   |-- travel/
|   |-- maps/
|
|-- source-text.txt                 (8,677 lines, read-only)
|-- progression-map.md              (52 steps across 12 phases)
|-- phase2-plan.md
|-- phase2-plan-revised.md
|-- CLAUDE.md                       (master project docs)
|-- volume1-analysis.md
|-- volume2-analysis.md
|-- volume3-analysis.md
|-- *.md                            (6 research documents)
```

## Appendix B: File Counts

| Category | Count |
|---|---|
| Engine Python modules | 10 |
| Engine JSON index files | 3 |
| Hook scripts | 6 |
| JSON schema templates | 85 |
| Reference databases | 16 (10 mythologies + 6 authors) |
| Test files | 9 (8 test + conftest) |
| Claude rules files | 3 |
| Research documents | 6 |
| Analysis documents | 3 |
| Documentation files | 5 (decisions, progress, phase3-research, integration-research, this audit) |
| **Total tracked files** | **~146+** |
