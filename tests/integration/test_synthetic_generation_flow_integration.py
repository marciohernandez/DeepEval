"""Primary end-to-end integration flow for the Synthetic Dataset Generator
(M4.1, T032): authenticated generation -> persistence -> fresh-service
retrieval -> semantic search -> JSON/CSV export, using a stubbed LLM, a local
Flowise HTTP bot, a local LangChain direct-call bot, and test Supabase/Qdrant.

Requires a dedicated test environment (see test_synthetic_storage_integration.py
for the same DATASET_TEST_ORG_A_ACCESS_TOKEN gate). Skips explicitly, not a
pass claim, when absent.
"""
from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import MagicMock

import pytest
from deepeval.models.base_model import DeepEvalBaseLLM
from deepeval.simulator.schema import ConversationCompletion, SimulatedInput

from deepeval_platform.synthetic.bot_invoker_factory import BotInvokerFactory
from deepeval_platform.synthetic.flowise_bot_invoker import FlowiseBotInvoker
from deepeval_platform.synthetic.langchain_bot_invoker import LangChainBotInvoker
from deepeval_platform.synthetic.synthetic_dataset_generator import SyntheticDatasetGenerator

_ORG_A_TOKEN = os.environ.get("DATASET_TEST_ORG_A_ACCESS_TOKEN")

pytestmark = pytest.mark.skipif(
    not _ORG_A_TOKEN,
    reason=(
        "DATASET_TEST_ORG_A_ACCESS_TOKEN is required for the real Supabase/Qdrant "
        "primary flow; skipping, not passing, when absent."
    ),
)


class _FakeJudgeModel(DeepEvalBaseLLM):
    """Deterministic fake driving the real ConversationSimulator without a
    live LLM: answers SimulatedInput/ConversationCompletion schema requests.
    """

    def load_model(self):
        return self

    def get_model_name(self) -> str:
        return "fake-judge-model"

    def generate(self, prompt: str, schema=None):
        if schema is SimulatedInput:
            return SimulatedInput(simulated_input="Can you help me with my issue?")
        if schema is ConversationCompletion:
            # The prompt embeds a static example conversation plus the real,
            # empty-until-now history after "Conversation History:"; only the
            # latter tells us whether a turn has actually happened yet.
            section = prompt.rsplit("Conversation History:", 1)[-1].strip()
            is_complete = not section.startswith("[]")
            return ConversationCompletion(
                is_complete=is_complete, reason="resolved" if is_complete else "continue"
            )
        return "ok"

    async def a_generate(self, prompt: str, schema=None):
        return self.generate(prompt, schema=schema)


class _FixedBotInvokerFactory:
    """Test-local stand-in for BotInvokerFactory selecting a real invoker by bot_id."""

    _flowise_port: int | None = None
    _fail_next_flowise_call = False

    @classmethod
    def create(cls, bot_id: str, config=None):
        if bot_id == "flowise_test_bot":
            return FlowiseBotInvoker(
                bot_id=bot_id, endpoint_url=f"http://127.0.0.1:{cls._flowise_port}/api"
            )
        if bot_id == "langchain_test_bot":
            return LangChainBotInvoker(
                bot_id=bot_id,
                chain_target="tests.integration._fixtures.fake_langchain_chain.chain",
            )
        raise ValueError(f"Unknown test bot_id: {bot_id}")


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)

        if _FixedBotInvokerFactory._fail_next_flowise_call:
            _FixedBotInvokerFactory._fail_next_flowise_call = False
            self.send_response(500)
            self.end_headers()
            return

        body = json.dumps({"text": "Here is help from the Flowise bot."}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: A002
        pass


@pytest.fixture
def flowise_server():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _FixedBotInvokerFactory._flowise_port = server.server_address[1]
    _FixedBotInvokerFactory._fail_next_flowise_call = False
    yield server
    server.shutdown()
    thread.join(timeout=5)


def _make_facade(tmp_path, mocker, fake_goldens):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "order.md").write_text("Order help center article.")
    output_dir = tmp_path / "output"

    config = MagicMock()
    values = {
        "synthetic.docs_dir": str(docs_dir),
        "synthetic.output_dir": str(output_dir),
        "synthetic.goldens_per_persona": "1",
        "synthetic.conversations_per_persona": "2",
        "synthetic.max_conversation_turns": "3",
        "evaluation.llm_judge.provider": "openai",
        "evaluation.llm_judge.model": "gpt-4o",
        "synthetic.exporters.json": (
            "deepeval_platform.synthetic.json_dataset_exporter.JsonDatasetExporter"
        ),
        "synthetic.exporters.csv": (
            "deepeval_platform.synthetic.csv_dataset_exporter.CsvDatasetExporter"
        ),
    }
    config.get.side_effect = lambda key: values[key]

    persona_resolver = MagicMock()
    from deepeval_platform.synthetic.persona import Persona, PersonaScenario

    persona_resolver.resolve.return_value = [
        Persona(
            name="frustrated_customer",
            profile="A customer whose order is late",
            scenarios=[
                PersonaScenario(name="refund_request", expected_outcome="Refund is processed"),
                PersonaScenario(name="escalation", expected_outcome="Ticket is escalated"),
            ],
        )
    ]

    synthesizer_cls = MagicMock()

    def make_synthesizer(*, model, styling_config):
        instance = MagicMock()
        instance.generate_goldens_from_docs.side_effect = (
            lambda document_paths, max_goldens_per_context: fake_goldens(
                document_paths[0], max_goldens_per_context
            )
        )
        return instance

    synthesizer_cls.side_effect = make_synthesizer
    mocker.patch("deepeval_platform.synthetic.golden_generator.Synthesizer", synthesizer_cls)

    llm_provider_factory_cls = MagicMock()
    llm_provider_factory_cls.create.return_value.as_deepeval_model.return_value = _FakeJudgeModel()

    facade = SyntheticDatasetGenerator(
        config=config,
        persona_resolver=persona_resolver,
        bot_invoker_factory_cls=_FixedBotInvokerFactory,
        llm_provider_factory_cls=llm_provider_factory_cls,
    )
    return facade, output_dir


