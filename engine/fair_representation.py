"""
Fair Representation System for the Worldbuilding Interactive Program.

Tracks usage across all 16 reference databases (10 mythologies, 6 authors)
so that no single tradition dominates the worldbuilding guidance.

All databases with relevant content for a step are consulted -- fair
representation is maintained by tracking which databases have contributed
content, not by gating which ones are searched.

Usage counters are persisted in user-world/state.json under
"reference_usage_counts" so tracking survives across sessions.
"""

import json
import random
import threading
from pathlib import Path

from engine.utils import safe_write_json as _safe_write_json

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MYTHOLOGIES = [
    "greek", "roman", "norse", "celtic", "chinese",
    "japanese", "native-american", "mesopotamian", "hindu", "biblical",
]

AUTHORS = [
    "tolkien", "martin", "rothfuss", "berg", "lovecraft", "jordan",
]

ALL_DATABASES = MYTHOLOGIES + AUTHORS

FEATURED_MYTHOLOGY_COUNT = 4
FEATURED_AUTHOR_COUNT = 3

# Paths relative to the project root for the reference database files.
MYTHOLOGY_PATH_TEMPLATE = "reference-databases/mythologies/{name}.md"
AUTHOR_PATH_TEMPLATE = "reference-databases/authors/{name}.md"


