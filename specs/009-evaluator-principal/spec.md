# Feature Specification: Evaluator Principal

**Feature Branch**: `009-evaluator-principal`

**Created**: 2026-07-15

**Status**: Draft

**Input**: User description: "Módulos em escopo para M4.2 — Evaluator Principal: EvaluationConfig (dataclass) — configuração de um run: bot_id, métricas, thresholds, período; EvaluationRun (dataclass) — estado de execução: status, progresso, timestamps, errors; Evaluator — orquestra o pipeline completo: extrai traces → normaliza → roda métricas → publica resultados"

## Clarifications

### Session 2026-07-15

- Q: FR-013 (now) — M4.1 (spec 004) left `EvaluationRepository` persistence and `ResultPublisher`
  observer notification explicitly out of scope, producing `EvaluationResult` only in memory.
  Does "publica resultados" in this milestone mean the Evaluator persists run results and
  notifies downstream destinations end-to-end, or does it hand completed results off through a
  defined interface, with persistence/notification built in a later milestone? → A: Interface
  only — the Evaluator's responsibility ends at publishing the completed, in-memory results
  through a defined interface; durable persistence and destination notification remain a
  separate, future milestone, consistent with M4.1's precedent.
- Q: `EvaluationConfig` carries `métricas`/`thresholds` even though M4.1 already resolves these
  per bot via `EvaluationStrategy` + `ConfigManager`. Do caller-supplied values in a run's
  configuration override the bot's existing defaults for that one run, or must they always mirror
  the bot's existing configuration? → A: Override for that run only — the bot's stored defaults
  are unaffected; callers can run one-off variations (e.g., a higher threshold) without editing
  `bots.yaml`. Every metric named in the override MUST be validated against the system's known
  metrics before the run starts, rejecting the run outright if an unrecognized metric is named.

### Session 2026-07-16

- Q: Which failures terminate the whole run rather than produce a partially successful run? → A:
  Setup or infrastructure failures before trace processing begins make the run unable to run;
  failures in individual traces after processing begins are isolated and produce completed with
  failures.
- Q: How can a requester observe a run while evaluation is still executing? → A: Starting a run
  returns its EvaluationRun handle immediately; processing continues asynchronously and updates
  that handle through completion.
- Q: What timezone and boundary semantics govern a run's trace period? → A: Normalize boundaries
  to UTC and use a half-open interval that includes the start and excludes the end: [start, end).
- Q: What is the valid scoring range for each metric threshold? → A: Every threshold must be
  within [0.0, 1.0], inclusive.
- Q: How must configured metrics correspond to configured thresholds? → A: Each metric is
  submitted as one metric-threshold entry, whose name and threshold are both required before an
  `EvaluationConfig` can be constructed. Metric names must be unique; malformed entries and
  duplicate metric names make the entire run configuration invalid.
- Q: What final state applies if result publication fails after trace evaluation completes? → A: Use a
  distinct delivery-failed final state and retain the completed in-memory results for retry or
  inspection.
- Q: How is run progress represented while traces are still being discovered? → A: Expose processed
  and total trace counts; total and derived progress are indeterminate until extraction finishes.
- Q: What happens when bot_id does not identify a configured bot? → A: Reject the configuration
  before creating run state, using the same validation treatment as an unknown metric.
- Q: Is a period with equal start and end boundaries valid? → A: No; the end must be strictly later
  than the start.
- Q: Does this milestone include retrying a failed result publication? → A: Yes; provide an explicit
  retry operation that reuses retained results without reevaluation.
- Q: How long must completed in-memory results remain available after delivery fails? → A: While
  the EvaluationRun handle remains reachable.
- Q: Must an accepted evaluation run support requester-initiated cancellation? → A: No;
  cancellation is out of scope.
- Q: What identity rule must each accepted EvaluationRun use? → A: A globally unique opaque
  identifier, such as a UUID.
- Q: What final status must a delivery-failed run enter after a successful publication retry? → A:
  Completed or completed with failures, based on the evaluation outcome.
- Q: What minimum information must each per-trace error contain? → A: Trace identifier, failed
  pipeline stage, stable error code, and human-readable message.
