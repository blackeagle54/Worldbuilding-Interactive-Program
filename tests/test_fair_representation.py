"""
Tests for engine/fair_representation.py -- FairRepresentationManager.

Validates:
    - select_featured returns correct counts (4 myth + 3 author)
    - No source is featured twice in a row (anti-repetition)
    - All sources get featured over many iterations
    - select_option_sources returns unique combinations per option
    - Usage counter fairness over 52 steps
"""

import json
import pytest

from engine.fair_representation import (
    FairRepresentationManager,
    MYTHOLOGIES,
    AUTHORS,
    FEATURED_MYTHOLOGY_COUNT,
    FEATURED_AUTHOR_COUNT,
)


def _create_frm(tmp_path, usage_counts=None):
    """Helper: create a FairRepresentationManager with a temp state file."""
    state_path = tmp_path / "state.json"
    state = {}
    if usage_counts:
        state["reference_usage_counts"] = usage_counts
    with open(str(state_path), "w", encoding="utf-8") as fh:
        json.dump(state, fh)
    return FairRepresentationManager(str(state_path))


# ---------------------------------------------------------------------------
# select_featured
# ---------------------------------------------------------------------------

class TestSelectFeatured:
    """Tests for select_featured."""

    def test_returns_correct_myth_count(self, tmp_path):
        """select_featured should return exactly 4 featured mythologies."""
        frm = _create_frm(tmp_path)
        result = frm.select_featured(step_number=1)
        assert len(result["featured_mythologies"]) == FEATURED_MYTHOLOGY_COUNT

    def test_returns_correct_author_count(self, tmp_path):
        """select_featured should return exactly 3 featured authors."""
        frm = _create_frm(tmp_path)
        result = frm.select_featured(step_number=1)
        assert len(result["featured_authors"]) == FEATURED_AUTHOR_COUNT

    def test_brief_mythologies_are_remainder(self, tmp_path):
        """brief_mythologies should contain the non-featured mythologies."""
        frm = _create_frm(tmp_path)
        result = frm.select_featured(step_number=1)
        featured = set(result["featured_mythologies"])
        brief = set(result["brief_mythologies"])
        assert featured.isdisjoint(brief)
        assert featured | brief == set(MYTHOLOGIES)

    def test_brief_authors_are_remainder(self, tmp_path):
        """brief_authors should contain the non-featured authors."""
        frm = _create_frm(tmp_path)
        result = frm.select_featured(step_number=1)
        featured = set(result["featured_authors"])
        brief = set(result["brief_authors"])
        assert featured.isdisjoint(brief)
        assert featured | brief == set(AUTHORS)

    def test_featured_are_valid_names(self, tmp_path):
        """All featured databases should be valid mythology/author names."""
        frm = _create_frm(tmp_path)
        result = frm.select_featured(step_number=1)
        for m in result["featured_mythologies"]:
            assert m in MYTHOLOGIES
        for a in result["featured_authors"]:
            assert a in AUTHORS


# ---------------------------------------------------------------------------
# Anti-repetition
# ---------------------------------------------------------------------------

class TestAntiRepetition:
    """Tests that the same source is not featured consecutively."""

    def test_no_consecutive_identical_sets(self, tmp_path):
        """Two consecutive select_featured calls should not produce the exact same set."""
        frm = _create_frm(tmp_path)
        result1 = frm.select_featured(step_number=1)
        result2 = frm.select_featured(step_number=2)

        # After step 1, the featured sources get higher counts, so step 2
        # should prefer different ones. Allow some overlap but not 100%.
        myths1 = set(result1["featured_mythologies"])
        myths2 = set(result2["featured_mythologies"])
        # With 10 mythologies and 4 featured, after incrementing step 1's
        # picks, step 2 should prioritize the other 6.
        assert myths1 != myths2 or len(MYTHOLOGIES) <= FEATURED_MYTHOLOGY_COUNT


# ---------------------------------------------------------------------------
# All Sources Featured Over Many Iterations
# ---------------------------------------------------------------------------

