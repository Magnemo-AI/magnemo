"""P-02 B1 — the arithmetic of earned trust. Every number here is hand-checkable."""
import json, os, shutil, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from magnemo.vault import Vault
from magnemo.governance import Governance, TrustLedger
from magnemo.config import load_config, DEFAULTS
from magnemo import trust

T0 = "2026-08-01T00:00:00Z"


def day(n):
    return f"2026-08-{n:02d}T00:00:00Z"


class TrustBase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.v = Vault(self.dir); self.v.init()
        self.cfg = load_config(self.dir)

    def tearDown(self):
        shutil.rmtree(self.dir)

    def rec(self, actor, klass, kind, when, by="founder", **kw):
        return trust.record(self.v, actor, klass, kind, by=by, when=when, **kw)


class TestLedgerEvents(TrustBase):
    def test_record_is_append_only_with_base_keys_intact(self):
        self.rec("bot", "merge-code", "success", day(1), ref="#7")
        path = os.path.join(self.dir, "_ledger", "trust_ledger.jsonl")
        with open(path) as f:
            first = f.readline()
        e = json.loads(first)
        for k in ("ts", "action_class", "verdict", "actor", "subject", "detail"):
            self.assertIn(k, e)            # the six base keys the whole vault reads
        self.assertEqual(e["action_class"], trust.TRUST_EVENT)
        self.assertEqual(e["subject"], "bot"); self.assertEqual(e["actor"], "founder")
        self.assertEqual(e["class"], "merge-code"); self.assertEqual(e["kind"], "success")
        self.assertEqual(e["ref"], "#7"); self.assertEqual(e["ts"], day(1))
        self.assertTrue(e["recorded_at"])   # backdated events keep the real clock
        self.rec("bot", "merge-code", "success", day(2))
        with open(path) as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 2); self.assertEqual(lines[0], first)

    def test_refusals_touch_nothing(self):
        for bad in (dict(actor="bot", klass="nope", kind="success"),
                    dict(actor="bot", klass="stage", kind="nope"),
                    dict(actor="", klass="stage", kind="success")):
            with self.assertRaises(ValueError):
                trust.record(self.v, by="founder", **bad)
        with self.assertRaises(ValueError):
            trust.record(self.v, "bot", "stage", "success", by="")
        self.assertEqual(TrustLedger(self.v).entries(), [])

    def test_old_ledger_readers_still_work(self):
        self.rec("bot", "stage", "success", day(1))
        L = TrustLedger(self.v)
        self.assertEqual(L.entries("memory.promote"), [])
        self.assertEqual(L.pass_rate("memory.promote"), (0.0, 0))
        self.assertEqual(len(L.entries()), 1)


