"""
app/services/context_builder.py -- Context gathering for Claude conversations.

Pulls together three-layer guidance, knowledge graph neighbors, recent
decisions, and entity summaries into a context package that fits within
a token budget.  Used by ClaudeClient to build each request.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Approximate token budget for context (leaving room for user message + response)
MAX_CONTEXT_CHARS = 12_000  # ~3000 tokens


def build_context(
    engine_manager: Any,
    step_number: int,
) -> dict:
    """Gather all context relevant to the current step.

    Parameters
    ----------
    engine_manager : EngineManager
        The engine manager singleton.
    step_number : int
        Current worldbuilding step (1-52).

    Returns
    -------
    dict
        Context package with keys:
        - system_prompt: str (full system prompt)
        - step_guidance: str (condensed guidance text)
        - featured_sources: dict (mythologies/authors)
        - entities_summary: str (brief summary of existing entities)
        - graph_summary: str (knowledge graph stats)
        - recent_decisions: str (recent bookkeeping entries)
        - step_info: dict (step number, title, phase)
    """
    from app.services.prompt_builder import build_system_prompt

    context: dict[str, Any] = {
        "step_info": {"number": step_number},
        "step_guidance": "",
        "featured_sources": {},
        "entities_summary": "",
        "graph_summary": "",
        "recent_decisions": "",
        "system_prompt": "",
    }

    # --- Step guidance from ChunkPuller ---
    step_title = ""
    phase_name = ""
    condensed = ""
    try:
        guidance = engine_manager.with_lock(
            "chunk_puller", lambda c: c.pull_condensed(step_number)
        )
        if isinstance(guidance, dict):
            condensed = guidance.get("condensed_text", "")
            step_title = guidance.get("title", f"Step {step_number}")
            phase_name = guidance.get("phase_name", "")
        elif isinstance(guidance, str):
            condensed = guidance
    except Exception:
        logger.debug("ChunkPuller unavailable for step %d", step_number, exc_info=True)

    context["step_guidance"] = condensed
    context["step_info"]["title"] = step_title
    context["step_info"]["phase_name"] = phase_name

    # --- Featured sources from FairRepresentation ---
    try:
        featured = engine_manager.with_lock(
            "fair_representation", lambda f: f.select_featured(step_number)
        )
        context["featured_sources"] = featured or {}
    except Exception:
        logger.debug("FairRepresentation unavailable", exc_info=True)

    # --- Entity summary ---
    entity_count = 0
    try:
        entities = engine_manager.with_lock("data_manager", lambda d: d.list_entities())
        entity_count = len(entities)

        if entities:
            lines = []
            # Group by type
            by_type: dict[str, list[str]] = {}
            for e in entities:
                etype = e.get("entity_type", "unknown")
                name = e.get("name", e.get("id", "?"))
                by_type.setdefault(etype, []).append(name)

            for etype, names in sorted(by_type.items()):
                display = etype.replace("_", " ").title()
                name_list = ", ".join(names[:5])
                if len(names) > 5:
                    name_list += f" (+{len(names) - 5} more)"
                lines.append(f"  {display}: {name_list}")

            summary = f"Existing entities ({entity_count}):\n" + "\n".join(lines)
            # Truncate if too long
            if len(summary) > MAX_CONTEXT_CHARS // 3:
                summary = summary[: MAX_CONTEXT_CHARS // 3] + "\n  ..."
            context["entities_summary"] = summary
    except Exception:
        logger.debug("DataManager unavailable", exc_info=True)

    # --- Knowledge graph summary ---
    try:
        stats = engine_manager.with_lock("world_graph", lambda g: g.get_stats())
        if stats:
            context["graph_summary"] = (
                f"Knowledge graph: {stats.get('node_count', 0)} nodes, "
                f"{stats.get('edge_count', 0)} edges, "
                f"{stats.get('orphan_count', 0)} orphans"
            )
    except Exception:
        logger.debug("WorldGraph unavailable", exc_info=True)

    # --- Recent decisions from Bookkeeper ---
    try:
        session_data = engine_manager.with_lock(
            "bookkeeper", lambda b: b.get_current_session()
        )
        if session_data and isinstance(session_data, dict):
            events = session_data.get("events", [])
            recent = events[-5:] if events else []
            if recent:
                lines = ["Recent decisions:"]
                for evt in recent:
                    desc = evt.get("description", evt.get("type", "event"))
                    lines.append(f"  - {desc}")
                context["recent_decisions"] = "\n".join(lines)
    except Exception:
        logger.debug("Bookkeeper unavailable", exc_info=True)

    # --- Build system prompt ---
    context["system_prompt"] = build_system_prompt(
        step_number=step_number,
        step_title=step_title or f"Step {step_number}",
        phase_name=phase_name or "foundation",
        condensed_guidance=condensed,
        featured_sources=context["featured_sources"],
        entity_count=entity_count,
        entities_summary=context["entities_summary"],
        graph_summary=context["graph_summary"],
        recent_decisions=context["recent_decisions"],
    )

    # --- Token budget tracking ---
    # Sum up all context sections and warn if exceeding budget
    total_chars = sum(
        len(str(v)) for k, v in context.items()
        if k != "step_info" and isinstance(v, str)
    )
    context["_context_chars"] = total_chars
    context["_budget_chars"] = MAX_CONTEXT_CHARS

    if total_chars > MAX_CONTEXT_CHARS:
        overage_pct = int((total_chars - MAX_CONTEXT_CHARS) / MAX_CONTEXT_CHARS * 100)
        logger.warning(
            "Context budget exceeded: %d / %d chars (%d%% over). "
            "Some context may be truncated or ignored by the model.",
            total_chars, MAX_CONTEXT_CHARS, overage_pct,
        )
        context["_budget_warning"] = (
            f"Context is {overage_pct}% over budget "
            f"({total_chars}/{MAX_CONTEXT_CHARS} chars)"
        )

    return context
