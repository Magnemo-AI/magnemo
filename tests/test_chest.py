"""THE CHEST — the gauntlet as drills, plus the law."""
import os, sys, json, shutil, tempfile, unittest, subprocess, hashlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from magnemo.vault import Vault
from magnemo.governance import Governance
from magnemo import chest, doctor, bootpack


def _bare(path):
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", path], check=True)
    return path


def _promote_n(vault_dir, n, prefix="note"):
    g = Governance(Vault(vault_dir))
    ids = []
    for i in range(n):
        nt = g.agent_write(title=f"{prefix} {i}", body=f"Body of {prefix} {i}.", partition="dev",
                           store="knowledge", author="drill", source=f"drill#{i}")
        g.promote(nt.id, "founder", "drill")
        ids.append(nt.id)
    return ids


def _pack_sha(vault_dir):
    data = bootpack.generate(Vault(vault_dir)).encode("utf-8")
    return hashlib.sha256(data).hexdigest(), data


class TestTheLaw(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.v = Vault(self.d); self.v.init()
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.d); shutil.rmtree(self.tmp)

    def test_no_hosted_kind_exists(self):
        self.assertEqual(chest.KINDS, ("git", "path"))
        with self.assertRaises(chest.ChestError):
            chest.add_destination(self.d, "s3", "s3://bucket")
        with self.assertRaises(chest.ChestError):
            chest.add_destination(self.d, "magnemo-cloud", "https://cloud.example")

    def test_max_two_and_sweep_not_configurable(self):
        chest.add_destination(self.d, "path", os.path.join(self.tmp, "b"), label="b")
        chest.add_destination(self.d, "path", os.path.join(self.tmp, "c"), label="c")
        with self.assertRaises(chest.ChestError):
            chest.add_destination(self.d, "path", os.path.join(self.tmp, "d"), label="d")
        with open(chest._cfg_path(self.d)) as f:
            cfg = json.load(f)
        cfg["sweep"] = "off"
        with open(chest._cfg_path(self.d), "w") as f:
            json.dump(cfg, f)
        self.assertEqual(chest.load(self.d)["sweep"], "sentinel")

    def test_copy_inside_vault_refused(self):
        with self.assertRaises(chest.ChestError):
            chest.add_destination(self.d, "path", os.path.join(self.d, "copy"))

    def test_gauge_shows_missing_copies_never_hidden(self):
        self.assertEqual(chest.gauge(self.d), "chest: A ✅ · B — · C —")
        r = doctor.run(self.d, [])
        line = next(x for x in r if x["label"] == "chest")
        self.assertEqual(line["level"], doctor.WARN)
        self.assertIn("ONE place", line["detail"])

    def test_broken_chain_is_refused_in_plain_english(self):
        chest.add_destination(self.d, "path", os.path.join(self.tmp, "b"), label="b")
        chest.push(self.d)
        chest.push(self.d, trigger="manual")
        lines = chest._read_ledger_lines(self.d)
        with open(chest._ledger_path(self.d), "w") as f:      # drop the first entry: the chain now points at nothing
            f.write("\n".join(lines[1:]) + "\n")
        ok, why = chest.verify_chain(self.d)
        self.assertFalse(ok)
        self.assertIn("append-only", why)
        out = chest.restore(os.path.join(self.tmp, "b"), os.path.join(self.tmp, "restored"))
        self.assertTrue(out["doctor_ok"])                      # the drawer copy is intact: it restores
        # now tamper the copy itself to prove refusal
        with open(os.path.join(self.tmp, "b", chest.LEDGER_REL), "w") as f:
            f.write("\n".join(lines[1:]) + "\n")
        with self.assertRaises(chest.ChestError) as cm:
            chest.restore(os.path.join(self.tmp, "b"), os.path.join(self.tmp, "restored2"))
        self.assertIn("Restore refused", str(cm.exception))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "restored2", "_staging")))  # nothing half-restored

    def test_sweep_disable_is_human_and_ledgered(self):
        chest.add_destination(self.d, "path", os.path.join(self.tmp, "b"), label="b")
        chest.push(self.d, no_sweep=True, by="founder")
        kinds = [e["kind"] for e in chest.entries(self.d)]
        self.assertIn("CHEST_SWEEP_DISABLED", kinds)
        self.assertEqual(next(e for e in chest.entries(self.d) if e["kind"] == "CHEST_SWEEP_DISABLED")["by"], "founder")

    def test_events_fire_and_never_block(self):
        chest.add_destination(self.d, "path", os.path.join(self.tmp, "b"), label="b")
        g = Governance(self.v)
        n = g.agent_write(title="t", body="b", partition="dev", store="knowledge", author="a", source="s")
        g.promote(n.id, "founder")
        trig = [e["trigger"] for e in chest.entries(self.d) if e["kind"] == "CHEST_PUSH"]
        self.assertIn("promote", trig)
        # a dead destination never blocks the agent's work
        cfg = chest.load(self.d); cfg["destinations"][0]["target"] = "/dev/null/impossible"; chest.save(self.d, cfg)
        n2 = g.agent_write(title="t2", body="b", partition="dev", store="knowledge", author="a", source="s")
        g.promote(n2.id, "founder")   # must not raise
        self.assertIn("CHEST_FAIL", [e["kind"] for e in chest.entries(self.d)])
        self.assertIn("🟠", chest.gauge(self.d))

    def test_four_verb_server_stays_four(self):
        from magnemo import mcp
        self.assertEqual(len(mcp.tools_spec()), 4)


