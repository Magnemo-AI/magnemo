"""P-19 THE BOARDROOM MOUNT — the engine laws it needed: a vault declares its own shape,
promotion renders with the prior hash ledgered, drift is re-staged as the founder's,
the inbox is the only door and Sentinel guards it, excerpts boot from canon."""
import os, sys, json, shutil, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from magnemo.vault import Vault
from magnemo.governance import Governance, TrustLedger
from magnemo.config import config_path
from magnemo import mcp, doctor, bootpack, chest
import subprocess

SHAPE = {"doctrine": ["canon"], "state": ["current"], "missions": ["scoped"], "receipts": ["filed"]}


def make_vault(tmp):
    root = os.path.join(tmp, "vault"); v = Vault(root); v.init()
    cfg = json.load(open(config_path(root)))
    cfg["partitions"] = SHAPE
    cfg["scopes"] = {"svtech": list(SHAPE)}
    cfg["render"] = {"root": ".."}
    cfg["inbox"] = {"dir": "../inbox", "routes": [
        {"match": "BATON.md", "partition": "doctrine", "store": "canon", "render": "BATON.md", "title": "BATON"},
        {"match": "*.md", "partition": "state", "store": "current", "render": "{name}", "title": "{stem}"},
    ]}
    cfg["bootpack"]["excerpts"] = [{"title": "REV BLOCK", "note": "BATON", "start": r"^## REV", "end": r"^## "}]
    json.dump(cfg, open(config_path(root), "w"), indent=2)
    v = Vault(root); v.init()   # re-init builds the declared shape
    return v


