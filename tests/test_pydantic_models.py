"""
Tests for engine/models/ -- Pydantic v2 models, factory, and validators.

Covers:
    - EntityMeta and WorldEntity base models
    - ModelFactory dynamic model generation from JSON schemas
    - Cross-reference, name uniqueness, canon claim, and canon readiness validators
    - Validation error handling and humanization
"""

import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ======================================================================
# Base model tests
# ======================================================================


class TestEntityMeta:
    """Tests for the EntityMeta base model."""

    def test_default_construction(self):
        from engine.models.base import EntityMeta
        meta = EntityMeta()
        assert meta.id == ""
        assert meta.status == "draft"
        assert meta.template_id == ""

    def test_valid_statuses(self):
        from engine.models.base import EntityMeta
        for status in ("draft", "canon", "archived"):
            meta = EntityMeta(status=status)
            assert meta.status == status

    def test_invalid_status_rejected(self):
        from engine.models.base import EntityMeta
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            EntityMeta(status="invalid_status")

    def test_extra_fields_allowed(self):
        from engine.models.base import EntityMeta
        meta = EntityMeta(id="test", custom_field="hello")
        assert meta.model_extra["custom_field"] == "hello"

    def test_all_fields_populated(self):
        from engine.models.base import EntityMeta
        meta = EntityMeta(
            id="thor-001",
            template_id="god-profile",
            entity_type="god",
            status="canon",
            file_path="user-world/entities/gods/thor-001.json",
            step_created=7,
            created_at="2025-01-01T00:00:00Z",
            updated_at="2025-06-01T00:00:00Z",
            revision_number=3,
        )
        assert meta.id == "thor-001"
        assert meta.entity_type == "god"
        assert meta.revision_number == 3


class TestWorldEntity:
    """Tests for the WorldEntity base model."""

    def test_default_construction(self):
        from engine.models.base import WorldEntity
        entity = WorldEntity()
        assert entity.name == ""
        assert entity.meta.id == ""

    def test_from_file_dict(self):
        from engine.models.base import WorldEntity
        data = {
            "_meta": {
                "id": "thor-001",
                "template_id": "god-profile",
                "entity_type": "god",
                "status": "draft",
            },
            "id": "thor-001",
            "name": "Thor Stormkeeper",
            "notes": "A test god",
        }
        entity = WorldEntity.model_validate(data)
        assert entity.entity_id == "thor-001"
        assert entity.name == "Thor Stormkeeper"
        assert entity.meta.template_id == "god-profile"

    def test_to_file_dict_roundtrip(self):
        from engine.models.base import WorldEntity
        data = {
            "_meta": {"id": "test-001", "template_id": "god-profile"},
            "name": "Test Entity",
        }
        entity = WorldEntity.model_validate(data)
        out = entity.to_file_dict()
        assert "_meta" in out
        assert "meta" not in out
        assert out["name"] == "Test Entity"

    def test_entity_type_property(self):
        from engine.models.base import WorldEntity
        data = {"_meta": {"entity_type": "settlement"}}
        entity = WorldEntity.model_validate(data)
        assert entity.entity_type == "settlement"

    def test_meta_status_property(self):
        from engine.models.base import WorldEntity
        data = {"_meta": {"status": "canon"}}
        entity = WorldEntity.model_validate(data)
        assert entity.meta_status == "canon"

    def test_extra_fields_pass_through(self):
        from engine.models.base import WorldEntity
        data = {
            "_meta": {"id": "test"},
            "name": "Test",
            "domain_primary": "storms",
            "alignment": "good",
        }
        entity = WorldEntity.model_validate(data)
        assert entity.model_extra["domain_primary"] == "storms"

    def test_blank_name_rejected(self):
        from engine.models.base import WorldEntity
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            WorldEntity(name="   ")


# ======================================================================
# Model factory tests
# ======================================================================


