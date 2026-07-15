"""PersonaConfigResolver — reconstructs Persona/PersonaScenario from config/personas.yaml
exclusively through ConfigManager (M4.1, data-model.md).
"""
from __future__ import annotations

from deepeval_platform.config.config_manager import ConfigManager
from deepeval_platform.synthetic.persona import Persona, PersonaScenario


class PersonaConfigError(Exception):
    pass


class PersonaConfigResolver:
    def __init__(self, config: ConfigManager | None = None) -> None:
        self._config = config if config is not None else ConfigManager.instance()

    def resolve(self, persona_names: list[str] | None) -> list[Persona]:
        configured_names = self._config.list_subkeys("personas")

        if persona_names is None:
            selected_names = configured_names
        else:
            if persona_names:
                missing = [name for name in persona_names if name not in configured_names]
                if missing:
                    raise PersonaConfigError(
                        f"Unknown persona(s) requested: {', '.join(missing)}"
                    )
            selected_names = list(persona_names)

        return [self._resolve_one(name) for name in selected_names]

    def _resolve_one(self, name: str) -> Persona:
        prefix = f"personas.{name}"
        return Persona(
            name=name,
            profile=self._config.get_optional(f"{prefix}.profile", default=""),
            styling_scenario=self._config.get_optional(
                f"{prefix}.styling_scenario", default=""
            )
            or None,
            task=self._config.get_optional(f"{prefix}.task", default="") or None,
            input_format=self._config.get_optional(f"{prefix}.input_format", default="")
            or None,
            expected_output_format=self._config.get_optional(
                f"{prefix}.expected_output_format", default=""
            )
            or None,
            scenarios=self._resolve_scenarios(prefix),
        )

    def _resolve_scenarios(self, persona_prefix: str) -> list[PersonaScenario]:
        scenarios: list[PersonaScenario] = []
        index = 0
        while True:
            scenario_prefix = f"{persona_prefix}.scenarios.{index}"
            scenario_name = self._config.get_optional(f"{scenario_prefix}.name", default="")
            if scenario_name == "":
                break
            expected_outcome = self._config.get_optional(
                f"{scenario_prefix}.expected_outcome", default=""
            )
            scenarios.append(
                PersonaScenario(name=scenario_name, expected_outcome=expected_outcome)
            )
            index += 1
        return scenarios
