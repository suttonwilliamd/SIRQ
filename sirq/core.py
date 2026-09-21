from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class Observation:
    source: str
    type: str
    observations: dict[str, Any] = field(default_factory=dict)
    history: dict[str, Any] = field(default_factory=dict)
    dependencies: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_now)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Observation":
        return cls(
            source=str(value["source"]),
            type=str(value.get("type", "unknown")),
            observations=dict(value.get("observations", {})),
            history=dict(value.get("history", {})),
            dependencies=dict(value.get("dependencies", {})),
            context=dict(value.get("context", {})),
            timestamp=str(value.get("timestamp", utc_now())),
        )


@dataclass(slots=True)
class SemanticScores:
    routine_event: float = 0.5
    abnormality: float = 0.0
    probable_failure: float = 0.0
    security_relevant: float = 0.0
    human_attention_needed: float = 0.0
    likely_transient: float = 0.0
    worsening: float = 0.0
    immediate_action: float = 0.0
    user_impact: float = 0.0
    recoverability: float = 0.5

    def clamp(self) -> "SemanticScores":
        for name in self.__dataclass_fields__:
            setattr(self, name, min(1.0, max(0.0, float(getattr(self, name)))))
        return self


@dataclass(slots=True)
class SIRQEvent:
    kind: str
    source: str
    confidence: float
    priority: int
    urgency: float
    impact: float
    recoverability: float
    human_attention: float
    scores: SemanticScores
    observation: dict[str, Any]
    timestamp: str = field(default_factory=utc_now)
    masked: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SIRQEvent":
        scores = value.get("scores", {})
        return cls(
            kind=str(value["kind"]), source=str(value["source"]),
            confidence=float(value["confidence"]), priority=int(value["priority"]),
            urgency=float(value["urgency"]), impact=float(value["impact"]),
            recoverability=float(value["recoverability"]),
            human_attention=float(value["human_attention"]),
            scores=SemanticScores(**scores), observation=dict(value.get("observation", {})),
            timestamp=str(value.get("timestamp", utc_now())), masked=bool(value.get("masked", False)),
            metadata=dict(value.get("metadata", {})),
        )


class SemanticEvaluator(Protocol):
    def evaluate(self, observation: Observation) -> SemanticScores: ...


def _number(mapping: Mapping[str, Any], *names: str, default: float = 0.0) -> float:
    for name in names:
        if name in mapping:
            try:
                return float(mapping[name])
            except (TypeError, ValueError):
                return default
    return default


class MockJevEvaluator:
    """Deterministic Jev stand-in based on explicit observations.

    It is intentionally explainable rather than clever. This lets policy and
    replay behavior be tested without network calls or model usage.
    """

    def evaluate(self, observation: Observation) -> SemanticScores:
        data = observation.observations
        history = observation.history
        failures = _number(data, "failure_rate", "failures_5m")
        baseline_failures = max(_number(history, "normal_failure_rate", "normal_failures_5m", default=1.0), 0.001)
        latency = _number(data, "latency_p95_ms")
        baseline_latency = max(_number(history, "normal_latency_p95_ms", default=latency or 1.0), 1.0)
        stopped = bool(data.get("status") in {"stopped", "dead", "failed"})
        blocked = bool(data.get("status") == "blocked" or data.get("blocked"))
        security = 1.0 if bool(data.get("security_relevant")) else 0.0
        certificate_hours = _number(data, "certificate_hours_remaining", "cert_expiry_hours", default=999999.0)
        certificate_due = certificate_hours <= 24
        if any(word in str(data.get("message", "")).lower() for word in ("intrusion", "malware", "credential", "ransom")):
            security = 1.0
        failure = max(0.0, min(1.0, (failures / baseline_failures - 1.0) / 8.0))
        if stopped:
            failure = max(failure, 0.95)
        latency_signal = max(0.0, min(1.0, (latency / baseline_latency - 1.0) / 10.0)) if latency else 0.0
        abnormal = max(failure, latency_signal, security, 0.75 if certificate_due else 0.0)
        transient = 0.75 if bool(data.get("likely_transient", data.get("retryable", False))) else 0.15
        if stopped:
            transient = 0.2
        if blocked:
            transient = 0.0
        impact = max(0.0, min(1.0, _number(data, "user_impact", default=max(failure, latency_signal))))
        if stopped:
            impact = max(impact, 0.75)
        if blocked:
            impact = max(impact, 0.75)
        attention = max(security, impact * (1 - transient), 0.85 if certificate_due else 0.0)
        return SemanticScores(
            routine_event=max(0.0, 1.0 - abnormal), abnormality=abnormal,
            probable_failure=max(failure, 0.8 * latency_signal), security_relevant=security,
            human_attention_needed=attention, likely_transient=transient,
            worsening=max(0.0, min(1.0, _number(data, "worsening", default=max(latency_signal, 0.6 if certificate_due else 0.0)))),
            immediate_action=max(security, 0.9 if stopped and impact > 0.8 else 0.7 if certificate_due and data.get("human_action_possible", True) else 0.0),
            user_impact=impact, recoverability=0.85 if transient else 0.35,
        ).clamp()


def event_from_scores(observation: Observation, scores: SemanticScores) -> SIRQEvent:
    scores.clamp()
    if scores.security_relevant >= 0.8:
        kind = "SECURITY_ANOMALY"
    elif scores.probable_failure >= 0.8 and scores.likely_transient >= 0.7:
        kind = "TRANSIENT_FAILURE"
    elif scores.probable_failure >= 0.55:
        kind = "PERSISTENT_FAILURE"
    elif scores.human_attention_needed >= 0.65:
        kind = "HUMAN_ATTENTION_REQUIRED"
    elif scores.abnormality >= 0.35:
        kind = "UNEXPECTED_BEHAVIOR"
    else:
        kind = "ROUTINE"
    priority = round(max(scores.immediate_action, scores.human_attention_needed, scores.user_impact) * 7)
    return SIRQEvent(
        kind=kind, source=observation.source,
        confidence=max(scores.abnormality, scores.security_relevant, scores.probable_failure, scores.human_attention_needed),
        priority=priority, urgency=max(scores.immediate_action, scores.worsening),
        impact=scores.user_impact, recoverability=scores.recoverability,
        human_attention=scores.human_attention_needed, scores=scores,
        observation=asdict(observation),
    )
