from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from .oncall import Recommendation, ReviewStatus, ShadowRecord


@dataclass(frozen=True, slots=True)
class ReviewRecord:
    """A human evaluation attached to one shadow-mode alert."""

    event_id: str
    status: ReviewStatus
    reviewer: str = ""
    note: str = ""
    reviewed_at: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.status, ReviewStatus):
            object.__setattr__(self, "status", ReviewStatus(str(self.status)))
        if not self.reviewed_at:
            object.__setattr__(self, "reviewed_at", datetime.now(timezone.utc).isoformat())

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ReviewRecord":
        return cls(
            event_id=str(value["event_id"]),
            status=ReviewStatus(str(value.get("status", value.get("review", "unsure")))),
            reviewer=str(value.get("reviewer", "")),
            note=str(value.get("note", "")),
            reviewed_at=str(value.get("reviewed_at", "")),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "event_id": self.event_id,
            "status": self.status.value,
            "reviewer": self.reviewer,
            "note": self.note,
            "reviewed_at": self.reviewed_at,
        }


def apply_reviews(records: Iterable[ShadowRecord], reviews: Iterable[ReviewRecord]) -> list[ShadowRecord]:
    """Return records with review labels applied, without mutating the runtime."""
    labels = {review.event_id: review.status for review in reviews}
    updated: list[ShadowRecord] = []
    for record in records:
        status = labels.get(record.alert.event_id)
        if status is not None:
            record.alert.review = status
        updated.append(record)
    return updated


@dataclass(frozen=True, slots=True)
class ShadowMetrics:
    alerts_observed: int
    existing_interruptions: int
    sirq_interruptions: int
    potential_reduction: float
    reviewed: int
    correct: int
    incorrect: int
    unsure: int
    reviewed_accuracy: float
    false_interruptions: int
    missed_critical_events: int
    duplicate_symptoms_avoided: int
    production_actions_taken: int
    existing_human_actions: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "alerts_observed": self.alerts_observed,
            "existing_interruptions": self.existing_interruptions,
            "sirq_interruptions": self.sirq_interruptions,
            "potential_reduction": self.potential_reduction,
            "reviewed": self.reviewed,
            "correct": self.correct,
            "incorrect": self.incorrect,
            "unsure": self.unsure,
            "reviewed_accuracy": self.reviewed_accuracy,
            "false_interruptions": self.false_interruptions,
            "missed_critical_events": self.missed_critical_events,
            "duplicate_symptoms_avoided": self.duplicate_symptoms_avoided,
            "production_actions_taken": self.production_actions_taken,
            "existing_human_actions": self.existing_human_actions,
        }


def calculate_shadow_metrics(records: Iterable[ShadowRecord]) -> ShadowMetrics:
    records = list(records)
    existing = sum(bool(record.alert.existing_outcome.paged_human) for record in records)
    sirq = sum(record.recommendation is Recommendation.INTERRUPT for record in records)
    reviewed_records = [record for record in records if record.alert.review is not None]
    correct = sum(record.alert.review is ReviewStatus.CORRECT for record in reviewed_records)
    incorrect = sum(record.alert.review is ReviewStatus.INCORRECT for record in reviewed_records)
    unsure = sum(record.alert.review is ReviewStatus.UNSURE for record in reviewed_records)
    critical = {
        "critical", "emergency", "fatal"
    }
    interrupted_correlations = {
        record.alert.correlation_key for record in records
        if record.recommendation is Recommendation.INTERRUPT
    }
    missed = sum(
        record.alert.existing_outcome.severity.lower() in critical
        and record.alert.correlation_key not in interrupted_correlations
        and not record.assessment.duplicate_symptom
        for record in records
    )
    false_interruptions = sum(
        record.recommendation is Recommendation.INTERRUPT
        and record.alert.review is ReviewStatus.INCORRECT
        for record in records
    )
    reduction = (existing - sirq) / existing if existing else 0.0
    return ShadowMetrics(
        alerts_observed=len(records),
        existing_interruptions=existing,
        sirq_interruptions=sirq,
        potential_reduction=reduction,
        reviewed=len(reviewed_records),
        correct=correct,
        incorrect=incorrect,
        unsure=unsure,
        reviewed_accuracy=correct / len(reviewed_records) if reviewed_records else 0.0,
        false_interruptions=false_interruptions,
        missed_critical_events=missed,
        duplicate_symptoms_avoided=sum(bool(record.assessment.duplicate_symptom) for record in records),
        production_actions_taken=0,
        existing_human_actions=sum(bool(record.alert.existing_outcome.human_action_taken) for record in records),
    )
