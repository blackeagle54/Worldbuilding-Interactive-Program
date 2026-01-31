"""
Tests for app/services/prompt_builder.py -- build_system_prompt and phase flavors.
"""

import pytest

from app.services.prompt_builder import (
    PROMPT_VERSION,
    _ANTI_DRIFT,
    _CONSTRAINTS,
    _PHASE_FLAVORS,
    _SYSTEM_ROLE,
    build_system_prompt,
)


class TestBuildSystemPrompt:
    def test_returns_string(self):
        result = build_system_prompt(
            step_number=7,
            step_title="Create Individual God Profiles",
            phase_name="cosmology",
        )
        assert isinstance(result, str)
        assert len(result) > 100

    def test_contains_step_info(self):
        result = build_system_prompt(
            step_number=7,
            step_title="Create Individual God Profiles",
            phase_name="cosmology",
        )
        assert "7/52" in result
        assert "Create Individual God Profiles" in result

    def test_contains_constraints_and_anti_drift(self):
        result = build_system_prompt(
            step_number=1,
            step_title="Define Scope",
            phase_name="foundation",
        )
        assert "CONSTRAINTS" in result
        assert "ANTI-DRIFT" in result

    def test_phase_flavor_included(self):
        result = build_system_prompt(
            step_number=6,
            step_title="Design Pantheon",
            phase_name="cosmology",
        )
        assert "divine" in result.lower() or "cosmic" in result.lower()

    def test_featured_sources_included(self):
        result = build_system_prompt(
            step_number=7,
            step_title="God Profiles",
            phase_name="cosmology",
            featured_sources={
                "featured_mythologies": ["Norse", "Greek"],
                "featured_authors": ["Tolkien"],
            },
        )
        assert "Norse" in result
        assert "Greek" in result
        assert "Tolkien" in result

    def test_condensed_guidance_included(self):
        result = build_system_prompt(
            step_number=7,
            step_title="God Profiles",
            phase_name="cosmology",
            condensed_guidance="Focus on personality and domain interplay.",
        )
        assert "Focus on personality" in result

    def test_entity_count_shown(self):
        result = build_system_prompt(
            step_number=10,
            step_title="Define Planet",
            phase_name="cosmology",
            entity_count=42,
        )
        assert "42" in result

    def test_prompt_version_included(self):
        result = build_system_prompt(
            step_number=1,
            step_title="Scope",
            phase_name="foundation",
        )
        assert PROMPT_VERSION in result


class TestPhaseFlavors:
    def test_all_expected_phases_have_flavors(self):
        expected = [
            "foundation", "cosmology", "land", "life", "civilization",
            "society", "supernatural", "history", "language", "travel",
            "finishing", "integration",
        ]
        for phase in expected:
            assert phase in _PHASE_FLAVORS, f"Missing flavor for phase: {phase}"
            assert len(_PHASE_FLAVORS[phase]) > 20

    def test_unknown_phase_produces_no_flavor(self):
        result = build_system_prompt(
            step_number=1,
            step_title="Test",
            phase_name="nonexistent_phase",
        )
        # Should still work, just without a phase flavor section
        assert "CONSTRAINTS" in result
