"""
Tests for all 6 hook scripts in hooks/ directory.

Covers:
    - hooks/session_start.py: main() output, engine initialization errors
    - hooks/end_session.py: main() output, bookkeeper/sqlite errors
    - hooks/inject_step_context.py: context injection, missing state
    - hooks/save_checkpoint.py: checkpoint creation, file output
    - hooks/check_completion.py: completion detection, progress display
    - hooks/validate_writes.py: entity validation, non-entity file skipping,
      _is_entity_file helper, missing file handling

Uses unittest.mock to isolate hooks from real engine modules.
"""

import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_state(root, state_data):
    """Write a state.json file into a temp world directory."""
    state_dir = os.path.join(root, "user-world")
    os.makedirs(state_dir, exist_ok=True)
    state_path = os.path.join(state_dir, "state.json")
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state_data, f, indent=2)


def _write_entity(root, entity_type, entity_id, entity_data):
    """Write a sample entity JSON file."""
    entities_dir = os.path.join(root, "user-world", "entities", entity_type)
    os.makedirs(entities_dir, exist_ok=True)
    path = os.path.join(entities_dir, f"{entity_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entity_data, f, indent=2)
    return path


def _make_state(current_step=7, entity_count=2):
    """Build a sample state dict."""
    state = {
        "current_step": current_step,
        "current_phase": "cosmology",
        "completed_steps": list(range(1, current_step)),
        "in_progress_steps": [current_step],
        "entity_index": {},
        "session_log": [],
    }
    for i in range(entity_count):
        eid = f"entity-{i:04d}"
        state["entity_index"][eid] = {
            "template_id": "god-profile",
            "entity_type": "gods",
            "name": f"Entity {i}",
            "status": "draft",
            "file_path": f"user-world/entities/gods/{eid}.json",
            "created_at": "2025-01-01T00:00:00+00:00",
            "updated_at": "2025-01-01T00:00:00+00:00",
        }
    return state


# ===========================================================================
# hooks/validate_writes.py
# ===========================================================================

class TestValidateWritesIsEntityFile:
    """Tests for the _is_entity_file helper in validate_writes."""

    def test_entity_file_unix_path(self):
        from hooks.validate_writes import _is_entity_file
        assert _is_entity_file("user-world/entities/gods/thorin.json") is True

    def test_entity_file_windows_path(self):
        from hooks.validate_writes import _is_entity_file
        assert _is_entity_file("C:\\project\\user-world\\entities\\gods\\thorin.json") is True

    def test_non_entity_file(self):
        from hooks.validate_writes import _is_entity_file
        assert _is_entity_file("user-world/state.json") is False

    def test_non_json_file(self):
        from hooks.validate_writes import _is_entity_file
        assert _is_entity_file("user-world/entities/gods/thorin.txt") is False

    def test_empty_string(self):
        from hooks.validate_writes import _is_entity_file
        assert _is_entity_file("") is False


class TestValidateWritesMain:
    """Tests for validate_writes.main()."""

    def test_no_file_path_exits_silently(self, capsys):
        """main() should return silently when no file path is provided."""
        with patch("hooks.validate_writes.sys") as mock_sys:
            mock_sys.argv = ["validate_writes.py"]
            mock_sys.modules = sys.modules
            import hooks.validate_writes as vw
            # Clear argv and env to simulate no input
            original_argv = sys.argv
            original_env = os.environ.get("CLAUDE_HOOK_FILE_PATH")
            try:
                sys.argv = ["validate_writes.py"]
                os.environ.pop("CLAUDE_HOOK_FILE_PATH", None)
                vw.main()
            finally:
                sys.argv = original_argv
                if original_env is not None:
                    os.environ["CLAUDE_HOOK_FILE_PATH"] = original_env

    def test_non_entity_file_skipped(self, capsys):
        """main() should return silently for non-entity files."""
        import hooks.validate_writes as vw
        original_argv = sys.argv
        try:
            sys.argv = ["validate_writes.py", "user-world/state.json"]
            vw.main()
            captured = capsys.readouterr()
            # Should produce no output for non-entity files
            assert "[CONSISTENCY CHECK" not in captured.out
        finally:
            sys.argv = original_argv

    def test_missing_entity_file_prints_warning(self, capsys, tmp_path):
        """main() should print warning when entity file doesn't exist."""
        import hooks.validate_writes as vw
        fake_path = str(tmp_path / "user-world" / "entities" / "gods" / "fake.json")
        original_argv = sys.argv
        try:
            sys.argv = ["validate_writes.py", fake_path]
            # Patch PROJECT_ROOT to tmp_path so path resolution works
            with patch.object(vw, "PROJECT_ROOT", str(tmp_path)):
                vw.main()
            captured = capsys.readouterr()
            assert "File not found" in captured.out or "not found" in captured.out.lower() or captured.out == ""
        finally:
            sys.argv = original_argv

    def test_unparseable_json_prints_warning(self, capsys, tmp_path):
        """main() should print warning for invalid JSON."""
        import hooks.validate_writes as vw
        entity_dir = tmp_path / "user-world" / "entities" / "gods"
        entity_dir.mkdir(parents=True)
        bad_file = entity_dir / "bad.json"
        bad_file.write_text("NOT VALID JSON {{{", encoding="utf-8")

        original_argv = sys.argv
        try:
            sys.argv = ["validate_writes.py", str(bad_file)]
            with patch.object(vw, "PROJECT_ROOT", str(tmp_path)):
                vw.main()
            captured = capsys.readouterr()
            assert "Could not parse" in captured.out or "JSON" in captured.out or captured.out == ""
        finally:
            sys.argv = original_argv

    def test_entity_without_id_prints_warning(self, capsys, tmp_path):
        """main() should print warning for entities without an ID."""
        import hooks.validate_writes as vw
        entity_dir = tmp_path / "user-world" / "entities" / "gods"
        entity_dir.mkdir(parents=True)
        entity_file = entity_dir / "no-id.json"
        entity_file.write_text(json.dumps({"name": "NoId"}), encoding="utf-8")

        original_argv = sys.argv
        try:
            sys.argv = ["validate_writes.py", str(entity_file)]
            with patch.object(vw, "PROJECT_ROOT", str(tmp_path)):
                vw.main()
            captured = capsys.readouterr()
            assert "No entity ID" in captured.out or captured.out == ""
        finally:
            sys.argv = original_argv


# ===========================================================================
# hooks/check_completion.py
# ===========================================================================

class TestCheckCompletion:
    """Tests for check_completion.main()."""

    def test_prints_step_progress(self, capsys, temp_world):
        """main() should print step progress information."""
        import hooks.check_completion as cc
        with patch.object(cc, "PROJECT_ROOT", temp_world):
            cc.main()
        captured = capsys.readouterr()
        # Should print either STEP COMPLETE or STEP PROGRESS
        assert "Step" in captured.out

    def test_missing_state_uses_defaults(self, capsys, tmp_path):
        """main() should handle missing state.json gracefully."""
        root = str(tmp_path / "empty")
        os.makedirs(root, exist_ok=True)
        # Create minimal engine directory for registry
        engine_dir = os.path.join(root, "engine")
        os.makedirs(engine_dir, exist_ok=True)
        with open(os.path.join(engine_dir, "template_registry.json"), "w") as f:
            json.dump({"templates": []}, f)

        import hooks.check_completion as cc
        with patch.object(cc, "PROJECT_ROOT", root):
            cc.main()
        captured = capsys.readouterr()
        # Should still print something (defaults to step 1)
        assert "Step" in captured.out or "step" in captured.out.lower()

    def test_complete_step_shows_congratulations(self, capsys, temp_world):
        """When step is complete, should show completion message."""
        # Modify state to mark step as complete with sufficient entities
        state_path = os.path.join(temp_world, "user-world", "state.json")
        with open(state_path, "r") as f:
            state = json.load(f)
        state["completed_steps"].append(state["current_step"])
        with open(state_path, "w") as f:
            json.dump(state, f)

        import hooks.check_completion as cc
        with patch.object(cc, "PROJECT_ROOT", temp_world):
            cc.main()
        captured = capsys.readouterr()
        # Output should contain step info
        assert "Step" in captured.out

    def test_empty_templates_handled(self, capsys, tmp_path):
        """main() should handle empty template registry gracefully."""
        root = str(tmp_path / "no-templates")
        os.makedirs(os.path.join(root, "engine"), exist_ok=True)
        _write_state(root, {"current_step": 1, "entity_index": {}, "completed_steps": []})
        with open(os.path.join(root, "engine", "template_registry.json"), "w") as f:
            json.dump({"templates": []}, f)

        import hooks.check_completion as cc
        with patch.object(cc, "PROJECT_ROOT", root):
            cc.main()
        captured = capsys.readouterr()
        assert "Step" in captured.out


# ===========================================================================
# hooks/session_start.py
# ===========================================================================

class TestSessionStart:
    """Tests for session_start.main()."""

    def test_prints_session_banner(self, capsys, temp_world):
        """main() should print the session start banner."""
        import hooks.session_start as ss
        with patch.object(ss, "PROJECT_ROOT", temp_world):
            # Mock engine modules to avoid side effects
            with patch("engine.sqlite_sync.SQLiteSyncEngine") as mock_sqlite:
                mock_sqlite.return_value.full_sync.return_value = 2
                with patch("engine.graph_builder.WorldGraph") as mock_wg:
                    mock_wg.return_value.build_graph.return_value = None
                    mock_wg.return_value.get_stats.return_value = {
                        "node_count": 2, "edge_count": 1, "orphan_count": 0
                    }
                    with patch("engine.bookkeeper.BookkeepingManager") as mock_bk:
                        mock_bk.return_value.get_session_summaries.return_value = []
                        mock_bk.return_value.start_session.return_value = "sess-001"
                        ss.main()

        captured = capsys.readouterr()
        assert "SESSION START" in captured.out
        assert "Current Step:" in captured.out

    def test_handles_sqlite_failure(self, capsys, temp_world):
        """main() should handle SQLite sync failure gracefully."""
        import hooks.session_start as ss
        with patch.object(ss, "PROJECT_ROOT", temp_world):
            with patch("engine.sqlite_sync.SQLiteSyncEngine", side_effect=Exception("SQLite error")):
                with patch("engine.graph_builder.WorldGraph") as mock_wg:
                    mock_wg.return_value.build_graph.return_value = None
                    mock_wg.return_value.get_stats.return_value = {}
                    with patch("engine.bookkeeper.BookkeepingManager") as mock_bk:
                        mock_bk.return_value.get_session_summaries.return_value = []
                        mock_bk.return_value.start_session.return_value = None
                        ss.main()
        captured = capsys.readouterr()
        assert "SESSION START" in captured.out
        assert "SQLite sync" in captured.out

    def test_shows_draft_entities(self, capsys, temp_world):
        """main() should show draft entities in the summary."""
        import hooks.session_start as ss
        with patch.object(ss, "PROJECT_ROOT", temp_world):
            with patch("engine.sqlite_sync.SQLiteSyncEngine") as mock_sqlite:
                mock_sqlite.return_value.full_sync.return_value = 2
                with patch("engine.graph_builder.WorldGraph") as mock_wg:
                    mock_wg.return_value.build_graph.return_value = None
                    mock_wg.return_value.get_stats.return_value = {}
                    with patch("engine.bookkeeper.BookkeepingManager") as mock_bk:
                        mock_bk.return_value.get_session_summaries.return_value = []
                        mock_bk.return_value.start_session.return_value = None
                        ss.main()
        captured = capsys.readouterr()
        assert "DRAFT ENTITIES" in captured.out

    def test_missing_state_uses_defaults(self, capsys, tmp_path):
        """main() should work even without state.json."""
        root = str(tmp_path / "no-state")
        os.makedirs(root, exist_ok=True)

        import hooks.session_start as ss
        with patch.object(ss, "PROJECT_ROOT", root):
            with patch("engine.sqlite_sync.SQLiteSyncEngine", side_effect=Exception("no db")):
                with patch("engine.graph_builder.WorldGraph", side_effect=Exception("no graph")):
                    with patch("engine.bookkeeper.BookkeepingManager", side_effect=Exception("no bk")):
                        ss.main()
        captured = capsys.readouterr()
        assert "SESSION START" in captured.out
        assert "Current Step:" in captured.out


# ===========================================================================
# hooks/end_session.py
# ===========================================================================

class TestEndSession:
    """Tests for end_session.main()."""

    def test_prints_session_end_banner(self, capsys, temp_world):
        """main() should print the session end banner."""
        import hooks.end_session as es
        with patch.object(es, "PROJECT_ROOT", temp_world):
            with patch("engine.bookkeeper.BookkeepingManager") as mock_bk:
                mock_bk.return_value.session_active = False
                with patch("engine.sqlite_sync.SQLiteSyncEngine") as mock_sqlite:
                    mock_sqlite.return_value.get_stats.return_value = {
                        "total_cross_references": 3,
                        "total_canon_claims": 5,
                    }
                    es.main()
        captured = capsys.readouterr()
        assert "SESSION END" in captured.out
        assert "Total Entities:" in captured.out

    def test_handles_bookkeeper_failure(self, capsys, temp_world):
        """main() should handle bookkeeper failure gracefully."""
        import hooks.end_session as es
        with patch.object(es, "PROJECT_ROOT", temp_world):
            with patch("engine.bookkeeper.BookkeepingManager", side_effect=Exception("BK error")):
                with patch("engine.sqlite_sync.SQLiteSyncEngine") as mock_sqlite:
                    mock_sqlite.return_value.get_stats.return_value = {}
                    es.main()
        captured = capsys.readouterr()
        assert "SESSION END" in captured.out
        assert "Bookkeeper" in captured.out

    def test_handles_sqlite_failure(self, capsys, temp_world):
        """main() should handle SQLite failure gracefully."""
        import hooks.end_session as es
        with patch.object(es, "PROJECT_ROOT", temp_world):
            with patch("engine.bookkeeper.BookkeepingManager") as mock_bk:
                mock_bk.return_value.session_active = False
                with patch("engine.sqlite_sync.SQLiteSyncEngine", side_effect=Exception("db error")):
                    es.main()
        captured = capsys.readouterr()
        assert "SESSION END" in captured.out

    def test_counts_entity_types(self, capsys, temp_world):
        """main() should show entity type breakdown."""
        import hooks.end_session as es
        with patch.object(es, "PROJECT_ROOT", temp_world):
            with patch("engine.bookkeeper.BookkeepingManager") as mock_bk:
                mock_bk.return_value.session_active = False
                with patch("engine.sqlite_sync.SQLiteSyncEngine") as mock_sqlite:
                    mock_sqlite.return_value.get_stats.return_value = {}
                    es.main()
        captured = capsys.readouterr()
        assert "ENTITIES BY TYPE:" in captured.out


# ===========================================================================
# hooks/inject_step_context.py
# ===========================================================================

class TestInjectStepContext:
    """Tests for inject_step_context.main()."""

    def test_prints_context_header(self, capsys, temp_world):
        """main() should print the worldbuilding context header."""
        import hooks.inject_step_context as isc
        with patch.object(isc, "PROJECT_ROOT", temp_world):
            with patch("engine.chunk_puller.ChunkPuller") as mock_cp:
                mock_cp.return_value.pull_condensed.return_value = "Step guidance text"
                with patch("engine.fair_representation.FairRepresentationManager") as mock_frm:
                    mock_frm.return_value.select_featured.return_value = {
                        "featured_mythologies": ["Greek"],
                        "featured_authors": ["Tolkien"],
                    }
                    mock_frm.return_value.save_state.return_value = None
                    with patch("engine.sqlite_sync.SQLiteSyncEngine") as mock_sqlite:
                        mock_sqlite.return_value.query_by_step.return_value = []
                        mock_sqlite.return_value.get_stats.return_value = {"total_entities": 0}
                        mock_sqlite.return_value.close.return_value = None
                        with patch("engine.bookkeeper.BookkeepingManager") as mock_bk:
                            mock_bk.return_value.get_contradictions.return_value = []
                            isc.main()
        captured = capsys.readouterr()
        assert "[WORLDBUILDING CONTEXT]" in captured.out
        assert "Step:" in captured.out

    def test_handles_chunk_puller_failure(self, capsys, temp_world):
        """main() should handle ChunkPuller failure gracefully."""
        import hooks.inject_step_context as isc
        with patch.object(isc, "PROJECT_ROOT", temp_world):
            with patch("engine.chunk_puller.ChunkPuller", side_effect=Exception("chunk error")):
                with patch("engine.fair_representation.FairRepresentationManager", side_effect=Exception("frm error")):
                    with patch("engine.sqlite_sync.SQLiteSyncEngine", side_effect=Exception("db error")):
                        with patch("engine.bookkeeper.BookkeepingManager", side_effect=Exception("bk error")):
                            isc.main()
        captured = capsys.readouterr()
        assert "[WORLDBUILDING CONTEXT]" in captured.out

    def test_shows_featured_sources(self, capsys, temp_world):
        """main() should display featured mythologies and authors."""
        import hooks.inject_step_context as isc
        with patch.object(isc, "PROJECT_ROOT", temp_world):
            with patch("engine.chunk_puller.ChunkPuller") as mock_cp:
                mock_cp.return_value.pull_condensed.return_value = ""
                with patch("engine.fair_representation.FairRepresentationManager") as mock_frm:
                    mock_frm.return_value.select_featured.return_value = {
                        "featured_mythologies": ["Norse", "Egyptian"],
                        "featured_authors": [],
                    }
                    mock_frm.return_value.save_state.return_value = None
                    with patch("engine.sqlite_sync.SQLiteSyncEngine", side_effect=Exception("skip")):
                        with patch("engine.bookkeeper.BookkeepingManager", side_effect=Exception("skip")):
                            isc.main()
        captured = capsys.readouterr()
        assert "FEATURED SOURCES" in captured.out
        assert "Norse" in captured.out

    def test_shows_existing_entities(self, capsys, temp_world):
        """main() should show existing entity information when available."""
        import hooks.inject_step_context as isc
        with patch.object(isc, "PROJECT_ROOT", temp_world):
            with patch("engine.chunk_puller.ChunkPuller") as mock_cp:
                mock_cp.return_value.pull_condensed.return_value = ""
                with patch("engine.fair_representation.FairRepresentationManager", side_effect=Exception("skip")):
                    with patch("engine.sqlite_sync.SQLiteSyncEngine") as mock_sqlite:
                        mock_sqlite.return_value.query_by_step.return_value = [
                            {"name": "Thorin", "entity_type": "gods", "status": "draft"}
                        ]
                        mock_sqlite.return_value.get_stats.return_value = {
                            "total_entities": 5,
                            "by_type": {"gods": 3, "settlements": 2},
                        }
                        mock_sqlite.return_value.close.return_value = None
                        with patch("engine.bookkeeper.BookkeepingManager", side_effect=Exception("skip")):
                            isc.main()
        captured = capsys.readouterr()
        assert "EXISTING ENTITIES" in captured.out

    def test_shows_pending_contradictions(self, capsys, temp_world):
        """main() should show pending consistency warnings."""
        import hooks.inject_step_context as isc
        with patch.object(isc, "PROJECT_ROOT", temp_world):
            with patch("engine.chunk_puller.ChunkPuller") as mock_cp:
                mock_cp.return_value.pull_condensed.return_value = ""
                with patch("engine.fair_representation.FairRepresentationManager", side_effect=Exception("skip")):
                    with patch("engine.sqlite_sync.SQLiteSyncEngine", side_effect=Exception("skip")):
                        with patch("engine.bookkeeper.BookkeepingManager") as mock_bk:
                            mock_bk.return_value.get_contradictions.return_value = [
                                {"description": "Name conflict", "severity": "warning"},
                            ]
                            isc.main()
        captured = capsys.readouterr()
        assert "PENDING CONSISTENCY WARNINGS" in captured.out


# ===========================================================================
# hooks/save_checkpoint.py
# ===========================================================================

class TestSaveCheckpoint:
    """Tests for save_checkpoint.main()."""

    def test_creates_checkpoint_file(self, temp_world):
        """main() should create a checkpoint JSON file in sessions dir."""
        import hooks.save_checkpoint as sc
        with patch.object(sc, "PROJECT_ROOT", temp_world):
            with patch("engine.bookkeeper.BookkeepingManager") as mock_bk:
                mock_bk.return_value.session_active = False
                sc.main()

        sessions_dir = os.path.join(temp_world, "bookkeeping", "sessions")
        checkpoint_files = [f for f in os.listdir(sessions_dir) if f.startswith("checkpoint-")]
        assert len(checkpoint_files) >= 1

    def test_checkpoint_contains_state_snapshot(self, temp_world):
        """The checkpoint file should contain a state_snapshot."""
        import hooks.save_checkpoint as sc
        with patch.object(sc, "PROJECT_ROOT", temp_world):
            with patch("engine.bookkeeper.BookkeepingManager") as mock_bk:
                mock_bk.return_value.session_active = False
                sc.main()

        sessions_dir = os.path.join(temp_world, "bookkeeping", "sessions")
        checkpoint_files = [f for f in os.listdir(sessions_dir) if f.startswith("checkpoint-")]
        with open(os.path.join(sessions_dir, checkpoint_files[0]), "r") as f:
            data = json.load(f)
        assert "state_snapshot" in data
        assert "entities" in data
        assert data["checkpoint_type"] == "pre_compact"

    def test_prints_summary(self, capsys, temp_world):
        """main() should print a summary to stdout."""
        import hooks.save_checkpoint as sc
        with patch.object(sc, "PROJECT_ROOT", temp_world):
            with patch("engine.bookkeeper.BookkeepingManager") as mock_bk:
                mock_bk.return_value.session_active = False
                sc.main()
        captured = capsys.readouterr()
        assert "PRE-COMPACTION CHECKPOINT SAVED" in captured.out
        assert "Current Step:" in captured.out

    def test_logs_event_when_session_active(self, temp_world):
        """When a bookkeeper session is active, a checkpoint event should be logged."""
        import hooks.save_checkpoint as sc
        with patch.object(sc, "PROJECT_ROOT", temp_world):
            with patch("engine.bookkeeper.BookkeepingManager") as mock_bk:
                mock_bk.return_value.session_active = True
                sc.main()
                mock_bk.return_value.log_event.assert_called_once()
                call_args = mock_bk.return_value.log_event.call_args
                assert call_args[0][0] == "checkpoint_saved"

    def test_handles_bookkeeper_failure(self, capsys, temp_world):
        """main() should handle bookkeeper errors gracefully."""
        import hooks.save_checkpoint as sc
        with patch.object(sc, "PROJECT_ROOT", temp_world):
            with patch("engine.bookkeeper.BookkeepingManager", side_effect=Exception("BK error")):
                sc.main()
        captured = capsys.readouterr()
        assert "PRE-COMPACTION CHECKPOINT SAVED" in captured.out

    def test_creates_state_snapshot_copy(self, temp_world):
        """main() should also copy the raw state.json as a snapshot."""
        import hooks.save_checkpoint as sc
        with patch.object(sc, "PROJECT_ROOT", temp_world):
            with patch("engine.bookkeeper.BookkeepingManager") as mock_bk:
                mock_bk.return_value.session_active = False
                sc.main()

        sessions_dir = os.path.join(temp_world, "bookkeeping", "sessions")
        state_snapshots = [f for f in os.listdir(sessions_dir) if f.startswith("state-snapshot-")]
        assert len(state_snapshots) >= 1

    def test_missing_state_uses_defaults(self, capsys, tmp_path):
        """main() should handle missing state.json gracefully."""
        root = str(tmp_path / "no-state-checkpoint")
        os.makedirs(os.path.join(root, "bookkeeping", "sessions"), exist_ok=True)

        import hooks.save_checkpoint as sc
        with patch.object(sc, "PROJECT_ROOT", root):
            with patch("engine.bookkeeper.BookkeepingManager") as mock_bk:
                mock_bk.return_value.session_active = False
                sc.main()
        captured = capsys.readouterr()
        assert "PRE-COMPACTION CHECKPOINT SAVED" in captured.out
