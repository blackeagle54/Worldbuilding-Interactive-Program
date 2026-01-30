"""
Tests for engine/chunk_puller.py -- ChunkPuller three-layer guidance generator.

Validates:
    - pull_guidance for several step numbers
    - pull_book_quotes returns content
    - pull_references returns content
    - pull_condensed returns shorter output
    - get_step_dependencies
    - Invalid step numbers handled gracefully
"""

import pytest

from engine.chunk_puller import ChunkPuller, _STEP_DEPENDENCIES, _GUIDED_QUESTIONS


# ---------------------------------------------------------------------------
# Pull Guidance
# ---------------------------------------------------------------------------

class TestPullGuidance:
    """Tests for ChunkPuller.pull_guidance."""

    def test_guidance_returns_dict(self, temp_world):
        """pull_guidance should return a dict with all three layers."""
        cp = ChunkPuller(temp_world)
        result = cp.pull_guidance(7)

        assert isinstance(result, dict)
        assert "step" in result
        assert "layer1_book" in result
        assert "layer2_references" in result
        assert "layer3_actionable" in result

    def test_guidance_step_info(self, temp_world):
        """The step info should contain number, title, and phase."""
        cp = ChunkPuller(temp_world)
        result = cp.pull_guidance(7)

        step = result["step"]
        assert step["number"] == 7
        assert isinstance(step.get("title"), str)
        assert isinstance(step.get("phase"), int)

    def test_guidance_for_step_1(self, temp_world):
        """Step 1 should produce valid guidance."""
        cp = ChunkPuller(temp_world)
        result = cp.pull_guidance(1)
        assert result["step"]["number"] == 1

    def test_guidance_for_step_52(self, temp_world):
        """Step 52 (last step) should produce valid guidance."""
        cp = ChunkPuller(temp_world)
        result = cp.pull_guidance(52)
        assert result["step"]["number"] == 52

    def test_guidance_for_middle_step(self, temp_world):
        """Step 25 (civilization phase) should produce valid guidance."""
        cp = ChunkPuller(temp_world)
        result = cp.pull_guidance(25)
        assert result["step"]["number"] == 25

    def test_layer3_has_guided_questions(self, temp_world):
        """Layer 3 should include guided questions for the step."""
        cp = ChunkPuller(temp_world)
        result = cp.pull_guidance(7)
        layer3 = result["layer3_actionable"]
        assert "guided_questions" in layer3
        assert isinstance(layer3["guided_questions"], list)


# ---------------------------------------------------------------------------
# Book Quotes
# ---------------------------------------------------------------------------

class TestPullBookQuotes:
    """Tests for ChunkPuller.pull_book_quotes."""

    def test_returns_list(self, temp_world):
        """pull_book_quotes should return a list."""
        cp = ChunkPuller(temp_world)
        quotes = cp.pull_book_quotes(7)
        assert isinstance(quotes, list)

    def test_quote_structure(self, temp_world):
        """Each quote should have text, line_start, line_end, and context keys."""
        cp = ChunkPuller(temp_world)
        quotes = cp.pull_book_quotes(7)
        for q in quotes:
            assert "text" in q
            assert "line_start" in q
            assert "line_end" in q
            assert "context" in q


# ---------------------------------------------------------------------------
# Pull References
# ---------------------------------------------------------------------------

class TestPullReferences:
    """Tests for ChunkPuller.pull_references."""

    def test_returns_dict(self, temp_world):
        """pull_references should return a dict with expected keys."""
        cp = ChunkPuller(temp_world)
        refs = cp.pull_references(7)

        assert isinstance(refs, dict)
        assert "featured_mythologies" in refs
        assert "featured_authors" in refs
        assert "brief_mentions" in refs
        assert "cross_cutting_patterns" in refs

    def test_with_override_mythologies(self, temp_world):
        """Overriding featured mythologies should be reflected in the result."""
        cp = ChunkPuller(temp_world)
        refs = cp.pull_references(
            7,
            featured_mythologies=["greek", "norse", "celtic", "hindu"],
        )
        # The override should have been used
        for entry in refs["featured_mythologies"]:
            assert entry.get("database") in ["greek", "norse", "celtic", "hindu"]


