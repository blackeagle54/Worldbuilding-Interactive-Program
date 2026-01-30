# Phase 2 Implementation Plan

**Purpose:** Turn the 52-step progression map and 84 template list into a working system that can guide a user through worldbuilding with intelligent reference support.

**Date:** January 30, 2026

---

## Table of Contents

1. [What Phase 2 Produces](#what-phase-2-produces)
2. [Architecture Overview](#architecture-overview)
3. [Task Breakdown and Order](#task-breakdown-and-order)
4. [Task A: Template Creation (84 Templates)](#task-a-template-creation-84-templates)
5. [Task B: Data Schema (User World Storage)](#task-b-data-schema-user-world-storage)
6. [Task C: Chunk Pulling System](#task-c-chunk-pulling-system)
7. [Task D: Reference Database Index](#task-d-reference-database-index)
8. [Task E: Hooks Setup](#task-e-hooks-setup)
9. [Task F: Knowledge Graph Population](#task-f-knowledge-graph-population)
10. [Dependency Map](#dependency-map)
11. [Execution Order](#execution-order)

---

## What Phase 2 Produces

By the end of Phase 2, the project will have:

1. **84 JSON schema templates** -- one for every template in the progression map. Each defines what fields exist, which are required, which are optional, and which cross-reference other templates.

2. **A user data folder structure** -- where the user's actual worldbuilding data lives as they fill out templates. JSON files organized by progression phase, with cross-reference IDs linking entities together.

3. **A chunk-pulling engine** -- a Python script that, given a progression step number, automatically:
   - Extracts the relevant quotes from the source book (`source-text.txt`)
   - Queries all 16 reference databases for relevant examples
   - Synthesizes the material into the three-layer guidance format (Book Quotes, Reference Synthesis, Actionable Output)

4. **A reference index** -- a structured JSON index of all 16 reference databases, mapping their sections to progression steps so the chunk-pulling system knows where to look.

5. **Hook scripts** -- Python scripts wired into Claude Code hooks that inject the right context at the right time and enforce progression rules.

6. **A knowledge graph seed** -- all 16 reference databases indexed into a queryable knowledge graph (using the Anthropic MCP Knowledge Graph server) so that cross-database queries are fast and entity relationships are explicit.

---

## Architecture Overview

```
C:\Worldbuilding-Interactive-Program\
|
|-- source-text.txt                    # The Ellefson book (read-only)
|-- reference-databases\               # 16 .md files (read-only)
|   |-- mythologies\                   # 10 mythology databases
|   |-- authors\                       # 6 author databases
|
|-- templates\                         # [NEW] 84 JSON schema files
|   |-- phase01-foundation\            # Templates 1-4 (Steps 1-5)
|   |-- phase02-cosmology\             # Templates 5-9 (Steps 6-11)
|   |-- phase03-land\                  # Templates 10-12 (Steps 12-15)
|   |-- phase04-life\                  # Templates 13-20 (Steps 16-24)
|   |-- phase05-civilization\          # Templates 21-26 (Steps 25-30)
|   |-- phase06-society\              # Templates 27-46 (Steps 31-34)
|   |-- phase07-supernatural\          # Templates 47-59 (Steps 35-39)
|   |-- phase08-history\               # Templates 60-63 (Steps 40-42)
|   |-- phase09-language\              # Templates 64-70 (Steps 43-45)
|   |-- phase10-travel\                # Templates 71-77 (Steps 46-48)
|   |-- phase11-finishing\             # Templates 78-82 (Steps 49-50)
|   |-- phase12-integration\           # Templates 83-84 (Steps 51-52)
|
|-- user-world\                        # [NEW] Where the user's data lives
|   |-- state.json                     # Current step, completed steps, etc.
|   |-- entities\                      # One JSON file per created entity
|   |   |-- gods\
|   |   |-- species\
|   |   |-- ... (one folder per entity type)
|   |-- worksheets\                    # Completed worksheets/checklists
|   |-- timelines\                     # History timeline entries
|   |-- registries\                    # Name registry, settlement spreadsheet, etc.
|
|-- engine\                            # [NEW] The chunk-pulling and orchestration code
|   |-- chunk_puller.py                # Main engine: given a step, produce guidance
|   |-- reference_index.json           # Maps step -> relevant DB sections
|   |-- source_index.json              # Maps step -> relevant source-text line ranges
|   |-- template_registry.json         # Master list of all 84 templates with metadata
|   |-- cross_reference.py             # Validates cross-references between entities
|   |-- fair_representation.py         # Ensures balanced DB sampling
|
|-- hooks\                             # [NEW] Hook scripts for Claude Code
|   |-- inject_step_context.py         # UserPromptSubmit: inject current step info
|   |-- validate_writes.py             # PostToolUse: validate data after writes
|   |-- session_start.py               # SessionStart: load project state
|   |-- check_completion.py            # Stop: verify step requirements met
|
|-- .claude\
|   |-- settings.json                  # Hook configuration
|   |-- rules\                         # Rule files for Claude Code
```

---

## Task Breakdown and Order

Here is the dependency graph. Tasks connected by arrows must happen in order. Tasks on the same level can be done in parallel.

```
Task A: Create 84 Templates (JSON schemas)
Task B: Design Data Schema (user-world/ structure)
    |
    +--> These two can be done in parallel, but both
    |    must finish before Task C.
    |
    v
Task D: Build Reference Index (maps steps to DB sections)
    |
    |  (can run in parallel with A and B)
    |
    v
Task C: Build Chunk-Pulling Engine
    |
    |  (needs A, B, and D to be done)
    |
    v
Task E: Set Up Hooks
    |
    |  (needs C to exist; hooks call the engine)
    |
    v
Task F: Populate Knowledge Graph
    |
    |  (needs D; can start once the index exists)
    |  (can run in parallel with E)
```

**Summary of order:**
1. Tasks A, B, and D can all start immediately and run in parallel.
2. Task C starts after A, B, and D are done.
3. Tasks E and F start after C and D respectively; they can run in parallel with each other.

---

## Task A: Template Creation (84 Templates)

### What Each Template Is

Each template is a JSON Schema file (`.json`) that defines:
- **`$id`**: Unique identifier (e.g., `"god-profile"`)
- **`title`**: Human-readable name (e.g., `"God Profile Template"`)
- **`description`**: What this template is for
- **`step`**: Which progression step first uses this template
- **`phase`**: Which progression phase it belongs to
- **`source_chapter`**: Which book chapter it comes from
- **`properties`**: Every field the user can fill in
- **`required`**: Which fields must be filled in (vs. optional)
- **`cross_references`**: Which fields reference entities from other templates

### Example Template: God Profile Template (#6)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "god-profile",
  "title": "God Profile Template",
  "description": "Defines a single deity in the world's pantheon. Each god needs at minimum: a domain, an alignment, a symbol, and at least one relationship to another god.",
  "step": 7,
  "phase": 2,
  "source_chapter": "V1 Ch2 -- Creating Gods",
  "type": "object",
  "properties": {
    "id": {
      "type": "string",
      "description": "Unique identifier for this god (auto-generated)"
    },
    "name": {
      "type": "string",
      "description": "The god's primary name"
    },
    "titles": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Alternate names, epithets, or titles"
    },
    "domain_primary": {
      "type": "string",
      "description": "The god's primary domain (war, love, death, wisdom, etc.)"
    },
    "domains_secondary": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Secondary domains or areas of influence"
    },
    "alignment": {
      "type": "string",
      "enum": ["good", "neutral", "evil", "complex"],
      "description": "The god's moral alignment"
    },
    "symbol": {
      "type": "string",
      "description": "The god's primary symbol (used in religious iconography)"
    },
    "appearance": {
      "type": "string",
      "description": "Physical appearance when manifesting"
    },
    "personality": {
      "type": "string",
      "description": "Core personality traits and behavioral tendencies"
    },
    "power_level": {
      "type": "string",
      "enum": ["supreme", "greater", "intermediate", "lesser", "demigod"],
      "description": "Relative power level within the pantheon"
    },
    "origin": {
      "type": "string",
      "description": "How this god came into being"
    },
    "residence": {
      "type": "string",
      "description": "Where this god lives (divine realm, physical location, etc.)"
    },
    "vulnerability": {
      "type": "string",
      "description": "What can weaken or threaten this god"
    },
    "relationships": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "target_id": {
            "type": "string",
            "description": "ID of the related god",
            "x-cross-reference": "god-profile"
          },
          "relationship_type": {
            "type": "string",
            "enum": ["parent", "child", "spouse", "sibling", "rival", "ally", "enemy", "creator", "servant"]
          },
          "description": {
            "type": "string"
          }
        }
      },
      "description": "Relationships to other gods. At least one required.",
      "minItems": 1
    },
    "species_created": {
      "type": "array",
      "items": {
        "type": "string",
        "x-cross-reference": "species-profile"
      },
      "description": "Species this god created or influenced"
    },
    "myths_featured_in": {
      "type": "array",
      "items": {
        "type": "string",
        "x-cross-reference": "mythology-worksheet"
      },
      "description": "Mythology worksheets that feature this god"
    },
    "worship_notes": {
      "type": "string",
      "description": "Brief notes on how this god is worshiped (expanded in Religion Profile)"
    },
    "pantheon_id": {
      "type": "string",
      "x-cross-reference": "pantheon-overview",
      "description": "Which pantheon this god belongs to"
    },
    "notes": {
      "type": "string",
      "description": "Freeform notes"
    }
  },
  "required": ["name", "domain_primary", "alignment", "symbol", "relationships", "pantheon_id"],
  "x-cross-references": {
    "pantheon-overview": "This god belongs to a pantheon defined in the Pantheon Overview Sheet",
    "mythology-worksheet": "This god appears in myths defined in Mythology Worksheets",
    "species-profile": "This god may have created species defined in Species Profiles",
    "religion-profile": "This god may be worshiped through religions defined in Religion Profiles"
  }
}
```

### How Cross-References Work

Every field that points to another entity uses the custom keyword `"x-cross-reference"` with the target template's `$id`. This tells the system:
- When displaying this field, offer a picker of existing entities of that type
- When validating, confirm the referenced entity actually exists
- When generating a report, trace all connections

### Template File Naming Convention

Each template file is named with its number and a slug:
```
templates/phase02-cosmology/06-god-profile.json
templates/phase02-cosmology/07-mythology-worksheet.json
templates/phase03-land/10-continent-profile.json
```

### Complete Template List with File Paths

Here is every template, its file path, and a brief note on its fields. The fields listed are the **key fields** -- the actual schema will have more.

**Phase 1: Foundation (4 templates)**

| # | Template | File | Key Fields |
|---|----------|------|------------|
| 1 | World Building Strategy Worksheet | `phase01-foundation/01-world-building-strategy.json` | scope, career_length, primary_medium, stories_planned, exposition_strategy |
| 2 | Analogue Modification Log | `phase01-foundation/02-analogue-modification-log.json` | earth_source, original_traits[], change_1, change_2, change_3, new_name, rationale |
| 3 | Worldbuilding Goals Worksheet | `phase01-foundation/03-worldbuilding-goals.json` | primary_goal, time_commitment, required_elements[], optional_elements[], priority_order[] |
| 4 | File Organization Template | `phase01-foundation/04-file-organization.json` | folder_structure, naming_convention, backup_plan, changes_file_location |

**Phase 2: Cosmology (5 templates)**

| # | Template | File | Key Fields |
|---|----------|------|------------|
| 5 | Pantheon Overview Sheet | `phase02-cosmology/05-pantheon-overview.json` | pantheon_name, organization_type, god_count, power_hierarchy, governing_rules, gods_are_real |
| 6 | God Profile Template | `phase02-cosmology/06-god-profile.json` | (see full example above) |
| 7 | Mythology Worksheet | `phase02-cosmology/07-mythology-worksheet.json` | myth_type (creation/end-of-world/other), title, gods_involved[], what_happened, what_is_true, what_inhabitants_believe, cultural_impact |
| 8 | Planet Profile Template | `phase02-cosmology/08-planet-profile.json` | star_type, rotation_direction, moon_count, moons[], axial_tilt, equator_position, prevailing_winds, constellations[] |
| 9 | Climate Zone Reference Sheet | `phase02-cosmology/09-climate-zone-reference.json` | zones[] (each with: name, latitude_range, temperature, precipitation, vegetation, species_found[]) |

**Phase 3: The Land (3 templates)**

| # | Template | File | Key Fields |
|---|----------|------|------------|
| 10 | Continent Profile Template | `phase03-land/10-continent-profile.json` | name, hemisphere, latitude_range, shape_description, plate_boundaries[], water_bodies[], other_continents[] |
| 11 | Water Body Reference Sheet | `phase03-land/11-water-body-reference.json` | name, type (ocean/sea/bay/strait/lake/river), location, connected_to[], significance |
| 12 | Land Feature Catalog Template | `phase03-land/12-land-feature-catalog.json` | name, type (mountain/river/lake/forest/desert/wetland/grassland), subtype, location, rain_shadow_direction, connected_features[], species_found[], sovereign_powers_nearby[] |

**Phase 4: Life (8 templates)**

| # | Template | File | Key Fields |
|---|----------|------|------------|
| 13 | Race Hierarchy Chart | `phase04-life/13-race-hierarchy-chart.json` | species_id, races[] (each with: name, parent_species, distinguishing_traits, habitat, disposition) |
| 14 | Species Profile Template | `phase04-life/14-species-profile.json` | name, habitat, disposition, creator_god, appearance, senses, world_view, government_type, language, customs, characteristics, technology_level, races[] |
| 15 | Species Relationship Matrix | `phase04-life/15-species-relationship-matrix.json` | species_a, species_b, relationship_type (ally/enemy/neutral/complicated), historical_events[], stereotypes_a_of_b, stereotypes_b_of_a |
| 16 | Products-to-Source Mapping Table | `phase04-life/16-products-to-source-mapping.json` | product_name, product_category, source_type (plant/animal), source_id, habitat, notes |
| 17 | Plant Profile Template | `phase04-life/17-plant-profile.json` | name, type, habitat, appearance, uses[], rarity, cultural_significance |
| 18 | Animal Profile Template | `phase04-life/18-animal-profile.json` | name, type (mammal/bird/reptile/etc.), habitat, appearance, behavior, uses[], domesticated, rarity |
| 19 | Monster Profile Template | `phase04-life/19-monster-profile.json` | name, origin (accidental/designed/evolved), motivation, lair_description, lair_contents[], appearance, abilities[], weakness, habitat, creator_god, myths_associated[] |
| 20 | Undead Type Profile Template | `phase04-life/20-undead-type-profile.json` | name, type, origin_method, prerequisites, goals[], behaviors[], destruction_method, cultural_burial_customs_inspired[], appearance |

**Phase 5: Civilization (6 templates)**

| # | Template | File | Key Fields |
|---|----------|------|------------|
| 21 | Sovereign Power Profile Template | `phase05-civilization/21-sovereign-power-profile.json` | name, government_type, head_of_state, head_of_government, population, species_breakdown[], languages[], world_view, location, climate, neighbors[], allies[], enemies[], symbol, colors, flag, slogan, reputation, previous_governments[] |
| 22 | Culture Profile Template | `phase05-civilization/22-culture-profile.json` | name, scope, sovereign_power_id, cultural_vision, core_values[], core_beliefs[], core_morals[], species_races[], social_classes[] |
| 23 | Cultural Manifestations Sheet | `phase05-civilization/23-cultural-manifestations.json` | culture_id, greetings, farewells, swear_words[], colloquialisms[], dining_etiquette, clothing_norms, hair_expectations, body_modifications, gestures, body_language, architecture, daily_life, transportation, pastimes, holidays_festivals[], folklore, food_drink |
| 24 | Cultural Clash Planner | `phase05-civilization/24-cultural-clash-planner.json` | culture_a_id, culture_b_id, key_differences[], potential_misunderstandings[], severity (minor/serious/deadly), story_use |
| 25 | Settlement Profile Template | `phase05-civilization/25-settlement-profile.json` | name, type (outpost/castle/village/town/city), sovereign_power_id, climate, terrain, population, species_breakdown[], leadership, quarters[], zoning, fortifications, history, reputation, products[], colors, symbol, secrets[] |
| 26 | Settlement Master Spreadsheet | `phase05-civilization/26-settlement-master-spreadsheet.json` | settlements[] (each with: name, sovereign_power, location, population, species_pct, products, symbol, colors, military, reputation, notes) |

**Phase 6: Society (20 templates)**

| # | Template | File | Key Fields |
|---|----------|------|------------|
| 27 | Religion Profile Template | `phase06-society/27-religion-profile.json` | name, gods_worshiped[], founding_story, symbols[], relics[], holy_sites[], worship_practices, afterlife_belief, clergy_structure |
| 28 | Religion History Sheet | `phase06-society/28-religion-history.json` | religion_id, founding_event, prophetic_figure, major_events[], schisms[], current_status |
| 29 | Religion Beliefs and Practices Template | `phase06-society/29-religion-beliefs-practices.json` | religion_id, core_beliefs[], prohibited_behaviors[], required_practices[], holidays[], rituals[] |
| 30 | Religion Membership Sheet | `phase06-society/30-religion-membership.json` | religion_id, membership_requirements, initiation_process, ranks[], obligations[], leaving_consequences |
| 31 | Clergy Profile Template | `phase06-society/31-clergy-profile.json` | religion_id, clergy_title, rank_structure[], duties[], vestments, privileges, restrictions, training_path |
| 32 | Afterlife Design Sheet | `phase06-society/32-afterlife-design.json` | religion_id, afterlife_exists (real/imagined/ambiguous), destinations[], sorting_criteria, description, relation_to_undead |
| 33 | Organization Profile Template | `phase06-society/33-organization-profile.json` | name, type, world_view, goals[], power_structure, symbol, identity_markers[], sovereign_power_id, formation_story, alignment |
| 34 | Organization Membership Sheet | `phase06-society/34-organization-membership.json` | organization_id, join_process, recruitment_methods[], failed_recruit_fate, leaving_process, defector_fate, ranks[] |
| 35 | Organization History Log | `phase06-society/35-organization-history-log.json` | organization_id, historical_actions[] (each with: date, title, description, outcome, entities_involved[]) |
| 36 | Organization Relationships Matrix | `phase06-society/36-organization-relationships.json` | organization_id, relationships[] (each with: target_id, target_type, relationship, reason) |
| 37 | Armed Forces Profile Template | `phase06-society/37-armed-forces-profile.json` | name, sovereign_power_id, purpose, terrain_specialization, transportation, weapons[], armor_by_rank[], special_sites[], customs[] |
| 38 | Military Membership Pipeline | `phase06-society/38-military-membership-pipeline.json` | force_id, prerequisites[], initiation_tests[], training_program, final_tests[], washout_rate, customs[] |
| 39 | Military Rank Structure | `phase06-society/39-military-rank-structure.json` | force_id, ranks[] (each with: title, level, duties, insignia, authority_scope, population_at_rank) |
| 40 | Military Relationships Sheet | `phase06-society/40-military-relationships.json` | force_id, relationships[] (each with: target_force_id, level (1-7 scale from cooperation to open conflict), description) |
| 41 | Military History and Lore Log | `phase06-society/41-military-history-lore.json` | force_id, notable_battles[], legends[], traditions[], famous_members[] |
| 42 | Education System Template | `phase06-society/42-education-system.json` | sovereign_power_id, basic_education_available, special_education_types[], apprenticeship_system, literacy_rate, notable_institutions[] |
| 43 | Health System Template | `phase06-society/43-health-system.json` | sovereign_power_id, life_expectancy, magical_healing_available, medical_knowledge_level, common_diseases[], health_infrastructure |
| 44 | Legal System Template | `phase06-society/44-legal-system.json` | sovereign_power_id, system_type (civil/common/religious), moral_laws[], incident_laws[], trial_types[], punishments[], unique_punishments[] |
| 45 | Commerce System Template | `phase06-society/45-commerce-system.json` | sovereign_power_id, currency_name, denominations[], price_reference (meal/weapon/horse/etc.), trade_goods[], trade_routes[], merchant_guilds[] |
| 46 | Information System Template | `phase06-society/46-information-system.json` | sovereign_power_id, news_methods[], message_speed, literacy_impact, censorship_level, notable_information_networks[] |

**Phase 7: Supernatural (12 templates)**

| # | Template | File | Key Fields |
|---|----------|------|------------|
| 47 | Supernatural Prevalence Worksheet | `phase07-supernatural/47-supernatural-prevalence.json` | prevalence (rare/uncommon/common/ubiquitous), industries_affected[], professions_changed[], transportation_impact, law_enforcement_impact, healthcare_impact, warfare_impact, attitudes_by_species[], attitudes_by_class[] |
| 48 | Supernatural Energy Template | `phase07-supernatural/48-supernatural-energy.json` | name, appearance, temperature, detection_range, occurrence_conditions, relation_to_gods[], dangers[] |
| 49 | Magic Path / Supernatural Land Template | `phase07-supernatural/49-magic-path.json` | name, type (path/land/pocket), doorway_description, advantages[], dangers[], rules, connected_locations[] |
| 50 | Supernatural Being Template | `phase07-supernatural/50-supernatural-being.json` | name, type (demigod/familiar/spirit/etc.), origin, abilities[], limitations[], relation_to_gods[], relation_to_mortals |
| 51 | Magic System Overview Template | `phase07-supernatural/51-magic-system-overview.json` | name, type (hard/soft/hybrid), source, possible_effects[], impossible_effects[], who_can_use, prevalence, cost |
| 52 | Magic System Rules Sheet | `phase07-supernatural/52-magic-system-rules.json` | system_id, law_1_possible_impossible, law_2_who_can_perform, law_3_types_and_interactions[], law_4_failure_consequences, law_5_legal_status[], law_6_consistency_notes, law_7_learning_path |
| 53 | Magic Type Detail Template | `phase07-supernatural/53-magic-type-detail.json` | name, system_id, description, effects[], limitations[], interaction_with_other_types[], practitioners[], cultural_perception |
| 54 | Spell Design Template | `phase07-supernatural/54-spell-design.json` | name, magic_type_id, gestures, ingredients[], words, effect, area, range, duration, failure_result, difficulty, notes |
| 55 | Magic Training and Society Template | `phase07-supernatural/55-magic-training-society.json` | system_id, training_structure (apprenticeship/school/self-taught), curriculum[], ranks[], tests[], graduation_requirements, institutions[] |
| 56 | Item Profile Template | `phase07-supernatural/56-item-profile.json` | name, type (magic/technological/regular), significance_source, creator, owner_history[], current_location, description, who_can_use |
| 57 | Magic Item Detail Sheet | `phase07-supernatural/57-magic-item-detail.json` | item_id, powers[], defects[], limitations[], magic_system_id, creation_method, attunement_requirements |
| 58 | Technological Item Detail Sheet | `phase07-supernatural/58-technological-item-detail.json` | item_id, manufacturer, species_origin, technology_level, capabilities[], limitations[], reputation |
| 59 | A.I. Profile Template | `phase07-supernatural/59-ai-profile.json` | name, creator, purpose, intelligence_level, capabilities[], limitations[], legal_status, personality, physical_form |

**Phase 8: History (4 templates)**

| # | Template | File | Key Fields |
|---|----------|------|------------|
| 60 | Time System Template | `phase08-history/60-time-system.json` | hours_per_day, days_per_week, day_names[], weeks_per_month, months_per_year, month_names[], year_length, calendar_anchor_event, named_ages[] |
| 61 | History Entry Template | `phase08-history/61-history-entry.json` | date, title, category (god_interference/technological/supernatural/rise_fall/war/group_forming/artifact/mission), summary, entities_involved[], consequences[], cross_file_updates[] |
| 62 | World History Timeline | `phase08-history/62-world-history-timeline.json` | ages[] (each with: name, start_date, end_date, defining_events[], key_figures[]) |
| 63 | World Figure Profile Template | `phase08-history/63-world-figure-profile.json` | name, fame_reason, species_id, sovereign_power_id, status (alive/dead/missing/imprisoned), deeds[], possessions[], what_people_believe, what_is_true, perception_by_species[] |

**Phase 9: Language (7 templates)**

| # | Template | File | Key Fields |
|---|----------|------|------------|
| 64 | Language Decision Worksheet | `phase09-language/64-language-decision.json` | approach (ignore/ad_hoc/naming_language/professional/full_conlang), medium, rationale, budget |
| 65 | Naming Language Brief | `phase09-language/65-naming-language-brief.json` | language_name, associated_culture_id, phonology_notes, common_prefixes[], common_suffixes[], sound_feel, example_words[] |
| 66 | Language Usage Tracker | `phase09-language/66-language-usage-tracker.json` | language_id, words_created[] (each with: word, meaning, used_in[], notes) |
| 67 | Naming Convention Sheet | `phase09-language/67-naming-convention.json` | culture_id, name_order (given_first/surname_first), typical_name_count, common_prefixes[], common_suffixes[], name_change_triggers[], compound_surname_rules |
| 68 | Name Registry | `phase09-language/68-name-registry.json` | entries[] (each with: name, type (person/place/thing/god/species/etc.), entity_id, culture_id, meaning, pronunciation, notes) |
| 69 | Place Name Worksheet | `phase09-language/69-place-name-worksheet.json` | place_id, name, naming_technique (suffix_prefix/vowel_sub/compound/foreign_adapt/etc.), source_word, modifications_made, pronunciation |
| 70 | Name Generation Checklist | `phase09-language/70-name-generation-checklist.json` | syllable_count_target, avoid_same_first_letter_as[], googled (yes/no), said_aloud (yes/no), culture_consistency_check, notes |

**Phase 10: Travel (7 templates)**

| # | Template | File | Key Fields |
|---|----------|------|------------|
| 71 | Land Travel Calculator Template | `phase10-travel/71-land-travel-calculator.json` | origin, destination, terrain_segments[] (each with: type, distance_miles, modifier), travel_mode, base_speed, total_distance, total_days |
| 72 | Travel Distance Reference | `phase10-travel/72-travel-distance-reference.json` | routes[] (each with: from, to, distance, terrain_summary, days_walking, days_riding, days_wagon) |
| 73 | Sea Travel Calculator Template | `phase10-travel/73-sea-travel-calculator.json` | origin_port, destination_port, distance_nautical_miles, ship_type, speed_knots, coastal_stops, total_days |
| 74 | Ship Profile Template | `phase10-travel/74-ship-profile.json` | name, type, sovereign_power_id, crew_size, cargo_capacity, speed, armament, notable_features |
| 75 | Naval Forces Summary | `phase10-travel/75-naval-forces-summary.json` | sovereign_power_id, fleet_size, ship_types[], key_ports[], naval_traditions, notable_admirals[] |
| 76 | Spacecraft Profile Template | `phase10-travel/76-spacecraft-profile.json` | name, class, propulsion_type, ftl_capable, crew_size, armament, cargo, manufacturer, notable_features |
| 77 | Space Travel Reference | `phase10-travel/77-space-travel-reference.json` | propulsion_types[], ftl_rules, speed_limits, key_routes[], space_stations[] |

**Phase 11: Finishing (5 templates)**

| # | Template | File | Key Fields |
|---|----------|------|------------|
| 78 | Place of Interest Profile Template | `phase11-finishing/78-place-of-interest-profile.json` | name, type (ruin/phenomenon/shipwreck/event_site/monument/catacomb/extraordinary), location, story, history_entries[], sovereign_power_id, current_state, secrets[] |
| 79 | Shipwreck Profile Template | `phase11-finishing/79-shipwreck-profile.json` | ship_name, location, sinking_cause, date, cargo, survivors, current_state, legends[], salvage_status |
| 80 | Phenomenon Catalog | `phase11-finishing/80-phenomenon-catalog.json` | name, type (dead_zone/portal/supercharged/other), location, effect, cause, known_by[], danger_level |
| 81 | Map Creation Checklist -- Continental | `phase11-finishing/81-map-checklist-continental.json` | coastline_done, latitude_marked, mountains_placed, rain_shadows_marked, rivers_drawn, settlements_placed, vegetation_marked, roads_drawn, borders_drawn, scale_noted, not_to_scale_added |
| 82 | Map Creation Checklist -- Settlement | `phase11-finishing/82-map-checklist-settlement.json` | water_source_placed, old_town_defined, expansion_rings_drawn, walls_drawn, gates_placed, key_buildings_placed, quarters_labeled, roads_drawn |

**Phase 12: Integration (2 templates)**

| # | Template | File | Key Fields |
|---|----------|------|------------|
| 83 | Worldbuilding Review Schedule | `phase12-integration/83-review-schedule.json` | review_frequency, last_review_date, next_review_date, review_checklist[], changes_to_make_file |
| 84 | Case Study Worksheet | `phase12-integration/84-case-study-worksheet.json` | geographic_feature, sovereign_powers_affected[], government_types[], geography_influence, alliances[], enmities[], trade_implications, naming_rationale |

### How to Execute Task A

**Approach:** Use a Python script to generate all 84 template files from a master definition. This is faster and more consistent than hand-writing each one.

**Steps:**
1. Create the folder structure under `templates/`.
2. Create a master definition file (`engine/template_definitions.py`) that contains the complete field list for each template, derived from the volume analyses.
3. Run the script to generate all 84 JSON schema files.
4. Review and refine -- some templates will need hand-tuning for specific fields.

**Estimated effort:** 4-6 hours for the master definition, 1-2 hours for review.

---

## Task B: Data Schema (User World Storage)

### Design Principles

1. **JSON files, one per entity.** Each god, species, settlement, etc. is a separate `.json` file. This makes version control (git) clean -- you can see exactly what changed.

2. **Folder structure mirrors entity types, not progression phases.** When the user creates a god in Step 7, the file goes in `user-world/entities/gods/`, not `user-world/step-07/`. This is because entities get updated across many steps.

3. **Every entity has an `id` field.** IDs are slugified names (e.g., `"thorin-stormkeeper"`) plus a short random suffix to avoid collisions. Cross-references use these IDs.

4. **A central state file tracks progression.** `user-world/state.json` knows what step the user is on, what's been completed, and what entities exist.

### Folder Structure

```
user-world/
|-- state.json                         # Progression state
|-- entities/
|   |-- gods/                          # God Profile instances
|   |   |-- thorin-stormkeeper-a1b2.json
|   |   |-- mira-sunweaver-c3d4.json
|   |-- pantheons/                     # Pantheon Overview instances
|   |-- myths/                         # Mythology Worksheet instances
|   |-- planets/                       # Planet Profile instances
|   |-- climate-zones/                 # Climate Zone Reference instances
|   |-- continents/                    # Continent Profile instances
|   |-- water-bodies/                  # Water Body Reference instances
|   |-- land-features/                 # Land Feature Catalog entries
|   |-- species/                       # Species Profile instances
|   |-- races/                         # Race Hierarchy Chart instances
|   |-- plants/                        # Plant Profile instances
|   |-- animals/                       # Animal Profile instances
|   |-- monsters/                      # Monster Profile instances
|   |-- undead/                        # Undead Type Profile instances
|   |-- sovereign-powers/              # Sovereign Power Profile instances
|   |-- cultures/                      # Culture Profile instances
|   |-- settlements/                   # Settlement Profile instances
|   |-- religions/                     # Religion Profile instances
|   |-- organizations/                 # Organization Profile instances
|   |-- armed-forces/                  # Armed Forces Profile instances
|   |-- items/                         # Item Profile instances
|   |-- spells/                        # Spell Design instances
|   |-- magic-systems/                 # Magic System instances
|   |-- supernatural-beings/           # Supernatural Being instances
|   |-- world-figures/                 # World Figure Profile instances
|   |-- ships/                         # Ship Profile instances
|   |-- spacecraft/                    # Spacecraft Profile instances
|   |-- places-of-interest/            # Place of Interest instances
|   |-- phenomena/                     # Phenomenon Catalog instances
|-- worksheets/
|   |-- strategy.json                  # World Building Strategy Worksheet
|   |-- analogue-log.json              # Analogue Modification Log (array of entries)
|   |-- goals.json                     # Worldbuilding Goals Worksheet
|   |-- file-organization.json         # File Organization Template
|   |-- supernatural-prevalence.json   # Supernatural Prevalence Worksheet
|   |-- language-decision.json         # Language Decision Worksheet
|   |-- review-schedule.json           # Review Schedule
|-- registries/
|   |-- name-registry.json             # Name Registry (all names in one file)
|   |-- settlement-master.json         # Settlement Master Spreadsheet
|   |-- products-mapping.json          # Products-to-Source Mapping Table
|   |-- species-relationships.json     # Species Relationship Matrix
|-- timelines/
|   |-- world-history.json             # World History Timeline
|   |-- time-system.json               # Time System definition
|-- travel/
|   |-- land-routes.json               # Land Travel Calculator results
|   |-- sea-routes.json                # Sea Travel Calculator results
|   |-- space-routes.json              # Space Travel Reference
|-- maps/
|   |-- continental-checklist.json     # Map Creation Checklist
|   |-- settlement-checklists/         # Per-settlement map checklists
```

### State File: `user-world/state.json`

```json
{
  "current_step": 1,
  "current_phase": "foundation",
  "completed_steps": [],
  "in_progress_steps": [],
  "entity_index": {
    "gods": ["thorin-stormkeeper-a1b2", "mira-sunweaver-c3d4"],
    "species": [],
    "settlements": []
  },
  "session_log": [
    {
      "date": "2026-02-01",
      "steps_worked_on": [1],
      "entities_created": [],
      "entities_modified": [],
      "notes": "Completed strategy worksheet"
    }
  ]
}
```

### Entity Instance Example

When the user creates a god, the resulting file (`user-world/entities/gods/thorin-stormkeeper-a1b2.json`) contains the actual data that matches the God Profile Template schema:

```json
{
  "$template": "god-profile",
  "id": "thorin-stormkeeper-a1b2",
  "name": "Thorin Stormkeeper",
  "titles": ["The Thunder Lord", "Voice of the Sky"],
  "domain_primary": "storms",
  "domains_secondary": ["protection", "sailors"],
  "alignment": "good",
  "symbol": "A bolt of lightning striking a wave",
  "appearance": "A towering figure wreathed in dark clouds, eyes flashing blue-white",
  "personality": "Fierce in battle but deeply protective of those who call upon him",
  "power_level": "greater",
  "relationships": [
    {
      "target_id": "mira-sunweaver-c3d4",
      "relationship_type": "spouse",
      "description": "They balance each other -- storm and sun, destruction and growth"
    }
  ],
  "pantheon_id": "the-celestial-court-e5f6",
  "notes": "",
  "created_at_step": 7,
  "last_modified_step": 7
}
```

Note the `$template` field -- this tells the system which schema to validate against.

### How to Execute Task B

1. Create the folder structure under `user-world/`.
2. Create an empty `state.json` with default values.
3. Write a Python utility (`engine/data_manager.py`) with functions:
   - `create_entity(template_id, data)` -- validates against schema, assigns ID, saves file
   - `update_entity(entity_id, data)` -- validates, updates, logs modification
   - `get_entity(entity_id)` -- loads and returns
   - `list_entities(entity_type)` -- returns all entities of a type
   - `get_cross_references(entity_id)` -- finds all entities that reference this one

**Estimated effort:** 3-4 hours.

---

## Task C: Chunk Pulling System

This is the core intelligence of the program. Given a progression step number, it produces the three-layer guidance:

1. **Book Quotes and Teaching** -- relevant passages from `source-text.txt`
2. **Synthesized Reference Material** -- examples from all 16 databases
3. **Actionable Output** -- the template(s) to fill in, with guided questions

### How It Works

```
User says: "I'm ready for Step 7 -- creating god profiles"
            |
            v
    chunk_puller.py receives step_number = 7
            |
            +-- Looks up step 7 in source_index.json
            |   -> Returns line ranges from source-text.txt
            |   -> Extracts: book quotes about god creation
            |
            +-- Looks up step 7 in reference_index.json
            |   -> Returns: which sections of which databases are relevant
            |   -> For step 7 (god profiles):
            |      - norse.md section 1 (Pantheon)
            |      - greek.md section 1 (Pantheon)
            |      - hindu.md section 1 (Pantheon)
            |      - ... all 10 mythologies, section 1
            |      - tolkien.md section 3 (Pantheon / Higher Powers)
            |      - martin.md section 3 (Religion and Power)
            |      - ... all 6 authors, relevant sections
            |
            +-- Looks up step 7 in template_registry.json
            |   -> Returns: template #6 (god-profile.json)
            |   -> Loads the schema with all fields
            |
            v
    fair_representation.py ensures balanced sampling:
            |   -> Selects 3-4 mythology examples (rotating which ones are featured)
            |   -> Selects 2-3 author examples (rotating which ones are featured)
            |   -> Tracks what has been shown before to avoid repetition
            |
            v
    Output: A structured guidance document with three layers
```

### The Source Index: `engine/source_index.json`

This maps each progression step to the line ranges in `source-text.txt` that contain the relevant teaching material.

```json
{
  "steps": {
    "1": {
      "title": "Define Your World Building Scope and Strategy",
      "source_chapter": "V1 Ch1",
      "line_ranges": [
        {"start": 1, "end": 45, "topic": "Why Build a World (introduction)"},
        {"start": 46, "end": 120, "topic": "Using Analogues"},
        {"start": 250, "end": 310, "topic": "How Many Worlds"}
      ],
      "key_quotes": [
        {"line": 15, "text": "Every world builder must decide...", "context": "opening"},
        {"line": 78, "text": "The Rule of Three states...", "context": "principle"}
      ]
    },
    "7": {
      "title": "Create Individual God Profiles",
      "source_chapter": "V1 Ch2",
      "line_ranges": [
        {"start": 500, "end": 620, "topic": "Pantheons"},
        {"start": 621, "end": 700, "topic": "Power and Hierarchy"},
        {"start": 750, "end": 850, "topic": "Characteristics and Identifiers"},
        {"start": 851, "end": 950, "topic": "Behavior and Relationships"}
      ],
      "key_quotes": [
        {"line": 510, "text": "...", "context": "pantheon structure"},
        {"line": 770, "text": "...", "context": "god characteristics"}
      ]
    }
  }
}
```

**How to build this index:** A Python script will scan `source-text.txt`, identify chapter boundaries and topic boundaries, and create the mapping. This needs to be done once, with manual verification.

### The Reference Index: `engine/reference_index.json`

This maps each progression step to the relevant sections in each of the 16 reference databases.

```json
{
  "steps": {
    "7": {
      "title": "Create Individual God Profiles",
      "databases": {
        "mythologies/norse.md": {
          "sections": ["1. PANTHEON"],
          "focus": "How Norse mythology structures its gods: Aesir vs Vanir, power dynamics, personality-driven roles"
        },
        "mythologies/greek.md": {
          "sections": ["1. PANTHEON"],
          "focus": "Olympian hierarchy, domains, family relationships as power structure"
        },
        "mythologies/hindu.md": {
          "sections": ["1. PANTHEON"],
          "focus": "Trimurti concept, avatar system, cosmic functions"
        },
        "mythologies/mesopotamian.md": {
          "sections": ["1. PANTHEON"],
          "focus": "Oldest pantheon structure, city-god patronage system"
        },
        "mythologies/celtic.md": {
          "sections": ["1. PANTHEON"],
          "focus": "Tuatha De Danann, skill-based domains rather than natural-force domains"
        },
        "mythologies/chinese.md": {
          "sections": ["1. PANTHEON"],
          "focus": "Bureaucratic heavenly hierarchy, Jade Emperor system"
        },
        "mythologies/japanese.md": {
          "sections": ["1. PANTHEON"],
          "focus": "Kami concept, nature spirits as deities, imperial divine lineage"
        },
        "mythologies/roman.md": {
          "sections": ["1. PANTHEON"],
          "focus": "Adaptation of Greek gods, state religion as political tool"
        },
        "mythologies/native-american.md": {
          "sections": ["1. PANTHEON"],
          "focus": "Creator-Trickster duality, animal spirits, regional variation"
        },
        "mythologies/biblical.md": {
          "sections": ["1. DIVINE BEINGS"],
          "focus": "Monotheistic structure, angelic hierarchy, divine attributes"
        },
        "authors/tolkien.md": {
          "sections": ["2. Cosmology & Creation", "3. Pantheon / Higher Powers"],
          "focus": "Eru + Valar + Maiar hierarchy, music-based creation, monotheism with stewards"
        },
        "authors/martin.md": {
          "sections": ["3. Religion and Power"],
          "focus": "Multiple competing religions, gods whose existence is ambiguous"
        },
        "authors/jordan.md": {
          "sections": ["2. Cosmology"],
          "focus": "Creator + Dark One duality, the Wheel of Time as cosmic structure"
        },
        "authors/rothfuss.md": {
          "sections": ["2. Cosmology"],
          "focus": "Tehlu and the Chandrian, gods as contested legends"
        },
        "authors/berg.md": {
          "sections": ["2. Cosmology"],
          "focus": "How divine powers interact with mortal affairs through transformation"
        },
        "authors/lovecraft.md": {
          "sections": ["2. Cosmology"],
          "focus": "Cosmic indifference, gods as alien entities beyond comprehension"
        }
      }
    }
  }
}
```

### Fair Representation System: `engine/fair_representation.py`

The goal: every reference database gets roughly equal airtime across the 52 steps. No single mythology or author should dominate.

**Algorithm:**
1. Maintain a usage counter per database (stored in `user-world/state.json` under `"reference_usage_counts"`).
2. For each step, all 16 databases have relevant content. Select a featured subset:
   - 4 mythologies (out of 10) get "featured" treatment (longer excerpts, more detail)
   - 3 authors (out of 6) get "featured" treatment
   - The remaining 9 get "brief mention" treatment (one-sentence summaries)
3. The selection algorithm prioritizes databases with the lowest usage count, ensuring rotation.
4. Over 52 steps, each mythology gets featured ~21 times and each author ~26 times (roughly even).

```python
def select_featured_databases(step_number, usage_counts, all_databases):
    """Select which databases to feature for this step, favoring underrepresented ones."""
    mythologies = [db for db in all_databases if db["type"] == "mythology"]
    authors = [db for db in all_databases if db["type"] == "author"]

    # Sort by usage count (ascending) -- least-used get priority
    mythologies.sort(key=lambda db: usage_counts.get(db["id"], 0))
    authors.sort(key=lambda db: usage_counts.get(db["id"], 0))

    featured_myths = mythologies[:4]
    featured_authors = authors[:3]

    # Update counts
    for db in featured_myths + featured_authors:
        usage_counts[db["id"]] = usage_counts.get(db["id"], 0) + 1

    return featured_myths, featured_authors
```

### The Chunk Puller Output Format

For each step, `chunk_puller.py` produces a structured document like this:

```
=== STEP 7: Create Individual God Profiles ===

--- LAYER 1: WHAT THE BOOK TEACHES ---

From Volume 1, Chapter 2 -- Creating Gods:

> "Every god needs at minimum: a domain, an alignment, a symbol, and at least
> one relationship to another god." (p. XX)

> "Consider whether your gods are truly real, merely imagined by the
> inhabitants, or deliberately ambiguous." (p. XX)

[3-5 key quotes with brief explanations of why each matters]

--- LAYER 2: HOW OTHERS HAVE DONE IT ---

FEATURED MYTHOLOGIES:

Norse: The Aesir are organized by function (Odin=wisdom/war, Thor=strength/
protection, Tyr=justice). Key insight: gods have *personality-driven* roles,
not just domain assignments. Odin is cunning and manipulative; Thor is
straightforward and loyal. Their personalities create natural conflicts.

Hindu: The Trimurti (Brahma=creation, Vishnu=preservation, Shiva=destruction)
shows a *cosmic function* model where gods represent forces of the universe
itself. Avatars allow one god to appear in many forms across history.

Chinese: The Jade Emperor presides over a *bureaucratic* heavenly hierarchy
that mirrors the imperial court. Gods hold official positions and can be
promoted or demoted. This is radically different from Western divine-right
models.

Japanese: Kami are not always "gods" in the Western sense -- they can be
nature spirits, ancestors, or abstract forces. This shows that divinity
does not require human-like personalities.

FEATURED AUTHORS:

Tolkien: Created a strict monotheism (Eru Iluvatar) with 14 Valar as
stewards, not gods. The Valar were created through *music* -- each
contributed a theme to a Great Song that became reality. This shows how
a creation method can define an entire cosmology.

Martin: Deliberately keeps divine existence ambiguous. Multiple religions
compete (the Faith of the Seven, the Old Gods, R'hllor, the Drowned God).
The reader never learns definitively whether any gods are real. This shows
how ambiguity itself can be a design choice.

Lovecraft: The "gods" (Great Old Ones) are utterly alien -- they do not
care about humanity at all. This is the extreme end of divine indifference
and shows that gods need not be human-like or interested in mortals.

BRIEF MENTIONS (for your awareness):
- Greek: Family-based Olympian hierarchy with Zeus as patriarch
- Roman: Greek structure adapted as state religion
- Celtic: Tuatha De Danann, skill-based domains (Lugh = "of many skills")
- Mesopotamian: City-patron system, oldest recorded pantheon
- Native American: Creator-Trickster pairs, animal spirits
- Biblical: Monotheistic with angelic hierarchy
- Jordan: Creator + Dark One cosmic duality
- Rothfuss: Tehlu as a contested historical/divine figure
- Berg: Divine transformation powers tied to mortal consequences

CROSS-CUTTING PATTERNS:
- Most pantheons organize by *function* (war, wisdom, love), but the
  specific functions vary by culture
- Family relationships among gods create natural drama
- The question of "are gods real?" is answered differently by every source
- Gods' personalities matter as much as their domains

--- LAYER 3: YOUR TURN ---

Template to fill: God Profile Template (#6)

For each god in your pantheon, you need:
- REQUIRED: Name, primary domain, alignment, symbol, at least one relationship
- RECOMMENDED: Titles, appearance, personality, power level
- OPTIONAL: Origin, residence, vulnerability, worship notes

Guided questions:
1. What is this god's primary domain? (What force or concept do they embody?)
2. Are they good, evil, neutral, or morally complex?
3. What symbol represents them? (This will appear in temples, flags, armor)
4. Who is their most important relationship? (Parent, child, rival, spouse?)
5. What is one thing that makes this god *interesting* -- not just powerful?

Aim for at least 3-5 gods before moving on.
```

### How to Execute Task C

1. Create `engine/source_index.json` by scanning `source-text.txt` for chapter/topic boundaries. This requires reading the source text and manually identifying line ranges for each of the 52 steps. A script can identify chapter headings automatically; topic boundaries within chapters need manual review.

2. Create `engine/reference_index.json` by mapping each step to the relevant sections in each database. This can be partially automated -- the section headings in the databases (listed via grep above) follow predictable patterns. The "focus" descriptions need manual writing.

3. Write `engine/chunk_puller.py`:
   - Takes a step number as input
   - Reads `source_index.json` and extracts book quotes from `source-text.txt`
   - Reads `reference_index.json` and extracts relevant sections from each database
   - Calls `fair_representation.py` to select featured databases
   - Formats the output as a three-layer guidance document
   - Returns the document as a string (for hook injection or direct display)

4. Write `engine/fair_representation.py` as described above.

5. Create `engine/template_registry.json` -- a master list mapping template numbers to file paths, step numbers, and brief descriptions. This is the "table of contents" for all 84 templates.

**Estimated effort:** 8-12 hours total. The source index is the most labor-intensive part because it requires reading through the source text.

---

## Task D: Reference Database Index

This is the structured index that makes the 16 reference databases queryable by topic rather than by file.

### What It Contains

For each of the 16 databases, the index records:
- The file path
- The type (mythology or author)
- Every section heading with its line range
- A list of "tags" per section that map to worldbuilding topics

### Structure: `engine/reference_db_index.json`

```json
{
  "databases": [
    {
      "id": "norse",
      "file": "reference-databases/mythologies/norse.md",
      "type": "mythology",
      "name": "Norse Mythology",
      "total_lines": 582,
      "sections": [
        {
          "heading": "1. PANTHEON",
          "line_start": 11,
          "line_end": 222,
          "tags": ["gods", "pantheon", "divine-hierarchy", "god-relationships", "god-domains"],
          "relevant_steps": [6, 7, 8, 9]
        },
        {
          "heading": "2. COSMOLOGY -- THE NINE WORLDS",
          "line_start": 223,
          "line_end": 260,
          "tags": ["cosmology", "planes", "afterlife", "world-structure"],
          "relevant_steps": [10, 36]
        },
        {
          "heading": "3. CREATION MYTH",
          "line_start": 261,
          "line_end": 295,
          "tags": ["creation-myth", "cosmogony", "origin-story"],
          "relevant_steps": [8]
        },
        {
          "heading": "5. CREATURES AND MONSTERS",
          "line_start": 335,
          "line_end": 377,
          "tags": ["monsters", "creatures", "fauna"],
          "relevant_steps": [22, 23]
        }
      ]
    }
  ]
}
```

### Tag Vocabulary

A controlled vocabulary of tags ensures consistent mapping. Here are the tags and which progression steps they map to:

| Tag | Steps |
|-----|-------|
| `gods` | 6, 7 |
| `pantheon` | 6 |
| `divine-hierarchy` | 6, 7 |
| `god-relationships` | 7 |
| `god-domains` | 7 |
| `creation-myth` | 8 |
| `end-of-world-myth` | 8 |
| `mythology-stories` | 9 |
| `cosmology` | 10 |
| `planets-astronomy` | 10, 11 |
| `constellations` | 11 |
| `continents` | 12 |
| `geography` | 12, 13, 14, 15 |
| `mountains` | 13 |
| `rivers-lakes` | 14 |
| `forests-deserts-wetlands` | 15 |
| `species-races` | 16, 17, 18, 19, 20, 21 |
| `plants-animals` | 22 |
| `monsters` | 23 |
| `undead` | 24 |
| `governments` | 25 |
| `cultures` | 26, 27, 28 |
| `settlements` | 29, 30 |
| `religions` | 31 |
| `organizations` | 32 |
| `military` | 33 |
| `societal-systems` | 34 |
| `supernatural` | 35, 36 |
| `magic-systems` | 37, 38 |
| `items-artifacts` | 39 |
| `time-calendar` | 40 |
| `history` | 41 |
| `heroes-villains` | 42 |
| `languages` | 43 |
| `naming` | 44, 45 |
| `travel-land` | 46 |
| `travel-sea` | 47 |
| `travel-space` | 48 |
| `places-of-interest` | 49 |
| `maps` | 50 |
| `worldbuilding-techniques` | 1, 2, 3, 4, 5, 51, 52 |

### How to Execute Task D

1. Write a Python script (`engine/build_reference_index.py`) that:
   - Reads each of the 16 database files
   - Extracts section headings (they all follow the pattern `## N. HEADING`)
   - Records line ranges for each section
   - Outputs a skeleton `reference_db_index.json`

2. Manually add tags and `relevant_steps` to each section. This requires reading the section headings and matching them to the tag vocabulary.

3. Manually add the "focus" descriptions (1-2 sentences per section per step) that explain what is uniquely valuable about that section for that step.

**Estimated effort:** 3-4 hours. The script handles the structural extraction; the tagging is manual but straightforward since the database sections follow consistent patterns.

---

## Task E: Hooks Setup

### Which Hooks We Need

| Hook | Script | Purpose |
|------|--------|---------|
| `SessionStart` | `hooks/session_start.py` | Load `state.json`, display current step, recent session log |
| `UserPromptSubmit` | `hooks/inject_step_context.py` | Inject current step guidance, relevant templates, cross-reference reminders |
| `PostToolUse` | `hooks/validate_writes.py` | After any file write to `user-world/`, validate against schema, update `state.json` entity index |
| `Stop` | `hooks/check_completion.py` | Before ending, verify that required template fields are filled for the current step |
| `PreCompact` | `hooks/save_checkpoint.py` | Save current step context to a checkpoint file before context compression |

### Hook Configuration: `.claude/settings.json`

```json
{
  "hooks": {
    "SessionStart": [
      {
        "command": "python C:/Worldbuilding-Interactive-Program/hooks/session_start.py",
        "description": "Load worldbuilding project state and display current step"
      }
    ],
    "UserPromptSubmit": [
      {
        "command": "python C:/Worldbuilding-Interactive-Program/hooks/inject_step_context.py",
        "description": "Inject current step context and relevant reference material"
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "command": "python C:/Worldbuilding-Interactive-Program/hooks/validate_writes.py",
        "description": "Validate data integrity after file changes in user-world/"
      }
    ],
    "Stop": [
      {
        "command": "python C:/Worldbuilding-Interactive-Program/hooks/check_completion.py",
        "description": "Verify step completion requirements before ending"
      }
    ],
    "PreCompact": [
      {
        "command": "python C:/Worldbuilding-Interactive-Program/hooks/save_checkpoint.py",
        "description": "Checkpoint project state before context compression"
      }
    ]
  }
}
```

### Hook Script Details

**`hooks/session_start.py`**
- Reads `user-world/state.json`
- Outputs to stdout (which Claude receives as context):
  ```
  [WORLDBUILDING PROJECT STATE]
  Current Step: 7/52 -- Create Individual God Profiles
  Current Phase: Phase 2 (Cosmology)
  Completed Steps: 1, 2, 3, 4, 5, 6
  Entities Created: 1 pantheon, 2 gods, 1 creation myth
  Last Session: 2026-02-01 -- Worked on Step 6, created pantheon overview
  ```

**`hooks/inject_step_context.py`**
- Reads the user's prompt from stdin (JSON with `"prompt"` field)
- Reads `state.json` for current step
- Calls `chunk_puller.py` to get the three-layer guidance for the current step
- Outputs a condensed version to stdout (not the full document -- just the most relevant parts to keep context lean)
- If the user mentions specific entities by name, also injects their cross-references

**`hooks/validate_writes.py`**
- Reads the tool input from stdin (JSON with file path and content)
- If the file path is under `user-world/`:
  - Loads the corresponding template schema
  - Validates the data against the schema
  - Updates `state.json` entity index if a new entity was created
  - Checks cross-references: do all referenced entity IDs actually exist?
  - Outputs warnings for invalid data or broken cross-references

**`hooks/check_completion.py`**
- Reads `state.json` for the current step
- Looks up the step's requirements (which templates must be filled, minimum entity counts)
- Checks whether requirements are met
- If not met, outputs a message explaining what is still needed and exits with code 2 (blocks Claude from stopping)
- If met, exits with code 0 (allows Claude to stop)

**`hooks/save_checkpoint.py`**
- Reads `state.json`
- Copies it to `user-world/checkpoints/checkpoint-{timestamp}.json`
- Outputs a summary of what was checkpointed

### How to Execute Task E

1. Create the `hooks/` directory.
2. Write each of the 5 hook scripts in Python.
3. Write the `.claude/settings.json` configuration.
4. Test each hook individually by running the Python script with sample input.
5. Test the full hook chain by starting a Claude Code session and verifying that context injection works.

**Estimated effort:** 4-6 hours. The `inject_step_context.py` hook is the most complex because it depends on the chunk puller (Task C).

---

## Task F: Knowledge Graph Population

### Why a Knowledge Graph

The 16 reference databases contain ~13,500 lines of structured information. A knowledge graph makes it possible to answer cross-database questions like:
- "Which mythologies have a trickster god?" (Norse: Loki, Native American: Coyote, etc.)
- "How do different authors handle magic systems?" (Tolkien: subtle, Rothfuss: scientific, Jordan: channeling)
- "What creation myths involve music or sound?" (Tolkien: the Ainulindale, Hindu: Om)

Without a knowledge graph, answering these questions requires reading through all 16 files every time.

### Technology Choice: Anthropic MCP Knowledge Graph Server

We start with the simplest option:

```bash
claude mcp add knowledge-graph npx @anthropic/mcp-knowledge-graph
```

This provides:
- `create_entities` -- batch create entities with types
- `create_relations` -- create directed relationships
- `add_observations` -- attach facts to entities
- `search_nodes` -- search by name, type, or observation text
- `read_graph` -- dump the full graph
- `open_nodes` -- retrieve specific entities

Data is stored in a local JSONL file. No database server required.

### What Gets Loaded

Every entity from every reference database gets loaded as a node. Here is the entity extraction plan:

**From each mythology database (10 databases):**
- Each god/deity as an entity (type: `reference-god`)
- Each creature/monster as an entity (type: `reference-creature`)
- Each artifact/item as an entity (type: `reference-item`)
- Each place/realm as an entity (type: `reference-place`)
- Each hero/figure as an entity (type: `reference-figure`)
- Each myth/story as an entity (type: `reference-myth`)

**From each author database (6 databases):**
- Each species/race as an entity (type: `reference-species`)
- Each magic system as an entity (type: `reference-magic`)
- Each political system as an entity (type: `reference-politics`)
- Each major character as an entity (type: `reference-character`)
- Each worldbuilding technique as an entity (type: `reference-technique`)

**Relations between entities:**
- `BELONGS_TO` (god -> pantheon)
- `CREATED_BY` (species -> god)
- `APPEARS_IN` (god -> myth)
- `USES` (character -> magic system)
- `RULES` (figure -> place)
- `FIGHTS` (god -> creature)
- `ANALOGOUS_TO` (cross-database similarity, e.g., Norse Odin ~ Greek Zeus)

**Observations on each entity:**
- Source database (e.g., "From Norse mythology database")
- Key traits (e.g., "Domain: wisdom and war")
- Worldbuilding lesson (e.g., "Shows how a god's quest for knowledge can define their entire character")
- Relevant progression steps (e.g., "Relevant to Steps 6, 7, 8")

### Population Script: `engine/populate_knowledge_graph.py`

This script:
1. Reads each of the 16 database files
2. Parses the markdown to extract entities, their attributes, and relationships
3. Calls the MCP Knowledge Graph tools to create entities, observations, and relations
4. Logs what was created for verification

**Parsing approach:** Each database follows a predictable markdown structure (## headings for sections, ### and #### for sub-entries, bold-text labels for attributes). A parser can extract:
- Entity name from heading
- Domain/Role from the first bullet point
- Relationships from "Key Relationships" sub-sections
- Major myths from "Major Myths" sub-sections

The parser does not need to be perfect -- it needs to capture enough for useful queries. Manual cleanup can follow.

### Estimated Entity Counts

| Category | Per Mythology DB | Per Author DB | Total |
|----------|-----------------|---------------|-------|
| Gods/Powers | ~15 | ~5 | ~180 |
| Creatures | ~10 | ~8 | ~148 |
| Places | ~8 | ~10 | ~140 |
| Items/Artifacts | ~5 | ~5 | ~80 |
| Figures/Characters | ~8 | ~10 | ~140 |
| Myths/Stories | ~5 | ~3 | ~68 |
| Systems (magic, political) | ~2 | ~5 | ~50 |
| **Total** | | | **~806** |

This is a manageable size for the JSONL-based knowledge graph server. If it proves too slow for searches, we upgrade to Neo4j later.

### How to Execute Task F

1. Install the MCP Knowledge Graph server: `claude mcp add knowledge-graph npx @anthropic/mcp-knowledge-graph`
2. Write `engine/populate_knowledge_graph.py` -- the markdown parser and entity extractor.
3. Run the script against all 16 databases.
4. Verify by running test queries (e.g., "search for all gods with domain 'war'").
5. Manually add key cross-database relations (e.g., analogous entities).

**Estimated effort:** 6-8 hours. The markdown parser is the bulk of the work. Cross-database relation tagging requires manual judgment.

---

## Dependency Map

```
                    PHASE 2 DEPENDENCY MAP
                    ======================

    [A] Templates ----+
                      |
    [B] Data Schema --+---> [C] Chunk Puller ---> [E] Hooks Setup
                      |
    [D] Ref Index ----+---> [F] Knowledge Graph
                      |
                      +---> [F] Knowledge Graph
```

**Critical path:** A + B + D (parallel) --> C --> E

**Parallel track:** D --> F (can happen alongside C --> E)

---

## Execution Order

### Sprint 1: Foundation (Can all start immediately, run in parallel)

| Task | Description | Estimated Hours | Can Parallel? |
|------|-------------|-----------------|---------------|
| A1 | Create template folder structure | 0.5 | Yes |
| A2 | Write master template definitions (all 84) | 5 | Yes |
| A3 | Generate JSON schema files from definitions | 1 | After A2 |
| B1 | Create user-world folder structure | 0.5 | Yes |
| B2 | Write data_manager.py (create, read, update, validate) | 3 | Yes |
| D1 | Write reference index builder script | 2 | Yes |
| D2 | Run builder, manually tag sections with steps | 2 | After D1 |

**Sprint 1 total:** ~14 hours
**Sprint 1 deliverables:** 84 template files, user-world folder, reference index

### Sprint 2: Engine (Depends on Sprint 1)

| Task | Description | Estimated Hours | Can Parallel? |
|------|-------------|-----------------|---------------|
| C1 | Build source_index.json (map steps to source-text lines) | 4 | Yes |
| C2 | Write fair_representation.py | 1 | Yes |
| C3 | Write chunk_puller.py | 3 | After C1 |
| C4 | Write template_registry.json | 1 | Yes |
| C5 | Test chunk puller on 3-5 sample steps | 2 | After C3 |

**Sprint 2 total:** ~11 hours
**Sprint 2 deliverables:** Working chunk puller that produces three-layer guidance for any step

### Sprint 3: Integration (Depends on Sprint 2; F is parallel)

| Task | Description | Estimated Hours | Can Parallel? |
|------|-------------|-----------------|---------------|
| E1 | Write session_start.py hook | 1 | Yes |
| E2 | Write inject_step_context.py hook | 2 | Yes |
| E3 | Write validate_writes.py hook | 2 | Yes |
| E4 | Write check_completion.py hook | 1.5 | Yes |
| E5 | Write save_checkpoint.py hook | 1 | Yes |
| E6 | Write .claude/settings.json | 0.5 | After E1-E5 |
| E7 | Test full hook chain | 2 | After E6 |
| F1 | Write populate_knowledge_graph.py (markdown parser) | 4 | Yes |
| F2 | Run population script on all 16 databases | 1 | After F1 |
| F3 | Verify and add cross-database relations | 2 | After F2 |

**Sprint 3 total:** ~17 hours
**Sprint 3 deliverables:** Fully wired hooks, populated knowledge graph

### Total Phase 2 Estimate

| Sprint | Hours | Calendar Time (assuming 4-6 hrs/day) |
|--------|-------|--------------------------------------|
| Sprint 1 | ~14 | 2-3 days |
| Sprint 2 | ~11 | 2 days |
| Sprint 3 | ~17 | 3 days |
| **Total** | **~42** | **7-8 days** |

---

## What Success Looks Like

Phase 2 is complete when:

1. A user can say "I'm ready for Step 7" and the system produces a three-layer guidance document with book quotes, synthesized reference material from multiple mythologies and authors, and a clear template to fill in.

2. When the user fills in a God Profile, the data is saved as a valid JSON file in the right folder, cross-references are checked, and the state file is updated.

3. No single mythology or author dominates the reference material -- the fair representation system ensures rotation.

4. The knowledge graph can answer questions like "show me all trickster figures across all mythologies" in seconds.

5. Hooks automatically keep Claude aware of the current step, relevant templates, and existing entities -- the user never has to manually manage context.

---

## What Phase 2 Does NOT Do

- **Build a user interface.** Phase 2 produces the engine and data layer. The actual user experience (whether it is a CLI, a web app, or just Claude Code conversations) is Phase 3.
- **Process all 52 steps for real.** Phase 2 builds the infrastructure. The user's actual worldbuilding journey starts in Phase 3.
- **Perfect the chunk pulling.** The source index and reference index will need refinement as we discover what guidance is most useful. Phase 2 gets them to "good enough to start."
