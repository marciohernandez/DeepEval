# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Early-stage Python project named `deepeval`, scaffolded with `uv`. Python 3.13 pinned (`.python-version`), minimum runtime `^3.11` per constitution. No dependencies or tests exist yet.

## Commands

```bash
# Install dependencies
uv sync

# Run the application
uv run python main.py

# Add a dependency
uv add <package>
```

## Structure

- `main.py` — entry point with a `main()` function
- `pyproject.toml` — project metadata and dependencies (managed by `uv`)
- `.python-version` — pins Python to 3.13

<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan at:
`specs/002-coleta-traces/plan.md`
<!-- SPECKIT END -->
