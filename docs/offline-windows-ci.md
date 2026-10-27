# Bounded offline Windows report qualification

This is CI preparation, not evidence that hosted Windows has passed. The accepted
runtime, evaluator, renderers, metrics, fixtures, styles and existing 27 tests
are unchanged. The original Ubuntu Python 3.11/3.12/3.13 regression, demo and
showcase commands remain. Windows adds Python 3.11 and 3.13 only, with a five-minute
job timeout, read-only contents permission, no persisted checkout credentials,
no package installation and no new trigger. A failed command fails its step/job;
there is no continue-on-error. Existing push/pull_request triggers are unchanged.

## Reproduce

From the checkout root on Python >=3.11, enable UTF-8 mode (PowerShell):

```powershell
$env:PYTHONUTF8 = "1"
python -m unittest discover -s tests -v
python scripts/qualify_offline_reports.py
```

On POSIX shells use `PYTHONUTF8=1 python ...` for each command. Explicit UTF-8
mode also covers the existing tests that use default-codec `read_text()` and
Windows subprocess console pipes; this does not claim legacy-codepage support.
No project dependencies are required. The helper uses only the standard library
and launches only `showcase --output ...` and `oncall-demo --output ...`, with
30-second per-process timeouts. It uses tracked deterministic mock/synthetic
fixtures, not generic reports, providers, endpoints, servers or production data.

Each run creates its own temporary directory with a nested spaces/Unicode path
(`reports with spaces café 雪`). It checks strict UTF-8 output, HTML document
markers/charset, article counts, absence of active/external report elements,
mock/synthetic/no-production-action disclosures, CLI JSON counts and fixture
outcomes, then verifies temporary directory cleanup. It prints a small JSON
summary without temporary paths or environment values. Exceptions fail closed;
the temporary-directory context also cleans up on validation failures. HTMLParser
checks are bounded source checks, not full HTML conformance or browser testing.

Expected results:

- Showcase: 4 articles/decisions, one each ROUTINE, TRANSIENT_FAILURE,
  SECURITY_ANOMALY and HUMAN_ATTENTION_REQUIRED.
- On-call: 9 articles/records; RECORD_ONLY=6, NOTIFY=1, INTERRUPT=2;
  reviewed=9, correct=8, incorrect=1, production actions=0.
- Fixture-only recommendation difference 77.8%; fixture-label agreement 88.9%.
  These are fixture arithmetic, not measured production efficacy/accuracy.

## Hosted acceptance and provenance

The authorized root must push the independently reviewed exact head and inspect
both Windows jobs and all three retained Ubuntu jobs. Require all 27 regressions
to pass in each job, both Windows qualification steps to succeed with expected
JSON counts, no skipped/allowed-failure qualification, and the intended checked-out
SHA. Record Actions run URL, event, `github.sha`, checkout/tested SHA, Python and
runner versions with the acceptance evidence. Pull requests normally test a
synthetic PR merge ref: that SHA is not necessarily the branch head. Do not label
merge-ref evidence as direct head testing, or reuse stale results after edits.

No hosted artifact upload is added: generated HTML is temporary synthetic output
and is deleted, avoiding arbitrary workspace dumps. Logs contain the bounded
result JSON, not HTML or environment/path dumps from this helper. If a later
artifact is authorized, restrict it to known synthetic HTML and allowlisted
machine-readable tested-SHA/results provenance; require successful validation,
short retention and inspection of its exact file list before acceptance.

Local Linux checks prove only the exercised Linux interpreter/source behavior;
they do not prove native Windows path/encoding/cleanup behavior or hosted Actions
success. Neither generated HTML nor native CLI checks establish visual release,
Windows browser, screen-reader or physical-device acceptance. Existing independent
engineering, visual, publication, private-source and root-ownership gates remain.
No dispatch, push, PR, merge, release or self-approval is performed here.
