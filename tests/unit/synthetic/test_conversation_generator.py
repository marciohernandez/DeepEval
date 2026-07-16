"""Unit tests for ConversationGenerator (M4.1, T020). ConversationSimulator is
mocked; the bot invoker is a stub callable (never raises, per BotInvokerBase
contract).
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from deepeval.test_case import ConversationalTestCase, Turn

from deepeval_platform.synthetic.conversation_generator import ConversationGenerator
from deepeval_platform.synthetic.persona import Persona, PersonaScenario


def _persona(scenarios: list[PersonaScenario]) -> Persona:
    return Persona(
        name="frustrated_customer",
        profile="A customer whose order is late",
        scenarios=scenarios,
    )


def _turns(*role_content_pairs, metadata_by_index: dict | None = None) -> list[Turn]:
    metadata_by_index = metadata_by_index or {}
    return [
        Turn(role=role, content=content, metadata=metadata_by_index.get(i))
        for i, (role, content) in enumerate(role_content_pairs)
    ]


def _test_case(turns: list[Turn], scenario: str, expected_outcome: str | None) -> ConversationalTestCase:
    return ConversationalTestCase(turns=turns, scenario=scenario, expected_outcome=expected_outcome)


@pytest.fixture
def mock_simulator(mocker):
    instances = []

    def make_instance(*, model_callback, simulator_model):
        instance = MagicMock()
        instances.append(instance)
        return instance

    simulator_cls = MagicMock(side_effect=make_instance)
    mocker.patch(
        "deepeval_platform.synthetic.conversation_generator.ConversationSimulator",
        simulator_cls,
    )
    return simulator_cls, instances


class TestStableDivmodAllocation:
    def test_conversations_distributed_across_scenarios(self, mock_simulator):
        simulator_cls, instances = mock_simulator
        scenarios = [
            PersonaScenario(name="refund_request", expected_outcome="Refund is processed"),
            PersonaScenario(name="escalation", expected_outcome="Ticket is escalated"),
        ]

        call_sizes = []

        def make_instance(*, model_callback, simulator_model):
            instance = MagicMock()

            def simulate(conversational_goldens, max_user_simulations):
                call_sizes.append(len(conversational_goldens))
                return [
                    _test_case(
                        _turns(("user", "hi"), ("assistant", "hello")),
                        scenario=g.scenario,
                        expected_outcome=g.expected_outcome,
                    )
                    for g in conversational_goldens
                ]

            instance.simulate.side_effect = simulate
            instances.append(instance)
            return instance

        simulator_cls.side_effect = make_instance

        generator = ConversationGenerator(judge_model=MagicMock(), invoker=MagicMock())
        records = generator.generate(
            persona=_persona(scenarios), conversations_per_persona=5, max_turns=10
        )

        assert call_sizes == [3, 2]
        assert len(records) == 5


class TestConfiguredMaxTurns:
    def test_max_turns_passed_as_max_user_simulations(self, mock_simulator):
        simulator_cls, instances = mock_simulator
        scenarios = [PersonaScenario(name="refund_request", expected_outcome="Refund is processed")]

        def make_instance(*, model_callback, simulator_model):
            instance = MagicMock()
            instance.simulate.return_value = [
                _test_case(_turns(("user", "hi"), ("assistant", "hello")), "refund_request", "Refund is processed")
            ]
            instances.append(instance)
            return instance

        simulator_cls.side_effect = make_instance

        generator = ConversationGenerator(judge_model=MagicMock(), invoker=MagicMock())
        generator.generate(persona=_persona(scenarios), conversations_per_persona=1, max_turns=15)

        _, kwargs = instances[0].simulate.call_args
        assert kwargs["max_user_simulations"] == 15


class TestEndingStatusExtraction:
    def _generate_single(self, mock_simulator, turns, scenario_name, expected_outcome, max_turns=5):
        simulator_cls, instances = mock_simulator

        def make_instance(*, model_callback, simulator_model):
            instance = MagicMock()
            instance.simulate.return_value = [_test_case(turns, scenario_name, expected_outcome)]
            instances.append(instance)
            return instance

        simulator_cls.side_effect = make_instance

        scenarios = [PersonaScenario(name=scenario_name, expected_outcome=expected_outcome or "")]
        generator = ConversationGenerator(judge_model=MagicMock(), invoker=MagicMock())
        records = generator.generate(
            persona=_persona(scenarios), conversations_per_persona=1, max_turns=max_turns
        )
        return records[0]

    def test_expected_outcome_reached_when_ended_early_with_expected_outcome(self, mock_simulator):
        turns = _turns(("user", "hi"), ("assistant", "hello"))  # 1 user turn < max_turns(5)
        record = self._generate_single(
            mock_simulator, turns, "refund_request", "Refund is processed", max_turns=5
        )
        assert record.ending_status == "expected_outcome_reached"

    def test_natural_conclusion_when_ended_early_without_expected_outcome(self, mock_simulator):
        turns = _turns(("user", "hi"), ("assistant", "hello"))
        record = self._generate_single(mock_simulator, turns, "chit_chat", None, max_turns=5)
        assert record.ending_status == "natural_conclusion"

    def test_max_turn_incomplete_when_all_turns_consumed(self, mock_simulator):
        turns = _turns(
            ("user", "u1"), ("assistant", "a1"),
            ("user", "u2"), ("assistant", "a2"),
        )  # 2 user turns == max_turns(2)
        record = self._generate_single(
            mock_simulator, turns, "refund_request", "Refund is processed", max_turns=2
        )
        assert record.ending_status == "max_turn_incomplete"

    def test_bot_failure_takes_precedence_over_expected_outcome(self, mock_simulator):
        turns = _turns(
            ("user", "hi"),
            ("assistant", "[BOT_UNREACHABLE]"),
            metadata_by_index={1: {"error": {"code": "invocation_error", "type": "RuntimeError", "message": "boom", "bot_id": "test_rag_bot"}}},
        )
        record = self._generate_single(
            mock_simulator, turns, "refund_request", "Refund is processed", max_turns=5
        )
        assert record.ending_status == "bot_failure"
        assert record.bot_error == {
            "code": "invocation_error",
            "type": "RuntimeError",
            "message": "boom",
            "bot_id": "test_rag_bot",
        }


class TestTranscriptRetentionAndNormalization:
    def test_turns_and_persona_scenario_fields_normalized(self, mock_simulator):
        simulator_cls, instances = mock_simulator
        turns = _turns(("user", "Where is my order?"), ("assistant", "Let me check that for you."))

        def make_instance(*, model_callback, simulator_model):
            instance = MagicMock()
            instance.simulate.return_value = [_test_case(turns, "refund_request", "Refund is processed")]
            instances.append(instance)
            return instance

        simulator_cls.side_effect = make_instance

        scenarios = [PersonaScenario(name="refund_request", expected_outcome="Refund is processed")]
        persona = _persona(scenarios)
        generator = ConversationGenerator(judge_model=MagicMock(), invoker=MagicMock())
        records = generator.generate(persona=persona, conversations_per_persona=1, max_turns=5)

        record = records[0]
        assert record.persona_name == "frustrated_customer"
        assert record.scenario_name == "refund_request"
        assert record.turns == [
            {"role": "user", "content": "Where is my order?", "metadata": {}},
            {"role": "assistant", "content": "Let me check that for you.", "metadata": {}},
        ]


class TestContinuationAfterOneScenarioFailure:
    def test_remaining_scenarios_continue_after_one_simulate_call_raises(self, mock_simulator):
        simulator_cls, instances = mock_simulator
        scenarios = [
            PersonaScenario(name="failing_scenario", expected_outcome="Should fail"),
            PersonaScenario(name="ok_scenario", expected_outcome="Should succeed"),
        ]

        call_order = []

        def make_instance(*, model_callback, simulator_model):
            instance = MagicMock()

            def simulate(conversational_goldens, max_user_simulations):
                scenario_name = conversational_goldens[0].scenario
                call_order.append(scenario_name)
                if scenario_name == "failing_scenario":
                    raise RuntimeError("simulator exploded")
                return [
                    _test_case(
                        _turns(("user", "hi"), ("assistant", "hello")),
                        scenario=g.scenario,
                        expected_outcome=g.expected_outcome,
                    )
                    for g in conversational_goldens
                ]

            instance.simulate.side_effect = simulate
            instances.append(instance)
            return instance

        simulator_cls.side_effect = make_instance

        generator = ConversationGenerator(judge_model=MagicMock(), invoker=MagicMock())
        records = generator.generate(
            persona=_persona(scenarios), conversations_per_persona=2, max_turns=5
        )

        assert call_order == ["failing_scenario", "ok_scenario"]
        assert len(records) == 1
        assert records[0].scenario_name == "ok_scenario"
