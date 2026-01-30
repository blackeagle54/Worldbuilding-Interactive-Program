# Worldbuilding Interactive Program

## What This Is

An interactive worldbuilding tool based on "The Complete Art of World Building" by Randy Ellefson. The system guides users through 52 structured progression steps across 12 phases, using **three-layer guidance** (book quotes, synthesized references, actionable output) and **2-4 option generation** at every creative decision point. Options are the most important feature -- everything else exists to make option generation informed and coherent.

## Critical Rules

- **Commit after every significant step.** Never let work accumulate uncommitted.
- **Use Opus-level agents** for research, analysis, and complex tasks.
- **The user is non-technical.** All messages must be friendly and clear. Never ask the user to run commands.
- **Never use external APIs.** Everything runs locally with Claude Code. Sub-agents handle semantic checks.
- **JSON is source of truth.** SQLite (`runtime/worldbuilding.db`) is derived and rebuildable from JSON files.
- **Fair representation** across all 16 reference databases (10 mythologies + 6 authors). No single source dominates.
- **Record decisions** in `docs/decisions.md`. **Update progress** in `docs/progress.md`.

## Directory Structure

```
C:\Worldbuilding-Interactive-Program\
|-- source-text.txt                  # Ellefson book full text (read-only)
|-- progression-map.md               # 52 steps across 12 phases
|-- phase2-plan-revised.md           # Full architecture plan
|
|-- reference-databases/             # 16 reference databases (read-only)
|   |-- mythologies/                 # 10: greek, roman, norse, celtic, chinese,
|   |                                #     japanese, native-american, mesopotamian, hindu, biblical
|   |-- authors/                     # 6: tolkien, martin, rothfuss, berg, lovecraft, jordan
|
|-- templates/                       # 85 JSON schema templates across 12 phases
|   |-- phase01-foundation/ ... phase12-integration/
|
|-- engine/                          # Core Python modules
|   |-- template_registry.json       # Master list of all 85 templates with metadata
|   |-- reference_index.json         # Maps 52 steps -> relevant DB sections
|   |-- source_index.json            # Maps 52 steps -> source-text.txt line ranges
|   |-- data_manager.py              # Entity CRUD, schema validation, prose generation
|   |-- bookkeeper.py                # Event-sourced decision/session tracking
|   |-- graph_builder.py             # NetworkX in-memory knowledge graph
|   |-- chunk_puller.py              # Three-layer guidance generator
|   |-- fair_representation.py       # Balanced DB sampling across 16 sources
|   |-- option_generator.py          # Divergent-convergent 2-4 option pipeline
|   |-- consistency_checker.py       # Three-layer validation (schema, rules, semantic)
|   |-- sqlite_sync.py              # JSON-to-SQLite sync + FTS5 search
|   |-- backup_manager.py           # Automated timestamped backups
|   |-- error_recovery.py           # Graceful failure handling with friendly messages
|
|-- hooks/                           # 6 Claude Code hook scripts
|   |-- session_start.py             # SessionStart: load state, rebuild SQLite/graph
|   |-- inject_step_context.py       # UserPromptSubmit: inject guidance + canon context
|   |-- validate_writes.py           # PostToolUse: three-layer validation on user-world/ writes
|   |-- check_completion.py          # PostToolUse: verify step requirements
|   |-- save_checkpoint.py           # PreCompact: snapshot state before compaction
|   |-- end_session.py               # SessionEnd: session summary + git commit
|
|-- user-world/                      # All user-created world data
|   |-- state.json                   # Current step, completed steps, entity index, usage counts
|   |-- entities/                    # One JSON file per created entity (gods, species, etc.)
|   |-- worksheets/                  # Completed worksheets and checklists
|   |-- registries/                  # Name registry, settlement spreadsheet
|   |-- timelines/                   # History timeline entries
|   |-- travel/                      # Travel calculators
|   |-- maps/                        # Map checklists
|
|-- bookkeeping/                     # Event-sourced tracking (never edited, only appended)
|   |-- events/                      # Append-only JSONL event logs (events-YYYY-MM.jsonl)
|   |-- indexes/                     # Derived JSON indexes (decisions, progression, entities, xrefs, contradictions)
|   |-- revisions/                   # Entity revision history + old version snapshots
|   |-- sessions/                    # Structured session summaries (Markdown)
|   |-- snapshots/                   # Periodic full-state snapshots
|
|-- generation/                      # Option generation tracking
|   |-- option-history.jsonl         # All previously generated options and themes
|   |-- concept-bank.json            # Evocative words for random creative injection
|
|-- runtime/                         # SQLite database (derived, .gitignored)
|-- backups/                         # Timestamped backup copies
|-- tests/                           # Automated test suite (smoke, schema, integration, consistency)
|
|-- docs/
|   |-- decisions.md                 # All project decisions
|   |-- progress.md                  # Current progress tracker
|
|-- .claude/
|   |-- settings.json                # Hook configuration (6 hooks)
|   |-- rules/                       # Scoped instruction files
```

