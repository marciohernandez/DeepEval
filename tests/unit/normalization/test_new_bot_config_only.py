"""US2 — Declaring a new bot's field mapping without writing code (M2.2).

Validates the extensibility contract Phase 3 (FieldMapper/TraceNormalizer) already
delivers: onboarding a bot is purely a bots.yaml (fixture config) edit. No new
production code in this phase.
"""
from __future__ import annotations

from datetime import datetime

from deepeval_platform.normalization.trace_normalizer import TraceNormalizer
from deepeval_platform.repositories.models import TraceRecord


def _make_record(bot_id: str, input_=None, output=None, metadata=None) -> TraceRecord:
    return TraceRecord(
        trace_id="t1",
        session_id=None,
        bot_id=bot_id,
        input=input_ if input_ is not None else {},
        output=output if output is not None else {},
        metadata=metadata if metadata is not None else {},
        start_time=datetime(2026, 1, 1),
        end_time=None,
    )


# A fixture bots.yaml fragment declaring a bot NOT present in the real config/bots.yaml.
_FIXTURE_BOT_TYPES = {
    "brand_new_bot": "rag",
    "sibling_bot": "rag",
}
_FIXTURE_MAPPING = {
    "bots.brand_new_bot.field_mapping.input": "input.data.question",
    "bots.brand_new_bot.field_mapping.output": "output.data.answer",
    "bots.sibling_bot.field_mapping.input": "input.query.text",
    "bots.sibling_bot.field_mapping.output": "output.result.text",
}


def _stub_config(mocker):
    config = mocker.MagicMock()

    def _get(key: str):
        from deepeval_platform.config.config_manager import ConfigError

        for bot_id, bot_type in _FIXTURE_BOT_TYPES.items():
            if key == f"bots.{bot_id}.bot_type":
                return bot_type
        raise ConfigError(key, ".env or config/*.yaml")

    config.get.side_effect = _get
    config.get_optional.side_effect = lambda key, default="": _FIXTURE_MAPPING.get(key, default)
    mocker.patch(
        "deepeval_platform.config.config_manager.ConfigManager.instance",
        return_value=config,
    )
    return config


class TestNewBotConfigOnlyOnboarding:
    def test_new_bot_field_mapping_declared_only_in_config_normalizes_correctly(self, mocker):
        _stub_config(mocker)
        record = _make_record(
            "brand_new_bot",
            input_={"data": {"question": "Q"}},
            output={"data": {"answer": "A"}},
        )

        trace = TraceNormalizer().normalize(record)

        assert trace.input == "Q"
        assert trace.output == "A"


class TestSiblingBotsResolveIndependently:
    def test_two_bots_same_platform_each_use_only_their_own_mapping(self, mocker):
        _stub_config(mocker)
        brand_new_record = _make_record(
            "brand_new_bot",
            input_={"data": {"question": "Q1"}},
            output={"data": {"answer": "A1"}},
        )
        sibling_record = _make_record(
            "sibling_bot",
            input_={"query": {"text": "Q2"}},
            output={"result": {"text": "A2"}},
        )

        normalizer = TraceNormalizer()
        brand_new_trace = normalizer.normalize(brand_new_record)
        sibling_trace = normalizer.normalize(sibling_record)

        assert brand_new_trace.input == "Q1"
        assert brand_new_trace.output == "A1"
        assert sibling_trace.input == "Q2"
        assert sibling_trace.output == "A2"
