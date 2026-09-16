import json, os, shutil, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from magnemo.vault import Vault, Note
from magnemo.governance import Governance
from magnemo.config import load_config, config_path, DEFAULTS
from magnemo import kairos


class TestKairos(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.v = Vault(self.dir); self.v.init()
        self.g = Governance(self.v)
        self.cfg = load_config(self.dir)

    def tearDown(self):
        shutil.rmtree(self.dir)

    def _write(self, title="t", body="b", impact="info", source="run#1",
               partition="ops", store="knowledge", tags=""):
        return self.g.agent_write(title=title, body=body, partition=partition,
                                  store=store, author="a", source=source,
                                  tags=tags, impact=impact)

    # ---------------- component: consequence ----------------
    def test_consequence_class_ordering(self):
        order = ["security", "money", "correctness", "process", "info"]
        scores = [kairos.consequence(Note(id="x", title="t", author="a",
                  written="w", source="s", status="staged", partition="ops",
                  store="knowledge", impact=i), self.cfg) for i in order]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertTrue(all(scores[i] > scores[i + 1] for i in range(len(scores) - 1)))

    def test_consequence_unknown_impact_falls_back_to_default(self):
        n = Note(id="x", title="t", author="a", written="w", source="s",
                 status="staged", partition="ops", store="knowledge",
                 impact="apocalyptic")
        self.assertEqual(kairos.consequence(n, self.cfg),
                         self.cfg["kairos"]["impact_classes"]["info"])

    # ---------------- component: novelty ----------------
    def test_novelty_empty_canon_is_fully_novel(self):
        n = self._write(title="First ever note", body="Something new entirely.")
        comps = json.loads(n.salience_components)
        self.assertEqual(comps["novelty"], 1.0)

    def test_novelty_drops_for_near_duplicate_of_canon(self):
        a = self._write(title="Kwik Lube month-end spike",
                        body="Volumes spike 35 percent in the last week of each month.")
        self.g.promote(a.id, "founder")
        dup = self._write(title="Kwik Lube month-end spike",
                          body="Volumes spike 35 percent in the last week of each month.")
        fresh = self._write(title="Delta Marine contamination Fridays",
                            body="Three contaminated loads in thirty days, all on Fridays.")
        cd = json.loads(dup.salience_components)["novelty"]
        cf = json.loads(fresh.salience_components)["novelty"]
        self.assertLess(cd, 0.2)
        self.assertGreater(cf, 0.7)
        self.assertLess(cd, cf)

    def test_novelty_only_compares_same_partition(self):
        a = self._write(title="Ops fact one", body="The rate card is forty dollars.",
                        partition="ops")
        self.g.promote(a.id, "founder")
        # identical text staged into dev: ops canon must not dent its novelty
        d = self._write(title="Ops fact one", body="The rate card is forty dollars.",
                        partition="dev", store="knowledge")
        self.assertEqual(json.loads(d.salience_components)["novelty"], 1.0)

    def test_novelty_tag_overlap_counts(self):
        a = self._write(title="Alpha", body="Completely unrelated body text.",
                        tags="audit,security,auth")
        self.g.promote(a.id, "founder")
        b = self._write(title="Zeta", body="Different words in every way here.",
                        tags="audit,security,auth")
        self.assertLess(json.loads(b.salience_components)["novelty"], 0.5)

    # ---------------- component: operator signal ----------------
    def test_flag_sets_operator_component_and_ledger(self):
        n = self._write(title="A note", body="Body.")
        self.assertEqual(json.loads(n.salience_components)["operator"], 0.0)
        self.g.flag(n.id, "founder", "matters")
        n2 = self.v.read(n.id)
        self.assertEqual(json.loads(n2.salience_components)["operator"], 1.0)
        self.assertIn(self.cfg["kairos"]["operator_tag"], n2.tags)
        self.assertEqual(len(self.g.ledger.entries("memory.flag")), 1)
        self.assertGreater(n2.salience, n.salience)

    def test_flag_requires_staged(self):
        n = self._write()
        self.g.promote(n.id, "founder")
        with self.assertRaises(ValueError):
            self.g.flag(n.id, "founder")

    # ---------------- component: source weight ----------------
    def test_source_weight_tiers(self):
        audit = self._write(title="From audit", body="x", source="audit#3")
        pm = self._write(title="From postmortem", body="y", source="postmortem-aug13")
        routine = self._write(title="From run", body="z", source="run#1847")
        ca = json.loads(audit.salience_components)["source"]
        cp = json.loads(pm.salience_components)["source"]
        cr = json.loads(routine.salience_components)["source"]
        self.assertEqual(ca, self.cfg["kairos"]["source_classes"]["audit"])
        self.assertEqual(cp, self.cfg["kairos"]["source_classes"]["postmortem"])
        self.assertEqual(cr, self.cfg["kairos"]["default_source_weight"])
        self.assertGreater(ca, cr)

    # ---------------- the gate: flag beats unflagged security ----------------
    def test_founder_flag_beats_unflagged_security_note(self):
        sec = self._write(title="Unflagged security finding",
                          body="Auth bypass on the login regex.",
                          impact="security", source="audit#2")  # max unflagged
        info = self._write(title="Routine info note",
                           body="Minor observation about formatting.",
                           impact="info", source="run#9")
        self.g.flag(info.id, "founder")
        queue = kairos.sorted_queue([self.v.read(sec.id), self.v.read(info.id)])
        self.assertEqual(queue[0].id, info.id)
        # structural invariant: operator weight exceeds the sum of the rest
        w = self.cfg["kairos"]["weights"]
        self.assertGreater(w["operator"],
                           w["consequence"] + w["novelty"] + w["source"])

    # ---------------- storage + ordering + batch ----------------
    def test_staging_stores_salience_in_frontmatter(self):
        n = self._write(title="Stored", body="Salience lives in the file.")
        path = os.path.join(self.dir, "_staging", f"{n.id}.md")
        with open(path) as f:
            text = f.read()
        self.assertIn("salience:", text)
        self.assertIn("salience_components:", text)
        self.assertIn("impact:", text)
        n2 = Note.from_markdown(text)
        self.assertEqual(n2.salience, n.salience)
        self.assertEqual(json.loads(n2.salience_components),
                         json.loads(n.salience_components))

    def test_review_queue_sorted_desc_with_batch_cap(self):
        lo = self._write(title="Low", body="a", impact="info")
        hi = self._write(title="High", body="b", impact="security", source="audit#1")
        mid = self._write(title="Mid", body="c", impact="correctness")
        staged = [n for n in self.v.staged() if n.status == "staged"]
        q = kairos.sorted_queue(staged)
        sals = [n.salience for n in q]
        self.assertEqual(sals, sorted(sals, reverse=True))
        self.assertEqual(q[0].id, hi.id)
        self.assertEqual(len(kairos.sorted_queue(staged, batch=2)), 2)
        self.assertEqual(kairos.sorted_queue(staged, batch=2)[0].id, hi.id)

    def test_unscored_legacy_notes_sort_last_and_rescore_fixes(self):
        n = self._write(title="Modern", body="scored at stage time")
        legacy = Note(id="00000000-legacy", title="Legacy", author="a",
                      written="2026-01-01T00:00:00Z", source="run#0",
                      status="staged", partition="ops", store="knowledge",
                      body="old note without salience")
        legacy.salience = -1.0
        self.v.stage(legacy)
        staged = [x for x in self.v.staged() if x.status == "staged"]
        q = kairos.sorted_queue(staged)
        self.assertEqual(q[-1].id, legacy.id)
        touched = self.g.rescore()
        self.assertEqual(len(touched), 2)
        self.assertGreaterEqual(self.v.read(legacy.id).salience, 0.0)

    def test_rewrite_preserves_unknown_frontmatter_keys(self):
        n = self._write(title="Carrier", body="Has a custom key.")
        path = os.path.join(self.dir, "_staging", f"{n.id}.md")
        with open(path) as f:
            text = f.read()
        text = text.replace("---\n\n#", "task: custom pipeline field\n---\n\n#", 1)
        with open(path, "w") as f:
            f.write(text)
        self.g.flag(n.id, "founder")  # triggers a rewrite
        with open(path) as f:
            after = f.read()
        self.assertIn("task: custom pipeline field", after)
        self.assertEqual(Note.from_markdown(after).extra["task"],
                         "custom pipeline field")

    # ---------------- determinism + config ----------------
    def test_score_is_deterministic(self):
        n = self._write(title="Det", body="same in, same out", impact="money",
                        source="gate#4")
        s1, c1 = kairos.score(n, self.v.canonical("ops"), self.cfg)
        s2, c2 = kairos.score(n, self.v.canonical("ops"), self.cfg)
        self.assertEqual((s1, c1), (s2, c2))
        self.assertEqual(n.salience, s1)

    def test_config_file_created_and_overrides_apply(self):
        p = config_path(self.dir)
        self.assertTrue(os.path.exists(p))
        with open(p) as f:
            on_disk = json.load(f)
        self.assertEqual(on_disk["kairos"]["weights"],
                         DEFAULTS["kairos"]["weights"])
        # founder edits: crank consequence weighting scheme
        on_disk["review"]["batch"] = 3
        with open(p, "w") as f:
            json.dump(on_disk, f)
        self.assertEqual(load_config(self.dir)["review"]["batch"], 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
