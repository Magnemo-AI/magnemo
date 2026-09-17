"""P-02 B2 — grants as data. P-01 is a record, not prose."""
import json, os, shutil, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from magnemo.vault import Vault
from magnemo.governance import TrustLedger
from magnemo.config import load_config
from magnemo import trust, grants

F = "The Founder"


def day(n):
    return f"2026-08-{n:02d}T00:00:00Z"


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.v = Vault(self.dir); self.v.init()

    def tearDown(self):
        shutil.rmtree(self.dir)


class TestIssue(Base):
    def test_grant_is_a_structured_append_only_record(self):
        g = grants.issue(self.v, "bot", ["merge-code"], 2, by=F, scope="repo X",
                         conditions=["tests green"], ref="P-01", when=day(1), reason="standing order")
        self.assertEqual(g["grant_id"], "G0001")
        es = TrustLedger(self.v).entries()
        self.assertEqual(len(es), 1)
        e = es[0]
        self.assertEqual(e["action_class"], "trust.grant"); self.assertEqual(e["verdict"], "issued")
        self.assertEqual(e["actor"], F); self.assertEqual(e["subject"], "bot"); self.assertEqual(e["ts"], day(1))
        self.assertTrue(e["recorded_at"])
        self.assertEqual(e["grant"]["classes"], ["merge-code"]); self.assertEqual(e["grant"]["level"], 2)
        self.assertEqual(e["grant"]["conditions"], ["tests green"]); self.assertEqual(e["grant"]["ref"], "P-01")
        g2 = grants.issue(self.v, "bot", ["stage"], 3, by=F)
        self.assertEqual(g2["grant_id"], "G0002")

    def test_only_keyholders_grant_or_revoke(self):
        with self.assertRaises(PermissionError):
            grants.issue(self.v, "bot", ["merge-code"], 2, by="some-agent")
        grants.issue(self.v, "bot", ["merge-code"], 2, by=F)
        with self.assertRaises(PermissionError):
            grants.revoke(self.v, "G0001", by="some-agent", reason="x")
        self.assertEqual(len(grants.records(self.v)), 1)

    def test_refusals_touch_nothing(self):
        for kw in (dict(grantee="", classes=["stage"], level=2),
                   dict(grantee="bot", classes=[], level=2),
                   dict(grantee="bot", classes=["nope"], level=2),
                   dict(grantee="bot", classes=["stage"], level=9),
                   dict(grantee="bot", classes=["stage"], level=2, kind="forever")):
            with self.assertRaises(ValueError):
                grants.issue(self.v, by=F, **kw)
        self.assertEqual(TrustLedger(self.v).entries(), [])

    def test_human_only_classes_cannot_be_granted_above_L1_to_non_humans(self):
        for k in trust.HUMAN_ONLY:
            with self.assertRaises(PermissionError):
                grants.issue(self.v, "bot", [k], 2, by=F)
            grants.issue(self.v, "bot", [k], 1, by=F)          # propose is fine
        with self.assertRaises(PermissionError):
            grants.issue(self.v, "bot", ["stage"], 4, by=F)  # L4 is held by keyholders only
        grants.issue(self.v, "founder", ["publish"], 4, by=F)   # a declared keyholder may hold the key

    def test_hand_edited_ledger_cannot_smuggle_a_key(self):
        # write a forged L3 publish grant straight into the file, bypassing issue()
        TrustLedger(self.v).record("trust.grant", "issued", F, "bot", "forged", ts=day(1),
                                   grant={"grant_id": "G9999", "grantee": "bot", "classes": ["publish", "stage"],
                                          "level": 3, "kind": "standing", "issued": day(1), "grantor": F,
                                          "scope": "", "conditions": [], "ref": "", "expires": ""})
        self.assertEqual(grants.granted_level(self.v, "bot", "publish", as_of=day(2))["level"], 1)
        self.assertEqual(grants.granted_level(self.v, "bot", "stage", as_of=day(2))["level"], 3)
        self.assertEqual(trust.effective_level(self.v, "bot", "publish", as_of=day(2))["effective_level"], 1)


