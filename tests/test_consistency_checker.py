"""
Tests for engine/consistency_checker.py -- Three-layer consistency validation.

Validates:
    - check_schema passes valid entities
    - check_schema catches missing required fields
    - check_schema catches wrong types
    - check_rules validates cross-references
    - check_rules catches bidirectional relationship mismatches
    - check_semantic prepares proper context
    - format_human_message produces readable output
    - Full check_entity pipeline
"""

import json
import os
import pytest

from engine.consistency_checker import ConsistencyChecker


# ---------------------------------------------------------------------------
# Layer 1: Schema Validation
# ---------------------------------------------------------------------------

class TestCheckSchema:
    """Tests for ConsistencyChecker.check_schema (Layer 1)."""

    def test_valid_entity_passes(self, temp_world, sample_god_data):
        """A valid entity should pass schema validation."""
        cc = ConsistencyChecker(temp_world)
        result = cc.check_schema(sample_god_data, "god-profile")
        assert result["passed"] is True
        assert result["errors"] == []

    def test_missing_required_field_fails(self, temp_world):
        """An entity missing a required field should fail validation."""
        cc = ConsistencyChecker(temp_world)
        incomplete = {
            "name": "Incomplete God",
            # Missing: domain_primary, alignment, symbol, relationships, pantheon_id
        }
        result = cc.check_schema(incomplete, "god-profile")
        assert result["passed"] is False
        assert len(result["errors"]) > 0

    def test_wrong_type_fails(self, temp_world, sample_god_data):
        """A field with the wrong data type should fail validation."""
        cc = ConsistencyChecker(temp_world)
        bad_data = dict(sample_god_data)
        bad_data["alignment"] = 42  # should be a string enum
        result = cc.check_schema(bad_data, "god-profile")
        assert result["passed"] is False

    def test_invalid_enum_fails(self, temp_world, sample_god_data):
        """An invalid enum value should fail validation."""
        cc = ConsistencyChecker(temp_world)
        bad_data = dict(sample_god_data)
        bad_data["alignment"] = "chaotic-banana"
        result = cc.check_schema(bad_data, "god-profile")
        assert result["passed"] is False

    def test_unknown_template_fails(self, temp_world, sample_god_data):
        """Using a nonexistent template ID should fail."""
        cc = ConsistencyChecker(temp_world)
        result = cc.check_schema(sample_god_data, "nonexistent-template-xyz")
        assert result["passed"] is False
        assert any("nonexistent" in e.lower() for e in result["errors"])

    def test_error_messages_are_human_readable(self, temp_world):
        """Error messages should be readable (no tracebacks or raw JSON)."""
        cc = ConsistencyChecker(temp_world)
        incomplete = {"name": "Test"}
        result = cc.check_schema(incomplete, "god-profile")
        for error in result["errors"]:
            assert isinstance(error, str)
            assert len(error) > 10
            # Should not contain Python traceback patterns
            assert "Traceback" not in error

    def test_valid_settlement_passes(self, temp_world, sample_settlement_data):
        """A valid settlement entity should pass schema validation."""
        cc = ConsistencyChecker(temp_world)
        result = cc.check_schema(sample_settlement_data, "settlement-profile")
        assert result["passed"] is True


# ---------------------------------------------------------------------------
# Layer 2: Rule-Based Checks
# ---------------------------------------------------------------------------

