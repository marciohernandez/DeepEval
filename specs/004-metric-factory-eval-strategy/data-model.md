# Phase 1 Data Model: MetricFactory + EvaluationStrategy Integration

All entities below live under `deepeval_platform/evaluation/`. None alter
`NormalizedTrace` (M2.2), `EvaluationStrategyBase`/`StrategyFactory`/`BotType` (M2.1), or
`repositories/models.py` (M1).

## MetricBase (ABC)

`deepeval_platform/evaluation/metrics/metric_base.py`

| Member | Type | Notes |
|---|---|---|
| `_native_metric_cls` | `ClassVar[type[BaseMetric]]` (abstract) | Each concrete subclass sets this to exactly one native DeepEval metric class (FR-002). |
| `__init__(self, threshold: float, deepeval_model: DeepEvalBaseLLM)` | — | Constructs `self._native = self._native_metric_cls(threshold=threshold, model=deepeval_model, async_mode=True)`. |
| `threshold` | `float` (property) | Proxies `self._native.threshold` (FR-001). |
| `passed` | `bool \| None` (property) | Proxies `self._native.success`; `None` before the first `measure()` call (FR-001). |
| `measure(self, context: EvaluationContext) -> MetricResult` | `async def` | Builds an `LLMTestCase` from `context.trace` (mapping, research.md §7), `await self._native.a_measure(test_case, _show_indicator=False)`, wraps `self._native.{score,threshold,success,reason}` into a `MetricResult` (FR-001, FR-002). Raises on failure — the orchestrator, not `MetricBase`, is responsible for catching and isolating (FR-011/FR-015); `MetricBase` never swallows exceptions itself. |

**Validation rules**: none beyond what DeepEval's own `check_llm_test_case_params` already enforces
per metric (research.md §3) — `MetricBase` does not duplicate `ValidationRule` (M2.2).

**State transitions**: an instance is single-use per `measure()` call (FR-008 — a fresh instance
per `MetricFactory.create()`, never reused across traces); `passed`/`threshold` reflect only the
most recent `measure()`.

## Concrete metric wrappers

`deepeval_platform/evaluation/metrics/native/*.py` — six subclasses, one native metric each,
self-registered via `@MetricFactory.register(<canonical_name>)`:

| Canonical name | Native class |
|---|---|
| `answer_relevancy` | `AnswerRelevancyMetric` |
| `faithfulness` | `FaithfulnessMetric` |
| `contextual_precision` | `ContextualPrecisionMetric` |
| `contextual_recall` | `ContextualRecallMetric` |
| `contextual_relevancy` | `ContextualRelevancyMetric` |
| `tool_correctness` | `ToolCorrectnessMetric` |

Each file is the minimal body shown in research.md §8 — no per-wrapper logic beyond the class
attribute and the registration decorator.

## MetricFactory

`deepeval_platform/evaluation/metrics/metric_factory.py`

| Member | Signature | Notes |
|---|---|---|
| `_registry` | `ClassVar[dict[str, type[MetricBase]]]` | Populated exclusively via `register()`; never edited directly (FR-008/FR-009). |
| `register(cls, name: str)` | `classmethod` decorator factory | Raises `DuplicateMetricNameError(name, existing_cls, new_cls)` immediately if `name` is already registered (FR-009, edge case). |
| `create(cls, name: str, *, threshold: float, deepeval_model: DeepEvalBaseLLM) -> MetricBase` | `classmethod` | Raises `UnknownMetricError(name, supported=sorted(cls._registry))` if `name` is not registered (FR-010). Returns a **new** instance every call (FR-008) — never caches/reuses. Never reads `ConfigManager` (FR-004). |

## EvaluationContext (dataclass)

`deepeval_platform/evaluation/evaluation_context.py`

| Field | Type | Notes |
|---|---|---|
| `trace` | `NormalizedTrace` | M2.2 output, read-only from this module's perspective (FR-003). |
| `thresholds` | `dict[str, float]` | Fully resolved `{canonical_metric_name: threshold}` map for every metric in the request, built by `EvaluationOrchestrator` before construction (FR-004/FR-005). Exactly two fields total, per FR-003. |

One `EvaluationContext` per trace evaluation (not per metric) — passed unmodified to every
`MetricBase.measure()` call for that trace.

## MetricResult (dataclass) — NEW type, resolves the naming collision (research.md §1)

`deepeval_platform/evaluation/evaluation_result.py`

| Field | Type | Notes |
|---|---|---|
| `score` | `float \| None` | `None` exclusively for exception/timeout/insufficient-input failures — never coerced to `0.0` (FR-006). |
| `threshold` | `float` | The threshold actually applied (configured or native default) — always populated, even on failure (FR-006). |
| `passed` | `bool` | `False` whenever `score is None`; otherwise `score >= threshold` per the native metric's own `success` (FR-006). |
| `error` | `ErrorDetail \| None` | `None` on success; populated on exception/timeout/insufficient-input (FR-006, FR-011, FR-015). |

