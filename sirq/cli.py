from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .adapters import stdin_adapter
from .core import MockJevEvaluator, Observation
from .policy import PolicyEngine, PolicyRule
from .replay import read_jsonl
from .runtime import JsonlRecorder, SIRQRuntime
from .daemon import serve


def build_runtime(record: str | None = None, masked_below: int = 0) -> SIRQRuntime:
    rules = [
        PolicyRule("SECURITY_ANOMALY", "NOTIFY", min_priority=5, min_confidence=0.8),
        PolicyRule("PERSISTENT_FAILURE", "DASHBOARD", min_priority=2, min_confidence=0.55,
                   debounce_observations=2, enter_threshold=0.55, exit_threshold=0.30),
        PolicyRule("TRANSIENT_FAILURE", "RECORD", min_confidence=0.5),
        PolicyRule("HUMAN_ATTENTION_REQUIRED", "NOTIFY", min_priority=4, min_confidence=0.65),
        PolicyRule("*", "IGNORE"),
    ]
    return SIRQRuntime(MockJevEvaluator(), PolicyEngine(rules, masked_below=masked_below),
                       JsonlRecorder(record) if record else None)


def print_decision(decision) -> None:
    payload = {
        "kind": decision.event.kind, "source": decision.event.source,
        "priority": decision.event.priority, "confidence": round(decision.event.confidence, 3),
        "handler": decision.handler, "allowed": decision.allowed, "reason": decision.reason,
    }
    print(json.dumps(payload, sort_keys=True))


def cmd_evaluate(path: str) -> int:
    runtime = build_runtime()
    with open(path, encoding="utf-8") as handle:
        decision = runtime.process(Observation.from_dict(json.load(handle)))
    print_decision(decision)
    return 0


def cmd_replay(path: str, record: str | None) -> int:
    runtime = build_runtime(record=record)
    decisions = runtime.process_many(read_jsonl(path))
    for decision in decisions:
        print_decision(decision)
    print(f"replayed={len(decisions)}", file=sys.stderr)
    return 0


def cmd_stdin(record: str | None) -> int:
    runtime = build_runtime(record=record)
    for observation in stdin_adapter():
        print_decision(runtime.process(observation))
    return 0


def cmd_serve(host: str, port: int, record: str | None) -> int:
    server = serve(build_runtime(record=record), host=host, port=port)
    print(f"sirq listening on http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def cmd_demo() -> int:
    runtime = build_runtime()
    samples = [
        Observation("jellyfin", "service_health", {"status": "running", "failures_5m": 1, "latency_p95_ms": 190}, {"normal_failures_5m": 2, "normal_latency_p95_ms": 180}),
        Observation("jellyfin", "service_health", {"status": "running", "failures_5m": 18, "latency_p95_ms": 1880, "retryable": True}, {"normal_failures_5m": 2, "normal_latency_p95_ms": 180}),
        Observation("ups", "power", {"status": "running", "security_relevant": True, "message": "credential anomaly"}),
    ]
    for sample in samples:
        print_decision(runtime.process(sample))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sirq")
    sub = parser.add_subparsers(dest="command", required=True)
    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("path")
    replay = sub.add_parser("replay")
    replay.add_argument("path")
    replay.add_argument("--record")
    stdin = sub.add_parser("stdin")
    stdin.add_argument("--record")
    server = sub.add_parser("serve")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8099)
    server.add_argument("--record")
    sub.add_parser("demo")
    args = parser.parse_args(argv)
    if args.command == "evaluate": return cmd_evaluate(args.path)
    if args.command == "replay": return cmd_replay(args.path, args.record)
    if args.command == "stdin": return cmd_stdin(args.record)
    if args.command == "serve": return cmd_serve(args.host, args.port, args.record)
    return cmd_demo()


if __name__ == "__main__":
    raise SystemExit(main())
