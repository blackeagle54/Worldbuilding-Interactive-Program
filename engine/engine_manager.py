"""
engine/engine_manager.py -- Thread-Safe Engine Singleton

Provides a single access point for all engine modules with per-module
threading locks.  Designed for the PySide6 desktop app where UI threads,
worker threads, and Claude integration threads all need safe access to
the engine.

Usage:
    from engine.engine_manager import EngineManager

    em = EngineManager.get_instance("C:/Worldbuilding-Interactive-Program")
    dm = em.data_manager       # lazy-loaded, thread-safe access
    wg = em.world_graph
    em.with_lock("data_manager", lambda dm: dm.get_entity("some-id"))
"""

import os
import threading
from pathlib import Path


class EngineManager:
    """Singleton that owns all engine module instances with per-module locks.

    Modules are lazily created on first access.  Each module has its own
    ``threading.RLock`` so that concurrent operations on different modules
    do not block each other.

    Parameters
    ----------
    project_root : str or pathlib.Path
        Absolute path to the project root directory.
    """

    _instance = None
    _init_lock = threading.Lock()

    def __init__(self, project_root):
        self.root = Path(project_root).resolve()

        # Per-module locks
        self._locks = {
            "data_manager": threading.RLock(),
            "world_graph": threading.RLock(),
            "chunk_puller": threading.RLock(),
            "option_generator": threading.RLock(),
            "consistency_checker": threading.RLock(),
            "sqlite_sync": threading.RLock(),
            "backup_manager": threading.RLock(),
            "bookkeeper": threading.RLock(),
            "fair_representation": threading.RLock(),
            "error_recovery": threading.RLock(),
        }

        # Lazy-loaded module instances
        self._modules = {}

    # ------------------------------------------------------------------
    # Singleton access
    # ------------------------------------------------------------------

    @classmethod
    def get_instance(cls, project_root=None):
        """Return the singleton instance, creating it if needed.

        Parameters
        ----------
        project_root : str or pathlib.Path, optional
            Required on first call.  Ignored on subsequent calls.

        Returns
        -------
        EngineManager
        """
        if cls._instance is not None:
            return cls._instance

        with cls._init_lock:
            # Double-check after acquiring lock
            if cls._instance is not None:
                return cls._instance
            if project_root is None:
                raise ValueError(
                    "project_root is required on first call to get_instance()"
                )
            cls._instance = cls(project_root)
            return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset the singleton (for testing).  Shuts down any open resources."""
        with cls._init_lock:
            if cls._instance is not None:
                cls._instance.shutdown()
            cls._instance = None

    # ------------------------------------------------------------------
    # Module properties (lazy-loaded)
    # ------------------------------------------------------------------

    @property
    def data_manager(self):
        return self._get_module("data_manager")

    @property
    def world_graph(self):
        return self._get_module("world_graph")

    @property
    def chunk_puller(self):
        return self._get_module("chunk_puller")

    @property
    def option_generator(self):
        return self._get_module("option_generator")

    @property
    def consistency_checker(self):
        return self._get_module("consistency_checker")

    @property
    def sqlite_sync(self):
        return self._get_module("sqlite_sync")

    @property
    def backup_manager(self):
        return self._get_module("backup_manager")

    @property
    def bookkeeper(self):
        return self._get_module("bookkeeper")

    @property
    def fair_representation(self):
        return self._get_module("fair_representation")

    @property
    def error_recovery(self):
        return self._get_module("error_recovery")

    # ------------------------------------------------------------------
    # Lock-guarded access
    # ------------------------------------------------------------------

    def get_lock(self, module_name):
        """Return the RLock for a given module name.

        Callers can use this for fine-grained locking::

            with em.get_lock("data_manager"):
                entity = em.data_manager.get_entity(eid)
                em.data_manager.update_entity(eid, data)

        Parameters
        ----------
        module_name : str
            One of the 10 module names (e.g. ``"data_manager"``).

        Returns
        -------
        threading.RLock
        """
        if module_name not in self._locks:
            raise KeyError(f"Unknown module: {module_name}")
        return self._locks[module_name]

    def with_lock(self, module_name, fn):
        """Execute *fn(module)* while holding the module's lock.

        Parameters
        ----------
        module_name : str
            Module name (e.g. ``"data_manager"``).
        fn : callable
            A callable that receives the module instance.

        Returns
        -------
        object
            Whatever *fn* returns.
        """
        with self.get_lock(module_name):
            module = self._get_module(module_name)
            return fn(module)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def shutdown(self):
        """Release resources held by engine modules."""
        # Close SQLite connection if open
        sqlite = self._modules.get("sqlite_sync")
        if sqlite is not None:
            try:
                sqlite.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_module(self, name):
        """Lazily create and return the named module instance."""
        if name in self._modules:
            return self._modules[name]

        with self._locks[name]:
            # Double-check after acquiring lock
            if name in self._modules:
                return self._modules[name]

            instance = self._create_module(name)
            self._modules[name] = instance
            return instance

    def _create_module(self, name):
        """Import and instantiate the named module."""
        root = str(self.root)

        if name == "data_manager":
            from engine.data_manager import DataManager
            return DataManager(root)

        if name == "world_graph":
            from engine.graph_builder import WorldGraph
            return WorldGraph(root)

        if name == "chunk_puller":
            from engine.chunk_puller import ChunkPuller
            return ChunkPuller(root)

        if name == "option_generator":
            from engine.option_generator import OptionGenerator
            return OptionGenerator(root)

        if name == "consistency_checker":
            from engine.consistency_checker import ConsistencyChecker
            return ConsistencyChecker(root)

        if name == "sqlite_sync":
            from engine.sqlite_sync import SQLiteSyncEngine
            return SQLiteSyncEngine(root)

        if name == "backup_manager":
            from engine.backup_manager import BackupManager
            return BackupManager(root)

        if name == "bookkeeper":
            from engine.bookkeeper import BookkeepingManager
            bookkeeping_root = os.path.join(root, "bookkeeping")
            return BookkeepingManager(bookkeeping_root)

        if name == "fair_representation":
            from engine.fair_representation import FairRepresentationManager
            state_path = os.path.join(root, "user-world", "state.json")
            return FairRepresentationManager(state_path)

        if name == "error_recovery":
            from engine.error_recovery import ErrorRecoveryManager
            return ErrorRecoveryManager(root)

        raise KeyError(f"Unknown module: {name}")
