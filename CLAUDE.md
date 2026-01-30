# Worldbuilding Interactive Program

## Project Purpose
An interactive worldbuilding tool based on "The Complete Art of World Building" by Randy Ellefson. The system guides users through a structured, step-by-step worldbuilding process where each chapter's concepts become progression steps with templates to fill out.

## Critical Rules
- **Commit after every significant step.** Never let work accumulate uncommitted.
- **Use Opus-level agents** for research, analysis, and complex tasks.
- **The user is non-technical.** Handle all code, tooling, and setup. Never ask the user to run commands themselves.
- **Keep decisions recorded.** Any important choice goes in `docs/decisions.md`.
- **Update progress.** After completing work, update `docs/progress.md`.

## Key Files
- `source-text.txt` — Full extracted text of the Ellefson worldbuilding book
- `volume1-analysis.md` — Dissection of Volume 1: Creating Life (7 chapters, 14 templates)
- `volume2-analysis.md` — Dissection of Volume 2: Creating Places (12 chapters, 16+ templates)
- `volume3-analysis.md` — Dissection of Volume 3: Cultures and Beyond (11 chapters, 15+ templates)
- `memory-research.md` — Research on persistent memory approaches for Claude Code
- `docs/decisions.md` — Log of all project decisions
- `docs/progress.md` — Current progress tracker

## Project Context
@docs/decisions.md
@docs/progress.md

## Architecture (TBD)
The end-user experience and tech stack have not been decided yet. The current phase is analyzing the source material and breaking it into structured chunks that form a progression system.

## Git
- Repository: https://github.com/blackeagle54/Worldbuilding-Interactive-Program
- Commit frequently with descriptive messages
- Treat this as a professional project with clean commit history