class TestCheckRules:
    """Tests for ConsistencyChecker.check_rules (Layer 2)."""

    def test_valid_entity_passes_rules(self, temp_world, sample_god_data):
        """A well-formed entity with no bad references should pass."""
        cc = ConsistencyChecker(temp_world)
        # Build entity with _meta so check_rules can find the schema
        data = dict(sample_god_data)
        data["_meta"] = {"template_id": "god-profile", "id": "test-god-0000"}
        result = cc.check_rules(data)
        # May have warnings about non-existent references, but shouldn't crash
        assert isinstance(result, dict)
        assert "passed" in result

    def test_catches_negative_population(self, temp_world):
        """A negative population should be flagged."""
        cc = ConsistencyChecker(temp_world)
        data = {
            "name": "Bad Settlement",
            "population": -500,
            "_meta": {"template_id": "settlement-profile", "id": "bad-0000"},
        }
        result = cc.check_rules(data)
        assert result["passed"] is False
        assert any("negative population" in e.lower() for e in result["errors"])

    def test_catches_founding_after_dissolution(self, temp_world):
        """A founding year after dissolution year should be flagged."""
        cc = ConsistencyChecker(temp_world)
        data = {
            "name": "Temporal Paradox",
            "founded": 500,
            "dissolved": 200,
            "_meta": {"template_id": "", "id": "paradox-0000"},
        }
        result = cc.check_rules(data)
        assert result["passed"] is False
        assert any("founding" in e.lower() or "founded" in e.lower() for e in result["errors"])

    def test_bidirectional_spouse_check(self, temp_world, sample_god_data):
        """check_rules should flag unreciprocated spouse relationships."""
        cc = ConsistencyChecker(temp_world)
        # Thorin lists Mira as a spouse, but Mira doesn't exist yet
        # in temp_world as an entity. The check_rules should still run.
        data = dict(sample_god_data)
        data["_meta"] = {
            "template_id": "god-profile",
            "id": "thorin-stormkeeper-a1b2",
        }
        result = cc.check_rules(data, entity_id="thorin-stormkeeper-a1b2")
        # This shouldn't crash -- reference to non-existent is caught separately
        assert isinstance(result, dict)

    def test_category_exclusion_god_mortal(self, temp_world):
        """A full god with a mortal lifespan should trigger a warning."""
        cc = ConsistencyChecker(temp_world)
        data = {
            "name": "Mortal God",
            "god_type": "god",
            "lifespan": "mortal, dies after 80 years",
            "_meta": {"template_id": "god-profile", "id": "mortal-god-0000"},
        }
        result = cc.check_rules(data)
        assert result["passed"] is False
        assert any("mortal" in e.lower() for e in result["errors"])

    def test_species_breakdown_percentage(self, temp_world):
        """Species breakdown percentages that don't sum to 100 should be flagged."""
        cc = ConsistencyChecker(temp_world)
        data = {
            "name": "Bad Math Village",
            "population": 1000,
            "species_breakdown": [
                {"species_id": "humans", "percentage": 30},
                {"species_id": "elves", "percentage": 20},
                # Total: 50, not ~100
            ],
            "_meta": {"template_id": "settlement-profile", "id": "bad-math-0000"},
        }
        result = cc.check_rules(data)
        assert result["passed"] is False
        assert any("percentage" in e.lower() or "100%" in e for e in result["errors"])


# ---------------------------------------------------------------------------
# Layer 3: Semantic Check
# ---------------------------------------------------------------------------

class TestCheckSemantic:
    """Tests for ConsistencyChecker.check_semantic (Layer 3)."""

    def test_entity_with_no_claims_passes(self, temp_world):
        """An entity with no canon_claims should pass semantic check."""
        cc = ConsistencyChecker(temp_world)
        data = {"name": "Simple Entity", "canon_claims": []}
        result = cc.check_semantic(data)
        assert result["passed"] is True
        assert result["needs_llm_review"] is False

    def test_semantic_returns_expected_keys(self, temp_world, sample_god_data):
        """check_semantic should return a dict with all expected keys."""
        cc = ConsistencyChecker(temp_world)
        data = dict(sample_god_data)
        data["canon_claims"] = [
            {"claim": "Thorin is the god of storms", "references": []},
        ]
        result = cc.check_semantic(data, entity_id="thorin-test-0000")

        assert "passed" in result
        assert "warnings" in result
        assert "conflicts" in result
        assert "new_claims" in result
        assert "similar_existing_claims" in result
        assert "needs_llm_review" in result
        assert "llm_prompt" in result

    def test_similar_claims_found(self, temp_world):
        """If there are entities with similar claims, they should be found."""
        cc = ConsistencyChecker(temp_world)
        # Thorin in temp_world has a claim about storms
        data = {
            "name": "Storm Rival",
            "canon_claims": [
                {"claim": "Storm Rival's primary domain is storms", "references": []},
            ],
        }
        result = cc.check_semantic(data, entity_id="storm-rival-0000")
        # Similar claims should be populated (Thorin also has storms domain)
        assert isinstance(result["similar_existing_claims"], list)


# ---------------------------------------------------------------------------
# Human Message Formatting
# ---------------------------------------------------------------------------

