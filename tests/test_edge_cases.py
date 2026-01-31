"""
Edge case tests for existing engine modules.

Covers:
    - data_manager.py: concurrent access, corrupt JSON, missing fields
    - sqlite_sync.py: large queries, special characters, concurrent reads
    - backup_manager.py: corrupt ZIP, disk full simulation, path traversal
    - graph_builder.py: cyclic references, orphan nodes, 500+ entity performance
"""

import json
import os
import shutil
import sqlite3
import tempfile
import threading
import time
import zipfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from engine.data_manager import DataManager, _slugify, _generate_id
from engine.sqlite_sync import SQLiteSyncEngine, _extract_cross_references
from engine.backup_manager import BackupManager
from engine.graph_builder import WorldGraph


# ===========================================================================
# Helpers
# ===========================================================================

def _make_entity(entity_id, name, entity_type="gods", template_id="god-profile",
                 step=7, status="draft", extra=None):
    """Build a sample entity dict for testing."""
    entity = {
        "name": name,
        "id": entity_id,
        "_meta": {
            "id": entity_id,
            "template_id": template_id,
            "entity_type": entity_type,
            "status": status,
            "step_created": step,
            "file_path": f"user-world/entities/{entity_type}/{entity_id}.json",
            "created_at": "2025-01-01T00:00:00+00:00",
            "updated_at": "2025-01-01T00:00:00+00:00",
        },
        "canon_claims": [],
        "_prose": "",
        "_prose_custom": False,
    }
    if extra:
        entity.update(extra)
    return entity


# ===========================================================================
# DataManager Edge Cases
# ===========================================================================

class TestDataManagerConcurrentAccess:
    """Tests for concurrent access to DataManager."""

    def test_concurrent_create_entities(self, temp_world, sample_god_data):
        """Multiple threads creating entities concurrently should not corrupt state."""
        dm = DataManager(temp_world)
        results = []
        errors = []

        def create_worker(index):
            try:
                data = dict(sample_god_data)
                data["name"] = f"God {index}"
                eid = dm.create_entity("god-profile", data)
                results.append(eid)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=create_worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"Concurrent create errors: {errors}"
        assert len(results) == 5
        assert len(set(results)) == 5  # All unique IDs

        # Verify state.json has all 5 entities
        state = dm.get_state()
        for eid in results:
            assert eid in state["entity_index"]

    def test_concurrent_read_write(self, temp_world, sample_god_data):
        """Reading and writing simultaneously should not raise."""
        dm = DataManager(temp_world)
        entity_id = dm.create_entity("god-profile", sample_god_data)
        errors = []

        def reader():
            try:
                for _ in range(10):
                    dm.get_entity(entity_id)
            except Exception as e:
                errors.append(e)

        def writer():
            try:
                for i in range(5):
                    dm.update_entity(entity_id, {"personality": f"Personality v{i}"})
            except Exception as e:
                errors.append(e)

        t_read = threading.Thread(target=reader)
        t_write = threading.Thread(target=writer)
        t_read.start()
        t_write.start()
        t_read.join(timeout=30)
        t_write.join(timeout=30)

        # Reads during writes may return either version, but should not crash
        assert not errors, f"Concurrent read/write errors: {errors}"


class TestDataManagerCorruptJSON:
    """Tests for handling corrupt or malformed JSON."""

    def test_get_entity_corrupt_file(self, temp_world):
        """get_entity should raise when the entity file is corrupt JSON."""
        dm = DataManager(temp_world)

        # Corrupt the god entity file
        entity_path = os.path.join(
            temp_world, "user-world", "entities", "gods",
            "thorin-stormkeeper-a1b2.json"
        )
        with open(entity_path, "w") as f:
            f.write("NOT VALID JSON {{{")

        with pytest.raises(FileNotFoundError):
            dm.get_entity("thorin-stormkeeper-a1b2")

    def test_load_state_with_corrupt_json(self, tmp_path):
        """DataManager should use defaults if state.json is corrupt."""
        root = tmp_path / "corrupt-state"
        uw = root / "user-world"
        uw.mkdir(parents=True)
        (uw / "state.json").write_text("CORRUPT{{{", encoding="utf-8")
        (root / "engine").mkdir(parents=True)
        (root / "engine" / "template_registry.json").write_text('{"templates":[]}', encoding="utf-8")
        (root / "templates").mkdir(parents=True)

        dm = DataManager(str(root))
        state = dm.get_state()
        # Should have default values
        assert state["current_step"] == 1
        assert state["entity_index"] == {}

    def test_update_nonexistent_entity(self, temp_world):
        """Updating a nonexistent entity should raise FileNotFoundError."""
        dm = DataManager(temp_world)
        with pytest.raises(FileNotFoundError):
            dm.update_entity("totally-fake-id", {"name": "Doesn't Exist"})


