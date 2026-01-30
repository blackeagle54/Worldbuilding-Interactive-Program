"""
Shared pytest fixtures for the Worldbuilding Interactive Program test suite.

Provides:
    - project_root: path to the real project root
    - temp_world: a temporary directory pre-populated with sample entity files
    - sample_god_data: valid god entity data matching the god-profile template
    - sample_settlement_data: valid settlement entity data
    - sample_template: a loaded god-profile template schema
"""

import json
import os
import sys
import shutil
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Ensure engine/ is importable regardless of where pytest is invoked
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENGINE_DIR = PROJECT_ROOT / "engine"

# Add project root to sys.path so that `from engine.xxx import ...` works.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def project_root():
    """Return the absolute path to the real project root directory."""
    return str(PROJECT_ROOT)


@pytest.fixture
def sample_god_data():
    """Return a valid god entity data dict matching the god-profile template.

    Includes all required fields:
        name, domain_primary, alignment, symbol, relationships, pantheon_id
    """
    return {
        "name": "Thorin Stormkeeper",
        "titles": ["Lord of Storms", "The Thunderer"],
        "domain_primary": "storms",
        "domains_secondary": ["lightning", "rain"],
        "alignment": "complex",
        "alignment_nuance": "benevolent but wrathful",
        "symbol": "a lightning bolt striking an anvil",
        "god_type": "god",
        "power_level": "greater",
        "origin": "born from the collision of the first storm and the first mountain",
        "personality": "Thorin is fierce and unyielding, but deeply protective of mortals.",
        "appearance": "A towering figure wreathed in storm clouds, with eyes of crackling lightning.",
        "mortal_interaction": "active",
        "reputation_among_mortals": "feared and revered in equal measure",
        "residence": "The Storm Citadel, high above the tallest peak",
        "patronage": "sailors, blacksmiths, and soldiers",
        "relationships": [
            {
                "target_id": "mira-sunweaver-c3d4",
                "relationship_type": "spouse",
                "description": "Married to Mira Sunweaver, goddess of dawn"
            }
        ],
        "pantheon_id": "celestial-court",
    }


@pytest.fixture
def sample_settlement_data():
    """Return a valid settlement entity data dict matching the settlement-profile template.

    Includes all required fields:
        name, type, sovereign_power_id, climate, terrain, population,
        species_breakdown, leadership
    """
    return {
        "name": "Havenport",
        "type": "city",
        "sovereign_power_id": "kingdom-of-aldara",
        "location": "southern coast of the Aldaran peninsula",
        "climate": "temperate maritime",
        "terrain": "coastal lowlands",
        "water_supply": {
            "type": "river",
            "location": "the River Aldyn runs through the city center",
            "reliability": "year-round"
        },
        "population": 45000,
        "species_breakdown": [
            {"species_id": "humans", "percentage": 70},
            {"species_id": "elves", "percentage": 20},
            {"species_id": "dwarves", "percentage": 10}
        ],
        "leadership": {
            "leader_name": "Castellan Elara Voss",
            "leader_title": "High Castellan",
            "power_level": "moderate",
            "limitations": "Answers to the Crown Council",
            "selection_method": "appointed by sovereign"
        },
        "reputation": "its bustling harbor and famous fish market",
        "fortifications": "a double ring of stone walls with 12 watchtowers",
        "slogan": "Safe Harbor, Open Arms",
    }


