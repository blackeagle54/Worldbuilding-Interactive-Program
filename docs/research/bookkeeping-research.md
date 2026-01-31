# Bookkeeping, Logging, and Decision Tracking Research

## Research for the Worldbuilding Interactive Program

**Date:** 2026-01-30
**Purpose:** Design a comprehensive system to track every decision, draft, revision, session, and creative rationale across 52 progression steps, 84 templates, and 16 reference databases -- all managed automatically by Claude Code with zero user overhead.

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [What Needs to Be Tracked](#2-what-needs-to-be-tracked)
3. [Approaches Evaluated](#3-approaches-evaluated)
4. [Approach Analysis Matrix](#4-approach-analysis-matrix)
5. [Industry Precedents](#5-industry-precedents)
6. [Recommended System: Hybrid Event-Sourced Bookkeeping](#6-recommended-system)
7. [Detailed File Structure](#7-detailed-file-structure)
8. [Schema Definitions](#8-schema-definitions)
9. [How Each Tracking Need Is Met](#9-how-each-tracking-need-is-met)
10. [Concrete Examples](#10-concrete-examples)
11. [Query Patterns](#11-query-patterns)
12. [Automation Strategy](#12-automation-strategy)
13. [Storage Projections](#13-storage-projections)
14. [Sources](#14-sources)

---

## 1. Problem Statement

The worldbuilding program will generate hundreds of decisions across weeks or months of interactive sessions. A user building a world will:

- Be presented with 2-4 options at each decision point
- Choose one, reject others, and sometimes explain why
- Produce drafts that may or may not become canon
- Revise canon entries when contradictions are found or ideas evolve
- Create entities (characters, places, cultures) that reference each other
- Progress through 52 steps in a non-linear order
- Return to earlier decisions and change them

Without a bookkeeping system, this information is lost between sessions. The user cannot ask "why did I choose a feudal government?" or "what were the other options for the magic system?" or "when did I change the capital city's name?" The system must answer all such questions automatically.

The critical constraint: the user is non-technical. Claude Code must manage every aspect of bookkeeping silently -- writing logs, updating indexes, maintaining consistency -- without the user ever needing to touch a file, run a command, or understand the underlying system.

---

## 2. What Needs to Be Tracked

| # | Category | Description | Volume Estimate |
|---|----------|-------------|-----------------|
| 1 | Decisions | What was decided, options presented, choice made, rationale | ~200-500 decisions |
| 2 | Drafts | Work in progress not yet finalized | ~100-300 drafts |
| 3 | Canon Status | Whether content is final (canon) or exploratory (draft) | Status per entity |
| 4 | Session Logs | What happened each session: topics, creations, modifications | ~50-150 sessions |
| 5 | Revision History | When canon changes, old version preserved with reason | ~50-200 revisions |
| 6 | Option History | The 2-4 options presented at each step, outcomes | ~400-1500 options |
| 7 | Cross-References | When entity A references entity B, record the link creation | ~300-1000 links |
| 8 | Progression | When each of 52 steps was started, worked on, completed | 52 step records |
| 9 | Contradictions | When contradictions found, how resolved | ~20-100 resolutions |
| 10 | Creative Rationale | Why the user chose what they chose | Embedded in decisions |

---

## 3. Approaches Evaluated

### 3.1 Git-Based Audit Trail

**How it works:** Every change to any worldbuilding file is a git commit. The commit message records what changed and why. Git history becomes the audit trail. Branches can represent draft vs. canon.

**Strengths:**
- Built-in version history for every file
- Diff capability shows exactly what changed between any two versions
- Branching supports draft/canon separation (draft branch vs. main/canon branch)
- Immutable history (commits cannot be silently altered)
- Claude Code already operates in git repositories naturally
- Conventional Commits format can encode decision types (e.g., `decision: chose feudal government for Eldoria`)
- Free, local, no dependencies

**Weaknesses:**
- Git history is not easily queryable ("show me all decisions about magic" requires parsing commit messages)
- Commit messages are unstructured text unless rigidly formatted
- Cross-referencing between commits is cumbersome
- Branching model adds complexity that Claude Code must manage silently
- Searching git log is slow and awkward for non-technical queries
- Git stores file-level changes, not semantic-level changes (a "decision" might touch 5 files)
- Merging draft branches into canon can create conflicts

**Assessment:** Git is excellent as a *backup layer* and *safety net* but poor as a *primary query interface*. It should underpin the system but not be the main bookkeeping mechanism.

### 3.2 Event Sourcing (Append-Only Event Log)

**How it works:** Every action that changes the world state is recorded as an immutable event in an append-only log. The current state of the world can be reconstructed by replaying all events from the beginning. Events are stored as JSON Lines (one JSON object per line in a `.jsonl` file) or in an SQLite database.

The pattern originates from distributed systems architecture (Martin Fowler, Microsoft Azure, AWS) where it provides complete auditability and the ability to "time-travel" to any past state.

**Strengths:**
- Complete, immutable history of every change
- Events capture intent and context, not just data changes
- Current state is derived from events, so nothing is ever truly lost
- Naturally supports "undo" by replaying events up to a point
- JSON Lines format is human-readable and trivially appendable
- Queryable with simple Python (filter events by type, entity, date)
- Events can carry arbitrary metadata (rationale, session ID, step number)
- The append-only nature means corruption risk is minimal

**Weaknesses:**
- Reconstructing current state from events requires "projection" logic
- Log grows indefinitely (mitigated by snapshots)
- Full event sourcing is architecturally complex for large systems
- Querying the event log directly can be slow for complex queries
- Requires careful event schema design upfront

**Assessment:** Event sourcing is the strongest conceptual fit for this project. Every decision, draft change, status transition, and cross-reference is naturally an event. The append-only property guarantees nothing is lost. However, pure event sourcing (deriving all state from events) adds unnecessary complexity. A hybrid approach is better.

### 3.3 Architectural Decision Records (ADRs)

**How it works:** Each significant decision gets its own structured Markdown document with a standard template: Title, Status, Context, Decision, Consequences. ADRs are immutable -- when a decision is superseded, the old ADR is marked "Superseded by ADR-XXX" and a new one is created.

ADRs are widely adopted in software architecture (recommended by AWS, Azure, ThoughtWorks Technology Radar "Adopt" rating) and the MADR (Markdown Any Decision Records) variant extends the pattern to any kind of decision.

**Strengths:**
- Highly structured and human-readable
- Each decision is a self-contained document
- Status tracking (proposed, accepted, rejected, superseded) built in
- Well-established pattern with proven templates
- Markdown format is simple and searchable
- Immutability principle preserves history

**Weaknesses:**
- One file per decision means hundreds of files for this project
- Files are individually readable but hard to query across ("show all decisions about geography")
- No built-in cross-referencing between decisions
- Does not cover drafts, sessions, or progression -- only decisions
- File proliferation becomes unwieldy at scale

**Assessment:** ADRs are the gold standard for individual decision documentation. The format should be adapted for worldbuilding decisions, but ADRs alone cannot cover the full tracking needs (sessions, drafts, progression, cross-references). The ADR structure should be embedded within a broader system.

### 3.4 Session Transcripts / Logs

**How it works:** Each Claude Code session generates a log of what was discussed, created, and modified. Logs can be full transcripts or structured summaries.

**Strengths:**
- Captures the full context of each working session
- Useful for reviewing "what did I do last time?"
- Can include informal rationale that would not fit in a decision record

**Weaknesses:**
- Full transcripts are enormous and mostly noise
- Summarization requires careful design to capture the right information
- Hard to search for specific decisions within narrative text
- Does not provide structured data for querying

**Assessment:** Session summaries (not full transcripts) are valuable as a "session journal." They should be structured with consistent fields (date, steps worked on, decisions made, entities created/modified) rather than free-form narrative. Claude Code's own transcript logs exist but are not designed for user-facing review.

### 3.5 Database Logging (SQLite)

**How it works:** All events, decisions, and state changes are logged to an SQLite database. Tables for decisions, drafts, sessions, entities, cross-references, and progression. SQL queries answer any question about the project history.

**Strengths:**
- Extremely powerful querying (SQL can answer almost any question)
- Structured data with enforced schemas
- SQLite is serverless, zero-config, single-file, and built into Python
- Handles large volumes efficiently
- Supports indexes for fast lookups
- Triggers can automate audit logging
- Python's `sqlite3` module is built-in (no pip install needed)

**Weaknesses:**
- Binary format is not human-readable (cannot open in a text editor)
- Harder for Claude Code to inspect quickly compared to JSON/Markdown
- Schema changes require migration logic
- Overkill for simple append operations
- User cannot casually browse the data

**Assessment:** SQLite is the most powerful option for queryability but the least accessible for casual inspection. It works best as a backend index that powers queries, not as the primary storage format that a user (or Claude Code reading context) would browse.

### 3.6 Wiki-Style Revision History

**How it works:** Each entity (character, place, culture, etc.) has its own page/file with a built-in revision history. When the entity is modified, the old version is preserved as a prior revision. Similar to how MediaWiki or World Anvil track changes.

**Strengths:**
- Natural mapping to worldbuilding entities
- Revision history is per-entity, making it easy to see how one thing evolved
- Familiar mental model (Wikipedia-style "view history")

**Weaknesses:**
- Does not capture decisions that span multiple entities
- Does not track what options were rejected
- Session context is lost
- Implementing revision history in flat files requires careful design

**Assessment:** Per-entity revision history is valuable but insufficient alone. It tracks *what* changed but not *why* or *what alternatives existed*. It should be one component of a broader system.

### 3.7 Hybrid Approaches

The clear conclusion from evaluating these approaches individually is that no single approach covers all ten tracking requirements. The optimal system combines:

- **Event log** (append-only JSONL) as the authoritative record of everything that happened
- **ADR-inspired decision records** embedded in the event log for structured decision tracking
- **Git commits** as a safety net and backup audit trail
- **Derived indexes** (JSON files or lightweight SQLite) for fast querying
- **Session summaries** as structured Markdown for human review
- **Per-entity revision history** embedded in entity metadata

---

## 4. Approach Analysis Matrix

| Criterion | Git | Event Sourcing | ADRs | Session Logs | SQLite | Wiki-Style | **Hybrid** |
|-----------|-----|---------------|------|-------------|--------|-----------|------------|
| **Completeness** | Medium | High | Low (decisions only) | Low (sessions only) | High | Medium | **High** |
| **Queryability** | Low | Medium | Low | Low | High | Medium | **High** |
| **Human Readability** | Low | Medium | High | High | Low | High | **High** |
| **Storage Efficiency** | High | Medium | Low (many files) | Medium | High | Medium | **Medium** |
| **Complexity to Implement** | Low | High | Low | Low | Medium | Medium | **Medium** |
| **Claude Code Can Automate** | Yes | Yes | Yes | Yes | Yes | Yes | **Yes** |
| **Handles All 10 Requirements** | No | Nearly | No | No | Yes (with schema) | No | **Yes** |
| **Corruption Risk** | Low | Low | Low | Low | Medium | Low | **Low** |
| **No Dependencies** | Needs git | None | None | None | Built into Python | None | **Minimal** |

---

## 5. Industry Precedents

### 5.1 Game Studios

Game studios use **lore bibles** (living documents that record all canonical world facts), **internal wikis** (Confluence, Notion, or custom tools), and **dedicated worldbuilding platforms** (World Anvil, LegendKeeper). Ubisoft Massive's lead writer Anna Megill emphasizes that story bibles must be "living documents" that evolve with the project, not static references.

The key insight from game studios: lore bibles track *what is true now* but rarely track *what was considered and rejected* or *why something was chosen*. Professional worldbuilders report that losing this context leads to revisiting settled decisions. Our system must do better.

### 5.2 Software Architecture (ADRs)

The ADR pattern (originated by Michael Nygard, recommended by ThoughtWorks, AWS, and Microsoft Azure) proves that structured decision records are essential for long-lived projects. The core principle -- decisions are immutable, superseded rather than edited -- maps perfectly to worldbuilding where creative decisions should be preserved even when overridden.

The MADR (Markdown Any Decision Records) variant is particularly relevant because it extends ADRs beyond software architecture to "any decision," which includes creative decisions.

### 5.3 Event Sourcing in Production Systems

Event sourcing is used in financial systems (where every transaction must be auditable), healthcare (where patient record changes must be traceable), and e-commerce (where order state changes must be reconstructable). The pattern's guarantees -- completeness, immutability, replayability -- are exactly what worldbuilding bookkeeping needs.

Martin Fowler's foundational description: "The fundamental idea is ensuring every change to the state of an application is captured in an event object, and that these event objects are themselves stored in the sequence they were applied."

### 5.4 Obsidian/Knowledge Management

Obsidian's approach (Markdown files with internal links, stored locally, with graph visualization) validates the file-based approach for creative knowledge management. Its success shows that plain-text formats with linking are powerful enough for complex knowledge graphs. However, Obsidian's version history is limited to sync subscribers and does not natively track decision rationale.

### 5.5 Creative Writing Version Control

The Ink & Switch "Upwelling" project demonstrates that creative writers need both real-time collaboration and version control, with the ability to work on private drafts and merge them when ready. This validates the draft/canon separation model.

Git has been successfully used for creative writing projects (documented by Invisible Publishing and others), with commit history serving as the change log. The limitation is always queryability -- git log is powerful but requires technical skill to use effectively.

---

## 6. Recommended System: Hybrid Event-Sourced Bookkeeping

### 6.1 Architecture Overview

The recommended system uses three layers:

```
LAYER 1: Event Log (Source of Truth)
  - Append-only JSONL file
  - Every action is an event with full context
  - Never edited, only appended
  - One file per month (for manageable size)

LAYER 2: Derived State Files (Human-Readable Views)
  - Session summaries (Markdown)
  - Decision index (JSON)
  - Entity revision index (JSON)
  - Progression tracker (JSON)
  - Cross-reference registry (JSON)
  - Contradiction log (Markdown)

LAYER 3: Safety Net
  - Git commits after every session
  - Commit messages summarize what happened
  - Git history as backup audit trail
```

### 6.2 Why This Architecture

**Layer 1 (Event Log)** guarantees that nothing is ever lost. Every event is appended with a timestamp, session ID, and full context. If any derived file is corrupted or lost, it can be rebuilt from the event log.

**Layer 2 (Derived State)** provides fast, queryable, human-readable views of the data. Claude Code reads these files to answer questions like "what decisions have I made about magic?" without scanning the entire event log. These files are *derived* -- they can always be regenerated from Layer 1.

**Layer 3 (Git)** provides a familiar version control safety net. If something goes catastrophically wrong, git history preserves every state the project has been in.

### 6.3 Why Not Pure Event Sourcing

Pure event sourcing derives ALL current state from replaying events. This is architecturally elegant but impractical for this project because:

1. Claude Code would need to replay potentially thousands of events at the start of every session to know the current world state
2. The canon world files already exist as Markdown in `user-world/` -- replicating them as event projections would be redundant
3. The complexity of maintaining projection logic outweighs the benefits for a single-user creative project

Instead, the event log serves as the **audit trail and history**, while the actual world state continues to live in the existing `user-world/` Markdown files. The derived index files bridge the gap, providing queryable metadata without the overhead of full event replay.

### 6.4 Why Not Pure SQLite

SQLite would provide the most powerful querying, but:

1. Claude Code cannot casually "read" a SQLite database the way it reads JSON or Markdown
2. The user cannot open and browse SQLite without tools
3. JSON files can be loaded into Python dictionaries with one line of code
4. For the expected data volumes (hundreds, not millions, of records), JSON is performant enough
5. JSONL (the event log) is both append-friendly and human-inspectable

If the project scales to a point where JSON querying becomes slow (unlikely), SQLite can be added as an optimization layer that indexes the JSONL event log.

---

## 7. Detailed File Structure

```
C:\Worldbuilding-Interactive-Program\
  bookkeeping\
    events\
      events-2026-01.jsonl        # Event log for January 2026
      events-2026-02.jsonl        # Event log for February 2026
      ...                         # One file per month

    indexes\
      decisions.json              # All decisions with options, choices, rationale
      progression.json            # Status of all 52 steps
      entity-registry.json        # All entities with status (draft/canon) and revision count
      cross-references.json       # All entity-to-entity links
      contradictions.json         # All contradictions found and resolutions

    sessions\
      session-2026-01-30-001.md   # Structured session summary
      session-2026-02-01-001.md
      ...

    revisions\
      revisions-by-entity.json    # Revision history keyed by entity ID

    snapshots\
      snapshot-2026-01-30.json    # Periodic full-state snapshot for fast reconstruction
```

### 7.1 File Purposes

| File | Purpose | Format | Updated When |
|------|---------|--------|-------------|
| `events-YYYY-MM.jsonl` | Immutable record of every action | JSON Lines (append-only) | Every action |
| `decisions.json` | Queryable index of all decisions | JSON (rewritten) | After each decision |
| `progression.json` | Status of all 52 steps | JSON (rewritten) | Step status changes |
| `entity-registry.json` | Master list of all entities | JSON (rewritten) | Entity created/modified |
| `cross-references.json` | All entity-to-entity links | JSON (rewritten) | Links created/removed |
| `contradictions.json` | Contradiction log | JSON (rewritten) | Contradictions found/resolved |
| `session-*.md` | Human-readable session journal | Markdown (write once) | End of each session |
| `revisions-by-entity.json` | Full revision history per entity | JSON (rewritten) | Entity revised |
| `snapshot-*.json` | Point-in-time full state | JSON (write once) | Periodically (weekly) |

---

## 8. Schema Definitions

### 8.1 Event Schema (events-YYYY-MM.jsonl)

Each line in the JSONL file is one event. Every event has these common fields:

```json
{
  "event_id": "evt-20260130-143022-001",
  "timestamp": "2026-01-30T14:30:22",
  "session_id": "ses-20260130-001",
  "event_type": "decision_made",
  "step_id": "step-03",
  "entity_id": "world-government-type",
  "data": { ... },
  "metadata": {
    "step_name": "Government & Power Structures",
    "template_used": "government-type.md"
  }
}
```

#### Event Types and Their Data Fields

**`decision_made`** -- A choice was made from presented options
```json
{
  "event_type": "decision_made",
  "data": {
    "decision_id": "dec-047",
    "question": "What type of government rules Eldoria?",
    "options_presented": [
      {
        "option_id": "opt-047-A",
        "label": "Feudal Monarchy",
        "summary": "A hereditary king rules through a hierarchy of lords and vassals."
      },
      {
        "option_id": "opt-047-B",
        "label": "Theocratic Council",
        "summary": "A council of high priests governs based on divine mandate."
      },
      {
        "option_id": "opt-047-C",
        "label": "Merchant Republic",
        "summary": "Wealthy trade guilds elect a leader from among their ranks."
      }
    ],
    "chosen_option": "opt-047-A",
    "rejected_options": ["opt-047-B", "opt-047-C"],
    "user_rationale": "I want a traditional fantasy feel with clear power hierarchies.",
    "replaces_decision": null
  }
}
```

**`draft_created`** -- New draft content was written
```json
{
  "event_type": "draft_created",
  "data": {
    "draft_id": "dft-012",
    "entity_id": "eldoria-government",
    "entity_type": "political_system",
    "file_path": "user-world/politics/eldoria-government.md",
    "status": "draft",
    "content_hash": "sha256:a1b2c3...",
    "summary": "Initial draft of Eldoria's feudal government structure."
  }
}
```

**`status_changed`** -- Content moved from draft to canon (or vice versa)
```json
{
  "event_type": "status_changed",
  "data": {
    "entity_id": "eldoria-government",
    "previous_status": "draft",
    "new_status": "canon",
    "reason": "User approved the feudal government draft after review."
  }
}
```

**`entity_revised`** -- Canon content was modified
```json
{
  "event_type": "entity_revised",
  "data": {
    "entity_id": "eldoria-government",
    "revision_number": 2,
    "previous_content_hash": "sha256:a1b2c3...",
    "new_content_hash": "sha256:d4e5f6...",
    "change_summary": "Changed succession rules from primogeniture to elective.",
    "reason": "User decided elective monarchy creates more interesting political conflict.",
    "previous_version_preserved": true
  }
}
```

**`cross_reference_created`** -- A link between entities was established
```json
{
  "event_type": "cross_reference_created",
  "data": {
    "source_entity": "eldoria-government",
    "target_entity": "house-valdris",
    "relationship_type": "rules",
    "description": "House Valdris holds the throne of Eldoria.",
    "bidirectional": true
  }
}
```

**`contradiction_found`** -- An inconsistency was detected
```json
{
  "event_type": "contradiction_found",
  "data": {
    "contradiction_id": "con-008",
    "entities_involved": ["eldoria-government", "eldoria-history"],
    "description": "Government page says 'founded 500 years ago' but history says 'kingdom is 300 years old'.",
    "severity": "major",
    "status": "open"
  }
}
```

**`contradiction_resolved`** -- A contradiction was resolved
```json
{
  "event_type": "contradiction_resolved",
  "data": {
    "contradiction_id": "con-008",
    "resolution": "Changed history to say the kingdom is 500 years old, matching the government page.",
    "entities_modified": ["eldoria-history"],
    "decision_id": "dec-052"
  }
}
```

**`step_status_changed`** -- A progression step changed status
```json
{
  "event_type": "step_status_changed",
  "data": {
    "step_id": "step-03",
    "step_name": "Government & Power Structures",
    "previous_status": "in_progress",
    "new_status": "completed",
    "completion_percentage": 100
  }
}
```

**`session_started`** / **`session_ended`** -- Session boundary markers
```json
{
  "event_type": "session_started",
  "data": {
    "session_number": 15,
    "planned_focus": "Government and political structures"
  }
}
```

```json
{
  "event_type": "session_ended",
  "data": {
    "session_number": 15,
    "steps_worked_on": ["step-03", "step-04"],
    "decisions_made": ["dec-047", "dec-048", "dec-049"],
    "entities_created": ["eldoria-government", "house-valdris"],
    "entities_modified": ["eldoria-history"],
    "summary": "Established the feudal government of Eldoria. Created House Valdris as the ruling dynasty. Resolved a dating contradiction in the history."
  }
}
```

### 8.2 Decision Index Schema (decisions.json)

```json
{
  "last_updated": "2026-01-30T14:30:22",
  "total_decisions": 49,
  "decisions": [
    {
      "decision_id": "dec-047",
      "timestamp": "2026-01-30T14:30:22",
      "session_id": "ses-20260130-001",
      "step_id": "step-03",
      "step_name": "Government & Power Structures",
      "question": "What type of government rules Eldoria?",
      "chosen": {
        "option_id": "opt-047-A",
        "label": "Feudal Monarchy"
      },
      "rejected": [
        {"option_id": "opt-047-B", "label": "Theocratic Council"},
        {"option_id": "opt-047-C", "label": "Merchant Republic"}
      ],
      "rationale": "I want a traditional fantasy feel with clear power hierarchies.",
      "status": "active",
      "superseded_by": null,
      "entities_affected": ["eldoria-government"]
    }
  ]
}
```

### 8.3 Progression Tracker Schema (progression.json)

```json
{
  "last_updated": "2026-01-30T14:30:22",
  "total_steps": 52,
  "completed": 3,
  "in_progress": 2,
  "not_started": 47,
  "steps": [
    {
      "step_id": "step-01",
      "step_name": "World Concept & Genre",
      "status": "completed",
      "started": "2026-01-15T10:00:00",
      "last_worked": "2026-01-15T11:30:00",
      "completed_at": "2026-01-15T11:30:00",
      "sessions_involved": ["ses-20260115-001"],
      "decisions_made": ["dec-001", "dec-002", "dec-003"],
      "entities_created": ["world-concept", "genre-definition"]
    },
    {
      "step_id": "step-03",
      "step_name": "Government & Power Structures",
      "status": "in_progress",
      "started": "2026-01-30T14:00:00",
      "last_worked": "2026-01-30T14:30:00",
      "completed_at": null,
      "sessions_involved": ["ses-20260130-001"],
      "decisions_made": ["dec-047"],
      "entities_created": ["eldoria-government"]
    }
  ]
}
```

### 8.4 Entity Registry Schema (entity-registry.json)

```json
{
  "last_updated": "2026-01-30T14:30:22",
  "total_entities": 24,
  "canon_count": 18,
  "draft_count": 6,
  "entities": {
    "eldoria-government": {
      "entity_type": "political_system",
      "name": "Eldoria Government",
      "status": "canon",
      "created": "2026-01-30T14:20:00",
      "last_modified": "2026-01-30T14:30:00",
      "file_path": "user-world/politics/eldoria-government.md",
      "revision_count": 2,
      "current_revision": 2,
      "step_id": "step-03",
      "created_in_session": "ses-20260130-001",
      "references_to": ["house-valdris", "eldoria-history"],
      "referenced_by": ["eldoria-overview", "noble-houses"]
    }
  }
}
```

### 8.5 Cross-Reference Registry Schema (cross-references.json)

```json
{
  "last_updated": "2026-01-30T14:30:22",
  "total_links": 45,
  "links": [
    {
      "link_id": "xref-089",
      "source": "eldoria-government",
      "target": "house-valdris",
      "relationship": "rules",
      "description": "House Valdris holds the throne of Eldoria.",
      "created": "2026-01-30T14:30:00",
      "created_in_session": "ses-20260130-001",
      "bidirectional": true,
      "status": "active"
    }
  ]
}
```

### 8.6 Revision History Schema (revisions-by-entity.json)

```json
{
  "eldoria-government": {
    "current_revision": 2,
    "revisions": [
      {
        "revision": 1,
        "timestamp": "2026-01-30T14:20:00",
        "status_at_time": "draft",
        "content_hash": "sha256:a1b2c3...",
        "change_summary": "Initial creation",
        "decision_id": "dec-047"
      },
      {
        "revision": 2,
        "timestamp": "2026-01-30T14:30:00",
        "status_at_time": "canon",
        "content_hash": "sha256:d4e5f6...",
        "change_summary": "Changed succession rules from primogeniture to elective.",
        "reason": "Elective monarchy creates more interesting political conflict.",
        "decision_id": "dec-052",
        "previous_revision_snapshot": "bookkeeping/revisions/snapshots/eldoria-government-rev1.md"
      }
    ]
  }
}
```

### 8.7 Session Summary Schema (session-YYYY-MM-DD-NNN.md)

```markdown
# Session 15 -- 2026-01-30

**Session ID:** ses-20260130-001
**Duration:** ~90 minutes
**Focus:** Government and Political Structures

## Steps Worked On
- **Step 03: Government & Power Structures** (in_progress -> completed)
- **Step 04: Noble Houses & Factions** (not_started -> in_progress)

## Decisions Made
1. **dec-047:** Chose Feudal Monarchy for Eldoria (over Theocratic Council, Merchant Republic)
   - *Rationale:* Traditional fantasy feel with clear power hierarchies
2. **dec-048:** Named the ruling dynasty "House Valdris"
   - *Rationale:* Strong-sounding name that implies authority
3. **dec-049:** Set succession as elective among noble houses
   - *Rationale:* Creates political intrigue and conflict potential

## Entities Created
- `eldoria-government` (political_system) -- Canon
- `house-valdris` (faction) -- Canon

## Entities Modified
- `eldoria-history` -- Updated founding date to be consistent

## Contradictions Resolved
- **con-008:** Kingdom age discrepancy (500 vs 300 years) -- resolved in favor of 500 years

## Cross-References Established
- eldoria-government <-> house-valdris (rules)
- house-valdris <-> eldoria-history (founded_by)

## Notes
User expressed interest in developing succession crisis as a future plot hook.
```

---

## 9. How Each Tracking Need Is Met

### 9.1 Every Decision

**Primary:** `decision_made` events in the event log capture the full decision context -- question, all options presented, chosen option, rejected options, and user rationale.

**Secondary:** `decisions.json` index provides fast querying of all decisions, filterable by step, date, entity, or keyword.

**Example query:** "What were the other options for the magic system?"
- Claude Code reads `decisions.json`, filters by step_id matching the magic system step, and retrieves the rejected options.

### 9.2 Every Draft

**Primary:** `draft_created` events record when drafts are created. The `entity-registry.json` tracks current status of every entity (draft vs. canon).

**Secondary:** The actual draft content lives in `user-world/` as Markdown files. The entity registry points to the file and records its status.

### 9.3 Canon vs. Draft Status

**Primary:** `entity-registry.json` has a `status` field for every entity: `"draft"`, `"canon"`, or `"archived"`.

**Secondary:** `status_changed` events in the event log record every status transition with timestamps and reasons.

**Mechanism:** When the user approves a draft, Claude Code:
1. Appends a `status_changed` event to the event log
2. Updates the entity's status in `entity-registry.json`
3. Commits the change to git with a descriptive message

### 9.4 Session Logs

**Primary:** `session_started` and `session_ended` events bracket each session in the event log.

**Secondary:** Structured Markdown session summaries in `bookkeeping/sessions/` provide a human-readable journal of each session.

**Mechanism:** At the end of each session, Claude Code generates the session summary automatically from the events logged during that session.

### 9.5 Revision History

**Primary:** `entity_revised` events capture every change to canon content, including content hashes, change summaries, and reasons.

**Secondary:** `revisions-by-entity.json` provides per-entity revision timelines. When important content is superseded, the old version is saved as a snapshot file in `bookkeeping/revisions/snapshots/`.

### 9.6 Option Generation History

**Primary:** Every `decision_made` event includes the full `options_presented` array with all 2-4 options, their summaries, and which was chosen vs. rejected.

**Secondary:** `decisions.json` index preserves this information in queryable form.

### 9.7 Cross-Reference Audit Trail

**Primary:** `cross_reference_created` events record when entity links are established, including the session in which they were created.

**Secondary:** `cross-references.json` provides a queryable registry of all active links.

### 9.8 Progression History

**Primary:** `step_status_changed` events track every progression step transition.

**Secondary:** `progression.json` provides a current-state view of all 52 steps with their histories.

### 9.9 Contradiction Resolutions

**Primary:** `contradiction_found` and `contradiction_resolved` event pairs track the full lifecycle of each contradiction.

**Secondary:** `contradictions.json` provides a queryable index of all contradictions, their status, and resolutions.

### 9.10 Creative Rationale

**Primary:** The `user_rationale` field in `decision_made` events captures why the user chose what they chose.

**Secondary:** Session summaries can include additional context and notes about the user's creative direction.

---

## 10. Concrete Examples

### Example 1: User Makes a Decision

**User says:** "I like option A, the feudal monarchy. It fits the traditional fantasy feel I'm going for."

**Claude Code automatically:**

1. Appends to `bookkeeping/events/events-2026-01.jsonl`:
```json
{"event_id":"evt-20260130-143022-001","timestamp":"2026-01-30T14:30:22","session_id":"ses-20260130-001","event_type":"decision_made","step_id":"step-03","entity_id":"world-government-type","data":{"decision_id":"dec-047","question":"What type of government rules Eldoria?","options_presented":[{"option_id":"opt-047-A","label":"Feudal Monarchy","summary":"A hereditary king rules through a hierarchy of lords and vassals."},{"option_id":"opt-047-B","label":"Theocratic Council","summary":"A council of high priests governs based on divine mandate."},{"option_id":"opt-047-C","label":"Merchant Republic","summary":"Wealthy trade guilds elect a leader from among their ranks."}],"chosen_option":"opt-047-A","rejected_options":["opt-047-B","opt-047-C"],"user_rationale":"Traditional fantasy feel with clear power hierarchies.","replaces_decision":null}}
```

2. Updates `bookkeeping/indexes/decisions.json` -- adds the new decision entry.

3. Updates `bookkeeping/indexes/progression.json` -- records activity on step-03.

4. Proceeds with the worldbuilding workflow (creating the government content).

### Example 2: User Revises a Canon Entry

**User says:** "Actually, I want to change Eldoria's succession from hereditary to elective. It creates more drama."

**Claude Code automatically:**

1. Saves the current version of `user-world/politics/eldoria-government.md` as a snapshot:
   `bookkeeping/revisions/snapshots/eldoria-government-rev1.md`

2. Appends an `entity_revised` event to the event log.

3. Updates `revisions-by-entity.json` with the new revision entry.

4. Updates the actual content in `user-world/politics/eldoria-government.md`.

5. Appends a `decision_made` event (since this revision is itself a decision).

6. Updates `decisions.json` and marks the old decision as superseded.

### Example 3: User Asks a History Question

**User says:** "What were the other options when I chose the government type?"

**Claude Code automatically:**

1. Reads `bookkeeping/indexes/decisions.json`.
2. Searches for decisions related to government type.
3. Finds `dec-047` with its full options list.
4. Responds: "When you chose the government type for Eldoria, I presented three options:
   - **Option A: Feudal Monarchy** (your choice) -- A hereditary king rules through lords and vassals
   - **Option B: Theocratic Council** (rejected) -- A council of high priests governs by divine mandate
   - **Option C: Merchant Republic** (rejected) -- Trade guilds elect a leader

   You chose the Feudal Monarchy because you wanted a traditional fantasy feel with clear power hierarchies."

### Example 4: End of Session

**At session end, Claude Code automatically:**

1. Appends a `session_ended` event to the event log.

2. Generates `bookkeeping/sessions/session-2026-01-30-001.md` with a structured summary.

3. Commits all changes to git:
   ```
   git add -A
   git commit -m "Session 15: Government & political structures

   - Chose feudal monarchy for Eldoria (dec-047)
   - Created House Valdris as ruling dynasty (dec-048)
   - Set elective succession (dec-049)
   - Resolved kingdom age contradiction (con-008)
   - Step 03 completed, Step 04 started"
   ```

---

## 11. Query Patterns

These are the types of questions the system can answer, and how:

| Question | Source File | Method |
|----------|------------|--------|
| "What did I decide about X?" | `decisions.json` | Filter by keyword in question/entity fields |
| "What were the other options for X?" | `decisions.json` | Look up decision, read rejected options |
| "Why did I choose X?" | `decisions.json` | Read rationale field |
| "What did I do last session?" | Latest `session-*.md` | Read the file directly |
| "When did I start step 5?" | `progression.json` | Look up step-05, read started timestamp |
| "What steps are still incomplete?" | `progression.json` | Filter by status != completed |
| "Is X canon or still a draft?" | `entity-registry.json` | Look up entity, read status |
| "What has changed since last session?" | Event log | Filter events by session_id |
| "What references X?" | `cross-references.json` | Filter by target entity |
| "What contradictions are unresolved?" | `contradictions.json` | Filter by status == open |
| "How has X evolved over time?" | `revisions-by-entity.json` | Look up entity, read revision timeline |
| "What was X before I changed it?" | Revision snapshots | Read the snapshot file |
| "How many decisions have I made?" | `decisions.json` | Read total_decisions count |
| "What entities were created in step 3?" | `entity-registry.json` | Filter by step_id |

---

## 12. Automation Strategy

### 12.1 When Does Bookkeeping Happen?

Claude Code performs bookkeeping at these moments, all silently:

| Trigger | Actions |
|---------|---------|
| **Session starts** | Append `session_started` event; load indexes into working memory |
| **Options presented** | (Held in memory until user decides) |
| **User makes a decision** | Append `decision_made` event; update `decisions.json` |
| **Draft content created** | Append `draft_created` event; update `entity-registry.json` |
| **Draft promoted to canon** | Append `status_changed` event; update `entity-registry.json` |
| **Canon content revised** | Save snapshot; append `entity_revised` event; update revision index |
| **Cross-reference created** | Append `cross_reference_created` event; update `cross-references.json` |
| **Contradiction found** | Append `contradiction_found` event; update `contradictions.json` |
| **Contradiction resolved** | Append `contradiction_resolved` event; update `contradictions.json` |
| **Step status changes** | Append `step_status_changed` event; update `progression.json` |
| **Session ends** | Append `session_ended` event; generate session summary; git commit |

### 12.2 Implementation in Claude Code

Claude Code manages this through the engine layer (Python scripts). The bookkeeping module would be a Python module that the engine calls at the appropriate moments:

```python
# Simplified API that the engine would call:
from bookkeeping import BookkeepingManager

bk = BookkeepingManager("C:/Worldbuilding-Interactive-Program/bookkeeping")

# At session start
bk.start_session(focus="Government and Political Structures")

# When a decision is made
bk.record_decision(
    step_id="step-03",
    question="What type of government rules Eldoria?",
    options=[
        {"id": "A", "label": "Feudal Monarchy", "summary": "..."},
        {"id": "B", "label": "Theocratic Council", "summary": "..."},
        {"id": "C", "label": "Merchant Republic", "summary": "..."},
    ],
    chosen="A",
    rationale="Traditional fantasy feel with clear power hierarchies."
)

# When an entity is created
bk.record_entity_created(
    entity_id="eldoria-government",
    entity_type="political_system",
    name="Eldoria Government",
    status="draft",
    file_path="user-world/politics/eldoria-government.md",
    step_id="step-03"
)

# When a cross-reference is established
bk.record_cross_reference(
    source="eldoria-government",
    target="house-valdris",
    relationship="rules",
    description="House Valdris holds the throne of Eldoria."
)

# At session end
bk.end_session(summary="Established feudal government, created ruling dynasty.")
```

### 12.3 User Experience

The user experiences none of the bookkeeping complexity. From their perspective:

1. They talk to Claude Code about their world
2. They make creative decisions
3. They can ask "what did I decide about X?" or "what were my other options?" and get instant answers
4. They can ask "what did I do last time?" and see their session summary
5. They can ask "what's still left to do?" and see their progression
6. Everything just works

---

## 13. Storage Projections

### 13.1 Estimated Sizes

| Component | Per Unit | Estimated Total |
|-----------|----------|-----------------|
| Event log entries | ~500 bytes each | ~500 events x 500B = **250 KB** |
| Decision index | ~300 bytes each | ~200 decisions x 300B = **60 KB** |
| Session summaries | ~2 KB each | ~100 sessions x 2KB = **200 KB** |
| Entity registry | ~200 bytes each | ~150 entities x 200B = **30 KB** |
| Cross-references | ~150 bytes each | ~500 links x 150B = **75 KB** |
| Revision snapshots | ~3 KB each | ~100 revisions x 3KB = **300 KB** |
| Progression tracker | Fixed | **~15 KB** |
| Contradictions | ~200 bytes each | ~50 x 200B = **10 KB** |
| **Total bookkeeping overhead** | | **~1 MB** |

The entire bookkeeping system for a complete worldbuilding project would occupy approximately 1 MB of storage. This is negligible.

### 13.2 Performance

- **Appending an event:** Instantaneous (file append, no parsing needed)
- **Updating an index:** < 100ms (read JSON, modify in memory, write back)
- **Querying an index:** < 50ms (read JSON, filter in Python)
- **Generating session summary:** < 200ms (scan session events, format Markdown)

All operations are well within the latency tolerance of an interactive Claude Code session.

---

## 14. Sources

### AI Project Management and Decision Logging
- [Jamie AI - What is a Decision Log?](https://www.meetjamie.ai/blog/decision-log)
- [Forecast - Best AI Project Management Tools 2026](https://www.forecast.app/blog/10-best-ai-project-management-software)
- [Capterra - 2025 PM Software Trends Report](https://www.capterra.com/resources/2025-pm-software-trends/)

### Creative Writing Version Control and Worldbuilding
- [Ink & Switch - Upwelling: Real-time Collaboration with Version Control for Writers](https://www.inkandswitch.com/upwelling/)
- [Invisible Publishing - Git for Creative Writing](https://invisiblepublishing.com/2017/07/12/my-friend-git/)
- [World Anvil - Worldbuilding Templates](https://www.worldanvil.com/features/worldbuilding-templates)
- [LegendKeeper - Worldbuilding Tool](https://www.legendkeeper.com/)
- [Arcweave - Top 10 Tools for Worldbuilding](https://blog.arcweave.com/top-10-tools-for-worldbuilding)
- [Automateed - World Building Software 2026](https://www.automateed.com/world-building-software)
- [Campfire Writing - Collaborative Worldbuilding](https://www.campfirewriting.com/learn/collaborative-worldbuilding)

### Architectural Decision Records (ADRs)
- [ADR GitHub Organization](https://adr.github.io/)
- [Joel Parker Henderson - Architecture Decision Records](https://github.com/joelparkerhenderson/architecture-decision-record)
- [MADR - Markdown Any Decision Records](https://adr.github.io/madr/)
- [Microsoft Azure - Architecture Decision Record](https://learn.microsoft.com/en-us/azure/well-architected/architect-role/architecture-decision-record)
- [AWS Prescriptive Guidance - ADR Process](https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/adr-process.html)
- [Claude ADR System Guide (GitHub Gist)](https://gist.github.com/joshrotenberg/a3ffd160f161c98a61c739392e953764)

### Event Sourcing
- [Martin Fowler - Event Sourcing](https://martinfowler.com/eaaDev/EventSourcing.html)
- [Microsoft Azure - Event Sourcing Pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/event-sourcing)
- [AWS - Event Sourcing Pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/event-sourcing.html)
- [Kurrent - Introduction to Event Sourcing](https://www.kurrent.io/event-sourcing)
- [Kurrent - Event Sourcing vs Audit Log](https://www.kurrent.io/blog/event-sourcing-audit)
- [Microservices.io - Event Sourcing Pattern](https://microservices.io/patterns/data/event-sourcing.html)
- [Python eventsourcing Library](https://eventsourcing.readthedocs.io/)

### Game Studio Lore Management
- [Game Developer - Building a Story Bible for Your Game](https://www.gamedeveloper.com/design/building-a-basic-story-bible-for-your-game)
- [StoryFlint - How to Create a World Building Bible](https://www.storyflint.com/blog/world-building-bible)
- [All That's Epic - Building Your Own Lore Bible](https://allthatsepic.com/blog/building-your-own-lore-bible-how-creators-construct-consistent-and-expansive-universes)
- [Dabble Writer - Worldbuilding Bible Guide](https://www.dabblewriter.com/articles/worldbuilding-bible)

### SQLite and Python Logging
- [Simon Willison - sqlite-history: Tracking Changes with Triggers](https://simonwillison.net/2023/Apr/15/sqlite-history/)
- [IT Trip - Implementing Logging and Audit Trails with SQLite in Python](https://en.ittrip.xyz/python/sqlite-logging-audit-trail)
- [sqlogging - SQLite3-based Logging for Python](https://github.com/brohrer/sqlogging)

### Claude Code Session Tracking
- [Claude Code Docs - Monitoring](https://code.claude.com/docs/en/monitoring-usage)
- [Anthropic - Claude Code Best Practices](https://www.anthropic.com/engineering/claude-code-best-practices)
- [LangChain - Trace Claude Code](https://docs.langchain.com/langsmith/trace-claude-code)
- [GitHub Issue #522 - Automated Project Tracking for Claude Sessions](https://github.com/anthropics/claude-code/issues/522)
- [Ben Newton - Command-Driven Development Logging with Claude Code](https://benenewton.com/blog/command-driven-development-logging-claude)

### Obsidian and Knowledge Management
- [Obsidian.md](https://obsidian.md/)
- [Obsidian for Writers (Medium)](https://medium.com/@mixasite/obsidian-for-writers-building-a-comprehensive-writing-system-and-capturing-ideas-effectively-970a7b86918)

### Git-Based Audit Trails
- [Kosli - Using Git for a Compliance Audit Trail](https://www.kosli.com/blog/using-git-for-a-compliance-audit-trail/)
- [UK Government Best Practice - Version Control](https://best-practice-and-impact.github.io/qa-of-code-guidance/version_control.html)
- [The Data Savvy Corner - GitHub Audit Trail](https://thedatasavvycorner.com/blogs/19-github-audit-trail)
- [Ziflow - Version Control in Creative Project Management](https://www.ziflow.com/blog/version-control-project-management)