class TestScoreMath(TrustBase):
    def test_fresh_actor_levels_are_the_class_floors(self):
        card = trust.scorecard(self.v, "newbie", as_of=day(10))
        lv = trust.levels_summary(card)
        self.assertEqual(lv, {"read": 2, "stage": 2, "merge-code": 1,
                              "promote-canon": 1, "publish": 1})
        for k in trust.CLASSES:
            self.assertEqual(card["classes"][k]["score"], 0.0)

    def test_score_is_weighted_sum_with_half_life_decay(self):
        # one success (1.0) 90 days old → 0.5 ; one verified (2.0) today → 2.0
        self.rec("bot", "merge-code", "success", "2026-05-03T00:00:00Z")   # 90 days before Aug 1
        self.rec("bot", "merge-code", "verified", T0)
        c = trust.computed(self.v, "bot", "merge-code", as_of=T0)
        self.assertEqual(c["score"], 2.5)
        self.assertEqual(c["components"]["success"], {"count": 1, "raw": 1.0, "decayed": 0.5})
        self.assertEqual(c["components"]["verified"], {"count": 1, "raw": 2.0, "decayed": 2.0})
        self.assertEqual(c["computed_level"], 1)                   # 2.5 < 5

    def test_stairs_thresholds_are_exact(self):
        for i in range(4):
            self.rec("bot", "merge-code", "success", day(1))
        self.assertEqual(trust.computed(self.v, "bot", "merge-code", as_of=day(1))["computed_level"], 1)  # 4.0 < 5
        self.rec("bot", "merge-code", "success", day(1))
        c = trust.computed(self.v, "bot", "merge-code", as_of=day(1))
        self.assertEqual(c["score"], 5.0); self.assertEqual(c["computed_level"], 2)          # 5.0 ≥ 5 exactly
        # the same five, one day later, have decayed below the stair: 5 × 0.5^(1/90) < 5
        self.assertEqual(trust.computed(self.v, "bot", "merge-code", as_of=day(2))["computed_level"], 1)
        for i in range(10):
            self.rec("bot", "merge-code", "success", day(1))
        c = trust.computed(self.v, "bot", "merge-code", as_of=day(1))
        self.assertEqual(c["score"], 15.0); self.assertEqual(c["computed_level"], 3)

    def test_negative_events_subtract_and_can_drop_below_propose(self):
        self.rec("bot", "merge-code", "success", day(1))
        self.rec("bot", "merge-code", "surprise", day(2))
        c = trust.computed(self.v, "bot", "merge-code", as_of=day(2))
        self.assertLess(c["score"], 0); self.assertEqual(c["computed_level"], 0)
        # floors hold for read/stage even when the score is negative (walls, not trust, govern them)
        self.rec("bot", "stage", "surprise", day(2))
        self.assertEqual(trust.computed(self.v, "bot", "stage", as_of=day(2))["computed_level"], 2)

    def test_inactivity_decays_toward_zero_never_negative(self):
        self.rec("bot", "merge-code", "success", day(1))
        s1 = trust.computed(self.v, "bot", "merge-code", as_of=day(1))["score"]
        s2 = trust.computed(self.v, "bot", "merge-code", as_of="2027-08-01T00:00:00Z")["score"]
        self.assertEqual(s1, 1.0); self.assertLess(s2, 0.07); self.assertGreater(s2, 0.0)

    def test_future_events_do_not_count_yet(self):
        self.rec("bot", "merge-code", "success", day(20))
        self.assertEqual(trust.computed(self.v, "bot", "merge-code", as_of=day(10))["score"], 0.0)

    def test_determinism_same_ledger_same_numbers(self):
        for i in range(1, 8):
            self.rec("bot", "stage", "success", day(i))
        a = trust.scorecard(self.v, "bot", as_of=day(9))
        b = trust.scorecard(self.v, "bot", as_of=day(9))
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))


class TestElevator(TrustBase):
    def test_violation_freezes_at_L0_and_discards_history(self):
        for i in range(1, 17):
            self.rec("bot", "merge-code", "success", day(i))
        self.assertEqual(trust.computed(self.v, "bot", "merge-code", as_of=day(16))["computed_level"], 3)
        self.rec("bot", "merge-code", "violation", day(17), reason="merged a gate change")
        c = trust.computed(self.v, "bot", "merge-code", as_of=day(17))
        self.assertTrue(c["frozen"]); self.assertEqual(c["computed_level"], 0)
        self.assertEqual(c["score"], 0.0); self.assertEqual(c["n_events"], 0)
        # positive events after the violation accrue, but the freeze holds
        self.rec("bot", "merge-code", "success", day(18))
        c = trust.computed(self.v, "bot", "merge-code", as_of=day(18))
        self.assertEqual(c["score"], 1.0); self.assertEqual(c["computed_level"], 0)

    def test_reinstate_lifts_freeze_but_not_the_discarded_history(self):
        for i in range(1, 17):
            self.rec("bot", "merge-code", "success", day(i))
        self.rec("bot", "merge-code", "violation", day(17))
        self.rec("bot", "merge-code", "reinstate", day(19), reason="postmortem accepted")
        c = trust.computed(self.v, "bot", "merge-code", as_of=day(19))
        self.assertFalse(c["frozen"]); self.assertEqual(c["score"], 0.0)
        self.assertEqual(c["computed_level"], 1)    # back at propose — climbing the stairs again
        # violation is per-class: stage untouched
        self.assertEqual(trust.computed(self.v, "bot", "stage", as_of=day(19))["frozen"], False)

    def test_violation_after_reinstate_freezes_again(self):
        self.rec("bot", "merge-code", "violation", day(1))
        self.rec("bot", "merge-code", "reinstate", day(2))
        self.rec("bot", "merge-code", "violation", day(3))
        self.assertTrue(trust.computed(self.v, "bot", "merge-code", as_of=day(4))["frozen"])