@pytest.fixture
def sample_template(project_root):
    """Load and return the god-profile template schema from the project."""
    template_path = os.path.join(
        project_root, "templates", "phase02-cosmology", "06-god-profile.json"
    )
    with open(template_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture
def temp_world(tmp_path, sample_god_data, sample_settlement_data):
    """Create a temporary directory tree that mimics the project structure.

    Includes:
        - user-world/state.json  (with entity_index pre-populated)
        - user-world/entities/gods/sample-god.json
        - user-world/entities/settlements/sample-settlement.json
        - templates/ copied from the real project
        - engine/template_registry.json copied from the real project
        - bookkeeping/ directory structure
        - generation/ directory structure

    Returns the path to the temporary project root.
    """
    root = tmp_path / "test-world"
    root.mkdir()

    # --- Copy templates from the real project ---
    src_templates = PROJECT_ROOT / "templates"
    dst_templates = root / "templates"
    if src_templates.exists():
        shutil.copytree(str(src_templates), str(dst_templates))
    else:
        dst_templates.mkdir(parents=True)

    # --- Copy engine index files ---
    engine_dir = root / "engine"
    engine_dir.mkdir(parents=True)
    for fname in ("template_registry.json", "reference_index.json", "source_index.json"):
        src = PROJECT_ROOT / "engine" / fname
        if src.exists():
            shutil.copy2(str(src), str(engine_dir / fname))

    # --- Create entity directories ---
    gods_dir = root / "user-world" / "entities" / "gods"
    settlements_dir = root / "user-world" / "entities" / "settlements"
    gods_dir.mkdir(parents=True)
    settlements_dir.mkdir(parents=True)

    # --- Write sample god entity ---
    god_entity = dict(sample_god_data)
    god_entity["id"] = "thorin-stormkeeper-a1b2"
    god_entity["_meta"] = {
        "id": "thorin-stormkeeper-a1b2",
        "template_id": "god-profile",
        "entity_type": "gods",
        "status": "draft",
        "created_at": "2025-01-01T00:00:00+00:00",
        "updated_at": "2025-01-01T00:00:00+00:00",
        "step_created": 7,
        "file_path": "user-world/entities/gods/thorin-stormkeeper-a1b2.json",
    }
    god_entity["canon_claims"] = [
        {"claim": "Thorin Stormkeeper's primary domain is storms", "references": []},
        {"claim": "Thorin Stormkeeper is aligned with complex forces", "references": []},
        {
            "claim": "Thorin Stormkeeper has spouse relationship with Mira Sunweaver",
            "references": ["mira-sunweaver-c3d4"],
        },
    ]
    god_entity["_prose"] = ""
    god_entity["_prose_custom"] = False

    god_path = gods_dir / "thorin-stormkeeper-a1b2.json"
    with open(str(god_path), "w", encoding="utf-8") as fh:
        json.dump(god_entity, fh, indent=2, ensure_ascii=False)

    # --- Write sample settlement entity ---
    settlement_entity = dict(sample_settlement_data)
    settlement_entity["id"] = "havenport-e5f6"
    settlement_entity["_meta"] = {
        "id": "havenport-e5f6",
        "template_id": "settlement-profile",
        "entity_type": "settlements",
        "status": "draft",
        "created_at": "2025-01-02T00:00:00+00:00",
        "updated_at": "2025-01-02T00:00:00+00:00",
        "step_created": 29,
        "file_path": "user-world/entities/settlements/havenport-e5f6.json",
    }
    settlement_entity["canon_claims"] = [
        {"claim": "Havenport is a city of 45000 inhabitants", "references": []},
        {
            "claim": "Havenport belongs to the Kingdom of Aldara",
            "references": ["kingdom-of-aldara"],
        },
    ]
    settlement_entity["_prose"] = ""
    settlement_entity["_prose_custom"] = False

    settlement_path = settlements_dir / "havenport-e5f6.json"
    with open(str(settlement_path), "w", encoding="utf-8") as fh:
        json.dump(settlement_entity, fh, indent=2, ensure_ascii=False)

    # --- Write state.json ---
    state = {
        "current_step": 7,
        "current_phase": "cosmology",
        "completed_steps": [1, 2, 3, 4, 5, 6],
        "in_progress_steps": [7],
        "entity_index": {
            "thorin-stormkeeper-a1b2": {
                "template_id": "god-profile",
                "entity_type": "gods",
                "name": "Thorin Stormkeeper",
                "status": "draft",
                "file_path": "user-world/entities/gods/thorin-stormkeeper-a1b2.json",
                "created_at": "2025-01-01T00:00:00+00:00",
                "updated_at": "2025-01-01T00:00:00+00:00",
            },
            "havenport-e5f6": {
                "template_id": "settlement-profile",
                "entity_type": "settlements",
                "name": "Havenport",
                "status": "draft",
                "file_path": "user-world/entities/settlements/havenport-e5f6.json",
                "created_at": "2025-01-02T00:00:00+00:00",
                "updated_at": "2025-01-02T00:00:00+00:00",
            },
        },
        "session_log": [],
        "reference_usage_counts": {},
    }
    state_dir = root / "user-world"
    state_path = state_dir / "state.json"
    with open(str(state_path), "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, ensure_ascii=False)

    # --- Create bookkeeping directories ---
    bk_root = root / "bookkeeping"
    for subdir in ("events", "indexes", "revisions", "revisions/snapshots", "sessions", "snapshots"):
        (bk_root / subdir).mkdir(parents=True, exist_ok=True)

    # --- Create generation directory ---
    gen_dir = root / "generation"
    gen_dir.mkdir(parents=True)
    # Write an empty concept bank
    concept_bank = {
        "concepts": {
            "emotions": ["wrath", "serenity", "grief", "ecstasy"],
            "elements": ["fire", "ice", "shadow", "crystal"],
            "themes": ["betrayal", "redemption", "discovery", "sacrifice"],
        }
    }
    with open(str(gen_dir / "concept-bank.json"), "w", encoding="utf-8") as fh:
        json.dump(concept_bank, fh, indent=2)

    # --- Create runtime directory ---
    (root / "runtime").mkdir(parents=True, exist_ok=True)

    return str(root)
