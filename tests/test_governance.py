import os, sys, json, shutil, tempfile, unittest, subprocess
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from magnemo.vault import Vault, Note
from magnemo.governance import Governance
from magnemo.search import Index

class TestGovernance(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.v = Vault(self.dir); self.v.init()
        self.g = Governance(self.v)

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_governed_write_lifecycle(self):
        # agent writes -> staged, invisible to search
        n = self.g.agent_write(title="Kwik Lube month-end spike",
            body="Volumes spike ~35% in the last week of each month. 7 occurrences.",
            partition="ops", store="knowledge", author="ops-agent", source="run#1847")
        self.assertEqual(n.status, "staged")
        idx = Index(self.v)
        self.assertEqual(idx.search("month-end spike")["results"], [])  # staged excluded
        # human promotes -> canonical, searchable, ledgered
        self.g.promote(n.id, reviewer="founder", reason="pattern confirmed")
        hits = idx.search("month-end spike")["results"]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["id"], n.id)
        rate, count = self.g.ledger.pass_rate("memory.promote")
        self.assertEqual((rate, count), (1.0, 1))

    def test_rejection_teaches(self):
        n = self.g.agent_write(title="Bad guess", body="Unverified claim.",
            partition="ops", store="knowledge", author="ops-agent", source="run#1")
        self.g.reject(n.id, reviewer="founder", reason="no evidence")
        n2 = self.v.read(n.id)
        self.assertEqual(n2.status, "rejected")
        self.assertIn("REJECTED", n2.body)
        self.assertEqual(Index(self.v).search("unverified")["results"], [])
        rate, count = self.g.ledger.pass_rate("memory.promote")
        self.assertEqual(count, 1); self.assertEqual(rate, 0.0)

    def test_supersession_archives_old(self):
        a = self.g.agent_write(title="Rate card v1", body="Rate is $40/bin.",
            partition="ops", store="knowledge", author="fin-agent", source="run#2")
        self.g.promote(a.id, "founder")
        b = self.g.agent_write(title="Rate card v2", body="Rate is $45/bin from Sept.",
            partition="ops", store="knowledge", author="fin-agent", source="run#3",
            supersedes=a.id)
        self.g.promote(b.id, "founder")
        old = self.v.read(a.id)
        self.assertEqual(old.status, "archived")
        self.assertIn(b.id, old.body)  # forward link
        hits = Index(self.v).search("rate bin")["results"]
        self.assertEqual([h["id"] for h in hits], [b.id])  # archived excluded
        prov = self.g.provenance(b.id)
        self.assertEqual(prov["supersession_chain"][0]["id"], a.id)

    def test_partition_and_store_validation(self):
        with self.assertRaises(ValueError):
            self.g.agent_write(title="x", body="y", partition="ops",
                store="debt", author="a", source="s")  # debt is dev-only

    def test_frontmatter_roundtrip(self):
        n = Note(id="t1", title="T: colons, — dashes", author="a", written="2026-01-01T00:00:00Z",
                 source="s", status="staged", partition="dev", store="knowledge",
                 body="Line one.\n\nLine two with # hash.")
        n2 = Note.from_markdown(n.to_markdown())
        self.assertEqual(n2.title, n.title)
        self.assertEqual(n2.body, n.body)

    def test_telos_yield_moves_ranking(self):
        a = self.g.agent_write(title="Route note A", body="Langley route timing pattern alpha.",
            partition="ops", store="knowledge", author="ops", source="r1")
        b = self.g.agent_write(title="Route note B", body="Langley route timing pattern beta.",
            partition="ops", store="knowledge", author="ops", source="r2")
        self.g.promote(a.id, "founder"); self.g.promote(b.id, "founder")
        idx = Index(self.v)
        out = idx.search("Langley route timing", agent="ops")
        rid = out["rid"]
        # outcome: this retrieval led to an APPROVED action -> both credited
        self.g.record_outcome(rid, "approved", "founder")
        # now debit B twice via targeted retrievals to invert ranking
        out_b = idx.search("beta", agent="ops")
        self.g.record_outcome(out_b["rid"], "denied", "founder")
        self.g.record_outcome(out_b["rid"], "denied", "founder")
        ranked = idx.search("Langley route timing")["results"]
        self.assertEqual(ranked[0]["id"], a.id)  # A outranks B on yield
        na = self.v.read(a.id); nb = self.v.read(b.id)
        self.assertEqual((na.yield_w, na.yield_l), (1, 0))
        self.assertEqual((nb.yield_w, nb.yield_l), (1, 2))

    def test_taint_is_hereditary_and_penalized(self):
        x = self.g.agent_write(title="Claim from inbound email",
            body="Vendor says rate should be $99.",
            partition="ops", store="knowledge", author="ops", source="email#7",
            taint="inbound-email")
        self.g.promote(x.id, "founder")  # promoted but still tainted
        y = self.g.agent_write(title="Derived pricing thought",
            body="Based on vendor claim, consider $99 tier.",
            partition="ops", store="knowledge", author="ops", source="r9",
            supersedes=x.id)
        self.assertEqual(y.taint, "inbound-email")  # inherited, not laundered
        self.g.promote(y.id, "founder")
        res = Index(self.v).search("vendor rate")["results"]
        self.assertTrue(all("taint" in r for r in res))
        clean = Index(self.v).search("vendor rate", include_tainted=False)["results"]
        self.assertEqual(clean, [])
        self.g.clear_taint(y.id, "founder", "verified by contract")
        self.assertEqual(self.v.read(y.id).taint, "")

    def test_char_budget_bounds_payload(self):
        n = self.g.agent_write(title="Long note", body="word " * 500,
            partition="ops", store="knowledge", author="ops", source="r")
        self.g.promote(n.id, "founder")
        out = Index(self.v).search("word", max_chars=100)
        self.assertLessEqual(len(out["results"][0]["snippet"]), 101)  # 100 + ellipsis
        self.assertLess(out["payload_chars"], 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