- Q: What must happen if the retry operation is invoked on a run that is not in the delivery-failed
  status? → A: Reject as invalid — retry is only a valid operation when the run's current status is
  delivery failed; invoking it on any other status (e.g., in progress, completed, unable to run) is
  rejected without changing the run's state.
- Q: What must happen if a retry is requested for a run while a previous retry attempt for that same
  run is still in flight? → A: Serialize — a second concurrent retry request for the same run is
  rejected while the first retry attempt has not yet completed.

### Session 2026-07-17

- Q: M2.1's public `TraceCollector.collect()` contract returns at most the most recent 500 traces,
  while FR-004 requires an evaluation run to process every trace in its period. Which contract
  governs M4.2? → A: Preserve M2.1's capped `collect()` behavior for existing callers and add an
  explicit exhaustive collection operation for evaluation runs. The exhaustive path MUST paginate
  the repository until every matching trace has been retrieved and MUST NOT silently truncate at
  500.
- Q: What status does the requester-supplied observer see while the initial result publication is
  executing? → A: `DELIVERING`, a distinct non-final lifecycle status entered after trace
  evaluation finishes and before invoking the observer. The run's wait operation remains
  unsignaled while delivery is in flight. Publication success transitions to completed or
  completed with failures; publication failure transitions to delivery failed. Delivery retries
  keep the already-final delivery-failed status while their serialized attempt is in flight.
- Q: Can a requester-supplied observer mutate the retained results it receives and thereby change
  later inspection or retry delivery? → A: No. The run retains its own deep canonical copy, and
  every public read or publication attempt receives a new detached, read-only mapping snapshot.
  Mutating a nested result object from one snapshot MUST NOT affect retained state or any later
  snapshot/retry payload.
- Q: How are coherent run-state reads guaranteed while the background worker is updating progress
  and status? → A: All mutable run state is guarded by a per-run reentrant lock. Individual public
  properties are synchronized, and the handle exposes one immutable state snapshot operation for
  callers that need status, counts, progress, timestamps, errors, and results from the same instant.
- Q: Which runtime values are valid metric thresholds? → A: Integers and floats are accepted except
  booleans; the numeric value must be finite and within `[0.0, 1.0]`, inclusive. `NaN`, positive or
  negative infinity, booleans, strings (including numeric strings), and other non-numeric objects
  are invalid and MUST NOT be coerced. Valid integers may be converted to float only after the
  complete configuration has passed validation.
- Q: What happens if exhaustive collection returns the same non-empty trace identifier more than
  once? → A: A trace identifier represents one logical trace and may have exactly one collection
  outcome. The collector MUST NOT choose or overwrite a duplicate silently. It removes all
  successful records for that duplicated identifier and emits one extraction-stage error for that
  identifier; other unique traces continue normally. Thus every logical trace ID contributes
  exactly one result or one error, never both.
- Q: How are naive period boundaries interpreted, and what happens for non-datetime boundaries? → A:
  A naive `datetime` is interpreted as already UTC; an aware `datetime` is converted to UTC.
  Non-`datetime` boundaries are invalid and reject `EvaluationConfig` construction.
- Q: Are empty bot identifiers, metric names, or trace identifiers valid? → A: No. Bot identifiers
  and metric names must contain at least one non-whitespace character. A collected outcome with an
  empty or whitespace-only trace identifier is an invalid collection outcome and makes exhaustive
  collection fail rather than inventing an identity that cannot be correlated by the requester.
- Q: What does `end_timestamp` mean after a successful retry? → A: It records when the run first
  reached any final status and never changes. A successful retry changes status but does not rewrite
  that first-terminal timestamp or reset the wait signal.
- Q: What exact payload does delivery use? → A: `EvaluationRun.delivery_payload()` returns exactly
  `(results_snapshot, observer)`, and the Evaluator calls
  `ResultPublisher.publish(run, results_snapshot, observer)`.
- Q: How is a run retrieved after `Evaluator.start()` returns? → A: This milestone tracks a run
  exclusively through the returned in-memory `EvaluationRun` handle. It does not provide a run
  registry or `get_run(id)` operation; durable lookup is deferred with persistence.
