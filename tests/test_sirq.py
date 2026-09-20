import io
import json
import tempfile
import unittest
from pathlib import Path

from sirq.adapters import stdin_adapter
from sirq.core import MockJevEvaluator, Observation, event_from_scores
from sirq.policy import PolicyEngine, PolicyRule
from sirq.runtime import JsonlRecorder, SIRQRuntime


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


if __name__ == "__main__":
    unittest.main()
