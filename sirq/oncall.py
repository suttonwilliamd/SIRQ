from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable, Mapping

from .core import Observation, SemanticEvaluator, SIRQEvent, event_from_scores, utc_now


class Recommendation(StrEnum):
    INTERRUPT = "INTERRUPT"
    NOTIFY = "NOTIFY"
    RECORD_ONLY = "RECORD_ONLY"


class ReviewStatus(StrEnum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    UNSURE = "unsure"


@dataclass(slots=True)
class ExistingOutcome:
    paged_human: bool = False
    severity: str = "info"
    destination: str = "none"
    resolved_after_seconds: float | None = None
    human_action_taken: bool = False

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "ExistingOutcome":
        value = value or {}
        resolved = value.get("resolved_after_seconds")
        return cls(
            paged_human=bool(value.get("paged_human", False)),
            severity=str(value.get("severity", "info")),
            destination=str(value.get("destination", "none")),
            resolved_after_seconds=float(resolved) if resolved is not None else None,
            human_action_taken=bool(value.get("human_action_taken", False)),
        )


@dataclass(slots=True)
class AlertEnvelope:
    event_id: str
    source: str
    service: str
    raw_payload: dict[str, Any]
    observed_at: str = field(default_factory=utc_now)
    correlation_key: str = ""
    existing_outcome: ExistingOutcome = field(default_factory=ExistingOutcome)
    review: ReviewStatus | None = None

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AlertEnvelope":
        return cls(
            event_id=str(value["event_id"]), source=str(value["source"]),
            service=str(value.get("service", value["source"])),
            raw_payload=dict(value.get("raw_payload", value.get("observations", {}))),
            observed_at=str(value.get("observed_at", value.get("timestamp", utc_now()))),
            correlation_key=str(value.get("correlation_key", value.get("service", value["source"]))),
            existing_outcome=ExistingOutcome.from_dict(value.get("existing_outcome")),
            review=ReviewStatus(value["review"]) if value.get("review") else None,
        )

    def to_observation(self) -> Observation:
        payload = dict(self.raw_payload)
        payload.setdefault("service", self.service)
        return Observation(
            source=self.source,
            type=str(payload.pop("type", "incoming_alert")),
            observations=payload,
            context={"alert_id": self.event_id, "correlation_key": self.correlation_key},
            timestamp=self.observed_at,
        )


@dataclass(slots=True)
class SIRQAssessment:
    human_action_required: float
    human_action_possible: float
    customer_impact: float
    likely_self_resolving: float
    security_relevant: float
    duplicate_symptom: float
    urgency: float
    confidence: float
    safe_to_delay: float

    @classmethod
    def from_event(cls, event: SIRQEvent, duplicate: bool = False) -> "SIRQAssessment":
        scores = event.scores
        return cls(
            human_action_required=scores.human_attention_needed,
            human_action_possible=max(scores.human_attention_needed, scores.immediate_action),
            customer_impact=scores.user_impact,
            likely_self_resolving=scores.likely_transient,
            security_relevant=scores.security_relevant,
            duplicate_symptom=1.0 if duplicate else 0.0,
            urgency=event.urgency,
            confidence=event.confidence,
            safe_to_delay=max(0.0, min(1.0, scores.recoverability - scores.immediate_action)),
        )


@dataclass(slots=True)
class ShadowRecord:
    alert: AlertEnvelope
    event: SIRQEvent
    assessment: SIRQAssessment
    recommendation: Recommendation
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert": asdict(self.alert),
            "event": self.event.to_dict(),
            "assessment": asdict(self.assessment),
            "recommendation": self.recommendation.value,
            "reason": self.reason,
        }


class ShadowRuntime:
    """Evaluate alerts without changing the production alert path."""

    def __init__(self, evaluator: SemanticEvaluator):
        self.evaluator = evaluator
        self._interrupted_correlations: set[str] = set()

    def process(self, alert: AlertEnvelope) -> ShadowRecord:
        observation = alert.to_observation()
        event = event_from_scores(observation, self.evaluator.evaluate(observation))
        duplicate = alert.correlation_key in self._interrupted_correlations
        assessment = SIRQAssessment.from_event(event, duplicate=duplicate)
        if duplicate:
            recommendation = Recommendation.RECORD_ONLY
            reason = "duplicate symptom already represented by an interrupt"
        elif assessment.security_relevant >= 0.8 or assessment.human_action_required >= 0.8:
            recommendation = Recommendation.INTERRUPT
            reason = "high human-action or security relevance"
            self._interrupted_correlations.add(alert.correlation_key)
        elif assessment.human_action_required >= 0.35 or event.scores.probable_failure >= 0.55:
            recommendation = Recommendation.NOTIFY
            reason = "worth notifying, but not an immediate interruption"
        else:
            recommendation = Recommendation.RECORD_ONLY
            reason = "likely routine or self-resolving"
        return ShadowRecord(alert, event, assessment, recommendation, reason)

    def process_many(self, alerts: Iterable[AlertEnvelope]) -> list[ShadowRecord]:
        return [self.process(alert) for alert in alerts]


def read_alerts(path: str | Path) -> Iterable[AlertEnvelope]:
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                yield AlertEnvelope.from_dict(json.loads(line))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid alert envelope on line {line_number}: {exc}") from exc
