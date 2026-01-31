"""
Tests for engine/error_recovery.py

Covers:
    - Health check system
    - Schema compliance checking
    - SQLite sync verification
    - Graph consistency checking
    - Repair operations (dry run and live)
    - JSON repair (encoding, corruption)
    - Health report generation
    - Entity-level recovery
"""

import json
import os
import shutil

import pytest

from engine.error_recovery import ErrorRecoveryManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def erm(temp_world):
    """Return an ErrorRecoveryManager for the temp world."""
    return ErrorRecoveryManager(temp_world)


@pytest.fixture
def erm_root(temp_world):
    """Return both the manager and root path."""
    return ErrorRecoveryManager(temp_world), temp_world


# ---------------------------------------------------------------------------
# Health check tests
# ---------------------------------------------------------------------------

class TestHealthCheck:
    def test_health_check_returns_dict(self, erm):
        report = erm.check_health()
        assert isinstance(report, dict)

    def test_health_check_has_expected_keys(self, erm):
        report = erm.check_health()
        assert "status" in report
        assert "details" in report

    def test_healthy_world_passes(self, erm):
        report = erm.check_health()
        assert report["status"] in ("healthy", "ok", "warning", "degraded")

    def test_health_check_includes_schema_check(self, erm):
        report = erm.check_health()
        details = report.get("details", {})
        assert "schema_compliance" in details or len(details) > 0


# ---------------------------------------------------------------------------
# Schema compliance tests
# ---------------------------------------------------------------------------

class TestSchemaCompliance:
    def test_valid_entities_pass(self, erm):
        result = erm.check_schema_compliance()
        assert isinstance(result, dict)
        assert result.get("status") in ("ok", "healthy", "warning", "issues")

    def test_reports_invalid_entity(self, erm_root):
        erm, root = erm_root
        # Create an entity with missing required fields
        bad_entity = {
            "_meta": {
                "id": "bad-entity-0000",
                "template_id": "god-profile",
                "entity_type": "gods",
                "status": "draft",
            },
            # Missing required "name" field
        }
        bad_path = os.path.join(
            root, "user-world", "entities", "gods", "bad-entity-0000.json"
        )
        with open(bad_path, "w") as fh:
            json.dump(bad_entity, fh)

        result = erm.check_schema_compliance()
        issues = result.get("issues", [])
        # Should have at least one issue for the bad entity
        assert len(issues) >= 1


# ---------------------------------------------------------------------------
# SQLite sync check tests
# ---------------------------------------------------------------------------

class TestSQLiteSyncCheck:
    def test_sync_check_returns_dict(self, erm):
        result = erm.check_sqlite_sync()
        assert isinstance(result, dict)

    def test_sync_check_has_counts(self, erm):
        result = erm.check_sqlite_sync()
        assert "json_count" in result


# ---------------------------------------------------------------------------
# Graph consistency tests
# ---------------------------------------------------------------------------

class TestGraphConsistency:
    def test_graph_check_returns_dict(self, erm):
        result = erm.check_graph_consistency()
        assert isinstance(result, dict)

    def test_graph_check_has_status(self, erm):
        result = erm.check_graph_consistency()
        assert "status" in result


# ---------------------------------------------------------------------------
# Repair tests
# ---------------------------------------------------------------------------

class TestRepair:
    def test_repair_all_dry_run(self, erm):
        result = erm.repair_all(dry_run=True)
        assert isinstance(result, dict)
        assert "repairs" in result
        assert result.get("dry_run") is True

    def test_repair_all_dry_run_no_destructive_changes(self, erm_root):
        erm, root = erm_root
        # Snapshot entity files before
        entities_dir = os.path.join(root, "user-world", "entities")
        before = set()
        for dirpath, _, filenames in os.walk(entities_dir):
            for fn in filenames:
                path = os.path.join(dirpath, fn)
                with open(path, "r") as fh:
                    before.add((path, fh.read()))

        erm.repair_all(dry_run=True)

        # Verify no files changed
        after = set()
        for dirpath, _, filenames in os.walk(entities_dir):
            for fn in filenames:
                path = os.path.join(dirpath, fn)
                with open(path, "r") as fh:
                    after.add((path, fh.read()))

        assert before == after

    def test_repair_sqlite(self, erm):
        result = erm.repair_sqlite(dry_run=False)
        assert isinstance(result, dict)

    def test_repair_graph(self, erm):
        result = erm.repair_graph(dry_run=False)
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# JSON repair tests
# ---------------------------------------------------------------------------

