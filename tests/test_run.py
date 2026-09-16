"""THE SUBSCRIPTION SOCKET v0 (P-22) — the drills with a fake engine (the real one is the Agent SDK)."""
import os, sys, json, shutil, tempfile, unittest, subprocess
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from magnemo.vault import Vault
from magnemo.governance import Governance
from magnemo import run as R, chest


def fake_engine(stage_body=None, rate=None, subtype="success", turns=3, cost=0.0123):
    def _engine(task, opts):
        ev = []
        if stage_body is not None:                               # the engine "calls" stage: simulate the MCP write
            v = Vault(opts["env"]["MAGNEMO_VAULT"])
            Governance(v).agent_write(title="run note", body=stage_body, partition=v.partitions[0], store=v.stores[v.partitions[0]][0],
                                      author=opts["env"]["MAGNEMO_AGENT"], source=f"run:{task}")
            ev.append({"type": "tool_use", "name": "mcp__magnemo__bootpack"}); ev.append({"type": "tool_use", "name": "mcp__magnemo__stage"})
        if rate:
            ev.append(dict(type="rate_limit", **rate))
        ev.append({"type": "result", "subtype": subtype, "is_error": subtype != "success", "turns": turns, "duration_ms": 1200,
                   "cost_usd": cost, "tokens_in": 1000, "tokens_out": 200, "result": "done"})
        return ev
    return _engine


class TestRun(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.v = Vault(self.d); self.v.init()

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_d1_a_run_stages_and_never_promotes(self):
        canon = len(self.v.canonical())
        r = R.run(self.d, "summarize", engine_fn=fake_engine(stage_body="a finding"))
        self.assertEqual(len(r["staged_notes"]), 1); self.assertEqual(r["exit_reason"], "completed")
        n = self.v.read(r["staged_notes"][0]); self.assertEqual(n.status, "staged"); self.assertEqual(n.author, r["agent"]); self.assertIn("run:", n.source)
        self.assertEqual(len(self.v.canonical()), canon)
        self.assertIn("FUEL: 1,000 in · 200 out tokens · 3 turns", r["fuel"]); self.assertIn("not reported", r["fuel"])
        ends = [e for e in R.entries(self.d) if e["kind"] == "RUN_END"]; self.assertEqual(ends[0]["stage_calls"], 1)

    def test_d2_cap_paths_exit_with_reason(self):
        r = R.run(self.d, "t", engine_fn=fake_engine(rate={"status": "rejected", "kind": "five_hour", "utilization": 1.0, "resets_at": "2026-09-05T12:00:00Z"}))
        self.assertIn("plan cap reached (five_hour)", r["exit_reason"]); self.assertIn("resets", r["exit_reason"]); self.assertIn("plan window (five_hour): rejected, 100% used", r["fuel"])
        r2 = R.run(self.d, "t", cap_turns=3, engine_fn=fake_engine(subtype="error_max_turns", turns=3))
        self.assertIn("turn cap reached (3 turns)", r2["exit_reason"])
        r3 = R.run(self.d, "t", cap_usd=0.01, engine_fn=fake_engine(cost=0.0123))
        self.assertIn("budget cap reached", r3["exit_reason"])
        self.assertTrue(all(e.get("exit_reason") for e in R.entries(self.d) if e["kind"] == "RUN_END"))   # never silent
        with self.assertRaises(R.RunError) as cm:
            R.run(self.d, "t", engine="codex")
        self.assertIn("not wired yet", str(cm.exception))

    def test_d3_schedule_writes_rail_and_a_job_and_fires_with_trigger(self):
        agents = os.path.join(self.d, "agents")
        out = R.schedule(self.d, "morning sweep", "0 9 * * 1", cap_turns=5, install=False, agents_dir=agents)
        self.assertEqual(out["plain"], "every Monday at 09:00")
        rail = open(out["rail"]).read(); self.assertIn("| every Monday at 09:00 (`0 9 * * 1`) | run-morning-sweep · engine claude | morning sweep | 5 turns | staged only — a human promotes |", rail)
        if sys.platform == "darwin":
            p = open(out["plist"]).read(); self.assertIn("<key>Hour</key><integer>9</integer>", p); self.assertIn("<key>Weekday</key><integer>1</integer>", p); self.assertIn("--trigger</string>", p); self.assertIn("schedule</string>", p)
        with self.assertRaises(R.RunError):
            R.schedule(self.d, "x", "*/5 * * * *", install=False, agents_dir=agents)      # v0: plain fields only, said plainly
        r = R.run(self.d, "morning sweep", trigger="schedule", engine_fn=fake_engine(stage_body="fired"))
        end = [e for e in R.entries(self.d) if e["kind"] == "RUN_END"][-1]
        self.assertEqual(end["trigger"], "schedule"); self.assertEqual(len(r["staged_notes"]), 1)
        self.assertIn("scheduled runs", open(out["rail"]).read())

    def test_d4_chest_event_fires_after_a_run(self):
        drawer = os.path.join(self.d, "..", "drawer-" + os.path.basename(self.d)); chest.add_destination(self.d, "path", os.path.abspath(drawer), label="drawer")
        R.run(self.d, "t", engine_fn=fake_engine(stage_body="x"))
        kinds = [(e["kind"], e.get("trigger")) for e in chest.entries(self.d)]
        self.assertIn(("CHEST_PUSH", "receipt"), kinds)
        shutil.rmtree(os.path.abspath(drawer), ignore_errors=True)

    def test_engine_failure_is_ledgered_in_plain_english(self):
        def broken(task, opts):
            raise RuntimeError("Claude Code returned an error result: Failed to authenticate: OAuth session expired")
        with self.assertRaises(R.RunError) as cm:
            R.run(self.d, "t", engine_fn=broken)
        self.assertIn("login on this machine has expired", str(cm.exception)); self.assertIn("never stores your token", str(cm.exception))
        end = [e for e in R.entries(self.d) if e["kind"] == "RUN_END"][-1]
        self.assertTrue(end["exit_reason"].startswith("engine error:"))                    # never silent, always ledgered

    def test_unschedule_retires_the_rail_row(self):
        agents = os.path.join(self.d, "agents")
        out = R.schedule(self.d, "nightly", "0 2 * * *", install=False, agents_dir=agents)
        self.assertIn("run-nightly ", open(out["rail"]).read())
        R.unschedule(self.d, out["label"], agents_dir=agents)
        self.assertNotIn("run-nightly ", open(out["rail"]).read()); self.assertFalse(os.path.exists(out["plist"]))

    def test_card(self):
        R.run(self.d, "t", engine_fn=fake_engine(cost=0.5)); R.run(self.d, "t", engine_fn=fake_engine(cost=0.25))
        c = R.card(self.d); self.assertIn("runs this month: 2", c); self.assertIn("API list-price avoided: $0.75", c); self.assertIn(R.PRICING_URL, c)

    def test_no_token_anywhere(self):
        src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "magnemo", "run.py")).read()
        for bad in ("ANTHROPIC_API_KEY", "access_token", "refresh_token", "api_key", "Authorization:", "Bearer "):
            self.assertNotIn(bad, src)                                          # no credential handling of any kind


if __name__ == "__main__":
    unittest.main()
