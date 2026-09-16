"""Regression for the 2026-08-20 ghost: after `promote`, the staging copy must be
CONSUMED — the id must not appear as an active staged candidate anywhere (review
queue, bootpack top-N, rescore, the filesystem), and exactly one file carries it."""
import os, sys, json, shutil, tempfile, unittest, subprocess
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from magnemo.vault import Vault
from magnemo.governance import Governance
from magnemo import kairos, bootpack
from magnemo.search import Index


def all_paths_for(vault_dir, note_id):
    hits = []
    for base, _d, files in os.walk(vault_dir):
        if f"{note_id}.md" in files:
            hits.append(os.path.relpath(os.path.join(base, f"{note_id}.md"), vault_dir))
    return sorted(hits)


class TestPromoteConsumesStaging(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.v = Vault(self.d); self.v.init()
        self.g = Governance(self.v)
        self.n = self.g.agent_write(title="THE CHARTER — test", body="To whoever wakes: be honest.",
                                    partition="shared", store="changelog", author="The Founder",
                                    source="founder/boardroom", tags="charter", impact="process")
        # a second staged note so queues are non-trivial
        self.other = self.g.agent_write(title="Other candidate", body="unrelated", partition="dev",
                                        store="knowledge", author="a", source="run#1")

    def tearDown(self):
        shutil.rmtree(self.d)

    def _assert_consumed(self, nid):
        # filesystem: exactly one file, and it is canonical, not in _staging
        paths = all_paths_for(self.d, nid)
        self.assertEqual(len(paths), 1, paths)
        self.assertFalse(paths[0].startswith("_staging"), paths)
        self.assertFalse(os.path.exists(os.path.join(self.d, "_staging", f"{nid}.md")))
        self.assertEqual(self.v.read(nid).status, "canonical")
        # review queue (what `cli review` iterates)
        staged = [n for n in self.v.staged() if n.status == "staged"]
        self.assertNotIn(nid, [n.id for n in staged])
        self.assertNotIn(nid, [n.id for n in kairos.sorted_queue(staged, 50)])
        # bootpack: appears in CANON DIGEST / CHARTER, never in the review-queue top-N
        pack = bootpack.generate(self.v)
        queue_section = pack.split("## OPEN THREADS & REVIEW QUEUE")[1].split("## LAST HANDOFF")[0]
        self.assertNotIn(nid, queue_section)
        self.assertIn("Staged notes awaiting review: 1", queue_section)
        # rescore touches staged notes only
        touched = self.g.rescore()
        self.assertNotIn(nid, [n.id for n in touched])
        self.assertEqual(self.v.read(nid).status, "canonical")
        # MCP-side views: retrieve sees it as canon; list of staged does not
        self.assertIn(nid, [r["id"] for r in Index(self.v).search("honest", log_receipt=False)["results"]])

    def test_governance_promote_consumes_staging(self):
        self.g.promote(self.n.id, "The Founder", "Canonical Memory #1")
        self._assert_consumed(self.n.id)
        self.assertEqual(all_paths_for(self.d, self.n.id), [f"shared/changelog/{self.n.id}.md"])

    def test_cli_promote_consumes_staging(self):
        p = subprocess.run([sys.executable, "-m", "magnemo.cli", "promote", self.n.id,
                            "--by", "The Founder", "--reason", "Canonical Memory #1", self.d],
                           capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("PROMOTED", p.stdout)
        self._assert_consumed(self.n.id)

    def test_promote_is_not_repeatable(self):
        self.g.promote(self.n.id, "The Founder")
        with self.assertRaises(ValueError):
            self.g.promote(self.n.id, "The Founder")   # already canonical — no second ledger entry
        self.assertEqual(len(self.g.ledger.entries("memory.promote")), 1)
        self.assertEqual(len(all_paths_for(self.d, self.n.id)), 1)

    def test_ghost_is_detected_if_it_ever_appears(self):
        """If a stale staging copy is re-introduced from outside (e.g. a VCS checkout),
        the vault must report the id as NOT staged: canon wins, and the duplicate is visible."""
        self.g.promote(self.n.id, "The Founder")
        ghost = os.path.join(self.d, "_staging", f"{self.n.id}.md")
        with open(ghost, "w") as f:                      # simulate the Aug-20 ghost
            f.write(self.v.read(self.n.id).to_markdown().replace("status: canonical", "status: staged"))
        self.assertEqual(len(all_paths_for(self.d, self.n.id)), 2)
        # the vault's view of "active staged candidates" must exclude ids that are already canonical
        staged_ids = [n.id for n in self.v.staged() if n.status == "staged"]
        self.assertNotIn(self.n.id, staged_ids)
        self.assertEqual(self.v.read(self.n.id).status, "canonical")   # read resolves to canon
        self.assertIn(self.n.id, self.v.ghosts())                        # and the ghost is reported


if __name__ == "__main__":
    unittest.main()
