"""
app/paths.py -- Path resolution for frozen and development modes.

Handles sys._MEIPASS detection for PyInstaller bundles and uses
platformdirs for user data directories.
"""

from __future__ import annotations

import os
import sys

from platformdirs import user_data_dir

_APP_NAME = "WorldbuildingInteractiveProgram"
_APP_AUTHOR = "WorldbuildingApp"


def is_frozen() -> bool:
    """Return True if running from a PyInstaller bundle."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def get_bundle_dir() -> str:
    """Return the bundle directory (PyInstaller _MEIPASS or project root)."""
    if is_frozen():
        return sys._MEIPASS  # type: ignore[attr-defined]
    # Development mode: project root is one level up from app/
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_project_root() -> str:
    """Return the project root for data files.

    In frozen mode, this is the user data directory so that engine data,
    templates, and user worlds persist across updates.  In dev mode,
    it's the repository root.
    """
    if is_frozen():
        return get_user_data_dir()
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_user_data_dir() -> str:
    """Return the platform-appropriate user data directory."""
    path = user_data_dir(_APP_NAME, _APP_AUTHOR)
    os.makedirs(path, exist_ok=True)
    return path


def get_engine_data_dir() -> str:
    """Return the directory containing engine data (templates, databases).

    In frozen mode, bundled data is in the bundle dir but user worlds
    are in user data dir.
    """
    if is_frozen():
        return get_bundle_dir()
    return get_project_root()


def ensure_user_data(bundle_dir: str, user_dir: str) -> None:
    """Copy initial data from bundle to user data dir on first run.

    Only copies directories that don't already exist in user_dir.
    """
    import shutil

    dirs_to_copy = ["user-world", "templates", "reference-databases"]
    for dirname in dirs_to_copy:
        src = os.path.join(bundle_dir, dirname)
        dst = os.path.join(user_dir, dirname)
        if os.path.isdir(src) and not os.path.isdir(dst):
            shutil.copytree(src, dst)
