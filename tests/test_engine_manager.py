"""
Tests for engine/engine_manager.py -- EngineManager thread-safe singleton.

Covers:
    - Singleton pattern (get_instance, reset_instance)
    - Double-checked locking (thread safety)
    - Lazy loading of all subsystems
    - Per-module RLock isolation
    - with_lock and get_lock helpers
    - Shutdown sequence
    - Error handling (missing project_root, unknown module)
"""

import threading
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from engine.engine_manager import EngineManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_singleton():
    """Ensure every test starts with a clean singleton state."""
    EngineManager._instance = None
    yield
    EngineManager._instance = None


@pytest.fixture
def em(temp_world):
    """Return a fresh EngineManager instance for the temp world."""
    return EngineManager.get_instance(temp_world)


# ---------------------------------------------------------------------------
# Singleton Pattern
# ---------------------------------------------------------------------------

class TestSingleton:
    """Tests for the singleton pattern."""

    def test_get_instance_returns_same_object(self, temp_world):
        """get_instance should return the exact same object on repeated calls."""
        em1 = EngineManager.get_instance(temp_world)
        em2 = EngineManager.get_instance()
        assert em1 is em2

    def test_get_instance_ignores_second_root(self, temp_world, tmp_path):
        """Subsequent calls with a different project_root are ignored."""
        em1 = EngineManager.get_instance(temp_world)
        other_root = str(tmp_path / "other-project")
        em2 = EngineManager.get_instance(other_root)
        assert em1 is em2
        assert em2.root == Path(temp_world).resolve()

    def test_get_instance_requires_root_on_first_call(self):
        """get_instance should raise ValueError if no root is given on first call."""
        with pytest.raises(ValueError, match="project_root is required"):
            EngineManager.get_instance(None)

    def test_reset_instance_clears_singleton(self, temp_world):
        """reset_instance should clear the singleton so a new one can be created."""
        em1 = EngineManager.get_instance(temp_world)
        EngineManager.reset_instance()
        assert EngineManager._instance is None

    def test_reset_instance_on_none_is_safe(self):
        """reset_instance when no instance exists should not raise."""
        EngineManager.reset_instance()  # Should not raise

    def test_new_instance_after_reset(self, temp_world, tmp_path):
        """After reset, a new instance with a different root can be created."""
        em1 = EngineManager.get_instance(temp_world)
        old_root = em1.root
        EngineManager.reset_instance()

        new_root = tmp_path / "new-project"
        new_root.mkdir(parents=True)
        em2 = EngineManager.get_instance(str(new_root))
        assert em2.root != old_root
        assert em2.root == new_root.resolve()


# ---------------------------------------------------------------------------
# Thread Safety
# ---------------------------------------------------------------------------

class TestThreadSafety:
    """Tests for thread-safety and RLock usage."""

    def test_concurrent_get_instance_returns_same_object(self, temp_world):
        """Multiple threads calling get_instance simultaneously should all
        get the same instance."""
        results = []
        errors = []
        barrier = threading.Barrier(10)

        def worker():
            try:
                barrier.wait(timeout=5)
                instance = EngineManager.get_instance(temp_world)
                results.append(id(instance))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Threads raised errors: {errors}"
        assert len(set(results)) == 1, "All threads should get the same instance"

    def test_per_module_locks_are_independent(self, em):
        """Each module should have its own independent RLock."""
        lock_dm = em.get_lock("data_manager")
        lock_wg = em.get_lock("world_graph")
        assert lock_dm is not lock_wg

    def test_rlock_is_reentrant(self, em):
        """Module locks should be RLocks (reentrant) so the same thread
        can acquire them multiple times without deadlock."""
        lock = em.get_lock("data_manager")
        lock.acquire()
        try:
            # Should not deadlock on reentrant acquire
            lock.acquire()
            lock.release()
        finally:
            lock.release()

    def test_all_ten_modules_have_locks(self, em):
        """All 10 module names should have dedicated locks."""
        expected = {
            "data_manager", "world_graph", "chunk_puller",
            "option_generator", "consistency_checker", "sqlite_sync",
            "backup_manager", "bookkeeper", "fair_representation",
            "error_recovery",
        }
        assert set(em._locks.keys()) == expected


# ---------------------------------------------------------------------------
# Lazy Loading of Subsystems
# ---------------------------------------------------------------------------

