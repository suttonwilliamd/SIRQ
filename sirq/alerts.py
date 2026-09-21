from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Mapping


class AlertValidationError(ValueError):
    """Raised when an alert envelope cannot be safely normalized."""


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AlertValidationError(f"{field_name} must be a non-empty string")
    return value.strip()


def _timestamp(value: Any, field_name: str) -> str:
    text = _required_text(value, field_name)
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise AlertValidationError(f"{field_name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AlertValidationError(f"{field_name} must include a timezone")
    return text


def _boolean(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise AlertValidationError(f"{field_name} must be a boolean")
    return value


@dataclass(slots=True)
class ExistingOutcome:
    """What the incumbent alerting path actually did for an incoming alert."""

    paged_human: bool
    severity: str
    destination: str
    human_action_taken: bool
    resolved_after_seconds: float | None = None

    def __post_init__(self) -> None:
        self.paged_human = _boolean(self.paged_human, "paged_human")
        self.human_action_taken = _boolean(self.human_action_taken, "human_action_taken")
        self.severity = _required_text(self.severity, "severity").lower()
        if self.severity not in {item.value for item in Severity}:
            raise AlertValidationError(f"severity must be one of: {', '.join(item.value for item in Severity)}")
        self.destination = _required_text(self.destination, "destination").lower()
        if self.resolved_after_seconds is not None:
            if isinstance(self.resolved_after_seconds, bool):
                raise AlertValidationError("resolved_after_seconds must be a non-negative number")
            try:
                self.resolved_after_seconds = float(self.resolved_after_seconds)
            except (TypeError, ValueError) as exc:
                raise AlertValidationError("resolved_after_seconds must be a non-negative number") from exc
            if self.resolved_after_seconds < 0:
                raise AlertValidationError("resolved_after_seconds must be a non-negative number")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ExistingOutcome":
        if not isinstance(value, Mapping):
            raise AlertValidationError("existing_outcome must be an object")
        required = ("paged_human", "severity", "destination", "human_action_taken")
        missing = [name for name in required if name not in value]
        if missing:
            raise AlertValidationError(f"existing_outcome missing required fields: {', '.join(missing)}")
        return cls(
            paged_human=value["paged_human"],
            severity=value["severity"],
            destination=value["destination"],
            human_action_taken=value["human_action_taken"],
            resolved_after_seconds=value.get("resolved_after_seconds"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class IncomingAlert:
    """Provider-neutral alert envelope consumed by Shadow Mode."""

    event_id: str
    source: str
    service: str
    observed_at: str
    correlation_key: str
    raw_payload: dict[str, Any]
    existing_outcome: ExistingOutcome
    incident_key: str | None = None
    received_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        self.event_id = _required_text(self.event_id, "event_id")
        self.source = _required_text(self.source, "source")
        self.service = _required_text(self.service, "service")
        self.observed_at = _timestamp(self.observed_at, "observed_at")
        self.received_at = _timestamp(self.received_at, "received_at")
        self.correlation_key = _required_text(self.correlation_key, "correlation_key")
        if self.incident_key is not None:
            self.incident_key = _required_text(self.incident_key, "incident_key")
        if not isinstance(self.raw_payload, Mapping):
            raise AlertValidationError("raw_payload must be an object")
        self.raw_payload = deepcopy(dict(self.raw_payload))
        if not isinstance(self.existing_outcome, ExistingOutcome):
            raise AlertValidationError("existing_outcome must be an ExistingOutcome")

    @property
    def alert_id(self) -> str:
        """Alias used by providers that call the identifier alert_id."""
        return self.event_id

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "IncomingAlert":
        if not isinstance(value, Mapping):
            raise AlertValidationError("incoming alert must be an object")
        required = ("event_id", "source", "service", "observed_at", "correlation_key", "raw_payload", "existing_outcome")
        missing = [name for name in required if name not in value]
        if missing:
            raise AlertValidationError(f"incoming alert missing required fields: {', '.join(missing)}")
        return cls(
            event_id=value["event_id"],
            source=value["source"],
            service=value["service"],
            observed_at=value["observed_at"],
            correlation_key=value["correlation_key"],
            raw_payload=value["raw_payload"],
            existing_outcome=ExistingOutcome.from_dict(value["existing_outcome"]),
            incident_key=value.get("incident_key"),
            received_at=value.get("received_at", utc_now()),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