class FairRepresentationManager:
    """Manages balanced rotation of the 16 reference databases.

    Tracks how many times each database has been featured and selects the
    least-used databases for each new step.  When counters are tied,
    selection is randomised among the tied candidates to avoid alphabetical
    bias.

    Parameters
    ----------
    state_file_path : str or pathlib.Path
        Absolute path to ``user-world/state.json``.
    """

    def __init__(self, state_file_path):
        self.state_file_path = Path(state_file_path)
        self._lock = threading.Lock()
        self._state = self._load_state()
        self._usage = self._state.setdefault("reference_usage_counts", {})
        self._ensure_all_counters()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def select_featured(self, step_number):
        """Select which databases to feature for *step_number*.

        Returns a dict with the following keys:

        - ``featured_mythologies``: list of 4 mythology names
        - ``featured_authors``: list of 3 author names
        - ``brief_mythologies``: list of the remaining 6 mythology names
        - ``brief_authors``: list of the remaining 3 author names

        Selection prioritises databases with the **lowest** usage count.
        When counts are tied the choice among tied candidates is random.
        After selection the usage counters are incremented (but **not**
        persisted -- call :meth:`save_state` to write to disk).

        Parameters
        ----------
        step_number : int
            The current progression step (1-52).

        Returns
        -------
        dict
        """
        featured_myths = self._select_lowest(MYTHOLOGIES, FEATURED_MYTHOLOGY_COUNT)
        featured_auths = self._select_lowest(AUTHORS, FEATURED_AUTHOR_COUNT)

        brief_myths = [m for m in MYTHOLOGIES if m not in featured_myths]
        brief_auths = [a for a in AUTHORS if a not in featured_auths]

        # Increment usage counters for the featured databases.
        for name in featured_myths + featured_auths:
            self._usage[name] = self._usage.get(name, 0) + 1

        # Auto-persist counters to prevent drift between in-memory and disk.
        try:
            self.save_state()
        except Exception:
            pass  # Non-critical; counters will persist on next explicit save

        return {
            "featured_mythologies": featured_myths,
            "featured_authors": featured_auths,
            "brief_mythologies": brief_myths,
            "brief_authors": brief_auths,
        }

    def record_usage(self, db_name: str) -> None:
        """Increment the usage counter for a single database.

        Called when a database contributes content to a response, so
        that fair representation tracking reflects actual usage rather
        than pre-selection.
        """
        if db_name in self._usage:
            self._usage[db_name] = self._usage.get(db_name, 0) + 1

    def get_usage_stats(self):
        """Return current usage counts for all 16 databases.

        Returns
        -------
        dict
            Mapping of database name to integer usage count, e.g.
            ``{"greek": 3, "roman": 2, ...}``.
        """
        return dict(self._usage)

    def save_state(self):
        """Persist updated usage counters back to ``state.json``.

        The counters are written under the key ``reference_usage_counts``
        inside the existing state file.  All other state data is preserved.
        """
        with self._lock:
            # Re-read the file to avoid clobbering concurrent changes to other
            # keys (e.g. current_step modified by another module).
            try:
                with open(self.state_file_path, "r", encoding="utf-8") as fh:
                    on_disk = json.load(fh)
            except (FileNotFoundError, json.JSONDecodeError):
                on_disk = {}

            on_disk["reference_usage_counts"] = dict(self._usage)

            _safe_write_json(str(self.state_file_path), on_disk)

    def select_option_sources(self, num_options):
        """Assign unique source-database combinations to each option.

        For option generation: each of *num_options* options receives a
        unique ``(primary_mythology, primary_author)`` pair so that no two
        options share the same primary inspiration.  Each option also gets a
        ``secondary`` list containing one additional mythology and one
        additional author for supplementary flavour.

        The selection draws from the **least-used** databases first, and
        usage counters are incremented for primary sources (but **not** for
        secondary sources, since those are lighter references).

        Parameters
        ----------
        num_options : int
            Number of options to generate (typically 2-4).

        Returns
        -------
        list[dict]
            Each dict has keys ``primary_mythology`` (str),
            ``primary_author`` (str), and ``secondary`` (list of str).

        Raises
        ------
        ValueError
            If *num_options* exceeds the number of available mythologies
            (10) or authors (6).
        """
        if num_options < 1:
            raise ValueError("num_options must be at least 1")
        if num_options > len(AUTHORS):
            raise ValueError(
                f"num_options ({num_options}) exceeds the number of "
                f"available authors ({len(AUTHORS)})"
            )

        # Pick primary sources -- all unique, lowest-usage first.
        primary_myths = self._select_lowest(MYTHOLOGIES, num_options)
        primary_auths = self._select_lowest(AUTHORS, num_options)

        # Build a pool of remaining databases for secondary picks.
        remaining_myths = [m for m in MYTHOLOGIES if m not in primary_myths]
        remaining_auths = [a for a in AUTHORS if a not in primary_auths]

        # Shuffle the remaining pools so secondary picks are varied.
        random.shuffle(remaining_myths)
        random.shuffle(remaining_auths)

        results = []
        for i in range(num_options):
            # Pick one secondary mythology and one secondary author.
            # Cycle through the remaining pools if num_options > pool size.
            sec_myth = remaining_myths[i % len(remaining_myths)] if remaining_myths else primary_myths[(i + 1) % num_options]
            sec_auth = remaining_auths[i % len(remaining_auths)] if remaining_auths else primary_auths[(i + 1) % num_options]

            results.append({
                "primary_mythology": primary_myths[i],
                "primary_author": primary_auths[i],
                "secondary": [sec_myth, sec_auth],
            })

        # Increment usage counters for primary selections only.
        for name in primary_myths + primary_auths:
            self._usage[name] = self._usage.get(name, 0) + 1

        # Auto-persist counters to prevent drift between in-memory and disk.
        try:
            self.save_state()
        except Exception:
            pass  # Non-critical; counters will persist on next explicit save

        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_state(self):
        """Load state.json, returning an empty dict on any failure."""
        try:
            with open(self.state_file_path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _ensure_all_counters(self):
        """Make sure every database has a counter entry (default 0)."""
        for name in ALL_DATABASES:
            self._usage.setdefault(name, 0)

    def _select_lowest(self, pool, count):
        """Select *count* names from *pool* with the lowest usage counts.

        When multiple candidates share the same lowest count the selection
        among them is randomised to avoid alphabetical bias.

        Parameters
        ----------
        pool : list[str]
            The candidate database names (e.g. MYTHOLOGIES or AUTHORS).
        count : int
            How many to select.

        Returns
        -------
        list[str]
            The selected database names (length == *count*).
        """
        if count > len(pool):
            count = len(pool)

        # Build (usage_count, name) pairs.
        candidates = [(self._usage.get(name, 0), name) for name in pool]

        # Sort by usage count ascending.  Among ties, random order.
        # We achieve this by sorting on (count, random_tiebreaker).
        candidates.sort(key=lambda pair: (pair[0], random.random()))

        return [name for _, name in candidates[:count]]