class TestGauntlet(unittest.TestCase):
    def setUp(self):
        os.environ["MAGNEMO_CHEST_NOW"] = "2026-09-02T00:00:00Z"   # every drill runs on a mocked clock
        self.tmp = tempfile.mkdtemp()
        self.A = os.path.join(self.tmp, "A"); Vault(self.A).init()
        self.remote = _bare(os.path.join(self.tmp, "remote.git"))
        chest.add_destination(self.A, "git", self.remote, label="laptop")

    def tearDown(self):
        shutil.rmtree(self.tmp)
        os.environ.pop("MAGNEMO_CHEST_NOW", None)

    def test_drill_1_kill_the_disk(self):
        chest.add_destination(self.A, "path", os.path.join(self.tmp, "drawer"), label="drawer")   # Copy C too
        _promote_n(self.A, 10)
        res = chest.push(self.A, trigger="manual")
        self.assertEqual([r["status"] for r in res], ["ok", "ok"], res)
        src_sha, src_pack = _pack_sha(self.A)
        self.assertIn("chest: A ✅ · B ✅ 2026-09-02T00:00:00Z · C ✅ 2026-09-02T00:00:00Z", src_pack.decode())
        shutil.rmtree(self.A)                                        # the disk dies
        R = os.path.join(self.tmp, "restored")
        out = chest.restore(self.remote, R)
        self.assertTrue(out["doctor_ok"], out["doctor"])
        r_sha, r_pack = _pack_sha(R)
        self.assertEqual(src_sha, r_sha)                             # byte-identical boot pack
        self.assertEqual(len(Vault(R).canonical()), 10)
        self.assertEqual(out["bootpack_sha256"], r_sha)
        self.__class__.drill1 = (src_sha, r_sha)

    def test_drill_2_plant_a_key(self):
        g = Governance(Vault(self.A))
        bad = g.agent_write(title="Vendor creds", body="here: AKIA" + "Q" * 16 + " (do not commit)",
                            partition="ops", store="knowledge", author="drill", source="drill")
        res = chest.push(self.A, trigger="manual")
        self.assertEqual(res[0]["status"], "blocked")
        self.assertIn("🔴", chest.gauge(self.A))
        sent = [n for n in Vault(self.A).staged() if n.author == "sentinel"]
        self.assertEqual(len(sent), 1)
        self.assertIn(f"_staging/{bad.id}.md", sent[0].body)
        self.assertIn("aws-access-key", sent[0].body)
        self.assertNotIn("AKIA" + "Q" * 16, sent[0].body)              # never the value
        self.assertNotIn("AKIA" + "Q" * 16, sent[0].title)
        # nothing left the machine: the remote has no commits
        r = subprocess.run(["git", "--git-dir", self.remote, "rev-parse", "main"], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        os.remove(os.path.join(self.A, "_staging", f"{bad.id}.md"))   # the keyholder moves the secret out
        res = chest.push(self.A, trigger="manual")
        self.assertEqual(res[0]["status"], "ok", res[0])
        self.assertIn("✅", chest.gauge(self.A).split("·")[1])
        kinds = [e["kind"] for e in chest.entries(self.A)]
        self.assertEqual(kinds.count("CHEST_BLOCKED"), 1)

    def test_drill_3_two_machine_drift(self):
        a_ids = _promote_n(self.A, 2, "a-note")
        chest.push(self.A, trigger="manual")
        B = os.path.join(self.tmp, "B")
        chest.restore(self.remote, B)
        # both sides change since the common ancestor
        a_new = _promote_n(self.A, 1, "a-only")[0]
        b_new = _promote_n(B, 1, "b-only")[0]
        # and B EDITS a note that A also holds — canon must not be overwritten on A
        vb = Vault(B); nb = vb.read(a_ids[0]); a_body_before = Vault(self.A).read(a_ids[0]).body
        nb.body = "B changed this canonical note."; vb.rewrite(nb)
        ra = chest.push(self.A, trigger="manual"); self.assertEqual(ra[0]["status"], "ok", ra[0])
        rb = chest.push(B, trigger="manual");      self.assertEqual(rb[0]["status"], "ok", rb[0])   # non-ff → merge rite
        # B now holds A's new canon as a PROPOSAL, not as canon
        props_b = [n for n in vb.staged() if n.source.startswith("chest:merge from")]
        self.assertTrue(any(n.id.startswith(a_new + "-merge-") for n in props_b))
        self.assertIsNone(vb.find(a_new) if a_new not in vb._canonical_ids() else None)
        self.assertIn("CHEST_MERGE", [e["kind"] for e in chest.entries(B)])
        # A reconverges: B's canon change and B's edit arrive as proposals; A's canon untouched
        ra2 = chest.push(self.A, trigger="manual"); self.assertEqual(ra2[0]["status"], "ok", ra2[0])
        va = Vault(self.A)
        props_a = [n for n in va.staged() if n.source.startswith("chest:merge from")]
        self.assertTrue(any(n.id.startswith(b_new + "-merge-") for n in props_a))
        edit = [n for n in props_a if n.supersedes == a_ids[0]]
        self.assertEqual(len(edit), 1)
        self.assertIn("B changed this canonical note.", edit[0].body)
        self.assertEqual(va.read(a_ids[0]).body, a_body_before)             # nothing overwritten
        self.assertNotIn(b_new, va._canonical_ids())                         # foreign canon is not canon here
        # ledger union: timestamp order, marker present, chain still verifies as a DAG
        ts = [e.get("ts", "") for e in chest.entries(self.A)]
        self.assertEqual(ts, sorted(ts))
        self.assertIn("CHEST_MERGE", [e["kind"] for e in chest.entries(self.A)])
        self.assertTrue(chest.verify_chain(self.A)[0])
        self.assertTrue(chest.verify_chain(B)[0])

    def test_drill_4_ceiling(self):
        chest.push(self.A, trigger="manual")
        self.assertEqual(chest.tick(self.A), [])                              # within the ceiling
        os.environ["MAGNEMO_CHEST_NOW"] = "2026-09-03T00:00:01Z"           # 24h + 1s of silence
        res = chest.tick(self.A)
        self.assertEqual(res[0]["status"], "ok", res[0])
        self.assertEqual(chest.entries(self.A)[-1]["trigger"], "ceiling")

    def test_taint_travels_with_the_copy(self):
        g = Governance(Vault(self.A))
        t = g.agent_write(title="from inbound email", body="claim", partition="ops", store="knowledge",
                          author="drill", source="email#1", taint="inbound-email")
        g.promote(t.id, "founder")
        chest.push(self.A, trigger="manual")
        R = os.path.join(self.tmp, "R"); chest.restore(self.remote, R)
        self.assertEqual(Vault(R).read(t.id).taint, "inbound-email")


if __name__ == "__main__":
    unittest.main()