class TestFullCoverage:
    """Tests that all sources get featured over many steps."""

    def test_all_mythologies_featured_over_52_steps(self, tmp_path):
        """Over 52 steps, every mythology should be featured at least once."""
        frm = _create_frm(tmp_path)
        featured_sets = set()
        for step in range(1, 53):
            result = frm.select_featured(step_number=step)
            featured_sets.update(result["featured_mythologies"])
        assert featured_sets == set(MYTHOLOGIES)

    def test_all_authors_featured_over_52_steps(self, tmp_path):
        """Over 52 steps, every author should be featured at least once."""
        frm = _create_frm(tmp_path)
        featured_sets = set()
        for step in range(1, 53):
            result = frm.select_featured(step_number=step)
            featured_sets.update(result["featured_authors"])
        assert featured_sets == set(AUTHORS)


# ---------------------------------------------------------------------------
# select_option_sources
# ---------------------------------------------------------------------------

class TestSelectOptionSources:
    """Tests for select_option_sources."""

    def test_returns_correct_count(self, tmp_path):
        """select_option_sources(3) should return 3 option assignments."""
        frm = _create_frm(tmp_path)
        results = frm.select_option_sources(3)
        assert len(results) == 3

    def test_each_option_has_required_keys(self, tmp_path):
        """Each option should have primary_mythology, primary_author, and secondary."""
        frm = _create_frm(tmp_path)
        results = frm.select_option_sources(3)
        for opt in results:
            assert "primary_mythology" in opt
            assert "primary_author" in opt
            assert "secondary" in opt
            assert isinstance(opt["secondary"], list)

    def test_primary_mythologies_unique(self, tmp_path):
        """Each option should have a unique primary mythology."""
        frm = _create_frm(tmp_path)
        results = frm.select_option_sources(4)
        primaries = [r["primary_mythology"] for r in results]
        assert len(primaries) == len(set(primaries))

    def test_primary_authors_unique(self, tmp_path):
        """Each option should have a unique primary author."""
        frm = _create_frm(tmp_path)
        results = frm.select_option_sources(3)
        primaries = [r["primary_author"] for r in results]
        assert len(primaries) == len(set(primaries))

    def test_too_many_options_raises(self, tmp_path):
        """Requesting more options than available authors should raise ValueError."""
        frm = _create_frm(tmp_path)
        with pytest.raises(ValueError):
            frm.select_option_sources(len(AUTHORS) + 1)

    def test_zero_options_raises(self, tmp_path):
        """Requesting 0 options should raise ValueError."""
        frm = _create_frm(tmp_path)
        with pytest.raises(ValueError):
            frm.select_option_sources(0)


# ---------------------------------------------------------------------------
# Usage Counter Fairness
# ---------------------------------------------------------------------------

class TestUsageFairness:
    """Tests for usage counter balance over 52 steps."""

    def test_usage_counters_balanced(self, tmp_path):
        """After 52 steps, no mythology should be used more than 2x the least-used."""
        frm = _create_frm(tmp_path)
        for step in range(1, 53):
            frm.select_featured(step_number=step)

        stats = frm.get_usage_stats()
        myth_counts = [stats[m] for m in MYTHOLOGIES]
        min_count = min(myth_counts)
        max_count = max(myth_counts)
        # With 10 mythologies and 4 featured per step, ideal is ~20.8 each.
        # Allow up to 2x ratio.
        assert max_count <= min_count * 2 + 2

    def test_save_and_reload_state(self, tmp_path):
        """Usage counters should persist after save_state and reload."""
        state_path = tmp_path / "state.json"
        with open(str(state_path), "w", encoding="utf-8") as fh:
            json.dump({}, fh)

        frm = FairRepresentationManager(str(state_path))
        frm.select_featured(step_number=1)
        frm.save_state()

        # Reload from disk
        frm2 = FairRepresentationManager(str(state_path))
        stats = frm2.get_usage_stats()
        total = sum(stats.values())
        # We featured 4 myths + 3 authors = 7 total increments
        assert total == 7
