"""Offline report trust-boundary tests; no network or browser required."""
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

from sirq.core import MockJevEvaluator, Observation, event_from_scores
from sirq.oncall import AlertEnvelope, ShadowRuntime
from sirq.policy import PolicyDecision
from sirq.report import render_html, write_report
from sirq.review import ReviewRecord, apply_reviews, calculate_shadow_metrics
from sirq.shadow_report import render_shadow_html, write_shadow_report


PAYLOADS = (
    '<script>alert("sirq")</script>',
    '<img src=x onerror="alert(1)">',
    '</title><svg onload=alert(1)>',
    '<a href="javascript:alert(1)">open</a>',
    '\"\' autofocus onfocus="alert(1)" & < >',
    '&lt;script&gt;alert(1)&lt;/script&gt;',
    'https://example.invalid/?a=1&b=2 javascript:alert(1)',
    'café 日本語 🐈 & "quoted"',
)


class ParsedReport(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.markup = []
        self.text = []
        self.feed(source)
        self.close()

    def handle_starttag(self, tag, attrs):
        self.markup.append(("start", tag, tuple(attrs)))

    def handle_startendtag(self, tag, attrs):
        self.markup.append(("empty", tag, tuple(attrs)))

    def handle_endtag(self, tag):
        self.markup.append(("end", tag, ()))

    def handle_data(self, data):
        self.text.append(data)


def decision():
    observation = Observation("source", "health", {"message": "message"})
    event = event_from_scores(observation, MockJevEvaluator().evaluate(observation))
    return PolicyDecision(event, "RECORD", True, "reason")


def shadow_record():
    alert = AlertEnvelope.from_dict({
        "event_id": "synthetic", "source": "source", "service": "service",
        "observed_at": "2026-10-26T12:34:00Z", "raw_payload": {},
        "existing_outcome": {"destination": "none"},
    })
    return ShadowRuntime(MockJevEvaluator()).process(alert)


class ReportSafetyTests(unittest.TestCase):
    def assert_inert(self, source, baseline, displayed):
        parsed = ParsedReport(source)
        # Compare all tags AND attributes, not just a denylist of script tags.
        # Hostile text must neither add markup nor alter existing attributes.
        self.assertEqual(parsed.markup, ParsedReport(baseline).markup)
        if displayed is not None:
            self.assertIn(displayed, "".join(parsed.text))
        self.assertFalse(any(tag in {"script", "a", "iframe", "img", "svg"}
                             for _, tag, _ in parsed.markup))

    def test_replay_text_fields_are_inert_and_preserved(self):
        for field in ("source", "kind", "reason", "handler", "message",
                      "failures_5m", "latency_p95_ms"):
            for payload in PAYLOADS:
                with self.subTest(field=field, payload=payload):
                    item = decision()
                    baseline = render_html([item])
                    if field in {"source", "kind"}:
                        setattr(item.event, field, payload)
                    elif field in {"reason", "handler"}:
                        setattr(item, field, payload)
                    else:
                        item.event.observation["observations"][field] = payload
                    self.assert_inert(render_html(iter([item])), baseline, payload)

    def test_shadow_text_fields_are_inert_and_preserved(self):
        for field in ("service", "kind", "reason", "destination"):
            for payload in PAYLOADS:
                with self.subTest(field=field, payload=payload):
                    item = shadow_record()
                    baseline = render_shadow_html([item])
                    target = {"service": item.alert, "kind": item.event,
                              "reason": item, "destination": item.alert.existing_outcome}[field]
                    setattr(target, field, payload)
                    self.assert_inert(render_shadow_html(iter([item])), baseline, payload)

    def test_shadow_time_label_escapes_after_slicing(self):
        # AlertEnvelope accepts arbitrary timestamp strings; the view slices them.
        for timestamp in ('T<svg>', 'T<&"\'', 'T日本語🐈', '<img>'):
            with self.subTest(timestamp=timestamp):
                item = shadow_record()
                baseline = render_shadow_html([item])
                item.alert.observed_at = timestamp
                expected = timestamp.split("T", 1)[1][:5] if "T" in timestamp else timestamp[-8:]
                self.assert_inert(render_shadow_html([item]), baseline, expected)

    def test_titles_cannot_break_out_of_title_element(self):
        for render in (render_html, render_shadow_html):
            for payload in PAYLOADS:
                with self.subTest(render=render.__name__, payload=payload):
                    self.assert_inert(render([], title=payload), render([]), payload)

    def test_unrendered_alert_and_review_text_stays_unrendered(self):
        for payload in PAYLOADS:
            with self.subTest(payload=payload):
                item = shadow_record()
                apply_reviews([item], [ReviewRecord("synthetic", "correct")])
                baseline = render_shadow_html([item])
                item.alert.event_id = payload
                item.alert.source = payload
                item.alert.correlation_key = payload
                item.alert.raw_payload = {"message": payload, "nested": {"html": payload}}
                item.event.observation["observations"]["message"] = payload
                records = apply_reviews([item], [ReviewRecord(
                    payload, "correct", reviewer=payload, note=payload, reviewed_at=payload)])
                self.assert_inert(render_shadow_html(records), baseline, None)
                self.assertEqual(calculate_shadow_metrics(records).production_actions_taken, 0)
                self.assertEqual(calculate_shadow_metrics(records).reviewed, 1)
                self.assertNotIn(payload, render_shadow_html(records))

    def test_writers_preserve_utf8_and_renderer_output(self):
        with tempfile.TemporaryDirectory() as directory:
            for render, write, items, name in (
                (render_html, write_report, [decision()], "replay"),
                (render_shadow_html, write_shadow_report, [shadow_record()], "shadow"),
            ):
                title = PAYLOADS[-1]
                path = Path(directory) / name / "report.html"
                self.assertEqual(write(iter(items), path, title), path)
                self.assertEqual(path.read_text(encoding="utf-8"), render(items, title))


if __name__ == "__main__":
    unittest.main()
