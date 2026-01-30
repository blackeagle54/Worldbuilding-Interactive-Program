# Decision Log

## 2026-01-30: Project Creation
- Created GitHub repo: `blackeagle54/Worldbuilding-Interactive-Program`
- Cloned to `C:\Worldbuilding-Interactive-Program`

## 2026-01-30: Source Material
- Using "The Complete Art of World Building" by Randy Ellefson as the foundation
- Book has 3 volumes, 30 chapters total
- Full text extracted to `source-text.txt` (8,677 paragraphs)

## 2026-01-30: Analysis Approach
- Each volume analyzed by an Opus-level agent in parallel
- Each chapter broken into: core concept, topics, key discussions, concepts, templates, dependencies, milestones
- Goal: chunk every element into stepping stones that must be progressed in order

## 2026-01-30: Agent Policy
- Use Opus-level agents for all research and complex tasks (user preference)

## 2026-01-30: Memory System
- Set up CLAUDE.md with project rules and file references
- Created docs/decisions.md (this file) and docs/progress.md for persistent context
- Set up .claude/rules/ directory for scoped instructions
- Researched MCP memory servers, hook-based systems, and file-based strategies

## 2026-01-30: Core Design Decision — Intelligent Reference Querying
- When guiding the user through worldbuilding steps, the system must query ALL 16 reference databases (10 mythologies + 6 authors) to find the most relevant information for the current creation task
- **Fair representation**: No single mythology or author should dominate suggestions. The system should pull diverse examples from across all databases, giving the user a broad palette of inspiration
- Examples: When creating gods, show how Greek, Norse, Hindu, Mesopotamian, etc. each handled pantheons differently, alongside how Tolkien, Jordan, Martin, etc. approached divine beings in fiction
- The goal is informed, guided creativity — not just a blank template, but options and patterns drawn from real mythological and literary traditions
- This querying will be powered by hooks (UserPromptSubmit) + a knowledge graph (MCP) that auto-inject relevant references based on the current progression step and what the user is discussing
- Implementation deferred until Phase 2 when templates and data structures are defined

## 2026-01-30: Core Design Decision — Three-Layer Step Guidance
Each progression step delivers a guided experience with three layers:
1. **Book Quotes & Teaching**: Direct quotes from Ellefson's source text explaining the concept, why it matters, and what to consider. The book is the authority — quote it, then explain how it applies to the user's world and what needs to be addressed.
2. **Synthesized Reference Material**: Pull relevant examples from ALL mythology and author databases, synthesized into a coherent picture. Not just "here's what Greek mythology did" — but a cross-referenced synthesis showing patterns, contrasts, and creative options drawn from all sources with fair representation.
3. **Actionable Output**: What the user needs to decide, create, or fill out for their specific world. Templates, prompts, and guided questions.
- This three-layer approach is the core user experience of the entire program.

## 2026-01-30: Core Design Decision — Option Generation (Most Important)
- At each progression step, after synthesizing all reference material AND reviewing the user's existing world state (canon, drafts, prior decisions), Claude generates **2-4 unique, fully fleshed out, standalone options** for the user to choose from.
- Each option is NOT a vague suggestion — it is a **complete, thought-through choice** that's ready to be adopted into the world as-is.
- Each option should be inspired by different combinations of mythologies and authors, ensuring variety and creative range.
- Each option must account for everything already established in the user's world (prior decisions, existing entities, established lore).
- The user can: pick one as-is, combine elements from multiple options, request new options, or go fully custom.
- The chosen option (or hybrid) becomes canon in the user's world and informs all future option generation.
- **This is the single most important feature of the entire program.** Everything else (templates, hooks, knowledge graph, databases) exists to make this option generation as informed and coherent as possible.

## 2026-01-30: Canon Consistency — Use Claude Code Sub-Agents, Not External API
- The three-layer consistency system (structural, rule-based, semantic) will NOT use external API calls for the LLM semantic check layer
- Instead, Claude Code sub-agents handle semantic contradiction detection — no API keys, no external infrastructure
- Layers 1 and 2 (structural + rule-based) remain as Python scripts in hooks (free, instant)
- Layer 3 (semantic) is a sub-agent call triggered when layers 1 and 2 pass — uses existing Claude Code tokens

## 2026-01-30: Phase 2 Plan Revised After Research
- Original phase2-plan.md was written before research was completed
- Revised to phase2-plan-revised.md integrating all 6 research documents
- Key changes: MCP Knowledge Graph replaced with NetworkX, bookkeeping system added, SQLite dual-layer added, option generator formalized with divergent-convergent pipeline, backup/test/error recovery systems added
- Sprint structure changed from 2 sprints (6 tasks) to 3 sprints (15 tasks)
- Only pip dependencies: jsonschema and networkx — no external APIs or services

## 2026-01-30: Phase 2 Complete — All 4 Sprints Done
- Sprint 1: 85 templates, user-world structure, reference indexes
- Sprint 2: Engine layer (7 modules)
- Sprint 3: Intelligence layer (SQLite sync, consistency checker, 6 hooks, prose generation)
- Sprint 4: Safety layer (backup manager, 182 tests, error recovery, CLAUDE.md rewrite)

## 2026-01-30: Phase 3 Research — Desktop Framework Decision Pending
- User requirements: standalone desktop window app (NOT web/browser), no API keys, Claude Code CLI as backend
- 4 research documents produced: phase3-research.md, claude-code-integration-research.md, project-audit.md, desktop-framework-research.md
- Claude Agent SDK (pip install claude-agent-sdk) confirmed as backend integration method — wraps Claude Code CLI, supports streaming, no API keys
- Desktop framework research evaluated 8 frameworks against 12 criteria
- **Top recommendation: PySide6 (Qt)** — scored 97/weighted, native knowledge graph via QGraphicsView, async via qasync, dark theme via qdarktheme, PyInstaller for .exe distribution
- Runner-up: Dear PyGui (scored 79) — built-in node editor, GPU-accelerated, but smaller ecosystem
- Third: NiceGUI native (scored 77) — web-in-window approach, fragile packaging on Windows
- **AWAITING USER DECISION on framework choice before implementation begins**