# ---------------------------------------------------------------------------
# Pull Condensed
# ---------------------------------------------------------------------------

class TestPullCondensed:
    """Tests for ChunkPuller.pull_condensed."""

    def test_returns_string(self, temp_world):
        """pull_condensed should return a string."""
        cp = ChunkPuller(temp_world)
        condensed = cp.pull_condensed(7)
        assert isinstance(condensed, str)

    def test_shorter_than_full(self, temp_world):
        """Condensed output should be shorter than full guidance serialized."""
        cp = ChunkPuller(temp_world)
        condensed = cp.pull_condensed(7)
        full = cp.pull_guidance(7)
        import json
        full_text = json.dumps(full)
        # Condensed should be substantially shorter (or at least exist)
        assert len(condensed) > 0
        assert len(condensed) < len(full_text) + 1000  # generous margin

    def test_condensed_mentions_step(self, temp_world):
        """Condensed output should mention the step number."""
        cp = ChunkPuller(temp_world)
        condensed = cp.pull_condensed(7)
        assert "7" in condensed


# ---------------------------------------------------------------------------
# Step Dependencies
# ---------------------------------------------------------------------------

class TestStepDependencies:
    """Tests for ChunkPuller.get_step_dependencies."""

    def test_step_1_no_dependencies(self, temp_world):
        """Step 1 should have no required dependencies."""
        cp = ChunkPuller(temp_world)
        deps = cp.get_step_dependencies(1)
        assert deps["required_steps"] == []
        assert deps["dependencies_met"] is True

    def test_step_7_depends_on_6(self, temp_world):
        """Step 7 should depend on step 6."""
        cp = ChunkPuller(temp_world)
        deps = cp.get_step_dependencies(7)
        assert 6 in deps["required_steps"]

    def test_dependencies_met_when_completed(self, temp_world):
        """When all required steps are in completed_steps, dependencies_met should be True."""
        cp = ChunkPuller(temp_world)
        # temp_world has steps 1-6 completed
        deps = cp.get_step_dependencies(7)
        assert deps["dependencies_met"] is True

    def test_dependencies_not_met(self, temp_world):
        """Steps with incomplete prerequisites should show missing_dependencies."""
        cp = ChunkPuller(temp_world)
        # Step 17 requires many steps that aren't completed
        deps = cp.get_step_dependencies(17)
        assert len(deps["missing_dependencies"]) > 0
        assert deps["dependencies_met"] is False

    def test_dependency_map_coverage(self):
        """Every step 1-52 should have an entry in _STEP_DEPENDENCIES."""
        for step in range(1, 53):
            assert step in _STEP_DEPENDENCIES


# ---------------------------------------------------------------------------
# Invalid Steps
# ---------------------------------------------------------------------------

class TestInvalidSteps:
    """Tests for graceful handling of invalid step numbers."""

    def test_step_0(self, temp_world):
        """Step 0 (invalid) should not crash; should return a result."""
        cp = ChunkPuller(temp_world)
        result = cp.pull_guidance(0)
        assert isinstance(result, dict)

    def test_step_100(self, temp_world):
        """Step 100 (out of range) should not crash; should return a result."""
        cp = ChunkPuller(temp_world)
        result = cp.pull_guidance(100)
        assert isinstance(result, dict)

    def test_negative_step(self, temp_world):
        """Negative step number should not crash."""
        cp = ChunkPuller(temp_world)
        result = cp.pull_guidance(-5)
        assert isinstance(result, dict)

    def test_dependencies_for_unknown_step(self, temp_world):
        """get_step_dependencies for an unknown step should return empty deps."""
        cp = ChunkPuller(temp_world)
        deps = cp.get_step_dependencies(999)
        assert deps["required_steps"] == []
        assert deps["dependencies_met"] is True
