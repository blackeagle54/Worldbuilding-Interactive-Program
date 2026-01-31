"""
app/services/tools.py -- Tool definitions for Claude integration.

Defines the tools Claude can call during conversation, each wrapping
engine functionality.  Tools are registered as Anthropic-format tool
definitions and have corresponding executor functions.

Tools:
    get_step_guidance    - Pull guidance for the current or any step
    get_canon_context    - Get existing entities and canon claims
    generate_options     - Trigger the option generation pipeline
    validate_entity      - Run consistency checks on an entity
    query_knowledge_graph - Query the entity relationship graph
    search_entities      - Full-text search across entities
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Tool definitions (Anthropic API format)
# --------------------------------------------------------------------------

TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "get_step_guidance",
        "description": (
            "Get worldbuilding guidance for a specific step. Returns the "
            "step title, phase, condensed guidance text, book quotes, "
            "guided questions, and template information."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "step_number": {
                    "type": "integer",
                    "description": "Step number (1-52). Defaults to current step.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_canon_context",
        "description": (
            "Get a summary of existing canon entities and their claims. "
            "Useful for checking what has already been established before "
            "suggesting new content."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_type": {
                    "type": "string",
                    "description": "Filter by entity type (e.g. 'god', 'species'). Optional.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "generate_options",
        "description": (
            "Generate 2-4 creative options for the current worldbuilding "
            "step using the divergent-convergent pipeline. Returns structured "
            "option data with inspirations, canon connections, and template "
            "data for each option."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "step_number": {
                    "type": "integer",
                    "description": "Step number (1-52). Defaults to current step.",
                },
                "num_options": {
                    "type": "integer",
                    "description": "Number of options to generate (2-4). Default 3.",
                },
                "user_preferences": {
                    "type": "string",
                    "description": "Optional user preferences or constraints to consider.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "validate_entity",
        "description": (
            "Validate an entity against its schema and consistency rules. "
            "Returns validation results including any errors or warnings."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "The entity ID to validate.",
                },
            },
            "required": ["entity_id"],
        },
    },
    {
        "name": "query_knowledge_graph",
        "description": (
            "Query the entity relationship graph. Can get neighbors, find "
            "paths between entities, list orphans, or get graph statistics."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query_type": {
                    "type": "string",
                    "enum": ["neighbors", "path", "orphans", "stats", "related"],
                    "description": "Type of graph query to perform.",
                },
                "entity_id": {
                    "type": "string",
                    "description": "Entity ID (required for neighbors, path, related).",
                },
                "target_id": {
                    "type": "string",
                    "description": "Target entity ID (required for path query).",
                },
                "depth": {
                    "type": "integer",
                    "description": "Search depth for neighbors (default 1).",
                },
            },
            "required": ["query_type"],
        },
    },
    {
        "name": "search_entities",
        "description": (
            "Search all entities by keyword. Returns matching entity "
            "summaries including name, type, status, and ID."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (keyword or phrase).",
                },
            },
            "required": ["query"],
        },
    },
]


# --------------------------------------------------------------------------
# Tool executors
# --------------------------------------------------------------------------

def execute_tool(
    tool_name: str,
    tool_input: dict,
    engine_manager: Any,
    current_step: int = 1,
) -> str:
    """Execute a tool call and return the result as a string.

    Parameters
    ----------
    tool_name : str
        The tool to execute.
    tool_input : dict
        The tool input parameters.
    engine_manager : EngineManager
        The engine manager singleton.
    current_step : int
        The current worldbuilding step (used as default for step_number).

    Returns
    -------
    str
        JSON-encoded result string.
    """
    try:
        executor = _EXECUTORS.get(tool_name)
        if executor is None:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
        result = executor(tool_input, engine_manager, current_step)
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        logger.exception("Tool execution failed: %s", tool_name)
        return json.dumps({"error": str(e)})


def _exec_get_step_guidance(
    params: dict, engine: Any, current_step: int
) -> dict:
    step = params.get("step_number", current_step)

    guidance = engine.with_lock("chunk_puller", lambda c: c.pull_guidance(step))
    if not isinstance(guidance, dict):
        return {"step": step, "guidance": str(guidance)}

    # Also get dependency status
    deps = engine.with_lock(
        "chunk_puller", lambda c: c.get_step_dependencies(step)
    )

    return {
        "step": step,
        "guidance": guidance,
        "dependencies": deps,
    }


def _exec_get_canon_context(
    params: dict, engine: Any, current_step: int
) -> dict:
    entity_type = params.get("entity_type")

    entities = engine.with_lock(
        "data_manager", lambda d: d.list_entities(entity_type=entity_type)
    )

    result: dict[str, Any] = {
        "entity_count": len(entities),
        "entities": [],
    }

    for ent in entities[:50]:  # Cap at 50 for token budget
        summary = {
            "id": ent.get("id", ""),
            "name": ent.get("name", ""),
            "entity_type": ent.get("entity_type", ""),
            "status": ent.get("status", "draft"),
        }
        result["entities"].append(summary)

    if len(entities) > 50:
        result["note"] = f"Showing 50 of {len(entities)} entities. Use search_entities for specific queries."

    return result


def _exec_generate_options(
    params: dict, engine: Any, current_step: int
) -> dict:
    step = params.get("step_number", current_step)
    num = params.get("num_options", 3)
    prefs = params.get("user_preferences", "")

    context = {"user_prefs": prefs} if prefs else {}

    result = engine.with_lock(
        "option_generator",
        lambda o: o.generate_options(step_number=step, num_options=num, context=context),
    )

    return result if isinstance(result, dict) else {"raw": str(result)}


def _exec_validate_entity(
    params: dict, engine: Any, current_step: int
) -> dict:
    entity_id = params["entity_id"]

    result = engine.with_lock(
        "consistency_checker",
        lambda c: c.check_entity(entity_id),
    )

    return result if isinstance(result, dict) else {"raw": str(result)}


def _exec_query_knowledge_graph(
    params: dict, engine: Any, current_step: int
) -> dict:
    query_type = params["query_type"]

    if query_type == "stats":
        return engine.with_lock("world_graph", lambda g: g.get_stats())

    elif query_type == "orphans":
        orphans = engine.with_lock("world_graph", lambda g: g.get_orphans())
        return {"orphans": orphans[:50], "count": len(orphans)}

    elif query_type == "neighbors":
        entity_id = params.get("entity_id", "")
        depth = params.get("depth", 1)
        neighbors = engine.with_lock(
            "world_graph", lambda g: g.get_neighbors(entity_id, depth=depth)
        )
        return {"entity_id": entity_id, "neighbors": neighbors[:50]}

    elif query_type == "path":
        entity_id = params.get("entity_id", "")
        target_id = params.get("target_id", "")
        path = engine.with_lock(
            "world_graph", lambda g: g.find_path(entity_id, target_id)
        )
        return {"from": entity_id, "to": target_id, "path": path}

    elif query_type == "related":
        entity_id = params.get("entity_id", "")
        related = engine.with_lock(
            "world_graph", lambda g: g.get_related_entities(entity_id)
        )
        return {"entity_id": entity_id, "related": related}

    return {"error": f"Unknown query type: {query_type}"}


def _exec_search_entities(
    params: dict, engine: Any, current_step: int
) -> dict:
    query = params.get("query", "")

    results = engine.with_lock(
        "data_manager", lambda d: d.search_entities(query)
    )

    return {
        "query": query,
        "count": len(results),
        "results": results[:20],
    }


_EXECUTORS = {
    "get_step_guidance": _exec_get_step_guidance,
    "get_canon_context": _exec_get_canon_context,
    "generate_options": _exec_generate_options,
    "validate_entity": _exec_validate_entity,
    "query_knowledge_graph": _exec_query_knowledge_graph,
    "search_entities": _exec_search_entities,
}
