"""ConversationGenerator — native ConversationSimulator per scenario, stable
divmod distribution, and explicit ending-status extraction (M4.1, R5/R2).
"""
from __future__ import annotations

from dataclasses import dataclass

from deepeval.dataset import ConversationalGolden
from deepeval.models.base_model import DeepEvalBaseLLM
from deepeval.simulator import ConversationSimulator
from deepeval.test_case import ConversationalTestCase

from deepeval_platform.synthetic.bot_invoker_base import BotInvokerBase
from deepeval_platform.synthetic.persona import Persona, PersonaScenario

_BOT_UNREACHABLE_CONTENT = "[BOT_UNREACHABLE]"


@dataclass
class GeneratedConversation:
    persona_name: str
    scenario_name: str
    turns: list[dict]
    ending_status: str
    bot_error: dict | None


class ConversationGenerator:
    def __init__(self, judge_model: DeepEvalBaseLLM, invoker: BotInvokerBase) -> None:
        self._judge_model = judge_model
        self._invoker = invoker

    def generate(
        self,
        persona: Persona,
        conversations_per_persona: int,
        max_turns: int,
    ) -> list[GeneratedConversation]:
        scenarios = persona.scenarios
        if not scenarios:
            return []

        base, remainder = divmod(conversations_per_persona, len(scenarios))
        records: list[GeneratedConversation] = []
        for index, scenario in enumerate(scenarios):
            allocation = base + 1 if index < remainder else base
            if allocation == 0:
                continue
            try:
                records.extend(
                    self._generate_for_scenario(persona, scenario, allocation, max_turns)
                )
            except Exception:
                continue
        return records

    def _generate_for_scenario(
        self,
        persona: Persona,
        scenario: PersonaScenario,
        allocation: int,
        max_turns: int,
    ) -> list[GeneratedConversation]:
        golden = ConversationalGolden(
            scenario=scenario.name,
            expected_outcome=scenario.expected_outcome,
            user_description=persona.profile,
        )
        simulator = ConversationSimulator(
            model_callback=self._invoker,
            simulator_model=self._judge_model,
        )
        test_cases = simulator.simulate(
            conversational_goldens=[golden] * allocation,
            max_user_simulations=max_turns,
        )
        return [
            self._to_record(persona, scenario, test_case, max_turns)
            for test_case in test_cases
        ]

    def _to_record(
        self,
        persona: Persona,
        scenario: PersonaScenario,
        test_case: ConversationalTestCase,
        max_turns: int,
    ) -> GeneratedConversation:
        turns = test_case.turns

        bot_error: dict | None = None
        for turn in turns:
            if turn.role == "assistant" and turn.content == _BOT_UNREACHABLE_CONTENT:
                bot_error = (turn.metadata or {}).get("error")
                break

        if bot_error is not None:
            ending_status = "bot_failure"
        else:
            user_turn_count = sum(1 for turn in turns if turn.role == "user")
            ended_early = user_turn_count < max_turns
            if ended_early and scenario.expected_outcome:
                ending_status = "expected_outcome_reached"
            elif ended_early:
                ending_status = "natural_conclusion"
            else:
                ending_status = "max_turn_incomplete"

        return GeneratedConversation(
            persona_name=persona.name,
            scenario_name=scenario.name,
            turns=[
                {"role": turn.role, "content": turn.content, "metadata": turn.metadata or {}}
                for turn in turns
            ],
            ending_status=ending_status,
            bot_error=bot_error,
        )
