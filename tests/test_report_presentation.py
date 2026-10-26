import contextlib
import io
from pathlib import Path
import tempfile
import unittest

from sirq.cli import cmd_oncall_demo, cmd_showcase, cmd_report, cmd_shadow_report
from sirq.report import render_html
from sirq.shadow_report import render_shadow_html


class PresentationTests(unittest.TestCase):
    def test_demo_and_generic_cli_provenance(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            for name, command in [('showcase', cmd_showcase), ('oncall', cmd_oncall_demo)]:
                path = Path(tmp) / (name + '.html')
                command(str(path))
                text = path.read_text()
                for label in ['Offline simulation', 'deterministic mock', 'synthetic fixtures', 'no production actions', 'mock score']:
                    self.assertIn(label, text)
                if name == 'oncall':
                    for label in ['fixture-only recommendation difference', 'fixture-label agreement: 88.9%', '77.8%']:
                        self.assertIn(label, text)
                else:
                    self.assertIn('permitted policy outcomes', text)
            for command, source in [(cmd_report, 'examples/showcase.jsonl'), (cmd_shadow_report, 'examples/one-bad-night.jsonl')]:
                path = Path(tmp) / 'generic.html'
                command(source, str(path))
                text = path.read_text()
                self.assertIn('provenance unknown', text)
                self.assertNotIn('synthetic fixtures', text)
                self.assertNotIn('fixture-label agreement', text)

    def test_provenance_escaped_and_public_defaults_compatible(self):
        for renderer in [render_html, render_shadow_html]:
            text = renderer([], 'Existing positional title', provenance='<img src=x onerror=bad>&')
            self.assertIn('&lt;img src=x onerror=bad&gt;&amp;', text)
            self.assertNotIn('<img', text)
            self.assertIn('Existing positional title', text)
            self.assertIn('provenance unknown', renderer([]))

    def test_old_efficacy_labels_removed(self):
        for text in [render_html([]), render_shadow_html([])]:
            for obsolete in ['allowed actions', 'reviewed accuracy:', 'potential reduction', 'incoming production alerts']:
                self.assertNotIn(obsolete, text)
            self.assertIn('not calibrated confidence', text)
