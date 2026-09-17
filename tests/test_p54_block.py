"""P-54 · THE BLOCK, TRUE TO ITS OWN LAW — the door refuses a seat signing as a keyholder,
the gate lift is a word, the record tells the truth about itself, the operator flag is
deterministic. Provenance enforced; promotion still never an MCP tool."""
import os, sys, io, json, shutil, tempfile, unittest, subprocess, contextlib
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from magnemo.vault import Vault
from magnemo.governance import Governance
from magnemo import mcp, cli
from tests.test_mcp import make_server, call


class TestTheDoor(unittest.TestCase):
    """D1: MCP `stage` with author="founder" from seat `agent` → refused, ledgered;
    author="cc-2" → written as author=agent, claimed_author=cc-2."""
    def setUp(self):
        self.tmp = tempfile.mkdtemp(); Vault(self.tmp).init()
        self.s = make_server(self.tmp, MAGNEMO_AGENT="agent")
    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
    def test_a_seat_cannot_sign_as_a_human(self):
        text, err = call(self.s, "stage", note={"title": "t", "body": "b", "partition": "dev", "store": "knowledge"},
                         provenance={"source": "drill-D1", "author": "founder"})
        self.assertTrue(err); self.assertIn("cannot sign as a keyholder", text)
        self.assertEqual([n for n in Vault(self.tmp).staged() if n.status == "staged"], [])
        led = Governance(Vault(self.tmp)).ledger.entries()
        denied = [e for e in led if e.get("verdict") == "denied" and e.get("subject") == "agent"]
        self.assertTrue(denied, "the refusal is ledgered as a stage denial for the seat")
        self.assertIn("claimed author 'founder'", denied[-1].get("reason", "") + denied[-1].get("detail", ""))
    def test_a_claimed_non_human_author_is_kept_beside_the_seat(self):
        text, err = call(self.s, "stage", note={"title": "t2", "body": "b2", "partition": "dev", "store": "knowledge"},
                         provenance={"source": "drill-D1", "author": "cc-2"})
        self.assertFalse(err, text)
        nid = json.loads(text)["staged"]
        n = Vault(self.tmp).read(nid)
        self.assertEqual(n.author, "agent")
        self.assertEqual(n.extra.get("claimed_author"), "cc-2")
        self.assertIn("magnemo yes", json.loads(text)["note"])
    def test_the_seat_signs_as_itself_without_a_claim(self):
        text, err = call(self.s, "stage", note={"title": "t3", "body": "b3", "partition": "dev", "store": "knowledge"},
                         provenance={"source": "drill-D1"})
        self.assertFalse(err, text)
        n = Vault(self.tmp).read(json.loads(text)["staged"])
        self.assertEqual(n.author, "agent"); self.assertNotIn("claimed_author", n.extra)


def run_cli(argv, env=None):
    e = dict(os.environ); e.pop("MAGNEMO_AGENT", None); e.update(env or {})
    p = subprocess.run([sys.executable, "-m", "magnemo.cli"] + argv, capture_output=True, text=True, env=e, cwd=ROOT)
    return p.returncode, p.stdout + p.stderr


