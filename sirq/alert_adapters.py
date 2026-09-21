from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any, TextIO

from .alerts import ExistingOutcome, IncomingAlert, Severity, utc_now


def _first(*values: Any, default: Any = None) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return default


def _tags(payload: Mapping[str, Any]) -> dict[str, str]:
    tags = payload.get("tags", {})
    if isinstance(tags, Mapping):
        return {str(key): str(value) for key, value in tags.items()}
    if isinstance(tags, list):
        result: dict[str, str] = {}
        for item in tags:
            if isinstance(item, str) and ":" in item:
                key, value = item.split(":", 1)
                result[key] = value
        return result
    return {}


def _outcome(
    *,
    paged_human: bool,
    severity: Any = Severity.UNKNOWN.value,
    destination: Any = "none",
    human_action_taken: bool = False,
    resolved_after_seconds: float | None = None,
) -> ExistingOutcome:
    return ExistingOutcome(
        paged_human=bool(paged_human),
        severity=str(severity or Severity.UNKNOWN.value).lower(),
        destination=str(destination or "none").lower(),
        human_action_taken=bool(human_action_taken),
        resolved_after_seconds=resolved_after_seconds,
    )


def _envelope(
    *,
    event_id: Any,
    source: str,
    service: Any,
    observed_at: Any,
    correlation_key: Any,
    raw_payload: Mapping[str, Any],
    existing_outcome: ExistingOutcome,
    incident_key: Any = None,
) -> IncomingAlert:
    return IncomingAlert(
        event_id=event_id,
        source=source,
        service=service,
        observed_at=observed_at,
        correlation_key=correlation_key,
        incident_key=incident_key,
        raw_payload=dict(raw_payload),
        existing_outcome=existing_outcome,
    )


def adapt_datadog(payload: Mapping[str, Any]) -> IncomingAlert:
    """Normalize a Datadog monitor/event payload without discarding its fields."""
    tags = _tags(payload)
    status = str(_first(payload.get("alert_status"), payload.get("status"), default="unknown")).lower()
    severity = {"alert": "critical", "warn": "warning", "warning": "warning", "ok": "info"}.get(status, "unknown")
    return _envelope(
        event_id=_first(payload.get("id"), payload.get("alert_id")),
        source="datadog",
        service=_first(tags.get("service"), payload.get("service"), default="datadog"),
        observed_at=_first(payload.get("date_happened"), payload.get("timestamp")),
        correlation_key=_first(payload.get("aggregation_key"), payload.get("group_key"), payload.get("monitor_id"), payload.get("id")),
        incident_key=_first(payload.get("monitor_id"), payload.get("id")),
        raw_payload=payload,
        existing_outcome=_outcome(
            paged_human=status in {"alert", "warn", "warning"},
            severity=severity,
            destination=_first(payload.get("destination"), "pagerduty" if status == "alert" else "none"),
            human_action_taken=status in {"acknowledged", "resolved"},
        ),
    )


def adapt_sentry(payload: Mapping[str, Any]) -> IncomingAlert:
    """Normalize a Sentry issue/event webhook payload."""
    issue = payload.get("issue") if isinstance(payload.get("issue"), Mapping) else {}
    project = payload.get("project") if isinstance(payload.get("project"), Mapping) else {}
    tags = _tags(payload)
    level = str(_first(payload.get("level"), issue.get("level"), default="unknown")).lower()
    severity = {"fatal": "critical", "error": "error", "warning": "warning", "info": "info"}.get(level, "unknown")
    event_id = _first(payload.get("event_id"), payload.get("id"), issue.get("id"))
    return _envelope(
        event_id=event_id,
        source="sentry",
        service=_first(tags.get("service"), project.get("slug"), project.get("name"), default="sentry"),
        observed_at=_first(payload.get("timestamp"), payload.get("received")),
        correlation_key=_first(payload.get("fingerprint"), issue.get("id"), event_id),
        incident_key=issue.get("id"),
        raw_payload=payload,
        existing_outcome=_outcome(
            paged_human=severity in {"critical", "error"},
            severity=severity,
            destination=_first(payload.get("destination"), "pagerduty" if severity == "critical" else "none"),
            human_action_taken=str(_first(payload.get("status"), issue.get("status"), default="open")).lower() in {"resolved", "closed"},
        ),
    )


