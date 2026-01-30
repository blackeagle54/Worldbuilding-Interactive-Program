# Worldbuilding Session Rules

## Hooks Handle Context Automatically
- When the user is actively worldbuilding (working on a progression step), the hook scripts in hooks/ handle context injection automatically via .claude/settings.json
- session_start.py loads project state at session begin
- inject_step_context.py injects three-layer guidance and canon context on every user prompt
- validate_writes.py runs three-layer validation after any write to user-world/
- check_completion.py verifies step requirements before Claude stops
- save_checkpoint.py snapshots state before context compaction
- end_session.py generates session summary and commits to git
- Do not manually duplicate what hooks already provide

## Option Generation (Most Important Feature)
- Always provide 2-4 complete, fully fleshed out, standalone options for every creative decision
- Each option must be a real choice ready to adopt as-is, not a vague suggestion
- Each option must account for ALL existing canon (entities, decisions, relationships)
- Draw from different mythological and authorial traditions for each option to ensure variety
- After the user chooses, record the decision with all options presented, chosen option, rejected options, and rationale via the bookkeeping system

## Fair Representation
- Use fair_representation.py to rotate which reference databases are featured
- No single mythology or author should dominate suggestions across sessions
- Each step features 4 mythologies and 3 authors in detail; the rest get brief mentions
- Option generation should draw inspiration from different source combinations per option

## Consistency and Safety
- Run consistency checks (consistency_checker.py) before saving any entity
- Three layers: schema validation, rule-based cross-references, LLM semantic check
- Semantic checks use Claude Code sub-agents, never external APIs
- Create backups before any destructive or bulk operation
- If validation fails, show a human-friendly error explaining the issue and offering solutions

## Communication
- Use human-friendly language in all user-facing output
- No Python tracebacks, JSON syntax errors, or technical jargon in messages
- Error messages should explain what happened, why it matters, and what the user can do
- Frame everything in terms of the user's world, not the underlying system
