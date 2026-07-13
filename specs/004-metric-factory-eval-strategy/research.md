# Phase 0 Research: MetricFactory + EvaluationStrategy Integration

All items below were "NEEDS CLARIFICATION" candidates in Technical Context or open technical
decisions left to this plan by the spec's own Assumptions section. Each is resolved with a
verified finding (not guesswork) against the installed `deepeval` package and the existing
codebase.

## 1. Naming collision: `EvaluationResult` (M3.1, in-memory) vs `EvaluationResult` (M1, persisted)

- **Decision**: Keep the spec's own Key Entity name `EvaluationResult` for the new in-memory,
  per-trace aggregate (`deepeval_platform/evaluation/evaluation_result.py`). Introduce a new type,
  `MetricResult`, for the per-metric embedded detail (score, threshold, passed, reason, error) —
  `EvaluationResult.metrics: dict[str, MetricResult]`.
- **Rationale**: `specs/004-metric-factory-eval-strategy/spec.md` Key Entities and FR-006/FR-007
  repeatedly and specifically name the trace-level aggregate `EvaluationResult`; renaming it would
  silently diverge from the ratified spec text without a corresponding spec amendment. The actual
  ambiguity flagged by the user is at the *per-metric* granularity — `deepeval_platform/
  repositories/models.py:EvaluationResult` (M1) is verified to already be a **per-metric row**
  (fields: `metric_name: str`, `score: float`, `passed: bool`, `threshold: float`, `reason: str |
  None` — one row per metric, meant for a Supabase insert), not a per-trace aggregate. So the two
  `EvaluationResult` names describe genuinely different shapes at different granularities; the
  collision is real only if both are imported unqualified in the same scope. `MetricResult` is the
  correctly-scoped new name for the per-metric shape, exactly matching the user's own suggestion.
- **Consequence for a future milestone (M3.2, out of scope here)**: persisting M3.1's output will
  require an explicit mapping function — `EvaluationResult.metrics[name] -> repositories.models.
  EvaluationResult` (one persisted row per `MetricResult`) — not a shared class. Documented here so
  it isn't rediscovered as a surprise later.
- **Alternatives considered**: Renaming the in-memory aggregate (e.g. `TraceEvaluationResult`) —
  rejected, deviates from the ratified spec's own entity name for no functional benefit.

## 2. `measure()` signature: sync vs async

- **Decision**: `MetricBase.measure(self, context: EvaluationContext) -> MetricResult` is `async
  def`, internally `await`-ing the wrapped native metric's own `a_measure()`.
