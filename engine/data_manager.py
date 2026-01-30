"""
engine/data_manager.py -- Entity CRUD Operations for the Worldbuilding Interactive Program

Handles all entity creation, reading, updating, validation, search, and
cross-reference resolution. Every other system in the program calls the
DataManager rather than reading/writing entity files directly.

Also provides lore sync capabilities: every entity carries a ``_prose`` field
containing a human-readable narrative paragraph derived from the structured
fields.  The prose is auto-regenerated on every create/update unless the
user has supplied custom prose (indicated by ``_prose_custom: true``).

Usage:
    from engine.data_manager import DataManager

    dm = DataManager("C:/Worldbuilding-Interactive-Program")
    entity_id = dm.create_entity("god-profile", {"name": "Thorin Stormkeeper", ...})
    entity = dm.get_entity(entity_id)
    errors = dm.validate_entity(entity_id)
    refs = dm.get_cross_references(entity_id)
"""

import json
import os
import re
import copy
import secrets
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

try:
    import jsonschema
except ImportError:
    raise ImportError(
        "The 'jsonschema' package is required but not installed. "
        "Install it with: pip install jsonschema"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    """Convert a human-readable name to a URL-friendly slug.

    Examples:
        "Thorin Stormkeeper"  -> "thorin-stormkeeper"
        "The Celestial Court" -> "the-celestial-court"
        "Mira's Haven"       -> "miras-haven"
    """
    # Normalize unicode characters to ASCII equivalents where possible
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    # Lowercase
    text = text.lower()
    # Replace any non-alphanumeric character with a hyphen
    text = re.sub(r"[^a-z0-9]+", "-", text)
    # Strip leading/trailing hyphens and collapse runs of hyphens
    text = re.sub(r"-+", "-", text).strip("-")
    return text


def _generate_id(name: str) -> str:
    """Generate a unique entity ID in the format: slugified-name-XXXX.

    The 4-character hex suffix prevents collisions when two entities share
    the same name (unlikely but possible across different entity types).
    """
    slug = _slugify(name)
    if not slug:
        slug = "entity"
    suffix = secrets.token_hex(2)  # 4 hex chars
    return f"{slug}-{suffix}"


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _safe_read_json(path: str, default=None):
    """Read a JSON file, returning *default* if the file is missing or corrupt."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default
    except json.JSONDecodeError:
        return default


def _safe_write_json(path: str, data, *, indent: int = 2) -> None:
    """Write JSON to *path*, creating parent directories if needed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=indent, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Canon-claims extraction
# ---------------------------------------------------------------------------

def _extract_canon_claims(entity_data: dict, template_schema: dict) -> list:
    """Extract discrete factual claims from an entity's field values.

    Each claim is a short, self-contained statement of fact that the
    consistency checker (Sprint 3) can compare against all other claims
    in the world.  Cross-references are recorded so the checker knows
    which other entities are involved.

    Returns a list of dicts: [{"claim": str, "references": [str, ...]}, ...]
    """
    claims: list[dict] = []
    name = entity_data.get("name", entity_data.get("_meta", {}).get("id", "Unknown"))
    schema_props = template_schema.get("properties", {})

    for field_key, value in entity_data.items():
        # Skip metadata, internal fields, and empty values
        if field_key.startswith("_") or field_key in ("id", "canon_claims"):
            continue
        if value is None or value == "" or value == []:
            continue

        field_schema = schema_props.get(field_key, {})
        field_desc = field_schema.get("description", field_key.replace("_", " "))

        # --- Simple string fields ---
        if isinstance(value, str) and field_key != "name":
            claim_text = f"{name}'s {field_desc.lower().rstrip('.')} is: {value}"
            # Detect if this field is a cross-reference
            refs = []
            if "x-cross-reference" in field_schema:
                refs.append(value)
            claims.append({"claim": claim_text, "references": refs})

        # --- Array of strings ---
        elif isinstance(value, list) and value and isinstance(value[0], str):
            item_schema = field_schema.get("items", {})
            is_xref = "x-cross-reference" in item_schema
            claim_text = f"{name}'s {field_desc.lower().rstrip('.')} includes: {', '.join(str(v) for v in value)}"
            refs = list(value) if is_xref else []
            claims.append({"claim": claim_text, "references": refs})

        # --- Array of objects (relationships, species_breakdown, etc.) ---
        elif isinstance(value, list) and value and isinstance(value[0], dict):
            for idx, item in enumerate(value):
                parts = []
                refs = []
                for sub_key, sub_val in item.items():
                    if sub_val is None or sub_val == "":
                        continue
                    parts.append(f"{sub_key}: {sub_val}")
                    # Check for cross-reference in nested schema
                    item_props = field_schema.get("items", {}).get("properties", {})
                    sub_schema = item_props.get(sub_key, {})
                    if "x-cross-reference" in sub_schema and isinstance(sub_val, str):
                        refs.append(sub_val)
                if parts:
                    claim_text = f"{name} has {field_desc.lower().rstrip('.')} entry: {'; '.join(parts)}"
                    claims.append({"claim": claim_text, "references": refs})

        # --- Nested object (water_supply, leadership, old_town, etc.) ---
        elif isinstance(value, dict):
            parts = []
            for sub_key, sub_val in value.items():
                if sub_val is None or sub_val == "":
                    continue
                parts.append(f"{sub_key}: {sub_val}")
            if parts:
                claim_text = f"{name}'s {field_desc.lower().rstrip('.')} is: {'; '.join(parts)}"
                claims.append({"claim": claim_text, "references": []})

        # --- Numeric / boolean fields ---
        elif isinstance(value, (int, float, bool)):
            claim_text = f"{name}'s {field_desc.lower().rstrip('.')} is {value}"
            claims.append({"claim": claim_text, "references": []})

    return claims


# ---------------------------------------------------------------------------
# Prose generation helpers (module-level, called by DataManager methods)
# ---------------------------------------------------------------------------

def _safe_get(data: dict, *keys, default=""):
    """Safely traverse nested dicts, returning *default* if any key is missing."""
    current = data
    for k in keys:
        if isinstance(current, dict):
            current = current.get(k, default)
        else:
            return default
    if current is None:
        return default
    return current


def _join_list(items: list | None, conjunction: str = "and") -> str:
    """Join a list of strings with commas and a final conjunction."""
    if not items:
        return ""
    items = [str(i) for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} {conjunction} {items[1]}"
    return ", ".join(items[:-1]) + f", {conjunction} {items[-1]}"


def _prose_for_god(data: dict) -> str:
    """Generate a prose paragraph for a god-profile entity."""
    name = data.get("name", "An unnamed god")
    titles = data.get("titles")
    domain_primary = data.get("domain_primary", "")
    domains_secondary = data.get("domains_secondary", [])
    alignment = data.get("alignment", "")
    personality = data.get("personality", "")
    appearance = data.get("appearance", "")
    god_type = data.get("god_type", "god")
    power_level = data.get("power_level", "")
    origin = data.get("origin", "")
    patronage = data.get("patronage", "")
    pantheon_id = data.get("pantheon_id", "")
    mortal_interaction = data.get("mortal_interaction", "")
    reputation = data.get("reputation_among_mortals", "")
    symbol = data.get("symbol", "")
    residence = data.get("residence", "")

    parts = []

    # Opening: name + titles + type + domain
    opening = name
    if titles:
        opening += f", known as {_join_list(titles)},"
    type_label = god_type.replace("_", " ") if god_type else "god"
    if power_level:
        opening += f" is a {power_level} {type_label}"
    else:
        opening += f" is a {type_label}"
    if domain_primary:
        opening += f" of {domain_primary}"
    if domains_secondary:
        opening += f" who also holds dominion over {_join_list(domains_secondary)}"
    opening += "."
    parts.append(opening)

    # Personality + appearance
    if personality:
        parts.append(f"{personality.rstrip('.')}.")
    if appearance:
        app = appearance.rstrip(".")
        parts.append(f"{name} manifests as {app[0].lower()}{app[1:]}." if app else "")

    # Origin
    if origin:
        parts.append(f"{name} came into being through {origin.rstrip('.')}.")

    # Patronage
    if patronage:
        parts.append(f"{name} is the patron of {patronage.rstrip('.')}.")

    # Relationships (brief)
    relationships = data.get("relationships", [])
    if relationships:
        rel_parts = []
        for rel in relationships[:4]:  # cap to keep it concise
            target = rel.get("target_id", "another god")
            rtype = rel.get("relationship_type", "related to")
            desc = rel.get("description", "")
            if desc:
                rel_parts.append(desc.rstrip("."))
            else:
                rel_parts.append(f"{rtype} of {target}")
        if rel_parts:
            parts.append(f"{name} is {_join_list(rel_parts)}.")

    # Alignment + pantheon
    tail = ""
    if pantheon_id:
        # Avoid "the The ..." if pantheon name already starts with "The"
        article = "" if pantheon_id.lower().startswith("the ") else "the "
        tail += f"{name} belongs to {article}{pantheon_id} pantheon"
    if alignment:
        if tail:
            tail += f" and is aligned with the forces of {alignment}"
        else:
            tail += f"{name} is aligned with the forces of {alignment}"
    if tail:
        parts.append(tail.rstrip(".") + ".")

    # Symbol
    if symbol:
        parts.append(f"The symbol of {name} is {symbol.rstrip('.')}.")

    # Mortal interaction + reputation
    if mortal_interaction:
        interaction_map = {
            "active": "actively intervenes in mortal affairs",
            "distant": "remains distant from mortal affairs",
            "forbidden": "is forbidden from interacting with mortals",
            "selective": "selectively engages with mortal affairs",
            "disguised": "walks among mortals in disguise",
        }
        desc = interaction_map.get(mortal_interaction, mortal_interaction)
        parts.append(f"{name} {desc}.")
    if reputation:
        parts.append(f"Among mortals, {name} is {reputation.rstrip('.')}.")

    return " ".join(p for p in parts if p)


def _prose_for_settlement(data: dict) -> str:
    """Generate a prose paragraph for a settlement-profile entity."""
    name = data.get("name", "An unnamed settlement")
    stype = data.get("type", "settlement")
    population = data.get("population")
    location = data.get("location", "")
    terrain = data.get("terrain", "")
    climate = data.get("climate", "")
    sovereign = data.get("sovereign_power_id", "")
    reputation = data.get("reputation", "")
    fortifications = data.get("fortifications", "")
    slogan = data.get("slogan", "")
    setting = data.get("setting", "")
    general = data.get("general", "")

    parts = []

    # Opening: name + type + population + location
    opening = f"{name} is a"
    if stype:
        label = stype.replace("_", " ")
        if label[0] in "aeiou":
            opening = f"{name} is an"
        opening += f" {label}"
    if population:
        opening += f" of {population:,} inhabitants" if isinstance(population, int) else f" of {population} inhabitants"
    if location:
        opening += f", {location.rstrip('.')}"
    opening += "."
    parts.append(opening)

    # Setting / terrain / climate
    if setting:
        parts.append(setting.rstrip(".") + ".")
    elif terrain or climate:
        env = ""
        if terrain:
            env += f"The surrounding terrain is {terrain.rstrip('.')}"
        if climate:
            if env:
                env += f", with a {climate.rstrip('.')} climate"
            else:
                env = f"The climate is {climate.rstrip('.')}"
        parts.append(env + ".")

    # Sovereign
    if sovereign:
        parts.append(f"It belongs to {sovereign}.")

    # Leadership
    leadership = data.get("leadership")
    if isinstance(leadership, dict):
        leader_name = leadership.get("leader_name", "")
        leader_title = leadership.get("leader_title", "")
        if leader_name and leader_title:
            parts.append(f"It is governed by {leader_title} {leader_name}.")
        elif leader_name:
            parts.append(f"It is governed by {leader_name}.")

    # Reputation
    if reputation:
        parts.append(f"{name} is known for {reputation.rstrip('.')}.")

    # Fortifications
    if fortifications:
        parts.append(f"Its defenses include {fortifications.rstrip('.')}.")

    # History (first event)
    history = data.get("history", [])
    if history and isinstance(history, list) and len(history) > 0:
        first = history[0]
        if isinstance(first, dict):
            event = first.get("event", "")
            date = first.get("date", "")
            if event:
                hist = f"Founded"
                if date:
                    hist += f" {date}"
                hist += f", {event.rstrip('.')}."
                parts.append(hist)

    # General description
    if general:
        parts.append(general.rstrip(".") + ".")

    # Slogan
    if slogan:
        parts.append(f'Its motto is "{slogan.rstrip(".")}."')

    return " ".join(p for p in parts if p)


def _prose_for_species(data: dict) -> str:
    """Generate a prose paragraph for a species-profile entity."""
    name = data.get("name", "An unnamed species")
    famous_for = data.get("famous_for", "")
    disposition = data.get("disposition", "")
    disp_detail = data.get("disposition_detail", "")
    world_view = data.get("world_view", "")
    classification = data.get("classification", "species")
    general_desc = data.get("general_description", "")
    creator_god = data.get("creator_god", "")
    nicknames = data.get("nicknames", [])

    parts = []

    # Opening
    opening = f"The {name}"
    if nicknames:
        opening += f" (also called {_join_list(nicknames)})"
    opening += f" are a"
    if disposition:
        opening += f" {disposition}"
    label = classification if classification else "species"
    opening += f" {label}"
    if famous_for:
        opening += f" known for {famous_for.rstrip('.')}"
    opening += "."
    parts.append(opening)

    # Appearance
    appearance = data.get("appearance")
    if isinstance(appearance, dict):
        summary = appearance.get("summary", "")
        if summary:
            parts.append(summary.rstrip(".") + ".")
        body = appearance.get("body")
        if isinstance(body, dict):
            height = body.get("height_range", "")
            build = body.get("build", "")
            features = body.get("distinguishing_features", "")
            body_parts = []
            if height:
                body_parts.append(height)
            if build:
                body_parts.append(build)
            if features:
                body_parts.append(features)
            if body_parts:
                parts.append(f"Physically, they are {_join_list(body_parts)}.")

    # Habitat
    habitat = data.get("habitat")
    if isinstance(habitat, dict):
        preferred = habitat.get("preferred_terrain", "")
        settle = habitat.get("settlement_type", "")
        if preferred:
            parts.append(f"They prefer {preferred.rstrip('.')} terrain.")
        if settle:
            settle_map = {
                "isolated": "tend to live in isolated communities of their own kind",
                "joint": "commonly live alongside other species",
                "nomadic": "lead a nomadic existence",
                "mixed": "are found in both their own communities and mixed settlements",
            }
            desc = settle_map.get(settle, settle)
            parts.append(f"They {desc}.")

    # World view (key differentiator)
    if world_view:
        wv = world_view.rstrip(".")
        # Keep it to a sentence or two for the prose field
        if len(wv) > 200:
            wv = wv[:200].rsplit(" ", 1)[0] + "..."
        parts.append(wv + ".")

    # General description
    if general_desc:
        parts.append(general_desc.rstrip(".") + ".")

    # Creator god
    if creator_god:
        parts.append(f"They were created by {creator_god}.")

    # Disposition detail
    if disp_detail:
        parts.append(disp_detail.rstrip(".") + ".")

    return " ".join(p for p in parts if p)


def _prose_for_religion(data: dict) -> str:
    """Generate a prose paragraph for a religion-profile entity."""
    name = data.get("name", "An unnamed religion")
    gods = data.get("gods_worshiped", [])
    founding = data.get("founding_story", "")
    symbols = data.get("symbols", [])
    afterlife = data.get("afterlife_belief", "")
    place = data.get("place_in_society", "")
    clergy = data.get("clergy_structure", "")
    famous = data.get("famous_for", "")
    world_view = data.get("world_view", "")
    nicknames = data.get("nicknames", [])
    followers = data.get("followers", "")

    parts = []

    # Opening
    opening = f"{name}"
    if nicknames:
        opening += f" (also known as {_join_list(nicknames)})"
    opening += " is a"
    if gods:
        if len(gods) == 1:
            opening += f" religion devoted to {gods[0]}"
        else:
            opening += f" religion devoted to {_join_list(gods)}"
    else:
        opening += " religion"
    opening += "."
    parts.append(opening)

    # Famous for
    if famous:
        parts.append(f"It is famous for {famous.rstrip('.')}.")

    # Founding story (brief)
    if founding:
        fs = founding.rstrip(".")
        if len(fs) > 250:
            fs = fs[:250].rsplit(" ", 1)[0] + "..."
        parts.append(f"Its founding story recounts how {fs[0].lower()}{fs[1:]}.")

    # Symbols
    if symbols:
        parts.append(f"Its sacred symbols include {_join_list(symbols)}.")

    # Afterlife
    if afterlife:
        parts.append(f"Followers believe that {afterlife.rstrip('.')}.")

    # Clergy
    if clergy:
        parts.append(f"The clergy is organized as {clergy.rstrip('.')}.")

    # World view
    if world_view:
        parts.append(world_view.rstrip(".") + ".")

    # Place in society
    if place:
        parts.append(f"In society, the religion {place.rstrip('.')}.")

    # Followers
    if followers:
        parts.append(f"Its followers are {followers.rstrip('.')}.")

    return " ".join(p for p in parts if p)


def _prose_for_culture(data: dict) -> str:
    """Generate a prose paragraph for a culture-profile entity."""
    name = data.get("name", "An unnamed culture")
    desc = data.get("description", data.get("general_description", ""))
    values = data.get("core_values", data.get("values", []))
    customs = data.get("customs", "")
    language = data.get("language", "")
    arts = data.get("arts", data.get("art_forms", ""))
    famous = data.get("famous_for", "")

    parts = [f"{name} is a distinct cultural tradition."]
    if desc:
        parts.append(desc.rstrip(".") + ".")
    if values:
        if isinstance(values, list):
            parts.append(f"Its core values include {_join_list(values)}.")
        else:
            parts.append(f"Its core values center on {str(values).rstrip('.')}.")
    if customs:
        parts.append(customs.rstrip(".") + ".")
    if famous:
        parts.append(f"It is famous for {famous.rstrip('.')}.")
    if arts:
        if isinstance(arts, list):
            parts.append(f"Its artistic traditions include {_join_list(arts)}.")
        else:
            parts.append(str(arts).rstrip(".") + ".")
    return " ".join(p for p in parts if p)


def _prose_for_organization(data: dict) -> str:
    """Generate a prose paragraph for an organization-profile entity."""
    name = data.get("name", "An unnamed organization")
    org_type = data.get("type", data.get("organization_type", ""))
    purpose = data.get("purpose", data.get("mission", ""))
    leader = data.get("leader", data.get("leader_name", ""))
    members = data.get("membership", data.get("members", ""))
    famous = data.get("famous_for", data.get("reputation", ""))
    history = data.get("history", data.get("founding", ""))

    parts = [f"{name} is"]
    if org_type:
        parts[0] += f" a {org_type}"
    else:
        parts[0] += " an organization"
    parts[0] += "."
    if purpose:
        parts.append(f"Its purpose is {purpose.rstrip('.')}.")
    if leader:
        if isinstance(leader, str):
            parts.append(f"It is led by {leader}.")
    if famous:
        parts.append(f"It is known for {str(famous).rstrip('.')}.")
    if history:
        parts.append(str(history).rstrip(".") + ".")
    if members:
        parts.append(f"Its membership consists of {str(members).rstrip('.')}.")
    return " ".join(p for p in parts if p)


def _prose_for_armed_forces(data: dict) -> str:
    """Generate a prose paragraph for an armed-forces entity."""
    name = data.get("name", "An unnamed military force")
    force_type = data.get("type", data.get("force_type", ""))
    commander = data.get("commander", data.get("leader", ""))
    size = data.get("size", data.get("strength", ""))
    sovereign = data.get("sovereign_power_id", "")
    tactics = data.get("tactics", "")
    reputation = data.get("reputation", data.get("famous_for", ""))

    parts = [f"{name} is"]
    if force_type:
        parts[0] += f" a {force_type}"
    else:
        parts[0] += " a military force"
    if sovereign:
        parts[0] += f" serving {sovereign}"
    parts[0] += "."
    if size:
        parts.append(f"It numbers {size} strong." if isinstance(size, (int, float)) else f"Its strength is {str(size).rstrip('.')}.")
    if commander:
        parts.append(f"It is commanded by {str(commander).rstrip('.')}.")
    if tactics:
        parts.append(f"They are known for {tactics.rstrip('.')}.")
    if reputation:
        parts.append(f"{str(reputation).rstrip('.')}.")
    return " ".join(p for p in parts if p)


def _prose_for_monster(data: dict) -> str:
    """Generate a prose paragraph for a monster-profile entity."""
    name = data.get("name", "An unnamed creature")
    desc = data.get("description", data.get("general_description", ""))
    habitat = data.get("habitat", "")
    danger = data.get("danger_level", data.get("threat_level", ""))
    abilities = data.get("abilities", data.get("special_abilities", []))
    appearance = data.get("appearance", "")
    behavior = data.get("behavior", "")

    parts = [f"{name} is a"]
    if danger:
        parts[0] += f" {danger}"
    parts[0] += " creature."
    if desc:
        parts.append(desc.rstrip(".") + ".")
    elif appearance:
        if isinstance(appearance, str):
            parts.append(appearance.rstrip(".") + ".")
    if habitat:
        if isinstance(habitat, str):
            parts.append(f"It inhabits {habitat.rstrip('.')}.")
        elif isinstance(habitat, dict):
            pref = habitat.get("preferred_terrain", "")
            if pref:
                parts.append(f"It inhabits {pref.rstrip('.')} regions.")
    if abilities:
        if isinstance(abilities, list):
            parts.append(f"Its abilities include {_join_list(abilities)}.")
        else:
            parts.append(f"It possesses {str(abilities).rstrip('.')}.")
    if behavior:
        parts.append(behavior.rstrip(".") + ".")
    return " ".join(p for p in parts if p)


def _prose_for_magic_system(data: dict) -> str:
    """Generate a prose paragraph for a magic-system entity."""
    name = data.get("name", "An unnamed magic system")
    desc = data.get("description", data.get("general_description", data.get("overview", "")))
    source = data.get("source", data.get("magic_source", ""))
    limitations = data.get("limitations", data.get("costs", ""))
    practitioners = data.get("practitioners", data.get("users", ""))
    famous = data.get("famous_for", "")

    parts = [f"{name} is a system of magic."]
    if desc:
        parts.append(desc.rstrip(".") + ".")
    if source:
        parts.append(f"Its power is drawn from {str(source).rstrip('.')}.")
    if limitations:
        parts.append(f"Its limitations include {str(limitations).rstrip('.')}.")
    if practitioners:
        parts.append(f"It is practiced by {str(practitioners).rstrip('.')}.")
    if famous:
        parts.append(f"It is famous for {famous.rstrip('.')}.")
    return " ".join(p for p in parts if p)


def _prose_for_world_figure(data: dict) -> str:
    """Generate a prose paragraph for a world-figure entity."""
    name = data.get("name", "An unnamed figure")
    title = data.get("title", data.get("titles", ""))
    role = data.get("role", data.get("occupation", ""))
    species = data.get("species", data.get("species_id", ""))
    desc = data.get("description", data.get("general_description", ""))
    famous = data.get("famous_for", "")
    personality = data.get("personality", "")

    parts = []
    opening = name
    if title:
        if isinstance(title, list):
            opening += f", {_join_list(title)},"
        else:
            opening += f", {title},"
    opening += " is"
    if role:
        opening += f" a {role}"
    else:
        opening += " a notable figure"
    if species:
        opening += f" of the {species}"
    opening += "."
    parts.append(opening)
    if desc:
        parts.append(desc.rstrip(".") + ".")
    if personality:
        parts.append(personality.rstrip(".") + ".")
    if famous:
        parts.append(f"They are famous for {famous.rstrip('.')}.")
    return " ".join(p for p in parts if p)


def _prose_for_item(data: dict) -> str:
    """Generate a prose paragraph for an item-profile entity."""
    name = data.get("name", "An unnamed item")
    item_type = data.get("type", data.get("item_type", ""))
    desc = data.get("description", data.get("general_description", ""))
    creator = data.get("creator", data.get("created_by", ""))
    powers = data.get("powers", data.get("abilities", data.get("magical_properties", "")))
    history = data.get("history", "")
    famous = data.get("famous_for", "")

    parts = []
    opening = f"{name} is"
    if item_type:
        opening += f" a {item_type}"
    else:
        opening += " an item"
    if creator:
        opening += f" created by {creator}"
    opening += "."
    parts.append(opening)
    if desc:
        parts.append(desc.rstrip(".") + ".")
    if powers:
        if isinstance(powers, list):
            parts.append(f"It possesses {_join_list(powers)}.")
        else:
            parts.append(f"It possesses {str(powers).rstrip('.')}.")
    if history:
        parts.append(str(history).rstrip(".") + ".")
    if famous:
        parts.append(f"It is famous for {famous.rstrip('.')}.")
    return " ".join(p for p in parts if p)


def _prose_for_undead(data: dict) -> str:
    """Generate a prose paragraph for an undead entity."""
    name = data.get("name", "An unnamed undead")
    desc = data.get("description", data.get("general_description", ""))
    origin = data.get("origin", data.get("creation_method", ""))
    abilities = data.get("abilities", data.get("special_abilities", []))
    danger = data.get("danger_level", data.get("threat_level", ""))

    parts = [f"{name} is"]
    if danger:
        parts[0] += f" a {danger}"
    parts[0] += " undead creature."
    if desc:
        parts.append(desc.rstrip(".") + ".")
    if origin:
        parts.append(f"They arise through {str(origin).rstrip('.')}.")
    if abilities:
        if isinstance(abilities, list):
            parts.append(f"They possess {_join_list(abilities)}.")
        else:
            parts.append(f"They possess {str(abilities).rstrip('.')}.")
    return " ".join(p for p in parts if p)


def _prose_for_plant(data: dict) -> str:
    """Generate a prose paragraph for a plant entity."""
    name = data.get("name", "An unnamed plant")
    desc = data.get("description", data.get("general_description", ""))
    habitat = data.get("habitat", "")
    uses = data.get("uses", data.get("properties", []))
    appearance = data.get("appearance", "")

    parts = [f"{name} is a plant"]
    if habitat:
        if isinstance(habitat, str):
            parts[0] += f" found in {habitat.rstrip('.')}"
        elif isinstance(habitat, dict):
            pref = habitat.get("preferred_terrain", habitat.get("biome", ""))
            if pref:
                parts[0] += f" found in {pref.rstrip('.')}"
    parts[0] += "."
    if desc:
        parts.append(desc.rstrip(".") + ".")
    elif appearance:
        parts.append(str(appearance).rstrip(".") + ".")
    if uses:
        if isinstance(uses, list):
            parts.append(f"It is used for {_join_list(uses)}.")
        else:
            parts.append(f"It is used for {str(uses).rstrip('.')}.")
    return " ".join(p for p in parts if p)


def _prose_for_animal(data: dict) -> str:
    """Generate a prose paragraph for an animal entity."""
    name = data.get("name", "An unnamed animal")
    desc = data.get("description", data.get("general_description", ""))
    habitat = data.get("habitat", "")
    behavior = data.get("behavior", "")
    domesticated = data.get("domesticated", data.get("is_domesticated", None))
    uses = data.get("uses", [])

    parts = [f"{name} is"]
    if domesticated is True:
        parts[0] += " a domesticated animal"
    elif domesticated is False:
        parts[0] += " a wild animal"
    else:
        parts[0] += " an animal"
    parts[0] += "."
    if desc:
        parts.append(desc.rstrip(".") + ".")
    if habitat:
        if isinstance(habitat, str):
            parts.append(f"It is found in {habitat.rstrip('.')}.")
        elif isinstance(habitat, dict):
            pref = habitat.get("preferred_terrain", habitat.get("biome", ""))
            if pref:
                parts.append(f"It is found in {pref.rstrip('.')} regions.")
    if behavior:
        parts.append(behavior.rstrip(".") + ".")
    if uses:
        if isinstance(uses, list):
            parts.append(f"It is valued for {_join_list(uses)}.")
        else:
            parts.append(f"It is valued for {str(uses).rstrip('.')}.")
    return " ".join(p for p in parts if p)


def _prose_generic(data: dict, template_id: str) -> str:
    """Generate a generic prose paragraph for any entity type without a
    specific prose builder.  Lists all populated string fields in readable
    sentences."""
    name = data.get("name", template_id.replace("-", " ").title())

    type_label = template_id.replace("-profile", "").replace("-template", "")
    type_label = type_label.replace("-worksheet", "").replace("-catalog", "")
    type_label = type_label.replace("-overview", "").replace("-detail", "")
    type_label = type_label.replace("-", " ")
    parts = [f"{name} is a {type_label}."]

    # Prioritise commonly meaningful fields
    priority_fields = [
        "description", "general_description", "overview", "general",
        "famous_for", "reputation", "summary",
    ]
    used = {"name", "id", "_meta", "canon_claims", "_prose", "_prose_custom"}

    for field in priority_fields:
        val = data.get(field)
        if val and isinstance(val, str) and field not in used:
            parts.append(val.rstrip(".") + ".")
            used.add(field)

    # Then iterate remaining populated string fields
    for key, val in data.items():
        if key in used or key.startswith("_"):
            continue
        if isinstance(val, str) and val.strip():
            label = key.replace("_", " ")
            parts.append(f"Its {label} is {val.rstrip('.')}.")
            used.add(key)
        elif isinstance(val, list) and val and all(isinstance(i, str) for i in val):
            label = key.replace("_", " ")
            parts.append(f"Its {label} includes {_join_list(val)}.")
            used.add(key)

        # Keep the prose to a reasonable length
        if len(" ".join(parts)) > 800:
            break

    return " ".join(p for p in parts if p)


# Registry mapping template-id keywords to prose builders
_PROSE_BUILDERS: dict[str, callable] = {
    "god": _prose_for_god,
    "settlement": _prose_for_settlement,
    "species": _prose_for_species,
    "religion": _prose_for_religion,
    "culture": _prose_for_culture,
    "organization": _prose_for_organization,
    "armed-forces": _prose_for_armed_forces,
    "monster": _prose_for_monster,
    "undead": _prose_for_undead,
    "plant": _prose_for_plant,
    "animal": _prose_for_animal,
    "magic-system": _prose_for_magic_system,
    "world-figure": _prose_for_world_figure,
    "item": _prose_for_item,
}


def _detect_entity_type_key(template_id: str) -> str | None:
    """Match a template_id to the closest prose builder key.

    For example:
        "god-profile"           -> "god"
        "settlement-profile"    -> "settlement"
        "magic-system-profile"  -> "magic-system"
        "armed-forces-profile"  -> "armed-forces"
    """
    if not template_id:
        return None
    # Try exact prefix match from longest keys first
    for key in sorted(_PROSE_BUILDERS.keys(), key=len, reverse=True):
        if template_id.startswith(key):
            return key
        # Also try contains (e.g. "undead-monster-profile" -> "undead")
        if key in template_id:
            return key
    return None


def _validate_prose_against_data(prose: str, data: dict) -> list[str]:
    """Check whether user-written prose contradicts structured fields.

    Returns a list of warning strings.  This is a best-effort heuristic
    check -- it flags obvious mismatches (name mismatch, missing name) but
    does not attempt deep semantic analysis (that is left to the Layer 3
    LLM consistency checker in Sprint 3).
    """
    warnings: list[str] = []
    prose_lower = prose.lower()
    name = data.get("name", "")
    if name and name.lower() not in prose_lower:
        warnings.append(
            f"The custom prose does not mention the entity's name ('{name}'). "
            f"This may confuse readers."
        )
    # Check that alignment or disposition matches if present
    alignment = data.get("alignment", data.get("disposition", ""))
    if alignment and alignment.lower() not in prose_lower:
        warnings.append(
            f"The custom prose does not mention the entity's alignment/disposition "
            f"('{alignment}'). Consider including it for consistency."
        )
    return warnings


# ---------------------------------------------------------------------------
# DataManager
# ---------------------------------------------------------------------------

class DataManager:
    """Central manager for all entity CRUD operations.

    Parameters
    ----------
    project_root : str
        Absolute path to the Worldbuilding Interactive Program root directory,
        e.g. ``"C:/Worldbuilding-Interactive-Program"``.
    """

    # Mapping from template $id to entity folder name under user-world/entities/
    # Built dynamically from the template registry, but we keep sensible
    # fallbacks derived from the template id itself.
    _TYPE_FOLDER_OVERRIDES: dict[str, str] = {
        # Explicitly map template ids whose folder names differ from a naive
        # slug derivation.  Add more as templates are discovered.
    }

    def __init__(self, project_root: str):
        self.root = Path(project_root).resolve()
        self.entities_dir = self.root / "user-world" / "entities"
        self.state_path = self.root / "user-world" / "state.json"
        self.templates_dir = self.root / "templates"
        self.registry_path = self.root / "engine" / "template_registry.json"
        self.bookkeeping_dir = self.root / "bookkeeping"
        self.snapshots_dir = self.bookkeeping_dir / "revisions" / "snapshots"

        # Load the template registry (maps template_id -> metadata)
        self._registry: dict = self._load_registry()
        # Cache of loaded template schemas keyed by template $id
        self._schema_cache: dict[str, dict] = {}
        # Load state
        self._state: dict = self._load_state()

    # ------------------------------------------------------------------
    # Internal loaders
    # ------------------------------------------------------------------

    def _load_registry(self) -> dict:
        """Load template_registry.json.  Returns the 'templates' dict or
        an empty dict if the file is missing / empty."""
        data = _safe_read_json(str(self.registry_path), default={})
        templates = data.get("templates", {})
        # The registry might be a dict keyed by template id, or a list.
        # Normalise to a dict keyed by template $id.
        if isinstance(templates, list):
            return {t["id"]: t for t in templates if "id" in t}
        if isinstance(templates, dict):
            return templates
        return {}

    def _load_state(self) -> dict:
        """Load user-world/state.json."""
        default_state = {
            "current_step": 1,
            "current_phase": "foundation",
            "completed_steps": [],
            "in_progress_steps": [],
            "entity_index": {},
            "session_log": [],
        }
        state = _safe_read_json(str(self.state_path), default=default_state)
        # Ensure entity_index exists (older state files may lack it)
        if "entity_index" not in state:
            state["entity_index"] = {}
        return state

    def _save_state(self) -> None:
        """Persist the current state to user-world/state.json."""
        _safe_write_json(str(self.state_path), self._state)

    def _get_template_schema(self, template_id: str) -> dict:
        """Load a template JSON schema by its ``$id``.

        The schema is read from the templates/ directory tree and cached.
        Raises ``ValueError`` if the template cannot be found.
        """
        if template_id in self._schema_cache:
            return self._schema_cache[template_id]

        # Strategy 1: look up file path in registry
        if template_id in self._registry:
            rel_path = self._registry[template_id].get("file", "")
            if rel_path:
                full_path = self.root / rel_path
                schema = _safe_read_json(str(full_path))
                if schema:
                    self._schema_cache[template_id] = schema
                    return schema

        # Strategy 2: scan all template files for matching $id
        for json_path in sorted(self.templates_dir.rglob("*.json")):
            schema = _safe_read_json(str(json_path))
            if schema and schema.get("$id") == template_id:
                self._schema_cache[template_id] = schema
                return schema

        raise ValueError(
            f"Could not find a template with id '{template_id}'. "
            f"Check that the template exists in the templates/ directory "
            f"and that its '$id' field matches."
        )

    def _entity_type_for_template(self, template_id: str) -> str:
        """Determine the entity type (= subfolder name) for a template.

        Checks the registry first, then falls back to a slug derivation
        of the template id.
        """
        if template_id in self._registry:
            meta = self._registry[template_id]
            # entity_folder might be "user-world/entities/gods/"
            folder = meta.get("entity_folder", "")
            if folder:
                # Extract the last meaningful path segment
                parts = [p for p in folder.replace("\\", "/").rstrip("/").split("/") if p]
                if parts:
                    return parts[-1]
            # Or there might be an explicit entity_type
            etype = meta.get("entity_type", "")
            if etype:
                return etype

        # Fallback: derive from template id  (e.g. "god-profile" -> "gods")
        # This is a best-effort heuristic.
        base = template_id.replace("-profile", "").replace("-worksheet", "")
        base = base.replace("-template", "").replace("-overview", "")
        base = base.replace("-catalog", "").replace("-detail", "")
        # Naive pluralisation
        if not base.endswith("s"):
            base += "s"
        return base

    def _entity_folder(self, entity_type: str) -> Path:
        """Return the directory where entities of *entity_type* are stored,
        creating it if necessary."""
        folder = self.entities_dir / entity_type
        os.makedirs(folder, exist_ok=True)
        return folder

    def _entity_path_from_index(self, entity_id: str) -> str | None:
        """Look up the file path of an entity in the state index."""
        entry = self._state.get("entity_index", {}).get(entity_id)
        if entry:
            return entry.get("file_path")
        return None

    def _find_entity_file(self, entity_id: str) -> str | None:
        """Find the JSON file for *entity_id*, searching the index first,
        then falling back to a filesystem scan."""
        # Try index
        path = self._entity_path_from_index(entity_id)
        if path:
            full = self.root / path if not os.path.isabs(path) else Path(path)
            if full.exists():
                return str(full)

        # Fallback: walk entities directory
        for json_path in self.entities_dir.rglob("*.json"):
            data = _safe_read_json(str(json_path))
            if data and data.get("_meta", {}).get("id") == entity_id:
                return str(json_path)

        return None

    # ------------------------------------------------------------------
    # Prose generation (Lore Sync -- Task 3D)
    # ------------------------------------------------------------------

    def generate_prose(self, entity_data: dict, template_id: str) -> str:
        """Generate a human-readable prose paragraph from structured entity data.

        Parameters
        ----------
        entity_data : dict
            The entity's field values (excluding ``_meta``, ``id``,
            ``canon_claims``, and other internal fields).
        template_id : str
            The template ``$id`` (e.g. ``"god-profile"``).

        Returns
        -------
        str
            A readable narrative paragraph summarising the entity.
        """
        # Strip internal fields so prose builders only see content
        clean = {
            k: v for k, v in entity_data.items()
            if not k.startswith("_") and k not in ("id", "canon_claims")
        }
        return self._build_prose_for_type(clean, template_id)

    @staticmethod
    def _build_prose_for_type(data: dict, template_id: str) -> str:
        """Dispatch to the appropriate prose builder based on *template_id*.

        Falls back to the generic builder for unrecognised entity types.
        """
        key = _detect_entity_type_key(template_id)
        if key and key in _PROSE_BUILDERS:
            return _PROSE_BUILDERS[key](data)
        return _prose_generic(data, template_id)

    def _apply_prose(self, entity_doc: dict, template_id: str) -> None:
        """Add or regenerate the ``_prose`` field on *entity_doc* in-place.

        Rules:
        - If ``_prose_custom`` is True **and** ``_prose`` already has
          content, the existing prose is preserved (user override).
          A best-effort validation is run; any warnings are stored in
          ``_prose_warnings``.
        - Otherwise, ``_prose`` is auto-generated from the structured
          fields and ``_prose_custom`` is set to False.
        """
        if entity_doc.get("_prose_custom") is True and entity_doc.get("_prose"):
            # Custom prose -- validate but do not overwrite
            warnings = _validate_prose_against_data(
                entity_doc["_prose"], entity_doc,
            )
            entity_doc["_prose_warnings"] = warnings
            return

        # Auto-generate prose from structured fields
        clean = {
            k: v for k, v in entity_doc.items()
            if not k.startswith("_") and k not in ("id", "canon_claims")
        }
        entity_doc["_prose"] = self._build_prose_for_type(clean, template_id)
        entity_doc["_prose_custom"] = False
        entity_doc.pop("_prose_warnings", None)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_entity(self, template_id: str, data: dict) -> str:
        """Create a new entity from a template.

        Parameters
        ----------
        template_id : str
            The ``$id`` of the template schema (e.g. ``"god-profile"``).
        data : dict
            The entity's field values.  Must satisfy the template's
            ``required`` fields and pass schema validation.

        Returns
        -------
        str
            The auto-generated entity ID (e.g. ``"thorin-stormkeeper-a1b2"``).

        Raises
        ------
        ValueError
            If the template cannot be found.
        jsonschema.ValidationError
            If *data* does not pass schema validation (raised as a
            ``ValueError`` with a friendly message).
        """
        # Load the template schema
        schema = self._get_template_schema(template_id)

        # Validate data against the schema
        errors = self._validate_data(data, schema)
        if errors:
            friendly = self._format_validation_errors(errors, template_id)
            raise ValueError(friendly)

        # Determine entity type and folder
        entity_type = self._entity_type_for_template(template_id)
        folder = self._entity_folder(entity_type)

        # Generate unique ID
        name = data.get("name", template_id)
        entity_id = _generate_id(name)

        # Ensure no collision (extremely unlikely but handle it)
        while self._entity_path_from_index(entity_id) is not None:
            entity_id = _generate_id(name)

        # Build relative file path (relative to project root)
        filename = f"{entity_id}.json"
        file_path_abs = folder / filename
        file_path_rel = str(file_path_abs.relative_to(self.root)).replace("\\", "/")

        # Build _meta section
        now = _now_iso()
        meta = {
            "id": entity_id,
            "template_id": template_id,
            "entity_type": entity_type,
            "status": "draft",
            "created_at": now,
            "updated_at": now,
            "step_created": self._state.get("current_step", None),
            "file_path": file_path_rel,
        }

        # Assemble full entity document
        entity_doc = dict(data)
        entity_doc["_meta"] = meta
        entity_doc["id"] = entity_id

        # Extract canon claims
        entity_doc["canon_claims"] = _extract_canon_claims(data, schema)

        # --- Lore Sync: generate or preserve _prose ---
        # If the incoming data already has custom _prose, carry it through
        if "_prose" in data and data.get("_prose"):
            entity_doc["_prose"] = data["_prose"]
            entity_doc["_prose_custom"] = data.get("_prose_custom", True)
        self._apply_prose(entity_doc, template_id)

        # Write entity file
        _safe_write_json(str(file_path_abs), entity_doc)

        # Update state.json entity index
        self._state.setdefault("entity_index", {})[entity_id] = {
            "template_id": template_id,
            "entity_type": entity_type,
            "name": data.get("name", entity_id),
            "status": "draft",
            "file_path": file_path_rel,
            "created_at": now,
            "updated_at": now,
        }
        self._save_state()

        return entity_id

    def update_entity(self, entity_id: str, data: dict) -> None:
        """Update an existing entity's fields.

        A snapshot of the previous version is saved to
        ``bookkeeping/revisions/snapshots/`` before the update is written.

        Parameters
        ----------
        entity_id : str
            The entity to update.
        data : dict
            A dict of fields to merge into the entity.  Fields present in
            *data* overwrite the entity's current values; fields not present
            in *data* are left unchanged.

        Raises
        ------
        FileNotFoundError
            If the entity does not exist.
        ValueError
            If the merged data fails schema validation.
        """
        file_path = self._find_entity_file(entity_id)
        if not file_path:
            raise FileNotFoundError(
                f"Could not find entity '{entity_id}'. "
                f"It may have been deleted or the ID may be incorrect."
            )

        # Load current entity
        current = _safe_read_json(file_path)
        if current is None:
            raise FileNotFoundError(
                f"The file for entity '{entity_id}' exists but could not be read. "
                f"It may be corrupted."
            )

        # Save revision snapshot
        self._save_revision_snapshot(entity_id, current)

        # Determine template schema
        template_id = current.get("_meta", {}).get("template_id", "")
        schema = self._get_template_schema(template_id)

        # Merge new data into existing entity (shallow merge of top-level keys)
        merged = dict(current)
        for key, value in data.items():
            if key not in ("_meta", "id", "canon_claims"):
                merged[key] = value

        # Validate merged data (exclude _meta / internal fields for validation)
        validation_data = {
            k: v for k, v in merged.items()
            if not k.startswith("_") and k not in ("id", "canon_claims")
        }
        errors = self._validate_data(validation_data, schema)
        if errors:
            friendly = self._format_validation_errors(errors, template_id)
            raise ValueError(friendly)

        # Update metadata
        now = _now_iso()
        merged["_meta"]["updated_at"] = now

        # Re-extract canon claims
        merged["canon_claims"] = _extract_canon_claims(validation_data, schema)

        # --- Lore Sync: regenerate or preserve _prose ---
        # If the update data explicitly sets custom _prose, honour it
        if "_prose" in data and data.get("_prose"):
            merged["_prose"] = data["_prose"]
            merged["_prose_custom"] = data.get("_prose_custom", True)
        self._apply_prose(merged, template_id)

        # Write updated entity
        _safe_write_json(file_path, merged)

        # Update state index
        index_entry = self._state.get("entity_index", {}).get(entity_id, {})
        index_entry["updated_at"] = now
        if "name" in data:
            index_entry["name"] = data["name"]
        self._state.setdefault("entity_index", {})[entity_id] = index_entry
        self._save_state()

    def get_entity(self, entity_id: str) -> dict:
        """Load and return a single entity by ID.

        Parameters
        ----------
        entity_id : str
            The entity's unique identifier.

        Returns
        -------
        dict
            The full entity document including ``_meta`` and ``canon_claims``.

        Raises
        ------
        FileNotFoundError
            If the entity cannot be found.
        """
        file_path = self._find_entity_file(entity_id)
        if not file_path:
            raise FileNotFoundError(
                f"Could not find entity '{entity_id}'. "
                f"It may have been deleted or the ID may be incorrect."
            )
        data = _safe_read_json(file_path)
        if data is None:
            raise FileNotFoundError(
                f"The file for entity '{entity_id}' exists but could not be read."
            )
        return data

    def list_entities(self, entity_type: str | None = None) -> list[dict]:
        """Return all entities, optionally filtered by type.

        Parameters
        ----------
        entity_type : str, optional
            If provided, only entities of this type are returned
            (e.g. ``"gods"``, ``"settlements"``).

        Returns
        -------
        list[dict]
            A list of entity summary dicts from the state index, each
            containing: id, template_id, entity_type, name, status,
            file_path, created_at, updated_at.
        """
        index = self._state.get("entity_index", {})
        results = []
        for eid, meta in index.items():
            if entity_type and meta.get("entity_type") != entity_type:
                continue
            entry = dict(meta)
            entry["id"] = eid
            results.append(entry)
        return results

    def get_cross_references(self, entity_id: str) -> dict:
        """Find all entities that reference *entity_id* and all entities
        that *entity_id* references.

        Returns
        -------
        dict
            ``{"references": [...], "referenced_by": [...]}``.
            Each item is a dict with ``id``, ``name``, ``entity_type``,
            and ``relationship`` (the field or relationship that creates
            the link).
        """
        # Load the target entity
        try:
            target = self.get_entity(entity_id)
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Cannot find cross-references for '{entity_id}' because "
                f"the entity does not exist."
            )

        references: list[dict] = []      # entities this one points to
        referenced_by: list[dict] = []    # entities that point to this one

        # --- Outbound: scan target entity for cross-reference fields ---
        target_schema = self._get_template_schema(
            target.get("_meta", {}).get("template_id", "")
        )
        outbound_ids = self._extract_referenced_ids(target, target_schema)
        for ref_id, field_name in outbound_ids:
            try:
                ref_entity = self.get_entity(ref_id)
                references.append({
                    "id": ref_id,
                    "name": ref_entity.get("name", ref_id),
                    "entity_type": ref_entity.get("_meta", {}).get("entity_type", ""),
                    "relationship": field_name,
                })
            except FileNotFoundError:
                # Referenced entity does not exist (orphan reference)
                references.append({
                    "id": ref_id,
                    "name": ref_id,
                    "entity_type": "unknown",
                    "relationship": field_name,
                })

        # --- Inbound: scan all other entities for references to entity_id ---
        index = self._state.get("entity_index", {})
        for other_id, other_meta in index.items():
            if other_id == entity_id:
                continue
            other_path = self._find_entity_file(other_id)
            if not other_path:
                continue
            other_data = _safe_read_json(other_path)
            if not other_data:
                continue
            other_template_id = other_data.get("_meta", {}).get("template_id", "")
            try:
                other_schema = self._get_template_schema(other_template_id)
            except ValueError:
                continue
            other_refs = self._extract_referenced_ids(other_data, other_schema)
            for ref_id, field_name in other_refs:
                if ref_id == entity_id:
                    referenced_by.append({
                        "id": other_id,
                        "name": other_data.get("name", other_id),
                        "entity_type": other_data.get("_meta", {}).get("entity_type", ""),
                        "relationship": field_name,
                    })

        return {"references": references, "referenced_by": referenced_by}

    def validate_entity(self, entity_id: str) -> list[str]:
        """Run schema validation on an existing entity.

        Parameters
        ----------
        entity_id : str
            The entity to validate.

        Returns
        -------
        list[str]
            A list of human-readable error messages.  Empty if valid.
        """
        try:
            entity = self.get_entity(entity_id)
        except FileNotFoundError as exc:
            return [str(exc)]

        template_id = entity.get("_meta", {}).get("template_id", "")
        try:
            schema = self._get_template_schema(template_id)
        except ValueError as exc:
            return [str(exc)]

        # Strip internal fields before validation
        validation_data = {
            k: v for k, v in entity.items()
            if not k.startswith("_") and k not in ("id", "canon_claims")
        }
        errors = self._validate_data(validation_data, schema)
        return [self._humanize_error(e) for e in errors]

    def search_entities(self, query: str) -> list[dict]:
        """Search entity names, tags, and descriptions for a keyword.

        This is a simple in-memory keyword search.  It will be upgraded to
        SQLite FTS5 in Sprint 3 for much faster results.

        Parameters
        ----------
        query : str
            The search term (case-insensitive substring match).

        Returns
        -------
        list[dict]
            Matching entity summaries (same shape as ``list_entities``).
        """
        if not query or not query.strip():
            return []

        query_lower = query.strip().lower()
        results = []
        index = self._state.get("entity_index", {})

        for eid, meta in index.items():
            # Check the index-level name first (fast path)
            name = meta.get("name", "")
            if query_lower in name.lower():
                entry = dict(meta)
                entry["id"] = eid
                results.append(entry)
                continue

            # Load the full entity to search deeper fields
            file_path = self._find_entity_file(eid)
            if not file_path:
                continue
            entity = _safe_read_json(file_path)
            if not entity:
                continue

            if self._entity_matches_query(entity, query_lower):
                entry = dict(meta)
                entry["id"] = eid
                results.append(entry)

        return results

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _validate_data(self, data: dict, schema: dict) -> list:
        """Validate *data* against a JSON Schema.

        Returns a list of ``jsonschema.ValidationError`` instances (empty
        if the data is valid).
        """
        # Build a validation-only copy of the schema.  We remove custom
        # fields that are not part of standard JSON Schema (step, phase,
        # source_chapter, x-cross-references, x-cross-reference, $id that
        # collides with jsonschema's internal use) to prevent validation
        # noise.
        clean_schema = self._clean_schema_for_validation(schema)

        validator_cls = jsonschema.Draft202012Validator
        validator = validator_cls(clean_schema)
        return list(validator.iter_errors(data))

    @staticmethod
    def _clean_schema_for_validation(schema: dict) -> dict:
        """Return a copy of *schema* stripped of custom extension fields
        so that ``jsonschema`` does not choke on them."""
        skip_keys = {
            "$id", "step", "phase", "source_chapter",
            "x-cross-references",
        }
        clean = {}
        for key, value in schema.items():
            if key in skip_keys:
                continue
            if isinstance(value, dict):
                clean[key] = DataManager._clean_schema_deep(value)
            elif isinstance(value, list):
                clean[key] = [
                    DataManager._clean_schema_deep(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                clean[key] = value
        return clean

    @staticmethod
    def _clean_schema_deep(obj: dict) -> dict:
        """Recursively remove ``x-cross-reference`` (and similar custom
        keywords) from nested schema objects."""
        skip_keys = {"x-cross-reference", "x-cross-references"}
        result = {}
        for key, value in obj.items():
            if key in skip_keys:
                continue
            if isinstance(value, dict):
                result[key] = DataManager._clean_schema_deep(value)
            elif isinstance(value, list):
                result[key] = [
                    DataManager._clean_schema_deep(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                result[key] = value
        return result

    @staticmethod
    def _format_validation_errors(errors: list, template_id: str) -> str:
        """Format a list of validation errors into a single friendly message."""
        lines = [
            f"The data for template '{template_id}' has some issues that need fixing:\n"
        ]
        for i, err in enumerate(errors, 1):
            lines.append(f"  {i}. {DataManager._humanize_error(err)}")
        lines.append(
            "\nPlease correct these issues and try again. "
            "If you are unsure what a field expects, check the template description."
        )
        return "\n".join(lines)

    @staticmethod
    def _humanize_error(error) -> str:
        """Convert a ``jsonschema.ValidationError`` into plain English."""
        path = " -> ".join(str(p) for p in error.absolute_path) if error.absolute_path else "(root)"
        msg = error.message
        # Make common messages friendlier
        if "'required'" in str(error.validator) or error.validator == "required":
            return f"Missing required field at {path}: {msg}"
        if error.validator == "type":
            return f"Wrong data type at '{path}': {msg}"
        if error.validator == "enum":
            return f"Invalid value at '{path}': {msg}"
        if error.validator == "minItems":
            return f"Not enough items at '{path}': {msg}"
        return f"Issue at '{path}': {msg}"

    # ------------------------------------------------------------------
    # Cross-reference extraction
    # ------------------------------------------------------------------

    def _extract_referenced_ids(self, entity: dict, schema: dict) -> list[tuple[str, str]]:
        """Walk an entity and its schema to find all cross-referenced IDs.

        Returns a list of ``(referenced_entity_id, field_name)`` tuples.
        """
        refs: list[tuple[str, str]] = []
        props = schema.get("properties", {})

        for field_key, field_schema in props.items():
            value = entity.get(field_key)
            if value is None:
                continue

            # Direct cross-reference field (string)
            if "x-cross-reference" in field_schema and isinstance(value, str) and value:
                refs.append((value, field_key))

            # Array of cross-reference strings
            elif isinstance(value, list):
                item_schema = field_schema.get("items", {})
                if "x-cross-reference" in item_schema:
                    for v in value:
                        if isinstance(v, str) and v:
                            refs.append((v, field_key))
                # Array of objects with nested cross-references
                elif isinstance(item_schema, dict) and "properties" in item_schema:
                    for item in value:
                        if not isinstance(item, dict):
                            continue
                        for sub_key, sub_schema in item_schema["properties"].items():
                            if "x-cross-reference" in sub_schema:
                                sub_val = item.get(sub_key)
                                if isinstance(sub_val, str) and sub_val:
                                    refs.append((sub_val, f"{field_key}.{sub_key}"))

        return refs

    # ------------------------------------------------------------------
    # Search helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _entity_matches_query(entity: dict, query_lower: str) -> bool:
        """Return True if *query_lower* appears anywhere in the entity's
        searchable text fields (name, tags, description, notes,
        canon_claims, titles)."""
        searchable_fields = [
            "name", "description", "notes", "titles", "tags",
            "reputation", "local_lore", "slogan",
            "domain_primary", "domains_secondary", "personality",
        ]
        for field in searchable_fields:
            val = entity.get(field)
            if val is None:
                continue
            if isinstance(val, str) and query_lower in val.lower():
                return True
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, str) and query_lower in item.lower():
                        return True

        # Search canon_claims text
        for claim in entity.get("canon_claims", []):
            claim_text = claim.get("claim", "") if isinstance(claim, dict) else str(claim)
            if query_lower in claim_text.lower():
                return True

        return False

    # ------------------------------------------------------------------
    # Revision snapshots
    # ------------------------------------------------------------------

    def _save_revision_snapshot(self, entity_id: str, entity_data: dict) -> str:
        """Save a timestamped snapshot of an entity before it is modified.

        Returns the absolute path to the saved snapshot file.
        """
        os.makedirs(str(self.snapshots_dir), exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"{entity_id}_{timestamp}.json"
        snapshot_path = self.snapshots_dir / filename
        _safe_write_json(str(snapshot_path), entity_data)
        return str(snapshot_path)

    # ------------------------------------------------------------------
    # Convenience / state helpers
    # ------------------------------------------------------------------

    def reload_state(self) -> None:
        """Re-read state.json from disk.  Useful after external changes."""
        self._state = self._load_state()

    def get_state(self) -> dict:
        """Return a copy of the current in-memory state."""
        return copy.deepcopy(self._state)

    def set_entity_status(self, entity_id: str, status: str) -> None:
        """Change an entity's status (e.g. from 'draft' to 'canon').

        Parameters
        ----------
        entity_id : str
            The entity to update.
        status : str
            New status value -- typically ``"draft"`` or ``"canon"``.
        """
        if status not in ("draft", "canon"):
            raise ValueError(
                f"Invalid status '{status}'. Must be 'draft' or 'canon'."
            )

        entity = self.get_entity(entity_id)
        old_status = entity.get("_meta", {}).get("status", "draft")
        entity["_meta"]["status"] = status
        entity["_meta"]["updated_at"] = _now_iso()

        file_path = self._find_entity_file(entity_id)
        _safe_write_json(file_path, entity)

        # Update state index
        index_entry = self._state.get("entity_index", {}).get(entity_id, {})
        index_entry["status"] = status
        index_entry["updated_at"] = entity["_meta"]["updated_at"]
        self._state["entity_index"][entity_id] = index_entry
        self._save_state()
