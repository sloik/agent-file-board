#!/usr/bin/env python3
"""Run bounded TLC models and require named counterexamples for mutation controls."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parent


def verified_jar(pin, explicit=None):
    cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "agent-file-board-formal"
    target = Path(explicit) if explicit else cache / ("tla2tools-" + pin["version"] + ".jar")
    if not target.exists():
        if explicit:
            raise ValueError("explicit TLC jar does not exist")
        cache.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(pin["url"], timeout=60) as response:
            raw = response.read(8 * 1024 * 1024 + 1)
        if len(raw) > 8 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != pin["sha256"]:
            raise ValueError("downloaded TLC jar checksum mismatch")
        with tempfile.NamedTemporaryFile(dir=cache, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(raw)
        try:
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    if hashlib.sha256(target.read_bytes()).hexdigest() != pin["sha256"]:
        raise ValueError("TLC jar checksum mismatch; replace the corrupt cached/explicit jar")
    return target.resolve()


def run_case(java, jar, case):
    with tempfile.TemporaryDirectory(prefix="afb-tlc-") as temporary:
        result = subprocess.run(
            [java, "-XX:+UseParallelGC", "-Xmx1g", "-Djava.io.tmpdir=" + temporary, "-cp", str(jar), "tlc2.TLC",
             "-workers", "1", "-metadir", temporary, "-config", str(ROOT / case["config"]),
             str(ROOT / case["module"])],
            cwd=temporary, capture_output=True, text=True, timeout=case.get("timeout", 90))
    output = result.stdout + result.stderr
    invariant = case.get("counterexample")
    if invariant:
        passed = (result.returncode != 0 and
                  "Error: Invariant " + invariant + " is violated." in output and
                  "The behavior up to this point is:" in output)
    else:
        passed = result.returncode == 0 and "Model checking completed. No error has been found." in output
    if not passed:
        raise RuntimeError(case["config"] + " unexpected TLC result:\n" + output)
    print(case["config"] + (": expected counterexample " + invariant if invariant else ": PASS"), flush=True)
    for line in output.splitlines():
        if "states generated" in line or "distinct states found" in line or "Finished in" in line:
            print("  " + line, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jar", help="existing jar (still checksum-verified)")
    args = parser.parse_args()
    from check_alignment import check as check_alignment
    alignment = check_alignment(ROOT.parent)
    if not alignment['ok']:
        raise ValueError('Formal alignment review required:\n' + '\n'.join(alignment['errors']))
    suite = json.loads((ROOT / "suite.json").read_text())
    java = os.environ.get("JAVA") or shutil.which("java")
    if not java:
        raise ValueError("Java11+ is required; set JAVA to its executable")
    jar = verified_jar(suite["tool"], args.jar)
    for case in suite["cases"]:
        run_case(java, jar, case)


if __name__ == "__main__":
    main()
