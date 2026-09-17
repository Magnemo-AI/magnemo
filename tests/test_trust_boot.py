"""P-02 B4 — the agent always knows its own level: boot pack + handoff."""
import json, os, shutil, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from magnemo.vault import Vault
from magnemo import trust, grants, bootpack, handoff

F = "The Founder"


def day(n):
    return f"2026-08-{n:02d}T00:00:00Z"


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.v = Vault(self.dir); self.v.init()

    def tearDown(self):
        shutil.rmtree(self.dir)


class TestBootPackScorecard(Base):
    def test_no_actor_no_section(self):
        pack = bootpack.generate(self.v)
        self.assertNotIn("## YOUR AUTONOMY", pack)

    def test_actor_section_sits_after_gates_before_canon_and_shows_levels(self):
        grants.issue(self.v, "bot", ["merge-code"], 2, by=F, ref="P-01", scope="repo", when=day(1))
        for _ in range(5):
            trust.record(self.v, "bot", "merge-code", "success", by=F, when=day(1))
        pack = bootpack.generate(self.v, actor="bot")
        self.assertLess(pack.index("## GATES"), pack.index("## YOUR AUTONOMY — bot"))
        self.assertLess(pack.index("## YOUR AUTONOMY — bot"), pack.index("## CANON DIGEST"))
        own = pack.split("## YOUR AUTONOMY — bot")[1].split("## CANON DIGEST")[0]
        self.assertIn("| merge-code | **L2 SUPERVISED** | L2 SUPERVISED | L2 SUPERVISED | 5.0000 |", own)
        self.assertIn("| promote-canon | **L1 PROPOSE** (keyholder-only cap)", own)
        self.assertIn("grant G0001 → L2 in merge-code (P-01) — repo", own)
        self.assertIn(f"ledger time {day(1)}", own)

    def test_frozen_class_is_shouted(self):
        trust.record(self.v, "bot", "merge-code", "violation", by=F, reason="merged gate code", when=day(2))
        own = bootpack.generate(self.v, actor="bot").split("## YOUR AUTONOMY — bot")[1]
        self.assertIn("**L0 FROZEN** FROZEN", own.split("## CANON DIGEST")[0])
        self.assertIn("merge-code is FROZEN", own)

    def test_keyholder_boot(self):
        own = bootpack.generate(self.v, actor=F).split("## YOUR AUTONOMY — ")[1]
        self.assertIn("declared keyholder: L4 in every class", own)

    def test_pure_same_vault_same_pack_per_actor(self):
        trust.record(self.v, "bot", "stage", "success", by=F, when=day(1))
        a = bootpack.generate(self.v, actor="bot"); b = bootpack.generate(self.v, actor="bot")
        self.assertEqual(a, b)
        other = bootpack.generate(self.v, actor="other")
        self.assertNotEqual(a, other)
        self.assertEqual(a.split("## CANON DIGEST")[1], other.split("## CANON DIGEST")[1])

    def test_write_passes_actor_and_logs_it(self):
        from magnemo import foresight
        path, n = bootpack.write(self.v, actor="bot")
        with open(path) as f:
            self.assertIn("## YOUR AUTONOMY — bot", f.read())
        self.assertEqual(foresight.entries(self.v)[-1]["meta"]["actor"], "bot")


class TestHandoffRecordsLevels(Base):
    def test_handoff_entry_and_note_carry_levels_at_ledger_time(self):
        grants.issue(self.v, "bot", ["merge-code"], 2, by=F, when=day(1))
        for _ in range(5):
            trust.record(self.v, "bot", "merge-code", "success", by=F, when=day(1))
        e = handoff.record(self.v, 90, "planned", cut="B4 docs", actor="bot")
        self.assertEqual(e["levels"], {"read": 2, "stage": 2, "merge-code": 2,
                                       "promote-canon": 1, "publish": 1})
        on_disk = handoff.entries(self.v)[-1]
        self.assertEqual(on_disk["levels"], e["levels"])
        note = self.v.read(e["note_id"])
        self.assertIn("autonomy at the boundary: read L2 · stage L2 · merge-code L2 · promote-canon L1 · publish L1",
                      note.body)

    def test_next_boot_inherits_the_boundary_levels(self):
        handoff.record(self.v, 88, "planned", actor="bot")
        pack = bootpack.generate(self.v, actor="bot")
        last = pack.split("## LAST HANDOFF")[1].split("## LEDGER TAIL")[0]
        self.assertIn("autonomy at the boundary: read L2 · stage L2 · merge-code L1 · promote-canon L1 · publish L1", last)

    def test_legacy_handoff_entries_without_levels_still_render(self):
        path = os.path.join(self.dir, "_ledger", "handoffs.jsonl")
        with open(path, "a") as f:
            f.write(json.dumps({"ts": day(1), "usage_pct": 98.0, "trigger": "wall", "cut": "", "actor": "old"}) + "\n")
        pack = bootpack.generate(self.v, actor="bot")
        last = pack.split("## LAST HANDOFF")[1].split("## LEDGER TAIL")[0]
        self.assertIn("usage 98%", last); self.assertNotIn("autonomy at the boundary", last)


if __name__ == "__main__":
    unittest.main()