def cli(args, cwd, **env):
    e = dict(os.environ, PYTHONPATH=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for k in ("MAGNEMO_VAULT", "MAGNEMO_AGENT", "MAGNEMO_SCOPE", "MAGNEMO_PARTITIONS"):
        e.pop(k, None)
    e.update(env)
    return subprocess.run([sys.executable, "-m", "magnemo.cli", *args], capture_output=True, text=True, cwd=cwd, env=e)


class TestShape(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(); self.v = make_vault(self.tmp)
        self.saved = {k: os.environ.pop(k, None) for k in ("MAGNEMO_VAULT", "MAGNEMO_AGENT", "MAGNEMO_SCOPE", "MAGNEMO_PARTITIONS")}

    def tearDown(self):
        shutil.rmtree(self.tmp)
        for k, val in self.saved.items():
            if val is not None: os.environ[k] = val
            else: os.environ.pop(k, None)

    def test_vault_declares_its_shape(self):
        self.assertEqual(self.v.partitions, ("doctrine", "state", "missions", "receipts"))
        for p, stores in SHAPE.items():
            for s in stores:
                self.assertTrue(os.path.isdir(os.path.join(self.v.root, p, s)))
        with self.assertRaises(ValueError):
            Governance(self.v).agent_write(title="x", body="y", partition="dev", store="knowledge", author="a", source="s")
        self.assertEqual(Vault(os.path.join(self.tmp, "plain")).partitions, ("dev", "ops", "shared"))  # the defaults still rule a plain vault

    def test_scope_alias_and_tool_schema_follow_the_vault(self):
        os.environ["MAGNEMO_VAULT"] = self.v.root; os.environ["MAGNEMO_AGENT"] = "boardroom"; os.environ["MAGNEMO_SCOPE"] = "svtech"
        s = mcp.MemoryServer()
        self.assertEqual(s.read_scope, ("doctrine", "state", "missions", "receipts"))
        spec = s.tools_spec()
        self.assertEqual(len(spec), 4)                                              # the four verbs stand
        stage = next(t for t in spec if t["name"] == "stage")
        def enums(o, key):
            if isinstance(o, dict):
                if key in o and isinstance(o[key], dict) and "enum" in o[key]:
                    yield o[key]["enum"]
                for v in o.values():
                    yield from enums(v, key)
            elif isinstance(o, list):
                for v in o:
                    yield from enums(v, key)
        found = list(enums(stage["inputSchema"], "partition"))
        self.assertTrue(found, "stage schema declares no partition enum")
        self.assertEqual(found[0], list(SHAPE))
        self.assertEqual(len(mcp.tools_spec()), 4)

    def test_promote_renders_and_ledgers_prior_hash(self):
        import hashlib
        g = Governance(self.v)
        n1 = g.agent_write(title="BATON", body="v1 body\n", partition="doctrine", store="canon", author="cc", source="s")
        n1.extra["render"] = "BATON.md"; self.v.rewrite(n1)
        g.promote(n1.id, "founder")
        path = os.path.join(self.tmp, "BATON.md")
        self.assertEqual(open(path).read(), "v1 body\n")
        n2 = g.agent_write(title="BATON", body="v2 body\n", partition="doctrine", store="canon", author="cc", source="s", supersedes=n1.id)
        n2.extra["render"] = "BATON.md"; self.v.rewrite(n2)
        g.promote(n2.id, "founder")
        self.assertEqual(open(path).read(), "v2 body\n")
        renders = [e for e in TrustLedger(self.v).entries("memory.render")]
        self.assertEqual(len(renders), 2)
        self.assertIsNone(renders[0]["prior_sha256"])
        self.assertEqual(renders[1]["prior_sha256"], hashlib.sha256(b"v1 body\n").hexdigest())
        self.assertEqual(self.v.read(n1.id).status, "archived")                       # v1 recoverable, not lost
        self.assertIn("v1 body", self.v.read(n1.id).body)

    def test_drift_owner_is_the_newest_canonical_version(self):
        """Sitting close Sep 9: promoting every version of a file oldest-first (no
        supersedes declared) leaves several canonical notes rendering to one path.
        The render belongs to the newest; older versions are superseded, not drift.
        Before the fix the doctor re-staged the current render as a phantom founder
        edit for every older version, on every run."""
        g = Governance(self.v)
        ids = []
        for body in ("v1 body\n", "v2 body\n", "v3 body\n"):
            n = g.agent_write(title="BATON", body=body, partition="doctrine", store="canon", author="boardroom-session", source="inbox")
            n.extra["render"] = "BATON.md"; self.v.rewrite(n); ids.append(n.id)
        for i in ids:
            g.promote(i, "founder")
        self.assertEqual(open(os.path.join(self.tmp, "BATON.md")).read(), "v3 body\n")
        self.assertEqual(len([n for n in self.v.canonical() if n.title == "BATON"]), 3)
        results = []
        doctor.check_drift(results, self.v)
        self.assertEqual([r for r in results if r["label"] == "drift"], [])
        self.assertEqual([n for n in self.v.staged() if n.status == "staged"], [])
        # a real edit on disk is still caught, once, against the newest version
        with open(os.path.join(self.tmp, "BATON.md"), "w") as f:
            f.write("edited by hand\n")
        results = []
        doctor.check_drift(results, self.v)
        drifted = [n for n in self.v.staged() if n.status == "staged"]
        self.assertEqual(len(drifted), 1)
        self.assertEqual(drifted[0].supersedes, ids[-1])

    def test_drift_restaged_as_founder(self):
        g = Governance(self.v)
        n = g.agent_write(title="BATON", body="canon body\n", partition="doctrine", store="canon", author="cc", source="s")
        n.extra["render"] = "BATON.md"; self.v.rewrite(n); g.promote(n.id, "founder")
        path = os.path.join(self.tmp, "BATON.md")
        with open(path, "a") as f: f.write("founder wrote this by hand\n")
        r1 = doctor.run(self.v.root, [])
        notes = [x for x in r1 if x["label"] == "drift"]
        self.assertEqual(len(notes), 1); self.assertIn("re-staged", notes[0]["detail"])
        st = [s for s in self.v.staged() if s.author == "founder" and s.supersedes == n.id]
        self.assertEqual(len(st), 1); self.assertIn("founder wrote this by hand", st[0].body)
        r2 = doctor.run(self.v.root, [])                                                # idempotent: no second copy
        self.assertEqual(len([s for s in self.v.staged() if s.supersedes == n.id]), 1)
        self.assertIn("already re-staged", next(x for x in r2 if x["label"] == "drift")["detail"])
        g.promote(st[0].id, "founder")                                                   # promotion keeps the edit
        self.assertIn("founder wrote this by hand", open(path).read())
        self.assertFalse(any(x["level"] == doctor.FAIL for x in doctor.run(self.v.root, [])))

    def test_inbox_is_the_door_and_sentinel_guards_it(self):
        inbox = os.path.join(self.tmp, "inbox"); os.makedirs(inbox)
        open(os.path.join(inbox, "BATON.md"), "w").write("## REV BLOCK\n- beat one\n## 0 · WHAT\nrest\n")
        open(os.path.join(inbox, "creds.md"), "w").write("key: AKIA" + "Q" * 16 + "\n")
        remote = os.path.join(self.tmp, "remote.git"); subprocess.run(["git", "init", "-q", "--bare", "-b", "main", remote], check=True)
        chest.add_destination(self.v.root, "git", remote, label="laptop")
        r = cli(["inbox", "--as", "cc", self.v.root], cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("staged  BATON.md", r.stdout); self.assertIn("HELD    creds.md", r.stdout)
        self.assertTrue(os.path.exists(os.path.join(inbox, "blocked", "creds.md")))     # held, not a memory
        staged = self.v.staged()
        baton = next(s for s in staged if s.title == "BATON")
        self.assertEqual(baton.author, "cc"); self.assertIn("sha256:", baton.source); self.assertEqual(baton.extra.get("render"), "BATON.md")
        sent = next(s for s in staged if s.author == "sentinel")
        self.assertIn("aws-access-key", sent.body); self.assertNotIn("AKIA" + "Q" * 16, sent.body); self.assertTrue(sent.taint.startswith("sentinel:"))
        res = chest.push(self.v.root, trigger="manual")[0]
        self.assertEqual(res["status"], "blocked"); self.assertIn("🔴", chest.gauge(self.v.root))
        os.remove(os.path.join(inbox, "blocked", "creds.md"))                           # the human clears it
        self.assertEqual(chest.push(self.v.root, trigger="manual")[0]["status"], "ok")
        # promote the drop: rendered to disk, and the boot pack lifts the REV BLOCK from CANON
        Governance(self.v).promote(baton.id, "founder")
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "BATON.md")))
        pack = bootpack.generate(self.v)
        self.assertIn("## REV BLOCK", pack); self.assertIn("- beat one", pack); self.assertNotIn("## 0 · WHAT", pack.split("## REV BLOCK")[1].split("##")[0])

    def test_inbox_survives_undeletable_drop(self):
        import magnemo.cli as cli_mod
        inbox = os.path.join(self.tmp, "inbox"); os.makedirs(inbox)
        open(os.path.join(inbox, "A.md"), "w").write("first\n"); open(os.path.join(inbox, "B.md"), "w").write("second\n")
        real_remove = os.remove
        def flaky(path):
            if path.endswith("A.md"):
                raise PermissionError("environment cannot delete")
            return real_remove(path)
        class A: pass
        a = A(); a.vault = self.v.root; a.dir = ""; a.tag = "cc"
        import io, contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            cli_mod.os.remove = flaky
            try:
                cli_mod.cmd_inbox(a)
            finally:
                cli_mod.os.remove = real_remove
        titles = sorted(n.title for n in self.v.staged() if n.status == "staged")
        self.assertEqual(titles, ["A", "B"])                                           # the loop never aborted
        self.assertTrue(os.path.exists(os.path.join(inbox, "_staged", "A.md")))     # set aside, not left as a drop
        self.assertFalse(os.path.exists(os.path.join(inbox, "A.md")))
        self.assertFalse(os.path.exists(os.path.join(inbox, "B.md")))

    def test_partner_class_adds_partner_excerpts(self):
        cfg = json.load(open(config_path(self.v.root)))
        cfg["bootpack"]["partner_excerpts"] = [{"title": "WHOLE CODEX", "note": "CODEX", "start": "", "end": ""}]
        json.dump(cfg, open(config_path(self.v.root), "w"), indent=2)
        g = Governance(self.v)
        n = g.agent_write(title="CODEX", body="voice line one\nvoice line two\n", partition="doctrine", store="canon", author="cc", source="s")
        g.promote(n.id, "founder")
        worker = bootpack.generate(self.v, cls="worker"); partner = bootpack.generate(self.v, cls="partner")
        self.assertNotIn("## WHOLE CODEX", worker)
        self.assertIn("## WHOLE CODEX", partner); self.assertIn("voice line two", partner)
        self.assertTrue(partner.startswith("# BOOT PACK — magnemo · partner boot"))

    def test_handoff_body_file(self):
        rb = os.path.join(self.tmp, "rev.md"); open(rb, "w").write("REV BLOCK line one\nline two\n")
        r = cli(["handoff", "--usage", "40", "--trigger", "planned", "--by", "boardroom", "--body-file", rb, self.v.root], cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        h = [s for s in self.v.staged() if s.title.startswith("Handoff")]
        self.assertEqual(len(h), 1); self.assertIn("REV BLOCK line one", h[0].body)


if __name__ == "__main__":
    unittest.main()
