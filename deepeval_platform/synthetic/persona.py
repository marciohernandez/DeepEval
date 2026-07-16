"""Persona and PersonaScenario configuration models (M4.1, data-model.md)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PersonaScenario:
    name: str
    expected_outcome: str


@dataclass
class Persona:
    name: str
    profile: str
    scenarios: list[PersonaScenario] = field(default_factory=list)
    styling_scenario: str | None = None
    task: str | None = None
    input_format: str | None = None
    expected_output_format: str | None = None
