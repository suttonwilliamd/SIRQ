from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

from .core import SIRQEvent


@dataclass(slots=True)
class PolicyRule:
    kind: str
    handler: str
    min_priority: int = 0
    min_confidence: float = 0.0
    debounce_observations: int = 1
    enter_threshold: float = 0.0
    exit_threshold: float = 0.0


@dataclass(slots=True)
class PolicyDecision:
    event: SIRQEvent
    handler: str
    allowed: bool
    reason: str


@dataclass(slots=True)
class _State:
    active: bool = False
    consecutive: int = 0


class PolicyEngine:
    """Deterministic routing layer; it never executes arbitrary actions."""

    SAFE_HANDLERS = {"IGNORE", "RECORD", "DASHBOARD", "NOTIFY"}

    def __init__(self, rules: Iterable[PolicyRule], masked_below: int = 0):
        self.rules = list(rules)
        self.masked_below = masked_below
        self._states: dict[tuple[str, str], _State] = {}

    def _rule_for(self, event: SIRQEvent) -> PolicyRule:
        for rule in self.rules:
            if rule.kind in {event.kind, "*"}:
                return rule
        return PolicyRule(kind="*", handler="RECORD")

    def decide(self, event: SIRQEvent) -> PolicyDecision:
        rule = self._rule_for(event)
        if rule.handler not in self.SAFE_HANDLERS:
            return PolicyDecision(event, "IGNORE", False, "handler is outside the MVP safe set")
        if event.priority < max(self.masked_below, rule.min_priority):
            event.masked = True
            return PolicyDecision(event, rule.handler, False, "priority masked")
        if event.confidence < rule.min_confidence:
            return PolicyDecision(event, rule.handler, False, "confidence below policy threshold")

        score = event.confidence
        key = (event.source, event.kind)
        state = self._states.setdefault(key, _State())
        enter = rule.enter_threshold
        exit_ = rule.exit_threshold if rule.exit_threshold else enter
        if state.active:
            if enter and score < exit_:
                state.consecutive += 1
                if state.consecutive >= rule.debounce_observations:
                    state.active = False
                    state.consecutive = 0
                    return PolicyDecision(event, "IGNORE", False, "hysteresis exit")
            else:
                state.consecutive = 0
            return PolicyDecision(event, rule.handler, True, "active policy state")
        if enter and score < enter:
            state.consecutive = 0
            return PolicyDecision(event, "IGNORE", False, "below enter threshold")
        state.consecutive += 1
        if state.consecutive < max(1, rule.debounce_observations):
            return PolicyDecision(event, "IGNORE", False, "debouncing")
        state.active = True
        state.consecutive = 0
        return PolicyDecision(event, rule.handler, True, "policy matched")

    def reset(self) -> None:
        self._states.clear()