- Q: Does a zero-trace run still publish? → A: Yes. It publishes one empty, detached read-only
  results mapping through the supplied observer and reaches a completion status only after that
  publication succeeds; publication failure still yields delivery failed.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Trigger a full evaluation run for a bot (Priority: P1)

A member of the technical team wants to evaluate how a specific bot performed over a given time
period. They provide the bot's identifier, the metrics and thresholds to apply, and the date
range to cover. The system extracts every trace generated by that bot in that period, prepares
each one for scoring, runs the configured metrics against each, and delivers a complete set of
results for the period — without the requester having to trigger or babysit each step by hand.

**Why this priority**: This is the core capability of the milestone. Without an end-to-end run
that goes from raw traces to delivered results, none of the rest of the evaluation platform
(dashboards, prompt optimization, reporting) has anything to work from.

**Independent Test**: Can be fully tested by submitting a run configuration for a bot with known
traces in a known period and confirming that results are produced covering all of those traces,
using only this capability (no dashboard or scheduler required).

**Acceptance Scenarios**:

1. **Given** a bot with traces recorded in Langfuse during the requested period and no
   trace-processing failures, **When** a run is started with that bot's identifier, the desired
   metrics, thresholds, and period, **Then** the system processes every trace in that period and
   produces one result for each trace.
2. **Given** a bot with zero traces recorded in the requested period, **When** a run is started
   for that bot and period, **Then** the run completes successfully with zero traces evaluated,
   publishes one empty results mapping to the supplied observer, and this is not reported as an
   error.
3. **Given** two different bots, **When** a run is started for each independently, **Then** each
   run receives a different globally unique opaque identifier, and each run's progress, results,
   and outcome are tracked separately and do not affect one another.

---

### User Story 2 - Observe the status of an in-progress run (Priority: P2)

While a run is executing — which may take a while for a bot with many traces in the period — a
technical team member wants to check whether it is still running, how far along it is, and
whether anything has already gone wrong, without waiting for the entire run to finish.

**Why this priority**: Evaluation runs process a variable, potentially large number of traces.
Without visibility into run state, the only way to know something is happening (or stuck) is to
wait for a final result, which is unacceptable for anything but the smallest runs.

**Independent Test**: Can be fully tested by starting a run and, before it finishes, querying its
current state to confirm it reflects a status (e.g., in progress) and a progress indicator that
increases as traces are processed.

**Acceptance Scenarios**:

1. **Given** a run has just started, **When** its state is checked immediately, **Then** it
   reports a status indicating it has started, a processed count of zero, and an indeterminate
   total count if extraction has not completed.
2. **Given** a run is partway through processing its traces, **When** its state is checked,
   **Then** its processed count reflects the traces already processed and its total count reflects
   the traces discovered for the run.
3. **Given** a run has finished, **When** its state is checked, **Then** it reports a final status
   and both a start and an end timestamp.
4. **Given** a valid run configuration, **When** the run is started, **Then** its EvaluationRun
   handle is returned immediately while processing continues asynchronously and updates that
    handle.
5. **Given** an active run, **When** its requester waits with a timeout, **Then** the wait reports
   whether the run reached its first final status before that timeout, without requiring arbitrary
   polling delays.

---

### User Story 3 - A run survives failures in individual traces (Priority: P3)

Some traces in a period may be malformed, incomplete, or cause a metric evaluation to fail. A
technical team member wants the overall run to still deliver results for every trace that could
be processed, with the failures clearly recorded, rather than losing an entire period's results
because of one bad trace.

**Why this priority**: This determines whether the evaluation platform is trustworthy at scale.
It is lower priority than the two above because it is a resilience property layered on top of the
core pipeline (P1) and the visibility into it (P2), not a capability on its own.

**Independent Test**: Can be fully tested by starting a run over a period known to contain at
least one trace that will fail to process, and confirming that the run still completes, with
results present for the unaffected traces and the failure recorded against the affected one.

**Acceptance Scenarios**:

1. **Given** a period containing one trace that fails during processing and several that do not,
   **When** the run completes, **Then** results are present for every trace that did not fail,
   and the failure records the affected trace's identifier, failed pipeline stage, stable error
   code, and human-readable message.