## ErrorDetail (dataclass)

`deepeval_platform/evaluation/errors.py`

| Field | Type | Notes |
|---|---|---|
| `category` | `str` | `type(exc).__name__` (e.g. `MissingTestCaseParamsError`, `TimeoutError`) — or `"timeout"` for the orchestrator's own `asyncio.wait_for` expiry. |
| `message` | `str` | Redacted, length-capped `str(exc)` — never raw payloads/credentials (FR-006, SC-008). |

## EvaluationResult (dataclass) — the spec's Key Entity; distinct from `repositories.models.EvaluationResult`

`deepeval_platform/evaluation/evaluation_result.py`

| Field | Type | Notes |
|---|---|---|
| `passed` | `bool` | `all(m.passed for m in metrics.values())` — AND aggregation (FR-007). |
| `metrics` | `dict[str, MetricResult]` | One entry per requested metric name, keyed by canonical name (SC-001: 100% coverage of the requested list). |

## Exceptions

`deepeval_platform/evaluation/errors.py` — all raised by `EvaluationOrchestrator` before
constructing `EvaluationContext` or executing any `measure()`, per the spec's fail-fast/abort-whole-
trace contract:

| Exception | Raised when | FR |
|---|---|---|
| `EmptyMetricListError` | `metric_names == []` | FR-012 |
| `UnknownMetricError` | any name not in `MetricFactory._registry`; message lists all unknown names + all supported names | FR-010 |
| `DuplicateMetricRequestError` | `metric_names` contains repeats; message lists all duplicated names | FR-010, edge case |
| `DuplicateMetricNameError` | two `MetricBase` subclasses register the same canonical name; message identifies the name and both classes | FR-009, edge case |
| `InvalidThresholdError` | any resolved threshold is non-numeric or outside `0.0–1.0`; message lists every offending `(metric, value)` pair | FR-005 |
| `InvalidTimeoutError` | global default or any per-metric override is non-numeric or `<= 0`; message lists every offending `(metric_or_"default", value)` pair | FR-015 |
| `ConfigResolutionError` | `ConfigManager` itself raises while resolving thresholds/timeouts for `bot_id`; wraps the original exception, fail-closed | FR-004 |

All inherit from a single `EvaluationOrchestratorError` base for callers who want one catch-all.

## EvaluationOrchestrator

`deepeval_platform/evaluation/evaluation_orchestrator.py`

| Member | Signature | Notes |
|---|---|---|
| `__init__(self, config: ConfigManager \| None = None)` | — | Defaults to `ConfigManager.instance()` (Singleton, M1); injectable for tests. |
| `evaluate(self, trace: NormalizedTrace, bot_id: str, metric_names: list[str]) -> EvaluationResult` | `async def` | Full flow: (1) reject empty list (FR-012); (2) validate names registered + unique (FR-010); (3) resolve thresholds via `ConfigManager`, fallback to native default, validate range (FR-004/FR-005); (4) resolve timeouts (global + overrides), validate `>0` (FR-015); (5) resolve judge once (research.md §5); (6) build the one `EvaluationContext`; (7) `MetricFactory.create()` + concurrent `measure()` under `asyncio.wait_for` per metric (FR-013/FR-014); (8) aggregate into `EvaluationResult`, isolating any per-metric exception/timeout (FR-011/FR-015) without retry. |

**Concurrency contract**: step (7) uses `asyncio.gather()` over one coroutine per metric; each
coroutine independently catches its own exception/timeout and returns a `MetricResult` (never
raises past the gather) — so aggregation order-independence (FR-014) falls out naturally, no
special-casing needed.

**Config resolution contract**: `bot_id` with zero `ConfigManager` entries is *not* an error —
every metric falls back to its native default threshold/timeout (FR-005/FR-015, "unknown bot_id"
edge case). A `ConfigManager` exception *while* resolving (e.g. malformed YAML) *is* fail-closed
(`ConfigResolutionError`, FR-004).

**str → float conversion**: `ConfigManager.get_optional(key, default="")` returns `str`.
`ConfigManager.get()` already treats "key missing" and "key present with empty-string value"
identically (both raise `ConfigError` internally, both fall through to `get_optional`'s default) —
so the orchestrator does not need to distinguish those two cases itself. Per threshold/timeout
key: call `get_optional(key, default="")`; an empty-string result means "not configured" → apply
the metric's native default (FR-005/FR-015); a non-empty result is parsed via `float(value)`,
with `ValueError`/`TypeError` treated as an explicitly-configured invalid value → fail-closed
abort (`InvalidThresholdError`/timeout equivalent, FR-005/FR-015) — never silently falls back to
the native default once a non-empty string was present.
