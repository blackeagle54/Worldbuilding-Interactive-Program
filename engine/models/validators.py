"""
engine/models/validators.py -- Custom worldbuilding validators.

Provides validation functions that go beyond JSON Schema structural checks.
These are the "Layer 2" semantic validators that understand worldbuilding
rules:

    - Cross-reference validation (do referenced entities actually exist?)
    - Name uniqueness checking
    - Canon claim extraction and validation
    - Required-field gating based on entity status (draft vs canon)

These validators are designed to be called *after* Pydantic structural
validation succeeds.  They operate on the validated entity data and the
current world state.

Usage::

    from engine.models.validators import validate_cross_references

    issues = validate_cross_references(entity_data, schema, entity_index)
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Cross-reference validation
# ------------------------------------------------------------------

def validate_cross_references(
    entity_data: dict[str, Any],
    schema: dict,
    entity_index: dict[str, Any],
) -> list[str]:
    """Check that all cross-referenced entity IDs actually exist.

    Scans the schema for fields marked with ``x-cross-reference`` and
    verifies that the corresponding values in ``entity_data`` appear in
    the ``entity_index``.

    Parameters
    ----------
    entity_data : dict
        The entity data (after structural validation).
    schema : dict
        The raw JSON Schema with ``x-cross-reference`` annotations.
    entity_index : dict
        The ``entity_index`` from state.json (entity_id -> metadata).

    Returns
    -------
    list[str]
        Human-readable warning messages for each broken reference.
    """
    issues: list[str] = []
    properties = schema.get("properties", {})
    entity_name = entity_data.get("name", entity_data.get("id", "this entity"))

    for field_name, field_def in properties.items():
        xref = field_def.get("x-cross-reference")
        if not xref:
            # Check inside array items
            items = field_def.get("items", {})
            if isinstance(items, dict):
                xref_in_items = items.get("x-cross-reference")
                if xref_in_items:
                    _check_array_refs(
                        entity_data, field_name, items, entity_index,
                        entity_name, issues,
                    )
                # Check nested object properties inside array items
                item_props = items.get("properties", {})
                for sub_name, sub_def in item_props.items():
                    sub_xref = sub_def.get("x-cross-reference")
                    if sub_xref:
                        _check_nested_array_refs(
                            entity_data, field_name, sub_name,
                            sub_xref, entity_index, entity_name, issues,
                        )
            continue

        value = entity_data.get(field_name)
        if not value:
            continue

        if isinstance(value, str):
            if value and value not in entity_index:
                issues.append(
                    f"'{entity_name}' references '{value}' in field "
                    f"'{field_name}' (expected a {xref}), but no entity "
                    f"with that ID exists yet."
                )
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item and item not in entity_index:
                    issues.append(
                        f"'{entity_name}' references '{item}' in field "
                        f"'{field_name}' (expected a {xref}), but no entity "
                        f"with that ID exists yet."
                    )

    return issues


def _check_array_refs(
    entity_data: dict,
    field_name: str,
    items_def: dict,
    entity_index: dict,
    entity_name: str,
    issues: list[str],
) -> None:
    """Check cross-refs in simple array-of-string fields."""
    xref = items_def.get("x-cross-reference", "")
    value = entity_data.get(field_name)
    if not isinstance(value, list):
        return
    for item in value:
        if isinstance(item, str) and item and item not in entity_index:
            issues.append(
                f"'{entity_name}' references '{item}' in field "
                f"'{field_name}' (expected a {xref}), but no entity "
                f"with that ID exists yet."
            )


def _check_nested_array_refs(
    entity_data: dict,
    array_field: str,
    sub_field: str,
    xref: str,
    entity_index: dict,
    entity_name: str,
    issues: list[str],
) -> None:
    """Check cross-refs inside array-of-object fields."""
    array_value = entity_data.get(array_field)
    if not isinstance(array_value, list):
        return
    for i, item in enumerate(array_value):
        if not isinstance(item, dict):
            continue
        ref_value = item.get(sub_field)
        if isinstance(ref_value, str) and ref_value and ref_value not in entity_index:
            issues.append(
                f"'{entity_name}' references '{ref_value}' in "
                f"'{array_field}[{i}].{sub_field}' (expected a {xref}), "
                f"but no entity with that ID exists yet."
            )


# ------------------------------------------------------------------
# Name uniqueness
# ------------------------------------------------------------------

def validate_name_uniqueness(
    entity_data: dict[str, Any],
    entity_index: dict[str, Any],
) -> list[str]:
    """Check that the entity name is unique within its type.

    Parameters
    ----------
    entity_data : dict
        The entity data being validated.
    entity_index : dict
        The entity_index from state.json.

    Returns
    -------
    list[str]
        Warning messages if a duplicate name is found.
    """
    issues: list[str] = []
    name = entity_data.get("name", "").strip().lower()
    if not name:
        return issues

    meta = entity_data.get("_meta", {})
    entity_id = meta.get("id") or entity_data.get("id", "")
    entity_type = meta.get("entity_type", "")

    for other_id, other_meta in entity_index.items():
        if other_id == entity_id:
            continue  # Skip self
        if entity_type and other_meta.get("entity_type") != entity_type:
            continue  # Only check within same type
        other_name = other_meta.get("name", "").strip().lower()
        if other_name == name:
            issues.append(
                f"The name '{entity_data.get('name')}' is already used by "
                f"entity '{other_id}' (type: {entity_type}). Consider "
                f"using a different name to avoid confusion."
            )
            break  # One warning is enough

    return issues


# ------------------------------------------------------------------
# Canon claim extraction
# ------------------------------------------------------------------

def extract_canon_claims(entity_data: dict[str, Any]) -> list[dict[str, str]]:
    """Extract canon claims from entity data.

    Canon claims are statements that establish facts about the world.
    They are found in fields like ``overview``, ``general_description``,
    ``history``, ``history_and_myths``, and ``famous_for``.

    Each claim is a dict with ``field``, ``text``, and ``claim_type``.

    Parameters
    ----------
    entity_data : dict
        The entity data.

    Returns
    -------
    list[dict[str, str]]
        Extracted canon claims.
    """
    claims: list[dict[str, str]] = []
    entity_name = entity_data.get("name", "Unknown")

    # Prose fields that contain world-building assertions
    prose_fields = [
        "overview", "general_description", "description",
        "history", "history_and_myths", "lore", "local_lore",
        "famous_for", "origin", "reputation",
    ]

    for field in prose_fields:
        value = entity_data.get(field)
        if not isinstance(value, str) or not value.strip():
            continue

        # Each non-empty prose field is a potential canon claim
        claims.append({
            "field": field,
            "text": value.strip(),
            "claim_type": "prose",
            "entity_name": entity_name,
        })

    # Relationship claims
    relationships = entity_data.get("relationships")
    if isinstance(relationships, list):
        for rel in relationships:
            if not isinstance(rel, dict):
                continue
            target = rel.get("target_id", "")
            rel_type = rel.get("relationship_type", "")
            desc = rel.get("description", "")
            if target and rel_type:
                claims.append({
                    "field": "relationships",
                    "text": f"{entity_name} has a {rel_type} relationship with {target}. {desc}".strip(),
                    "claim_type": "relationship",
                    "entity_name": entity_name,
                })

    return claims


# ------------------------------------------------------------------
# Draft vs Canon gating
# ------------------------------------------------------------------

def validate_canon_readiness(
    entity_data: dict[str, Any],
    schema: dict,
) -> list[str]:
    """Check whether an entity is ready to be promoted to canon status.

    Canon entities must have all required fields filled with meaningful
    content (not just empty strings or placeholder values).

    Parameters
    ----------
    entity_data : dict
        The entity data.
    schema : dict
        The raw JSON Schema with required field definitions.

    Returns
    -------
    list[str]
        Issues that must be resolved before promotion to canon.
    """
    issues: list[str] = []
    required = set(schema.get("required", []))
    entity_name = entity_data.get("name", "this entity")

    for field_name in required:
        if field_name in ("id",):
            continue  # Auto-generated, always present

        value = entity_data.get(field_name)

        if value is None:
            issues.append(
                f"'{entity_name}' is missing the required field "
                f"'{field_name}' for canon status."
            )
        elif isinstance(value, str) and not value.strip():
            issues.append(
                f"'{entity_name}' has an empty value for the required "
                f"field '{field_name}'. Fill this in before promoting to canon."
            )
        elif isinstance(value, list) and len(value) == 0:
            issues.append(
                f"'{entity_name}' has no entries in the required field "
                f"'{field_name}'. Add at least one entry before promoting to canon."
            )

    return issues