2. **Given** a run that recorded one or more trace-level failures, **When** its final state is
   checked, **Then** its status distinguishes "completed with some failures" from a fully clean
   run, so the failures cannot be mistaken for full success.

---

### Edge Cases

- What happens when the requested period has no traces for the bot? The run MUST complete
  successfully with zero traces evaluated (see User Story 1, Scenario 2) — this is not an error.
- What happens when the same bot is evaluated by two runs whose periods overlap? Each run MUST be
  tracked and produce results independently; overlapping periods are not prevented or merged.
- What happens to traces exactly on a period boundary? Period boundaries MUST be normalized to UTC;
  a trace at the start is included and a trace at the end is excluded, so adjacent periods do not
  evaluate the same boundary trace twice.
- What happens when the run configuration itself is invalid (e.g., an out-of-range threshold, or a
  period whose end is not later than its start)? The run MUST be rejected before any trace processing
  begins, and no partial run state should be created. A threshold is invalid when it is boolean,
  not an `int`/`float`, non-finite, less than 0.0, or greater than 1.0; numeric strings are not
  coerced. A malformed metric-threshold entry lacking either its metric name or threshold, and
  duplicate metric names, are also invalid. A bot identifier that does not identify
  a configured bot is invalid and receives the same treatment; it MUST NOT be interpreted as a
  valid zero-trace run. Bot identifiers and metric names that are empty or contain only whitespace
  are invalid. Period boundaries that are not `datetime` values are invalid; naive datetimes are
  interpreted as UTC and aware datetimes are converted to UTC.
- What happens when trace extraction cannot proceed at all (e.g., the trace source is entirely
  unreachable, as opposed to a single trace being malformed)? This MUST be distinguishable, in the
  run's final state, from a run that completed with isolated per-trace failures. A setup or
  infrastructure failure before trace processing begins makes the run unable to run. A trace
  discovery or retrieval failure that identifies an affected trace after processing begins MUST be
  recorded as an extraction-stage per-trace error and MUST NOT stop the remaining traces; the run
  then completes with failures.
- What happens when publication through the `ResultPublisher` interface fails after evaluation? The run
  MUST enter a distinct delivery-failed final state and retain its completed in-memory results for
  retry or inspection for as long as its EvaluationRun handle remains reachable; it MUST NOT be
  reported as unable to run or fully completed. An explicit retry MUST repeat only publication
  using those retained results, without extracting traces or evaluating metrics again. A successful
  retry MUST transition the run to completed or completed with failures according to its original
  trace-evaluation outcome; another failed attempt leaves it delivery failed. Invoking retry on a
  run whose status is anything other than delivery failed (e.g., in progress, completed, unable to
  run) MUST be rejected outright, leaving that run's state unchanged. A retry request for a run that
  already has a retry attempt in flight MUST also be rejected until that in-flight attempt
  completes, so at most one retry attempt runs at a time per run.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST allow a run to be started by supplying the target bot's identifier,
  an ordered non-empty collection of metric-threshold entries, the period (start and end) of traces
  to cover, and exactly one `ResultObserver`. This milestone defines no other required or optional
  `Evaluator.start()` inputs.
- **FR-002**: The system MUST validate a run's configuration — including that every threshold is
  an `int` or `float` but not a `bool`, is finite, is within [0.0, 1.0], inclusive, and that the
  period's end is strictly later than its start — before any trace processing begins, and MUST
  reject the run outright if validation fails. Period boundaries MUST
   be normalized to UTC before comparison. Validation MUST confirm that the bot identifier identifies
   a configured bot; a bot whose exact `bots.{bot_id}.bot_type` configuration key is missing or
   empty MUST be rejected before run state is created. Configuration-loading or parsing failures
   unrelated to that key MUST NOT be reclassified as an unknown bot.
  Threshold strings and other values MUST NOT be numerically coerced during validation; `NaN` and
  either infinity are outside the valid range. `period_start` and `period_end` MUST be `datetime`
  values; naive values MUST be interpreted as UTC and aware values MUST be converted to UTC.
  `bot_id` MUST contain at least one non-whitespace character.