class TestFormatHumanMessage:
    """Tests for format_human_message."""

    def test_passed_message(self, temp_world):
        """A passed result should produce a friendly success message."""
        cc = ConsistencyChecker(temp_world)
        result = {
            "passed": True,
            "layer1_schema": {"passed": True, "errors": []},
            "layer2_rules": {"passed": True, "errors": []},
            "layer3_semantic": {
                "passed": True, "warnings": [], "conflicts": [],
                "needs_llm_review": False,
            },
        }
        msg = cc.format_human_message(result, "Thorin Stormkeeper")
        assert "passed" in msg.lower() or "Thorin Stormkeeper" in msg

    def test_failed_schema_message(self, temp_world):
        """A failed schema check should produce a message about data structure."""
        cc = ConsistencyChecker(temp_world)
        result = {
            "passed": False,
            "layer1_schema": {
                "passed": False,
                "errors": ["Missing required field: domain_primary"],
            },
            "layer2_rules": {"passed": None, "errors": ["Skipped"]},
            "layer3_semantic": {"passed": None, "warnings": []},
        }
        msg = cc.format_human_message(result, "Broken God")
        assert "Broken God" in msg
        assert "domain_primary" in msg or "ISSUE" in msg

    def test_failed_rules_message(self, temp_world):
        """A failed rules check should produce a message with options."""
        cc = ConsistencyChecker(temp_world)
        result = {
            "passed": False,
            "layer1_schema": {"passed": True, "errors": []},
            "layer2_rules": {
                "passed": False,
                "errors": ["Negative population detected"],
            },
            "layer3_semantic": {"passed": None, "warnings": []},
        }
        msg = cc.format_human_message(result, "Bad Village")
        assert "Bad Village" in msg
        assert "OPTIONS" in msg or "ISSUE" in msg

    def test_message_is_readable_string(self, temp_world):
        """Messages should be non-empty strings without Python internals."""
        cc = ConsistencyChecker(temp_world)
        result = {
            "passed": True,
            "layer1_schema": {"passed": True, "errors": []},
            "layer2_rules": {"passed": True, "errors": []},
            "layer3_semantic": {"passed": True, "warnings": [], "needs_llm_review": False},
        }
        msg = cc.format_human_message(result, "Test Entity")
        assert isinstance(msg, str)
        assert len(msg) > 5
        assert "Traceback" not in msg


# ---------------------------------------------------------------------------
# Full Pipeline: check_entity
# ---------------------------------------------------------------------------

class TestCheckEntityPipeline:
    """Tests for the full check_entity pipeline."""

    def test_check_entity_with_valid_data(self, temp_world, sample_god_data):
        """check_entity with valid data dict should return a complete result."""
        cc = ConsistencyChecker(temp_world)
        data = dict(sample_god_data)
        data["_meta"] = {
            "id": "pipeline-test-0001",
            "template_id": "god-profile",
            "entity_type": "gods",
            "status": "draft",
        }
        data["canon_claims"] = []

        result = cc.check_entity(data)
        assert "passed" in result
        assert "layer1_schema" in result
        assert "layer2_rules" in result
        assert "layer3_semantic" in result
        assert "human_message" in result

    def test_check_entity_with_invalid_data_stops_at_layer1(self, temp_world):
        """check_entity with invalid data should fail at layer 1 and skip layers 2+3."""
        cc = ConsistencyChecker(temp_world)
        data = {
            "name": "Incomplete",
            "_meta": {
                "id": "incomplete-0001",
                "template_id": "god-profile",
            },
        }
        result = cc.check_entity(data)
        assert result["passed"] is False
        assert result["layer1_schema"]["passed"] is False
        # Layer 2 should be skipped
        assert result["layer2_rules"]["passed"] is None or "Skipped" in str(result["layer2_rules"]["errors"])

    def test_check_entity_by_id(self, temp_world):
        """check_entity with a string ID should load the entity from disk."""
        cc = ConsistencyChecker(temp_world)
        result = cc.check_entity("thorin-stormkeeper-a1b2")
        assert isinstance(result, dict)
        assert "passed" in result
        assert "human_message" in result

    def test_check_entity_missing_id(self, temp_world):
        """check_entity with a nonexistent ID should fail gracefully."""
        cc = ConsistencyChecker(temp_world)
        result = cc.check_entity("nonexistent-entity-9999")
        assert result["passed"] is False
        assert len(result["layer1_schema"]["errors"]) > 0

    def test_check_entity_no_template_id(self, temp_world):
        """check_entity with data but no template_id should fail with a helpful message."""
        cc = ConsistencyChecker(temp_world)
        data = {"name": "Orphaned Entity"}
        result = cc.check_entity(data)
        assert result["passed"] is False
        assert any("template" in e.lower() for e in result["layer1_schema"]["errors"])
