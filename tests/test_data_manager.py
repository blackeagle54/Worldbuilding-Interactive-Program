"""
Tests for engine/data_manager.py -- DataManager entity CRUD and prose generation.

Validates:
    - Entity creation with valid and invalid data
    - Entity update and retrieval
    - Entity listing and search
    - Schema validation
    - Canon claims extraction
    - Prose generation for multiple entity types
    - Custom prose override behavior
"""

import json
import os
import pytest

from engine.data_manager import (
    DataManager,
    _slugify,
    _generate_id,
    _extract_canon_claims,
    _prose_for_god,
    _prose_for_settlement,
    _prose_for_species,
    _prose_for_religion,
    _prose_generic,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class TestSlugify:
    """Tests for the _slugify helper."""

    def test_basic_name(self):
        """Verify a normal name is lowercased and hyphenated."""
        assert _slugify("Thorin Stormkeeper") == "thorin-stormkeeper"

    def test_special_characters(self):
        """Verify special characters are replaced with hyphens."""
        result = _slugify("Mira's Haven")
        assert "mira" in result
        assert "haven" in result
        # Apostrophe becomes a separator
        assert result == "mira-s-haven"

    def test_empty_string(self):
        """Verify empty input produces empty string."""
        assert _slugify("") == ""


class TestGenerateId:
    """Tests for the _generate_id helper."""

    def test_format(self):
        """Verify generated IDs have the expected slug-XXXX format."""
        eid = _generate_id("Thorin Stormkeeper")
        parts = eid.rsplit("-", 1)
        assert len(parts) == 2
        assert parts[0].startswith("thorin-stormkeeper")
        assert len(parts[-1]) == 4

    def test_uniqueness(self):
        """Verify two calls produce different IDs (extremely high probability)."""
        id1 = _generate_id("Test")
        id2 = _generate_id("Test")
        assert id1 != id2


# ---------------------------------------------------------------------------
# DataManager creation
# ---------------------------------------------------------------------------

class TestCreateEntity:
    """Tests for DataManager.create_entity."""

    def test_create_with_valid_data(self, temp_world, sample_god_data):
        """Creating an entity with all required fields should succeed and return an ID."""
        dm = DataManager(temp_world)
        entity_id = dm.create_entity("god-profile", sample_god_data)

        assert entity_id is not None
        assert isinstance(entity_id, str)
        assert len(entity_id) > 0

    def test_created_entity_has_meta(self, temp_world, sample_god_data):
        """A newly created entity should have _meta with expected keys."""
        dm = DataManager(temp_world)
        entity_id = dm.create_entity("god-profile", sample_god_data)
        entity = dm.get_entity(entity_id)

        assert "_meta" in entity
        assert entity["_meta"]["id"] == entity_id
        assert entity["_meta"]["template_id"] == "god-profile"
        assert entity["_meta"]["status"] == "draft"
        assert "created_at" in entity["_meta"]
        assert "updated_at" in entity["_meta"]

    def test_create_with_missing_required_fields(self, temp_world):
        """Creating an entity missing required fields should raise ValueError."""
        dm = DataManager(temp_world)
        incomplete_data = {
            "name": "Incomplete God",
            # Missing: domain_primary, alignment, symbol, relationships, pantheon_id
        }
        with pytest.raises(ValueError):
            dm.create_entity("god-profile", incomplete_data)

    def test_create_with_invalid_enum_value(self, temp_world, sample_god_data):
        """Creating an entity with an invalid enum value should raise ValueError."""
        dm = DataManager(temp_world)
        bad_data = dict(sample_god_data)
        bad_data["alignment"] = "chaotic-banana"  # not a valid enum
        with pytest.raises(ValueError):
            dm.create_entity("god-profile", bad_data)

    def test_create_updates_state_index(self, temp_world, sample_god_data):
        """After creation, the entity should appear in the state's entity_index."""
        dm = DataManager(temp_world)
        entity_id = dm.create_entity("god-profile", sample_god_data)
        state = dm.get_state()

        assert entity_id in state["entity_index"]
        assert state["entity_index"][entity_id]["name"] == "Thorin Stormkeeper"

    def test_create_invalid_template_raises(self, temp_world, sample_god_data):
        """Creating with a nonexistent template should raise ValueError."""
        dm = DataManager(temp_world)
        with pytest.raises(ValueError):
            dm.create_entity("nonexistent-template-xyz", sample_god_data)


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

class TestUpdateEntity:
    """Tests for DataManager.update_entity."""

    def test_update_existing_entity(self, temp_world, sample_god_data):
        """Updating an existing entity should merge new fields."""
        dm = DataManager(temp_world)
        entity_id = dm.create_entity("god-profile", sample_god_data)

        dm.update_entity(entity_id, {"personality": "Updated personality text."})
        entity = dm.get_entity(entity_id)

        assert entity["personality"] == "Updated personality text."

    def test_update_preserves_untouched_fields(self, temp_world, sample_god_data):
        """Updating one field should not alter unrelated fields."""
        dm = DataManager(temp_world)
        entity_id = dm.create_entity("god-profile", sample_god_data)
        original = dm.get_entity(entity_id)

        dm.update_entity(entity_id, {"personality": "New personality."})
        updated = dm.get_entity(entity_id)

        assert updated["name"] == original["name"]
        assert updated["domain_primary"] == original["domain_primary"]

    def test_update_nonexistent_entity_raises(self, temp_world):
        """Updating a non-existent entity should raise FileNotFoundError."""
        dm = DataManager(temp_world)
        with pytest.raises(FileNotFoundError):
            dm.update_entity("nonexistent-id-0000", {"name": "Ghost"})

    def test_update_changes_updated_at(self, temp_world, sample_god_data):
        """After update, _meta.updated_at should change."""
        dm = DataManager(temp_world)
        entity_id = dm.create_entity("god-profile", sample_god_data)
        original = dm.get_entity(entity_id)
        original_time = original["_meta"]["updated_at"]

        dm.update_entity(entity_id, {"personality": "Changed."})
        updated = dm.get_entity(entity_id)

        assert updated["_meta"]["updated_at"] >= original_time


# ---------------------------------------------------------------------------
# Get and List
# ---------------------------------------------------------------------------

class TestGetAndList:
    """Tests for DataManager.get_entity and list_entities."""

    def test_get_entity(self, temp_world, sample_god_data):
        """get_entity should return the full entity document."""
        dm = DataManager(temp_world)
        entity_id = dm.create_entity("god-profile", sample_god_data)
        entity = dm.get_entity(entity_id)

        assert entity["name"] == "Thorin Stormkeeper"
        assert "canon_claims" in entity

    def test_get_nonexistent_entity_raises(self, temp_world):
        """get_entity with a bad ID should raise FileNotFoundError."""
        dm = DataManager(temp_world)
        with pytest.raises(FileNotFoundError):
            dm.get_entity("does-not-exist-0000")

    def test_list_entities_all(self, temp_world):
        """list_entities without filter should return all entities from the state index."""
        dm = DataManager(temp_world)
        # temp_world fixture has 2 pre-loaded entities
        all_entities = dm.list_entities()
        assert len(all_entities) >= 2

    def test_list_entities_by_type(self, temp_world):
        """list_entities with a type filter should return only matching entities."""
        dm = DataManager(temp_world)
        gods = dm.list_entities(entity_type="gods")
        settlements = dm.list_entities(entity_type="settlements")

        assert all(e["entity_type"] == "gods" for e in gods)
        assert all(e["entity_type"] == "settlements" for e in settlements)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

class TestSearch:
    """Tests for DataManager.search_entities."""

    def test_search_by_name(self, temp_world):
        """Searching by entity name should return matching results."""
        dm = DataManager(temp_world)
        results = dm.search_entities("Thorin")
        assert len(results) >= 1
        assert any("Thorin" in r.get("name", "") for r in results)

    def test_search_empty_query(self, temp_world):
        """An empty search query should return no results."""
        dm = DataManager(temp_world)
        results = dm.search_entities("")
        assert results == []

    def test_search_no_match(self, temp_world):
        """Searching for a nonexistent term should return empty list."""
        dm = DataManager(temp_world)
        results = dm.search_entities("xyzzyplughfrobozz")
        assert results == []


# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------

class TestValidateEntity:
    """Tests for DataManager.validate_entity."""

    def test_validate_valid_entity(self, temp_world, sample_god_data):
        """Validating a correctly formed entity should produce no errors."""
        dm = DataManager(temp_world)
        entity_id = dm.create_entity("god-profile", sample_god_data)
        errors = dm.validate_entity(entity_id)
        assert errors == []


# ---------------------------------------------------------------------------
# Canon Claims
# ---------------------------------------------------------------------------

class TestCanonClaims:
    """Tests for _extract_canon_claims."""

    def test_extracts_string_fields(self, sample_god_data, sample_template):
        """Canon claims should be extracted from simple string fields."""
        claims = _extract_canon_claims(sample_god_data, sample_template)
        assert isinstance(claims, list)
        assert len(claims) > 0
        # Should have a claim about domain_primary
        domain_claims = [c for c in claims if "storms" in c["claim"].lower()]
        assert len(domain_claims) >= 1

    def test_extracts_relationship_refs(self, sample_god_data, sample_template):
        """Canon claims from relationship arrays should include references."""
        claims = _extract_canon_claims(sample_god_data, sample_template)
        ref_claims = [c for c in claims if c.get("references")]
        # The spouse relationship should produce a referenced claim
        assert len(ref_claims) >= 1

    def test_skips_internal_fields(self, sample_template):
        """Canon claims should skip fields starting with underscore."""
        data = {
            "name": "Test",
            "_prose": "Should be ignored",
            "domain_primary": "wisdom",
        }
        claims = _extract_canon_claims(data, sample_template)
        prose_claims = [c for c in claims if "_prose" in c["claim"]]
        assert len(prose_claims) == 0


# ---------------------------------------------------------------------------
# Prose Generation
# ---------------------------------------------------------------------------

class TestProseGeneration:
    """Tests for prose generation functions."""

    def test_prose_for_god(self, sample_god_data):
        """God prose should mention the god's name and domain."""
        prose = _prose_for_god(sample_god_data)
        assert "Thorin Stormkeeper" in prose
        assert "storm" in prose.lower()

    def test_prose_for_settlement(self, sample_settlement_data):
        """Settlement prose should mention the settlement name and type."""
        prose = _prose_for_settlement(sample_settlement_data)
        assert "Havenport" in prose
        assert "city" in prose.lower()

    def test_prose_for_species(self):
        """Species prose should mention the species name."""
        data = {
            "name": "Drakken",
            "classification": "species",
            "disposition": "proud",
            "famous_for": "their fire-breathing ability",
        }
        prose = _prose_for_species(data)
        assert "Drakken" in prose
        assert "proud" in prose.lower()

    def test_prose_for_religion(self):
        """Religion prose should mention the religion name and gods worshiped."""
        data = {
            "name": "The Solar Covenant",
            "gods_worshiped": ["Solara", "Luminos"],
            "founding_story": "Two sages witnessed a double sunrise",
        }
        prose = _prose_for_religion(data)
        assert "Solar Covenant" in prose
        assert "Solara" in prose

    def test_prose_generic_fallback(self):
        """The generic prose builder should handle unknown entity types."""
        data = {
            "name": "Mystic Rune",
            "description": "A glowing rune of power.",
        }
        prose = _prose_generic(data, "unknown-type-profile")
        assert "Mystic Rune" in prose

    def test_generate_prose_via_manager(self, temp_world, sample_god_data):
        """DataManager.generate_prose should produce a non-empty string."""
        dm = DataManager(temp_world)
        prose = dm.generate_prose(sample_god_data, "god-profile")
        assert isinstance(prose, str)
        assert len(prose) > 20
        assert "Thorin Stormkeeper" in prose


# ---------------------------------------------------------------------------
# Custom Prose Override
# ---------------------------------------------------------------------------

class TestCustomProse:
    """Tests for custom prose override behavior during create and update."""

    def test_create_with_custom_prose(self, temp_world, sample_god_data):
        """If _prose and _prose_custom=True are provided, custom prose is preserved."""
        dm = DataManager(temp_world)
        data = dict(sample_god_data)
        data["_prose"] = "This is my custom prose about Thorin."
        data["_prose_custom"] = True

        entity_id = dm.create_entity("god-profile", data)
        entity = dm.get_entity(entity_id)

        assert entity["_prose"] == "This is my custom prose about Thorin."
        assert entity["_prose_custom"] is True

    def test_create_without_custom_prose_autogenerates(self, temp_world, sample_god_data):
        """If no custom prose is provided, prose is auto-generated."""
        dm = DataManager(temp_world)
        entity_id = dm.create_entity("god-profile", sample_god_data)
        entity = dm.get_entity(entity_id)

        assert entity["_prose_custom"] is False
        assert len(entity.get("_prose", "")) > 0
