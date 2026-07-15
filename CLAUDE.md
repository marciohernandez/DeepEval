# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Python project named `deepeval-platform` (source package: `deepeval_platform/`), scaffolded with
`uv`. Python 3.13 pinned (`.python-version`), minimum runtime `^3.11` per constitution.

**Naming note**: the source package is `deepeval_platform/`, NOT `deepeval/`. It was renamed on
2026-07-09 (post-M2.1) because a top-level `deepeval/` directory shadowed the installed `deepeval`
PyPI library on `sys.path`, making it impossible to import DeepEval's native classes
(`DeepEvalBaseLLM`, metrics, etc.) from within the project's own code. See
`.specify/memory/constitution.md` Principle II (DeepEval-First) — this rename is what makes that
principle practically enforceable.

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
shell commands, and other important information, read the current plan
at specs/008-synthetic-dataset-generator/plan.md
<!-- SPECKIT END -->
