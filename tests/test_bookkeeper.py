"""
Tests for engine/bookkeeper.py -- BookkeepingManager event logging and sessions.

Validates:
    - Event logging for all 10 event types
    - Session start/end lifecycle
    - Derived index rebuilding
    - Session summary generation
"""

import json
import os
import pytest

from engine.bookkeeper import BookkeepingManager


# ---------------------------------------------------------------------------
# Event Logging
# ---------------------------------------------------------------------------

class TestEventLogging:
    """Tests that every event type can be recorded."""

    def test_record_session_started(self, tmp_path):
        """session_started event should be appended to the event log."""
        bm = BookkeepingManager(str(tmp_path / "bookkeeping"))
        sid = bm.start_session(focus="Testing session start")
        assert sid is not None
        assert sid.startswith("session-")

    def test_record_decision(self, tmp_path):
        """record_decision should create a decision_made event."""
        bm = BookkeepingManager(str(tmp_path / "bookkeeping"))
        bm.start_session()
        event = bm.record_decision(
            step_id="step-07",
            question="Which pantheon structure?",
            options=[
                {"name": "Olympian", "description": "Greek-style hierarchy"},
                {"name": "Elemental", "description": "Element-based domains"},
            ],
            chosen="Olympian",
            rationale="Familiar structure for readers",
        )
        assert event["event_type"] == BookkeepingManager.EVENT_DECISION_MADE
        assert event["data"]["chosen"] == "Olympian"
        assert "Elemental" in event["data"]["rejected"]

    def test_record_entity_created(self, tmp_path):
        """record_entity_created should create a draft_created event."""
        bm = BookkeepingManager(str(tmp_path / "bookkeeping"))
        bm.start_session()
        event = bm.record_entity_created(
            entity_id="thorin-a1b2",
            entity_type="gods",
            file_path="user-world/entities/gods/thorin-a1b2.json",
        )
        assert event["event_type"] == BookkeepingManager.EVENT_DRAFT_CREATED
        assert event["data"]["entity_id"] == "thorin-a1b2"

    def test_record_status_change(self, tmp_path):
        """record_status_change should create a status_changed event."""
        bm = BookkeepingManager(str(tmp_path / "bookkeeping"))
        bm.start_session()
        event = bm.record_status_change(
            entity_id="thorin-a1b2",
            old_status="draft",
            new_status="canon",
            reason="Reviewed and approved",
        )
        assert event["event_type"] == BookkeepingManager.EVENT_STATUS_CHANGED
        assert event["data"]["new_status"] == "canon"

    def test_record_entity_revised(self, tmp_path):
        """record_entity_revised should create an entity_revised event."""
        bm = BookkeepingManager(str(tmp_path / "bookkeeping"))
        bm.start_session()
        event = bm.record_entity_revised(
            entity_id="thorin-a1b2",
            revision_number=1,
            change_summary="Changed domain from war to storms",
            reason="Better fits the narrative",
            snapshot_path="/snapshots/thorin-a1b2_v0.json",
        )
        assert event["event_type"] == BookkeepingManager.EVENT_ENTITY_REVISED
        assert event["data"]["revision_number"] == 1

    def test_record_cross_reference(self, tmp_path):
        """record_cross_reference should create a cross_reference_created event."""
        bm = BookkeepingManager(str(tmp_path / "bookkeeping"))
        bm.start_session()
        event = bm.record_cross_reference(
            source_id="thorin-a1b2",
            target_id="mira-c3d4",
            relationship_type="spouse",
            bidirectional=True,
        )
        assert event["event_type"] == BookkeepingManager.EVENT_CROSS_REFERENCE_CREATED
        assert event["data"]["bidirectional"] is True

    def test_record_contradiction(self, tmp_path):
        """record_contradiction should create a contradiction_found event."""
        bm = BookkeepingManager(str(tmp_path / "bookkeeping"))
        bm.start_session()
        event = bm.record_contradiction(
            entities=["thorin-a1b2", "kael-e5f6"],
            description="Both gods claim storms as primary domain",
            severity="warning",
        )
        assert event["event_type"] == BookkeepingManager.EVENT_CONTRADICTION_FOUND
        assert "contradiction" in event["data"]["contradiction_id"]

    def test_resolve_contradiction(self, tmp_path):
        """resolve_contradiction should create a contradiction_resolved event."""
        bm = BookkeepingManager(str(tmp_path / "bookkeeping"))
        bm.start_session()
        event = bm.resolve_contradiction(
            contradiction_id="contradiction-0001",
            resolution="Changed Kael's domain to wind",
            entities_modified=["kael-e5f6"],
        )
        assert event["event_type"] == BookkeepingManager.EVENT_CONTRADICTION_RESOLVED

    def test_record_step_change(self, tmp_path):
        """record_step_change should create a step_status_changed event."""
        bm = BookkeepingManager(str(tmp_path / "bookkeeping"))
        bm.start_session()
        event = bm.record_step_change(
            step_id="step-07",
            old_status="not_started",
            new_status="in_progress",
        )
        assert event["event_type"] == BookkeepingManager.EVENT_STEP_STATUS_CHANGED
        assert event["data"]["new_status"] == "in_progress"

    def test_session_ended_event(self, tmp_path):
        """end_session should record a session_ended event."""
        bm = BookkeepingManager(str(tmp_path / "bookkeeping"))
        bm.start_session(focus="Test session")
        result = bm.end_session(summary="Completed testing")
        # result is a path to the summary file
        assert result is not None


# ---------------------------------------------------------------------------
# Session Lifecycle
# ---------------------------------------------------------------------------

