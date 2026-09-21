import io
import json
import tempfile
import unittest
from pathlib import Path

from sirq.adapters import stdin_adapter
from sirq.core import MockJevEvaluator, Observation, event_from_scores
from sirq.policy import PolicyEngine, PolicyRule
from sirq.runtime import JsonlRecorder, SIRQRuntime
from sirq.report import render_html
from sirq.oncall import Recommendation, ShadowRuntime, read_alerts
from sirq.shadow_report import render_shadow_html


class SIRQTests(unittest.TestCase):
    def test_mock_evaluator_classifies_transient_failure(self):
        observation = Observation("api", "health", {"failures_5m": 20, "retryable": True}, {"normal_failures_5m": 1})
        event = event_from_scores(observation, MockJevEvaluator().evaluate(observation))
        self.assertEqual(event.kind, "TRANSIENT_FAILURE")
        self.assertGreaterEqual(event.scores.probable_failure, 0.8)

    def test_policy_debounce_and_hysteresis(self):
        engine = PolicyEngine([PolicyRule("PERSISTENT_FAILURE", "DASHBOARD", debounce_observations=2, enter_threshold=.5, exit_threshold=.2)])
        make = lambda confidence: _persistent_event(confidence)
        def _persistent_event(confidence):
            event = event_from_scores(Observation("svc", "health"), type("Scores", (), {
                "routine_event": 0, "abnormality": confidence, "probable_failure": confidence,
                "security_relevant": 0, "human_attention_needed": confidence, "likely_transient": 0,
                "worsening": 0, "immediate_action": 0, "user_impact": confidence,
                "recoverability": .3, "clamp": lambda self: self
            })())
            event.kind = "PERSISTENT_FAILURE"
            return event
        first = engine.decide(make(.8))
        second = engine.decide(make(.8))
        self.assertFalse(first.allowed)
        self.assertTrue(second.allowed)
        engine.decide(make(.1))
        exit_decision = engine.decide(make(.1))
        self.assertFalse(exit_decision.allowed)
        self.assertIn("hysteresis", exit_decision.reason)

    def test_safe_handler_boundary(self):
        engine = PolicyEngine([PolicyRule("*", "shell")])
        decision = engine.decide(event_from_scores(Observation("x", "y"), MockJevEvaluator().evaluate(Observation("x", "y"))))
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.handler, "IGNORE")

    def test_jsonl_record_and_replay_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            runtime = SIRQRuntime(MockJevEvaluator(), PolicyEngine([]), JsonlRecorder(path))
            runtime.process(Observation("x", "health", {"status": "running"}))
            record = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(record["event"]["source"], "x")

    def test_stdin_adapter(self):
        stream = io.StringIO('{"source":"x","type":"health"}\n')
        self.assertEqual(next(stdin_adapter(stream)).source, "x")

    def test_blocked_agent_requires_human_attention(self):
        observation = Observation("agent-17", "agent_state", {
            "status": "blocked", "blocked": True, "user_impact": 0.8,
            "message": "needs human permission",
        })
        event = event_from_scores(observation, MockJevEvaluator().evaluate(observation))
        self.assertEqual(event.kind, "HUMAN_ATTENTION_REQUIRED")
        self.assertGreaterEqual(event.priority, 5)

    def test_report_contains_event_and_summary(self):
        observation = Observation("api", "health", {"security_relevant": True})
        runtime = SIRQRuntime(MockJevEvaluator(), PolicyEngine([]))
        html = render_html([runtime.process(observation)])
        self.assertIn("SECURITY_ANOMALY", html)
        self.assertIn("Semantic replay report", html)

    def test_one_bad_night_shadow_mode_is_powerless_and_actionable(self):
        records = ShadowRuntime(MockJevEvaluator()).process_many(
            read_alerts("examples/one-bad-night.jsonl")
        )
        self.assertEqual(len(records), 9)
        self.assertEqual(sum(r.recommendation == Recommendation.INTERRUPT for r in records), 2)
        self.assertEqual(sum(r.alert.existing_outcome.paged_human for r in records), 9)
        report = render_shadow_html(records)
        self.assertIn("potential reduction", report)
        self.assertIn("ZERO", report)


if __name__ == "__main__":
    unittest.main()