@pytest.mark.integration
class TestSyntheticGenerationFlowIntegration:
    def test_full_flow_with_flowise_bot(self, tmp_path, mocker, flowise_server):
        from deepeval.dataset.golden import Golden

        def fake_goldens(path, count):
            return [Golden(input=f"q{i}", source_file=path) for i in range(count)]

        facade, output_dir = _make_facade(tmp_path, mocker, fake_goldens)

        dataset = facade.generate(
            access_token=_ORG_A_TOKEN, bot_id="flowise_test_bot", persona_names=None
        )

        fresh_facade, _ = _make_facade(tmp_path, mocker, fake_goldens)
        reloaded = fresh_facade.get_dataset(access_token=_ORG_A_TOKEN, dataset_id=dataset.id)

        assert reloaded.id == dataset.id
        assert len(reloaded.goldens) == 1
        assert len(reloaded.conversations) == 2

        hits = fresh_facade.search_content(
            access_token=_ORG_A_TOKEN, query="order help", k=5
        )
        assert isinstance(hits, list)

        json_path = fresh_facade.export_dataset(
            access_token=_ORG_A_TOKEN, dataset_id=dataset.id, format="json"
        )
        csv_path = fresh_facade.export_dataset(
            access_token=_ORG_A_TOKEN, dataset_id=dataset.id, format="csv"
        )
        assert json_path.exists()
        assert csv_path.exists()

    def test_both_bot_invokers_produce_equivalent_normalized_conversations(
        self, tmp_path, mocker, flowise_server
    ):
        from deepeval.dataset.golden import Golden

        def fake_goldens(path, count):
            return [Golden(input=f"q{i}", source_file=path) for i in range(count)]

        flowise_facade, _ = _make_facade(tmp_path, mocker, fake_goldens)
        langchain_facade, _ = _make_facade(tmp_path, mocker, fake_goldens)

        flowise_dataset = flowise_facade.generate(
            access_token=_ORG_A_TOKEN, bot_id="flowise_test_bot"
        )
        langchain_dataset = langchain_facade.generate(
            access_token=_ORG_A_TOKEN, bot_id="langchain_test_bot"
        )

        flowise_fields = {
            (c.persona_name, c.scenario_name, c.ending_status)
            for c in flowise_dataset.conversations
        }
        langchain_fields = {
            (c.persona_name, c.scenario_name, c.ending_status)
            for c in langchain_dataset.conversations
        }
        assert flowise_fields == langchain_fields

    def test_one_failed_conversation_does_not_block_remaining_attempts(
        self, tmp_path, mocker, flowise_server
    ):
        from deepeval.dataset.golden import Golden

        def fake_goldens(path, count):
            return [Golden(input=f"q{i}", source_file=path) for i in range(count)]

        facade, _ = _make_facade(tmp_path, mocker, fake_goldens)
        _FixedBotInvokerFactory._fail_next_flowise_call = True

        dataset = facade.generate(access_token=_ORG_A_TOKEN, bot_id="flowise_test_bot")

        assert len(dataset.conversations) == 2
        statuses = {c.ending_status for c in dataset.conversations}
        assert "bot_failure" in statuses

        fresh_facade, _ = _make_facade(tmp_path, mocker, fake_goldens)
        reloaded = fresh_facade.get_dataset(access_token=_ORG_A_TOKEN, dataset_id=dataset.id)
        failed = [c for c in reloaded.conversations if c.ending_status == "bot_failure"]
        assert len(failed) == 1
        assert failed[0].bot_error is not None

        json_path = fresh_facade.export_dataset(
            access_token=_ORG_A_TOKEN, dataset_id=dataset.id, format="json"
        )
        csv_path = fresh_facade.export_dataset(
            access_token=_ORG_A_TOKEN, dataset_id=dataset.id, format="csv"
        )
        assert "bot_failure" in json_path.read_text()
        assert "bot_failure" in csv_path.read_text()