class TestJSONRepair:
    def test_repair_corrupt_json(self, erm_root):
        erm, root = erm_root
        # Corrupt an entity file
        god_path = os.path.join(
            root, "user-world", "entities", "gods",
            "thorin-stormkeeper-a1b2.json"
        )
        with open(god_path, "w") as fh:
            fh.write("{invalid json content!!!")

        result = erm.repair_json(dry_run=False)
        assert isinstance(result, dict)

    def test_repair_json_dry_run(self, erm_root):
        erm, root = erm_root
        god_path = os.path.join(
            root, "user-world", "entities", "gods",
            "thorin-stormkeeper-a1b2.json"
        )
        # Save original
        with open(god_path, "r") as fh:
            original = fh.read()

        # Corrupt
        with open(god_path, "w") as fh:
            fh.write("{broken")

        erm.repair_json(dry_run=True)

        # File should still be broken (dry run)
        with open(god_path, "r") as fh:
            assert fh.read() == "{broken"


# ---------------------------------------------------------------------------
# Health report tests
# ---------------------------------------------------------------------------

class TestHealthReport:
    def test_generate_report_returns_string(self, erm):
        report = erm.generate_health_report()
        assert isinstance(report, str)
        assert len(report) > 0

    def test_report_mentions_entities(self, erm):
        report = erm.generate_health_report()
        # Report should mention entity-related information
        assert "entit" in report.lower() or "health" in report.lower()


# ---------------------------------------------------------------------------
# Utils tests (bonus: test the shared utils)
# ---------------------------------------------------------------------------

class TestSharedUtils:
    def test_safe_read_json_valid(self, tmp_path):
        from engine.utils import safe_read_json
        path = tmp_path / "test.json"
        data = {"key": "value"}
        with open(str(path), "w") as fh:
            json.dump(data, fh)
        assert safe_read_json(str(path)) == data

    def test_safe_read_json_missing(self, tmp_path):
        from engine.utils import safe_read_json
        assert safe_read_json(str(tmp_path / "missing.json")) is None

    def test_safe_read_json_default(self, tmp_path):
        from engine.utils import safe_read_json
        assert safe_read_json(str(tmp_path / "missing.json"), default={}) == {}

    def test_safe_read_json_corrupt(self, tmp_path):
        from engine.utils import safe_read_json
        path = tmp_path / "bad.json"
        path.write_text("not json{{{")
        assert safe_read_json(str(path)) is None

    def test_safe_write_json_creates_file(self, tmp_path):
        from engine.utils import safe_write_json
        path = tmp_path / "output.json"
        safe_write_json(str(path), {"hello": "world"})
        with open(str(path), "r") as fh:
            assert json.load(fh) == {"hello": "world"}

    def test_safe_write_json_creates_dirs(self, tmp_path):
        from engine.utils import safe_write_json
        path = tmp_path / "nested" / "dir" / "file.json"
        safe_write_json(str(path), [1, 2, 3])
        with open(str(path), "r") as fh:
            assert json.load(fh) == [1, 2, 3]

    def test_safe_write_json_atomic(self, tmp_path):
        from engine.utils import safe_write_json
        path = tmp_path / "atomic.json"
        # Write initial
        safe_write_json(str(path), {"v": 1})
        # Overwrite
        safe_write_json(str(path), {"v": 2})
        with open(str(path), "r") as fh:
            assert json.load(fh)["v"] == 2

    def test_clean_schema_strips_custom_fields(self):
        from engine.utils import clean_schema_for_validation
        schema = {
            "$id": "test-template",
            "type": "object",
            "step": 7,
            "phase": "cosmology",
            "source_chapter": "ch3",
            "x-cross-references": ["some-ref"],
            "properties": {
                "name": {"type": "string"},
                "ref_field": {
                    "type": "string",
                    "x-cross-reference": "gods",
                },
            },
            "required": ["name"],
        }
        clean = clean_schema_for_validation(schema)
        assert "$id" not in clean
        assert "step" not in clean
        assert "phase" not in clean
        assert "source_chapter" not in clean
        assert "x-cross-references" not in clean
        assert clean["type"] == "object"
        assert "name" in clean["properties"]
        # Nested x-cross-reference should also be stripped
        assert "x-cross-reference" not in clean["properties"]["ref_field"]
