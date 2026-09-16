"""P-10 dogfood QoL: `magnemo stage` (founder's terminal write path),
`magnemo doctor` (rename survivor's checkup), and the fresh-vault
bootpack rendering fix."""
import json, os, shutil, subprocess, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from magnemo.vault import Vault
from magnemo import bootpack, doctor

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def cli(args, env_extra=None, stdin=None):
    env = dict(os.environ, PYTHONPATH=REPO)
    env.pop("MAGNEMO_AGENT", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run([sys.executable, "-m", "magnemo.cli"] + args,
                          capture_output=True, text=True, env=env, input=stdin)


class TestCliStage(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.vault = os.path.join(self.dir, "vault")
        Vault(self.vault).init()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_stage_lands_in_staging_with_provenance(self):
        r = cli(["stage", "Pail counts drift on route 7",
                 "--body", "Two short on Tuesdays; depot scale suspected.",
                 "--partition", "dev", "--store", "knowledge",
                 "--source", "test-run#1", "--tags", "dogfood", self.vault])
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("staged:", r.stdout)
        v = Vault(self.vault)
        staged = v.staged()
        self.assertEqual(len(staged), 1)
        n = staged[0]
        self.assertEqual(n.status, "staged")
        self.assertEqual(n.source, "test-run#1")
        self.assertEqual(n.author, "founder")        # default when no $MAGNEMO_AGENT
        self.assertGreaterEqual(n.salience, 0)       # KAIROS ran at stage time

    def test_stage_refuses_paperless(self):
        r = cli(["stage", "No papers", "--body", "x",
                 "--partition", "dev", "--store", "knowledge", self.vault])
        self.assertNotEqual(r.returncode, 0)         # --source is mandatory
        self.assertEqual(len(Vault(self.vault).staged()), 0)

    def test_stage_refuses_empty_body(self):
        r = cli(["stage", "No body", "--partition", "dev", "--store",
                 "knowledge", "--source", "s", self.vault], stdin="")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(len(Vault(self.vault).staged()), 0)

    def test_stage_body_from_stdin_and_foresight_logged(self):
        r = cli(["stage", "Stdin note", "--partition", "dev",
                 "--store", "knowledge", "--source", "s2", self.vault],
                stdin="body came through the pipe")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        costs = os.path.join(self.vault, "_ledger", "costs.jsonl")
        events = [json.loads(l) for l in open(costs) if l.strip()]
        stage_events = [e for e in events if e["kind"] == "stage"]
        self.assertEqual(len(stage_events), 1)
        self.assertEqual(stage_events[0]["meta"]["via"], "cli")


class TestDoctor(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.vault = os.path.join(self.dir, "vault")
        Vault(self.vault).init()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def _levels(self, results):
        return {r["label"]: r["level"] for r in results}

    def test_healthy_vault_passes(self):
        results = doctor.run(self.vault, [])
        self.assertFalse([r for r in results if r["level"] == doctor.FAIL],
                         results)

    def test_missing_vault_fails(self):
        results = doctor.run(os.path.join(self.dir, "nowhere"), [])
        self.assertTrue(any(r["level"] == doctor.FAIL and r["label"] == "vault"
                            for r in results))

    def test_mount_with_dead_command_fails(self):
        mf = os.path.join(self.dir, ".mcp.json")
        with open(mf, "w") as f:
            json.dump({"mcpServers": {"magnemo-mcp": {
                "command": "/renamed/away/bin/magnemo-mcp",
                "env": {"MAGNEMO_VAULT": self.vault}}}}, f)
        results = doctor.run(self.vault, [self.dir])
        fails = [r for r in results if r["level"] == doctor.FAIL]
        self.assertEqual(len(fails), 1)
        self.assertIn("command missing", fails[0]["detail"])

    def test_mount_with_dead_vault_fails(self):
        mf = os.path.join(self.dir, "m.json")
        with open(mf, "w") as f:
            json.dump({"mcpServers": {"magnemo-mcp": {
                "command": sys.executable,
                "env": {"MAGNEMO_VAULT": "/no/vault/here"}}}}, f)
        results = doctor.run(self.vault, [mf])
        self.assertTrue(any("MAGNEMO_VAULT has no vault" in r["detail"]
                            for r in results if r["level"] == doctor.FAIL))

    def test_broken_ledger_line_fails(self):
        with open(os.path.join(self.vault, "_ledger", "costs.jsonl"), "w") as f:
            f.write('{"ts": "2026-01-01T00:00:00Z", "kind": "stage"}\nnot json\n')
        results = doctor.run(self.vault, [])
        self.assertTrue(any(r["label"] == "ledger costs.jsonl"
                            and r["level"] == doctor.FAIL for r in results))

    def test_cli_exit_codes(self):
        ok = cli(["doctor", self.vault])
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        bad = cli(["doctor", os.path.join(self.dir, "nowhere")])
        self.assertEqual(bad.returncode, 1)


class TestFreshVaultBootpackRendering(unittest.TestCase):
    def test_empty_ledger_never_prints_epoch(self):
        d = tempfile.mkdtemp()
        try:
            v = Vault(os.path.join(d, "vault")); v.init()
            text = bootpack.generate(v, "worker", None, actor="probe")
            self.assertNotIn("1970-01-01", text)
            self.assertIn("before any ledger event (fresh vault)", text)
        finally:
            shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()
