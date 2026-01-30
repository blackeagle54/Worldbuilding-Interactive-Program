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