- **FR-003**: The system MUST create a trackable run record the moment a valid run configuration
  is accepted, assign it a globally unique opaque identifier, return its EvaluationRun handle
  immediately, and update that handle while processing continues asynchronously through a final
  status. The handle MUST provide a wait operation that reports whether the run reached its first
  final status before an optional timeout. It MUST also provide an immutable, coherent state
  snapshot captured under the run's synchronization boundary. For this in-memory milestone, the
  returned handle MUST be the only retrieval mechanism: no process-wide registry or `get_run(id)`
  API is included, and losing the handle makes the run unavailable to the requester.
- **FR-004**: For an accepted run, the system MUST extract every trace produced by the target bot
  within the configured UTC half-open period, including traces at the start and excluding traces
  at the end. The Evaluator MUST use the collector's exhaustive operation, not M2.1's capped
  `collect()` operation; result sets larger than 500 MUST be retrieved across all repository pages
  without changing the capped operation's existing public behavior. Exhaustive pagination MUST use
  one implementation-owned fixed page-size constant and the same deterministic ascending ordering
  by trace timestamp and then non-empty trace identifier on every page of the complete request.
  The page size is a protocol batching detail, not an environment setting; changing it MUST NOT
  change which traces are returned. Malformed metadata,
  repeated pages or data, changing total-page metadata, or an empty page before the declared final
  page MUST fail collection rather than loop or return a partial result.
- **FR-005**: The system MUST prepare (normalize) each extracted trace into the standard form
  required for scoring before that trace is evaluated.
- **FR-006**: The system MUST attempt to evaluate each prepared trace against the run's configured
  metrics and thresholds. Each successfully evaluated trace MUST produce one result; failures MUST
  follow the isolation and error-recording behavior defined by FR-010. Result keys MUST be unique
  trace identifiers; inserting a later result MUST never overwrite an earlier trace result.
  Per-metric failure handling within one trace MUST remain the responsibility of the existing
  `EvaluationOrchestrator` contract; the Evaluator treats an orchestrator call as successful when
  that contract returns an `EvaluationResult`, including any metric-level error details it
  supports, and records a trace-level evaluation failure only when the orchestrator call raises.
- **FR-007**: The system MUST require the requester to supply exactly one non-null
  `ResultObserver` ABC instance when
  starting a run and MUST publish completed results only to that observer through the defined
  `ResultPublisher` interface once trace evaluation finishes. The observer is retained with the run
  solely for retrying a failed publication. Persisting those results durably and notifying other
  destinations (e.g., dashboards, exports) are handled by
  separately-specified capabilities and are out of scope for this milestone; the Evaluator's
  responsibility ends at publishing the completed, in-memory results. If that publication fails,
  the run MUST enter a distinct delivery-failed
   final state and retain its completed in-memory results for retry or inspection for as long as its
   EvaluationRun handle remains reachable. The EvaluationRun handle MUST expose those retained
   results through a public read-only interface; requesters MUST NOT need to access private state
   to inspect them. Retained results MUST be a deep copy owned by the run. Every public inspection
   and observer call MUST receive a fresh detached, read-only mapping snapshot so observer code
   cannot mutate the canonical retained results, including through nested `EvaluationResult` or
   `MetricResult` objects. The system MUST provide an explicit retry operation that
  repeats only the failed publication using the retained results and MUST NOT re-extract traces,
  normalize traces, or rerun metrics. If the retry succeeds, the run MUST transition to fully
  completed or completed with failures according to its original trace-evaluation outcome; if the
  retry fails, it MUST remain delivery failed. The system MUST reject a retry request outright,
  without altering run state, when invoked against a run whose current status is not delivery
  failed. The system MUST also reject a retry request made while a previous retry attempt for that
  same run is still in flight, ensuring at most one retry attempt executes per run at a time.
  After trace processing and result retention finish, the run MUST transition to the non-final
  `DELIVERING` status before the initial call to the observer. The observer MUST see `DELIVERING`
  during that call, and the run's wait operation MUST remain unsignaled until the call either
  succeeds or raises. A delivery retry is different: it MUST retain `DELIVERY_FAILED` while its
  attempt is in flight so concurrent retry requests are rejected as retry-in-progress.
  `EvaluationRun.delivery_payload()` MUST return exactly a fresh detached results snapshot and the
  retained observer, in that order; publication MUST invoke
  `ResultPublisher.publish(run, results_snapshot, observer)`. The run MUST release its private
  observer reference after successful publication, including a successful retry, because no later
  retry is valid; it MUST retain the observer after failed publication while retry remains valid.
  Successful publication MUST apply the completion status and clear the observer in one
  synchronized run-owned operation, so no public state can expose a completed run that still
  retains a now-invalid retry observer. A zero-trace run MUST still perform exactly one initial
  publication with an empty results snapshot.
