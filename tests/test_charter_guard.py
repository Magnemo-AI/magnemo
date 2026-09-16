"""P-08 guard: exactly one canonical note carries the charter tag, and every
boot pack opens with it. Found live on 2026-08-22 when a promoted design
note tagged `charter` out-sorted the Charter itself."""
import os, shutil, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from magnemo.vault import Vault
from magnemo.governance import Governance
from magnemo.config import load_config
from magnemo import bootpack
from magnemo.bootpack import _tagset

REPO_VAULT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vault")


def charter_notes(vault, cfg):
    tag = cfg["bootpack"]["charter_tag"].strip().lower()
    return [n for n in vault.canonical() if tag in _tagset(n)]


@unittest.skipUnless(os.path.isdir(REPO_VAULT), "the repo's dogfood vault is private — not in the public tree")
class TestRepoVaultCharter(unittest.TestCase):
    """The real vault: one Charter, and the pack opens with it."""
    def test_exactly_one_canonical_charter(self):
        v = Vault(REPO_VAULT)
        hits = charter_notes(v, load_config(REPO_VAULT))
        self.assertEqual([n.id for n in hits], ["20260822-the-charter-canonical-memory-1-a7eccaa2"])

    def test_bootpack_opens_with_the_charter(self):
        v = Vault(REPO_VAULT)
        pack = bootpack.generate(v)
        section = pack.split("## THE CHARTER", 1)[1].split("## ", 1)[0]
        self.assertIn("`shared/changelog/20260822-the-charter-canonical-memory-1-a7eccaa2.md`", section)
        self.assertIn("You've booted into Magnemo", section)
        self.assertNotIn("Remanence", pack)


class TestCharterSelection(unittest.TestCase):
    """Unit: a lower-id canonical note that merely carries the tag must not
    displace the Charter. The guard is the count; the pack test is the symptom."""
    def setUp(self):
        self.dir = tempfile.mkdtemp(); self.v = Vault(self.dir); self.v.init(); self.g = Governance(self.v)

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_two_charter_tags_is_a_detectable_collision(self):
        a = self.g.agent_write(title="Design note about charter-first", body="doctrine", partition="dev",
                               store="decisions", author="x", source="s", tags="design,charter")
        b = self.g.agent_write(title="THE CHARTER", body="To whoever wakes", partition="shared",
                               store="changelog", author="founder", source="s", tags="charter")
        self.g.promote(a.id, "founder"); self.g.promote(b.id, "founder")
        self.assertEqual(len(charter_notes(self.v, load_config(self.dir))), 2)   # the guard fires here
        # and the symptom: with the collision, the pack may open with the wrong note
        pack = bootpack.generate(self.v)
        self.assertIn("## THE CHARTER", pack)
        # fix = drop the tag from the design note; the pack then opens with the Charter
        a2 = self.v.read(a.id); a2.tags = "design"; self.v.rewrite(a2)
        self.assertEqual([n.id for n in charter_notes(self.v, load_config(self.dir))], [b.id])
        section = bootpack.generate(self.v).split("## THE CHARTER", 1)[1].split("## ", 1)[0]
        self.assertIn("To whoever wakes", section); self.assertNotIn("doctrine", section)


if __name__ == "__main__":
    unittest.main()
