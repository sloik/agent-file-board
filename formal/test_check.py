"""Fail-closed controls for the model-checking harness itself."""
import contextlib
import hashlib
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import check


class FormalRunnerTests(unittest.TestCase):
    def test_explicit_jar_is_always_verified(self):
        with tempfile.TemporaryDirectory() as temporary:
            jar = Path(temporary) / "tools.jar"
            jar.write_bytes(b"wrong jar")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                check.verified_jar({"sha256": "0" * 64}, jar)

    def test_fresh_download_and_cached_read_both_require_matching_digest(self):
        raw = b"verified tool fixture"
        pin = {"version": "fixture", "url": "https://example.invalid/tool.jar",
               "sha256": hashlib.sha256(raw).hexdigest()}
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"XDG_CACHE_HOME": temporary}):
            with patch.object(check.urllib.request, "urlopen", return_value=io.BytesIO(raw)) as download:
                jar = check.verified_jar(pin)
                self.assertEqual(jar.read_bytes(), raw)
                check.verified_jar(pin)
                download.assert_called_once()
            jar.write_bytes(b"cache changed")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                check.verified_jar(pin)

    def test_wrong_download_is_never_installed(self):
        pin = {"version": "fixture", "url": "https://example.invalid/tool.jar", "sha256": "0" * 64}
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"XDG_CACHE_HOME": temporary}):
            with patch.object(check.urllib.request, "urlopen", return_value=io.BytesIO(b"bad download")):
                with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                    check.verified_jar(pin)
            self.assertEqual(list(Path(temporary).rglob("*.jar")), [])

    def test_expected_counterexample_rejects_parse_errors_wrong_invariant_and_zero_exit(self):
        case = {"module": "ignored.tla", "config": "ignored.cfg", "counterexample": "Security"}
        trace = "Error: Invariant Security is violated.\nThe behavior up to this point is:"
        for code, output in [(1, "Parse error"), (12, trace.replace("Security", "Different")),
                             (0, trace), (12, "Error: Invariant Security is violated.")]:
            with self.subTest(code=code, output=output):
                result = subprocess.CompletedProcess([], code, output, "")
                with patch.object(check.subprocess, "run", return_value=result):
                    with self.assertRaisesRegex(RuntimeError, "unexpected TLC result"):
                        check.run_case("java", Path("tools.jar"), case)

    def test_success_requires_both_exit_zero_and_completion_marker(self):
        case = {"module": "ignored.tla", "config": "ignored.cfg"}
        marker = "Model checking completed. No error has been found."
        for code, output in [(0, ""), (1, marker)]:
            with patch.object(check.subprocess, "run", return_value=subprocess.CompletedProcess([], code, output, "")):
                with self.assertRaisesRegex(RuntimeError, "unexpected TLC result"):
                    check.run_case("java", Path("tools.jar"), case)

    def test_valid_named_counterexample_is_accepted(self):
        case = {"module": "ignored.tla", "config": "ignored.cfg", "counterexample": "Security"}
        result = subprocess.CompletedProcess([], 12, "Error: Invariant Security is violated.\nThe behavior up to this point is:", "")
        with patch.object(check.subprocess, "run", return_value=result), contextlib.redirect_stdout(io.StringIO()) as out:
            check.run_case("java", Path("tools.jar"), case)
        self.assertIn("expected counterexample Security", out.getvalue())


if __name__ == "__main__":
    unittest.main()