class TestModelFactory:
    """Tests for the dynamic model factory."""

    @pytest.fixture
    def factory(self):
        from engine.models.factory import ModelFactory
        return ModelFactory(str(PROJECT_ROOT))

    def test_get_template_ids(self, factory):
        ids = factory.get_template_ids()
        assert len(ids) >= 80
        assert "god-profile" in ids
        assert "settlement-profile" in ids

    def test_get_schema(self, factory):
        schema = factory.get_schema("god-profile")
        assert schema is not None
        assert schema["$id"] == "god-profile"
        assert "properties" in schema

    def test_get_schema_missing(self, factory):
        schema = factory.get_schema("nonexistent-template")
        assert schema is None

    def test_get_model_creates_class(self, factory):
        model = factory.get_model("god-profile")
        assert model is not None
        assert model.__name__ == "GodProfileModel"

    def test_model_has_template_fields(self, factory):
        model = factory.get_model("god-profile")
        fields = model.model_fields
        assert "domain_primary" in fields
        assert "alignment" in fields
        assert "relationships" in fields

    def test_model_has_base_fields(self, factory):
        model = factory.get_model("god-profile")
        fields = model.model_fields
        assert "name" in fields
        assert "meta" in fields

    def test_model_caching(self, factory):
        model1 = factory.get_model("god-profile")
        model2 = factory.get_model("god-profile")
        assert model1 is model2

    def test_preload_all(self, factory):
        count = factory.preload_all()
        assert count >= 80

    def test_model_json_schema_works(self, factory):
        model = factory.get_model("god-profile")
        schema = model.model_json_schema()
        assert "properties" in schema
        assert "title" in schema

    def test_required_fields_stored(self, factory):
        model = factory.get_model("god-profile")
        required = model._required_fields
        assert "name" in required
        assert "domain_primary" in required
        assert "alignment" in required

    def test_cross_references_stored(self, factory):
        model = factory.get_model("god-profile")
        xrefs = model._cross_references
        assert "pantheon-overview" in xrefs


class TestValidation:
    """Tests for factory validation."""

    @pytest.fixture
    def factory(self):
        from engine.models.factory import ModelFactory
        return ModelFactory(str(PROJECT_ROOT))

    def test_valid_entity_passes(self, factory):
        data = {
            "_meta": {"id": "thor-001", "template_id": "god-profile"},
            "name": "Thor Stormkeeper",
            "domain_primary": "storms",
            "alignment": "good",
            "symbol": "lightning bolt",
            "relationships": [{"target_id": "odin-001", "relationship_type": "child"}],
            "pantheon_id": "norse-001",
        }
        result = factory.validate_entity(data, "god-profile")
        assert result.passed is True
        assert result.errors == []
        assert result.entity is not None

    def test_missing_required_field_fails(self, factory):
        data = {
            "_meta": {"id": "thor-001", "template_id": "god-profile"},
            "name": "Thor",
            # Missing: domain_primary, alignment, symbol, relationships, pantheon_id
        }
        result = factory.validate_entity(data, "god-profile")
        assert result.passed is False
        assert len(result.errors) >= 1

    def test_invalid_enum_fails(self, factory):
        data = {
            "_meta": {"id": "thor-001", "template_id": "god-profile"},
            "name": "Thor",
            "domain_primary": "storms",
            "alignment": "chaotic_evil",  # Not a valid enum
            "symbol": "bolt",
            "relationships": [{"target_id": "x", "relationship_type": "child"}],
            "pantheon_id": "p-001",
        }
        result = factory.validate_entity(data, "god-profile")
        assert result.passed is False
        assert any("alignment" in e for e in result.errors)

    def test_missing_template_fails(self, factory):
        data = {"name": "Test"}
        result = factory.validate_entity(data, "nonexistent-template")
        assert result.passed is False
        assert any("template" in e.lower() for e in result.errors)

    def test_no_template_id_fails(self, factory):
        data = {"name": "Test"}
        result = factory.validate_entity(data)
        assert result.passed is False

    def test_to_dict(self, factory):
        data = {
            "_meta": {"template_id": "god-profile"},
            "name": "Thor",
            "domain_primary": "storms",
            "alignment": "good",
            "symbol": "bolt",
            "relationships": [{"target_id": "x", "relationship_type": "child"}],
            "pantheon_id": "p",
        }
        result = factory.validate_entity(data, "god-profile")
        d = result.to_dict()
        assert "passed" in d
        assert "errors" in d

    def test_settlement_validation(self, factory):
        data = {
            "_meta": {"template_id": "settlement-profile"},
            "name": "Ironhaven",
            "type": "city",
            "sovereign_power_id": "sp-001",
            "climate": "temperate",
            "terrain": "coastal",
            "population": 25000,
            "species_breakdown": [{"species_id": "human", "percentage": 80}],
            "leadership": {"leader_name": "Mayor Smith"},
        }
        result = factory.validate_entity(data, "settlement-profile")
        assert result.passed is True

    def test_settlement_bad_type_fails(self, factory):
        data = {
            "_meta": {"template_id": "settlement-profile"},
            "name": "Ironhaven",
            "type": "megacity",  # Not in enum
            "sovereign_power_id": "sp-001",
            "climate": "temperate",
            "terrain": "coastal",
            "population": 25000,
            "species_breakdown": [],
            "leadership": {},
        }
        result = factory.validate_entity(data, "settlement-profile")
        assert result.passed is False