class TestSessionLifecycle:
    """Tests for session start/end flow."""

    def test_session_starts_inactive(self, tmp_path):
        """Before start_session, session_active should be False."""
        bm = BookkeepingManager(str(tmp_path / "bookkeeping"))
        assert bm.session_active is False
        assert bm.current_session_id is None

    def test_session_becomes_active(self, tmp_path):
        """After start_session, session_active should be True."""
        bm = BookkeepingManager(str(tmp_path / "bookkeeping"))
        bm.start_session()
        assert bm.session_active is True
        assert bm.current_session_id is not None

    def test_session_ends_cleanly(self, tmp_path):
        """After end_session, session_active should return to False."""
        bm = BookkeepingManager(str(tmp_path / "bookkeeping"))
        bm.start_session()
        bm.end_session(summary="Done")
        assert bm.session_active is False

    def test_end_session_without_start_returns_none(self, tmp_path):
        """Ending a session that was never started returns None."""
        bm = BookkeepingManager(str(tmp_path / "bookkeeping"))
        result = bm.end_session()
        assert result is None

    def test_session_numbers_increment(self, tmp_path):
        """Each new session should have a higher session number."""
        bm = BookkeepingManager(str(tmp_path / "bookkeeping"))

        sid1 = bm.start_session()
        bm.end_session()

        sid2 = bm.start_session()
        bm.end_session()

        # Extract numbers from session IDs
        num1 = int(sid1.split("-")[1])
        num2 = int(sid2.split("-")[1])
        assert num2 > num1


# ---------------------------------------------------------------------------
# Derived Index Rebuilding
# ---------------------------------------------------------------------------

class TestIndexRebuilding:
    """Tests for rebuild_indexes from the event log."""

    def test_rebuild_decisions(self, tmp_path):
        """After recording a decision and rebuilding, the decisions index should contain it."""
        bm = BookkeepingManager(str(tmp_path / "bookkeeping"))
        bm.start_session()
        bm.record_decision(
            step_id="step-07",
            question="How many gods?",
            options=[{"name": "Few", "description": "5 or fewer"}],
            chosen="Few",
        )
        bm.end_session()  # end_session calls rebuild_indexes

        decisions = bm.get_decisions()
        assert len(decisions) >= 1
        assert decisions[0]["chosen"] == "Few"

    def test_rebuild_entity_registry(self, tmp_path):
        """After recording entity creation and rebuilding, the registry should contain the entity."""
        bm = BookkeepingManager(str(tmp_path / "bookkeeping"))
        bm.start_session()
        bm.record_entity_created("test-entity-1234", "gods", "/path/to/file.json")
        bm.end_session()

        index = bm._read_json(bm.entity_registry_index)
        assert "test-entity-1234" in index.get("entities", {})

    def test_rebuild_cross_references(self, tmp_path):
        """After recording cross-references and rebuilding, the index should contain them."""
        bm = BookkeepingManager(str(tmp_path / "bookkeeping"))
        bm.start_session()
        bm.record_cross_reference("a-1111", "b-2222", "ally")
        bm.end_session()

        index = bm._read_json(bm.cross_references_index)
        xrefs = index.get("cross_references", [])
        assert len(xrefs) >= 1
        assert xrefs[0]["source_id"] == "a-1111"

    def test_rebuild_contradictions(self, tmp_path):
        """After recording and resolving a contradiction, both states should be in the index."""
        bm = BookkeepingManager(str(tmp_path / "bookkeeping"))
        bm.start_session()
        bm.record_contradiction(["a", "b"], "Conflict!", "critical")
        bm.resolve_contradiction("contradiction-0001", "Fixed it", ["a"])
        bm.end_session()

        contradictions = bm.get_contradictions()
        assert len(contradictions) >= 1
        resolved = bm.get_contradictions(status="resolved")
        assert len(resolved) >= 1


# ---------------------------------------------------------------------------
# Session Summary
# ---------------------------------------------------------------------------

class TestSessionSummary:
    """Tests for session summary generation."""

    def test_summary_file_created(self, tmp_path):
        """end_session should create a markdown summary file."""
        bm = BookkeepingManager(str(tmp_path / "bookkeeping"))
        bm.start_session(focus="Pantheon design")
        bm.record_decision(
            step_id="step-07",
            question="Pantheon type?",
            options=[{"name": "Olympian", "description": "Hierarchy"}],
            chosen="Olympian",
        )
        summary_path = bm.end_session(summary="Designed the pantheon structure")

        assert summary_path is not None
        assert summary_path.exists()

        content = summary_path.read_text(encoding="utf-8")
        assert "Session" in content
        assert "Decisions Made" in content

    def test_summary_contains_session_data(self, tmp_path):
        """The summary should contain decisions and entities from the session."""
        bm = BookkeepingManager(str(tmp_path / "bookkeeping"))
        bm.start_session()
        bm.record_entity_created("god-test-0001", "gods", "/path.json")
        bm.record_decision(
            step_id="step-07",
            question="Q?",
            options=[{"name": "A", "description": "d"}],
            chosen="A",
        )
        summary_path = bm.end_session(summary="Test run")

        content = summary_path.read_text(encoding="utf-8")
        assert "god-test-0001" in content

    def test_get_session_summaries(self, tmp_path):
        """get_session_summaries should return recent summaries."""
        bm = BookkeepingManager(str(tmp_path / "bookkeeping"))
        bm.start_session()
        bm.end_session(summary="First session")
        bm.start_session()
        bm.end_session(summary="Second session")

        summaries = bm.get_session_summaries(last_n=2)
        assert len(summaries) >= 1
        assert "content" in summaries[0]