class TestHumanOnlyCaps(TrustBase):
    def test_no_score_lifts_promote_or_publish_above_propose(self):
        for i in range(1, 30):
            self.rec("bot", "promote-canon", "verified", day(i) if i < 29 else day(28))
            self.rec("bot", "publish", "verified", day(i) if i < 29 else day(28))
        card = trust.scorecard(self.v, "bot", as_of=day(28))
        self.assertGreater(card["classes"]["promote-canon"]["score"], 15)
        self.assertEqual(card["classes"]["promote-canon"]["effective_level"], 1)
        self.assertEqual(card["classes"]["publish"]["effective_level"], 1)

    def test_config_cannot_lift_the_human_only_cap(self):
        cfg = load_config(self.dir)
        cfg["trust"]["classes"]["publish"]["ceiling"] = 3
        cfg["trust"]["classes"]["publish"]["floor"] = 3
        cfg["trust"]["classes"]["publish"]["default_grant"] = 3
        c = trust.effective_level(self.v, "bot", "publish", as_of=day(1), cfg=cfg)
        self.assertEqual(c["computed_level"], 1); self.assertEqual(c["effective_level"], 1)

    def test_declared_humans_are_keyholders_not_scored(self):
        card = trust.scorecard(self.v, "The Founder", as_of=day(1))
        self.assertTrue(card["human"])
        self.assertEqual(set(trust.levels_summary(card).values()), {4})
        self.assertEqual(trust.scorecard(self.v, "bot", as_of=day(1))["human"], False)


class TestDerivedEvents(TrustBase):
    def test_promote_and_reject_score_the_author_in_stage(self):
        g = Governance(self.v)
        n1 = g.agent_write(title="a", body="alpha body", partition="dev", store="knowledge",
                           author="dev-agent", source="run#1")
        n2 = g.agent_write(title="b", body="beta body", partition="dev", store="knowledge",
                           author="dev-agent", source="run#2")
        g.promote(n1.id, "founder", "good")
        g.reject(n2.id, "founder", "wrong")
        evs = trust.events(self.v, "dev-agent", "stage")
        self.assertEqual([e["kind"] for e in evs], ["success", "failure"])
        self.assertEqual([e["ref"] for e in evs], [n1.id, n2.id])
        self.assertEqual([e["actor"] for e in evs], ["founder", "founder"])
        c = trust.computed(self.v, "dev-agent", "stage")
        self.assertAlmostEqual(c["score"], 0.0, places=3)    # +1 −1, same day

    def test_scorecard_lists_last_events(self):
        for i in range(1, 9):
            self.rec("bot", "stage", "success", day(i), ref=f"n{i}")
        card = trust.scorecard(self.v, "bot", as_of=day(9), last_n=3)
        refs = [e["ref"] for e in card["classes"]["stage"]["last_events"]]
        self.assertEqual(refs, ["n6", "n7", "n8"])


class TestRender(TrustBase):
    def test_render_mentions_every_class_and_the_caps(self):
        self.rec("bot", "merge-code", "halt", day(1), reason="stopped at ceiling 4")
        out = trust.render_scorecard(trust.scorecard(self.v, "bot", as_of=day(2)))
        for k in trust.CLASSES:
            self.assertIn(k, out)
        self.assertIn("human-only cap", out); self.assertIn("halt", out)
        self.assertIn("L1 PROPOSE", out); self.assertIn("stopped at ceiling 4", out)


class TestConfigInvariants(unittest.TestCase):
    def test_defaults_are_sane(self):
        t = DEFAULTS["trust"]
        self.assertEqual(set(t["classes"]), set(trust.CLASSES))
        self.assertTrue(all(t["weights"][k] > 0 for k in trust.POSITIVE))
        self.assertTrue(all(t["weights"][k] < 0 for k in trust.NEGATIVE))
        self.assertNotIn("violation", t["weights"]); self.assertNotIn("reinstate", t["weights"])
        th = t["thresholds"]; self.assertLess(th["1"], th["2"]); self.assertLess(th["2"], th["3"])
        for k in trust.HUMAN_ONLY:
            self.assertEqual(t["classes"][k]["ceiling"], 1)


if __name__ == "__main__":
    unittest.main()
