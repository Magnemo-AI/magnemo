"""P-02 B3 — the Gate Map: every wall, derived from config + grant ledger."""
import json, os, shutil, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from magnemo.vault import Vault
from magnemo.governance import Governance
from magnemo.config import load_config, DEFAULTS
from magnemo import trust, grants, gates, bootpack

F = "The Founder"


def day(n):
    return f"2026-08-{n:02d}T00:00:00Z"


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.v = Vault(self.dir); self.v.init()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def by_name(self, as_of=None):
        return {g["name"]: g for g in gates.gate_map(self.v, as_of or day(1))}


class TestDefinitions(unittest.TestCase):
    def test_defaults_cover_every_class_and_lock_human_only(self):
        defs = gates.definitions(DEFAULTS)
        self.assertEqual({d["class"] for d in defs}, set(trust.CLASSES))
        for d in defs:
            if d["class"] in trust.HUMAN_ONLY:
                self.assertEqual(d["state"], "locked")
        names = [d["name"] for d in defs]
        self.assertEqual(names, ["retrieve", "staging", "main", "gate-code", "canon", "publish"])

    def test_config_cannot_open_a_human_only_gate(self):
        cfg = json.loads(json.dumps(DEFAULTS))
        for g in cfg["trust"]["gates"]:
            if g["name"] in ("canon", "publish"):
                g["state"] = "open"
        for d in gates.definitions(cfg):
            if d["name"] in ("canon", "publish"):
                self.assertEqual(d["state"], "locked")


class TestDerivedState(Base):
    def test_fresh_vault_main_is_locked_until_delegated(self):
        m = self.by_name()
        self.assertEqual(m["main"]["state"], "locked"); self.assertEqual(m["main"]["last_change"], "genesis")
        self.assertEqual(m["retrieve"]["state"], "open"); self.assertEqual(m["staging"]["state"], "open")
        self.assertEqual(m["canon"]["state"], "locked"); self.assertTrue(m["canon"]["human_only"])
        grants.issue(self.v, "bot", ["merge-code"], 2, by=F, ref="P-01", scope="repo", when=day(2))
        m = self.by_name(day(2))
        self.assertEqual(m["main"]["state"], "delegated"); self.assertEqual(m["main"]["last_change"], day(2))
        self.assertEqual(m["main"]["delegations"], [{"grant_id": "G0001", "grantee": "bot", "level": 2,
                                                     "scope": "repo", "ref": "P-01", "kind": "standing"}])
        # before the grant existed, the map says locked — as_of is honoured
        self.assertEqual(self.by_name(day(1))["main"]["state"], "locked")

    def test_revocation_relocks_and_keeps_history(self):
        grants.issue(self.v, "bot", ["merge-code"], 2, by=F, when=day(2))
        grants.revoke(self.v, "G0001", by=F, reason="one sentence", when=day(3))
        m = self.by_name(day(3))
        self.assertEqual(m["main"]["state"], "locked"); self.assertEqual(m["main"]["delegations"], [])
        self.assertEqual(m["main"]["last_change"], day(3))
        self.assertEqual([h["state"] for h in m["main"]["grant_history"]], ["revoked"])

    def test_locked_gate_is_not_opened_by_a_grant_on_its_class(self):
        grants.issue(self.v, "bot", ["merge-code"], 3, by=F, when=day(2))
        m = self.by_name(day(2))
        self.assertEqual(m["gate-code"]["state"], "locked")
        self.assertEqual(m["gate-code"]["delegations"], [])
        self.assertEqual(len(m["gate-code"]["grant_history"]), 1)   # visible, not effective
        self.assertEqual(m["main"]["state"], "delegated")

    def test_grants_to_humans_do_not_count_as_delegation(self):
        grants.issue(self.v, "founder", ["merge-code"], 4, by=F, when=day(2))
        self.assertEqual(self.by_name(day(2))["main"]["state"], "locked")

    def test_human_only_gates_never_delegate(self):
        grants.issue(self.v, "bot", ["promote-canon", "publish"], 1, by=F, when=day(2))
        m = self.by_name(day(2))
        self.assertEqual(m["canon"]["state"], "locked"); self.assertEqual(m["publish"]["state"], "locked")
        self.assertEqual(m["canon"]["delegations"], [])

    def test_render_and_json_shape(self):
        grants.issue(self.v, "bot", ["merge-code"], 2, by=F, ref="P-01", when=day(2))
        gm = gates.gate_map(self.v, day(2))
        out = gates.render(gm, day(2))
        self.assertIn("delegated", out); self.assertIn("P-01", out); self.assertIn("keyholder-only", out)
        for k in ("name", "class", "state", "keyholder", "last_change", "delegations", "grant_history"):
            self.assertIn(k, gm[0])
        json.dumps(gm)


class TestBootPackGates(Base):
    def test_gates_section_sits_after_charter_before_canon(self):
        pack = bootpack.generate(self.v)
        self.assertLess(pack.index("## THE CHARTER"), pack.index("## GATES"))
        self.assertLess(pack.index("## GATES"), pack.index("## CANON DIGEST"))
        for name in ("retrieve", "staging", "main", "gate-code", "canon", "publish"):
            self.assertIn(f"**{name}**", pack)
        self.assertIn("keyholder-only forever (#81)", pack)

    def test_gates_section_reads_the_ledger_at_ledger_time_and_stays_pure(self):
        grants.issue(self.v, "bot", ["merge-code"], 2, by=F, ref="P-01", scope="repo", when=day(2))
        p1 = bootpack.generate(self.v); p2 = bootpack.generate(self.v)
        self.assertEqual(p1, p2)
        self.assertIn(f"ledger time {day(2)}", p1)
        self.assertIn("DELEGATED", p1); self.assertIn("delegated to `bot` at L2 (G0001, P-01) — repo", p1)
        grants.revoke(self.v, "G0001", by=F, reason="done", when=day(3))
        p3 = bootpack.generate(self.v)
        self.assertIn(f"ledger time {day(3)}", p3); self.assertNotIn("DELEGATED", p3)

    def test_ledger_tail_count_unchanged_by_gates_section(self):
        g = Governance(self.v)
        n = g.agent_write(title="t", body="b", partition="dev", store="knowledge", author="a", source="s")
        g.promote(n.id, F)
        pack = bootpack.generate(self.v)
        self.assertIn("## LEDGER TAIL (last 2 of 2)", pack)   # promote + derived trust event


if __name__ == "__main__":
    unittest.main()
