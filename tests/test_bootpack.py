import os, shutil, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from magnemo.vault import Vault
from magnemo.governance import Governance
from magnemo import bootpack


class TestBootPack(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.v = Vault(self.dir); self.v.init()
        self.g = Governance(self.v)

    def tearDown(self):
        shutil.rmtree(self.dir)

    def _seed(self, charter=True):
        if charter:
            c = self.g.agent_write(title="The SVTech Charter",
                body="1. Canon is founder-owned.\n2. Agents stage; humans promote.",
                partition="dev", store="decisions", author="founder",
                source="manual", tags="charter,doctrine", impact="process")
            self.g.promote(c.id, "founder", "ratified")
        k = self.g.agent_write(title="Kwik Lube month-end spike",
            body="Volumes spike in the last week of each month.",
            partition="ops", store="knowledge", author="ops-agent",
            source="run#1847", impact="money")
        self.g.promote(k.id, "founder")
        self.g.agent_write(title="Open hardening thread",
            body="Unbounded queries remain.", partition="dev", store="debt",
            author="dev-agent", source="audit#4", tags="debt,open",
            impact="security")
        self.g.agent_write(title="Routine observation",
            body="Formatting drift in reports.", partition="ops",
            store="knowledge", author="ops-agent", source="run#2",
            impact="info")

    def _write_codex(self, text="## Voice\nDry wit. Callsign: Ariadne."):
        d = os.path.join(self.dir, "_codex")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "CODEX.md"), "w") as f:
            f.write(text)

    # ---------------- charter ----------------
    def test_charter_first_and_verbatim(self):
        self._seed()
        pack = bootpack.generate(self.v)
        i_charter = pack.index("## THE CHARTER")
        self.assertIn("Agents stage; humans promote.", pack)  # verbatim body
        for section in ("## CANON DIGEST", "## OPEN THREADS", "## LEDGER TAIL"):
            self.assertGreater(pack.index(section), i_charter)
        self.assertNotIn("CHARTER NOT YET PROMOTED", pack)

    def test_charter_placeholder_never_fabricated(self):
        self._seed(charter=False)
        pack = bootpack.generate(self.v)
        self.assertIn("CHARTER NOT YET PROMOTED", pack)
        self.assertIn("never fabricated", pack)
        # staged-but-unpromoted charter must NOT be served
        self.g.agent_write(title="Draft charter", body="Draft only.",
            partition="dev", store="decisions", author="a", source="s",
            tags="charter")
        pack2 = bootpack.generate(self.v)
        self.assertIn("CHARTER NOT YET PROMOTED", pack2)
        self.assertNotIn("Draft only.", pack2.split("## CANON DIGEST")[0])

    # ---------------- relationship layer / codex seam ----------------
    def test_partner_includes_relationship_layer_when_codex_exists(self):
        self._seed()
        self._write_codex()
        pack = bootpack.generate(self.v, cls="partner")
        self.assertIn("## RELATIONSHIP LAYER", pack)
        self.assertIn("Callsign: Ariadne.", pack)
        # ordering: charter still first, relationship layer before canon
        self.assertLess(pack.index("## THE CHARTER"),
                        pack.index("## RELATIONSHIP LAYER"))
        self.assertLess(pack.index("## RELATIONSHIP LAYER"),
                        pack.index("## CANON DIGEST"))

    def test_worker_never_includes_relationship_layer(self):
        self._seed()
        self._write_codex()
        pack = bootpack.generate(self.v, cls="worker")
        self.assertNotIn("## RELATIONSHIP LAYER", pack)
        self.assertNotIn("Ariadne", pack)

    def test_partner_without_codex_degrades_to_worker_boot(self):
        self._seed()
        partner = bootpack.generate(self.v, cls="partner")
        worker = bootpack.generate(self.v, cls="worker")
        self.assertNotIn("## RELATIONSHIP LAYER", partner)
        # identical except the class stamp in the header
        self.assertEqual(partner.replace("partner boot", "worker boot"), worker)

    def test_codex_source_is_pluggable(self):
        self._seed()
        pack = bootpack.generate(self.v, cls="partner",
                                 codex_source=lambda: "## Lore\nFrom anywhere.")
        self.assertIn("From anywhere.", pack)
        none_pack = bootpack.generate(self.v, cls="partner",
                                      codex_source=lambda: None)
        self.assertNotIn("## RELATIONSHIP LAYER", none_pack)

    # ---------------- digest, queue, ledger ----------------
    def test_canon_digest_titles_summaries_paths(self):
        self._seed()
        pack = bootpack.generate(self.v)
        self.assertIn("**Kwik Lube month-end spike**", pack)
        self.assertIn("Volumes spike in the last week of each month.", pack)
        self.assertIn("(`ops/knowledge/", pack)
        self.assertIn("### ops/knowledge", pack)

    def test_open_threads_staged_count_and_top_salient(self):
        self._seed()
        pack = bootpack.generate(self.v)
        self.assertIn("Open threads: 1", pack)
        self.assertIn("Open hardening thread", pack)
        self.assertIn("Staged notes awaiting review: 2", pack)
        # security+audit note outranks the routine info note
        qsec = pack.index("1. [")
        self.assertLess(qsec, pack.index("Routine observation"))
        self.assertIn("Open hardening thread", pack[qsec:])

    def test_ledger_tail_present(self):
        self._seed()
        pack = bootpack.generate(self.v)
        self.assertIn("## LEDGER TAIL", pack)
        self.assertIn("memory.promote", pack)

    def test_scope_filters_partition(self):
        self._seed()
        pack = bootpack.generate(self.v, scope="dev")
        self.assertIn("scope: dev", pack)
        self.assertNotIn("Kwik Lube", pack)          # ops canon excluded
        self.assertIn("The SVTech Charter", pack)    # charter is vault-wide
        self.assertIn("Staged notes awaiting review: 1", pack)

    # ---------------- determinism ----------------
    def test_byte_stable_per_class(self):
        self._seed()
        self._write_codex()
        for cls in ("worker", "partner"):
            a = bootpack.generate(self.v, cls=cls).encode("utf-8")
            b = bootpack.generate(self.v, cls=cls).encode("utf-8")
            self.assertEqual(a, b, f"{cls} pack not byte-stable")
        self.assertNotEqual(bootpack.generate(self.v, cls="worker"),
                            bootpack.generate(self.v, cls="partner"))

    def test_write_creates_file_in_index(self):
        self._seed()
        path, nbytes = bootpack.write(self.v)
        self.assertEqual(path, os.path.join(self.dir, "_index", "BOOT_PACK.md"))
        self.assertEqual(os.path.getsize(path), nbytes)
        with open(path) as f:
            self.assertTrue(f.read().startswith("# BOOT PACK — magnemo"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
