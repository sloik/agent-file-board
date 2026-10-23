import base64
import json
from pathlib import Path
import unittest

import room_history as history
import signing_core as core

VECTORS = json.loads((Path(__file__).resolve().parent / "fixtures/room-history/vectors.json").read_bytes())


class VectorCheckpoint(history.Checkpoint):
    """Checkpoint.entry over abstract vector inputs; no filesystem or keys involved."""

    def __init__(self, case):
        self.case = case
        self.state = {"sources": {h: {} for h in case["commitments"]}, "acknowledgements": {},
                      "commitments": {"rooms/general": {"x.txt": case["commitments"]}}, "unavailable": {}}
        ack = case["acknowledgement"]
        if ack:
            self.state["acknowledgements"]["x.txt"] = {"superseded": ack["superseded"], "reviewed": "reviewed"}

    def key_status(self, source):
        return self.case["sourceStatus"][next(h for h, s in self.state["sources"].items() if s is source)]

    def current(self, path):
        return self.case["current"]

    def sidecar(self, scope, record):
        return self.case["sidecars"].get(record)

    def reviewed(self, scope, path, digests):
        return "reviewed" if self.case["acknowledgement"]["reviewedMatches"] else "changed since review"


class RoomHistoryVectorTests(unittest.TestCase):
    def verify(self, raw):
        profile = core.verify_profile(base64.b64decode(VECTORS["profileEnvelopeBase64"]),
                                      expected_sha256=VECTORS["profileSha256"], board_id=VECTORS["boardId"],
                                      participant=VECTORS["participant"])
        payload, signature, statement = history.parse(raw)
        config = {"board": {"direct_directory": VECTORS["directDirectory"]}}
        history.check_statement(statement, VECTORS["boardId"], config, VECTORS["scope"])
        core._verify_signature((history.INVENTORY_TYPE, payload, signature), profile.descriptor)

    def test_inventory_vectors(self):
        self.assertGreaterEqual(sum(v["expect"] == "invalid" for v in VECTORS["inventories"]), 10)
        for vector in VECTORS["inventories"]:
            with self.subTest(vector["name"]):
                raw = base64.b64decode(vector["envelopeBase64"])
                if vector["expect"] == "valid":
                    self.verify(raw)
                else:
                    with self.assertRaises(ValueError):
                        self.verify(raw)

    def test_status_vectors(self):
        self.assertEqual(VECTORS["observedPrecedence"], list(history.OBSERVED))
        self.assertEqual(VECTORS["sourcePrecedence"], list(history.SOURCE))
        for case in VECTORS["statuses"]:
            with self.subTest(case["name"]):
                checkpoint = VectorCheckpoint(case)
                row = checkpoint.entry("rooms/general", "x.txt", case["commitments"])
                got = {k: row[k] for k in ("observed", "source", "needsAttention", "neutral")}
                self.assertEqual(got, case["expect"])


if __name__ == "__main__":
    unittest.main()