## Engine Modules

| Module | Class/Purpose |
|---|---|
| `data_manager.py` | `DataManager` -- Entity CRUD, schema validation with jsonschema, ID generation (slug + 4-hex), canon_claims extraction, prose generation |
| `bookkeeper.py` | `BookkeepingManager` -- Append-only event log, derived indexes, session summaries. Event types: session_started, decision_made, draft_created, status_changed, entity_revised, cross_reference_created, contradiction_found/resolved, step_status_changed, session_ended |
| `graph_builder.py` | `GraphBuilder` -- NetworkX directed graph from entity cross-references. Provides neighbor queries, path finding, community detection, orphan detection |
| `chunk_puller.py` | `ChunkPuller` -- Produces three-layer guidance: (1) book quotes from source-text.txt, (2) synthesized references from all 16 DBs with fair rotation, (3) actionable template output with existing canon awareness |
| `fair_representation.py` | `FairRepresentation` -- Selects 4 featured mythologies + 3 featured authors per step, rotating by lowest usage count |
| `option_generator.py` | `OptionGenerator` -- Divergent phase (6-8 raw ideas) -> convergent phase (filter, score diversity) -> flesh out phase (2-4 complete standalone options). Uses concept-bank for random injection, tracks history to avoid repetition |
| `consistency_checker.py` | `ConsistencyChecker` -- Layer 1: JSON schema validation. Layer 2: rule-based cross-reference checks. Layer 3: LLM semantic check via Claude Code sub-agents (no external API) |
| `sqlite_sync.py` | `SQLiteSync` -- Syncs all JSON entity files to SQLite with FTS5 full-text search. Tables: entities, cross_references, canon_claims, entity_search |
| `backup_manager.py` | `BackupManager` -- Timestamped copies of user-world/ and bookkeeping/. Keeps last 20, auto-rotates |
| `error_recovery.py` | `ErrorRecovery` -- Handles malformed JSON, corrupted SQLite, missing references, schema failures. All messages human-friendly |

## Templates

85 templates across 12 phases (registered in `engine/template_registry.json`):

| Phase | Name | Steps |
|---|---|---|
| 01 | Foundation | Steps 1-4 |
| 02 | Cosmology | Steps 5-10 |
| 03 | The Land | Steps 11-16 |
| 04 | Life | Steps 17-22 |
| 05 | Civilization | Steps 23-30 |
| 06 | Society | Steps 31-37 |
| 07 | The Supernatural | Steps 38-41 |
| 08 | History & Legend | Steps 42-45 |
| 09 | Language & Names | Steps 46-47 |
| 10 | Travel & Scale | Steps 48-49 |
| 11 | Finishing Touches | Steps 50-51 |
| 12 | Integration | Step 52 |

## Key Design Decisions

1. **Three-layer guidance**: Every step delivers book quotes, synthesized cross-database references, and actionable templates
2. **Option generation (MOST IMPORTANT)**: 2-4 complete, standalone options at every decision. Each accounts for all existing canon. Each draws from different mythological/authorial traditions
3. **Fair representation**: All 16 reference databases get roughly equal airtime across 52 steps
4. **Canon consistency**: Three-layer validation (schema, rules, semantic). Semantic layer uses Claude Code sub-agents, NOT external APIs
5. **Event-sourced bookkeeping**: Append-only JSONL events are source of truth. Indexes are derived and rebuildable
6. **JSON source of truth**: All entity data stored as JSON files (human-readable, Git-friendly). SQLite is runtime-only
7. **NetworkX over MCP**: In-memory graph sufficient for initial scale (<1000 entities). ChromaDB planned for later

## Dependencies

- `jsonschema` -- JSON Schema validation
- `networkx` -- In-memory knowledge graph
- `pytest` -- Test suite (dev only)
- Python 3.13 standard library (sqlite3, json, datetime, shutil, hashlib)
- No external APIs, no Docker, no cloud services

## How to Run

- **Tests**: `pytest tests/` (when test suite exists)
- **Smoke tests**: `pytest tests/smoke/` (quick health check)
- **Individual modules**: `python -c "from engine.data_manager import DataManager; ..."`
- **Hooks run automatically** via `.claude/settings.json` -- no manual invocation needed

## Project Context

@docs/decisions.md
@docs/progress.md

## Git

- Repository: https://github.com/blackeagle54/Worldbuilding-Interactive-Program
- Commit frequently with descriptive messages
- Treat this as a professional project with clean commit history