- **FR-008**: The system MUST update the run's progress indicator as traces move through the
  pipeline by exposing processed and total trace counts. The total count and any progress derived
  from it MUST remain indeterminate until extraction completes; afterward, derived progress MUST
  equal processed count divided by total count, with a zero-trace run treated as complete rather
  than requiring division by zero. Status, counts, derived progress, timestamps, errors, and
  retained results returned together by the snapshot operation MUST represent one atomic read;
  requesters MUST NOT observe partially-applied state transitions.
  `total` MUST be set exactly once to a non-negative integer after extraction succeeds;
  `processed` MUST start at zero, MUST increment exactly once per identified trace outcome only
  after `total` is known, and MUST never exceed `total`. Invalid state mutations MUST be rejected
  without partially changing run state.
- **FR-009**: The system MUST record a start timestamp when a run begins and an end timestamp when
  it first reaches a final status. That first-terminal timestamp MUST be set exactly once and MUST
  NOT change when a later successful delivery retry changes `DELIVERY_FAILED` to a completion
  status.
- **FR-010**: A failure while processing one trace (during extraction, normalization, or
  evaluation) that identifies the affected trace MUST be recorded against that specific trace and
  MUST NOT prevent the run from continuing to process the remaining traces in the period. A failure
  before trace processing begins that cannot identify an affected trace is unable to run under
  FR-011. Each per-trace error MUST contain the affected trace's identifier, the pipeline stage
  that failed, a stable error code of `extraction_failed`, `normalization_failed`, or
  `evaluation_failed`, and a human-readable message. Public error messages MUST use the existing
  `sanitize_error()` redaction policy, MUST NOT expose raw exception text, bearer tokens, API keys,
  passwords, or opaque credential values, and MUST retain a stable stage-specific human-readable
  fallback after redaction.
  Collection MUST enforce exactly one outcome per non-empty trace identifier across successful
  traces and extraction errors. If an identifier appears more than once in collected outcomes, all
  successful records for that identifier MUST be excluded and replaced by one extraction-stage
  error for that identifier; processing of other identifiers MUST continue. Any successful or
  failed collection outcome whose trace identifier is empty or whitespace-only MUST invalidate the
  exhaustive collection result and fail the run as unable to run; the collector MUST NOT invent a
  replacement identifier.
- **FR-011**: The system MUST report a run's final status in a way that distinguishes four
  outcomes: fully completed with no failures, completed with one or more recorded per-trace
  failures, unable to run at all, and delivery failed after evaluation. The unable-to-run outcome
  MUST be used for setup or infrastructure failures that prevent trace processing from beginning;
  once trace processing begins, individual trace failures MUST be isolated and yield completed
  with failures. A result-publication failure MUST yield delivery failed instead and preserve the
  completed in-memory results. Successful publication retry MUST restore the completed or completed
  with failures outcome that corresponds to the run's trace-evaluation results. An unexpected
  worker-level failure that cannot be attributed to an identified trace MUST also reach unable to
  run, record a sanitized run-level failure message, set the end timestamp, and signal the run's
  wait operation; it MUST NOT leave the run in a non-final status.
  A run-level failure message MUST follow the same `sanitize_error()` redaction guarantees as a
  per-trace message: it MUST NOT contain raw exception text, bearer tokens, API keys, passwords, or
  opaque credential values, and MUST retain a stable human-readable fallback after redaction.
  Failure to create or start the background worker after run state is accepted MUST also transition
  that run to unable to run with these guarantees rather than leave it in `STARTED`; because the
  configuration was already accepted, `start()` MUST return that terminal handle rather than raise
  the worker-start exception.
  `STARTED`, `IN_PROGRESS`, and `DELIVERING` are non-final lifecycle statuses and do not add a fifth
  final outcome. A worker MUST NOT terminate while the run remains in any of these statuses.
  Valid forward transitions are `STARTED` to `IN_PROGRESS` or `UNABLE_TO_RUN`, `IN_PROGRESS` to
  `DELIVERING` or `UNABLE_TO_RUN`, `DELIVERING` to `COMPLETED`,
  `COMPLETED_WITH_FAILURES`, or `DELIVERY_FAILED`, and `DELIVERY_FAILED` to `COMPLETED` or
  `COMPLETED_WITH_FAILURES` after successful retry. Reapplying the current status MAY be an
  idempotent no-op; every other transition MUST be rejected without changing state.