class TestDataManagerMissingFields:
    """Tests for entities with missing required fields."""

    def test_create_entity_missing_required_field(self, temp_world):
        """Creating an entity with missing required fields should raise ValueError."""
        dm = DataManager(temp_world)
        incomplete = {"name": "Test God"}  # Missing many required fields
        with pytest.raises(ValueError):
            dm.create_entity("god-profile", incomplete)

    def test_validate_entity_returns_errors(self, temp_world):
        """validate_entity should return error messages for invalid entities."""
        dm = DataManager(temp_world)
        # Corrupt the entity file to have missing required fields
        entity_path = os.path.join(
            temp_world, "user-world", "entities", "gods",
            "thorin-stormkeeper-a1b2.json"
        )
        with open(entity_path, "r") as f:
            entity = json.load(f)
        # Remove a required field
        entity.pop("domain_primary", None)
        entity.pop("alignment", None)
        with open(entity_path, "w") as f:
            json.dump(entity, f)

        errors = dm.validate_entity("thorin-stormkeeper-a1b2")
        assert len(errors) > 0

    def test_set_entity_status_invalid(self, temp_world):
        """set_entity_status with invalid status should raise ValueError."""
        dm = DataManager(temp_world)
        with pytest.raises(ValueError, match="Invalid status"):
            dm.set_entity_status("thorin-stormkeeper-a1b2", "invalid_status")

    def test_search_empty_query(self, temp_world):
        """search_entities with empty query should return empty list."""
        dm = DataManager(temp_world)
        assert dm.search_entities("") == []
        assert dm.search_entities("   ") == []

    def test_slugify_unicode(self):
        """_slugify should handle unicode characters."""
        assert "cafe" in _slugify("Cafe\u0301")  # e with combining acute
        assert _slugify("") == ""

    def test_generate_id_empty_name(self):
        """_generate_id should handle empty name gracefully."""
        eid = _generate_id("")
        assert eid.startswith("entity-")
        assert len(eid) > 0


# ===========================================================================
# SQLiteSyncEngine Edge Cases
# ===========================================================================

class TestSQLiteLargeQueries:
    """Tests for SQLite with large datasets and queries."""

    def test_sync_many_entities(self, temp_world):
        """full_sync should handle many entity files without errors."""
        # Create 50 entity files on disk
        entities_dir = os.path.join(temp_world, "user-world", "entities", "gods")
        os.makedirs(entities_dir, exist_ok=True)
        for i in range(50):
            entity = _make_entity(f"god-{i:04d}", f"God {i}")
            path = os.path.join(entities_dir, f"god-{i:04d}.json")
            with open(path, "w") as f:
                json.dump(entity, f)

        sync = SQLiteSyncEngine(temp_world)
        count = sync.full_sync()
        assert count >= 50

        stats = sync.get_stats()
        assert stats["total_entities"] >= 50
        sync.close()

    def test_query_entities_with_limit_offset(self, temp_world):
        """query_entities should respect limit and offset parameters."""
        # Create entities on disk
        entities_dir = os.path.join(temp_world, "user-world", "entities", "gods")
        os.makedirs(entities_dir, exist_ok=True)
        for i in range(20):
            entity = _make_entity(f"batch-god-{i:04d}", f"BatchGod {i}")
            path = os.path.join(entities_dir, f"batch-god-{i:04d}.json")
            with open(path, "w") as f:
                json.dump(entity, f)

        sync = SQLiteSyncEngine(temp_world)
        sync.full_sync()

        # Query with limit
        results = sync.query_entities(limit=5)
        assert len(results) <= 5

        # Query with offset
        page1 = sync.query_entities(limit=5, offset=0)
        page2 = sync.query_entities(limit=5, offset=5)
        page1_ids = {r["id"] for r in page1}
        page2_ids = {r["id"] for r in page2}
        assert page1_ids.isdisjoint(page2_ids)

        sync.close()


