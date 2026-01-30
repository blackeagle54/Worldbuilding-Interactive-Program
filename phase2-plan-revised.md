# Phase 2 Implementation Plan -- REVISED

**Purpose:** Turn the 52-step progression map and 85 template list into a working system that guides a user through worldbuilding with intelligent reference support, option generation, canon consistency checking, and full bookkeeping.

**Date:** January 30, 2026 (Revised)
**Revises:** `phase2-plan.md` (original)

**Why this revision exists:** The original plan was written before six critical research documents were completed (retrieval, bookkeeping, scale gaps, consistency, orchestration, memory). This revised plan integrates ALL findings from those research efforts into concrete sprint tasks.

---

## Table of Contents

1. [What Has Changed](#what-has-changed)
2. [What Sprint 1 Already Delivered](#what-sprint-1-already-delivered)
3. [Revised Architecture Overview](#revised-architecture-overview)
4. [Sprint 2: The Engine Layer](#sprint-2-the-engine-layer)
5. [Sprint 3: The Intelligence Layer](#sprint-3-the-intelligence-layer)
6. [Sprint 4: The Safety and Polish Layer](#sprint-4-the-safety-and-polish-layer)
7. [Dependency Map](#dependency-map)
8. [What Success Looks Like](#what-success-looks-like)
9. [What This Plan Does NOT Cover](#what-this-plan-does-not-cover)

---

## What Has Changed

The original plan had six tasks (A through F). Sprint 1 completed Tasks A, B, and D. The remaining tasks (C, E, F) are now redesigned to incorporate these research findings:

| Research Document | Key Changes to the Plan |
|---|---|
| **Retrieval Research** | Replace the MCP Knowledge Graph with a phased approach: start with structured JSON + NetworkX in-memory graph (free, instant). Plan for ChromaDB later. Use sub-agents for contradiction detection instead of external API calls. |
| **Bookkeeping Research** | Add an append-only JSONL event log as the source of truth for all decisions, drafts, revisions, and session history. Add six derived index files for fast querying. Add session summary markdown files. |
| **Scale Gaps Research** | Add a dual-layer architecture: JSON files remain the source of truth (human-readable, Git-friendly) but SQLite becomes the runtime query engine. Add FTS5 full-text search. Add content diversity techniques for option generation. Add backup system. Add testing/validation suite. Add human-readable error recovery. |
| **Consistency Research** | Implement three-layer validation: (1) JSON schema checks, (2) rule-based cross-reference checks, (3) LLM semantic checks via Claude Code sub-agents (NOT external API). Add `canon_claims` field to entity schemas. Wire validation into PostToolUse hooks. |
| **Orchestration Research** | Add UserPromptSubmit hooks for context injection. Add Stop hooks for completion verification. Add PreCompact hooks for state checkpointing. Build dynamic system prompts that change based on the current progression step. |
| **Decisions Log** | The option generation system (2-4 unique, fully fleshed out options at each step) is confirmed as the MOST IMPORTANT FEATURE. Everything else exists to support it. Options must draw from all 16 databases with fair representation and must account for all existing canon. |

---

## What Sprint 1 Already Delivered

These are complete and will not be touched:

| Deliverable | Location | Description |
|---|---|---|
| 85 JSON schema templates | `templates/phase01-foundation/` through `templates/phase12-integration/` | One schema per template, defining fields, types, required fields, and cross-references via `x-cross-reference` |
| User-world folder structure | `user-world/` | Entity folders by type (gods, species, settlements, etc.), worksheets, registries, timelines, travel, maps |
| State tracking file | `user-world/state.json` | Tracks current step, completed steps, entity index, session log |
| Reference database index | `engine/reference_index.json` | Maps each of the 52 steps to the relevant sections in all 16 reference databases |
| Source text index | `engine/source_index.json` | Maps each of the 52 steps to the relevant line ranges in `source-text.txt` |

---

## Revised Architecture Overview

```
C:\Worldbuilding-Interactive-Program\
|
|-- source-text.txt                          # The Ellefson book (read-only)
|-- reference-databases\                     # 16 .md files (read-only)
|   |-- mythologies\                         # 10 mythology databases
|   |-- authors\                             # 6 author databases
|
|-- templates\                               # [SPRINT 1 - DONE] 85 JSON schema files
|   |-- phase01-foundation\ ... phase12-integration\
|
|-- user-world\                              # [SPRINT 1 - DONE] Where user data lives
|   |-- state.json                           # Progression state
|   |-- entities\                            # One JSON file per created entity
|   |-- worksheets\                          # Completed worksheets/checklists
|   |-- registries\                          # Name registry, settlement spreadsheet, etc.
|   |-- timelines\                           # History timeline entries
|   |-- travel\                              # Travel calculators
|   |-- maps\                                # Map checklists
|
|-- engine\                                  # [SPRINT 1 PARTIAL + SPRINT 2]
|   |-- reference_index.json                 # [DONE] Step -> DB section mapping
|   |-- source_index.json                    # [DONE] Step -> source-text line ranges
|   |-- template_registry.json               # [SPRINT 2] Master list of all 85 templates
|   |-- chunk_puller.py                      # [SPRINT 2] Three-layer guidance generator
|   |-- fair_representation.py               # [SPRINT 2] Balanced DB sampling
|   |-- option_generator.py                  # [SPRINT 2] Divergent-convergent option pipeline
|   |-- data_manager.py                      # [SPRINT 2] Create/read/update/validate entities
|   |-- cross_reference.py                   # [SPRINT 2] Cross-reference validation
|   |-- graph_builder.py                     # [SPRINT 2] NetworkX in-memory graph from entities
|   |-- sqlite_sync.py                       # [SPRINT 3] JSON-to-SQLite sync + FTS5 search
|   |-- consistency_checker.py               # [SPRINT 3] Three-layer consistency validation
|   |-- bookkeeper.py                        # [SPRINT 2] Event log + derived index manager
|
|-- bookkeeping\                             # [SPRINT 2] Decision/session/revision tracking
|   |-- events\                              # Append-only JSONL event logs
|   |   |-- events-YYYY-MM.jsonl             # One file per month
|   |-- indexes\                             # Derived JSON indexes for fast querying
|   |   |-- decisions.json                   # All decisions with options and rationale
|   |   |-- progression.json                 # Status of all 52 steps
|   |   |-- entity-registry.json             # All entities with status and revision count
|   |   |-- cross-references.json            # All entity-to-entity links
|   |   |-- contradictions.json              # All contradictions found and resolutions
|   |-- revisions\
|   |   |-- revisions-by-entity.json         # Full revision history per entity
|   |   |-- snapshots\                       # Old versions of revised entities
|   |-- sessions\                            # Structured session summaries (Markdown)
|   |   |-- session-YYYY-MM-DD-NNN.md
|   |-- snapshots\                           # Periodic full-state snapshots
|
|-- generation\                              # [SPRINT 2] Content diversity tracking
|   |-- option-history.jsonl                 # Previously generated options and themes
|   |-- concept-bank.json                    # Curated evocative words for random injection
|
|-- hooks\                                   # [SPRINT 3] Claude Code hook scripts
|   |-- session_start.py                     # Load state, display current step
|   |-- inject_step_context.py               # Inject guidance + canon context per prompt
|   |-- validate_writes.py                   # Three-layer validation after file writes
|   |-- check_completion.py                  # Verify step requirements before stopping
|   |-- save_checkpoint.py                   # Checkpoint state before context compaction
|   |-- end_session.py                       # Generate session summary, commit to git
|
|-- backups\                                 # [SPRINT 4] Automated backup directory
|   |-- YYYY-MM-DD_HH-MM\                   # Timestamped backup copies
|
|-- tests\                                   # [SPRINT 4] Automated test suite
|   |-- smoke\                               # Quick health checks (< 30 seconds)
|   |-- schemas\                             # Validate all 85 schemas
|   |-- integration\                         # Full workflow tests
|   |-- consistency\                         # Contradiction detection tests
|
|-- runtime\                                 # [SPRINT 3] Runtime database
|   |-- worldbuilding.db                     # SQLite database (derived from JSON files)
|
|-- .claude\
|   |-- settings.json                        # [SPRINT 3] Hook configuration
|   |-- rules\                               # Rule files for Claude Code
```

---

## Sprint 2: The Engine Layer

**Goal:** Build the core systems that power the worldbuilding experience -- the chunk puller that produces three-layer guidance, the option generator that creates 2-4 unique choices, the bookkeeping system that tracks every decision, and the data manager that keeps entities organized.

**Depends on:** Sprint 1 (complete).

**Everything in this sprint is built by Claude Code. The user does not touch any of it.**

---

### Task 2A: Template Registry

**What it is:** A master JSON file that lists all 85 templates with their metadata, so any script can look up what templates belong to which step.

**What it produces:** `engine/template_registry.json`

**Structure:**
```json
{
  "templates": [
    {
      "number": 6,
      "id": "god-profile",
      "title": "God Profile Template",
      "file": "templates/phase02-cosmology/06-god-profile.json",
      "step": 7,
      "phase": 2,
      "entity_type": "gods",
      "entity_folder": "user-world/entities/gods/",
      "is_multi_instance": true,
      "minimum_count": 3,
      "cross_references": ["pantheon-overview", "mythology-worksheet", "species-profile", "religion-profile"]
    }
  ]
}
```

**Key fields:**
- `is_multi_instance`: Whether the user creates multiple entities from this template (true for gods, species, etc.) or fills it out once (true for worksheets).
- `minimum_count`: How many entities are recommended before moving on.
- `entity_folder`: Where instances of this template are stored in `user-world/`.

**How to build it:** A Python script reads all 85 template JSON files from `templates/`, extracts their metadata (`$id`, `step`, `phase`, cross-references), and writes the registry.

---

### Task 2B: Data Manager

**What it is:** A Python module that handles all entity creation, reading, updating, and validation. Every other system calls the data manager rather than reading/writing entity files directly.

**What it produces:** `engine/data_manager.py`

**Functions it provides:**

| Function | What It Does |
|---|---|
| `create_entity(template_id, data)` | Validates data against the template schema, assigns a unique ID (slugified name + 4-character random suffix), saves the entity JSON file to the correct folder, updates `user-world/state.json`, and returns the entity ID. |
| `update_entity(entity_id, data)` | Validates the updated data, saves a revision snapshot of the old version to `bookkeeping/revisions/snapshots/`, writes the updated entity, and logs the revision. |
| `get_entity(entity_id)` | Loads and returns an entity by ID. |
| `list_entities(entity_type)` | Returns all entities of a given type (e.g., all gods, all settlements). |
| `get_cross_references(entity_id)` | Finds all entities that reference this one AND all entities this one references. Returns a bidirectional map. |
| `validate_entity(entity_id)` | Runs schema validation against the entity's template. Returns a list of errors (empty if valid). |
| `search_entities(query)` | Searches entity names, tags, and descriptions for a keyword. (Simple keyword search initially; upgraded to SQLite FTS5 in Sprint 3.) |

**Schema validation:** Uses Python's `jsonschema` library to validate entity data against the template schemas created in Sprint 1.

**ID generation:** IDs are `{slugified-name}-{4-random-hex}`, for example `thorin-stormkeeper-a1b2`. This prevents collisions while keeping IDs human-readable.

**canon_claims field (from consistency research):** The data manager ensures every entity has a `canon_claims` array. When an entity is created or updated, the data manager extracts discrete factual claims from the entity's data and populates this field. These claims are what the consistency checker (Sprint 3) uses for precise contradiction detection.

Example `canon_claims` on a god entity:
```json
"canon_claims": [
  {
    "claim": "Thorin Stormkeeper's primary domain is storms",
    "references": []
  },
  {
    "claim": "Thorin Stormkeeper is the spouse of Mira Sunweaver",
    "references": ["mira-sunweaver-c3d4"]
  },
  {
    "claim": "Thorin Stormkeeper belongs to The Celestial Court pantheon",
    "references": ["the-celestial-court-e5f6"]
  }
]
```

---

### Task 2C: Bookkeeping System

**What it is:** An event-sourced bookkeeping system that silently records every decision, draft, revision, and session. The user never interacts with it directly -- Claude Code manages it automatically.

**What it produces:**
- `engine/bookkeeper.py` (the Python module)
- `bookkeeping/` folder structure with events, indexes, sessions, revisions, and snapshots

**Architecture (three layers):**

```
LAYER 1: Event Log (Source of Truth)
  - Append-only JSONL files in bookkeeping/events/
  - Every action is an event with timestamp, session ID, and full context
  - Never edited, only appended
  - One file per month (events-YYYY-MM.jsonl)

LAYER 2: Derived Index Files (Fast Querying)
  - bookkeeping/indexes/decisions.json
  - bookkeeping/indexes/progression.json
  - bookkeeping/indexes/entity-registry.json
  - bookkeeping/indexes/cross-references.json
  - bookkeeping/indexes/contradictions.json
  - bookkeeping/revisions/revisions-by-entity.json
  - These are DERIVED from Layer 1 and can always be rebuilt

LAYER 3: Session Summaries (Human-Readable)
  - bookkeeping/sessions/session-YYYY-MM-DD-NNN.md
  - Structured markdown with: steps worked on, decisions made,
    entities created/modified, contradictions resolved, notes
```

**Event types the bookkeeper records:**

| Event Type | When It Fires | What It Captures |
|---|---|---|
| `session_started` | Session begins | Session number, planned focus |
| `decision_made` | User picks an option | Question, all 2-4 options presented, chosen option, rejected options, user rationale |
| `draft_created` | New entity written | Entity ID, type, file path, status (draft), content hash |
| `status_changed` | Draft promoted to canon (or vice versa) | Entity ID, old status, new status, reason |
| `entity_revised` | Canon entity modified | Entity ID, revision number, change summary, reason, previous version snapshot path |
| `cross_reference_created` | Link between entities established | Source entity, target entity, relationship type, bidirectional flag |
| `contradiction_found` | Consistency checker flags a conflict | Entities involved, description, severity |
| `contradiction_resolved` | User resolves a conflict | Contradiction ID, resolution description, entities modified |
| `step_status_changed` | Step started/completed | Step ID, old status, new status |
| `session_ended` | Session closes | Steps worked on, decisions made, entities created/modified, summary |

**API the bookkeeper provides:**

```python
from engine.bookkeeper import BookkeepingManager

bk = BookkeepingManager("C:/Worldbuilding-Interactive-Program/bookkeeping")

bk.start_session(focus="Creating god profiles")
bk.record_decision(step_id="step-07", question="...", options=[...], chosen="A", rationale="...")
bk.record_entity_created(entity_id="...", entity_type="gods", ...)
bk.record_cross_reference(source="...", target="...", relationship="spouse", ...)
bk.end_session(summary="Created three gods for the Celestial Court pantheon.")
```

**Queryable questions the bookkeeping system answers:**

| Question | Source File |
|---|---|
| "What did I decide about the magic system?" | `decisions.json` (filter by step or keyword) |
| "What were the other options when I chose the government?" | `decisions.json` (read rejected options) |
| "Why did I make that choice?" | `decisions.json` (read rationale field) |
| "What did I do last session?" | Latest `session-*.md` |
| "What steps are still incomplete?" | `progression.json` (filter by status) |
| "Is this entity canon or still a draft?" | `entity-registry.json` (read status field) |
| "What references this entity?" | `cross-references.json` (filter by target) |
| "Are there unresolved contradictions?" | `contradictions.json` (filter by status) |
| "How has this entity changed over time?" | `revisions-by-entity.json` (read revision timeline) |

---

### Task 2D: In-Memory Knowledge Graph (NetworkX)

**What it is:** A lightweight, in-memory graph built from entity cross-references using Python's NetworkX library. This replaces the original plan's MCP Knowledge Graph server -- it is simpler, faster, has zero dependencies beyond `pip install networkx`, and is more than sufficient for the initial scale.

**What it produces:** `engine/graph_builder.py`

**Why NetworkX instead of the MCP Knowledge Graph:**
- The retrieval research recommends structured JSON + NetworkX as the Phase 1 retrieval approach (free, instant, no external services).
- The MCP Knowledge Graph stores data in a JSONL file and provides basic search -- NetworkX provides the same plus real graph algorithms (shortest path, community detection, centrality).
- The user's world will start small (under 100 entities). NetworkX handles thousands of nodes effortlessly in-memory.
- Upgrading to ChromaDB + Contextual Retrieval happens later (around 15,000 lines of content, per the retrieval research phased plan).

**What the graph contains:**

Each entity becomes a node with attributes:
- `entity_type` (god, species, settlement, etc.)
- `name`
- `file_path`
- `step_created`
- `status` (draft or canon)

Each cross-reference becomes a directed edge with attributes:
- `relationship_type` (worships, rules, inhabits, created, rivals, etc.)
- `source_field` (which schema field created this link)

**Functions it provides:**

| Function | What It Does |
|---|---|
| `build_graph()` | Reads all entity files, extracts cross-references, and builds the NetworkX graph. Called on session start. |
| `add_entity(entity_id, entity_data)` | Adds a single node (called when a new entity is created). |
| `add_relationship(source_id, target_id, rel_type)` | Adds a single edge. |
| `get_neighbors(entity_id, depth=1)` | Returns all entities within N relationship hops. |
| `get_related_entities(entity_id)` | Returns all directly connected entities with relationship types. |
| `find_path(entity_a, entity_b)` | Finds the shortest relationship path between two entities. |
| `get_entity_cluster(entity_id)` | Returns the community/cluster this entity belongs to (using Louvain community detection). |
| `get_orphans()` | Returns entities with zero connections (potential gaps). |
| `get_most_connected()` | Returns entities ranked by number of connections (the most important entities in the world). |

**When the graph is rebuilt:** At session start (from the entity files). During a session, it is updated incrementally as entities are created or modified.

---

### Task 2E: Chunk Puller (Three-Layer Guidance Generator)

**What it is:** The core intelligence engine. Given a progression step number, it produces the three-layer guidance document: book quotes, synthesized references, and actionable output with templates.

**What it produces:** `engine/chunk_puller.py`

**How it works (unchanged from original, but now integrated with new systems):**

```
User says: "I'm ready for Step 7"
    |
    v
chunk_puller.py receives step_number = 7
    |
    +-- Reads source_index.json -> Extracts book quotes from source-text.txt
    |
    +-- Reads reference_index.json -> Gets relevant sections from all 16 databases
    |
    +-- Calls fair_representation.py -> Selects 4 featured mythologies + 3 featured authors
    |   (rotating which ones are featured to ensure balanced coverage)
    |
    +-- Reads template_registry.json -> Loads the God Profile template schema
    |
    +-- [NEW] Reads user-world/state.json -> Gets existing entities and canon
    |   so guidance accounts for what the user has already built
    |
    +-- [NEW] Queries the NetworkX graph -> Gets related entities for context
    |
    v
Output: A structured three-layer guidance document
```

**The three layers:**

1. **Book Quotes and Teaching** -- 3-5 key quotes from `source-text.txt` with explanations of why each matters and how it applies to the user's specific world.

2. **Synthesized Reference Material** -- Examples from all 16 databases:
   - 4 featured mythologies with detailed analysis (2-3 paragraphs each)
   - 3 featured authors with detailed analysis (2-3 paragraphs each)
   - 9 brief mentions (one sentence each) for the remaining databases
   - Cross-cutting patterns identified across all sources

3. **Actionable Output** -- The template to fill in, with:
   - Required, recommended, and optional fields listed
   - 5-7 guided questions
   - Minimum entity count before moving on
   - [NEW] Awareness of existing entities: "You have already created 2 gods. You need at least 1 more before moving on."

---

### Task 2F: Fair Representation System

**What it is:** Ensures that no single mythology or author dominates the reference material across the 52 steps. Every database gets roughly equal airtime.

**What it produces:** `engine/fair_representation.py`

**Algorithm:**

1. Maintain a usage counter per database in `user-world/state.json` under `reference_usage_counts`.
2. For each step, select:
   - 4 mythologies (out of 10) as "featured" (longer excerpts, more detail)
   - 3 authors (out of 6) as "featured" (longer excerpts, more detail)
   - The remaining 9 get "brief mention" treatment
3. Selection prioritizes databases with the LOWEST usage count (least recently featured).
4. Over 52 steps, each mythology gets featured roughly 21 times and each author roughly 26 times.

**Source rotation (from scale gaps research):** The fair representation system also feeds into option generation. When generating 2-4 options, each option should be inspired by different mythological and authorial traditions. This prevents the world from becoming "Norse mythology with the serial numbers filed off."

---

### Task 2G: Option Generator

**What it is:** The MOST IMPORTANT system in the entire program. At each decision point, it generates 2-4 unique, fully fleshed out, standalone options for the user to choose from.

**What it produces:** `engine/option_generator.py` and `generation/option-history.jsonl` and `generation/concept-bank.json`

**How it works (divergent-convergent pipeline from scale gaps research):**

```
PHASE 1: DIVERGENT (Generate widely)
  |
  +-- Load current step's reference material (from chunk_puller)
  +-- Load ALL existing canon (entities, decisions, relationships)
  +-- Load option history (to avoid repeating themes)
  +-- Inject 1-2 random concepts from concept-bank.json
  +-- Rotate source databases (different inspirations per option)
  |
  +-- Generate 6-8 raw idea sketches
  |   Each sketch: 2-3 sentences capturing a unique creative direction
  |   Each inspired by different combinations of mythologies and authors
  |
  v
PHASE 2: CONVERGENT (Refine and select)
  |
  +-- Filter raw ideas: remove any that contradict existing canon
  +-- Filter raw ideas: remove any that repeat themes from option history
  +-- Score remaining ideas for diversity (theme overlap, vocabulary, structure)
  +-- Select top 2-4 most diverse, high-quality ideas
  |
  v
PHASE 3: FLESH OUT (Make each option standalone)
  |
  +-- For each selected idea, generate a COMPLETE option:
  |   - A name/title for the option
  |   - A full description (3-5 paragraphs)
  |   - How it connects to existing canon
  |   - What implications it would have for future steps
  |   - Which mythological/authorial traditions inspired it
  |
  v
OUTPUT: 2-4 fully fleshed out options presented to the user
  |
  +-- User picks one, combines elements, requests new ones, or goes custom
  +-- The chosen option (or hybrid) becomes canon
  +-- The bookkeeper records all options presented, which was chosen, and why
```

**Anti-repetition tracking (from scale gaps research):**
- `generation/option-history.jsonl` logs every set of options ever generated, including their themes, inspirations, and which were chosen/rejected.
- Before generating new options, the system reads the last 10-20 entries and tells Claude: "Avoid these previously used themes: [list]."

**Random concept injection (from scale gaps research):**
- `generation/concept-bank.json` contains 500-1000 evocative words and concepts (e.g., "erosion," "inheritance," "silence," "fermentation," "exile").
- 1-2 random concepts are injected into the generation prompt to push Claude into unexpected creative territory.

**Canon awareness:** Every option must account for everything already established in the user's world. The option generator pulls all relevant existing entities from the data manager and NetworkX graph and includes them in the generation context.

---

### Sprint 2 Task Summary

| Task | Description | Produces | Depends On |
|---|---|---|---|
| 2A | Template Registry | `engine/template_registry.json` | Sprint 1 templates |
| 2B | Data Manager | `engine/data_manager.py` | Sprint 1 templates + folders |
| 2C | Bookkeeping System | `engine/bookkeeper.py` + `bookkeeping/` folder | Nothing (can start immediately) |
| 2D | In-Memory Knowledge Graph | `engine/graph_builder.py` | 2B (needs entity data) |
| 2E | Chunk Puller | `engine/chunk_puller.py` | 2A, Sprint 1 indexes |
| 2F | Fair Representation | `engine/fair_representation.py` | 2A |
| 2G | Option Generator | `engine/option_generator.py` + `generation/` folder | 2B, 2D, 2E, 2F |

**What can run in parallel:**
- 2A, 2B, 2C can all start immediately
- 2D starts after 2B
- 2E starts after 2A
- 2F starts after 2A
- 2G starts after 2B, 2D, 2E, 2F are all done (it depends on everything)

**Critical path:** 2A + 2B (parallel) -> 2D + 2E + 2F (parallel) -> 2G

---

## Sprint 3: The Intelligence Layer

**Goal:** Wire everything together with Claude Code hooks that automatically inject context, validate writes, check consistency, and manage sessions. Add SQLite as the runtime query engine for fast search.

**Depends on:** Sprint 2 (all tasks).

---

### Task 3A: SQLite Sync Engine

**What it is:** A sync layer that converts all JSON entity files into a SQLite database on session startup. The JSON files remain the source of truth (human-readable, Git-friendly). SQLite is the runtime query engine (fast search, FTS5 full-text search, indexed lookups).

**What it produces:** `engine/sqlite_sync.py` and `runtime/worldbuilding.db`

**Why this architecture (from scale gaps research):**
- JSON files as source of truth: readable in any text editor, clean Git diffs, portable
- SQLite as runtime engine: millisecond queries instead of scanning hundreds of files
- A case study showed that migrating from thousands of JSON files to SQLite reduced startup time from 30 minutes to 10 seconds

**What the SQLite database contains:**

```sql
-- Main entity table
CREATE TABLE entities (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    name TEXT NOT NULL,
    template_id TEXT NOT NULL,
    status TEXT DEFAULT 'draft',     -- 'draft' or 'canon'
    step_created INTEGER,
    file_path TEXT NOT NULL,
    data JSON NOT NULL,              -- Full entity JSON
    created_at TEXT,
    updated_at TEXT
);

-- Cross-reference table
CREATE TABLE cross_references (
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    source_field TEXT,
    FOREIGN KEY (source_id) REFERENCES entities(id),
    FOREIGN KEY (target_id) REFERENCES entities(id)
);

-- Canon claims table (for contradiction checking)
CREATE TABLE canon_claims (
    entity_id TEXT NOT NULL,
    claim TEXT NOT NULL,
    references TEXT,                  -- JSON array of referenced entity IDs
    FOREIGN KEY (entity_id) REFERENCES entities(id)
);

-- Full-text search index
CREATE VIRTUAL TABLE entity_search USING fts5(
    name,
    entity_type,
    tags,
    description,
    canon_claims_text,
    content='entities',
    content_rowid='rowid',
    tokenize='porter unicode61'
);

-- Indexes for common queries
CREATE INDEX idx_entity_type ON entities(entity_type);
CREATE INDEX idx_entity_status ON entities(status);
CREATE INDEX idx_entity_step ON entities(step_created);
CREATE INDEX idx_xref_source ON cross_references(source_id);
CREATE INDEX idx_xref_target ON cross_references(target_id);
```

**Sync process:**
1. On session start: Read all JSON entity files, populate SQLite tables, build FTS5 index
2. During session: When an entity is created/updated via the data manager, update BOTH the JSON file AND the SQLite database
3. The SQLite database file (`runtime/worldbuilding.db`) is .gitignored -- it is always rebuilt from JSON

**What SQLite enables:**
- "Show me all coastal settlements" -> `SELECT * FROM entities WHERE entity_type = 'settlements' AND json_extract(data, '$.terrain') LIKE '%coast%'`
- "Find everything mentioning the Dragon Wars" -> `SELECT * FROM entity_search WHERE entity_search MATCH 'Dragon Wars'`
- "Which entities were created at step 7?" -> `SELECT * FROM entities WHERE step_created = 7`

---

### Task 3B: Three-Layer Consistency Checker

**What it is:** An automated system that validates every entity write against three layers of checks. Wired into the PostToolUse hook so it runs automatically after every file write to `user-world/`.

**What it produces:** `engine/consistency_checker.py`

**The three layers (from consistency research):**

```
Layer 1: Schema Validation (instant, free)
    Does the entity match its JSON schema?
    Are required fields present?
    Are field types correct?
    -> If FAILS: Block the write. Show human-readable error.
    |
    v
Layer 2: Rule-Based Cross-Reference Checks (instant, free)
    Do all referenced entity IDs actually exist?
    Are relationships bidirectional where required?
    Are numerical values consistent (dates, lifespans, populations)?
    Are category exclusions respected (mortal vs immortal, etc.)?
    -> If FAILS: Block the write. Show human-readable error.
    |
    v
Layer 3: LLM Semantic Check via Claude Code Sub-Agent (seconds, uses existing tokens)
    Retrieve the entity's canon_claims.
    Find the top 10-15 most similar existing claims (keyword matching initially).
    Spawn a Claude Code sub-agent with a focused prompt:
      "Compare these new claims against existing canon. Identify contradictions."
    -> If CRITICAL contradiction: Block the write. Show the conflict.
    -> If WARNING: Allow the write. Show the warning for the user to review.
    -> If no issues: Allow the write silently.
```

**IMPORTANT (from decisions log): Layer 3 uses Claude Code sub-agents, NOT external API calls.** No API keys needed, no external infrastructure. The sub-agent uses the same Claude Code session tokens.

**How Layer 3 works in practice:**
- The consistency checker script spawns a sub-agent via Claude Code's Task tool
- The sub-agent receives ONLY the new entity's claims and the retrieved existing claims (focused context, no pollution)
- The sub-agent returns a structured JSON response with any contradictions found
- The hook script processes the response and decides whether to block

---

### Task 3C: Hook Scripts

**What it is:** Five Python scripts wired into Claude Code's hook system. These are the "guarantees" -- unlike prompt instructions which Claude can forget, hooks execute deterministically every time.

**What it produces:** Five scripts in `hooks/` plus `.claude/settings.json` configuration.

---

#### Hook 1: Session Start (`hooks/session_start.py`)

**When it fires:** Every time a Claude Code session begins.

**What it does:**
1. Reads `user-world/state.json` for current step and progression status
2. Reads the last 3 session summaries from `bookkeeping/sessions/`
3. Reads `bookkeeping/indexes/progression.json` for overall progress
4. Rebuilds the SQLite database from JSON files (sync)
5. Rebuilds the NetworkX graph from entity files
6. Outputs a compact project briefing to Claude's context:

```
[WORLDBUILDING PROJECT STATE]
Current Step: 7/52 -- Create Individual God Profiles
Current Phase: Phase 2 (Cosmology)
Completed Steps: 1, 2, 3, 4, 5, 6
In Progress: 7
Entities: 1 pantheon, 2 gods, 1 creation myth, 1 planet
Last Session (Jan 30): Created 2 gods for the Celestial Court. Next: need 1-3 more gods.
Open Contradictions: None
```

---

#### Hook 2: Context Injection (`hooks/inject_step_context.py`)

**When it fires:** On every user prompt (UserPromptSubmit hook).

**What it does:**
1. Reads the user's prompt from stdin
2. Determines the current step from `user-world/state.json`
3. Calls `chunk_puller.py` to get a CONDENSED version of the three-layer guidance for the current step (not the full document -- just the most relevant parts to keep context lean)
4. If the user mentions specific entities by name, queries the NetworkX graph and injects their cross-references
5. Injects the dynamic system prompt (phase-specific rules from orchestration research):

```python
# Phase-specific rules injected with every prompt
if current_phase == "cosmology":
    print("ACTIVE RULES:")
    print("- New entities need connections to existing gods/myths")
    print("- Check planet/climate data for consistency")
elif current_phase == "civilization":
    print("ACTIVE RULES:")
    print("- Cross-reference ALL new elements against species and land features")
    print("- Every sovereign power needs at least one ally and one enemy")
```

6. Injects option generation reminders:
```
OPTION GENERATION RULES:
- Present 2-4 unique, fully fleshed out options for every creative decision
- Each option must be a complete, standalone choice (not a vague suggestion)
- Each option must account for ALL existing canon
- Draw from different mythological and authorial traditions for variety
- After user chooses, record the decision with all options and rationale
```

---

#### Hook 3: Write Validation (`hooks/validate_writes.py`)

**When it fires:** After any Write or Edit tool use that targets files in `user-world/` (PostToolUse hook with matcher).

**What it does:**
1. Reads the tool input from stdin to get the file path
2. If the file is NOT under `user-world/`, exits immediately (no validation needed)
3. Determines the entity type from the file path
4. Runs the three-layer consistency checker (Task 3B):
   - Layer 1: Schema validation
   - Layer 2: Rule-based cross-reference checks
   - Layer 3: LLM semantic check (if Layers 1-2 pass)
5. Updates `user-world/state.json` entity index
6. Updates the bookkeeping system (entity created/modified events)
7. Updates the NetworkX graph (add node/edge)
8. Updates the SQLite database
9. If validation fails: exits with code 2 (blocks the write) and outputs a HUMAN-READABLE error message:
   ```
   Something went wrong while saving the god "Thorin Stormkeeper."

   ISSUE: Thorin is listed as the god of storms, but you already have a god
   of storms -- Kael Thunderborn (created in your last session).

   OPTIONS:
   1. Give Thorin a different primary domain
   2. Make storms a SHARED domain with a rivalry between them
   3. Rename one of them and merge their profiles

   Your data is safe. Nothing was changed.
   ```

**Error recovery (from scale gaps research):** Every error message is written for a non-technical user. No Python tracebacks, no JSON syntax errors, no technical jargon. The message explains what happened, why it matters, and what the user can do about it.

---

#### Hook 4: Completion Verification (`hooks/check_completion.py`)

**When it fires:** When Claude tries to stop/end a response (Stop hook).

**What it does:**
1. Reads `user-world/state.json` for the current step
2. Looks up the step's requirements in `engine/template_registry.json`:
   - Which templates must be filled
   - Minimum entity counts (e.g., "at least 3 gods before moving on")
   - Which cross-references must exist
3. Checks whether requirements are met
4. If NOT met: exits with code 2 (blocks Claude from stopping) and outputs what is still needed:
   ```
   Before we wrap up Step 7, you still need:
   - At least 1 more god profile (you have 2, minimum is 3)
   - At least one god relationship to a god outside the current pantheon

   Would you like to continue, or save your progress and come back later?
   ```
5. If met: exits with code 0 (allows Claude to stop)

**Note:** This does NOT prevent the user from ending a session. It prevents Claude from SILENTLY moving on when requirements are not met. The user can always say "I want to stop here and come back later" -- the hook allows this by checking for explicit user intent.

---

#### Hook 5: State Checkpoint (`hooks/save_checkpoint.py`)

**When it fires:** Before context compaction (PreCompact hook).

**What it does:**
1. Reads `user-world/state.json`
2. Saves a full state snapshot to `bookkeeping/snapshots/snapshot-YYYY-MM-DD-HHMMSS.json`
3. Outputs a summary of what was checkpointed so Claude retains awareness after compaction:
   ```
   [CHECKPOINT SAVED]
   Working on: Step 7 (God Profiles)
   Entities in progress: thorin-stormkeeper-a1b2 (god, draft)
   Decisions this session: 3 (dec-014 through dec-016)
   This checkpoint can be restored if needed.
   ```

---

#### Hook 6: Session End (`hooks/end_session.py`)

**When it fires:** At session end (SessionEnd hook, if available) or triggered manually.

**What it does:**
1. Calls `bookkeeper.end_session()` to:
   - Append a `session_ended` event to the event log
   - Generate a structured session summary in `bookkeeping/sessions/`
   - Update all derived index files
2. Commits all changes to git with a descriptive message:
   ```
   git add -A
   git commit -m "Session 15: Created 3 god profiles for the Celestial Court

   - Created Thorin Stormkeeper (god of storms)
   - Created Mira Sunweaver (god of light)
   - Created Kael Shadowmend (god of secrets)
   - Established 4 divine relationships
   - Step 7 in progress (3/5 minimum gods complete)"
   ```

---

#### Hook Configuration: `.claude/settings.json`

```json
{
  "hooks": {
    "SessionStart": [
      {
        "command": "python C:/Worldbuilding-Interactive-Program/hooks/session_start.py",
        "description": "Load worldbuilding project state, rebuild SQLite and graph"
      }
    ],
    "UserPromptSubmit": [
      {
        "command": "python C:/Worldbuilding-Interactive-Program/hooks/inject_step_context.py",
        "description": "Inject step guidance, canon context, and option generation rules"
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "command": "python C:/Worldbuilding-Interactive-Program/hooks/validate_writes.py",
        "description": "Three-layer validation after file changes in user-world/"
      }
    ],
    "Stop": [
      {
        "command": "python C:/Worldbuilding-Interactive-Program/hooks/check_completion.py",
        "description": "Verify step requirements before allowing Claude to stop"
      }
    ],
    "PreCompact": [
      {
        "command": "python C:/Worldbuilding-Interactive-Program/hooks/save_checkpoint.py",
        "description": "Checkpoint state before context compaction"
      }
    ]
  }
}
```

---

### Task 3D: Lore Sync (Structured Data + Prose)

**What it is:** A system that keeps structured entity data and human-readable prose descriptions in sync. Every entity has both a structured JSON representation (for validation and search) AND a prose narrative (for reading and export).

**What it produces:** Updates to `engine/data_manager.py` -- adds a `_prose` field to every entity and a `generate_prose()` function.

**Why (from scale gaps research):** "Production teams don't want lore as pages -- they want lore as data." But users want to READ lore as prose, not as JSON. The solution: structured data drives validation and search; prose drives reading and export. They are always kept in sync.

**How it works:**
- When an entity is created or updated, the data manager auto-generates a `_prose` field containing a readable narrative paragraph derived from the structured fields.
- Example for a god entity:
  ```json
  "_prose": "Thorin Stormkeeper, known as The Thunder Lord and Voice of the Sky, is a greater god of storms who also holds dominion over protection and sailors. Fierce in battle but deeply protective of those who call upon him, Thorin manifests as a towering figure wreathed in dark clouds with eyes flashing blue-white. He is the spouse of Mira Sunweaver, and together they balance destruction and growth. He belongs to The Celestial Court pantheon and is aligned with the forces of good."
  ```
- The prose is regenerated whenever the structured data changes, so they never drift apart.
- Claude can also write custom prose that overrides the auto-generated version -- this is stored separately and validated against the structured fields.

---

### Sprint 3 Task Summary

| Task | Description | Produces | Depends On |
|---|---|---|---|
| 3A | SQLite Sync Engine | `engine/sqlite_sync.py` + `runtime/worldbuilding.db` | Sprint 2 (2B data manager) |
| 3B | Three-Layer Consistency Checker | `engine/consistency_checker.py` | Sprint 2 (2B, 2D) |
| 3C | Hook Scripts (6 scripts) | `hooks/*.py` + `.claude/settings.json` | Sprint 2 (all) + 3A + 3B |
| 3D | Lore Sync (Prose Generation) | Updates to `engine/data_manager.py` | Sprint 2 (2B) |

**What can run in parallel:**
- 3A and 3B can start immediately (both depend on Sprint 2)
- 3D can start alongside 3A and 3B
- 3C starts after 3A and 3B are done (hooks call both systems)

**Critical path:** 3A + 3B (parallel) -> 3C

---

## Sprint 4: The Safety and Polish Layer

**Goal:** Add automated testing, backup systems, and error recovery to make the system robust enough for daily use by a non-technical user. This sprint ensures that when the user starts actually building their world, nothing breaks in a way they cannot recover from.

**Depends on:** Sprint 3 (all tasks).

---

### Task 4A: Automated Backup System

**What it is:** A Python script that creates timestamped backup copies of the entire world data directory. Runs automatically (triggered by hooks) and silently in the background.

**What it produces:** `engine/backup_manager.py` and `backups/` directory

**How it works:**
1. **Automatic backups:** After every session end, copies `user-world/` and `bookkeeping/` to `backups/YYYY-MM-DD_HH-MM/`
2. **Pre-operation snapshots:** Before any bulk edit, schema migration, or refactor, creates a full snapshot
3. **Rotation:** Keeps the last 20 backups, automatically deletes older ones
4. **Restore command:** If something goes wrong, Claude can say "Restoring from backup taken at [date/time]" and copy the backup back

**Implementation:** ~50 lines of Python using `shutil.copytree` and `datetime`. Zero external dependencies.

---

### Task 4B: Test Suite

**What it is:** An automated test suite that verifies the entire system is working before the user starts worldbuilding.

**What it produces:** `tests/` directory with smoke tests, schema tests, integration tests, and consistency tests

**Test categories:**

| Category | What It Tests | Location | Run Time |
|---|---|---|---|
| **Smoke tests** | Database connects, schemas load, search works, backup runs, hooks fire | `tests/smoke/` | < 30 seconds |
| **Schema validation** | All 85 schemas accept valid data and reject invalid data | `tests/schemas/` | < 60 seconds |
| **Integration tests** | Full workflow: create entity -> validate -> store -> retrieve -> search | `tests/integration/` | < 2 minutes |
| **Consistency tests** | Feed known-bad data with specific contradictions -> verify they are caught | `tests/consistency/` | < 2 minutes |

**Smoke test as startup check:** The session_start hook runs the smoke test suite before anything else. If any smoke test fails, Claude tells the user: "I found a problem with the worldbuilding system. Let me fix it before we continue." and auto-repairs if possible.

**Test data factory:** A module (`tests/factory.py`) that generates realistic test entities covering all 85 schema types, producing both valid and deliberately invalid entities for testing.

---

### Task 4C: Error Recovery System

**What it is:** A set of recovery tools that handle common failures gracefully, with human-readable messages for the non-technical user.

**What it produces:** `engine/error_recovery.py`

**What it handles:**

| Error | Recovery | User-Facing Message |
|---|---|---|
| Malformed JSON entity file | Restore from last backup | "Something went wrong with one of your files. I restored it from a backup. No data was lost." |
| SQLite database corrupted | Rebuild from JSON files | "I need to rebuild the search database. This takes a few seconds." (runs automatically) |
| Missing entity referenced by another entity | Flag as orphan, offer to create or remove the reference | "The settlement 'Ironhold' references a ruler named 'King Aldric,' but King Aldric doesn't exist yet. Would you like to create him now, or remove the reference for now?" |
| Git merge conflict | Auto-resolve by keeping the newest version, save both versions | "There was a conflict in your files. I kept the newest version and saved the older one in backups, just in case." |
| Schema validation failure on existing entity | Log the issue, do not block the session | "I noticed an issue with one of your older entities -- it doesn't quite match the current template. I'll flag it for you to review when convenient." |

**Health check command:** A function that verifies all systems are operational:
- All JSON entity files are valid JSON
- All entity files pass schema validation
- All cross-references point to existing entities
- The SQLite database is in sync with JSON files
- The NetworkX graph matches entity relationships
- Backups are running and recent

The user can ask "Is everything working?" and Claude runs the health check.

---

### Task 4D: CLAUDE.md and Rules Update

**What it is:** Update the project's CLAUDE.md and .claude/rules/ files to reflect the new systems, so Claude Code has full awareness of the architecture at every session start.

**What it produces:** Updated `CLAUDE.md` and new rule files in `.claude/rules/`

**New rule files:**

| File | Content |
|---|---|
| `.claude/rules/option-generation.md` | Rules for generating 2-4 options, diversity requirements, canon awareness, fair representation |
| `.claude/rules/consistency-rules.md` | Three-layer validation process, what to do when contradictions are found |
| `.claude/rules/bookkeeping-rules.md` | When to record events, how to update indexes, session summary requirements |
| `.claude/rules/progression-rules.md` | Step ordering, dependencies, minimum requirements per step, parallel work opportunities |
| `.claude/rules/error-handling.md` | Human-readable error messages, recovery procedures, when to use backups |

**Updated CLAUDE.md additions:**
- References to all new engine scripts and what they do
- References to the bookkeeping system and how to query it
- References to the hook scripts and their purposes
- The option generation rules (most important feature reminder)
- The three-layer guidance format

---

### Sprint 4 Task Summary

| Task | Description | Produces | Depends On |
|---|---|---|---|
| 4A | Automated Backup System | `engine/backup_manager.py` + `backups/` | Sprint 3 (hooks to trigger backups) |
| 4B | Test Suite | `tests/` directory (smoke, schema, integration, consistency) | Sprint 2 + 3 (needs all systems to test) |
| 4C | Error Recovery System | `engine/error_recovery.py` | Sprint 2 + 3 (needs all systems to recover) |
| 4D | CLAUDE.md and Rules Update | Updated `CLAUDE.md` + `.claude/rules/*.md` | Sprint 2 + 3 + 4A-C (documents everything) |

**All Sprint 4 tasks can run in parallel** (they are independent of each other).

---

## Dependency Map

```
SPRINT 1 (COMPLETE)
  [A] 85 Templates
  [B] User-World Structure + state.json
  [D] Reference Index + Source Index
      |
      v
SPRINT 2: THE ENGINE LAYER
  [2A] Template Registry --------+
  [2B] Data Manager -------------+----> [2D] NetworkX Graph ----+
  [2C] Bookkeeping System        +----> [2E] Chunk Puller ------+----> [2G] Option Generator
                                  +----> [2F] Fair Representation+
      |
      v
SPRINT 3: THE INTELLIGENCE LAYER
  [3A] SQLite Sync Engine -------+
  [3B] Consistency Checker ------+----> [3C] Hook Scripts (all 6)
  [3D] Lore Sync ---------------+
      |
      v
SPRINT 4: THE SAFETY LAYER
  [4A] Backup System     (parallel)
  [4B] Test Suite        (parallel)
  [4C] Error Recovery    (parallel)
  [4D] CLAUDE.md Update  (parallel, last to finish)
```

**Critical path through all sprints:**
Sprint 1 -> 2A+2B (parallel) -> 2D+2E+2F (parallel) -> 2G -> 3A+3B (parallel) -> 3C -> 4B+4D

---

## What Success Looks Like

Phase 2 is complete when all of the following are true:

1. **The user can say "I'm ready for Step 7"** and the system produces a three-layer guidance document with book quotes, synthesized reference material from multiple mythologies and authors (fairly rotated), and a clear template to fill in -- all while accounting for what the user has already built.

2. **The system presents 2-4 unique, fully fleshed out options** for every creative decision. Each option is a complete, standalone choice inspired by different mythological and authorial traditions. Each option accounts for all existing canon. The user can pick one, combine elements, request new options, or go custom.

3. **When the user makes a choice**, the bookkeeping system silently records the decision with all options presented, which was chosen, which were rejected, and the user's rationale. The user can later ask "What were my other options for the magic system?" and get an instant answer.

4. **When the user fills in a God Profile**, the data is validated against the schema, cross-references are checked, and an LLM sub-agent scans for contradictions against existing canon. If there is a problem, the user sees a clear, friendly message explaining the issue and their options.

5. **No single mythology or author dominates** the reference material. The fair representation system ensures rotation, and the option generator draws from different traditions for each option.

6. **The user can ask questions about their world** and get fast answers: "What references this god?" "What settlements are near the coast?" "What did I decide about the government?" All answered via the bookkeeping indexes and SQLite search.

7. **Sessions pick up where they left off.** The session start hook loads the project state, the last few session summaries, and the current step context. The PreCompact hook saves checkpoints before context compression. The session end hook generates a summary and commits to git.

8. **Nothing breaks in a way the user cannot recover from.** The backup system runs automatically, the error recovery system handles common failures with friendly messages, and the smoke test suite verifies everything is working at session start.

9. **Everything is automated.** The user never runs a command, edits a config file, or touches the bookkeeping system. They just talk to Claude about their world.

---

## What This Plan Does NOT Cover

These are deferred to later phases, per the research recommendations:

- **ChromaDB + Contextual Retrieval:** Planned for when the corpus exceeds ~15,000 lines (Phase 2 of the retrieval research phased plan). Not needed at initial scale.
- **LightRAG / Full Knowledge Graph:** Planned for when hundreds of entities create relationship complexity that NetworkX cannot handle (Phase 4 of retrieval research). Not needed initially.
- **Visualization (Mermaid/Graphviz):** Rated IMPORTANT but not CRITICAL in scale gaps research. Add within first few weeks of use.
- **Export (PDF/Wiki/Game Engine):** Rated IMPORTANT. Add when the user wants to share their world.
- **Branching/What-If Exploration:** Rated IMPORTANT. Add when the user wants to explore alternate versions.
- **Schema Versioning and Migration:** Rated IMPORTANT. Add when schemas need to evolve.
- **Collaboration:** Rated NICE-TO-HAVE. The user is solo.
- **User Interface:** Phase 2 builds the engine. The user experience is Claude Code conversations. A web or CLI interface is a separate phase.

---

## Appendix: Python Dependencies

All dependencies are installable via `pip` with no external services:

| Package | Purpose | Install |
|---|---|---|
| `jsonschema` | JSON Schema validation (Layer 1 consistency) | `pip install jsonschema` |
| `networkx` | In-memory knowledge graph | `pip install networkx` |
| (none -- built-in) | SQLite + FTS5 | Python's built-in `sqlite3` module |
| (none -- built-in) | JSON, datetime, shutil, hashlib | Python standard library |

No external APIs. No Docker. No cloud services. No npm packages. Everything runs locally on Python 3.13.
