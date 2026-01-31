"""
engine/chunk_puller.py -- Three-Layer Guidance Generator for the Worldbuilding
Interactive Program.

The core intelligence engine. Given a progression step number, it produces a
structured three-layer guidance document:

    Layer 1 (Book Quotes)      - Relevant passages from source-text.txt
    Layer 2 (References)       - Synthesised material from the 16 reference databases
    Layer 3 (Actionable)       - Template info, field lists, guided questions,
                                  existing entity awareness, and dependency status

This module prepares and structures all data.  It does NOT call Claude or any
LLM -- Claude performs the actual synthesis and presentation when it consumes
the structured output.

Usage:
    from engine.chunk_puller import ChunkPuller

    cp = ChunkPuller("C:/Worldbuilding-Interactive-Program")
    guidance = cp.pull_guidance(7)
    condensed = cp.pull_condensed(7)
"""

import json
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

from engine.utils import safe_read_json as _safe_read_json


def _read_lines_range(file_path: str, start: int, end: int) -> list[str]:
    """Read lines *start* through *end* (1-indexed, inclusive) from a text file.

    Returns a list of strings.  If the file cannot be read or the range
    is invalid, returns an empty list.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except (FileNotFoundError, OSError):
        return []

    # Clamp to valid range (1-indexed)
    start = max(1, start)
    end = min(len(lines), end)
    if start > end:
        return []
    return [line.rstrip("\n") for line in lines[start - 1 : end]]


def _extract_md_section(file_path: str, section_title: str) -> str:
    """Extract the content of a markdown section from a ``.md`` file.

    Searches for a heading line whose text matches *section_title*
    (case-insensitive, ignoring leading ``#`` characters and whitespace).
    Returns all text from that heading to the next heading of equal or
    higher level, or to end-of-file.

    If the section cannot be found, returns an empty string.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except (FileNotFoundError, OSError):
        return ""

    target = section_title.strip().lower()
    # Also try matching just the numeric-prefix-stripped version
    # e.g. "1. PANTHEON" should match a heading "## 1. PANTHEON"
    target_stripped = re.sub(r"^[\d]+\.\s*", "", target)

    start_idx = None
    start_level = 0

    for idx, line in enumerate(lines):
        heading_match = re.match(r"^(#{1,6})\s+(.*)", line)
        if not heading_match:
            continue
        level = len(heading_match.group(1))
        heading_text = heading_match.group(2).strip().lower()
        heading_text_stripped = re.sub(r"^[\d]+\.\s*", "", heading_text)

        if start_idx is None:
            # Looking for the start of the section
            if (target in heading_text
                    or heading_text in target
                    or target_stripped in heading_text_stripped
                    or heading_text_stripped in target_stripped):
                start_idx = idx
                start_level = level
        else:
            # Already inside the section -- stop at next heading of same
            # or higher (lower number) level
            if level <= start_level:
                content_lines = lines[start_idx + 1 : idx]
                return "".join(content_lines).strip()

    # If we found the heading but hit end-of-file
    if start_idx is not None:
        content_lines = lines[start_idx + 1 :]
        return "".join(content_lines).strip()

    return ""


def _extract_md_section_by_lines(file_path: str, line_start: int, line_end: int) -> str:
    """Extract content from a markdown file by line range (1-indexed, inclusive).

    Falls back to line-range extraction when section-title matching is
    unreliable.
    """
    lines = _read_lines_range(file_path, line_start, line_end)
    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# Phase name lookup
# ---------------------------------------------------------------------------

_PHASE_NAMES = {
    1: "Foundation",
    2: "Cosmology",
    3: "The Land",
    4: "Life",
    5: "Civilization",
    6: "Society",
    7: "The Supernatural",
    8: "History & Legend",
    9: "Language & Names",
    10: "Travel & Scale",
    11: "Finishing Touches",
    12: "Integration",
}


# ---------------------------------------------------------------------------
# Guided questions by step (topic-specific questions to help the user)
# ---------------------------------------------------------------------------

_GUIDED_QUESTIONS = {
    1: [
        "Will you build one world or multiple?",
        "What medium is this world for (novel, game, film, RPG)?",
        "Will you build depth-first (one area in detail) or breadth-first (many areas lightly)?",
        "How will you reveal world details to the audience -- show vs. tell?",
        "What real-world sources will you draw inspiration from?",
    ],
    2: [
        "Pick one real-world analogue. What three changes will you make?",
        "Does the original source have cultural elements you want to keep recognisable?",
        "How far can you deviate before the analogue loses its value?",
    ],
    3: [
        "When you modify something from reality, how much change warrants a new name?",
        "Will you use known fantasy terms (elf, dwarf) or invent your own?",
        "What naming feeling do you want -- familiar, exotic, ancient, alien?",
    ],
    4: [
        "What is your primary goal: storytelling, gaming, or personal hobby?",
        "How many hours per week can you commit to world building?",
        "Which elements are essential vs. optional for your project?",
        "What is your priority order for building?",
    ],
    5: [
        "How will you organise your files?",
        "What backup strategy will you use?",
        "Will you maintain a 'changes to make' file for capturing ideas?",
    ],
    6: [
        "How are your gods organised -- by family, element, domain, or something else?",
        "What is the power hierarchy among gods?",
        "Are gods real, imagined, or ambiguous in your world?",
        "What rules govern divine behaviour, and what happens when broken?",
        "How many gods exist in your pantheon?",
    ],
    7: [
        "What domain does this god govern?",
        "What is this god's alignment (good, evil, neutral, complex)?",
        "What symbol represents this god?",
        "How does this god relate to other gods in the pantheon?",
        "What does this god look like when they choose to appear?",
        "What is this god's personality -- and their fatal flaw?",
    ],
    8: [
        "How did the world begin according to the inhabitants?",
        "What is true versus what people believe about creation?",
        "How might the world end -- and who prophesied it?",
        "Which gods played central roles in creation?",
        "What was the first act of defiance or disobedience?",
    ],
    9: [
        "What moral lesson does this myth teach?",
        "Which gods and mortals are involved?",
        "How does this myth explain something in the natural world?",
        "Is this myth believed by all cultures or only some?",
    ],
    10: [
        "What type of star does your planet orbit?",
        "How many moons does your planet have?",
        "What is the axial tilt and how does it affect seasons?",
        "Where is the equator relative to your main continent?",
        "What are the prevailing wind directions by latitude zone?",
    ],
    11: [
        "Which constellations are visible from each hemisphere?",
        "Which gods or figures are associated with each constellation?",
        "Are there 'dark constellations' in your night sky?",
    ],
    12: [
        "What is the overall shape of your continent?",
        "Which hemisphere does it occupy, and what is its latitude range?",
        "Where are the plate boundaries that form mountains?",
        "What major water bodies surround the continent?",
    ],
    13: [
        "Where do plate boundaries create mountain ranges?",
        "Which mountains have volcanoes (ocean-continent convergence)?",
        "Which direction do prevailing winds hit each range?",
        "What grows on the windward side vs. the leeward side?",
    ],
    14: [
        "Where do major rivers originate (mountains)?",
        "Which rivers serve as natural national boundaries?",
        "Where will major lakes form?",
        "Which rivers are young (straight, fast) vs. old (meandering)?",
    ],
    15: [
        "Where do forests grow based on your rain shadow map?",
        "What type of desert dominates (hot, cold, rocky, sandy)?",
        "Where do wetlands form near rivers and coasts?",
        "Which creatures and species will inhabit each biome?",
    ],
    16: [
        "Will you use public domain species, original ones, or both?",
        "What distinguishes a 'species' from a 'race' in your world?",
        "How many species do you plan to create?",
    ],
    17: [
        "What terrain and climate does this species prefer?",
        "Do they live in isolated or joint settlements?",
        "What is their overall disposition (good, evil, complex)?",
        "Which god created or influences them?",
    ],
    18: [
        "What makes this species visually distinct from humans?",
        "Which senses are enhanced, diminished, or entirely new?",
        "How does their appearance reflect their habitat?",
    ],
    19: [
        "How does this species view itself compared to other species?",
        "What do they consider humanity's greatest flaw -- and how do they handle it differently?",
        "What is their relationship with mortality, ambition, and conflict?",
    ],
    20: [
        "What type of government does this species favour?",
        "What are their key customs and taboos?",
        "What languages do they speak and write?",
        "What is their technology level?",
    ],
    21: [
        "Which species are natural allies?",
        "Which are historical enemies -- and what caused the enmity?",
        "What stereotypes does each species hold about the others?",
    ],
    22: [
        "What products do your inhabitants need (food, medicine, leather, ink)?",
        "What plant or animal provides each product?",
        "How are these organisms domesticated or harvested?",
    ],
    23: [
        "What is the monster's origin -- accidental, designed, or evolved?",
        "What motivates this monster (isolation, hoarding, hunger, revenge)?",
        "What does its lair look like and contain?",
        "What makes it different from a species or animal?",
    ],
    24: [
        "What types of undead exist in your world?",
        "What are the prerequisites for becoming undead?",
        "How do the living prevent someone from rising?",
        "What goals drive the undead -- unfinished business, regaining life, causing torment?",
    ],
    25: [
        "What type of government does this nation have?",
        "What species make up the population, and in what proportions?",
        "Who are its allies and enemies, and why?",
        "What is the nation's world view -- what 2-3 ideas drive it?",
        "What are its symbol, colours, and reputation?",
    ],
    26: [
        "What are the foundational values and beliefs of this culture?",
        "What is its cultural vision (formal, exuberant, modest, calculating)?",
        "How does culture vary between social classes?",
    ],
    27: [
        "How do people greet each other and say farewell?",
        "What is dining etiquette -- seating, utensils, toasts?",
        "What does clothing signal about status?",
        "What does a typical day look like for a commoner vs. a noble?",
        "Describe at least one holiday or festival.",
    ],
    28: [
        "Which cultural differences could cause misunderstanding?",
        "How severe is each potential clash (minor, serious, deadly)?",
        "How might each clash appear in a story scene?",
    ],
    29: [
        "What type of settlement is this (outpost, village, town, city)?",
        "What water source supports it?",
        "What species live here, and in what proportions?",
        "What is the settlement's primary product or trade good?",
        "What is the settlement's one big secret?",
    ],
    30: [
        "Have you listed every named settlement?",
        "Does each entry have a sovereign power, population, and product?",
        "Are there duplicate symbols or colours among settlements?",
    ],
    31: [
        "What event or figure founded this religion?",
        "What do followers believe the god wants from them?",
        "How is the clergy structured?",
        "What is the afterlife in this religion -- paradise, rebirth, oblivion?",
        "What holidays and worship practices exist?",
    ],
    32: [
        "Is this a force for good or evil?",
        "What is its true goal beyond power?",
        "How do people join and leave?",
        "What happens to defectors?",
    ],
    33: [
        "What terrain does this force specialise in?",
        "What weapons and armour are standard?",
        "How does someone enlist -- prerequisites, tests, training?",
        "What is the rank structure?",
        "Describe one military custom (toast, burial, greeting).",
    ],
    34: [
        "How does education work -- schools, apprenticeships, or both?",
        "What legal system is used (civil, common, religious)?",
        "What currency system exists and what can you buy with it?",
        "How does news travel across the land?",
    ],
    35: [
        "How common is the supernatural -- rare, uncommon, common, or ubiquitous?",
        "What industries vanish or change because of magic?",
        "How does society view the supernatural -- with fear, reverence, or acceptance?",
    ],
    36: [
        "What properties does supernatural energy have (appearance, temperature)?",
        "Do magic paths or alternate realities exist?",
        "What supernatural beings inhabit your world?",
    ],
    37: [
        "What is possible and impossible with magic?",
        "Who can perform magic, and how common are they?",
        "What happens when magic fails?",
        "What is the cost of using magic (fatigue, aging, madness)?",
        "Is your system hard (rule-based) or soft (mysterious)?",
    ],
    38: [
        "How are spells structured -- gestures, ingredients, words?",
        "What happens on spell failure?",
        "How is magical ability trained -- apprenticeship or schools?",
        "What are the ranks of magical mastery?",
    ],
    39: [
        "What makes this item significant -- its powers, history, or owner?",
        "What limitations or defects does it have?",
        "How was it created, and by whom?",
        "Who can use it, and who cannot?",
    ],
    40: [
        "How long is a week, a month, a year in your world?",
        "What event anchors your universal calendar?",
        "What are the named ages of your world's history?",
    ],
    41: [
        "What god-interference events shaped history?",
        "What wars defined the rise and fall of powers?",
        "What artifacts were discovered, and what was their impact?",
        "What missions or quests became legendary?",
    ],
    42: [
        "Why is this figure famous -- what deeds define them?",
        "What do people believe vs. what is true about them?",
        "Are they alive, dead, missing, or imprisoned?",
        "How do different species view this figure?",
    ],
    43: [
        "Will you create a full conlang, a naming language, or ad-hoc phrases?",
        "What medium are you working in, and how much does it benefit from languages?",
    ],
    44: [
        "How many names do people in this culture typically have?",
        "What common prefixes and suffixes are used?",
        "What triggers a name change (coming of age, marriage, magic)?",
    ],
    45: [
        "Have you named all gods, species, nations, settlements, and features?",
        "Are there any same-first-letter collisions among major characters?",
        "Have you said each name aloud to check pronunciation?",
    ],
    46: [
        "What is your map scale (inches to miles)?",
        "What terrain types does each route cross?",
        "How long does travel between key settlements take?",
    ],
    47: [
        "What ship types does each naval power use?",
        "What are the key sea routes and their distances?",
        "How long does a coastal journey take vs. open ocean?",
    ],
    48: [
        "What FTL method exists (jump, hyper, warp)?",
        "What limits FTL travel to preserve story conflict?",
        "What does the interior of a key spacecraft look like?",
    ],
    49: [
        "What story makes this place interesting?",
        "What type of location is it (ruin, phenomenon, shipwreck, monument)?",
        "How does it connect to your history timeline?",
    ],
    50: [
        "Does your map show coastline, mountains, rivers, settlements, and roads?",
        "Have you added sovereign power boundaries?",
        "Does the scale feel right for your travel calculations?",
    ],
    51: [
        "Does every entity connect to at least one other entity?",
        "Are there contradictions between files?",
        "Have you traced a geographic feature through all its consequences?",
    ],
    52: [
        "How often will you review your world files?",
        "Do you have a 'changes to make' file for capturing ideas?",
        "What is your process for keeping files in sync?",
    ],
}


# ---------------------------------------------------------------------------
# Step dependency map (step -> list of prerequisite steps)
# ---------------------------------------------------------------------------

_STEP_DEPENDENCIES = {
    1: [],
    2: [],
    3: [2],
    4: [1],
    5: [4],
    6: [1, 2, 3],
    7: [6],
    8: [7],
    9: [8],
    10: [7],
    11: [7, 10],
    12: [10],
    13: [10, 12],
    14: [13],
    15: [13, 14],
    16: [1, 2, 3],
    17: [7, 13, 14, 15, 16],
    18: [17],
    19: [17],
    20: [18, 19],
    21: [20],
    22: [17, 13, 14, 15],
    23: [7, 16, 17, 18, 19, 13, 14, 15],
    24: [7, 16, 17, 18, 19, 20, 22],
    25: [12, 13, 14, 15, 16, 17, 18, 19, 20, 21],
    26: [25, 16, 17, 18, 19, 20],
    27: [26],
    28: [27],
    29: [14, 15, 25, 26, 27],
    30: [29],
    31: [7, 8, 9, 16, 17, 18, 19, 20, 21, 25],
    32: [25, 26, 31],
    33: [25, 13, 14, 15, 29, 30, 26],
    34: [25, 29, 30, 26, 31],
    35: [25, 26, 27, 28, 29, 30, 31, 32, 33, 34],
    36: [35, 7, 31],
    37: [35, 36],
    38: [37],
    39: [37, 38, 25, 7],
    40: [10, 7, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34],
    41: [40, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39],
    42: [7, 8, 9, 16, 17, 18, 19, 20, 21, 25, 26, 41],
    43: [26, 16, 17, 18, 19, 20],
    44: [43, 26],
    45: [44],
    46: [12, 13, 14, 15, 29, 30],
    47: [10, 12, 13, 14, 15, 25, 29, 30],
    48: [10, 25],
    49: [12, 13, 14, 15, 25, 29, 30, 41, 35, 36, 37, 38, 39],
    50: [12, 13, 14, 15, 25, 29, 30, 46, 47],
    51: list(range(1, 51)),
    52: [51],
}


# ---------------------------------------------------------------------------
# ChunkPuller
# ---------------------------------------------------------------------------

class ChunkPuller:
    """Three-layer guidance generator for the Worldbuilding Interactive Program.

    Given a progression step number, produces all three layers of guidance:

    - **Layer 1 -- Book Quotes:**  Key passages from ``source-text.txt`` with
      line references and contextual notes.
    - **Layer 2 -- References:**  Material from the 16 reference databases,
      split into featured mythologies, featured authors, brief mentions, and
      cross-cutting patterns.
    - **Layer 3 -- Actionable:**  Template metadata, field classifications,
      guided questions, existing entity counts, and dependency status.

    Parameters
    ----------
    project_root : str
        Absolute path to the Worldbuilding Interactive Program root directory,
        e.g. ``"C:/Worldbuilding-Interactive-Program"``.
    """

    def __init__(self, project_root: str):
        self.root = Path(project_root).resolve()

        # Load the three index files
        self._source_index = _safe_read_json(
            str(self.root / "engine" / "source_index.json"), default={}
        )
        self._reference_index = _safe_read_json(
            str(self.root / "engine" / "reference_index.json"), default={}
        )
        self._template_registry = _safe_read_json(
            str(self.root / "engine" / "template_registry.json"), default={}
        )

        # Normalise template registry to a dict keyed by template id
        raw_templates = self._template_registry.get("templates", [])
        if isinstance(raw_templates, list):
            self._templates_by_id = {t["id"]: t for t in raw_templates if "id" in t}
            self._templates_list = raw_templates
        elif isinstance(raw_templates, dict):
            self._templates_by_id = raw_templates
            self._templates_list = list(raw_templates.values())
        else:
            self._templates_by_id = {}
            self._templates_list = []

        # Build step -> template list mapping
        self._step_templates: dict[int, list[dict]] = {}
        for tmpl in self._templates_list:
            step = tmpl.get("step")
            if step is not None:
                self._step_templates.setdefault(step, []).append(tmpl)

        # Pre-index reference databases
        self._databases = self._reference_index.get("databases", {})

        # Source text path
        self._source_text_path = str(self.root / "reference-databases" / "source-text.txt")

        # State path
        self._state_path = str(self.root / "user-world" / "state.json")

    # ------------------------------------------------------------------
    # Main public method
    # ------------------------------------------------------------------

    def pull_guidance(self, step_number: int) -> dict:
        """Produce the full three-layer guidance document for a step.

        Parameters
        ----------
        step_number : int
            The progression step (1--52).

        Returns
        -------
        dict
            A structured document containing ``step``, ``layer1_book``,
            ``layer2_references``, and ``layer3_actionable`` keys.
        """
        step_info = self._get_step_info(step_number)

        return {
            "step": step_info,
            "layer1_book": self._build_layer1(step_number),
            "layer2_references": self._build_layer2(step_number),
            "layer3_actionable": self._build_layer3(step_number),
        }

    # ------------------------------------------------------------------
    # Individual layer methods (also publicly accessible)
    # ------------------------------------------------------------------

    def pull_book_quotes(self, step_number: int) -> list:
        """Extract just the book quotes for a step (Layer 1 only).

        Reads ``source_index.json`` for line ranges, then reads
        ``source-text.txt`` for the actual content.

        Parameters
        ----------
        step_number : int
            The progression step (1--52).

        Returns
        -------
        list[dict]
            Each dict has ``text``, ``line_start``, ``line_end``, and
            ``context`` keys.
        """
        return self._build_layer1(step_number).get("quotes", [])

    def pull_references(
        self,
        step_number: int,
        featured_mythologies: list[str] | None = None,
        featured_authors: list[str] | None = None,
    ) -> dict:
        """Extract reference material for a step (Layer 2 only).

        Uses ``reference_index.json`` to find relevant sections, then
        reads the actual ``.md`` database files for content.

        Parameters
        ----------
        step_number : int
            The progression step (1--52).
        featured_mythologies : list[str], optional
            Override the 4 featured mythology database names.  If ``None``,
            the ``FairRepresentationManager`` is used to select them.
        featured_authors : list[str], optional
            Override the 3 featured author database names.  If ``None``,
            the ``FairRepresentationManager`` is used to select them.

        Returns
        -------
        dict
            Contains ``featured_mythologies``, ``featured_authors``,
            ``brief_mentions``, and ``cross_cutting_patterns`` keys.
        """
        return self._build_layer2(
            step_number,
            override_mythologies=featured_mythologies,
            override_authors=featured_authors,
        )

    def pull_template_info(self, step_number: int) -> dict:
        """Extract template and actionable info for a step (Layer 3 only).

        Uses ``template_registry.json`` and checks existing entities via
        the state file.

        Parameters
        ----------
        step_number : int
            The progression step (1--52).

        Returns
        -------
        dict
            Template metadata, field classifications, guided questions,
            existing entity counts, and dependency status.
        """
        return self._build_layer3(step_number)

    def pull_condensed(self, step_number: int) -> str:
        """Return a condensed text version of the guidance for context injection.

        Much shorter than the full guidance -- includes key quotes (truncated),
        brief reference summaries, and a template overview.  Designed to fit
        inside a hook context injection without bloating.

        Parameters
        ----------
        step_number : int
            The progression step (1--52).

        Returns
        -------
        str
            A compact, human-readable text block.
        """
        step_info = self._get_step_info(step_number)
        layer1 = self._build_layer1(step_number)
        layer3 = self._build_layer3(step_number)

        parts: list[str] = []

        # Header
        parts.append(
            f"[STEP {step_info['number']}: {step_info['title']}]"
            f"  (Phase {step_info['phase']} -- {step_info.get('phase_name', '')})"
        )
        parts.append("")

        # Key quotes (first 3, truncated)
        if layer1.get("quotes"):
            parts.append("KEY BOOK QUOTES:")
            for q in layer1["quotes"][:3]:
                text = q.get("text", "")
                if len(text) > 200:
                    text = text[:200] + "..."
                parts.append(f"  - \"{text}\" (lines {q.get('line_start', '?')}-{q.get('line_end', '?')})")
            parts.append("")

        # Teaching summary
        if layer1.get("teaching_summary"):
            summary = layer1["teaching_summary"]
            if len(summary) > 300:
                summary = summary[:300] + "..."
            parts.append(f"BOOK TEACHING: {summary}")
            parts.append("")

        # Template summary
        if layer3.get("template_id"):
            tmpl_ids = layer3["template_id"] if isinstance(layer3["template_id"], list) else [layer3["template_id"]]
            parts.append(f"TEMPLATES: {', '.join(tmpl_ids)}")
            if layer3.get("required_fields"):
                parts.append(f"  Required fields: {', '.join(layer3['required_fields'][:8])}")
            min_c = layer3.get("minimum_count", 0)
            exist_c = layer3.get("existing_count", 0)
            if min_c:
                parts.append(f"  Progress: {exist_c}/{min_c} entities created")
            parts.append("")

        # Layer 2: Condensed reference content (2 mythology + 1 author, ~500 chars each)
        layer2 = self._build_layer2(step_number)
        mythology_refs = layer2.get("featured_mythologies", [])
        author_refs = layer2.get("featured_authors", [])

        condensed_refs: list[dict] = []
        for ref in mythology_refs[:2]:
            condensed_refs.append(ref)
        for ref in author_refs[:1]:
            condensed_refs.append(ref)

        if condensed_refs:
            parts.append("REFERENCE DATABASE CONTENT:")
            for ref in condensed_refs:
                db_name = ref.get("database_name", ref.get("database", ""))
                section = ref.get("section", "")
                content = ref.get("content", "")
                if len(content) > 500:
                    content = content[:500] + "..."
                parts.append(f"  [{db_name} -- {section}]")
                parts.append(f"  {content}")
                parts.append("")

        # Dependencies
        deps = self.get_step_dependencies(step_number)
        if deps.get("missing_dependencies"):
            missing = deps["missing_dependencies"]
            parts.append(f"BLOCKED: Steps {', '.join(str(s) for s in missing)} not completed yet.")
            parts.append("")

        # Guided questions (first 3)
        questions = layer3.get("guided_questions", [])
        if questions:
            parts.append("GUIDING QUESTIONS:")
            for q in questions[:3]:
                parts.append(f"  - {q}")
            parts.append("")

        return "\n".join(parts)

    def get_step_dependencies(self, step_number: int) -> dict:
        """Return dependency status for a step.

        Parameters
        ----------
        step_number : int
            The progression step (1--52).

        Returns
        -------
        dict
            Contains ``required_steps``, ``completed``, ``missing_dependencies``,
            and ``dependencies_met`` keys.
        """
        required = _STEP_DEPENDENCIES.get(step_number, [])
        state = _safe_read_json(self._state_path, default={})
        completed = set(state.get("completed_steps", []))

        missing = [s for s in required if s not in completed]

        return {
            "required_steps": required,
            "completed": [s for s in required if s in completed],
            "missing_dependencies": missing,
            "dependencies_met": len(missing) == 0,
        }

    # ------------------------------------------------------------------
    # Step info
    # ------------------------------------------------------------------

    def _get_step_info(self, step_number: int) -> dict:
        """Return basic metadata about a step."""
        steps_data = self._source_index.get("steps", {})
        step_key = str(step_number)
        step_entry = steps_data.get(step_key, {})

        title = step_entry.get("title", f"Step {step_number}")
        phase = step_entry.get("phase", self._guess_phase(step_number))

        return {
            "number": step_number,
            "title": title,
            "phase": phase,
            "phase_name": _PHASE_NAMES.get(phase, ""),
            "source_chapter": step_entry.get("source_chapter", ""),
        }

    @staticmethod
    def _guess_phase(step_number: int) -> int:
        """Approximate the phase from a step number when metadata is absent."""
        if step_number <= 5:
            return 1
        if step_number <= 11:
            return 2
        if step_number <= 15:
            return 3
        if step_number <= 24:
            return 4
        if step_number <= 30:
            return 5
        if step_number <= 34:
            return 6
        if step_number <= 39:
            return 7
        if step_number <= 42:
            return 8
        if step_number <= 45:
            return 9
        if step_number <= 48:
            return 10
        if step_number <= 50:
            return 11
        return 12

    # ------------------------------------------------------------------
    # Layer 1: Book Quotes and Teaching
    # ------------------------------------------------------------------

    def _build_layer1(self, step_number: int) -> dict:
        """Build the Layer 1 guidance (book quotes and teaching summary)."""
        steps_data = self._source_index.get("steps", {})
        step_entry = steps_data.get(str(step_number), {})

        quotes: list[dict] = []

        # Extract text from each line range
        line_ranges = step_entry.get("line_ranges", [])
        for lr in line_ranges:
            start = lr.get("start", lr.get("line_start", 0))
            end = lr.get("end", lr.get("line_end", 0))
            topic = lr.get("topic", "")
            if start and end:
                text_lines = _read_lines_range(self._source_text_path, start, end)
                text = "\n".join(text_lines).strip()
                if text:
                    quotes.append({
                        "text": text,
                        "line_start": start,
                        "line_end": end,
                        "context": topic,
                    })

        # Also extract key_quotes entries (single-line highlights)
        key_quotes = step_entry.get("key_quotes", [])
        key_quote_contexts: list[str] = []
        for kq in key_quotes:
            line = kq.get("line", 0)
            context = kq.get("context", "")
            if line:
                text_lines = _read_lines_range(self._source_text_path, line, line)
                text = text_lines[0].strip() if text_lines else ""
                if text:
                    # Check this line is not already inside a range quote
                    already_included = any(
                        q["line_start"] <= line <= q["line_end"] for q in quotes
                    )
                    if not already_included:
                        quotes.append({
                            "text": text,
                            "line_start": line,
                            "line_end": line,
                            "context": context,
                        })
            if context:
                key_quote_contexts.append(context)

        # Build a teaching summary from the context strings
        teaching_summary = ""
        all_contexts = [lr.get("topic", "") for lr in line_ranges] + key_quote_contexts
        all_contexts = [c for c in all_contexts if c]
        if all_contexts:
            teaching_summary = (
                f"This step covers: {'; '.join(all_contexts)}. "
                f"The source text (Chapter: {step_entry.get('source_chapter', 'N/A')}) "
                f"provides practical guidance on these topics."
            )

        return {
            "quotes": quotes,
            "teaching_summary": teaching_summary,
        }

    # ------------------------------------------------------------------
    # Layer 2: References
    # ------------------------------------------------------------------

    def _build_layer2(
        self,
        step_number: int,
        override_mythologies: list[str] | None = None,
        override_authors: list[str] | None = None,
    ) -> dict:
        """Build the Layer 2 guidance (reference material from 16 databases).

        Searches ALL databases for sections relevant to the current step
        and pulls full content from every database that has matching
        material.  Fair representation is maintained by tracking usage
        counts, not by gating which databases are consulted.
        """
        all_myth_names = override_mythologies or self._get_all_db_names("mythology")
        all_auth_names = override_authors or self._get_all_db_names("author")

        # Collect relevant sections from ALL databases
        featured_mythologies = self._collect_featured_references(
            step_number, all_myth_names, "mythology"
        )
        featured_authors = self._collect_featured_references(
            step_number, all_auth_names, "author"
        )

        # Track usage for fair representation (all databases that
        # contributed content get their counters incremented)
        try:
            from engine.fair_representation import FairRepresentationManager
            frm = FairRepresentationManager(self._state_path)
            contributed_dbs = set()
            for ref in featured_mythologies + featured_authors:
                db_name = ref.get("database", "")
                if db_name and ref.get("content"):
                    contributed_dbs.add(db_name)
            for db_name in contributed_dbs:
                frm.record_usage(db_name)
            frm.save_state()
        except Exception:
            logger.debug("Could not update fair representation usage counts", exc_info=True)

        # Build cross-cutting patterns prompt across ALL databases
        all_db_names = all_myth_names + all_auth_names
        cross_cutting = self._build_cross_cutting_prompt(step_number, all_db_names)

        # Brief mentions are no longer needed since all databases are
        # fully consulted, but we keep the key for API compatibility
        brief_mentions: list[dict] = []

        logger.info(
            "Layer 2 built: %d mythology refs, %d author refs from %d databases",
            len(featured_mythologies), len(featured_authors),
            len(set(r.get("database", "") for r in featured_mythologies + featured_authors)),
        )

        return {
            "featured_mythologies": featured_mythologies,
            "featured_authors": featured_authors,
            "brief_mentions": brief_mentions,
            "cross_cutting_patterns": cross_cutting,
        }

    def _select_featured_databases(
        self,
        step_number: int,
        override_mythologies: list[str] | None,
        override_authors: list[str] | None,
    ) -> tuple[list[str], list[str], list[str], list[str]]:
        """Choose which databases to feature and which to brief-mention.

        If overrides are provided, uses those.  Otherwise, attempts to use
        the ``FairRepresentationManager``.  Falls back to simple rotation
        if fair_representation is not available.

        Returns (featured_myths, featured_auths, brief_myths, brief_auths).
        """
        # Try to import the fair representation system
        try:
            from engine.fair_representation import FairRepresentationManager
            frm = FairRepresentationManager(self._state_path)
            selection = frm.select_featured(step_number)
            frm.save_state()

            featured_myths = override_mythologies or selection["featured_mythologies"]
            featured_auths = override_authors or selection["featured_authors"]
            brief_myths = [m for m in selection.get("brief_mythologies", [])
                           if m not in featured_myths]
            brief_auths = [a for a in selection.get("brief_authors", [])
                           if a not in featured_auths]

            # If overrides were provided, recompute briefs
            if override_mythologies:
                all_myths = self._get_all_db_names("mythology")
                brief_myths = [m for m in all_myths if m not in featured_myths]
            if override_authors:
                all_auths = self._get_all_db_names("author")
                brief_auths = [a for a in all_auths if a not in featured_auths]

            return featured_myths, featured_auths, brief_myths, brief_auths
        except Exception:
            logger.exception("Failed to use FairRepresentationManager for source selection")

        # Fallback: simple rotation based on step number
        all_myths = self._get_all_db_names("mythology")
        all_auths = self._get_all_db_names("author")

        if override_mythologies:
            featured_myths = override_mythologies
        else:
            start = ((step_number - 1) * 4) % max(len(all_myths), 1)
            featured_myths = []
            for i in range(4):
                if all_myths:
                    featured_myths.append(all_myths[(start + i) % len(all_myths)])
            # Deduplicate while preserving order
            seen = set()
            featured_myths = [m for m in featured_myths if not (m in seen or seen.add(m))]

        if override_authors:
            featured_auths = override_authors
        else:
            start = ((step_number - 1) * 3) % max(len(all_auths), 1)
            featured_auths = []
            for i in range(3):
                if all_auths:
                    featured_auths.append(all_auths[(start + i) % len(all_auths)])
            seen = set()
            featured_auths = [a for a in featured_auths if not (a in seen or seen.add(a))]

        brief_myths = [m for m in all_myths if m not in featured_myths]
        brief_auths = [a for a in all_auths if a not in featured_auths]

        return featured_myths, featured_auths, brief_myths, brief_auths

    def _get_all_db_names(self, db_type: str) -> list[str]:
        """Return all database names of the given type ('mythology' or 'author')."""
        names = []
        for _key, db_info in self._databases.items():
            if db_info.get("type") == db_type:
                names.append(db_info["id"])
        return sorted(names)

    def _collect_featured_references(
        self,
        step_number: int,
        db_names: list[str],
        db_type: str,
    ) -> list[dict]:
        """Collect full-content reference entries for featured databases.

        For each database in *db_names*, finds the sections relevant to
        *step_number* and reads their content from the ``.md`` file.
        """
        results: list[dict] = []

        for db_name in db_names:
            db_info = self._find_db_info(db_name)
            if not db_info:
                continue

            file_path = str(self.root / db_info.get("file", ""))
            sections = db_info.get("sections", [])

            # Find sections relevant to this step
            relevant_sections = [
                s for s in sections
                if step_number in s.get("relevant_steps", [])
            ]

            if not relevant_sections:
                # No relevant sections for this step -- skip this database
                # rather than pulling irrelevant content
                continue

            for section in relevant_sections:
                title = section.get("title", "")
                line_start = section.get("line_start", 0)
                line_end = section.get("line_end", 0)

                # Try by section title first, fall back to line range
                content = _extract_md_section(file_path, title)
                if not content and line_start and line_end:
                    content = _extract_md_section_by_lines(file_path, line_start, line_end)

                # Truncate very long sections for manageability
                if len(content) > 3000:
                    content = content[:3000] + "\n\n[...truncated for length...]"

                relevance = (
                    f"This section from {db_info.get('name', db_name)} covers "
                    f"{title} and is tagged with: {', '.join(section.get('tags', []))}."
                )

                results.append({
                    "database": db_name,
                    "database_name": db_info.get("name", db_name),
                    "section": title,
                    "content": content,
                    "relevance": relevance,
                    "tags": section.get("tags", []),
                })

        return results

    def _collect_brief_mentions(
        self,
        step_number: int,
        db_names: list[str],
    ) -> list[dict]:
        """Collect one-liner brief mentions for non-featured databases."""
        results: list[dict] = []

        for db_name in db_names:
            db_info = self._find_db_info(db_name)
            if not db_info:
                continue

            sections = db_info.get("sections", [])

            # Find sections relevant to this step
            relevant_sections = [
                s for s in sections
                if step_number in s.get("relevant_steps", [])
            ]

            if relevant_sections:
                section = relevant_sections[0]
                one_liner = (
                    f"{db_info.get('name', db_name)} has relevant material in "
                    f"\"{section.get('title', '')}\" "
                    f"(tags: {', '.join(section.get('tags', []))})."
                )
            else:
                # No directly relevant section
                one_liner = (
                    f"{db_info.get('name', db_name)} -- no section directly "
                    f"tagged for this step, but may contain tangential material."
                )

            results.append({
                "database": db_name,
                "database_name": db_info.get("name", db_name),
                "section": relevant_sections[0].get("title", "") if relevant_sections else "",
                "one_liner": one_liner,
            })

        return results

    def _build_cross_cutting_prompt(self, step_number: int, db_names: list[str]) -> str:
        """Build a cross-cutting patterns block.

        This is raw material organised for Claude to synthesise.  It lists
        which databases have content relevant to this step and what tags
        overlap, so Claude can identify shared patterns across traditions.
        """
        tag_to_dbs: dict[str, list[str]] = {}

        for db_name in db_names:
            db_info = self._find_db_info(db_name)
            if not db_info:
                continue
            for section in db_info.get("sections", []):
                if step_number in section.get("relevant_steps", []):
                    for tag in section.get("tags", []):
                        tag_to_dbs.setdefault(tag, []).append(
                            db_info.get("name", db_name)
                        )

        if not tag_to_dbs:
            return "No cross-cutting tag patterns found for this step."

        lines: list[str] = [
            "CROSS-CUTTING PATTERNS (for synthesis):",
            f"The following tags are shared across multiple traditions for Step {step_number}:",
            "",
        ]
        for tag, dbs in sorted(tag_to_dbs.items()):
            unique_dbs = sorted(set(dbs))
            if len(unique_dbs) > 1:
                lines.append(f"  [{tag}] -- shared by: {', '.join(unique_dbs)}")
            else:
                lines.append(f"  [{tag}] -- {unique_dbs[0]}")

        lines.append("")
        lines.append(
            "When presenting references, look for patterns that appear across "
            "multiple traditions (e.g., similar pantheon structures, recurring "
            "monster origins, common settlement patterns) and highlight them."
        )

        return "\n".join(lines)

    def _find_db_info(self, db_name: str) -> dict | None:
        """Find the database metadata block by short name (e.g. 'greek')."""
        # Direct lookup by various key patterns
        for key, info in self._databases.items():
            if info.get("id") == db_name:
                return info
        # Try key-based lookup
        for prefix in ("mythologies/", "authors/"):
            full_key = prefix + db_name
            if full_key in self._databases:
                return self._databases[full_key]
        return None

    # ------------------------------------------------------------------
    # Layer 3: Actionable
    # ------------------------------------------------------------------

    def _build_layer3(self, step_number: int) -> dict:
        """Build the Layer 3 guidance (template info and actionable output)."""
        templates = self._step_templates.get(step_number, [])

        state = _safe_read_json(self._state_path, default={})
        entity_index = state.get("entity_index", {})
        completed_steps = set(state.get("completed_steps", []))

        # Aggregate template info
        template_ids: list[str] = []
        template_files: list[str] = []
        required_fields: list[str] = []
        recommended_fields: list[str] = []
        optional_fields: list[str] = []
        total_minimum_count = 0
        all_cross_refs: list[str] = []
        is_multi = False
        primary_entity_type = ""

        for tmpl in templates:
            tid = tmpl.get("id", "")
            template_ids.append(tid)
            template_files.append(tmpl.get("file", ""))
            total_minimum_count += tmpl.get("minimum_count", 1)
            all_cross_refs.extend(tmpl.get("cross_references", []))
            if tmpl.get("is_multi_instance"):
                is_multi = True
            if not primary_entity_type:
                primary_entity_type = tmpl.get("entity_type", "")

            # Load the actual template schema to get field info
            schema_path = self.root / tmpl.get("file", "")
            schema = _safe_read_json(str(schema_path), default={})
            if schema:
                req = schema.get("required", [])
                props = schema.get("properties", {})
                for field_name, field_def in props.items():
                    if field_name.startswith("_"):
                        continue
                    desc = field_def.get("description", field_name)
                    label = f"{field_name}: {desc}" if desc != field_name else field_name
                    if field_name in req:
                        if label not in required_fields:
                            required_fields.append(label)
                    elif field_def.get("x-recommended"):
                        if label not in recommended_fields:
                            recommended_fields.append(label)
                    else:
                        if label not in optional_fields:
                            optional_fields.append(label)

        # Count existing entities matching this step's templates
        existing_entities: list[dict] = []
        for eid, emeta in entity_index.items():
            if emeta.get("template_id") in template_ids:
                existing_entities.append({
                    "id": eid,
                    "name": emeta.get("name", eid),
                    "status": emeta.get("status", "draft"),
                    "template_id": emeta.get("template_id", ""),
                })
            elif primary_entity_type and emeta.get("entity_type") == primary_entity_type:
                existing_entities.append({
                    "id": eid,
                    "name": emeta.get("name", eid),
                    "status": emeta.get("status", "draft"),
                    "template_id": emeta.get("template_id", ""),
                })

        existing_count = len(existing_entities)

        # Check dependencies
        deps = self.get_step_dependencies(step_number)

        # Guided questions
        questions = _GUIDED_QUESTIONS.get(step_number, [])

        # Build the result
        result = {
            "template_id": template_ids[0] if len(template_ids) == 1 else template_ids,
            "template_file": template_files[0] if len(template_files) == 1 else template_files,
            "entity_type": primary_entity_type,
            "is_multi_instance": is_multi,
            "required_fields": required_fields,
            "recommended_fields": recommended_fields,
            "optional_fields": optional_fields,
            "cross_references": sorted(set(all_cross_refs)),
            "guided_questions": questions,
            "minimum_count": total_minimum_count,
            "existing_count": existing_count,
            "existing_entities": existing_entities,
            "dependencies_met": deps["dependencies_met"],
            "missing_dependencies": deps["missing_dependencies"],
        }

        # If no templates for this step, note it
        if not templates:
            result["template_id"] = None
            result["template_file"] = None
            result["note"] = (
                f"Step {step_number} does not have a dedicated template. "
                f"It may produce a written statement or strategy document."
            )

        return result


# ---------------------------------------------------------------------------
# Convenience: module-level factory
# ---------------------------------------------------------------------------

def create_chunk_puller(project_root: str = "C:/Worldbuilding-Interactive-Program") -> ChunkPuller:
    """Create and return a ChunkPuller instance with the default project root.

    Parameters
    ----------
    project_root : str
        Path to the project root.  Defaults to the standard location.

    Returns
    -------
    ChunkPuller
    """
    return ChunkPuller(project_root)
