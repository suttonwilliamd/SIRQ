import io
import json
import unittest

from sirq.alert_adapters import (
    adapt_datadog,
    adapt_generic_webhook,
    adapt_grafana_alertmanager,
    adapt_pagerduty,
    adapt_sentry,
    replay_jsonl,
)
from sirq.alerts import AlertValidationError, ExistingOutcome, IncomingAlert


class AlertFoundationTests(unittest.TestCase):
    def test_incoming_alert_round_trips_and_preserves_raw_payload(self):
        payload = {"nested": {"value": 7}, "message": "keep every provider field"}
        alert = IncomingAlert(
            event_id="evt-1",
            source="test",
            service="checkout",
            observed_at="2026-09-21T12:00:00Z",
            correlation_key="checkout/errors",
            incident_key="inc-1",
            raw_payload=payload,
            existing_outcome=ExistingOutcome(True, "critical", "pagerduty", True, 12),
        )
        payload["nested"]["value"] = 99
        self.assertEqual(alert.raw_payload["nested"]["value"], 7)
        restored = IncomingAlert.from_dict(alert.to_dict())
        self.assertEqual(restored.to_dict(), alert.to_dict())

    def test_required_fields_and_keys_are_validated(self):
        base = {
            "event_id": "evt-1",
            "source": "test",
            "service": "checkout",
            "observed_at": "2026-09-21T12:00:00Z",
            "correlation_key": "checkout/errors",
            "raw_payload": {},
            "existing_outcome": {
                "paged_human": False,
                "severity": "info",
                "destination": "none",
                "human_action_taken": False,
            },
        }
        for field in ("event_id", "source", "service", "observed_at", "correlation_key", "raw_payload", "existing_outcome"):
            with self.subTest(field=field):
                value = dict(base)
                value.pop(field)
                with self.assertRaises(AlertValidationError):
                    IncomingAlert.from_dict(value)
        with self.assertRaises(AlertValidationError):
            IncomingAlert.from_dict({**base, "correlation_key": "   "})
        with self.assertRaises(AlertValidationError):
            IncomingAlert.from_dict({**base, "incident_key": ""})

    def test_timestamp_severity_destination_and_boolean_validation(self):
        with self.assertRaises(AlertValidationError):
            IncomingAlert("e", "s", "svc", "2026-09-21T12:00:00", "c", {}, ExistingOutcome(False, "info", "none", False))
        with self.assertRaises(AlertValidationError):
            ExistingOutcome(False, "urgent", "none", False)
        with self.assertRaises(AlertValidationError):
            ExistingOutcome(False, "info", "", False)
        with self.assertRaises(AlertValidationError):
            ExistingOutcome("false", "info", "none", False)
        with self.assertRaises(AlertValidationError):
            ExistingOutcome(False, "info", "none", 0)
        with self.assertRaises(AlertValidationError):
            ExistingOutcome.from_dict({"paged_human": False, "severity": "info", "destination": "none"})

    def test_datadog_adapter(self):
        payload = {
            "id": "dd-1",
            "date_happened": "2026-09-21T12:00:00Z",
            "alert_status": "alert",
            "monitor_id": "mon-7",
            "aggregation_key": "checkout/errors",
            "tags": ["service:checkout"],
            "message": "error rate high",
        }
        alert = adapt_datadog(payload)
        self.assertEqual(alert.source, "datadog")
        self.assertEqual(alert.service, "checkout")
        self.assertEqual(alert.incident_key, "mon-7")
        self.assertEqual(alert.raw_payload, payload)
        self.assertTrue(alert.existing_outcome.paged_human)

    def test_sentry_adapter(self):
        alert = adapt_sentry({
            "event_id": "sentry-event",
            "timestamp": "2026-09-21T12:00:00Z",
            "level": "error",
            "issue": {"id": "issue-9", "title": "Error"},
            "project": {"slug": "checkout"},
        })
        self.assertEqual(alert.correlation_key, "issue-9")
        self.assertEqual(alert.existing_outcome.severity, "error")

    def test_grafana_alertmanager_adapter_returns_each_alert(self):
        payload = {
            "groupKey": "group-1",
            "receiver": "oncall-team",
            "alerts": [
                {"fingerprint": "fp-1", "startsAt": "2026-09-21T12:00:00Z", "status": "firing", "labels": {"alertname": "CPUHigh", "service": "api"}},
                {"fingerprint": "fp-2", "startsAt": "2026-09-21T12:01:00Z", "status": "resolved", "labels": {"alertname": "Disk", "service": "db"}},
            ],
        }
        alerts = adapt_grafana_alertmanager(payload)
        self.assertEqual([item.event_id for item in alerts], ["fp-1", "fp-2"])
        self.assertEqual(alerts[0].existing_outcome.destination, "oncall-team")
        self.assertTrue(alerts[0].existing_outcome.paged_human)
        self.assertFalse(alerts[1].existing_outcome.paged_human)
        self.assertEqual(alerts[0].raw_payload, payload)

    def test_pagerduty_adapter_returns_each_message(self):
        alerts = adapt_pagerduty({
            "messages": [{
                "id": "msg-1",
                "event_type": "incident.triggered",
                "created_at": "2026-09-21T12:00:00Z",
                "incident": {"id": "inc-1", "urgency": "high", "service": {"summary": "api"}},
            }]
        })
        self.assertEqual(alerts[0].correlation_key, "inc-1")
        self.assertEqual(alerts[0].service, "api")
        self.assertTrue(alerts[0].existing_outcome.paged_human)

    def test_generic_webhook_and_local_jsonl_replay(self):
        payload = {
            "event_id": "generic-1",
            "source": "internal-hook",
            "service": "worker",
            "observed_at": "2026-09-21T12:00:00Z",
            "correlation_key": "worker/restarts",
            "incident_key": "incident-1",
            "raw_payload": {"arbitrary": [1, 2, 3]},
            "existing_outcome": {"paged_human": False, "severity": "warning", "destination": "slack", "human_action_taken": False},
        }
        alert = adapt_generic_webhook(payload)
        line = json.dumps(alert.to_dict())
        replayed = list(replay_jsonl(io.StringIO(line + "\n")))
        self.assertEqual(replayed[0].event_id, "generic-1")
        self.assertEqual(replayed[0].raw_payload, payload)


if __name__ == "__main__":
    unittest.main()
