"""
app/services/update_checker.py -- Non-intrusive update checker.

Polls a GitHub Releases API endpoint in the background to check for
new versions.  Shows a non-blocking notification if an update is found.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import urllib.request
import urllib.error
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal

logger = logging.getLogger(__name__)


def _read_version() -> str:
    """Read the application version from the VERSION file."""
    # When running from source, VERSION is at the project root (two levels up)
    source_version = os.path.normpath(
        os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "VERSION")
    )
    # When running from a PyInstaller bundle, VERSION is in the bundle root
    bundle_version = os.path.join(
        getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))),
        "VERSION",
    )
    for path in (source_version, bundle_version):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except FileNotFoundError:
            continue
    return "0.0.0"


_CURRENT_VERSION = _read_version()
_GITHUB_REPO = "worldbuilding-app/worldbuilding-interactive-program"
_API_URL = f"https://api.github.com/repos/{_GITHUB_REPO}/releases/latest"


class _CheckWorker(QThread):
    """Background thread that checks GitHub for the latest release."""

    result = Signal(dict)

    def run(self) -> None:
        try:
            req = urllib.request.Request(
                _API_URL,
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                self.result.emit({
                    "tag": data.get("tag_name", ""),
                    "name": data.get("name", ""),
                    "url": data.get("html_url", ""),
                    "body": data.get("body", "")[:200],
                })
        except Exception as e:
            logger.debug("Update check failed: %s", e)
            self.result.emit({})


class UpdateChecker(QObject):
    """Checks for application updates from GitHub Releases.

    Signals
    -------
    update_available(str, str)
        Emitted when a newer version is found: (version_tag, release_url).
    """

    update_available = Signal(str, str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._worker: _CheckWorker | None = None

    @property
    def current_version(self) -> str:
        return _CURRENT_VERSION

    def check(self) -> None:
        """Start a background check for updates."""
        if self._worker is not None and self._worker.isRunning():
            return

        self._worker = _CheckWorker(self)
        self._worker.result.connect(self._on_result)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _on_result(self, data: dict) -> None:
        if not data or not data.get("tag"):
            return

        tag = data["tag"].lstrip("v")
        current = _CURRENT_VERSION.lstrip("v")

        try:
            tag_tuple = tuple(int(x) for x in tag.split("."))
            current_tuple = tuple(int(x) for x in current.split("."))
        except (ValueError, AttributeError):
            # Fall back to string comparison if parsing fails
            tag_tuple = (tag,)
            current_tuple = (current,)

        if tag_tuple > current_tuple:
            logger.info("Update available: %s (current: %s)", tag, current)
            self.update_available.emit(tag, data.get("url", ""))
