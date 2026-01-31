"""
app/services/prompt_builder.py -- Step-specific prompt construction.

Builds system prompts for Claude that include the worldbuilding role,
current step context, constraints, and anti-drift instructions.
Prompt templates are versioned for reproducibility.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

PROMPT_VERSION = "1.0"

_SYSTEM_ROLE = (
    "You are a worldbuilding assistant guiding the user through a structured "
    "52-step process based on Randy Ellefson's 'The Complete Art of World "
    "Building.' You help the user create a rich, consistent, and original "
    "fantasy world by asking thoughtful questions, offering creative options, "
    "and ensuring all decisions remain internally consistent."
)

_CONSTRAINTS = (
    "CONSTRAINTS:\n"
    "- Always respect the user's existing canon decisions. Never contradict "
    "established facts.\n"
    "- When presenting options, always offer 2-4 distinct choices with clear "
    "trade-offs. Never present a single 'right answer.'\n"
    "- Draw inspiration from the featured reference sources but create original "
    "content. Never copy directly.\n"
    "- Keep responses conversational and encouraging. The user may not be a "
    "writer -- explain concepts clearly.\n"
    "- If the user seems stuck, offer a concrete suggestion to move forward.\n"
    "- Always consider how decisions affect other parts of the world "
    "(cross-references, consistency).\n"
    "- Use the available tools to validate entities, check consistency, and "
    "query the knowledge graph rather than guessing."
)

_ANTI_DRIFT = (
    "ANTI-DRIFT RULES:\n"
    "- Stay focused on the current step. Do not jump ahead to future steps "
    "unless the user explicitly asks.\n"
    "- Do not invent entities or facts that the user hasn't approved.\n"
    "- When referencing existing entities, always verify via tools first.\n"
    "- If the conversation drifts off-topic, gently guide back to the "
    "current worldbuilding step.\n"
    "- Do not make assumptions about the user's world -- ask questions.\n"
    "- Keep the scope manageable: one decision at a time."
)

# Phase-specific guidance flavor
_PHASE_FLAVORS: dict[str, str] = {
    "foundation": (
        "You are helping the user lay the groundwork for their world. "
        "Focus on scope, strategy, and naming philosophy. These early "
        "decisions will shape everything that follows."
    ),
    "cosmology": (
        "You are helping the user design the divine and cosmic elements. "
        "Focus on pantheons, myths, and the physical nature of their world. "
        "Encourage internal logic and interconnection between gods."
    ),
    "land": (
        "You are helping the user shape the physical geography. "
        "Focus on how terrain, climate, and natural features affect "
        "civilizations and story possibilities."
    ),
    "life": (
        "You are helping the user populate their world with species and "
        "creatures. Focus on ecological niches, cultural distinctiveness, "
        "and how species relate to each other and the land."
    ),
    "civilization": (
        "You are helping the user build nations, cultures, and settlements. "
        "Focus on how geography, species, and history shape civilizations. "
        "Encourage cultural diversity and realistic social dynamics."
    ),
    "society": (
        "You are helping the user design social institutions. "
        "Focus on religions, organizations, armed forces, and systems "
        "that govern daily life. Consider how these interact and conflict."
    ),
    "supernatural": (
        "You are helping the user design magic and supernatural elements. "
        "Focus on rules, limitations, and costs of magic. A well-constrained "
        "magic system creates better stories than unlimited power."
    ),
    "history": (
        "You are helping the user write the history of their world. "
        "Focus on how past events created the present situation. "
        "Great world histories feel inevitable in hindsight."
    ),
    "language": (
        "You are helping the user develop naming conventions and language "
        "elements. Focus on consistency within cultures and distinctiveness "
        "between them. Names should feel natural and evocative."
    ),
    "travel": (
        "You are helping the user calculate travel times and logistics. "
        "Focus on how distance and terrain affect story pacing, trade, "
        "and political boundaries."
    ),
    "finishing": (
        "You are helping the user add final details and polish. "
        "Focus on places of interest, map creation, and filling gaps. "
        "These details bring the world to life."
    ),
    "integration": (
        "You are helping the user review and cross-reference everything. "
        "Focus on consistency, completeness, and identifying gaps. "
        "This is the quality assurance phase."
    ),
}


def build_system_prompt(
    step_number: int,
    step_title: str,
    phase_name: str,
    condensed_guidance: str = "",
    featured_sources: dict | None = None,
    reference_content: list[dict] | None = None,
    entity_count: int = 0,
    entities_summary: str = "",
    graph_summary: str = "",
    recent_decisions: str = "",
) -> str:
    """Build a complete system prompt for a given step.

    Parameters
    ----------
    step_number : int
        Current step (1-52).
    step_title : str
        Human-readable step title.
    phase_name : str
        Phase key (e.g. "foundation", "cosmology").
    condensed_guidance : str
        Output from ChunkPuller.pull_condensed().
    featured_sources : dict | None
        Featured mythologies and authors for this step.
    reference_content : list[dict] | None
        Actual content from featured reference databases.  Each dict has
        ``database_name``, ``section``, and ``content`` keys.
    entity_count : int
        Number of existing entities in the world.
    entities_summary : str
        Summary of existing entities grouped by type.
    graph_summary : str
        Knowledge graph statistics summary.
    recent_decisions : str
        Recent bookkeeping decisions made in this session.

    Returns
    -------
    str
        Complete system prompt for Claude.
    """
    parts = [
        _SYSTEM_ROLE,
        "",
        f"CURRENT STEP: {step_number}/52 -- {step_title}",
        f"PHASE: {phase_name.replace('_', ' ').title()}",
        f"EXISTING ENTITIES: {entity_count}",
        f"PROMPT VERSION: {PROMPT_VERSION}",
        "",
    ]

    # Phase-specific flavor
    flavor = _PHASE_FLAVORS.get(phase_name, "")
    if flavor:
        parts.append(flavor)
        parts.append("")

    # Condensed guidance from ChunkPuller
    if condensed_guidance:
        parts.append("STEP GUIDANCE (from source material):")
        parts.append(condensed_guidance)
        parts.append("")

    # Existing entities detail
    if entities_summary:
        parts.append("WORLD STATE -- EXISTING ENTITIES:")
        parts.append(entities_summary)
        parts.append("")

    # Knowledge graph stats
    if graph_summary:
        parts.append("WORLD STATE -- KNOWLEDGE GRAPH:")
        parts.append(graph_summary)
        parts.append("")

    # Recent decisions
    if recent_decisions:
        parts.append("SESSION CONTEXT -- RECENT DECISIONS:")
        parts.append(recent_decisions)
        parts.append("")

    # Featured sources
    if featured_sources:
        myths = featured_sources.get("featured_mythologies", [])
        authors = featured_sources.get("featured_authors", [])
        if myths or authors:
            parts.append("FEATURED REFERENCE SOURCES THIS SESSION:")
            if myths:
                parts.append(f"  Mythologies: {', '.join(myths)}")
            if authors:
                parts.append(f"  Authors: {', '.join(authors)}")
            parts.append("")

    # Actual reference database content
    if reference_content:
        parts.append("REFERENCE DATABASE CONTENT:")
        for ref in reference_content:
            db_name = ref.get("database_name", "")
            section = ref.get("section", "")
            content = ref.get("content", "")
            if len(content) > 800:
                content = content[:800] + "..."
            parts.append(f"  [{db_name} -- {section}]")
            parts.append(f"  {content}")
            parts.append("")

    # Instruction for using references
    if reference_content or (featured_sources and (
        featured_sources.get("featured_mythologies") or featured_sources.get("featured_authors")
    )):
        parts.append(
            "When presenting worldbuilding options, draw specific examples and "
            "patterns from the reference content above. Compare how different "
            "mythological traditions handle similar concepts. Reference specific "
            "details (god attributes, creation patterns, narrative techniques) to "
            "enrich your suggestions. Synthesize ideas across traditions to create "
            "unique combinations."
        )
        parts.append("")

    parts.append(_CONSTRAINTS)
    parts.append("")
    parts.append(_ANTI_DRIFT)

    return "\n".join(parts)