# ======================================================================
# Validator tests
# ======================================================================


class TestCrossReferenceValidator:
    """Tests for validate_cross_references."""

    def test_broken_ref_detected(self):
        from engine.models.validators import validate_cross_references
        schema = {
            "properties": {
                "pantheon_id": {"type": "string", "x-cross-reference": "pantheon-overview"},
            }
        }
        entity = {"name": "Thor", "pantheon_id": "nonexistent"}
        issues = validate_cross_references(entity, schema, {})
        assert len(issues) == 1
        assert "nonexistent" in issues[0]

    def test_valid_ref_passes(self):
        from engine.models.validators import validate_cross_references
        schema = {
            "properties": {
                "pantheon_id": {"type": "string", "x-cross-reference": "pantheon-overview"},
            }
        }
        entity = {"name": "Thor", "pantheon_id": "norse-001"}
        issues = validate_cross_references(entity, schema, {"norse-001": {}})
        assert len(issues) == 0

    def test_empty_ref_ignored(self):
        from engine.models.validators import validate_cross_references
        schema = {
            "properties": {
                "pantheon_id": {"type": "string", "x-cross-reference": "pantheon-overview"},
            }
        }
        entity = {"name": "Thor", "pantheon_id": ""}
        issues = validate_cross_references(entity, schema, {})
        assert len(issues) == 0

    def test_array_refs_checked(self):
        from engine.models.validators import validate_cross_references
        schema = {
            "properties": {
                "species_created": {
                    "type": "array",
                    "items": {"type": "string", "x-cross-reference": "species-profile"},
                }
            }
        }
        entity = {"name": "Thor", "species_created": ["human", "elf"]}
        issues = validate_cross_references(entity, schema, {"human": {}})
        assert len(issues) == 1
        assert "elf" in issues[0]

    def test_nested_object_refs_checked(self):
        from engine.models.validators import validate_cross_references
        schema = {
            "properties": {
                "relationships": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "target_id": {"type": "string", "x-cross-reference": "god-profile"},
                        }
                    }
                }
            }
        }
        entity = {
            "name": "Thor",
            "relationships": [
                {"target_id": "odin-001"},
                {"target_id": "loki-001"},
            ]
        }
        issues = validate_cross_references(entity, schema, {"odin-001": {}})
        assert len(issues) == 1
        assert "loki-001" in issues[0]


class TestNameUniqueness:
    """Tests for validate_name_uniqueness."""

    def test_duplicate_detected(self):
        from engine.models.validators import validate_name_uniqueness
        entity = {"name": "Thor", "_meta": {"id": "new-thor", "entity_type": "god"}}
        index = {"old-thor": {"name": "Thor", "entity_type": "god"}}
        issues = validate_name_uniqueness(entity, index)
        assert len(issues) == 1

    def test_same_entity_not_flagged(self):
        from engine.models.validators import validate_name_uniqueness
        entity = {"name": "Thor", "_meta": {"id": "thor-001", "entity_type": "god"}}
        index = {"thor-001": {"name": "Thor", "entity_type": "god"}}
        issues = validate_name_uniqueness(entity, index)
        assert len(issues) == 0

    def test_different_type_not_flagged(self):
        from engine.models.validators import validate_name_uniqueness
        entity = {"name": "Thor", "_meta": {"id": "thor-001", "entity_type": "god"}}
        index = {"thor-ship": {"name": "Thor", "entity_type": "ship"}}
        issues = validate_name_uniqueness(entity, index)
        assert len(issues) == 0

    def test_case_insensitive(self):
        from engine.models.validators import validate_name_uniqueness
        entity = {"name": "THOR", "_meta": {"id": "new-thor", "entity_type": "god"}}
        index = {"old-thor": {"name": "thor", "entity_type": "god"}}
        issues = validate_name_uniqueness(entity, index)
        assert len(issues) == 1


