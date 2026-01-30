# Scale Gaps Research: What We Are Missing

**Date:** 2026-01-30
**Purpose:** Identify systems, patterns, and infrastructure gaps for a large-scale worldbuilding program (hundreds of thousands of lines, 500+ entity files, non-technical user, Claude Code on Windows with Python 3.13).

**Rating Key:**
- **CRITICAL** -- Must have before the user starts building their world
- **IMPORTANT** -- Should add within the first few weeks of use
- **NICE-TO-HAVE** -- Add when the need becomes apparent

---

## Table of Contents

1. [Backup and Disaster Recovery](#1-backup-and-disaster-recovery)
2. [Performance at Scale (JSON to SQLite Migration)](#2-performance-at-scale)
3. [Search and Discovery](#3-search-and-discovery)
4. [Visualization](#4-visualization)
5. [Export and Portability](#5-export-and-portability)
6. [Multi-Session Continuity](#6-multi-session-continuity)
7. [Branching and What-If Exploration](#7-branching-and-what-if-exploration)
8. [Collaboration](#8-collaboration)
9. [Content Generation Quality](#9-content-generation-quality)
10. [Testing and Validation](#10-testing-and-validation)
11. [Additional Gaps from Research](#11-additional-gaps-from-research)

---

## 1. Backup and Disaster Recovery

**Rating: CRITICAL**

### The Problem

Git tracks changes, but it does not protect against:
- Corrupted `.git` directory (single point of failure on one machine)
- Accidental `git reset --hard` or branch deletion
- Disk failure, ransomware, or Windows Update breaking things
- The user accidentally deleting files outside of Claude Code

Git is version control, not backup. These are different things.

### Research Findings

The industry standard is the **3-2-1 rule**: 3 copies of data, on 2 different media, with 1 offsite. Game studios using Git typically pair it with automated backup systems that create timestamped snapshots. A real-world case study showed that migrating from thousands of JSON files to consolidated storage reduced the blast radius of corruption events dramatically.

Versioned backups (timestamped directory copies) allow recovery to any point in time, independent of Git history. Incremental backups save only changes since the last backup, conserving space.

### Recommendations

1. **Automated local backup script (CRITICAL):** A Python script triggered by a Claude Code hook (PostToolUse on file writes) that:
   - Copies the entire world data directory to a timestamped backup folder (e.g., `backups/2026-01-30_14-30/`)
   - Keeps the last 20 backups, deletes older ones (rotation)
   - Runs silently in the background
   - Implementation: ~50 lines of Python using `shutil.copytree` and `datetime`

2. **Cloud sync (IMPORTANT):** If the user has OneDrive, Google Drive, or Dropbox, place the project folder inside the synced directory. This gives automatic offsite backup with zero configuration.

3. **Git bundle export (IMPORTANT):** A weekly hook or command that runs `git bundle create world-backup.bundle --all`, producing a single file containing the entire Git history. This file can be copied to a USB drive or cloud storage.

4. **Pre-operation snapshots (CRITICAL):** Before any destructive operation (bulk edits, schema migrations, refactors), automatically create a full snapshot. This is the safety net the non-technical user will actually need.

### Implementation Estimate
- Backup script: 1-2 hours
- Hook integration: 30 minutes
- Cloud sync setup: user configuration only

---

## 2. Performance at Scale

**Rating: CRITICAL**

### The Problem

At 500+ JSON entity files, every operation that needs to scan or cross-reference entities will suffer from:
- File I/O overhead (opening, reading, parsing 500+ files)
- JSON parsing cost (Python's `json.load` on every file, every time)
- No indexing (to find "all entities with fire magic" you must read every file)
- Memory pressure (loading all entities into RAM for cross-referencing)

### Research Findings

A compelling case study involved an application managing tens of thousands of JSON configuration files. Migrating to SQLite reduced startup time from **30 minutes to 10 seconds** (180x improvement) and storage by 22.5x. The key insight: "The fastest possible way to parse something is to not parse it at all." SQLite's in-memory database mode eliminates the parsing step entirely.

Tailscale's migration from JSON files showed write latency dropping from nearly a second to milliseconds after moving off JSON.

SQLite's JSONB format (available in recent versions) provides an additional 3x speedup for JSON-heavy operations within the database.

### Recommendations

1. **Plan for SQLite migration now, execute at ~100 entities (CRITICAL):**
   - Design the system so JSON files are the *authoring format* (human-readable, Git-friendly) but SQLite is the *runtime format* (queried by Claude Code during sessions)
   - A sync script converts JSON files to SQLite on startup
   - This dual approach keeps Git diffs readable while giving query performance

2. **Indexing layer (CRITICAL):**
   - Build indexes on entity type, name, tags, relationships, and geographic region
   - Use SQLite indexes (`CREATE INDEX`) on commonly queried fields
   - This turns "find all coastal settlements" from a 500-file scan into a millisecond query

3. **Lazy loading with caching (IMPORTANT):**
   - Do not load all entities at once
   - Cache frequently accessed entities in memory during a session
   - Invalidate cache when files change

4. **Architecture decision: JSON files as source of truth, SQLite as derived index:**
   ```
   JSON files (Git-tracked, human-readable)
       |
       v  [sync script on startup]
   SQLite database (runtime queries, FTS, indexes)
       |
       v  [write-back on entity updates]
   JSON files updated
   ```

### Implementation Estimate
- SQLite sync script: 4-6 hours
- Index design: 2-3 hours
- Cache layer: 3-4 hours

---

## 3. Search and Discovery

**Rating: CRITICAL**

### The Problem

The user (via Claude) needs to ask questions like:
- "Show me all settlements near the coast"
- "Which characters have fire magic?"
- "Find every entity that mentions the Dragon Wars"
- "What factions are allied with the Iron Kingdom?"

Without full-text search, Claude must read every file to answer these questions. At 500+ entities, this will exhaust context windows and be painfully slow.

### Research Findings

SQLite FTS5 (Full-Text Search 5) is the standard lightweight solution. It:
- Creates an inverted index mapping every word to the documents containing it
- Supports Boolean queries (AND, OR, NOT)
- Provides BM25 relevance ranking (same algorithm as search engines)
- Supports custom tokenizers for handling fantasy names and terminology
- Works with external content tables (index points to data stored elsewhere)
- Is built into Python's `sqlite3` module (though FTS5 may need `pysqlite3` on some systems)

### Recommendations

1. **SQLite FTS5 index (CRITICAL):**
   ```python
   # Create FTS5 virtual table
   CREATE VIRTUAL TABLE entity_search USING fts5(
       name,
       entity_type,
       description,
       tags,
       full_text,
       content='entities',
       content_rowid='id',
       tokenize='porter unicode61'
   );
   ```
   - The `porter` tokenizer handles stemming ("settlements" matches "settlement")
   - `unicode61` handles accented/fantasy characters
   - `content='entities'` links to the main entities table without duplicating data

2. **Tag-based search (CRITICAL):**
   - Every entity should have a `tags` array in its JSON schema
   - Tags like `["coastal", "settlement", "fire-magic", "faction:iron-kingdom"]`
   - SQLite query: `SELECT * FROM entities WHERE tags LIKE '%coastal%'`
   - Or better: a separate `entity_tags` junction table for proper relational queries

3. **Relationship traversal (IMPORTANT):**
   - The knowledge graph already handles this, but ensure it is queryable
   - "Find all entities within 2 relationship hops of Character X"
   - SQLite recursive CTEs can handle graph traversal

4. **Semantic search (NICE-TO-HAVE, future):**
   - Embed entity descriptions using a local embedding model
   - Store vectors in SQLite (or a vector store)
   - Enable "find entities similar to this one" queries
   - This is the RAG research already in progress

### Implementation Estimate
- FTS5 setup: 2-3 hours (builds on the SQLite migration from Gap #2)
- Tag system: 1-2 hours
- Relationship traversal queries: 2-3 hours

---

## 4. Visualization

**Rating: IMPORTANT**

### The Problem

A non-technical user building a world with hundreds of entities will quickly lose track of relationships, hierarchies, and geography without visual aids. Text descriptions alone cannot convey:
- Family trees and lineage
- Faction alliances and rivalries
- Geographic proximity
- Timelines and event sequences
- Magic system hierarchies

### Research Findings

Two primary text-to-diagram tools are well-suited:

**Mermaid.js:**
- Text-based diagram syntax that renders to SVG/PNG
- Supported natively in GitHub, VS Code, and many Markdown renderers
- Good for: flowcharts, entity relationship diagrams, timelines, mind maps
- Easy for Claude to generate (it is just text)
- Example: family tree, faction relationship map, quest flowchart

**Graphviz:**
- DOT language for graph descriptions
- Better for large, complex hierarchies and networks
- Renders well in headless environments (can generate PDF/SVG from command line)
- Better suited for: genealogies, political structures, large relationship graphs
- `pip install graphviz` works on Windows (requires Graphviz system install)

**LegendKeeper and World Anvil** both emphasize interactive maps and timelines as core features. LegendKeeper's "four pillars" are: Wiki, Maps, Whiteboards, and Timelines.

### Recommendations

1. **Mermaid diagram generation (IMPORTANT):**
   - Claude can generate Mermaid syntax from entity data
   - Save as `.mmd` files, render to SVG/PNG using `mmdc` (Mermaid CLI)
   - Install: `npm install -g @mermaid-js/mermaid-cli`
   - Types to support:
     - `graph TD` for faction hierarchies
     - `gantt` for timelines
     - `erDiagram` for entity relationships
     - `mindmap` for concept exploration

2. **Graphviz for complex graphs (IMPORTANT):**
   - Install: `pip install graphviz` + system Graphviz binaries
   - Generate DOT files from the knowledge graph
   - Render to SVG/PNG/PDF: `dot -Tsvg graph.dot -o graph.svg`
   - Better than Mermaid for graphs with 50+ nodes

3. **Auto-generated relationship maps (IMPORTANT):**
   - A Python script that reads the knowledge graph and outputs Mermaid/Graphviz
   - Triggered by user request: "Show me the relationship map for the Northern Kingdoms"
   - Filter by entity type, region, or relationship type

4. **Timeline visualization (NICE-TO-HAVE):**
   - Generate HTML timelines using `timeline.js` or similar
   - Or use Mermaid's `gantt` chart with eras as tasks

5. **Simple web viewer (NICE-TO-HAVE):**
   - A local Python HTTP server (`python -m http.server`) serving generated SVG files
   - The user opens `localhost:8000` in their browser to see diagrams
   - No deployment needed, runs locally

### Implementation Estimate
- Mermaid generation scripts: 3-4 hours
- Graphviz generation scripts: 3-4 hours
- Auto-generated relationship maps: 4-6 hours
- Timeline visualization: 4-6 hours

---

## 5. Export and Portability

**Rating: IMPORTANT**

### The Problem

The world data is locked in JSON files. The user may want to:
- Share their world as a readable document (PDF)
- Publish a wiki-style website
- Import into a game engine (Unity, Unreal, Godot)
- Move to a different worldbuilding platform (World Anvil, LegendKeeper)
- Print a physical lore bible

### Research Findings

The Urdr platform emphasizes that "when your lore is structured, exporting is a mapping problem." This is the key insight: because the 84 JSON schemas impose structure, export becomes a template transformation problem, not a content extraction problem.

Python static site generators like **Papery** and **staticjinja** natively support JSON data sources with Jinja2 templates. **MkDocs** (with the Material theme) can generate professional documentation sites from Markdown.

### Recommendations

1. **Jinja2 export templates (IMPORTANT):**
   - Define Jinja2 templates for each entity type
   - Templates produce Markdown, HTML, or LaTeX output
   - Example: `character.md.j2` transforms a character JSON into a readable Markdown page
   - This is a natural extension of the existing 84 JSON schemas

2. **PDF export via Markdown-to-PDF (IMPORTANT):**
   - Pipeline: JSON -> Jinja2 -> Markdown -> PDF
   - Use `pandoc` (install on Windows) or `weasyprint` (Python library)
   - Generate a complete "Lore Bible" PDF with table of contents, chapters by region/faction/era
   - `pip install weasyprint` or install Pandoc separately

3. **Static wiki site (NICE-TO-HAVE):**
   - Use MkDocs with Material theme: `pip install mkdocs-material`
   - Generate Markdown files from JSON, MkDocs renders them as a searchable website
   - Deploy to GitHub Pages for free hosting, or view locally
   - Cross-links between entities become hyperlinks automatically

4. **Game engine export (NICE-TO-HAVE):**
   - JSON is already the native data format for most game engines
   - Provide export scripts that restructure JSON to match common engine formats
   - Unity: JSON files in `Resources/` folder, loaded via `JsonUtility`
   - Godot: JSON files loaded via `FileAccess` and `JSON.parse()`

5. **Platform migration export (NICE-TO-HAVE):**
   - World Anvil and LegendKeeper have import capabilities
   - Map JSON schemas to their expected formats
   - This is a one-time script per target platform

### Implementation Estimate
- Jinja2 templates for all 84 schemas: 8-12 hours (can be incremental)
- PDF pipeline: 3-4 hours
- MkDocs site: 4-6 hours
- Game engine exporters: 2-4 hours each

---

## 6. Multi-Session Continuity

**Rating: CRITICAL**

### The Problem

The user will work on this world across dozens or hundreds of Claude Code sessions over months or years. Each new session, Claude starts fresh. CLAUDE.md helps, but it has limits:
- CLAUDE.md cannot contain the full state of a world with 500+ entities
- The user may forget what they were working on last session
- Decisions made 3 months ago may be forgotten or contradicted
- There is no "project journal" showing what happened over time

### Research Findings

The **Session Continuity Protocol (SCP)** is a lightweight method specifically designed for preventing "session amnesia" in LLM projects. It treats each new session as "onboarding a capable new developer who has not attended prior meetings." SCP uses:
- **Project Memory Pack (PMP):** Compact, versioned project state
- **Decision Log (ADR-lite):** Short decision records capturing rationale
- **Changelog/Diff:** Delta summary of changes since last session

Claude Code's own documentation emphasizes: "The key insight is treating documentation as external memory -- what gets written down persists across sessions, while what stays in conversation memory disappears."

Research on recursive summarization shows that continuously integrating historical information into real-time memory (structured, under 20 sentences) enables long-distance dependency modeling.

### Recommendations

1. **Session journal system (CRITICAL):**
   - At the end of every session, Claude auto-generates a session summary
   - Stored in `sessions/YYYY-MM-DD_session-NNN.md`
   - Contains: what was created, what was modified, decisions made, open questions
   - At the start of every session, Claude reads the last 3-5 session summaries
   - Implementation: Claude Code hook (PostToolUse or session end trigger)

2. **Decision log (CRITICAL):**
   - File: `decisions/decision-log.jsonl` (one JSON object per line)
   - Each entry: `{"date": "...", "decision": "...", "rationale": "...", "alternatives_rejected": [...], "entities_affected": [...]}`
   - Claude consults this before proposing changes that might contradict past decisions
   - This is distinct from the canon consistency checker -- it captures *why*, not just *what*

3. **Project state summary (CRITICAL):**
   - Auto-generated file: `state/project-summary.md`
   - Updated after every session
   - Contains: entity counts by type, recent changes, current focus areas, open threads
   - This is what goes into CLAUDE.md or is read at session start
   - Keep it under 2000 tokens for context efficiency

4. **"Where was I?" command (IMPORTANT):**
   - A slash command or prompt that Claude recognizes
   - Reads session journal, decision log, and project summary
   - Produces a briefing: "Last session you created 3 new characters in the Northern Reach and were exploring the question of whether fire magic should be hereditary."

5. **Milestone markers (IMPORTANT):**
   - When major creative milestones are reached (e.g., "The Northern Reach region is complete"), record them
   - Helps the user and Claude track progress through the world

### Implementation Estimate
- Session journal system: 3-4 hours
- Decision log: 2-3 hours
- Project state summary: 2-3 hours
- "Where was I?" command: 1-2 hours

---

## 7. Branching and What-If Exploration

**Rating: IMPORTANT**

### The Problem

The user may want to:
- Explore "What if the Dragon Wars ended differently?"
- Try two different versions of a character's backstory
- Test whether a plot thread works before committing it to canon
- Compare alternate versions of a region's history

Overwriting canon to test ideas is destructive and risky.

### Research Findings

Game studios use Git branching exactly this way. As one source put it: "If you want to try something radical without cluttering or polluting your codebase, you simply branch. If the idea doesn't pan out, just leave the branch." Git branching is essentially "alternate timelines" for your project.

Git Flow provides a structured model: `main` (canon), `develop` (work in progress), and `feature/*` branches (experiments). This maps naturally to worldbuilding:
- `main` = canonical lore
- `explore/what-if-dragon-wars-alt` = experimental branch
- Merge back to `main` if the user likes the result

AI creative writing tools like Sudowrite and Squibler offer "branching storylines" as a core feature, allowing users to explore multiple narrative paths without losing the original.

### Recommendations

1. **Git branch abstraction for the non-technical user (IMPORTANT):**
   - Claude handles all Git commands behind the scenes
   - User says: "I want to explore an alternate version where the Elves won the war"
   - Claude runs: `git checkout -b explore/elves-won-the-war`
   - User explores freely
   - When done: "I like this version" (merge) or "Discard this" (delete branch)
   - The user never sees Git commands

2. **Branch management UI (IMPORTANT):**
   - A command like "Show me my explorations" that lists active branches
   - "Compare this exploration to canon" that runs `git diff main`
   - "Merge this exploration into canon" that runs `git merge`

3. **Snapshot-based alternative (simpler) (IMPORTANT):**
   - If Git branching is too complex, use directory-level snapshots
   - "Explore alternate" copies the current state to `explorations/elves-won/`
   - User works in the copy
   - "Accept alternate" copies changes back to the main directory
   - Less elegant but more transparent

4. **Comparison view (NICE-TO-HAVE):**
   - Show the user a diff between the exploration and canon
   - "In the alternate version, the Elves control the Northern Reach instead of humans"
   - Claude generates a narrative summary of the differences

### Implementation Estimate
- Git branch abstraction: 3-4 hours
- Branch management commands: 2-3 hours
- Comparison/narrative diff: 2-3 hours

---

## 8. Collaboration

**Rating: NICE-TO-HAVE**

### The Problem

Could multiple people work on the same world? Is this relevant for this project?

### Research Findings

Tools like LegendKeeper and Kanka emphasize real-time collaboration as a core feature. Arcweave allows "invite writers, designers, artists, and other players to craft your world together in real-time." Game studios with narrative teams of 5-20 people absolutely need this.

However, this project runs in Claude Code on one machine for one user. Multi-user collaboration would require:
- A shared repository (GitHub/GitLab)
- Merge conflict resolution for JSON files
- Access control (who can edit what)
- Real-time sync (complex)

### Recommendations

1. **Not needed for initial deployment.** The user is solo.

2. **If collaboration becomes needed later (NICE-TO-HAVE):**
   - Use a shared Git repository (GitHub private repo)
   - Each collaborator works in their own Claude Code instance
   - Pull/push to sync changes
   - JSON files handle merge conflicts reasonably well (each entity is a separate file)
   - The existing validation system catches inconsistencies introduced by parallel edits

3. **Read-only sharing is easier (NICE-TO-HAVE):**
   - The export system (Gap #5) can generate a website or PDF
   - Share that with collaborators, beta readers, or players
   - They read, you write

### Implementation Estimate
- Shared Git setup: 1-2 hours (user configuration)
- No code changes needed for basic collaboration

---

## 9. Content Generation Quality

**Rating: CRITICAL**

### The Problem

The system generates 2-4 options per worldbuilding step. If these options are generic, repetitive, or tropey, the entire project fails at its core purpose. Research shows LLMs suffer from a "homogenization effect" -- they converge on similar outputs across generations, and this problem gets worse at scale.

### Research Findings

A PNAS study found that GPT-4 and LLaMA-3 produce stories with "echoed" plot elements across generations -- an "Artificial Hivemind" effect. Each additional human-written essay contributed more new ideas than each AI-generated essay, and this gap widened as more essays were generated. The problem persists "despite efforts to enhance AI-generated content through both prompt and parameter modifications."

Key techniques identified by research:

1. **G2 (Guide-to-Generation):** A training-free strategy using three modules: base generator (quality), Diversity Guide (novelty), and Dedupe Guide (repetition suppression). "Significantly improves output diversity while maintaining high response quality."

2. **CreativeDC (Divergent-Convergent Prompting):** Inspired by psychological models of creativity. Phase 1: divergent exploration (brainstorm widely). Phase 2: convergent refinement (select and develop the best). "Explicitly structuring LLM prompting according to psychological models of creativity significantly enhances output originality."

3. **Random Concept Injection:** Infusing a random word or concept into the prompt. "Effective at improving LLM generations... resulting in statistically significant improvements in both the number of unique responses and the entropy of the response distribution."

4. **Persona Simulation:** Inserting a sampled persona description into the prompt increases output diversity via role-play.

5. **Temperature and top-p alone are insufficient.** Higher temperature increases randomness but sacrifices quality. The trade-off is real.

### Recommendations

1. **Divergent-convergent option generation (CRITICAL):**
   - Step 1: Generate 8-10 raw ideas with high temperature (divergent phase)
   - Step 2: Filter and refine to 2-4 polished options (convergent phase)
   - Step 3: Present only the refined options to the user
   - This mirrors how creative professionals actually ideate

2. **Anti-repetition tracking (CRITICAL):**
   - Maintain a log of previously generated options and their themes
   - File: `generation/option-history.jsonl`
   - Before presenting options, check that they do not repeat themes from the last N generations
   - Include this history in the prompt: "Avoid these previously used themes: [list]"

3. **Random concept injection (IMPORTANT):**
   - Maintain a curated list of evocative words/concepts (500-1000 entries)
   - Randomly inject 1-2 into the generation prompt
   - Example: "Incorporate the concept of 'erosion' into at least one option"
   - This pushes Claude into unexpected creative territory

4. **Mythological source rotation (IMPORTANT):**
   - The 10 mythologies in the reference database should be rotated
   - Track which mythologies have been drawn from recently
   - Bias generation toward under-used sources
   - Prevents the world from becoming "Norse mythology with serial numbers filed off"

5. **Author style rotation (IMPORTANT):**
   - Similarly, rotate through the 6 author references
   - Each option can be "in the style of" a different author influence
   - This creates natural diversity in tone and approach

6. **Diversity metrics (NICE-TO-HAVE):**
   - After generating options, score them for diversity:
     - Theme overlap (low is good)
     - Vocabulary diversity (high is good)
     - Structural variety (different narrative shapes)
   - Regenerate if diversity score is below threshold

### Implementation Estimate
- Divergent-convergent pipeline: 4-6 hours
- Anti-repetition tracking: 2-3 hours
- Random concept injection: 1-2 hours
- Source rotation: 1-2 hours

---

## 10. Testing and Validation

**Rating: CRITICAL**

### The Problem

This is a system with 84 JSON schemas, knowledge graphs, validation layers, hooks, option generation, search, and backup. If any component breaks, the user (who is non-technical) cannot diagnose or fix it. The system must work correctly from day one.

### Research Findings

pytest is the standard Python testing framework, supporting:
- Fixtures for reusable test setup/teardown
- Parameterized tests for testing many inputs
- Module/session-scoped fixtures for expensive setup (like database creation)
- Integration tests that verify components work together

Best practice: "Generate consistent test data with factories, snapshots, or fixtures to avoid drift and unreliable validations."

### Recommendations

1. **Schema validation tests (CRITICAL):**
   - For each of the 84 JSON schemas, test that:
     - Valid entity JSON passes validation
     - Invalid entity JSON (missing required fields, wrong types) is rejected
     - Edge cases are handled (empty strings, very long text, Unicode characters)
   - Use `pytest.mark.parametrize` to test all schemas efficiently
   - Estimated: 1 test file per schema group, ~10-15 test files total

2. **Integration tests (CRITICAL):**
   - Test the full workflow: create entity -> validate -> store -> retrieve -> search
   - Test cross-entity operations: create two entities -> link them -> verify relationship
   - Test the option generation pipeline: request options -> verify they meet format requirements
   - Test backup/restore: create data -> backup -> corrupt data -> restore -> verify

3. **Consistency checker tests (CRITICAL):**
   - Feed the three-layer validation system known-good data (should pass)
   - Feed it known-bad data with specific contradictions (should catch them)
   - Test edge cases: circular relationships, orphaned entities, conflicting timelines

4. **Smoke test suite (CRITICAL):**
   - A single command (`python -m pytest tests/smoke/`) that verifies the entire system is operational
   - Tests: database connects, schemas load, search works, backup runs, hooks fire
   - Run this before the user starts every session (could be a startup hook)
   - Under 30 seconds total runtime

5. **Test data factory (IMPORTANT):**
   - A module that generates realistic test entities
   - Covers all 84 schema types
   - Produces both valid and deliberately invalid entities
   - Used by all test suites

6. **Performance benchmarks (IMPORTANT):**
   - Test with 100, 500, and 1000 simulated entities
   - Measure: search time, validation time, backup time, startup time
   - Set acceptable thresholds (e.g., search under 500ms, startup under 5 seconds)
   - Alert if performance degrades

### Implementation Estimate
- Schema validation tests: 6-8 hours
- Integration tests: 8-10 hours
- Smoke test suite: 2-3 hours
- Test data factory: 3-4 hours
- Performance benchmarks: 3-4 hours

---

## 11. Additional Gaps from Research

### 11a. Lore as Data, Not Pages

**Rating: CRITICAL**

**Source:** Urdr's "World Bible as Data" philosophy and game studio lore bible practices.

The Urdr platform articulates a principle that directly validates the JSON-first approach: "Production teams don't want lore as pages -- they want lore as data." And: "When your lore is structured, exporting is a mapping problem. Contradictions aren't 'opinions' -- you can't check what you can't structure."

**What this means for us:** The 84 JSON schemas are the right foundation. But ensure that:
- Every piece of lore has both a structured data representation AND a prose description
- The structured data drives validation and search
- The prose drives reading and export
- They are always in sync (the prose is generated from or validated against the data)

**Recommendation:** Add a `_prose` field to every entity schema that contains a human-readable narrative description. This field is auto-generated or manually written but always validated against the structured fields.

### 11b. Living Document Architecture

**Rating: IMPORTANT**

**Source:** Game studio narrative design practices (Anna Megill, Ubisoft; King's lore bible team).

Anna Megill (Ubisoft Massive lead writer) emphasizes that a story bible must be a "living document" -- not static, but designed to grow. King's narrative team maintains a lore bible that is "huge and takes forever to load but is awesome."

**What this means for us:** The system must gracefully handle:
- New entity types being added (schema evolution)
- Existing schemas gaining new fields (migration)
- Relationships changing meaning over time
- Retcons (deliberate changes to established canon)

**Recommendation:**
- Schema versioning: each schema has a `version` field
- Migration scripts: when a schema changes, a script updates all existing entities
- Retcon system: a way to mark "this was changed, here's why" (links to decision log)

### 11c. Error Recovery for Non-Technical Users

**Rating: CRITICAL**

**Source:** General software engineering best practice + the user profile.

When something goes wrong (and it will), the user cannot:
- Read Python tracebacks
- Debug JSON syntax errors
- Fix corrupted SQLite databases
- Resolve Git merge conflicts

**Recommendation:**
- Every error must produce a human-readable message: "Something went wrong while saving the character 'Aldric.' Your data is safe. Would you like me to try again?"
- Auto-recovery where possible: if JSON is malformed, restore from last backup
- A "health check" command that verifies all systems are working
- A "repair" command that fixes common issues (rebuild SQLite index, re-validate all entities, clean up temp files)

### 11d. Onboarding / Tutorial System

**Rating: IMPORTANT**

**Source:** World Anvil and LegendKeeper UX design; non-technical user requirement.

World Anvil is criticized for its "sharp learning curve" and "complicated UI." LegendKeeper is praised for being "more digestible for less experienced users." The non-technical user needs a guided introduction.

**Recommendation:**
- A "first run" experience that walks the user through creating their first entity
- Progressive disclosure: start with simple entities (a settlement, a character), introduce complexity over time
- A "help" command that explains what each system does in plain language
- Template suggestions: "You haven't created any religions yet. Would you like to start one?"

### 11e. Content Audit and World Health Dashboard

**Rating: IMPORTANT**

**Source:** Game studio pipeline management; LegendKeeper's four-pillar architecture.

As the world grows, the user needs to know:
- Which regions are well-developed vs. sparse?
- Are there orphaned entities (referenced but not created)?
- Are there entities that haven't been updated in months?
- What is the overall "completeness" of each region/faction/era?

**Recommendation:**
- A "world health" report generated on demand
- Metrics: entity count by type and region, relationship density, orphan detection, staleness (days since last edit)
- Visual output: a simple text table or Mermaid chart showing coverage
- "Suggested next steps" based on gaps: "The Southern Coast has locations but no characters. Would you like to populate it?"

### 11f. Rate Limiting and Cost Awareness

**Rating: IMPORTANT**

**Source:** Practical concern for any LLM-powered system at scale.

Generating 2-4 options per step, with divergent-convergent generation (8-10 raw ideas refined to 2-4), across hundreds of worldbuilding decisions means thousands of LLM calls. Claude Code usage has costs.

**Recommendation:**
- Track token usage per session and cumulative
- Offer "quick mode" (1 option, less exploration) vs. "deep mode" (4 options, full divergent-convergent)
- Cache option results so re-asking the same question does not regenerate
- Log: `usage/token-log.jsonl` with date, operation, tokens used

### 11g. Naming and Terminology Consistency

**Rating: IMPORTANT**

**Source:** King's lore bible practices; cross-team consistency challenges.

In large worlds, the same entity gets referred to by different names:
- "The Northern Reach" vs. "Northern Reaches" vs. "the North"
- "King Aldric" vs. "Aldric the Bold" vs. "the King"

**Recommendation:**
- A glossary/alias system in each entity's schema: `{"name": "Northern Reach", "aliases": ["The North", "Northern Reaches"]}`
- The validation system flags unknown names that are similar to known aliases
- Claude's generation prompts include the canonical name and aliases

---

## Summary Priority Matrix

### CRITICAL (Must have before the user starts)

| Gap | Description | Est. Hours |
|-----|-------------|-----------|
| 2 | Performance: SQLite migration architecture | 8-12 |
| 3 | Search: FTS5 full-text search | 4-6 |
| 6 | Multi-session: Session journal + decision log | 8-12 |
| 9 | Generation quality: Divergent-convergent + anti-repetition | 6-10 |
| 10 | Testing: Smoke tests + schema validation + integration | 20-28 |
| 1 | Backup: Automated local backups + pre-operation snapshots | 2-4 |
| 11a | Lore as data: Prose/data sync | 4-6 |
| 11c | Error recovery: Human-readable errors + auto-recovery | 4-6 |

**Total Critical: ~56-84 hours**

### IMPORTANT (Add within first few weeks)

| Gap | Description | Est. Hours |
|-----|-------------|-----------|
| 4 | Visualization: Mermaid + Graphviz generation | 10-14 |
| 5 | Export: Jinja2 templates + PDF pipeline | 12-16 |
| 7 | Branching: Git branch abstraction for what-if | 6-10 |
| 11b | Living document: Schema versioning + migration | 4-6 |
| 11d | Onboarding: Tutorial + progressive disclosure | 4-6 |
| 11e | World health: Audit dashboard + gap detection | 4-6 |
| 11f | Cost awareness: Token tracking + quick/deep modes | 2-3 |
| 11g | Naming consistency: Glossary/alias system | 2-3 |

**Total Important: ~44-64 hours**

### NICE-TO-HAVE (Add later)

| Gap | Description | Est. Hours |
|-----|-------------|-----------|
| 4c | Timeline visualization (HTML) | 4-6 |
| 4d | Web viewer (local HTTP server) | 2-3 |
| 5c | Static wiki site (MkDocs) | 4-6 |
| 5d | Game engine export | 4-8 |
| 8 | Collaboration (shared Git) | 2-4 |
| 9f | Diversity metrics (automated scoring) | 3-4 |
| 3d | Semantic search (embeddings) | 8-12 |

**Total Nice-to-Have: ~27-43 hours**

---

## Key Architectural Decision

The single most impactful architectural decision identified by this research:

**JSON files as source of truth + SQLite as runtime engine.**

This dual-layer approach solves Gaps #2, #3, and partially #5 simultaneously:
- JSON files remain human-readable, Git-friendly, and portable
- SQLite provides fast queries, full-text search, and indexing
- A sync layer keeps them in sync
- This is exactly how Urdr approaches the problem ("your world bible can behave like a backend")

This should be designed into the system from the start, even if the SQLite layer is not built until 100+ entities exist.

---

## Sources

- [World Anvil](https://www.worldanvil.com/) -- Worldbuilding tools and RPG Campaign Manager
- [LegendKeeper](https://www.legendkeeper.com/) -- Collaborative worldbuilding tool
- [Arcweave](https://blog.arcweave.com/top-10-tools-for-worldbuilding) -- Top 10 tools for worldbuilding
- [Kanka](https://kanka.io/) -- Worldbuilding tool and RPG campaign manager
- [Urdr: World Bible as Data](https://urdr.io/blog/world-bible-as-data-json-first) -- JSON-first lore structured backend
- [Urdr: World Anvil vs Campfire vs Urdr](https://urdr.io/blog/world-anvil-vs-campfire-vs-urdr) -- Tool comparison
- [Gamedeveloper.com: Building a Story Bible](https://www.gamedeveloper.com/design/building-a-basic-story-bible-for-your-game) -- Story bible practices
- [Gamedeveloper.com: Narrative Design at King](https://www.gamedeveloper.com/design/crash-meetings-keep-a-lore-bible-and-other-narrative-design-tips-learned-at-king) -- Lore bible management
- [Arctic7: Series Bible for Multimedia](https://www.arctic7.com/post/create-series-bible-guide) -- Cross-platform consistency
- [pl-rants.net: When JSON Sucks](https://pl-rants.net/posts/when-not-json/) -- JSON to SQLite migration case study
- [Tailscale: Database Migration](https://tailscale.com/blog/an-unlikely-database-migration) -- JSON write latency
- [SQLite FTS5 Documentation](https://sqlite.org/fts5.html) -- Full-text search extension
- [PNAS: Echoes in AI](https://www.pnas.org/doi/10.1073/pnas.2504966122) -- LLM output diversity study
- [G2: Guided Generation](https://arxiv.org/html/2511.00432) -- Training-free diversity strategy
- [CreativeDC: Divergent-Convergent Prompting](https://www.emergentmind.com/papers/2512.23601) -- Psychological creativity models for LLMs
- [Random Concept Injection](https://arxiv.org/html/2601.18053) -- Addressing LLM diversity
- [Mermaid.js](https://mermaid.js.org/) -- Text-based diagram generation
- [Session Continuity Protocol](https://github.com/chris-patenaude/session-continuity-protocal) -- Multi-session AI amnesia prevention
- [OpenAI Agents SDK: Session Memory](https://cookbook.openai.com/examples/agents_sdk/session_memory) -- Context engineering
- [Claude Code Hooks Guide](https://code.claude.com/docs/en/hooks-guide) -- Hook-based automation
- [staticjinja](https://github.com/staticjinja/staticjinja) -- Lightweight Jinja2 static site generator
- [Papery](https://github.com/withletters/papery) -- JSON + Jinja2 static site generator
- [Gridly: Version Control in Game Development](https://www.gridly.com/blog/version-control-in-game-development/) -- Branching for games
- [pytest Documentation](https://pytest.org/) -- Python testing framework