class TestLifecycle(Base):
    def test_states_active_revoked_expired_pending(self):
        grants.issue(self.v, "bot", ["merge-code"], 2, by=F, when=day(1))
        grants.issue(self.v, "bot", ["stage"], 3, by=F, when=day(1), expires=day(5))
        grants.issue(self.v, "bot", ["read"], 3, by=F, when=day(9))
        grants.revoke(self.v, "G0001", by=F, reason="one sentence", when=day(3))
        st = {g["grant_id"]: g["state"] for g in grants.status(self.v, as_of=day(2))}
        self.assertEqual(st, {"G0001": "active", "G0002": "active", "G0003": "pending"})
        st = {g["grant_id"]: g["state"] for g in grants.status(self.v, as_of=day(6))}
        self.assertEqual(st, {"G0001": "revoked", "G0002": "expired", "G0003": "pending"})
        st = {g["grant_id"]: g["state"] for g in grants.status(self.v, as_of=day(10))}
        self.assertEqual(st["G0003"], "active")
        rv = [g for g in grants.status(self.v, as_of=day(10)) if g["grant_id"] == "G0001"][0]
        self.assertEqual(rv["revoke_reason"], "one sentence"); self.assertEqual(rv["revoked"], day(3))

    def test_revoke_requires_reason_and_existing_unrevoked_grant(self):
        with self.assertRaises(FileNotFoundError):
            grants.revoke(self.v, "G0001", by=F, reason="x")
        grants.issue(self.v, "bot", ["merge-code"], 2, by=F)
        with self.assertRaises(ValueError):
            grants.revoke(self.v, "G0001", by=F, reason="")
        grants.revoke(self.v, "G0001", by=F, reason="done")
        with self.assertRaises(ValueError):
            grants.revoke(self.v, "G0001", by=F, reason="again")

    def test_one_time_grant_is_consumed_by_the_event_that_cites_it(self):
        grants.issue(self.v, "bot", ["merge-code"], 2, by=F, kind="one-time", ref="#42", when=day(1))
        self.assertEqual(grants.active(self.v, "bot", "merge-code", as_of=day(2))[0]["grant_id"], "G0001")
        trust.record(self.v, "bot", "merge-code", "success", by=F, ref="#42", grant="G0001", when=day(2))
        self.assertEqual(grants.active(self.v, "bot", "merge-code", as_of=day(3)), [])
        self.assertEqual(grants.status(self.v, as_of=day(3))[0]["state"], "consumed")
        # a standing grant is not consumed by citation
        grants.issue(self.v, "bot", ["merge-code"], 2, by=F, kind="standing", when=day(4))
        trust.record(self.v, "bot", "merge-code", "success", by=F, grant="G0002", when=day(5))
        self.assertEqual(len(grants.active(self.v, "bot", "merge-code", as_of=day(6))), 1)


class TestEffective(Base):
    def test_effective_is_min_of_computed_and_granted(self):
        # earned L3 (15 same-day successes), granted only the default L1 → effective L1
        for _ in range(15):
            trust.record(self.v, "bot", "merge-code", "success", by=F, when=day(1))
        r = trust.effective_level(self.v, "bot", "merge-code", as_of=day(1))
        self.assertEqual((r["computed_level"], r["granted_level"], r["effective_level"]), (3, 1, 1))
        grants.issue(self.v, "bot", ["merge-code"], 2, by=F, when=day(1))
        r = trust.effective_level(self.v, "bot", "merge-code", as_of=day(1))
        self.assertEqual((r["computed_level"], r["granted_level"], r["effective_level"]), (3, 2, 2))
        self.assertEqual(r["grants"][0]["grant_id"], "G0001")
        # granted L3 but nothing earned → still L1
        grants.issue(self.v, "newbie", ["merge-code"], 3, by=F, when=day(1))
        r = trust.effective_level(self.v, "newbie", "merge-code", as_of=day(1))
        self.assertEqual((r["computed_level"], r["granted_level"], r["effective_level"]), (1, 3, 1))

    def test_revocation_drops_effective_immediately(self):
        for _ in range(5):
            trust.record(self.v, "bot", "merge-code", "success", by=F, when=day(1))
        grants.issue(self.v, "bot", ["merge-code"], 2, by=F, when=day(1))
        self.assertEqual(trust.effective_level(self.v, "bot", "merge-code", as_of=day(1))["effective_level"], 2)
        grants.revoke(self.v, "G0001", by=F, reason="one sentence", when=day(1))
        self.assertEqual(trust.effective_level(self.v, "bot", "merge-code", as_of=day(1))["effective_level"], 1)

    def test_a_violation_beats_any_grant(self):
        grants.issue(self.v, "bot", ["merge-code"], 3, by=F, when=day(1))
        for _ in range(15):
            trust.record(self.v, "bot", "merge-code", "success", by=F, when=day(1))
        trust.record(self.v, "bot", "merge-code", "violation", by=F, when=day(2))
        r = trust.effective_level(self.v, "bot", "merge-code", as_of=day(2))
        self.assertEqual(r["effective_level"], 0); self.assertEqual(r["granted_level"], 3)


@unittest.skipUnless(os.path.isdir(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vault")), "the repo's dogfood vault is private — not in the public tree")
class TestGenesis(unittest.TestCase):
    """The repo vault carries P-01 as G0001 — the genesis grant."""
    def test_genesis_grant_on_record(self):
        root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vault")
        v = Vault(root)
        gs = [g for g in grants.status(v, as_of="2026-08-21T00:00:00Z") if g["ref"] == "P-01"]
        self.assertEqual(len(gs), 1)
        g = gs[0]
        self.assertEqual(g["grant_id"], "G0001"); self.assertEqual(g["grantee"], "claude-worker")
        self.assertEqual(g["classes"], ["merge-code"]); self.assertEqual(g["level"], 2)
        self.assertEqual(g["kind"], "standing"); self.assertEqual(g["grantor"], "The Founder")
        self.assertEqual(g["issued"], "2026-08-20T00:00:00Z"); self.assertEqual(g["state"], "active")
        self.assertEqual(len(g["conditions"]), 5)
        self.assertTrue(any("ceiling" in c for c in g["conditions"]))

    def test_render_lists_conditions(self):
        root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vault")
        out = grants.render(grants.status(Vault(root), as_of="2026-08-21T00:00:00Z"))
        self.assertIn("G0001", out); self.assertIn("P-01", out); self.assertIn("condition:", out)


if __name__ == "__main__":
    unittest.main()
