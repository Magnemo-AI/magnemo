import json, os, shutil, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from magnemo.vault import Vault
from magnemo.governance import Governance
from magnemo.search import Index
from magnemo import bootpack, foresight


class TestForesightCounters(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.v = Vault(self.dir); self.v.init()
        self.g = Governance(self.v)
        n = self.g.agent_write(title="Kwik Lube month-end spike",
            body="Volumes spike in the last week of each month.",
            partition="ops", store="knowledge", author="ops-agent",
            source="run#1847", impact="money")
        self.g.promote(n.id, "founder")

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_retrieval_logs_bytes_and_token_estimate(self):
        out = Index(self.v).search("month-end spike")
        self.assertGreater(out["payload_bytes"], 0)
        es = [e for e in foresight.entries(self.v) if e["kind"] == "retrieval"]
        self.assertEqual(len(es), 1)
        e = es[0]
        self.assertEqual(e["bytes"], out["payload_bytes"])
        self.assertEqual(e["tokens_est"], round(e["bytes"] / foresight.BYTES_PER_TOKEN))
        self.assertEqual(e["meta"]["rid"], out["rid"])
        self.assertEqual(e["meta"]["results"], 1)

    def test_empty_retrieval_still_measured(self):
        Index(self.v).search("zebra quantum nothing")
        es = [e for e in foresight.entries(self.v) if e["kind"] == "retrieval"]
        self.assertEqual(len(es), 1)
        self.assertEqual(es[0]["meta"]["results"], 0)

    def test_bootpack_write_logs_actual_file_bytes(self):
        path, nbytes = bootpack.write(self.v, cls="partner")
        es = [e for e in foresight.entries(self.v) if e["kind"] == "bootpack"]
        self.assertEqual(len(es), 1)
        self.assertEqual(es[0]["bytes"], nbytes)
        self.assertEqual(es[0]["bytes"], os.path.getsize(path))
        self.assertEqual(es[0]["meta"]["class"], "partner")

    def test_costs_file_append_only(self):
        Index(self.v).search("month-end")
        path = os.path.join(self.dir, "_ledger", "costs.jsonl")
        with open(path) as f:
            first = f.readline()
        bootpack.write(self.v)
        with open(path) as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], first)

    def test_summary_states_baseline(self):
        self.assertIn("No cost events", foresight.summary_table(self.v))
        Index(self.v).search("month-end spike")
        Index(self.v).search("volumes")
        bootpack.write(self.v)
        t = foresight.summary_table(self.v)
        self.assertIn("BASELINE", t)
        self.assertIn("retrieval: 2 events", t)
        self.assertIn("bootpack: 1 events", t)
        self.assertIn("mean ~", t)
        self.assertIn(f"bytes/{foresight.BYTES_PER_TOKEN}", t)
        self.assertIn("ALL", t)

    def test_counter_failure_never_breaks_serving(self):
        # point the ledger dir at a file so the append fails: log_cost must
        # swallow it (a failed counter must not fail a retrieval)
        shutil.rmtree(os.path.join(self.dir, "_ledger"))
        with open(os.path.join(self.dir, "_ledger"), "w") as f:
            f.write("not a dir")
        e = foresight.log_cost(self.v, "retrieval", 123)  # must not raise
        self.assertEqual(e["tokens_est"], round(123 / foresight.BYTES_PER_TOKEN))
        self.assertEqual(foresight.entries(self.v), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