- **FR-012**: The system MUST support running evaluations for multiple bots, or multiple periods
  of the same bot, concurrently, with each run's status, progress, and results tracked
  independently of any other run.
- **FR-013**: The metrics and thresholds supplied in a run's configuration MUST override the
  bot's existing default metrics/thresholds for that one run only; the bot's stored defaults MUST
  remain unchanged after the run. A run's configuration MUST NOT be silently coerced to match the
  bot's defaults.
- **FR-014**: Every metric named in a run's configuration MUST be validated against the set of
  metrics the system knows how to evaluate before the run starts; a run naming an unrecognized
  metric MUST be rejected outright, with no partial run state created (same treatment as FR-002).
  A metric name MUST contain at least one non-whitespace character.
- **FR-015**: A run's configuration MUST preserve each supplied metric-threshold entry until it
  has been validated. Each entry MUST contain exactly one metric name and one threshold; malformed
  entries lacking either field MUST be rejected during configuration construction, before
  `Evaluator.start()` can create run state. Metric names MUST be unique, and a duplicate name MUST
  cause the entire run configuration to be rejected before run state is created. The collection
  MUST contain only `MetricThreshold` instances; arbitrary look-alike objects, mappings, tuples, or
  entries with an incompatible structure MUST be rejected rather than accepted by duck typing.

### Key Entities

- **EvaluationConfig**: The configuration submitted to start one run. Identifies the target bot,
  an ordered collection of metric-threshold entries to evaluate, and the period (start/end) of
  traces the run must cover. Entries are preserved until validation so duplicate metric names can
  be rejected; the Evaluator may construct an internal metric-to-threshold mapping only after a
  configuration is valid. Its metrics and thresholds override the bot's existing configured defaults
  for that one run only, without altering the bot's stored defaults. Rejected as a whole if any
  part of it is invalid, including a malformed metric-threshold entry, an unknown bot identifier,
  or an unrecognized or duplicate metric name. Period boundaries are normalized to UTC and
  interpreted as a half-open interval that includes start and excludes end.
- **EvaluationRun**: The trackable record of one run's execution. It is identified by a globally
  unique opaque identifier (such as a UUID) and holds the run's
  current status (started, in progress, delivering, completed, completed with failures, unable to
  run, or delivery failed), processed and total trace counts, a start timestamp, an end timestamp once
  finished, and the set of per-trace errors recorded during the run, if any. Its total count and
  derived progress are indeterminate until extraction completes. Setup or infrastructure failures
  before trace processing starts transition it to unable to run; isolated failures after processing
  starts transition it to completed with failures; result-publication failures transition it to
   delivery failed while retaining completed in-memory results for as long as the EvaluationRun
   handle remains reachable. It exposes retained completed results through a public read-only
   interface for inspection, while retaining its mutable backing state privately. It privately
   retains the requester-supplied `ResultObserver` only for
  delivery and delivery retry; it does not expose the observer through the public run state. An
  unexpected worker-level failure records a sanitized run-level failure message and transitions it
  to unable to run. All mutable backing state is protected by a per-run reentrant lock. Its public
  properties are synchronized, and `snapshot()` returns an immutable `EvaluationRunSnapshot` for
  coherent multi-field inspection.
