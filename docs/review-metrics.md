# Shadow review and evaluation integration

Track B adds `sirq.review` without changing the evaluator or adapter contracts.

## Flow

1. `ShadowRuntime.process_many(read_alerts(...))` produces `ShadowRecord` values.
2. A reviewer creates `ReviewRecord(event_id, status, reviewer, note)` where status is `correct`, `incorrect`, or `unsure`.
3. `apply_reviews(records, reviews)` attaches labels to the matching alert IDs.
4. `calculate_shadow_metrics(records)` returns the customer-facing `ShadowMetrics` contract.
5. `render_shadow_html` and `sirq shadow-report` consume the same metrics object.

No external API, paid model, or production action is required.

## Metric definitions

- **Alerts observed:** number of shadow records.
- **Existing interruptions:** records whose existing outcome paged a human.
- **SIRQ interruptions:** records recommended as `INTERRUPT`.
- **Potential reduction:** `(existing - SIRQ) / existing`, or `0` when no existing interruptions exist.
- **Reviewed accuracy:** `correct / reviewed`; `unsure` remains visible and is not counted as correct.
- **False interruptions:** reviewed `incorrect` records where SIRQ recommended `INTERRUPT`.
- **Missed critical events:** critical/emergency/fatal records whose correlation group never receives an SIRQ interrupt, excluding already-duplicate symptoms.
- **Duplicate symptoms avoided:** records marked as duplicate by the existing correlation-aware shadow runtime.
- **Production actions taken:** always `0` in this shadow-only layer; existing human actions are exposed separately as `existing_human_actions`.

The alert timeline keeps the concise `ShadowRecord.reason` beside every event, so a customer can inspect why SIRQ interrupted, notified, or recorded only.

## Coordinator integration dependency

The coordinator only needs to import `calculate_shadow_metrics` (and optionally `ReviewRecord`/`apply_reviews`) from `sirq.review`. Existing `ShadowRuntime`, `read_alerts`, `oncall-demo`, and alert adapter behavior remain compatible.
