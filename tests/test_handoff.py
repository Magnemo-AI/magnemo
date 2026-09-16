import json, os, shutil, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from magnemo.vault import Vault
from magnemo import handoff


class TestHandoff(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.v = Vault(self.dir); self.v.init()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_record_appends_structured_entry(self):
        e = handoff.record(self.v, 91, "planned", cut="deferred B4", actor="founder")
        path = os.path.join(self.dir, "_ledger", "handoffs.jsonl")
        with open(path) as f:
            lines = f.read().strip().splitlines()
        self.assertEqual(len(lines), 1)
        on_disk = json.loads(lines[0])
        self.assertEqual(on_disk, e)
        self.assertEqual(on_disk["usage_pct"], 91.0)
        self.assertEqual(on_disk["trigger"], "planned")
        self.assertEqual(on_disk["cut"], "deferred B4")
        self.assertEqual(on_disk["actor"], "founder")
        self.assertTrue(on_disk["ts"])
        self.assertTrue(on_disk["recorded_at"])

    def test_append_only_earlier_entries_untouched(self):
        handoff.record(self.v, 88, "planned")
        path = os.path.join(self.dir, "_ledger", "handoffs.jsonl")
        with open(path) as f:
            first = f.readline()
        handoff.record(self.v, 97, "wall")
        with open(path) as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], first)  # append-only: line 1 byte-identical
        es = handoff.entries(self.v)
        self.assertEqual([e["usage_pct"] for e in es], [88.0, 97.0])

    def test_record_stages_provenance_complete_note(self):
        e = handoff.record(self.v, 92, "compaction", cut="dropped scratch",
                           actor="build-agent")
        n = self.v.read(e["note_id"])
        self.assertEqual(n.status, "staged")
        self.assertEqual(n.author, "build-agent")
        self.assertTrue(n.written)
        self.assertTrue(n.source)
        self.assertIn("handoff", n.tags)
        self.assertIn("92%", n.body)
        self.assertIn("compaction", n.body)
        self.assertIn("dropped scratch", n.body)
        self.assertGreaterEqual(n.salience, 0.0)  # KAIROS scored at stage time

    def test_validation(self):
        with self.assertRaises(ValueError):
            handoff.record(self.v, 91, "panic")
        with self.assertRaises(ValueError):
            handoff.record(self.v, 140, "wall")
        with self.assertRaises(ValueError):
            handoff.record(self.v, -3, "wall")
        with self.assertRaises(ValueError):
            handoff.record(self.v, "lots", "wall")
        self.assertEqual(handoff.entries(self.v), [])  # nothing recorded

    def test_when_override_records_historical_boundary_honestly(self):
        e = handoff.record(self.v, 98, "wall", actor="founder",
                           when="2026-08-13", cut="",
                           source="boundary-telemetry-seed (operator-confirmed)")
        self.assertEqual(e["ts"], "2026-08-13")
        self.assertNotEqual(e["ts"], e["recorded_at"])  # honesty: both kept

    def test_report_table_renders_all(self):
        self.assertIn("No handoffs", handoff.report_table(self.v))
        handoff.record(self.v, 98, "wall", when="2026-08-13", actor="founder")
        handoff.record(self.v, 88, "planned", cut="stood down early")
        t = handoff.report_table(self.v)
        self.assertIn("2026-08-13", t)
        self.assertIn("98%", t)
        self.assertIn("wall", t)
        self.assertIn("88%", t)
        self.assertIn("stood down early", t)
        self.assertIn("2 boundary(ies)", t)
        self.assertIn("1 hit the wall", t)
        self.assertIn("~90%", t)


if __name__ == "__main__":
    unittest.main(verbosity=2)
