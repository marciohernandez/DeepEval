"""Unit tests for Persona/PersonaScenario models and PersonaConfigResolver (M4.1, T007)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from deepeval_platform.synthetic.persona import Persona, PersonaScenario
from deepeval_platform.synthetic.persona_config_resolver import (
    PersonaConfigError,
    PersonaConfigResolver,
)


def _config_with(personas: dict) -> MagicMock:
    """Build a stub ConfigManager backed by a flattened dotted-key dict, mirroring
    real ConfigManager._flatten_yaml semantics (lists become index-keyed entries).
    """
    flat: dict[str, str] = {}

    def _flatten(prefix: str, value):
        if isinstance(value, dict):
            for k, v in value.items():
                _flatten(f"{prefix}.{k}" if prefix else str(k), v)
        elif isinstance(value, list):
            for i, item in enumerate(value):
                _flatten(f"{prefix}.{i}", item)
        else:
            flat[prefix] = str(value) if value is not None else ""

    _flatten("personas", personas)

    config = MagicMock()

    def _get_optional(key: str, default: str = ""):
        return flat.get(key, default)

    def _list_subkeys(prefix: str) -> list[str]:
        needle = f"{prefix}."
        children = set()
        for key in flat:
            if key.startswith(needle):
                children.add(key[len(needle):].split(".", 1)[0])
        return sorted(children)

    config.get_optional.side_effect = _get_optional
    config.list_subkeys.side_effect = _list_subkeys
    return config


_FULL_PERSONA_YAML = {
    "frustrated_customer": {
        "profile": "A customer whose order is late",
        "styling_scenario": "Speaking with visible frustration",
        "task": "Resolve the delayed order",
        "input_format": "Casual chat messages",
        "expected_output_format": "Empathetic, concise replies",
        "scenarios": [
            {"name": "refund_request", "expected_outcome": "Refund is processed"},
            {"name": "escalation", "expected_outcome": "Ticket is escalated"},
        ],
    },
    "happy_customer": {
        "profile": "A satisfied returning customer",
        "scenarios": [
            {"name": "reorder", "expected_outcome": "Reorder is placed"},
        ],
    },
}


class TestPersonaDataclasses:
    def test_persona_scenario_fields(self):
        scenario = PersonaScenario(name="refund_request", expected_outcome="Refund is processed")
        assert scenario.name == "refund_request"
        assert scenario.expected_outcome == "Refund is processed"

    def test_persona_all_fields(self):
        scenario = PersonaScenario(name="refund_request", expected_outcome="Refund is processed")
        persona = Persona(
            name="frustrated_customer",
            profile="A customer whose order is late",
            styling_scenario="Speaking with visible frustration",
            task="Resolve the delayed order",
            input_format="Casual chat messages",
            expected_output_format="Empathetic, concise replies",
            scenarios=[scenario],
        )
        assert persona.name == "frustrated_customer"
        assert persona.profile == "A customer whose order is late"
        assert persona.styling_scenario == "Speaking with visible frustration"
        assert persona.task == "Resolve the delayed order"
        assert persona.input_format == "Casual chat messages"
        assert persona.expected_output_format == "Empathetic, concise replies"
        assert persona.scenarios == [scenario]

    def test_persona_optional_styling_fields_default_none(self):
        persona = Persona(name="minimal", profile="A minimal persona", scenarios=[])
        assert persona.styling_scenario is None
        assert persona.task is None
        assert persona.input_format is None
        assert persona.expected_output_format is None


class TestPersonaConfigResolver:
    def test_resolves_all_configured_personas_when_none_requested(self):
        config = _config_with(_FULL_PERSONA_YAML)
        resolver = PersonaConfigResolver(config=config)

        personas = resolver.resolve(None)

        assert {p.name for p in personas} == {"frustrated_customer", "happy_customer"}

    def test_all_styling_fields_parsed_for_full_persona(self):
        config = _config_with(_FULL_PERSONA_YAML)
        resolver = PersonaConfigResolver(config=config)

        personas = {p.name: p for p in resolver.resolve(None)}
        frustrated = personas["frustrated_customer"]

        assert frustrated.profile == "A customer whose order is late"
        assert frustrated.styling_scenario == "Speaking with visible frustration"
        assert frustrated.task == "Resolve the delayed order"
        assert frustrated.input_format == "Casual chat messages"
        assert frustrated.expected_output_format == "Empathetic, concise replies"

    def test_nested_scenarios_parsed_in_order(self):
        config = _config_with(_FULL_PERSONA_YAML)
        resolver = PersonaConfigResolver(config=config)

        personas = {p.name: p for p in resolver.resolve(None)}
        frustrated = personas["frustrated_customer"]

        assert frustrated.scenarios == [
            PersonaScenario(name="refund_request", expected_outcome="Refund is processed"),
            PersonaScenario(name="escalation", expected_outcome="Ticket is escalated"),
        ]

    def test_persona_without_optional_styling_fields_defaults_to_none(self):
        config = _config_with(_FULL_PERSONA_YAML)
        resolver = PersonaConfigResolver(config=config)

        personas = {p.name: p for p in resolver.resolve(None)}
        happy = personas["happy_customer"]

        assert happy.styling_scenario is None
        assert happy.task is None
        assert happy.input_format is None
        assert happy.expected_output_format is None
        assert happy.scenarios == [
            PersonaScenario(name="reorder", expected_outcome="Reorder is placed"),
        ]

    def test_zero_personas_configured_returns_empty_list(self):
        config = _config_with({})
        resolver = PersonaConfigResolver(config=config)

        assert resolver.resolve(None) == []

    def test_explicit_empty_selection_returns_empty_list(self):
        config = _config_with(_FULL_PERSONA_YAML)
        resolver = PersonaConfigResolver(config=config)

        assert resolver.resolve([]) == []

    def test_selected_persona_filtering(self):
        config = _config_with(_FULL_PERSONA_YAML)
        resolver = PersonaConfigResolver(config=config)

        personas = resolver.resolve(["happy_customer"])

        assert [p.name for p in personas] == ["happy_customer"]

    def test_selected_but_missing_persona_raises(self):
        config = _config_with(_FULL_PERSONA_YAML)
        resolver = PersonaConfigResolver(config=config)

        with pytest.raises(PersonaConfigError):
            resolver.resolve(["does_not_exist"])

    def test_default_config_manager_used_when_none_provided(self, mocker):
        instance = _config_with(_FULL_PERSONA_YAML)
        mocker.patch(
            "deepeval_platform.config.config_manager.ConfigManager.instance",
            return_value=instance,
        )

        resolver = PersonaConfigResolver()
        personas = resolver.resolve(["happy_customer"])

        assert [p.name for p in personas] == ["happy_customer"]
