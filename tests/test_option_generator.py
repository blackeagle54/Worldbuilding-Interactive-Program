"""
Tests for engine/option_generator.py -- OptionGenerator divergent-convergent pipeline.

Validates:
    - generate_options returns correct structure
    - Anti-repetition tracking
    - Concept injection adds variety
    - Context assembly includes all required sections
"""

import json
import os
import pytest

from engine.option_generator import OptionGenerator


# ---------------------------------------------------------------------------
# Generate Options Structure
# ---------------------------------------------------------------------------

class TestGenerateOptions:
    """Tests for OptionGenerator.generate_options."""

    def test_returns_dict(self, temp_world):
        """generate_options should return a dict."""
        og = OptionGenerator(temp_world)
        result = og.generate_options(step_number=7, num_options=3)
        assert isinstance(result, dict)

    def test_has_step_metadata(self, temp_world):
        """Result should contain step metadata."""
        og = OptionGenerator(temp_world)
        result = og.generate_options(step_number=7)
        assert "step" in result
        assert result["step"]["number"] == 7

    def test_has_divergent_phase(self, temp_world):
        """Result should contain the divergent phase section."""
        og = OptionGenerator(temp_world)
        result = og.generate_options(step_number=7)
        assert "divergent_phase" in result
        div = result["divergent_phase"]
        assert "instructions" in div
        assert "step_guidance" in div
        assert "existing_canon" in div
        assert "source_assignments" in div
        assert "random_concepts" in div

    def test_has_convergent_phase(self, temp_world):
        """Result should contain the convergent phase section."""
        og = OptionGenerator(temp_world)
        result = og.generate_options(step_number=7)
        assert "convergent_phase" in result
        conv = result["convergent_phase"]
        assert "anti_repetition" in conv
        assert "canon_consistency" in conv
        assert "diversity_criteria" in conv

    def test_has_flesh_out_phase(self, temp_world):
        """Result should contain the flesh-out phase section."""
        og = OptionGenerator(temp_world)
        result = og.generate_options(step_number=7)
        assert "flesh_out_phase" in result
        flesh = result["flesh_out_phase"]
        assert "output_schema" in flesh
        assert "template_fields" in flesh

    def test_has_generation_metadata(self, temp_world):
        """Result should contain generation metadata."""
        og = OptionGenerator(temp_world)
        result = og.generate_options(step_number=7)
        assert "generation_metadata" in result
        meta = result["generation_metadata"]
        assert "generated_at" in meta
        assert "target_option_count" in meta

    def test_num_options_clamped(self, temp_world):
        """num_options should be clamped to the 2-4 range."""
        og = OptionGenerator(temp_world)
        result = og.generate_options(step_number=7, num_options=10)
        assert result["convergent_phase"]["target_count"] <= 4

        result2 = og.generate_options(step_number=7, num_options=0)
        assert result2["convergent_phase"]["target_count"] >= 2

    def test_source_assignments_count(self, temp_world):
        """Source assignments should match the requested number of options."""
        og = OptionGenerator(temp_world)
        result = og.generate_options(step_number=7, num_options=3)
        assignments = result["source_assignments"]
        assert len(assignments) == 3

    def test_option_ids_generated(self, temp_world):
        """The output schema should include option IDs (opt-a, opt-b, etc.)."""
        og = OptionGenerator(temp_world)
        result = og.generate_options(step_number=7, num_options=3)
        option_ids = result["flesh_out_phase"]["output_schema"]["option_ids"]
        assert option_ids == ["opt-a", "opt-b", "opt-c"]


# ---------------------------------------------------------------------------
# Anti-Repetition
# ---------------------------------------------------------------------------

class TestAntiRepetition:
    """Tests for anti-repetition tracking."""

    def test_used_themes_initially_empty(self, temp_world):
        """Before any choices are recorded, used themes should be empty."""
        og = OptionGenerator(temp_world)
        themes = og.get_used_themes()
        assert isinstance(themes, list)
        assert len(themes) == 0

    def test_record_choice_adds_themes(self, temp_world):
        """After recording a choice with themes, get_used_themes should return them."""
        og = OptionGenerator(temp_world)
        og.record_choice(
            step_number=7,
            chosen_option_id="opt-a",
            rationale="Liked the storm theme",
            themes_used=["storms", "divine wrath"],
            random_concepts_used=["fire"],
        )
        themes = og.get_used_themes()
        assert "storms" in themes
        assert "divine wrath" in themes

    def test_anti_repetition_in_generation(self, temp_world):
        """After recording themes, generate_options should include them in anti_repetition."""
        og = OptionGenerator(temp_world)
        og.record_choice(
            step_number=7,
            chosen_option_id="opt-a",
            themes_used=["thunder", "revenge"],
        )
        result = og.generate_options(step_number=8, num_options=3)
        avoid = result["convergent_phase"]["anti_repetition"]["themes_to_avoid"]
        assert "thunder" in avoid
        assert "revenge" in avoid


# ---------------------------------------------------------------------------
# Concept Injection
# ---------------------------------------------------------------------------

class TestConceptInjection:
    """Tests for random concept injection."""

    def test_concepts_are_included(self, temp_world):
        """The divergent phase should include random concept injections."""
        og = OptionGenerator(temp_world)
        result = og.generate_options(step_number=7)
        concepts = result["divergent_phase"]["random_concepts"]
        assert isinstance(concepts, list)
        # The concept bank was set up in temp_world, so should have picks
        if og._all_concepts:
            assert len(concepts) > 0

    def test_concept_has_category(self, temp_world):
        """Each injected concept should have a concept and category key."""
        og = OptionGenerator(temp_world)
        result = og.generate_options(step_number=7)
        for concept in result["divergent_phase"]["random_concepts"]:
            assert "concept" in concept
            assert "category" in concept


# ---------------------------------------------------------------------------
# Context Assembly
# ---------------------------------------------------------------------------

class TestContextAssembly:
    """Tests that the context includes all required sections."""

    def test_existing_canon_entities(self, temp_world):
        """The divergent phase should include existing canon entity summaries."""
        og = OptionGenerator(temp_world)
        result = og.generate_options(step_number=7)
        canon = result["divergent_phase"]["existing_canon"]
        assert "all_entities" in canon
        assert "entity_count_by_type" in canon
        # temp_world has entities, so these should be populated
        assert len(canon["all_entities"]) >= 1

    def test_additional_context_passthrough(self, temp_world):
        """Caller-supplied additional_context should be passed through."""
        og = OptionGenerator(temp_world)
        result = og.generate_options(
            step_number=7,
            context={"user_preference": "I like storms"},
        )
        assert result["additional_context"]["user_preference"] == "I like storms"

    def test_generation_summary(self, temp_world):
        """get_generation_summary should return a human-readable string."""
        og = OptionGenerator(temp_world)
        summary = og.get_generation_summary(7)
        assert isinstance(summary, str)
        assert "7" in summary

    def test_record_choice_returns_record(self, temp_world):
        """record_choice should return the history record dict."""
        og = OptionGenerator(temp_world)
        record = og.record_choice(
            step_number=7,
            chosen_option_id="opt-b",
            rationale="Interesting direction",
        )
        assert record["step_number"] == 7
        assert record["chosen_option_id"] == "opt-b"
        assert "timestamp" in record