- **EvaluationRunSnapshot**: An immutable point-in-time view of one run containing identity,
  status, processed/total/progress, timestamps, errors, failure message, and detached retained
  results, all captured while holding the run's state lock.
- **PerTraceError**: A failure isolated to one trace during extraction, normalization, or metric
  evaluation. Identifies the affected trace and failed pipeline stage and provides one stable
  error code per stage (`extraction_failed`, `normalization_failed`, or `evaluation_failed`) and a
  human-readable message.
- **Evaluator**: The orchestrator that carries an accepted EvaluationConfig through the full
  pipeline for one run — extracting the bot's traces for the configured period, preparing
  (normalizing) each one, evaluating each against the configured metrics and thresholds, and
  publishing the resulting EvaluationRun and its results through the `ResultPublisher` interface
  to the one `ResultObserver` supplied by that run's requester. It returns
  the EvaluationRun handle immediately and updates it as processing continues asynchronously. It
  marks the run `DELIVERING` before the initial observer call and reaches a final status only after
  that call succeeds or raises. It
  also exposes an explicit retry for a failed publication that reuses retained results without repeating
  extraction, normalization, or evaluation, and rejects that retry outright — without changing run
  state — when called against a run that is not currently delivery failed, or when a prior retry for
  that same run is still in flight. Durable persistence of results and notification of downstream
  destinations are out of scope for this milestone.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A technical team member can start an evaluation for a bot whose required configuration
  is present over a valid explicit date range and, without further manual steps, use the returned
  handle's wait/snapshot API to observe exactly one of the four final outcomes defined by FR-011.
- **SC-002**: 100% of traces that do not themselves fail to process are still reflected in a run's
  results, even when other traces in the same run fail.
- **SC-003**: At any point while a run is active, checking its state returns a progress indicator
  that is indeterminate during extraction and, once extraction completes, equals the processed
  trace count divided by the total trace count.
- **SC-004**: A run over a period with no traces for the bot completes successfully in the same
  way a run with traces does, requiring no special handling by the requester.
- **SC-005**: When a run finishes with one or more trace-level failures, a team member can tell,
  from the run's final state alone, that it is not a fully clean success — without inspecting logs.
- **SC-006**: When result publication fails after evaluation, the run's final state identifies the
   delivery failure and its completed in-memory results remain available through the run handle for
   retry or read-only inspection.
- **SC-007**: Retrying a failed publication makes exactly one new delivery attempt using the retained
  results and performs no new trace extraction, normalization, or metric evaluation. A successful
  retry leaves the run completed or completed with failures according to its trace-evaluation
  outcome; an unsuccessful retry leaves it delivery failed.

## Assumptions

- Triggering a run (manual request, scheduled/cron trigger, or API call) is outside this
  milestone's scope. The Evaluator exposes a capability that can be invoked by any such trigger,
  but the trigger mechanism itself (e.g., the scheduler) is specified separately.
- The internal mechanics of trace extraction (per bot platform) and trace normalization are
  governed by the already-specified trace collection and normalization capabilities. This
  milestone covers how the Evaluator sequences and consumes them for a run, not how they work
  internally.
- The internal mechanics of metric evaluation (per-metric concurrency, timeout, and failure
  isolation for a single trace) are governed by the already-specified metric evaluation
  capability. This milestone covers how the Evaluator supplies configuration to it and consumes
  its per-trace results, not how it scores a trace internally.
- The order and concurrency with which traces within a single run are processed (e.g., one at a
  time vs. many in parallel) is an implementation decision for the technical plan, not specified
  here.
- A run's period always covers an explicit, caller-supplied start and end; this milestone does not
  define incremental/delta evaluation (e.g., "only traces since the last run").
- Requester-initiated cancellation of an accepted run is out of scope for this milestone. An
  accepted run proceeds to one of the final outcomes defined by FR-011.
- Durable persistence of run results (e.g., an `EvaluationRepository`) and notification of
  downstream destinations (e.g., a `ResultObserver` for Langfuse, CSV, Qdrant, or the
  dashboard) are separately-specified capabilities and are out of scope for this milestone — see
  Clarifications.
