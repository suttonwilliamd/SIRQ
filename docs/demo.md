# SIRQ demo talk track

This is the five-minute developer demo for SIRQ.

## Run it

```bash
python -m sirq.cli showcase --output sirq-showcase.html
```

Open `sirq-showcase.html` in a browser. The report intentionally puts four events next to one another:

1. **Routine high CPU** — CPU is high, but it is explained by a scheduled transcode. SIRQ keeps it routine.
2. **Transient API failure** — failures and latency are far above baseline, but the request is retryable. SIRQ records a transient failure without requiring a human.
3. **Successful security anomaly** — the request succeeds, but the surrounding evidence is suspicious. SIRQ raises a security anomaly and selects `NOTIFY`.
4. **Blocked agent** — an agent cannot continue without permission. SIRQ selects `HUMAN_ATTENTION_REQUIRED` and `NOTIFY`.

The point is not that the mock evaluator is intelligent. The point is the boundary:

```text
messy state → semantic assessment → SIRQ event → deterministic policy
```

The evaluator never receives a tool, shell, or restart capability. The policy engine only selects safe named dispositions.

## Where it plugs in

SIRQ is meant to sit beside tools developers already use, not replace them:

```text
Docker healthchecks ─┐
GitHub Actions      ─┤
webhooks / alerts   ─┼─→ SIRQ → record / dashboard / notify
AI workers          ─┘
```

Concrete examples:

- **Docker:** container is technically running, but request failures and latency are rising. SIRQ classifies a transient service degradation instead of paging immediately.
- **GitHub Actions:** a scheduled build consumes a CPU-heavy runner. SIRQ recognizes the expected job context instead of treating high utilization as an incident.
- **Webhooks:** an authentication endpoint returns `200 OK`, but the surrounding evidence suggests a credential anomaly. SIRQ escalates it.
- **Coding agents:** an agent is blocked waiting for a permission boundary. SIRQ interrupts the orchestrator or human instead of forwarding every status update.

The same observation contract handles all four sources; only the adapter changes. Try each concrete payload directly:

```bash
python -m sirq.cli evaluate examples/integrations/docker.json
python -m sirq.cli evaluate examples/integrations/github-actions.json
python -m sirq.cli evaluate examples/integrations/webhook.json
python -m sirq.cli evaluate examples/integrations/coding-agent.json
```

## Live HTTP version

In one terminal:

```bash
python -m sirq.cli serve --port 8099
```

In another:

```bash
curl http://127.0.0.1:8099/health
curl -X POST http://127.0.0.1:8099/events \
  -H 'Content-Type: application/json' \
  --data-binary @examples/degraded-service.json
```

## Replay version

Record a stream and replay it later:

```bash
python -m sirq.cli replay examples/showcase.jsonl --record .sirq/showcase-record.jsonl
python -m sirq.cli report examples/showcase.jsonl --output sirq-replay.html
```

The replay report is the foundation for comparing policies and evaluator versions before enabling any reflexive handler.