- **Rationale**: Verified in the installed `deepeval` package
  (`deepeval.metrics.base_metric.BaseMetric`) that every metric already exposes both `measure()`
  (sync, `async_mode: bool = True` by default) and `a_measure()` (native async coroutine) — DeepEval
  itself is built async-first for exactly this reason. FR-014 requires the orchestrator to run all
  of a trace's `measure()` calls concurrently, and FR-015 requires a per-call timeout; `asyncio.
  gather()` + `asyncio.wait_for()` around `a_measure()` is the direct, idiomatic mechanism with zero
  custom threading/loop-management code, and avoids reimplementing what DeepEval's own async support
  already provides (Principle II).
- **Alternatives considered**: Keep `measure()` synchronous and run each call in a
  `ThreadPoolExecutor` for concurrency — rejected; adds a redundant compatibility layer when native
  async execution is already available, and the surrounding stack (FastAPI, APScheduler) already
  supports async call sites.

## 3. Insufficient-input edge case (e.g. `faithfulness` needs `context`, trace has none)

- **Decision**: `MetricBase` does **not** pre-validate `NormalizedTrace` fields before building the
  `LLMTestCase` and calling `a_measure()`. No duplicate minimum-field check is added.
- **Rationale**: Verified in `deepeval.metrics.utils.check_llm_test_case_params` (called from every
  native metric's `measure`/`a_measure` before scoring) that DeepEval already raises
  `MissingTestCaseParamsError` (e.g. for an empty `actual_output`, and equivalently for other
  required `SingleTurnParams` such as `retrieval_context`) whenever a required field for that metric
  is missing/empty. That exception surfaces exactly like any other `measure()` exception and is
  caught by the orchestrator's standard per-metric isolation path (FR-011), producing `score=null,
  passed=false` with a sanitized detail — satisfying the spec's edge case ("não como exceção não
  tratada" is about *isolation*, not about DeepEval never raising) without duplicating `ValidationRule`
  (M2.2) or DeepEval's own validation.
- **Alternatives considered**: Re-implementing per-metric minimum-field checks inside `MetricBase`
  — rejected as duplicated logic violating Principle II (DeepEval-First) and Principle I (single
  responsibility — that check already exists in two other places).

## 4. Config schema for thresholds and timeouts

- **Decision**:
  - `config/bots.yaml`, per bot: new `metrics: {<canonical_name>: {threshold: <float>}}` map,
    sibling to the existing `bot_type`/`platform`/`field_mapping` keys.
  - `config/settings.yaml`: new `evaluation:` top-level section —
    `evaluation.metric_timeout_seconds` (global default, required), `evaluation.
    metric_timeout_overrides.<canonical_name>` (optional per-metric override),
    `evaluation.llm_judge.provider` / `evaluation.llm_judge.model` (judge selection, §5 below).
  - Read via `ConfigManager.get_optional("bots.<bot_id>.metrics.<name>.threshold")` /
    `ConfigManager.get_optional("evaluation.metric_timeout_overrides.<name>")`, etc.
- **Rationale**: Verified `ConfigManager._flatten_yaml` already flattens arbitrarily nested YAML
  into dotted keys and is format-agnostic — no changes to `ConfigManager` itself are needed to
  support these new keys; they fall out of the existing flatten mechanism for free. Mirrors the
  existing bot-scoped-vs-global split already used in the repo (`bots.yaml` for per-bot config,
  `settings.yaml` for global defaults).
- **Alternatives considered**: A new dedicated `config/metrics.yaml` file — rejected, unnecessary
  new file when the existing two-file split already covers the bot-scoped/global axis needed here.

## 5. LLM judge provider selection

- **Decision**: `EvaluationOrchestrator` resolves the judge **once per `evaluate()` call** (not once
  per metric) via `ConfigManager.get_optional("evaluation.llm_judge.provider", default=...)` /
  `get_optional("evaluation.llm_judge.model", default=...)`, calls `LLMProviderFactory.create(
  provider, model)` (M1), and reuses the single resulting `provider.as_deepeval_model()` instance
  across every `MetricFactory.create()` call for that trace.
- **Rationale**: Matches the pattern already established for thresholds/timeouts (resolved once per
  trace by the orchestrator, never per-metric or inside `MetricFactory`/`MetricBase`). Confirmed via
  the user's own M3.1 stack brief: `LLMProviderBase` does not implement `DeepEvalBaseLLM` directly
  (diverging `generate()` contracts — `tuple[str, TokenUsage]` vs DeepEval's own cost type) so
  `as_deepeval_model()` is the only supported way to hand a judge to a `Metric(model=...)`
  constructor; native `GPTModel`/`AnthropicModel`/`OpenRouterModel` are never instantiated directly
  by this feature.
- **Alternatives considered**: Per-metric judge override — out of scope; the spec does not request
  per-metric judge configuration in M3.1, and adding it now would be speculative.

## 6. Error sanitization (FR-006/FR-011/SC-008)

- **Decision**: A single `sanitize_error(exc: BaseException) -> ErrorDetail` helper in
  `deepeval_platform/evaluation/errors.py`. `ErrorDetail.category = type(exc).__name__`;
  `ErrorDetail.message` = a length-capped, regex-redacted `str(exc)` (patterns redacted: API-key-
  shaped tokens, `Bearer <token>` headers, long opaque alphanumeric strings). The orchestrator logs
  the same redacted detail via `logging.getLogger(__name__).exception(...)` for internal
  observability — this milestone has no Langfuse/Confident-AI reporting in scope (Assumptions), so
  stdlib `logging` is the entire "internal observability" surface for now.
- **Rationale**: FR-006/FR-011 require category/code + sanitized message in the public
  `EvaluationResult`, and require that technical detail sent to internal observability is also
  redacted — a single shared helper guarantees both call sites (result field and log line) apply
  the same redaction, instead of two independently-maintained sanitization paths that could drift.
- **Alternatives considered**: Passing raw `str(exc)` straight into `MetricResult.error` — rejected
  outright, directly violates FR-006/FR-011/SC-008.

## 7. `NormalizedTrace` → `LLMTestCase` field mapping

- **Decision**:
  | `NormalizedTrace` field | `LLMTestCase` field |
  |---|---|
  | `input` | `input` |
  | `output` | `actual_output` |
  | `expected_output` | `expected_output` |
  | `context` (list) | `retrieval_context` (list) |
  | `tools_called` (list of project `ToolCall`) | `tools_called` (list of `deepeval.test_case.ToolCall(name=, input_parameters=, output=)`) |

  `messages` and `metadata` are **not** mapped this milestone — no metric in FR-002's list
  (`answer_relevancy`, `faithfulness`, `contextual_precision`, `contextual_recall`,
  `contextual_relevancy`, `tool_correctness`) requires `ConversationalTestCase`.
- **Rationale**: Verified directly against the installed `deepeval` package —
  `ContextualPrecisionMetric`/`ContextualRecallMetric`/`ContextualRelevancyMetric`/
  `FaithfulnessMetric._required_params` all declare `SingleTurnParams.RETRIEVAL_CONTEXT` (not a
  generic "context" field), confirming `context` → `retrieval_context` is the correct mapping, not
  `LLMTestCase.context` (a separate, unused field in this project's usage).
- **Alternatives considered**: Mapping `context` → `LLMTestCase.context` — rejected; verified that
  field is not what any of the six in-scope metrics actually read (`retrieval_context` is).
- **Known gap (documented, not blocking)**: if a future milestone adds a conversational metric under
  `ConversationStrategy`, `messages`/`metadata` mapping to `ConversationalTestCase` will need its own
  research pass — out of scope for M3.1 (FR-002's metric list has no conversational metric yet).
- **Known gap — `tool_correctness` (documented, not blocking)**: `ToolCorrectnessMetric._required_params`
  includes `SingleTurnParams.EXPECTED_TOOLS` (verified against installed `deepeval` 4.0.7), but no
  `NormalizedTrace` field maps to `LLMTestCase.expected_tools` — the table above has no entry for it,
  and `NormalizedTrace` is frozen this milestone (Assumptions). `ToolCorrectnessMetricWrapper.measure()`
  will therefore always raise `MissingTestCaseParamsError` and always land in the FR-011 isolated-failure
  branch (`score=None, passed=False`) — it can never produce a real score in M3.1. This is expected
  behavior, not a defect in the wrapper; sourcing `expected_tools` requires a `NormalizedTrace` field
  addition, which is out of scope here (M2.2 follow-up).

## 8. Metric wrapper implementation shape (Principle I + II + VI)

- **Decision**: `MetricBase` implements `measure()`, `threshold`, and `passed` **once**, generically,
  driven by a single required class attribute each concrete subclass supplies:
  `_native_metric_cls: ClassVar[type[BaseMetric]]`. A concrete wrapper is therefore just:
  ```python
  @MetricFactory.register("faithfulness")
  class FaithfulnessMetricWrapper(MetricBase):
      _native_metric_cls = FaithfulnessMetric
  ```
  `MetricBase.__init__` instantiates `self._native = self._native_metric_cls(threshold=threshold,
  model=deepeval_model, async_mode=True)`; `threshold`/`passed` proxy `self._native.threshold` /
  `self._native.success`.
- **Rationale**: Satisfies FR-009/SC-002 ("adding a metric requires only creating the subclass")
  literally — the subclass body is a single class attribute — while keeping `MetricBase` the one
  place that adapts DeepEval's `BaseMetric` contract to this project's `EvaluationContext`/
  `MetricResult` contract (Principle I single responsibility, Principle II no scoring
  reimplementation).
- **Alternatives considered**: Each wrapper reimplementing its own `measure()` body — rejected,
  duplicates the adapter logic six times for no variation between wrappers.