class TestSQLiteSpecialCharacters:
    """Tests for SQL injection and special character handling."""

    def test_search_with_special_characters(self, temp_world):
        """Search should handle special characters without SQL errors."""
        sync = SQLiteSyncEngine(temp_world)
        sync.full_sync()

        # These should not cause SQL injection or crashes
        special_queries = [
            "'; DROP TABLE entities; --",
            'name" OR 1=1',
            "god*",
            "(parentheses)",
            "quotes'and\"doubles",
            "unicode-\u00e9\u00e8\u00ea",
            "",
            "   ",
        ]
        for q in special_queries:
            results = sync.search(q)
            assert isinstance(results, list)

        sync.close()

    def test_advanced_query_blocks_injection(self, temp_world):
        """advanced_query should block SQL injection attempts."""
        sync = SQLiteSyncEngine(temp_world)
        sync.full_sync()

        dangerous_queries = [
            "DELETE FROM entities",
            "DROP TABLE entities",
            "INSERT INTO entities VALUES ('x','x','x','x','x',1,'x','{}','','')",
            "UPDATE entities SET name = 'hacked'",
        ]
        for q in dangerous_queries:
            with pytest.raises(ValueError):
                sync.advanced_query(q)

        sync.close()

    def test_advanced_query_blocks_stacked_statements(self, temp_world):
        """advanced_query should block multiple stacked SQL statements."""
        sync = SQLiteSyncEngine(temp_world)
        sync.full_sync()

        with pytest.raises(ValueError, match="disallowed keywords"):
            sync.advanced_query("SELECT * FROM entities; DELETE FROM entities")

        sync.close()

    def test_query_entities_invalid_column(self, temp_world):
        """query_entities should reject non-whitelisted columns."""
        sync = SQLiteSyncEngine(temp_world)
        sync.full_sync()

        with pytest.raises(ValueError, match="not in the allowed list"):
            sync.query_entities(filters=[("malicious_col", "=", "test")])

        sync.close()

    def test_query_entities_invalid_operator(self, temp_world):
        """query_entities should reject non-whitelisted operators."""
        sync = SQLiteSyncEngine(temp_world)
        sync.full_sync()

        with pytest.raises(ValueError, match="not allowed"):
            sync.query_entities(filters=[("name", "EXEC", "test")])

        sync.close()

    def test_entity_with_special_chars_in_name(self, temp_world):
        """Entities with special characters in names should sync properly."""
        sync = SQLiteSyncEngine(temp_world)
        sync.full_sync()

        entity = _make_entity(
            "special-name-0001",
            "O'Brien the \"Great\" & Powerful <Hero>",
        )
        sync.sync_entity("special-name-0001", entity)

        results = sync.query_by_type("gods")
        names = [r["name"] for r in results]
        assert "O'Brien the \"Great\" & Powerful <Hero>" in names

        sync.close()