class TestTheWord(unittest.TestCase):
    """D2: `yes` promotes the top of the queue with by=founder, reason="approved in chat",
    ran_by=<seat|terminal>; an ambiguous fragment refuses; `no` without --reason refuses."""
    def setUp(self):
        self.tmp = tempfile.mkdtemp(); Vault(self.tmp).init()
        self.g = Governance(Vault(self.tmp))
        self.a = self.g.agent_write(title="alpha one", body="a", partition="dev", store="knowledge", author="agent", source="d2")
        self.b = self.g.agent_write(title="alpha two", body="b", partition="dev", store="knowledge", author="agent", source="d2")
    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
    def _promotions(self):
        return [e for e in Governance(Vault(self.tmp)).ledger.entries("memory.promote")]
    def test_yes_promotes_the_top_with_the_seat_on_the_record(self):
        rc, out = run_cli(["yes", self.tmp], env={"MAGNEMO_AGENT": "agent"})
        self.assertEqual(rc, 0, out); self.assertIn("PROMOTED", out)
        e = self._promotions()[-1]
        self.assertEqual(e["verdict"], "approved"); self.assertEqual(e["actor"], "founder")
        self.assertEqual(e["detail"], "approved in chat"); self.assertEqual(e["ran_by"], "agent")
        top = [n for n in Vault(self.tmp).staged() if n.status == "staged"]
        self.assertEqual(len(top), 1)
    def test_yes_from_a_terminal_records_terminal(self):
        rc, out = run_cli(["yes", "alpha-one", self.tmp])
        self.assertEqual(rc, 0, out)
        self.assertEqual(self._promotions()[-1]["ran_by"], "terminal")
    def test_an_ambiguous_fragment_refuses_and_lists(self):
        rc, out = run_cli(["yes", "alpha", self.tmp])
        self.assertNotEqual(rc, 0); self.assertIn("2 staged notes match", out)
        self.assertIn(self.a.id, out); self.assertIn(self.b.id, out)
        self.assertEqual(self._promotions(), [])
    def test_yes_all_writes_one_entry_per_note(self):
        rc, out = run_cli(["yes", "--all", self.tmp])
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(self._promotions()), 2)
        self.assertTrue(all(e.get("ran_by") == "terminal" for e in self._promotions()))
    def test_no_requires_a_reason(self):
        rc, out = run_cli(["no", "alpha-one", self.tmp])
        self.assertNotEqual(rc, 0); self.assertIn("--reason", out)
        rc, out = run_cli(["no", "alpha-one", "--reason", "not true", self.tmp], env={"MAGNEMO_AGENT": "agent"})
        self.assertEqual(rc, 0, out)
        e = self._promotions()[-1]
        self.assertEqual(e["verdict"], "rejected"); self.assertEqual(e["detail"], "not true"); self.assertEqual(e["ran_by"], "agent")
    def test_promote_long_form_is_unchanged(self):
        rc, out = run_cli(["promote", self.a.id, self.tmp])
        self.assertNotEqual(rc, 0); self.assertIn("--by", out)
        rc, out = run_cli(["promote", self.a.id, "--by", "founder", self.tmp])
        self.assertEqual(rc, 0, out); self.assertNotIn("ran_by", self._promotions()[-1])


class TestTheCount(unittest.TestCase):
    """D3: the four tools stay four; `yes` is never a tool."""
    def test_tool_names_are_the_four(self):
        self.assertEqual(mcp.TOOL_NAMES, ("retrieve", "stage", "bootpack", "handoff"))
        self.assertEqual([t["name"] for t in mcp.tools_spec()], list(mcp.TOOL_NAMES))
    def test_the_boot_line_reports_the_queue(self):
        tmp = tempfile.mkdtemp(); Vault(tmp).init()
        try:
            g = Governance(Vault(tmp)); g.agent_write(title="q", body="q", partition="dev", store="knowledge", author="agent", source="d3")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                make_server(tmp, MAGNEMO_AGENT="agent")
            self.assertIn("queue=1", err.getvalue())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestTheOperatorFlag(unittest.TestCase):
    """Item 4: a note staged by a keyholder's own hand carries the operator tag; an agent's does not."""
    def test_human_hand_gets_the_tag(self):
        tmp = tempfile.mkdtemp(); Vault(tmp).init()
        try:
            rc, out = run_cli(["stage", "by the founder", "--body", "x", "--partition", "dev", "--store", "knowledge", "--source", "hand", "--author", "founder", tmp])
            self.assertEqual(rc, 0, out)
            rc, out2 = run_cli(["stage", "by an agent", "--body", "y", "--partition", "dev", "--store", "knowledge", "--source", "run", "--author", "cc", tmp])
            self.assertEqual(rc, 0, out2)
            notes = {n.title: n for n in Vault(tmp).staged()}
            self.assertIn("founder-flag", notes["by the founder"].tags.split(","))
            self.assertNotIn("founder-flag", notes["by an agent"].tags.split(","))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestTheVersionFlag(unittest.TestCase):
    def test_version_prints_the_one_version(self):
        import magnemo
        rc, out = run_cli(["--version"])
        self.assertEqual((rc, out.strip()), (0, "magnemo " + magnemo.__version__))


if __name__ == "__main__":
    unittest.main()