class TestCanonClaims:
    """Tests for extract_canon_claims."""

    def test_prose_fields_extracted(self):
        from engine.models.validators import extract_canon_claims
        entity = {
            "name": "Thor",
            "overview": "God of storms and thunder.",
            "history": "Created the first thunderstorm.",
        }
        claims = extract_canon_claims(entity)
        assert len(claims) == 2
        assert all(c["claim_type"] == "prose" for c in claims)

    def test_relationship_claims(self):
        from engine.models.validators import extract_canon_claims
        entity = {
            "name": "Thor",
            "relationships": [
                {"target_id": "odin", "relationship_type": "child", "description": "Son of Odin"}
            ],
        }
        claims = extract_canon_claims(entity)
        assert len(claims) == 1
        assert claims[0]["claim_type"] == "relationship"

    def test_empty_fields_skipped(self):
        from engine.models.validators import extract_canon_claims
        entity = {"name": "Thor", "overview": "", "history": "   "}
        claims = extract_canon_claims(entity)
        assert len(claims) == 0

    def test_entity_name_in_claim(self):
        from engine.models.validators import extract_canon_claims
        entity = {"name": "Thor", "overview": "God of storms."}
        claims = extract_canon_claims(entity)
        assert claims[0]["entity_name"] == "Thor"


class TestCanonReadiness:
    """Tests for validate_canon_readiness."""

    def test_complete_entity_passes(self):
        from engine.models.validators import validate_canon_readiness
        entity = {
            "name": "Thor",
            "domain_primary": "storms",
            "alignment": "good",
        }
        schema = {"required": ["name", "domain_primary", "alignment"]}
        issues = validate_canon_readiness(entity, schema)
        assert len(issues) == 0

    def test_missing_field_flagged(self):
        from engine.models.validators import validate_canon_readiness
        entity = {"name": "Thor"}
        schema = {"required": ["name", "domain_primary"]}
        issues = validate_canon_readiness(entity, schema)
        assert len(issues) == 1
        assert "domain_primary" in issues[0]

    def test_empty_string_flagged(self):
        from engine.models.validators import validate_canon_readiness
        entity = {"name": "Thor", "domain_primary": ""}
        schema = {"required": ["name", "domain_primary"]}
        issues = validate_canon_readiness(entity, schema)
        assert len(issues) == 1

    def test_empty_list_flagged(self):
        from engine.models.validators import validate_canon_readiness
        entity = {"name": "Thor", "relationships": []}
        schema = {"required": ["name", "relationships"]}
        issues = validate_canon_readiness(entity, schema)
        assert len(issues) == 1


# ======================================================================
# Error humanization tests
# ======================================================================


class TestErrorHumanization:
    """Tests for Pydantic error humanization."""

    def test_missing_field_message(self):
        from engine.models.factory import _humanize_pydantic_error
        err = {"type": "missing", "loc": ("domain_primary",), "msg": "Field required"}
        msg = _humanize_pydantic_error(err, {"name": "Thor"})
        assert "domain_primary" in msg
        assert "Thor" in msg
        assert "required" in msg

    def test_literal_error_message(self):
        from engine.models.factory import _humanize_pydantic_error
        err = {
            "type": "literal_error",
            "loc": ("alignment",),
            "msg": "Input should be 'good', 'neutral', or 'evil'",
        }
        msg = _humanize_pydantic_error(err, {"name": "Thor"})
        assert "alignment" in msg
        assert "invalid value" in msg.lower()

    def test_type_error_message(self):
        from engine.models.factory import _humanize_pydantic_error
        err = {
            "type": "string_type",
            "loc": ("name",),
            "msg": "Input should be a valid string",
        }
        msg = _humanize_pydantic_error(err, {"name": 42})
        assert "name" in msg
        assert "wrong type" in msg.lower()