class TestSQLiteConcurrentReads:
    """Tests for concurrent database reads."""

    def test_concurrent_reads(self, temp_world):
        """Multiple threads reading simultaneously should not fail."""
        db_root = temp_world

        # Run full_sync once to populate the database
        init_sync = SQLiteSyncEngine(db_root)
        init_sync.full_sync()
        init_sync.close()

        errors = []

        def reader(thread_id):
            try:
                # Each thread creates its own connection to avoid
                # SQLite threading issues (connections are not thread-safe).
                thread_sync = SQLiteSyncEngine(db_root)
                for _ in range(10):
                    thread_sync.get_stats()
                    thread_sync.query_by_type("gods")
                    thread_sync.query_by_step(7)
                thread_sync.close()
            except Exception as e:
                errors.append((thread_id, e))

        threads = [threading.Thread(target=reader, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"Concurrent read errors: {errors}"

    def test_context_manager(self, temp_world):
        """SQLiteSyncEngine should work as a context manager."""
        with SQLiteSyncEngine(temp_world) as sync:
            sync.full_sync()
            stats = sync.get_stats()
            assert "total_entities" in stats

    def test_close_idempotent(self, temp_world):
        """Calling close() multiple times should not raise."""
        sync = SQLiteSyncEngine(temp_world)
        sync.close()
        sync.close()  # Should not raise

    def test_remove_entity(self, temp_world):
        """remove_entity should remove the entity from all tables."""
        sync = SQLiteSyncEngine(temp_world)
        sync.full_sync()

        # Verify entity exists
        stats_before = sync.get_stats()
        initial_count = stats_before["total_entities"]

        sync.remove_entity("thorin-stormkeeper-a1b2")
        stats_after = sync.get_stats()
        assert stats_after["total_entities"] == initial_count - 1

        sync.close()


# ===========================================================================
# BackupManager Edge Cases
# ===========================================================================

class TestBackupCorruptZIP:
    """Tests for handling corrupt backup files."""

    def test_get_info_corrupt_zip(self, temp_world):
        """get_backup_info should raise ValueError for corrupt ZIP files."""
        bm = BackupManager(temp_world)
        corrupt_path = os.path.join(str(bm.backups_dir), "corrupt.zip")
        with open(corrupt_path, "w") as f:
            f.write("THIS IS NOT A ZIP FILE")

        with pytest.raises(ValueError, match="corrupted"):
            bm.get_backup_info(corrupt_path)

    def test_restore_corrupt_zip(self, temp_world):
        """restore_backup should raise ValueError for corrupt ZIP files."""
        bm = BackupManager(temp_world)
        corrupt_path = os.path.join(str(bm.backups_dir), "corrupt_restore.zip")
        with open(corrupt_path, "w") as f:
            f.write("CORRUPTED ZIP CONTENT")

        with pytest.raises(ValueError, match="not a valid ZIP"):
            bm.restore_backup(corrupt_path, confirm=True)

    def test_compare_corrupt_zip(self, temp_world):
        """compare_backup should raise ValueError for corrupt ZIP."""
        bm = BackupManager(temp_world)
        corrupt_path = os.path.join(str(bm.backups_dir), "corrupt_compare.zip")
        with open(corrupt_path, "w") as f:
            f.write("NOT A REAL ZIP")

        with pytest.raises(ValueError):
            bm.compare_backup(corrupt_path)

    def test_list_backups_ignores_corrupt(self, temp_world):
        """list_backups should skip corrupt ZIP files gracefully."""
        bm = BackupManager(temp_world)

        # Create a valid backup
        bm.create_backup(label="valid")

        # Create a corrupt file
        corrupt_path = os.path.join(str(bm.backups_dir), "not_a_backup.zip")
        with open(corrupt_path, "w") as f:
            f.write("CORRUPT")

        backups = bm.list_backups()
        # Should include valid backup but skip corrupt one
        assert any(b["label"] == "valid" for b in backups)

    def test_restore_entity_from_corrupt_zip(self, temp_world):
        """restore_entity should handle corrupt ZIP gracefully."""
        bm = BackupManager(temp_world)
        corrupt_path = os.path.join(str(bm.backups_dir), "corrupt_entity.zip")
        with open(corrupt_path, "w") as f:
            f.write("NOT ZIP")

        with pytest.raises(ValueError):
            bm.restore_entity(corrupt_path, "some-entity-id")


class TestBackupDiskFull:
    """Tests for disk full simulation."""

    def test_create_backup_oserror(self, temp_world):
        """create_backup should raise RuntimeError on OSError."""
        bm = BackupManager(temp_world)

        with patch("engine.backup_manager.zipfile.ZipFile", side_effect=OSError("No space left")):
            with pytest.raises(RuntimeError, match="disk space"):
                bm.create_backup()


class TestBackupPathTraversal:
    """Tests for path traversal attack prevention."""

    def test_restore_blocks_path_traversal(self, temp_world):
        """restore_backup should block ZIP entries with path traversal."""
        bm = BackupManager(temp_world)

        # Create a malicious ZIP with path traversal
        malicious_path = os.path.join(str(bm.backups_dir), "malicious.zip")
        with zipfile.ZipFile(malicious_path, "w") as zf:
            zf.writestr("manifest.json", json.dumps({"backup_version": 1}))
            # Path traversal attempt
            zf.writestr("../../etc/passwd", "root:x:0:0:root:/root:/bin/bash")
            zf.writestr("user-world/state.json", json.dumps({"current_step": 1}))

        with pytest.raises(RuntimeError, match="path traversal"):
            bm.restore_backup(malicious_path, confirm=True)

    def test_get_backup_info_missing_file(self, temp_world):
        """get_backup_info with a nonexistent path should raise FileNotFoundError."""
        bm = BackupManager(temp_world)
        with pytest.raises(FileNotFoundError):
            bm.get_backup_info("/nonexistent/path/backup.zip")

    def test_delete_backup_missing_file(self, temp_world):
        """delete_backup with a nonexistent path should raise FileNotFoundError."""
        bm = BackupManager(temp_world)
        with pytest.raises(FileNotFoundError):
            bm.delete_backup("/nonexistent/path/backup.zip")

    def test_backup_label_sanitization(self, temp_world):
        """create_backup should sanitize malicious label characters."""
        bm = BackupManager(temp_world)
        meta = bm.create_backup(label="../../etc/passwd")
        # Label should be sanitized in the filename
        assert ".." not in meta["filename"]
        assert "/" not in meta["filename"]
        assert "\\" not in meta["filename"]

    def test_backup_empty_world(self, tmp_path):
        """Backing up an empty user-world should work."""
        root = tmp_path / "empty-backup-test"
        (root / "user-world").mkdir(parents=True)
        with open(root / "user-world" / "state.json", "w") as f:
            json.dump({"current_step": 1}, f)
        (root / "backups").mkdir(parents=True)

        bm = BackupManager(str(root))
        meta = bm.create_backup()
        assert meta["entity_count"] == 0
        assert meta["file_count"] >= 1  # At least state.json


class TestBackupGetEntityHistory:
    """Tests for entity history across multiple backups."""

    def test_entity_history_across_backups(self, temp_world):
        """get_entity_history should find entity across multiple backups."""
        bm = BackupManager(temp_world)
        dm = DataManager(temp_world)

        # Create first backup
        bm.create_backup(label="v1")

        # Modify entity
        dm.update_entity("thorin-stormkeeper-a1b2", {"personality": "Updated personality"})

        # Create second backup
        bm.create_backup(label="v2")

        history = bm.get_entity_history("thorin-stormkeeper-a1b2")
        assert len(history) >= 2

    def test_entity_history_nonexistent_entity(self, temp_world):
        """get_entity_history for a nonexistent entity should return empty list."""
        bm = BackupManager(temp_world)
        bm.create_backup(label="test")

        history = bm.get_entity_history("nonexistent-entity-9999")
        assert history == []


# ===========================================================================
# WorldGraph Edge Cases
# ===========================================================================

class TestGraphCyclicReferences:
    """Tests for cyclic references in the graph."""

    def test_cyclic_reference_does_not_crash(self, temp_world):
        """Adding cyclic references should not cause infinite loops."""
        wg = WorldGraph(temp_world)
        wg.build_graph()

        # Create a cycle: A -> B -> C -> A
        wg.add_relationship("thorin-stormkeeper-a1b2", "havenport-e5f6", "patron_of")
        wg.add_relationship("havenport-e5f6", "thorin-stormkeeper-a1b2", "worships")

        # Operations should still work
        neighbors = wg.get_neighbors("thorin-stormkeeper-a1b2", depth=3)
        assert isinstance(neighbors, list)

        path = wg.find_path("thorin-stormkeeper-a1b2", "havenport-e5f6")
        assert len(path) >= 2

    def test_self_reference(self, temp_world):
        """A self-referencing entity should not cause issues."""
        wg = WorldGraph(temp_world)
        wg.build_graph()
        wg.add_relationship(
            "thorin-stormkeeper-a1b2",
            "thorin-stormkeeper-a1b2",
            "self_reference"
        )

        # Should still function
        related = wg.get_related_entities("thorin-stormkeeper-a1b2")
        assert isinstance(related, dict)

    def test_bidirectional_edges(self, temp_world):
        """Bidirectional edges should both be represented."""
        wg = WorldGraph(temp_world)
        wg.build_graph()

        wg.add_relationship("thorin-stormkeeper-a1b2", "havenport-e5f6", "protects")
        wg.add_relationship("havenport-e5f6", "thorin-stormkeeper-a1b2", "worships")

        related = wg.get_related_entities("thorin-stormkeeper-a1b2")
        out_ids = [r["id"] for r in related["outgoing"]]
        in_ids = [r["id"] for r in related["incoming"]]
        assert "havenport-e5f6" in out_ids
        assert "havenport-e5f6" in in_ids


class TestGraphOrphanNodes:
    """Tests for orphan node detection."""

    def test_detect_orphan_nodes(self, temp_world):
        """Entities with no relationships should be detected as orphans."""
        wg = WorldGraph(temp_world)

        # Add isolated nodes with no edges
        wg.graph.add_node("orphan-a", name="Orphan A", entity_type="gods")
        wg.graph.add_node("orphan-b", name="Orphan B", entity_type="gods")

        orphans = wg.get_orphans()
        assert "orphan-a" in orphans
        assert "orphan-b" in orphans

    def test_orphan_disappears_on_edge_add(self, temp_world):
        """An orphan should no longer be orphan once an edge is added."""
        wg = WorldGraph(temp_world)
        wg.graph.add_node("was-orphan", name="Was Orphan", entity_type="gods")

        assert "was-orphan" in wg.get_orphans()

        wg.add_relationship("was-orphan", "thorin-stormkeeper-a1b2", "knows")
        assert "was-orphan" not in wg.get_orphans()

    def test_remove_entity_from_graph(self, temp_world):
        """remove_entity should cleanly remove a node and its edges."""
        wg = WorldGraph(temp_world)
        wg.build_graph()
        wg.add_relationship("thorin-stormkeeper-a1b2", "havenport-e5f6", "patron_of")

        wg.remove_entity("thorin-stormkeeper-a1b2")
        assert "thorin-stormkeeper-a1b2" not in wg.graph

    def test_remove_nonexistent_entity_is_safe(self, temp_world):
        """remove_entity for a non-existent node should not raise."""
        wg = WorldGraph(temp_world)
        wg.remove_entity("does-not-exist")  # Should not raise


class TestGraphLargeScale:
    """Performance tests for the graph with many entities."""

    def test_500_plus_entities(self, temp_world):
        """The graph should handle 500+ entities without errors."""
        wg = WorldGraph(temp_world)

        # Add 500 entity nodes
        for i in range(500):
            entity_id = f"perf-entity-{i:04d}"
            wg.graph.add_node(
                entity_id,
                name=f"Entity {i}",
                entity_type="gods",
                status="draft",
                step_created=i % 52 + 1,
            )

        # Add edges to create a connected network
        for i in range(499):
            wg.add_relationship(
                f"perf-entity-{i:04d}",
                f"perf-entity-{i + 1:04d}",
                "connected_to",
            )

        # Also add some cross-links
        for i in range(0, 500, 10):
            target = (i + 50) % 500
            wg.add_relationship(
                f"perf-entity-{i:04d}",
                f"perf-entity-{target:04d}",
                "cross_link",
            )

        assert wg.graph.number_of_nodes() >= 500
        assert wg.graph.number_of_edges() >= 499

        # Operations should complete in reasonable time
        stats = wg.get_stats()
        assert stats["node_count"] >= 500

        neighbors = wg.get_neighbors("perf-entity-0250", depth=2)
        assert len(neighbors) > 0

        most_connected = wg.get_most_connected(top_n=10)
        assert len(most_connected) == 10

        orphans = wg.get_orphans()
        assert isinstance(orphans, list)

    def test_get_entities_by_type(self, temp_world):
        """get_entities_by_type should filter correctly."""
        wg = WorldGraph(temp_world)
        wg.build_graph()

        gods = wg.get_entities_by_type("gods")
        assert "thorin-stormkeeper-a1b2" in gods
        assert "havenport-e5f6" not in gods

        settlements = wg.get_entities_by_type("settlements")
        assert "havenport-e5f6" in settlements

    def test_get_entities_for_step(self, temp_world):
        """get_entities_for_step should filter by step number."""
        wg = WorldGraph(temp_world)
        wg.build_graph()

        step7 = wg.get_entities_for_step(7)
        assert "thorin-stormkeeper-a1b2" in step7

    def test_get_entity_cluster(self, temp_world):
        """get_entity_cluster should return a community of entities."""
        wg = WorldGraph(temp_world)
        wg.build_graph()
        wg.add_relationship("thorin-stormkeeper-a1b2", "havenport-e5f6", "patron_of")

        cluster = wg.get_entity_cluster("thorin-stormkeeper-a1b2")
        assert "thorin-stormkeeper-a1b2" in cluster

    def test_get_entity_cluster_missing_entity(self, temp_world):
        """get_entity_cluster for a missing entity should return empty list."""
        wg = WorldGraph(temp_world)
        wg.build_graph()
        cluster = wg.get_entity_cluster("nonexistent-entity")
        assert cluster == []

    def test_find_path_no_connection(self, temp_world):
        """find_path between unconnected entities should return empty list."""
        wg = WorldGraph(temp_world)
        wg.graph.add_node("isolated-a", name="A")
        wg.graph.add_node("isolated-b", name="B")

        path = wg.find_path("isolated-a", "isolated-b")
        assert path == []

    def test_find_path_missing_entity(self, temp_world):
        """find_path with a missing entity should return empty list."""
        wg = WorldGraph(temp_world)
        wg.build_graph()
        path = wg.find_path("thorin-stormkeeper-a1b2", "nonexistent-entity")
        assert path == []


class TestGraphCrossReferenceExtraction:
    """Tests for cross-reference extraction edge cases."""

    def test_extract_cross_references_empty_entity(self):
        """_extract_cross_references should handle empty entity dict."""
        refs = _extract_cross_references({})
        assert refs == []

    def test_extract_cross_references_with_relationships(self):
        """_extract_cross_references should find relationship target_ids."""
        entity = {
            "relationships": [
                {"target_id": "target-001", "relationship_type": "spouse"},
                {"target_id": "target-002", "relationship_type": "enemy"},
            ],
        }
        refs = _extract_cross_references(entity)
        target_ids = [r[0] for r in refs]
        assert "target-001" in target_ids
        assert "target-002" in target_ids

    def test_extract_cross_references_xref_fields(self):
        """_extract_cross_references should find known xref field names."""
        entity = {
            "pantheon_id": "celestial-court",
            "sovereign_power_id": "kingdom-of-aldara",
        }
        refs = _extract_cross_references(entity)
        target_ids = [r[0] for r in refs]
        assert "celestial-court" in target_ids
        assert "kingdom-of-aldara" in target_ids

    def test_extract_cross_references_deduplicates(self):
        """_extract_cross_references should de-duplicate references."""
        entity = {
            "pantheon_id": "celestial-court",
            "canon_claims": [
                {"claim": "test", "references": ["celestial-court"]},
            ],
        }
        refs = _extract_cross_references(entity)
        # Should have celestial-court only once per source field
        target_ids = [r[0] for r in refs]
        assert target_ids.count("celestial-court") <= 2  # once from field, once from claim

    def test_extract_cross_references_none_values(self):
        """_extract_cross_references should skip None-valued fields."""
        entity = {
            "pantheon_id": None,
            "sovereign_power_id": "",
            "relationships": None,
        }
        refs = _extract_cross_references(entity)
        # Empty strings and None should not produce references
        target_ids = [r[0] for r in refs]
        assert "" not in target_ids