def adapt_grafana_alertmanager(payload: Mapping[str, Any]) -> list[IncomingAlert]:
    """Normalize every alert in a Grafana Alertmanager webhook."""
    alerts = payload.get("alerts")
    if not isinstance(alerts, list) or not alerts:
        alerts = [payload]
    result: list[IncomingAlert] = []
    for alert in alerts:
        if not isinstance(alert, Mapping):
            raise ValueError("Grafana Alertmanager alerts must be objects")
        labels = alert.get("labels", {}) if isinstance(alert.get("labels"), Mapping) else {}
        annotations = alert.get("annotations", {}) if isinstance(alert.get("annotations"), Mapping) else {}
        status = str(alert.get("status", "firing")).lower()
        severity = str(_first(labels.get("severity"), default="critical" if status == "firing" else "info")).lower()
        result.append(_envelope(
            event_id=_first(alert.get("fingerprint"), labels.get("alertname")),
            source="grafana_alertmanager",
            service=_first(labels.get("service"), labels.get("job"), default="grafana"),
            observed_at=_first(alert.get("startsAt"), alert.get("endsAt")),
            correlation_key=_first(payload.get("groupKey"), alert.get("fingerprint"), labels.get("alertname")),
            incident_key=alert.get("fingerprint"),
            raw_payload=payload,
            existing_outcome=_outcome(
                paged_human=status == "firing",
                severity=severity,
                destination=_first(payload.get("receiver"), "none"),
                human_action_taken=status in {"resolved", "acknowledged"},
            ),
        ))
    return result


def adapt_pagerduty(payload: Mapping[str, Any]) -> list[IncomingAlert]:
    """Normalize PagerDuty v2 webhook messages."""
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        messages = [payload]
    result: list[IncomingAlert] = []
    for message in messages:
        if not isinstance(message, Mapping):
            raise ValueError("PagerDuty messages must be objects")
        incident = message.get("incident") if isinstance(message.get("incident"), Mapping) else message
        service = incident.get("service") if isinstance(incident.get("service"), Mapping) else {}
        event_type = str(_first(message.get("event_type"), message.get("type"), default="triggered")).lower()
        urgency = str(_first(incident.get("urgency"), default="high")).lower()
        result.append(_envelope(
            event_id=_first(message.get("id"), incident.get("id")),
            source="pagerduty",
            service=_first(service.get("summary"), service.get("name"), incident.get("service_name"), default="pagerduty"),
            observed_at=_first(message.get("created_at"), incident.get("created_at")),
            correlation_key=_first(incident.get("id"), message.get("id")),
            incident_key=incident.get("id"),
            raw_payload=payload,
            existing_outcome=_outcome(
                paged_human=event_type in {"triggered", "incident.triggered"},
                severity="critical" if urgency == "high" else "warning",
                destination="pagerduty",
                human_action_taken=event_type in {"acknowledged", "resolved", "incident.acknowledged", "incident.resolved"},
            ),
        ))
    return result


def adapt_generic_webhook(payload: Mapping[str, Any], *, source: str = "generic_webhook") -> IncomingAlert:
    """Normalize a canonical or lightly structured webhook payload."""
    if "existing_outcome" in payload:
        outcome = ExistingOutcome.from_dict(payload["existing_outcome"])
    else:
        outcome = _outcome(
            paged_human=bool(payload.get("paged_human", False)),
            severity=payload.get("severity", "unknown"),
            destination=payload.get("destination", "none"),
            human_action_taken=bool(payload.get("human_action_taken", False)),
        )
    return _envelope(
        event_id=_first(payload.get("event_id"), payload.get("alert_id"), payload.get("id")),
        source=source,
        service=_first(payload.get("service"), source),
        observed_at=_first(payload.get("observed_at"), payload.get("timestamp"), payload.get("created_at")),
        correlation_key=_first(payload.get("correlation_key"), payload.get("group_key"), payload.get("event_id"), payload.get("id")),
        incident_key=payload.get("incident_key"),
        raw_payload=payload,
        existing_outcome=outcome,
    )


def replay_jsonl(source: str | Path | TextIO) -> Iterator[IncomingAlert]:
    """Replay canonical IncomingAlert JSON objects from a local JSONL source."""
    should_close = isinstance(source, (str, Path))
    handle = Path(source).open(encoding="utf-8") if should_close else source
    try:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                yield IncomingAlert.from_dict(json.loads(line))
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                raise ValueError(f"invalid alert envelope on line {line_number}: {exc}") from exc
    finally:
        if should_close:
            handle.close()


__all__ = [
    "adapt_datadog",
    "adapt_sentry",
    "adapt_grafana_alertmanager",
    "adapt_pagerduty",
    "adapt_generic_webhook",
    "replay_jsonl",
]
