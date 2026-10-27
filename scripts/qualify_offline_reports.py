"""Bounded stdlib-only CLI checks; no provider, server, or retained HTML."""
from collections import Counter
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


class ReportParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = Counter()
        self.utf8 = False
        self.disallowed = False

    def handle_starttag(self, tag, attrs):
        self.tags[tag] += 1
        attributes = dict(attrs)
        if tag == "meta" and attributes.get("charset", "").lower() == "utf-8":
            self.utf8 = True
        if tag in {"script", "iframe", "object", "embed", "link", "img"}:
            self.disallowed = True
        if any(key.startswith("on") or key in {"src", "href"} for key in attributes):
            self.disallowed = True


def validate_html(path, count):
    raw = path.read_bytes()
    require(0 < len(raw) < 1_000_000, "unexpected HTML size")
    text = raw.decode("utf-8", errors="strict")
    parser = ReportParser()
    parser.feed(text)
    parser.close()
    require(text.lower().startswith("<!doctype html>"), "missing HTML doctype")
    require(text.rstrip().endswith("</html>"), "incomplete HTML document")
    require(parser.utf8 and parser.tags["html"] == 1 and parser.tags["body"] == 1,
            "missing document/UTF-8 structure")
    require(parser.tags["article"] == count, "unexpected rendered fixture count")
    require(not parser.disallowed, "unexpected active or external HTML content")
    for label in ("Offline simulation", "deterministic mock", "synthetic fixtures",
                  "no production actions", "not calibrated confidence"):
        require(label in text, "missing disclosure: " + label)
    return text


def qualify():
    # Explicit UTF-8 mode covers Windows console pipes and existing default-codec tests.
    env = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    results = {}
    with tempfile.TemporaryDirectory(prefix="sirq offline ") as temporary:
        directory = Path(temporary) / "reports with spaces caf\u00e9 \u96ea"
        directory.mkdir()
        for command, count in (("showcase", 4), ("oncall-demo", 9)):
            output = directory / (command + ".html")
            run = subprocess.run(
                [sys.executable, "-m", "sirq.cli", command, "--output", str(output)],
                cwd=ROOT, env=env, capture_output=True, encoding="utf-8",
                errors="strict", timeout=30, check=True,
            )
            require(not run.stderr, "unexpected CLI stderr")
            text = validate_html(output, count)
            lines = run.stdout.splitlines()
            if command == "showcase":
                records = [json.loads(line) for line in lines[1:]]
                require(len(records) == 4, "expected four showcase decisions")
                require(Counter(item["kind"] for item in records) == Counter({
                    "ROUTINE": 1, "TRANSIENT_FAILURE": 1,
                    "SECURITY_ANOMALY": 1, "HUMAN_ATTENTION_REQUIRED": 1,
                }), "unexpected showcase decisions")
                require("permitted policy outcomes" in text, "missing policy scope")
            else:
                metrics = json.loads(lines[0])
                records = [json.loads(line) for line in lines[2:]]
                for key, value in {"alerts_observed": 9, "reviewed": 9, "correct": 8,
                                   "incorrect": 1, "sirq_interruptions": 2,
                                   "production_actions_taken": 0}.items():
                    require(metrics[key] == value, "unexpected metric: " + key)
                require(len(records) == 9, "expected nine oncall records")
                require(Counter(item["recommendation"] for item in records) ==
                        Counter({"RECORD_ONLY": 6, "NOTIFY": 1, "INTERRUPT": 2}),
                        "unexpected oncall recommendations")
                for label in ("fixture-only recommendation difference", "77.8%",
                              "fixture-label agreement: 88.9%"):
                    require(label in text, "missing fixture metric disclosure")
            results[command] = {"fixtures": count, "utf8_html": True}
    require(not Path(temporary).exists(), "temporary report cleanup failed")
    return {"scope": "offline deterministic mock / tracked synthetic fixtures only",
            "reports": results, "temporary_cleanup": True,
            "python": ".".join(map(str, sys.version_info[:3])),
            "platform": sys.platform}


if __name__ == "__main__":
    print(json.dumps(qualify(), sort_keys=True))
