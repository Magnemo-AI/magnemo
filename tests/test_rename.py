"""0.4.0 "First Name": the package is magnemo. The old name is retired (0.6.1)."""
import os, sys, json, shutil, tempfile, unittest, subprocess, warnings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import magnemo
from magnemo.vault import Vault
from magnemo.config import load_config, config_path, ensure_config, CONFIG_FILE, LEGACY_CONFIG_FILES


class TestIdentity(unittest.TestCase):
    def test_version_and_codename(self):
        # ONE version: pyproject.toml is the single source of truth
        import re
        with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as f:
            pinned = re.search(r'^version\s*=\s*"([^"]+)"', f.read(), re.M).group(1)
        self.assertEqual(magnemo.__version__, pinned)
        self.assertEqual(magnemo.__codename__, "First Trust")

    def test_mcp_server_identity(self):
        from magnemo.transport import SERVER_INFO
        self.assertEqual(SERVER_INFO["name"], "magnemo")
        self.assertEqual(SERVER_INFO["version"], magnemo.__version__)

    def test_cli_runs_under_new_name(self):
        d = tempfile.mkdtemp()
        try:
            p = subprocess.run([sys.executable, "-m", "magnemo.cli", "init", d], capture_output=True, text=True, cwd=ROOT)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertTrue(os.path.exists(os.path.join(d, "_config", CONFIG_FILE)))
            p = subprocess.run([sys.executable, "-m", "magnemo.cli", "bootpack", "--stdout", d], capture_output=True, text=True, cwd=ROOT)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertTrue(p.stdout.startswith("# BOOT PACK — magnemo · worker boot"))
        finally:
            shutil.rmtree(d)


class TestLegacyConfig(unittest.TestCase):
    """Vaults initialised before the rename carry the config under the old filename."""
    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.d, "_config"))

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_legacy_file_is_read(self):
        old = os.path.join(self.d, "_config", LEGACY_CONFIG_FILES[0])
        with open(old, "w") as f:
            json.dump({"review": {"batch": 3}}, f)
        self.assertEqual(config_path(self.d), old)
        self.assertEqual(load_config(self.d)["review"]["batch"], 3)
        ensure_config(self.d)  # must NOT clobber a founder-edited legacy file with a new default
        self.assertFalse(os.path.exists(os.path.join(self.d, "_config", CONFIG_FILE)))
        self.assertEqual(load_config(self.d)["review"]["batch"], 3)

    def test_new_name_wins_when_both_exist(self):
        with open(os.path.join(self.d, "_config", LEGACY_CONFIG_FILES[0]), "w") as f:
            json.dump({"review": {"batch": 3}}, f)
        with open(os.path.join(self.d, "_config", CONFIG_FILE), "w") as f:
            json.dump({"review": {"batch": 7}}, f)
        self.assertEqual(load_config(self.d)["review"]["batch"], 7)

    def test_fresh_vault_gets_new_name(self):
        v = Vault(self.d); v.init()
        self.assertTrue(os.path.exists(os.path.join(self.d, "_config", CONFIG_FILE)))
        self.assertFalse(os.path.exists(os.path.join(self.d, "_config", LEGACY_CONFIG_FILES[0])))


if __name__ == "__main__":
    unittest.main()