class TestLazyLoading:
    """Tests for lazy loading of engine modules."""

    def test_modules_empty_on_init(self, temp_world):
        """No modules should be loaded on initialization."""
        em = EngineManager(temp_world)
        assert len(em._modules) == 0

    def test_data_manager_lazy_loaded(self, em):
        """Accessing data_manager should create the module on first access."""
        assert "data_manager" not in em._modules
        dm = em.data_manager
        assert dm is not None
        assert "data_manager" in em._modules

    def test_data_manager_returns_same_instance(self, em):
        """Repeated access to data_manager should return the same instance."""
        dm1 = em.data_manager
        dm2 = em.data_manager
        assert dm1 is dm2

    def test_world_graph_lazy_loaded(self, em):
        """Accessing world_graph should create the WorldGraph module."""
        wg = em.world_graph
        assert wg is not None
        assert "world_graph" in em._modules

    def test_sqlite_sync_lazy_loaded(self, em):
        """Accessing sqlite_sync should create the SQLiteSyncEngine module."""
        ss = em.sqlite_sync
        assert ss is not None
        assert "sqlite_sync" in em._modules

    def test_backup_manager_lazy_loaded(self, em):
        """Accessing backup_manager should create the BackupManager module."""
        bm = em.backup_manager
        assert bm is not None
        assert "backup_manager" in em._modules

    def test_bookkeeper_lazy_loaded(self, em):
        """Accessing bookkeeper should create the BookkeepingManager module."""
        bk = em.bookkeeper
        assert bk is not None
        assert "bookkeeper" in em._modules

    def test_unknown_module_raises_keyerror(self, em):
        """Accessing an unknown module should raise KeyError."""
        with pytest.raises(KeyError, match="nonexistent_module"):
            em._get_module("nonexistent_module")

    def test_get_lock_unknown_module_raises(self, em):
        """get_lock with an unknown module name should raise KeyError."""
        with pytest.raises(KeyError, match="Unknown module"):
            em.get_lock("nonexistent_module")


# ---------------------------------------------------------------------------
# with_lock Helper
# ---------------------------------------------------------------------------

class TestWithLock:
    """Tests for the with_lock convenience method."""

    def test_with_lock_executes_function(self, em):
        """with_lock should execute the provided function with the module."""
        result = em.with_lock("data_manager", lambda dm: dm.__class__.__name__)
        assert result == "DataManager"

    def test_with_lock_returns_function_result(self, em):
        """with_lock should return whatever the function returns."""
        result = em.with_lock("backup_manager", lambda bm: 42)
        assert result == 42

    def test_with_lock_unknown_module_raises(self, em):
        """with_lock with an unknown module should raise KeyError."""
        with pytest.raises(KeyError, match="Unknown module"):
            em.with_lock("fake_module", lambda m: None)


# ---------------------------------------------------------------------------
# Shutdown Sequence
# ---------------------------------------------------------------------------

class TestShutdown:
    """Tests for the shutdown lifecycle."""

    def test_shutdown_closes_sqlite(self, em):
        """shutdown should close the SQLite connection if it was opened."""
        # Access sqlite_sync to force it to be lazy-loaded
        sync = em.sqlite_sync
        assert sync is not None
        em.shutdown()
        # After shutdown, the connection should have been closed
        assert sync._conn is None

    def test_shutdown_without_sqlite_is_safe(self, em):
        """shutdown when sqlite_sync was never accessed should not raise."""
        assert "sqlite_sync" not in em._modules
        em.shutdown()  # Should not raise

    def test_shutdown_handles_sqlite_error(self, em):
        """shutdown should handle errors from sqlite close gracefully."""
        mock_sqlite = MagicMock()
        mock_sqlite.close.side_effect = RuntimeError("close failed")
        em._modules["sqlite_sync"] = mock_sqlite
        # Should not raise even if close fails
        em.shutdown()

    def test_reset_instance_calls_shutdown(self, temp_world):
        """reset_instance should call shutdown on the existing instance."""
        em = EngineManager.get_instance(temp_world)
        with patch.object(em, "shutdown") as mock_shutdown:
            EngineManager.reset_instance()
            mock_shutdown.assert_called_once()


# ---------------------------------------------------------------------------
# Module Initialization (root path handling)
# ---------------------------------------------------------------------------

class TestModuleInitialization:
    """Tests for proper module initialization with the project root."""

    def test_root_is_resolved_path(self, temp_world):
        """The root attribute should be a resolved Path object."""
        em = EngineManager(temp_world)
        assert em.root == Path(temp_world).resolve()
        assert em.root.is_absolute()

    def test_create_module_data_manager(self, em):
        """_create_module('data_manager') should return a DataManager instance."""
        dm = em._create_module("data_manager")
        from engine.data_manager import DataManager
        assert isinstance(dm, DataManager)

    def test_create_module_world_graph(self, em):
        """_create_module('world_graph') should return a WorldGraph instance."""
        wg = em._create_module("world_graph")
        from engine.graph_builder import WorldGraph
        assert isinstance(wg, WorldGraph)

    def test_create_module_unknown_raises(self, em):
        """_create_module with an unknown name should raise KeyError."""
        with pytest.raises(KeyError, match="Unknown module"):
            em._create_module("totally_unknown")
