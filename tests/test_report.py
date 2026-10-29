"""Report artifact integrity and escaped rendering tests."""

import base64
from contextlib import redirect_stdout, redirect_stderr
import hashlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import tempfile
import unittest

from lab.report import main as report_main, render_report
from lab.runner import main as run_main


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.attributes = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attributes.extend(attrs)


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "run"
        with redirect_stdout(io.StringIO()):
            self.assertEqual(run_main(["--steps", "4", "--output", str(self.directory)]), 0)

    def update_manifest(self, **changes):
        path = self.directory / "manifest.json"
        value = json.loads(path.read_text())
        value.update(changes)
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_simulated_label_and_operation_count(self):
        rendered = render_report(self.directory)
        self.assertIn("SIMULATED EVIDENCE", rendered)
        self.assertIn("not the Linux driver", rendered)
        self.assertEqual(rendered.count('class="operation"'), 4)
        self.assertIn('id="operation-0"', rendered)

    def test_untrusted_text_does_not_create_elements(self):
        payload = '</pre><img src=x onerror="alert(1)"><script>alert(2)</script>'
        self.update_manifest(platform=payload, git_commit=payload)
        rendered = render_report(self.directory)
        parsed = Tags()
        parsed.feed(rendered)
        self.assertNotIn("img", parsed.tags)
        self.assertEqual(parsed.tags.count("script"), 1)
        self.assertFalse(any(name.startswith("on") for name, _ in parsed.attributes))
        self.assertIn("&lt;script&gt;alert(2)&lt;/script&gt;", rendered)

    def test_csp_matches_embedded_script(self):
        rendered = render_report(self.directory)
        script = rendered.split("<script>")[1].split("</script>")[0]
        digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
        self.assertIn("script-src 'sha256-" + digest + "'", rendered)
        self.assertIn("default-src 'none'", rendered)

    def test_rejects_inconsistent_status_and_unknown_backend(self):
        self.update_manifest(status="fail")
        with self.assertRaises(ValueError):
            render_report(self.directory)
        self.update_manifest(status="pass", backend="unrecognized")
        with self.assertRaises(ValueError):
            render_report(self.directory)

    def test_incomplete_capture_has_no_pass_verdict(self):
        self.update_manifest(status="running")
        (self.directory / "result.json").unlink()
        (self.directory / "history.jsonl").unlink()
        rendered = render_report(self.directory)
        self.assertIn("Incomplete capture", rendered)
        self.assertNotIn("Contract pass", rendered)
        self.assertIn("No matching operations", rendered)

    def test_report_cannot_overwrite_evidence(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(report_main([str(self.directory)]), 0)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            report_main([str(self.directory), "--output", str(self.directory / "manifest.json")])
        self.assertEqual(json.loads((self.directory / "manifest.json").read_text())["status"], "pass")

    def test_rejects_missing_history_in_passing_run(self):
        (self.directory / "history.jsonl").unlink()
        self.update_manifest(operations_observed=0)
        with self.assertRaises(ValueError):
            render_report(self.directory)


if __name__ == "__main__":
    unittest.main()
