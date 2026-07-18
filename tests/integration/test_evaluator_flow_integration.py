"""Integration test for Evaluator (M4.2 T037) — real composition, stubbed HTTP only.

Exercises the real TraceRepository -> TraceCollector.collect_all() -> TraceNormalizer ->
EvaluationOrchestrator -> ResultPublisher -> observer chain against an in-process HTTP
server serving deterministic paginated responses matching the Langfuse `{data, meta}`
list contract. Only the external judge-model boundary is replaced by a deterministic
DeepEvalBaseLLM fake (same convention as test_evaluation_orchestrator_integration.py).
No `.env` is read, no external host is contacted, and no skip/skipif marker is used.
"""
from __future__ import annotations

import http.server
import json
import threading
import typing
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from pydantic import BaseModel

from deepeval.models.base_model import DeepEvalBaseLLM

from deepeval_platform.config.config_manager import ConfigEntry, ConfigManager
from deepeval_platform.evaluation import metrics  # noqa: F401 — triggers native wrapper self-registration
from deepeval_platform.evaluation.evaluation_config import EvaluationConfig, MetricThreshold
from deepeval_platform.evaluation.evaluation_run import RunStatus
from deepeval_platform.evaluation.evaluator import Evaluator
from deepeval_platform.evaluation.result_publisher import ResultObserver


# ---------------------------------------------------------------------------
# Deterministic judge-model fake (mirrors test_evaluation_orchestrator_integration.py)
# ---------------------------------------------------------------------------

def _dummy_value_for_annotation(annotation):
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if origin is typing.Union:
        non_none = [a for a in args if a is not type(None)]
        return _dummy_value_for_annotation(non_none[0]) if non_none else None
    if origin is list:
        item_type = args[0] if args else str
        return [_dummy_value_for_annotation(item_type)]
    if origin is typing.Literal:
        return args[0]
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return _build_dummy_schema(annotation)
    if annotation is float:
        return 1.0
    if annotation is int:
        return 1
    if annotation is bool:
        return True
    return "stub"


def _build_dummy_schema(schema_cls: type[BaseModel]) -> BaseModel:
    kwargs = {
        name: _dummy_value_for_annotation(field.annotation)
        for name, field in schema_cls.model_fields.items()
    }
    return schema_cls(**kwargs)


class _FakeJudgeModel(DeepEvalBaseLLM):
    def load_model(self):
        return self

    def get_model_name(self) -> str:
        return "fake-judge"

    def generate(self, *args, **kwargs) -> str:
        return "{}"

    async def a_generate(self, *args, **kwargs) -> str:
        return "{}"

    async def a_generate_with_schema(self, *args, schema=None, **kwargs):
        assert schema is not None
        return _build_dummy_schema(schema)


# ---------------------------------------------------------------------------
# In-process Langfuse-shaped paginated HTTP stub
# ---------------------------------------------------------------------------

class _LangfuseStubHandler(http.server.BaseHTTPRequestHandler):
    pages: dict[int, dict] = {}

    def do_GET(self) -> None:
        query = parse_qs(urlparse(self.path).query)
        page = int(query.get("page", ["1"])[0])
        payload = self.pages.get(page)
        if payload is None:
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - stdlib signature
        pass


def _start_stub_server(pages: dict[int, dict]) -> http.server.HTTPServer:
    handler_cls = type("_BoundHandler", (_LangfuseStubHandler,), {"pages": pages})
    server = http.server.HTTPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _raw_trace(trace_id: str, session_id: str, timestamp: str) -> dict:
    return {
        "id": trace_id,
        "sessionId": session_id,
        "tags": ["test_rag_bot"],
        "input": {"data": {"question": "What is the refund policy?"}},
        "output": {
            "data": {
                "answer": "Refunds are available within 30 days.",
                "retrieved_contexts": ["Refunds are allowed within 30 days of purchase."],
            }
        },
        "metadata": {"expected_answer": "Refunds within 30 days."},
        "timestamp": timestamp,
    }


def _make_test_config_manager(langfuse_host: str) -> ConfigManager:
    """A real ConfigManager instance, populated directly (bypasses _load()/filesystem)."""
    config = ConfigManager()
    raw = {
        "LANGFUSE_HOST": langfuse_host,
        "LANGFUSE_PUBLIC_KEY": "test-public-key",
        "LANGFUSE_SECRET_KEY": "test-secret-key",
        "bots.test_rag_bot.bot_type": "rag",
        "bots.test_rag_bot.platform": "flowise",
        "bots.test_rag_bot.field_mapping.input": "input.data.question",
        "bots.test_rag_bot.field_mapping.output": "output.data.answer",
        "bots.test_rag_bot.field_mapping.context": "output.data.retrieved_contexts",
        "bots.test_rag_bot.field_mapping.expected_output": "metadata.expected_answer",
        "evaluation.metric_timeout_seconds": "30",
        "evaluation.llm_judge.provider": "openai",
        "evaluation.llm_judge.model": "gpt-4o",
    }
    config._store = {
        key: ConfigEntry(key=key, value=value, source="yaml", source_file="test", is_sensitive=False)
        for key, value in raw.items()
    }
    return config


class _CollectingObserver(ResultObserver):
    def __init__(self) -> None:
        self.calls: list[tuple[object, object]] = []

    def publish(self, run, results) -> None:
        self.calls.append((run, results))


@pytest.mark.integration
class TestEvaluatorFlowIntegration:
    def test_real_composition_reaches_completed_with_one_result_per_fixture_trace(self, mocker):
        page1 = {
            "data": [_raw_trace("trace-1", "sess-1", "2026-07-02T10:00:00")],
            "meta": {"page": 1, "limit": 100, "totalItems": 2, "totalPages": 2},
        }
        page2 = {
            "data": [_raw_trace("trace-2", "sess-2", "2026-07-02T11:00:00")],
            "meta": {"page": 2, "limit": 100, "totalItems": 2, "totalPages": 2},
        }
        server = _start_stub_server({1: page1, 2: page2})
        try:
            host, port = server.server_address
            config = _make_test_config_manager(f"http://{host}:{port}")
            ConfigManager._instance = config
            ConfigManager._loaded = True

            judge = _FakeJudgeModel()
            provider = mocker.MagicMock()
            provider.as_deepeval_model.return_value = judge
            mocker.patch(
                "deepeval_platform.llm.factory.LLMProviderFactory.create", return_value=provider
            )

            evaluator = Evaluator(config_manager=config)
            observer = _CollectingObserver()
            eval_config = EvaluationConfig(
                bot_id="test_rag_bot",
                metric_thresholds=[MetricThreshold("faithfulness", 0.1)],
                period_start=datetime(2026, 7, 1, tzinfo=timezone.utc),
                period_end=datetime(2026, 7, 8, tzinfo=timezone.utc),
            )

            run = evaluator.start(eval_config, observer)

            assert run.wait(20.0) is True, "run did not reach a terminal status in time"
            assert run.status == RunStatus.COMPLETED
            assert run.total == 2
            assert run.processed == 2
            assert run.errors == ()
            assert len(observer.calls) == 1
            _, results = observer.calls[0]
            assert set(results.keys()) == {"trace-1", "trace-2"}
            for trace_id, result in results.items():
                assert "faithfulness" in result.metrics
                metric_result = result.metrics["faithfulness"]
                assert metric_result.error is None, f"{trace_id} failed: {metric_result.error}"
                assert metric_result.score is not None
        finally:
            server.shutdown()
