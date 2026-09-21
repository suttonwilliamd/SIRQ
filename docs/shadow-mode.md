# SIRQ Shadow Mode: one bad night

SIRQ is now pointed at the first product question:

> How many times did the existing alert path wake a human, and how many of those interruptions were necessary?

## Run the demo

```bash
python -m sirq.cli oncall-demo --output sirq-one-bad-night.html
```

Open the generated HTML file. It shows:

- alerts observed
- existing human interruptions
- SIRQ-recommended interruptions
- estimated interruption reduction
- reviewed correctness
- production actions taken
- a concrete alert-by-alert timeline

The included fixture contains nine alerts from one simulated night:

- expected GitHub Actions runner CPU
- a self-resolving Redis latency spike
- three correlated checkout failures
- a healthy worker restart
- a certificate expiring in 18 hours

The current mock evaluator recommends two interruptions: the checkout incident and the certificate expiry. Repeated checkout symptoms are correlated so they do not become three separate interruptions.

## Why this is safe

Shadow Mode never changes the existing alert path. Existing PagerDuty, Slack, Discord, or email behavior is treated as the source of truth and stored as `ExistingOutcome`. SIRQ writes a recommendation beside it:

```text
IncomingAlert
    ├── ExistingOutcome       what production actually did
    ├── SIRQAssessment         what the semantic layer inferred
    ├── Recommendation         INTERRUPT / NOTIFY / RECORD_ONLY
    └── Review                 correct / incorrect / unsure
```

The mock evaluator remains the default so this can be developed without paid Jev calls. A future evaluator can implement the existing `SemanticEvaluator` protocol and be compared against the same replay fixture.
