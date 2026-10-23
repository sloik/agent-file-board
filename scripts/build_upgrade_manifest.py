#!/usr/bin/env python3
"""Build audited upgrade data from the template and supported release tags."""
import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
PATHS = ("GLOSSARY.md", "components/board-report-v1.schema.json", "components/board-report-v2.schema.json", "components/board-report-v3.schema.json", "components/form-question-v2.schema.json", "components/form-answer-v2.schema.json", "components/form-question-v3.schema.json", "components/form-answer-v3.schema.json", "CONVENTION.md")
BASELINES = ("1.9.2", "2.0.0", "2.0.1", "2.1.0", "2.2.0", "2.3.0", "2.4.0", "2.5.0", "2.5.1", "2.6.0", "2.6.1", "2.7.0", "2.8.0", "2.9.0", "2.9.1", "2.10.0", "2.11.0", "2.11.1", "2.12.0", "2.12.1", "2.12.2", "3.0.0", "3.1.0", "3.2.0", "3.3.0")


def build():
    version = re.search(r"^Version: (\S+)$", (ROOT / ".agent-board/CONVENTION.md").read_text(), re.M)[1]
    files = []
    for path in PATHS:
        content = (ROOT / ".agent-board" / path).read_bytes()
        known = {hashlib.sha256(content).hexdigest()}
        for baseline in BASELINES:
            result = subprocess.run(["git", "-C", str(ROOT), "show", f"v{baseline}:.agent-board/{path}"], capture_output=True)
            if result.returncode == 0:
                known.add(hashlib.sha256(result.stdout).hexdigest())
            else:
                introduced = {"components/board-report-v1.schema.json": (2, 0, 0),
                              "components/board-report-v2.schema.json": (2, 1, 0),
                              "components/board-report-v3.schema.json": (2, 2, 0),
                              "components/form-question-v2.schema.json": (2, 3, 0),
                              "components/form-answer-v2.schema.json": (2, 3, 0),
                              "components/form-question-v3.schema.json": (2, 4, 0),
                              "components/form-answer-v3.schema.json": (2, 4, 0)}
                expected_absent = path in introduced and tuple(map(int, baseline.split("."))) < introduced[path]
                # Confirm the tag exists and the path is absent. Never swallow
                # arbitrary git read errors just because this is an old schema.
                listing = subprocess.run(["git", "-C", str(ROOT), "ls-tree", "-z", f"v{baseline}", "--", f".agent-board/{path}"], capture_output=True, check=True)
                if not expected_absent or listing.stdout:
                    raise RuntimeError(result.stderr.decode())
        files.append({"path": path, "content": base64.b64encode(content).decode(),
                      "sha256": hashlib.sha256(content).hexdigest(), "known": sorted(known)})
    return {"version": version, "supported": list(dict.fromkeys((*BASELINES, version))), "files": files}


if __name__ == "__main__":
    data = json.dumps(build(), indent=2) + "\n"
    dest = ROOT / "upgrade-manifest.json"
    if "--check" in sys.argv:
        if dest.read_text() != data:
            raise SystemExit("Upgrade manifest stale: run python3 scripts/build_upgrade_manifest.py")
    else:
        dest.write_text(data)
