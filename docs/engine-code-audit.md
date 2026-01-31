# Engine Code Audit Report

**Date:** 2026-01-30
**Auditor:** Claude Opus 4.5 (Automated Production-Readiness Audit)
**Scope:** All 10 engine modules, 9 test files, 6 hook files
**Standard:** Production-readiness for PySide6 desktop application with Claude LLM integration

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Audit Methodology](#audit-methodology)
3. [Per-Module Audit](#per-module-audit)
   - [data_manager.py](#1-data_managerpy)
   - [bookkeeper.py](#2-bookkeeperpy)
   - [graph_builder.py](#3-graph_builderpy)
   - [chunk_puller.py](#4-chunk_pullerpy)
   - [fair_representation.py](#5-fair_representationpy)
   - [option_generator.py](#6-option_generatorpy)
   - [consistency_checker.py](#7-consistency_checkerpy)
   - [sqlite_sync.py](#8-sqlite_syncpy)
   - [backup_manager.py](#9-backup_managerpy)
   - [error_recovery.py](#10-error_recoverypy)
4. [Hook Files Audit](#hook-files-audit)
5. [Cross-Cutting Issues](#cross-cutting-issues)
6. [Test Coverage Analysis](#test-coverage-analysis)
7. [Prioritized Fix List](#prioritized-fix-list)
8. [Overall Assessment](#overall-assessment)

---

## Executive Summary

The engine layer comprises approximately **11,000 lines of Python** across 10 modules, forming the critical enforcement barrier between Claude (LLM) and user world data. The code demonstrates strong architectural thinking -- event sourcing, three-layer validation, FTS5 search, knowledge graphs, fair representation algorithms, and comprehensive error recovery. However, several systemic issues threaten production reliability:

- **No thread safety anywhere.** Every module performs unprotected file I/O. This is a showstopper for a PySide6 desktop app where engine operations will run on background threads.
- **No atomic file writes.** All JSON writes use direct `open()` without temp-file-then-rename, risking data corruption on crash or power loss.
- **Broad exception swallowing.** Multiple modules catch `Exception` and silently discard errors, making debugging nearly impossible.
- **No tests for 2 of 10 modules** (backup_manager.py, error_recovery.py) -- the two modules responsible for data safety.
- **Duplicated code** across 3+ modules (_safe_read_json, _safe_write_json, _clean_schema_for_validation).

**Overall Verdict: Needs Major Work before production deployment.**

The architectural foundation is solid. The issues are primarily in reliability engineering: concurrency, atomicity, error propagation, and test coverage. These are fixable without redesigning the system.

---

## Audit Methodology

Each module was evaluated across 7 dimensions, scored 1-5:

| Dimension | Description |
|---|---|
| **Robustness** | Handles edge cases, corrupt data, missing files gracefully |
| **Validation Completeness** | Validates all inputs, enforces constraints |
| **Error Handling** | Errors are caught, logged, and propagated appropriately |
| **API Surface** | Clean, consistent, well-documented interface for desktop app |
| **Thread Safety** | Safe for concurrent access from UI and background threads |
| **Test Coverage** | Comprehensive tests covering happy path, edge cases, failures |
| **Code Quality** | Readable, maintainable, follows conventions, no dead code |

Scores: 1 = Critical deficiency, 2 = Needs Major Work, 3 = Needs Minor Fixes, 4 = Ready, 5 = Exemplary

---

## Per-Module Audit

### 1. data_manager.py

**File:** `C:\Worldbuilding-Interactive-Program\engine\data_manager.py`
**Lines:** ~1838
**Role:** Entity CRUD, JSON schema validation, prose generation, canon claims, revision snapshots
**Verdict: Needs Minor Fixes**

| Dimension | Score | Notes |
|---|---|---|
| Robustness | 3 | Good fallbacks, but filesystem scan fallback in `_find_entity_file` is O(n) |
| Validation | 4 | Thorough jsonschema validation with Draft202012Validator |
| Error Handling | 3 | Raises ValueError/FileNotFoundError appropriately; some bare excepts |
| API Surface | 4 | Clean CRUD interface: create, update, get, list, search, validate |
| Thread Safety | 1 | No locking on any file operation |
| Test Coverage | 4 | Solid tests for CRUD, prose, canon claims, custom prose |
| Code Quality | 3 | 14 prose functions could be a registry/dispatch pattern; `_clean_schema_for_validation` duplicated |

**Specific Issues:**

| Severity | Issue | Location |
|---|---|---|
| CRITICAL | `_safe_write_json` writes directly to target file without atomic temp-file-then-rename. A crash mid-write corrupts the entity file permanently. | Lines ~45-50 |
| CRITICAL | No thread safety. Concurrent create/update from UI thread and background sync will cause data races. | Entire class |
| HIGH | `_find_entity_file` falls back to `os.walk()` scanning the entire entities directory tree when the expected path fails. On large worlds (hundreds of entities), this is O(n) per lookup. | Lines ~90-110 |
| MEDIUM | `_clean_schema_for_validation` is duplicated in consistency_checker.py and error_recovery.py. Any fix must be applied in 3 places. | Lines ~150-180 |
| MEDIUM | `_safe_read_json` helper is copy-pasted into every module and every hook file (16+ copies). Should be a shared utility. | Lines ~32-38 |
| LOW | 14 separate `_prose_for_*` functions could be refactored into a dispatch table for maintainability. | Lines ~800-1600 |

---

### 2. bookkeeper.py

**File:** `C:\Worldbuilding-Interactive-Program\engine\bookkeeper.py`
**Lines:** ~834
**Role:** Event-sourced bookkeeping with append-only JSONL, session management, derived indexes
**Verdict: Needs Minor Fixes**

| Dimension | Score | Notes |
|---|---|---|
| Robustness | 3 | Event sourcing design is inherently resilient; JSONL is append-only |
| Validation | 3 | Validates event types but not all event payloads |
| Error Handling | 3 | Appropriate exceptions; some swallowed errors in index rebuild |
| API Surface | 4 | Clean event recording API with 10 event types |
| Thread Safety | 1 | No locking on JSONL file appends |
| Test Coverage | 4 | Tests cover all event types, session lifecycle, index rebuilding |
| Code Quality | 4 | Well-structured event sourcing pattern |

**Specific Issues:**

| Severity | Issue | Location |
|---|---|---|
| CRITICAL | `_append_event` opens the JSONL file in append mode without file locking. Concurrent appends from multiple hook invocations can interleave writes, producing corrupt JSON lines. | Lines ~120-140 |
| HIGH | `_next_session_number` reads ALL events from the JSONL file every time it is called (to find the highest session number). For long-running worlds with thousands of events, this becomes increasingly slow. Should maintain a cached counter. | Lines ~160-180 |
| MEDIUM | `rebuild_indexes` loads all events into memory. For very large event logs (10k+ events), this could cause memory pressure. | Lines ~200-250 |
| LOW | `get_session_summaries` reads markdown files from disk; no caching. | Lines ~700-750 |

---

### 3. graph_builder.py

**File:** `C:\Worldbuilding-Interactive-Program\engine\graph_builder.py`
**Lines:** ~671
**Role:** NetworkX DiGraph for entity relationships, traversal, community detection
**Verdict: Needs Minor Fixes**

| Dimension | Score | Notes |
|---|---|---|
| Robustness | 3 | Handles missing nodes gracefully; BFS depth-limited |
| Validation | 2 | Does not validate relationship types against schema |
| Error Handling | 2 | `get_entity_cluster` catches bare Exception and returns empty dict |
| API Surface | 4 | Clean graph query API: neighbors, paths, clusters, orphans, stats |
| Thread Safety | 1 | NetworkX graph object is not thread-safe |
| Test Coverage | 4 | Tests cover build, add/remove, relationships, paths, clusters, orphans |
| Code Quality | 3 | `_add_inbound_edges_for` has O(n) file reads problem |

**Specific Issues:**

| Severity | Issue | Location |
|---|---|---|
| CRITICAL | `_add_inbound_edges_for(entity_id)` re-reads ALL entity JSON files from disk every time `add_entity()` is called, scanning for inbound references. Adding 50 entities = 50 * n file reads. | Lines ~180-220 |
| HIGH | `get_entity_cluster` catches bare `Exception` and returns `{}`, hiding NetworkX errors and making debugging impossible. | Lines ~380-400 |
| MEDIUM | `build_graph()` loads all entities into memory simultaneously. Should stream entities for large worlds. | Lines ~80-120 |
| MEDIUM | Relationship types from entity data are not validated against any schema -- arbitrary strings become edge labels. | Lines ~130-160 |
| LOW | No support for weighted edges or temporal relationships (e.g., "was spouse until year X"). | N/A (design limitation) |

---

### 4. chunk_puller.py

**File:** `C:\Worldbuilding-Interactive-Program\engine\chunk_puller.py`
**Lines:** ~1313
**Role:** Three-layer guidance system with 52 step definitions, book quotes, references
**Verdict: Ready (with minor notes)**

| Dimension | Score | Notes |
|---|---|---|
| Robustness | 4 | Step definitions are hardcoded (stable); graceful degradation for missing data |
| Validation | 3 | Validates step numbers; does not validate guidance content structure |
| Error Handling | 2 | Multiple `except Exception: pass` blocks silently swallow errors |
| API Surface | 4 | Clean guidance API: pull_guidance, pull_condensed, get_step_dependencies |
| Thread Safety | 2 | Read-only after initialization, mostly safe; _select_featured_databases mutates state |
| Test Coverage | 4 | Tests cover guidance structure, multiple steps, dependencies, invalid steps |
| Code Quality | 3 | Large inline data structures; runtime import of fair_representation |

**Specific Issues:**

| Severity | Issue | Location |
|---|---|---|
| HIGH | `_select_featured_databases()` does a runtime `from engine.fair_representation import FairRepresentationManager` inside a try/except that silently falls back to random selection on any import error. This masks configuration problems. | Lines ~900-940 |
| MEDIUM | Multiple `except Exception: pass` blocks throughout. Errors in book quote loading, reference loading, and guided question assembly are silently discarded. | Lines ~600, ~700, ~850 |
| MEDIUM | Step definitions (`_STEP_DEPENDENCIES`, `_GUIDED_QUESTIONS`) are large inline dicts. These should be loaded from a JSON config file for maintainability. | Lines ~50-400 |
| LOW | `pull_condensed()` rebuilds the full guidance then truncates it. Could be optimized to build only the condensed version. | Lines ~1100-1150 |

---

### 5. fair_representation.py

**File:** `C:\Worldbuilding-Interactive-Program\engine\fair_representation.py`
**Lines:** ~253
**Role:** Fair rotation of 10 mythologies + 6 authors across 52 steps
**Verdict: Ready (with minor notes)**

| Dimension | Score | Notes |
|---|---|---|
| Robustness | 4 | Simple algorithm with graceful defaults |
| Validation | 3 | Validates input counts; does not validate mythology/author names |
| Error Handling | 3 | Appropriate for scope |
| API Surface | 4 | Simple: select_featured, select_option_sources, save_state |
| Thread Safety | 1 | `save_state()` does read-then-write without locking |
| Test Coverage | 4 | Tests cover selection, anti-repetition, full 52-step coverage, fairness |
| Code Quality | 4 | Clean, concise, single-responsibility |

**Specific Issues:**

| Severity | Issue | Location |
|---|---|---|
| HIGH | `save_state()` reads the state file, modifies the in-memory dict, then writes it back. If two processes call `save_state()` concurrently (e.g., inject_step_context hook + validate_writes hook), one write is lost. | Lines ~200-230 |
| MEDIUM | Uses `random.shuffle` and `random.random` without seeding. Results are non-reproducible, making debugging difficult. Consider allowing an optional seed parameter. | Lines ~100-120 |
| LOW | The 10 mythologies and 6 authors are hardcoded. Should be configurable from a JSON file. | Lines ~20-40 |

---

### 6. option_generator.py

**File:** `C:\Worldbuilding-Interactive-Program\engine\option_generator.py`
**Lines:** ~1036
**Role:** Divergent-convergent option generation pipeline, context assembly for Claude
**Verdict: Needs Minor Fixes**

| Dimension | Score | Notes |
|---|---|---|
| Robustness | 3 | Graceful degradation when subsystems fail |
| Validation | 3 | Clamps num_options to 2-4 range; validates step numbers |
| Error Handling | 1 | Catches bare Exception everywhere, swallows errors, returns empty defaults |
| API Surface | 4 | Clean: generate_options, record_choice, get_used_themes |
| Thread Safety | 1 | Initializes 5 engine systems; no thread safety |
| Test Coverage | 3 | Tests cover structure, anti-repetition, concept injection, context |
| Code Quality | 2 | Initializes 5 subsystems eagerly in __init__; massive broad except blocks |

**Specific Issues:**

| Severity | Issue | Location |
|---|---|---|
| CRITICAL | `__init__` eagerly initializes DataManager, WorldGraph, ChunkPuller, FairRepresentationManager, and BookkeepingManager. This means constructing an OptionGenerator performs full filesystem scans, SQLite connections, and graph builds. In a desktop app, this will freeze the UI if done on the main thread. | Lines ~40-80 |
| CRITICAL | At least 8 `except Exception` blocks that catch, silently log to an internal list, and return empty defaults. If the ChunkPuller fails to load, the user gets empty guidance with no indication of why. | Lines ~200, ~300, ~400, ~500, ~600, ~700, ~800, ~900 |
| HIGH | `record_choice` writes to a JSON history file without any locking or atomic write protection. | Lines ~850-900 |
| MEDIUM | No lazy loading -- all subsystems are initialized whether they are needed or not. A generate_options call that only needs ChunkPuller still initializes WorldGraph, BookkeepingManager, etc. | Lines ~40-80 |
| LOW | `_all_concepts` concept bank is loaded from a JSON file; if the file is missing, an empty list is used silently. | Lines ~90-100 |

---

### 7. consistency_checker.py

**File:** `C:\Worldbuilding-Interactive-Program\engine\consistency_checker.py`
**Lines:** ~1444
**Role:** Three-layer validation: schema, rules (cross-refs, numerical, category), semantic
**Verdict: Needs Minor Fixes**

| Dimension | Score | Notes |
|---|---|---|
| Robustness | 4 | Three-layer approach is well-designed; fails gracefully per layer |
| Validation | 4 | Comprehensive: schema, enums, cross-refs, numerical ranges, category logic |
| Error Handling | 3 | Human-readable error messages; some silent fallbacks in semantic layer |
| API Surface | 4 | Clean pipeline: check_entity, check_schema, check_rules, check_semantic |
| Thread Safety | 1 | Entity cache not thread-safe; file reads unprotected |
| Test Coverage | 4 | Tests cover all 3 layers, human messaging, full pipeline, edge cases |
| Code Quality | 3 | Duplicated schema cleaning code; entity cache never invalidates |

**Specific Issues:**

| Severity | Issue | Location |
|---|---|---|
| HIGH | `_entity_cache` dict is populated on first access and never invalidated. If an entity is modified after being cached, all subsequent consistency checks use stale data. In a long-running desktop app session, this will cause false positives/negatives. | Lines ~60-80 |
| HIGH | `_clean_schema_for_validation` is a copy of the same function in data_manager.py and error_recovery.py. This is the third copy. | Lines ~150-180 |
| MEDIUM | `_keyword_similarity` uses Jaccard similarity on word sets. This is simple but misses semantic nuances. "God of storms" and "deity of tempests" would score 0.0 similarity. Acceptable for V1 but should be documented as a known limitation. | Lines ~800-830 |
| MEDIUM | `check_semantic` builds an LLM prompt but never actually calls the LLM. It sets `needs_llm_review=True` and expects the caller to handle it. This implicit contract is not documented in the API. | Lines ~900-1000 |
| LOW | `format_human_message` has hardcoded strings like "ISSUE", "OPTIONS", "NOTES". These should be constants for consistency. | Lines ~1100-1300 |

---

### 8. sqlite_sync.py

**File:** `C:\Worldbuilding-Interactive-Program\engine\sqlite_sync.py`
**Lines:** ~803
**Role:** SQLite FTS5 full-text search, entity mirroring, cross-reference queries
**Verdict: Needs Minor Fixes**

| Dimension | Score | Notes |
|---|---|---|
| Robustness | 4 | WAL mode, proper schema creation, graceful handling of missing data |
| Validation | 3 | Validates SQL safety via keyword blocking; parameterized queries |
| Error Handling | 3 | Context manager support; proper close() |
| API Surface | 4 | Clean query API: search, query_by_type/step/status, cross_references, claims |
| Thread Safety | 2 | SQLite itself supports WAL concurrency; Python connection object is not thread-safe |
| Test Coverage | 4 | Tests cover sync, search, queries, SQL safety, stats, context manager |
| Code Quality | 4 | Well-structured; proper use of FTS5 |

**Specific Issues:**

| Severity | Issue | Location |
|---|---|---|
| HIGH | `advanced_query` SQL injection protection splits the query on whitespace and checks tokens against a blocklist (`INSERT`, `DELETE`, `DROP`, `UPDATE`, `ALTER`, `CREATE`). This can be bypassed with creative formatting: `"SELECT/**/ * FROM entities; DELETE FROM entities"` (comment-based bypass), or `"SELECT * FROM entities WHERE id='' OR 1=1; --"`. Should use a proper SQL parser or only allow parameterized prepared statements. | Lines ~600-640 |
| MEDIUM | `_conn` (sqlite3.Connection) is created in `__init__` and is not thread-safe. If the desktop app calls `search()` from a background thread while the UI thread calls `sync_entity()`, undefined behavior occurs. Solution: use `check_same_thread=False` and add a threading.Lock, or create per-thread connections. | Lines ~30-50 |
| MEDIUM | `full_sync()` reads all entity JSON files, parses them, and inserts them into SQLite in a single transaction. For large worlds (500+ entities), this could take several seconds and should show progress. | Lines ~100-160 |
| LOW | `get_stats()` runs 4 separate SQL queries. Could be combined into a single query for efficiency. | Lines ~700-760 |

---

### 9. backup_manager.py

**File:** `C:\Worldbuilding-Interactive-Program\engine\backup_manager.py`
**Lines:** ~838
**Role:** ZIP backup creation/restore, manifests, pre-restore safety backups, entity-level restore
**Verdict: Needs Minor Fixes**

| Dimension | Score | Notes |
|---|---|---|
| Robustness | 4 | Pre-restore safety backups; manifest validation; entity-level granularity |
| Validation | 3 | Validates manifest presence; checks backup integrity |
| Error Handling | 3 | Good exception hierarchy; one potentially unbound variable |
| API Surface | 4 | Clean: create, restore, restore_entity, compare, cleanup, should_auto_backup |
| Thread Safety | 1 | No locking; backup creation reads files that may be concurrently written |
| Test Coverage | 1 | **NO TESTS EXIST** for this module |
| Code Quality | 3 | Solid design; one variable scoping bug |

**Specific Issues:**

| Severity | Issue | Location |
|---|---|---|
| CRITICAL | **No tests exist.** This module handles data backup and restore -- arguably the most safety-critical code in the system. A bug in `restore_backup()` could destroy user data. Zero test coverage is unacceptable. | N/A |
| HIGH | In `create_backup()`, the exception handler references `tmp_path` which may be unbound if `tempfile.mkstemp()` itself raises an exception (e.g., disk full, permission denied). This would cause a `NameError` inside the exception handler, masking the original error. | Lines ~180-190 |
| HIGH | `restore_backup()` uses `shutil.rmtree()` to delete the existing entities directory before extracting the backup. If the extraction fails after deletion, the user loses both the current data AND the backup fails to restore. The pre-restore safety backup mitigates this, but the restore sequence should be: extract to temp dir first, then swap. | Lines ~300-340 |
| MEDIUM | No progress reporting for backup creation or restoration. For large worlds, these operations could take 10+ seconds with no feedback. | Lines ~100-200, ~300-400 |
| LOW | `cleanup_old_backups()` sorts by filename (which includes timestamps). This relies on timestamp format consistency. | Lines ~700-750 |

---

### 10. error_recovery.py

**File:** `C:\Worldbuilding-Interactive-Program\engine\error_recovery.py`
**Lines:** ~1875
**Role:** Health checking, auto-repair, crash recovery, entity rollback, human-friendly reporting
**Verdict: Needs Minor Fixes**

| Dimension | Score | Notes |
|---|---|---|
| Robustness | 4 | Comprehensive health checks; dry_run default prevents accidental damage |
| Validation | 4 | Checks JSON integrity, schema compliance, SQLite sync, graph, state, bookkeeping |
| Error Handling | 4 | `dry_run=True` default is excellent defensive design |
| API Surface | 4 | Clean: check_health, repair_all, recover_entity, rollback_entity, recover_from_crash |
| Thread Safety | 1 | No locking; repair operations modify files |
| Test Coverage | 1 | **NO TESTS EXIST** for this module |
| Code Quality | 3 | Third copy of _clean_schema_for_validation; uses private API of bookkeeper |

**Specific Issues:**

| Severity | Issue | Location |
|---|---|---|
| CRITICAL | **No tests exist.** This is the error recovery and repair module. A bug in `repair_all(dry_run=False)` could corrupt healthy entities while attempting to fix broken ones. Untested recovery code is worse than no recovery code -- it gives false confidence. | N/A |
| HIGH | `_log_recovery_action` calls `bk._append_event()` -- a private method of BookkeepingManager (note the underscore prefix). If the BookkeepingManager's internal implementation changes, this will break silently. Should use a public API method instead. | Lines ~1700-1720 |
| HIGH | `_find_backup_for_file(file_path)` matches backup ZIPs by checking if the file's basename is a substring of the ZIP's member names. This could match the wrong file if two entities have overlapping names (e.g., "thorin.json" would match "thorin-junior.json"). | Lines ~1400-1440 |
| MEDIUM | `_clean_schema_for_validation` is the third copy of this function (also in data_manager.py, consistency_checker.py). | Lines ~200-230 |
| MEDIUM | `recover_from_crash()` attempts to detect incomplete writes by checking file sizes and JSON parse-ability. A file that is valid JSON but contains partial/incorrect data (e.g., a write that completed but with wrong content) would not be detected. | Lines ~1500-1550 |
| LOW | `generate_health_report()` produces a long string by concatenation. Could use a template for better maintainability. | Lines ~1800-1875 |

---

## Hook Files Audit

**Files:** `C:\Worldbuilding-Interactive-Program\hooks\`

All 6 hooks follow a consistent pattern: read state.json, initialize engine modules, perform their specific task, print output to stdout. This is well-designed for Claude Code's hook system.

### Cross-Cutting Hook Issues

| Severity | Issue | Files Affected |
|---|---|---|
| HIGH | Every hook re-imports and re-initializes engine modules from scratch. `validate_writes.py` creates a new ConsistencyChecker, SQLiteSyncEngine, WorldGraph, and BookkeepingManager on every single file write. For a session with 20 entity writes, this means 80 module initializations. | All 6 hooks |
| HIGH | `validate_writes.py` calls `wg.build_graph()` (rebuilds the entire graph from disk) followed immediately by `wg.add_entity()`. The build_graph already includes all entities; the add_entity is redundant and adds duplicate edges. | `validate_writes.py` lines 130-133 |
| HIGH | `inject_step_context.py` calls `frm.save_state()` on every user message. This mutates the fair representation state for every message, not just when options are actually generated. The selection counter increments even on simple "hello" messages. | `inject_step_context.py` lines 75 |
| MEDIUM | `save_checkpoint.py` calls `bk._append_event()` (private method) directly instead of using a public BookkeepingManager API. Same issue as error_recovery.py. | `save_checkpoint.py` line 109 |
| MEDIUM | `_safe_read_json` is copy-pasted into all 6 hooks and all 10 engine modules. This is 16 copies of the same 6-line function. | All hooks |
| MEDIUM | `check_completion.py` calls `cp._get_step_info()` (private method) to get step titles. Should use a public API. | `check_completion.py` lines 74, 80 |
| LOW | `session_start.py` and `end_session.py` both create a new SQLiteSyncEngine but handle the connection lifecycle differently. start opens but never explicitly closes; end closes explicitly. | `session_start.py`, `end_session.py` |
| LOW | All hooks use hardcoded `PROJECT_ROOT = "C:/Worldbuilding-Interactive-Program"`. This will break if the project is relocated. Should be derived from the hook file's own path. | All 6 hooks |

---

## Cross-Cutting Issues

These issues affect multiple modules and require systemic fixes.

### 1. No Atomic File Writes (CRITICAL)

**Affects:** data_manager.py, bookkeeper.py, fair_representation.py, option_generator.py, backup_manager.py, error_recovery.py, save_checkpoint.py

Every module writes JSON files using:
```python
with open(path, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2)
```

If the process crashes, the OS loses power, or the write is interrupted, the file is left in a corrupt state (truncated or empty). The fix is standard:

```python
import tempfile
fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
try:
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp_path, path)  # atomic on POSIX; near-atomic on Windows NTFS
except:
    os.unlink(tmp_path)
    raise
```

### 2. No Thread Safety (CRITICAL)

**Affects:** All 10 modules

The PySide6 desktop app will need to run engine operations on background threads (QThread or QRunnable) to keep the UI responsive. Currently:
- No module uses `threading.Lock` or `threading.RLock`
- File read/write operations are unprotected
- In-memory caches (consistency_checker._entity_cache, graph_builder._graph) are shared mutable state
- SQLite connection is single-threaded by default

**Recommended approach:** Create a singleton `EngineManager` that owns all module instances and serializes access via a lock, or use per-module locks for finer granularity.

### 3. Duplicated Utility Code (MEDIUM)

**Affects:** All modules and hooks

| Function | Copies | Locations |
|---|---|---|
| `_safe_read_json` | 16+ | All 10 engine modules + all 6 hooks |
| `_safe_write_json` | 8+ | data_manager, bookkeeper, fair_representation, option_generator, backup_manager, error_recovery, save_checkpoint, session_start |
| `_clean_schema_for_validation` | 3 | data_manager.py, consistency_checker.py, error_recovery.py |

**Fix:** Create `engine/utils.py` with shared helpers. All modules import from there.

### 4. Broad Exception Swallowing (HIGH)

**Affects:** option_generator.py, chunk_puller.py, graph_builder.py, all hooks

Pattern:
```python
try:
    # complex operation
except Exception:
    pass  # or: return empty default
```

This makes debugging nearly impossible. At minimum, these should log the exception with `logging.exception()` or `traceback.format_exc()`. In a desktop app, swallowed exceptions mean the user sees wrong results with no explanation.

### 5. Hardcoded Project Root (LOW-MEDIUM)

**Affects:** All 6 hooks

All hooks use `PROJECT_ROOT = "C:/Worldbuilding-Interactive-Program"`. This:
- Breaks if the user installs the app elsewhere
- Prevents running tests from a different location
- Prevents multiple worlds on the same machine

Should be: `PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))`

---

## Test Coverage Analysis

**Test Directory:** `C:\Worldbuilding-Interactive-Program\tests\`

### Coverage Summary

| Module | Test File | Tests | Coverage Assessment |
|---|---|---|---|
| data_manager.py | test_data_manager.py | 20 | Good: CRUD, validation, prose, canon claims, custom prose |
| bookkeeper.py | test_bookkeeper.py | ~15 | Good: All event types, sessions, indexes |
| graph_builder.py | test_graph_builder.py | ~14 | Good: Build, add/remove, relationships, paths, clusters |
| chunk_puller.py | test_chunk_puller.py | ~10 | Adequate: Structure, multiple steps, dependencies |
| fair_representation.py | test_fair_representation.py | ~8 | Good: Selection, anti-repetition, 52-step coverage, fairness |
| option_generator.py | test_option_generator.py | ~12 | Adequate: Structure, anti-repetition, concepts, context |
| consistency_checker.py | test_consistency_checker.py | ~18 | Good: All 3 layers, human messages, pipeline, edge cases |
| sqlite_sync.py | test_sqlite_sync.py | ~20 | Good: Sync, search, queries, SQL safety, stats, context manager |
| backup_manager.py | **NONE** | 0 | **CRITICAL GAP** |
| error_recovery.py | **NONE** | 0 | **CRITICAL GAP** |

### Missing Test Scenarios (across all tested modules)

| Module | Missing Test |
|---|---|
| data_manager.py | Concurrent create/update; corrupt JSON file recovery; very large entity (>1MB) |
| bookkeeper.py | Corrupt JSONL line recovery; concurrent append; very large event log (10k+) |
| graph_builder.py | Graph with 500+ nodes performance; circular relationship handling |
| chunk_puller.py | Step with unmet dependencies behavior; corrupt guidance data |
| option_generator.py | Subsystem initialization failure; all subsystems fail simultaneously |
| consistency_checker.py | Stale cache detection; concurrent validation of same entity |
| sqlite_sync.py | Database file locked by another process; corrupt FTS5 index recovery |

### Test Infrastructure Assessment

The `conftest.py` fixture system is well-designed:
- `temp_world` creates a full temporary project structure with state.json, template_registry.json, sample entities, and concept bank
- `sample_god_data` and `sample_settlement_data` provide reusable test fixtures
- `sample_template` provides a god-profile schema for direct validation tests

**No integration tests exist.** There are no tests that exercise the full pipeline: hook -> engine module -> file write -> consistency check -> SQLite sync -> graph update. This is a significant gap for a system where modules are tightly orchestrated by hooks.

---

## Prioritized Fix List

### CRITICAL (Must fix before production)

| # | Issue | Module(s) | Effort |
|---|---|---|---|
| C1 | Implement atomic file writes (temp-file-then-rename) for all JSON/JSONL writes | All modules | 2-3 days |
| C2 | Add threading.Lock to all file I/O and shared mutable state | All modules | 3-4 days |
| C3 | Write comprehensive tests for backup_manager.py | backup_manager.py | 2 days |
| C4 | Write comprehensive tests for error_recovery.py | error_recovery.py | 2 days |
| C5 | Fix OptionGenerator eager initialization -- use lazy loading or dependency injection | option_generator.py | 1 day |
| C6 | Fix `_add_inbound_edges_for` O(n) file scan on every `add_entity()` call | graph_builder.py | 1 day |

### HIGH (Should fix before production)

| # | Issue | Module(s) | Effort |
|---|---|---|---|
| H1 | Replace broad `except Exception: pass` with proper logging throughout | option_generator.py, chunk_puller.py, all hooks | 1-2 days |
| H2 | Fix `advanced_query` SQL injection protection -- use SQL parser or whitelist approach | sqlite_sync.py | 0.5 day |
| H3 | Add cache invalidation to consistency_checker._entity_cache | consistency_checker.py | 0.5 day |
| H4 | Fix `restore_backup` to extract to temp dir first, then swap | backup_manager.py | 0.5 day |
| H5 | Fix unbound `tmp_path` variable in backup creation exception handler | backup_manager.py | 0.5 hour |
| H6 | Stop calling private `_append_event` from hooks and error_recovery | error_recovery.py, save_checkpoint.py | 0.5 day |
| H7 | Fix validate_writes.py redundant build_graph + add_entity | validate_writes.py | 0.5 hour |
| H8 | Fix inject_step_context.py incrementing fair representation on every message | inject_step_context.py | 0.5 hour |
| H9 | Cache session number in bookkeeper instead of scanning all events | bookkeeper.py | 0.5 day |
| H10 | Fix `_find_backup_for_file` substring matching that can match wrong files | error_recovery.py | 0.5 day |

### MEDIUM (Should fix soon after launch)

| # | Issue | Module(s) | Effort |
|---|---|---|---|
| M1 | Extract `_safe_read_json`, `_safe_write_json`, `_clean_schema_for_validation` into shared `engine/utils.py` | All modules, all hooks | 1 day |
| M2 | Add SQLite `check_same_thread=False` with threading.Lock wrapper | sqlite_sync.py | 0.5 day |
| M3 | Document `check_semantic` implicit LLM review contract in API docstring | consistency_checker.py | 0.5 hour |
| M4 | Add progress callbacks for full_sync, backup creation, restore | sqlite_sync.py, backup_manager.py | 1 day |
| M5 | Replace hardcoded PROJECT_ROOT in all hooks with path-derived value | All 6 hooks | 0.5 hour |
| M6 | Reduce hook initialization overhead (share engine instances across hooks or use a daemon) | All 6 hooks | 2-3 days |
| M7 | Add integration tests for the full hook-to-engine pipeline | tests/ | 2 days |

### LOW (Nice to have)

| # | Issue | Module(s) | Effort |
|---|---|---|---|
| L1 | Refactor 14 prose functions into a dispatch table | data_manager.py | 1 day |
| L2 | Move step definitions from inline dicts to JSON config files | chunk_puller.py | 0.5 day |
| L3 | Make mythologies/authors configurable from JSON | fair_representation.py | 0.5 hour |
| L4 | Combine get_stats() into a single SQL query | sqlite_sync.py | 0.5 hour |
| L5 | Add optional seed parameter to FairRepresentationManager for reproducibility | fair_representation.py | 0.5 hour |
| L6 | Add weighted edges support to WorldGraph | graph_builder.py | 1 day |

---

## Overall Assessment

### Scorecard

| Module | Robustness | Validation | Error Handling | API | Thread Safety | Tests | Code Quality | **Verdict** |
|---|---|---|---|---|---|---|---|---|
| data_manager.py | 3 | 4 | 3 | 4 | 1 | 4 | 3 | **Needs Minor Fixes** |
| bookkeeper.py | 3 | 3 | 3 | 4 | 1 | 4 | 4 | **Needs Minor Fixes** |
| graph_builder.py | 3 | 2 | 2 | 4 | 1 | 4 | 3 | **Needs Minor Fixes** |
| chunk_puller.py | 4 | 3 | 2 | 4 | 2 | 4 | 3 | **Ready** |
| fair_representation.py | 4 | 3 | 3 | 4 | 1 | 4 | 4 | **Ready** |
| option_generator.py | 3 | 3 | 1 | 4 | 1 | 3 | 2 | **Needs Major Work** |
| consistency_checker.py | 4 | 4 | 3 | 4 | 1 | 4 | 3 | **Needs Minor Fixes** |
| sqlite_sync.py | 4 | 3 | 3 | 4 | 2 | 4 | 4 | **Needs Minor Fixes** |
| backup_manager.py | 4 | 3 | 3 | 4 | 1 | 1 | 3 | **Needs Major Work** |
| error_recovery.py | 4 | 4 | 4 | 4 | 1 | 1 | 3 | **Needs Major Work** |

### Summary Verdicts

- **Ready (2 modules):** chunk_puller.py, fair_representation.py
- **Needs Minor Fixes (5 modules):** data_manager.py, bookkeeper.py, graph_builder.py, consistency_checker.py, sqlite_sync.py
- **Needs Major Work (3 modules):** option_generator.py, backup_manager.py, error_recovery.py

### Architecture Strengths

1. **Event sourcing** in bookkeeper.py is an excellent choice for audit trails and replay
2. **Three-layer validation** (schema, rules, semantic) is thorough and well-layered
3. **FTS5 search** is the right tool for entity search at this scale
4. **Fair representation algorithm** is clever and ensures diversity
5. **52-step guidance system** with dependencies is well-structured
6. **dry_run=True default** in error_recovery.py shows good defensive thinking
7. **Pre-restore safety backups** in backup_manager.py show good data safety awareness
8. **Hook architecture** cleanly separates Claude Code lifecycle management from engine logic

### Architecture Weaknesses

1. **No concurrency story.** The single biggest risk for the PySide6 desktop app
2. **No shared utility layer.** 16+ copies of the same helper functions
3. **No integration tests.** Modules are tested in isolation but never as a system
4. **Silent failure culture.** Too many `except Exception: pass` blocks
5. **Eager initialization.** OptionGenerator (and hooks) pay full startup cost regardless of what is needed

### Final Recommendation

The engine layer has strong bones but is not production-ready. The two blocking issues are:

1. **Thread safety must be added before shipping the PySide6 app.** Without it, the app will experience data corruption under normal usage patterns (background save while user browses entities, concurrent hook executions, etc.).

2. **backup_manager and error_recovery must have tests before shipping.** These are the data safety net. Untested safety code is dangerous.

Estimated total effort for all CRITICAL fixes: **11-15 developer-days.**
Estimated total effort for CRITICAL + HIGH fixes: **16-22 developer-days.**

Once the CRITICAL and HIGH items are addressed, this engine will be robust enough for production use. The architectural decisions are sound -- the implementation just needs reliability hardening.
