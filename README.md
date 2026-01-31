# Worldbuilding Interactive Program

![Version](https://img.shields.io/badge/version-0.3.0-blue)
![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)
![Framework](https://img.shields.io/badge/PySide6-desktop-41CD52?logo=qt&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green)

A guided desktop application for **systematic worldbuilding**, based on Randy Ellefson's *The Complete Art of World Building* (3 volumes). Build rich, consistent fictional worlds through a structured **52-step process across 12 phases** -- with an AI assistant that validates every decision through a 7-layer pipeline.

Whether you are writing a novel, designing a tabletop RPG setting, or simply exploring the craft of worldbuilding, this program walks you through every dimension of a fictional world: gods, geography, species, civilizations, magic systems, history, and more.

---

## Key Features

- **52-Step Guided Workflow** -- 12 phases from Foundation to Integration, each broken into focused steps that guide you from world concept through final integration.
- **AI-Powered Assistant** -- Claude integration with streaming responses, 6 specialized tools, and context-aware prompts tailored to each step.
- **Option Generation Pipeline** -- Divergent-convergent approach generating 2-4 validated options per decision, drawing from 16 reference databases (10 mythologies + 6 authors).
- **Knowledge Graph** -- Interactive NetworkX-powered visualization with 18 entity types. Drag to connect relationships and see your world take shape.
- **7-Layer Validation** -- Schema, cross-reference, range, enum, drift detection, semantic checks, and structured results ensure AI output stays consistent.
- **Fair Representation** -- Balanced sourcing across Greek, Roman, Norse, Celtic, Chinese, Japanese, Native American, Mesopotamian, Hindu, and Biblical mythologies, plus Tolkien, Martin, Rothfuss, Berg, Lovecraft, and Jordan.
- **Event-Sourced Bookkeeping** -- Complete audit trail with append-only logs, derived indexes, and session summaries. Every decision is recorded.
- **Error Recovery** -- Health monitoring (healthy / degraded / critical), auto-repair, and crash recovery so you never lose work.
- **85 Entity Templates** -- Covering gods, species, settlements, cultures, religions, magic systems, items, and more across all 12 phases.

---

## Screenshots

> *Screenshots coming soon.* The application uses a **dark theme** (qt-material) designed for comfortable extended worldbuilding sessions.

---

## Architecture Overview

The application is organized into four layers with clear boundaries and event-driven communication:

```
┌─────────────────────────────────────────────────┐
│          PySide6 GUI (panels, widgets)           │
├─────────────────────────────────────────────────┤
│              EventBus + Signals                  │
├─────────────────────────────────────────────────┤
│  App Services (Claude, validation, enforcement,  │
│                  sessions)                       │
├─────────────────────────────────────────────────┤
│        EngineManager (thread-safe locks)         │
├─────────────────────────────────────────────────┤
│      Engine (10 modules + Pydantic models)       │
├─────────────────────────────────────────────────┤
│              Atomic I/O                          │
├─────────────────────────────────────────────────┤
│       Data (JSON files, SQLite, backups)         │
└─────────────────────────────────────────────────┘
```

| Layer | Location | Responsibility |
|-------|----------|----------------|
| **GUI** | `app/` | PySide6 panels, widgets, services, dark theme |
| **Engine** | `engine/` | 10 modules -- DataManager, WorldGraph, ChunkPuller, OptionGenerator, ConsistencyChecker, SQLiteSync, BackupManager, BookkeepingManager, FairRepresentation, ErrorRecovery |
| **Hooks** | `hooks/` | 6 Claude Code lifecycle hooks |
| **Data** | `user-world/`, `runtime/` | JSON source of truth, SQLite derived index, NetworkX graph |

---

## Installation

### Prerequisites

- **Python 3.11** or higher
- **Git**

### From Source

```bash
git clone https://github.com/blackeagle54/Worldbuilding-Interactive-Program.git
cd Worldbuilding-Interactive-Program
pip install -r requirements.txt
python -m app.main
```

### AI Features (Optional)

To enable the Claude AI assistant:

- Install the [Claude CLI](https://docs.anthropic.com/en/docs/claude-cli) **or** set the `ANTHROPIC_API_KEY` environment variable.
- The application works **fully offline** without AI -- you simply will not have the AI assistant panel.

### Windows Installer

- Download the latest installer from [GitHub Releases](https://github.com/blackeagle54/Worldbuilding-Interactive-Program/releases).
- Run the installer (no admin required, per-user install).
- Or build your own:
  ```bash
  python packaging/build_release.py
  ```

---

## Quick Start

1. **Launch** the application (`python -m app.main` or the installed shortcut).
2. A **Welcome dialog** checks prerequisites and introduces the workflow.
3. **Start at Step 1** (World Concept) in the Progress Sidebar.
4. Use the **Chat Panel** to discuss ideas with Claude.
5. **Generate options** via the Option Comparison Panel -- the engine produces 2-4 validated alternatives for each decision.
6. **Select and customize** entities in the Entity Detail view.
7. Watch your world grow in the **Knowledge Graph**.
8. Progress through all **52 steps** at your own pace.

---

## The 52-Step Process

<details>
<summary><strong>Click to expand all 12 phases</strong></summary>

| # | Phase | Steps | Focus |
|---|-------|-------|-------|
| 1 | **Foundation** | 1 -- 5 | World concept, scope, tone, genre, premise |
| 2 | **Cosmology** | 6 -- 11 | Creation myths, gods, pantheons, planes of existence |
| 3 | **The Land** | 12 -- 15 | Continents, geography, climate, notable locations |
| 4 | **Life** | 16 -- 24 | Species, flora, fauna, monsters, ecological relationships |
| 5 | **Civilization** | 25 -- 30 | Cultures, governments, settlements, economies, power structures |
| 6 | **Society** | 31 -- 34 | Social classes, customs, education, daily life |
| 7 | **The Supernatural** | 35 -- 39 | Magic systems, supernatural beings, artifacts, metaphysical rules |
| 8 | **History & Legend** | 40 -- 42 | Timelines, wars, legendary figures, turning points |
| 9 | **Language & Names** | 43 -- 45 | Naming conventions, languages, scripts, linguistic families |
| 10 | **Travel & Scale** | 46 -- 48 | Transportation, distances, trade routes, maps |
| 11 | **Finishing Touches** | 49 -- 50 | Unresolved threads, polish, internal consistency review |
| 12 | **Integration** | 51 -- 52 | Cross-referencing, final validation, world bible export |

</details>

---

## Project Structure

```
Worldbuilding-Interactive-Program/
├── app/                  # Desktop application (PySide6 GUI, services)
├── engine/               # Core engine modules (10 modules + models)
├── hooks/                # Claude Code lifecycle hooks
├── templates/            # 85 JSON Schema entity templates
├── reference-databases/  # Mythology and author reference files
├── tests/                # Test suite
├── docs/                 # Documentation and research
├── packaging/            # Installer and release build scripts
├── user-world/           # Per-user world data (JSON source of truth)
├── runtime/              # Runtime artifacts (SQLite, graph)
├── bookkeeping/          # Event-sourced audit logs
├── backups/              # Automatic backup storage
├── requirements.txt      # Production dependencies
├── requirements-dev.txt  # Development dependencies
└── pyproject.toml        # Project metadata and tool config
```

---

## Development

**Run tests:**

```bash
pytest tests/ -q
```

**Build a release:**

```bash
python packaging/build_release.py
```

**Code style:** Enforced via [Ruff](https://docs.astral.sh/ruff/), configured in `pyproject.toml`.

---

## How It Works Together

1. The user interacts through the **Chat Panel** or triggers option generation.
2. **Claude** responds with streaming tokens and tool calls, guided by step-specific system prompts.
3. **Engine modules** process requests behind thread-safe locks via the EngineManager.
4. The **7-layer validation pipeline** checks all AI output for schema conformance, cross-reference integrity, range validity, enum compliance, drift detection, and semantic coherence.
5. Entities are saved as **JSON** (atomic writes), then synced to **SQLite** (full-text search) and the **NetworkX graph**.
6. Every decision is logged to an **append-only event store** for full auditability.
7. The **EventBus** broadcasts signals so all panels (progress sidebar, knowledge graph, entity detail) update in real time.

---

## Tech Stack

| Category | Technology |
|----------|------------|
| Language | Python 3.11+ |
| GUI | PySide6, qt-material (dark theme) |
| Validation | Pydantic v2 |
| Graph | NetworkX |
| Search | SQLite with FTS5 |
| AI | Anthropic SDK / Claude CLI |
| Packaging | PyInstaller + Inno Setup |
| Linting | Ruff |

---

## Contributing

Contributions are welcome! To get started:

1. **Fork** the repository.
2. **Create a feature branch** (`git checkout -b feature/my-feature`).
3. **Make your changes** and add tests where appropriate.
4. **Run the test suite** (`pytest tests/ -q`) and linter (`ruff check .`).
5. **Open a Pull Request** with a clear description of your changes.

Please keep PRs focused on a single concern and follow the existing code style.

---

## Credits

- Worldbuilding methodology based on [*The Complete Art of World Building*](https://www.artofworldbuilding.com/) by **Randy Ellefson**.
- AI assistant powered by [Anthropic's Claude](https://www.anthropic.com/).
- Built with [PySide6](https://doc.qt.io/qtforpython/), [NetworkX](https://networkx.org/), and [Pydantic](https://docs.pydantic.dev/).

---

## License

This project is licensed under the **MIT License**. See [LICENSE](LICENSE) for details.
