from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .core import Observation, SemanticEvaluator, SIRQEvent, event_from_scores
from .policy import PolicyDecision, PolicyEngine


class JsonlRecorder:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, observation: Observation, event: SIRQEvent, decision: PolicyDecision) -> None:
        record = {"observation": observation.__dict__ if hasattr(observation, "__dict__") else {
            "source": observation.source, "type": observation.type, "observations": observation.observations,
            "history": observation.history, "dependencies": observation.dependencies, "context": observation.context,
            "timestamp": observation.timestamp,
        }, "event": event.to_dict(), "decision": {
            "handler": decision.handler, "allowed": decision.allowed, "reason": decision.reason,
        }}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


class SIRQRuntime:
    def __init__(self, evaluator: SemanticEvaluator, policy: PolicyEngine, recorder: JsonlRecorder | None = None):
        self.evaluator = evaluator
        self.policy = policy
        self.recorder = recorder

    def process(self, observation: Observation) -> PolicyDecision:
        event = event_from_scores(observation, self.evaluator.evaluate(observation))
        decision = self.policy.decide(event)
        if self.recorder:
            self.recorder.append(observation, event, decision)
        return decision

    def process_many(self, observations: Iterable[Observation]) -> list[PolicyDecision]:
        return [self.process(item) for item in observations]
