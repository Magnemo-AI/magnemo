"""P-18: MAGNEMO_* is the name; MEMOS_* is honored for one release; the doctor says so once."""
import os, sys, json, shutil, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from magnemo.vault import Vault
from magnemo import mcp, doctor
from magnemo.config import env, legacy_env_in_use

ALL = [p + n for p in ("MAGNEMO_", "MEMOS_") for n in ("VAULT", "AGENT", "SCOPE", "PARTITIONS")]


class TestEnvNames(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); Vault(self.d).init()
        self.saved = {k: os.environ.pop(k, None) for k in ALL}

    def tearDown(self):
        shutil.rmtree(self.d)
        for k in ALL:
            os.environ.pop(k, None)
        for k, v in self.saved.items():
            if v is not None:
                os.environ[k] = v

    def test_magnemo_names_work(self):
        os.environ["MAGNEMO_VAULT"] = self.d; os.environ["MAGNEMO_AGENT"] = "new-name"
        s = mcp.MemoryServer()
        self.assertEqual(s.agent, "new-name"); self.assertEqual(s.vault.root, os.path.abspath(self.d))

    def test_memos_names_alone_still_work(self):
        os.environ["MEMOS_VAULT"] = self.d; os.environ["MEMOS_AGENT"] = "old-name"; os.environ["MEMOS_SCOPE"] = "dev"
        s = mcp.MemoryServer()
        self.assertEqual(s.agent, "old-name"); self.assertEqual(s.read_scope, ("dev",))

    def test_both_set_magnemo_wins(self):
        os.environ["MEMOS_VAULT"] = self.d; os.environ["MAGNEMO_VAULT"] = self.d
        os.environ["MEMOS_AGENT"] = "old-name"; os.environ["MAGNEMO_AGENT"] = "new-name"
        self.assertEqual(env("AGENT"), "new-name")
        self.assertEqual(mcp.MemoryServer().agent, "new-name")

    def test_doctor_notice_exactly_once(self):
        os.environ["MEMOS_AGENT"] = "old-name"                      # in the process env
        mf = os.path.join(self.d, ".mcp.json")
        with open(mf, "w") as f:                                       # AND in a mount's env
            json.dump({"mcpServers": {"magnemo": {"command": "magnemo-mcp", "env": {"MEMOS_VAULT": self.d}}}}, f)
        results = doctor.run(self.d, [mf])
        notes = [r for r in results if r["level"] == doctor.NOTE]
        self.assertEqual(len(notes), 1)
        self.assertIn("MEMOS_* settings", notes[0]["detail"]); self.assertIn("MAGNEMO_*", notes[0]["detail"])
        self.assertIn("MEMOS_AGENT", notes[0]["detail"]); self.assertIn("MEMOS_VAULT", notes[0]["detail"])
        self.assertFalse(any(r["level"] == doctor.FAIL for r in results))
        self.assertTrue(doctor.report(results))                        # a note never fails the checkup

    def test_no_notice_without_legacy(self):
        os.environ["MAGNEMO_AGENT"] = "new-name"
        results = doctor.run(self.d, [])
        self.assertEqual([r for r in results if r["level"] == doctor.NOTE], [])
        self.assertEqual(legacy_env_in_use({"MAGNEMO_VAULT": "x"}), [])


if __name__ == "__main__":
    unittest.main()
