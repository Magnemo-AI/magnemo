"""P-93 · THE HONEST PAGE — the docs a stranger reads say what the code does, and nothing stronger; and the suite
runs where a stranger can see it. These tests hold the words, so a claim cannot drift back in."""
import os, re, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHELF = os.path.join(ROOT, "registry", "public-root")            # the private tree keeps the public root's files here
if not os.path.isdir(SHELF):
    SHELF = ROOT                                                 # the public tree keeps them at its root
PAGES = ("README.md", "KNOWN_LIMITS.md", os.path.join("docs", "MCP.md"))     # these are rendered on magnemo.ai


def read(*parts) -> str:
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


def prose(text: str) -> str:
    """The words a reader meets: no code blocks, no code spans, no badge pictures."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    return re.sub(r"`[^`\n]*`", " ", text).replace("![", "[")


class TestTheYesIsSaidAsItIs(unittest.TestCase):
    """Until the CLI checks who runs `magnemo yes`, the words say "promotion is not an MCP tool" and nothing stronger."""

    def test_no_page_promises_that_only_a_person_can_promote(self):
        for name in PAGES + ("llms-install.md",):
            text = " ".join(read(ROOT, name).lower().split())
            for claim in ("until you say yes", "is a person's click", "it is your act, always", "keyholders alone promote",
                          "nothing is kept until they approve", "waits in a review queue for your yes",
                          "invisible until you promote", "only on your yes", "who promoted it", "zero network calls"):
                self.assertNotIn(claim, text, f"{name}: {claim}")

    def test_the_limit_is_written_down_where_the_limits_are(self):
        limits = " ".join(read(ROOT, "KNOWN_LIMITS.md").split())
        self.assertIn("**The yes is not checked yet.**", limits)
        self.assertIn("`magnemo yes` itself takes no credential", limits)
        self.assertIn("Promotion is not an MCP tool", limits)
        self.assertIn("KNOWN_LIMITS.md", read(ROOT, "README.md").split("Agents get four MCP tools. Promotion is not one of them.")[1][:400])
        self.assertIn("An agent that has a shell running `magnemo yes` itself", read(ROOT, "SECURITY.md"))
        self.assertIn("or the first keyholder's name when none is given", limits)

    def test_the_network_sentence_says_what_doctor_checks_and_names_the_push(self):
        readme = " ".join(read(ROOT, "README.md").split())
        self.assertIn("The package imports no network module", readme)
        self.assertIn("the only traffic is `git push` to a backup destination, if you add one", readme)
        self.assertIn("def network_surface", read(ROOT, "magnemo", "doctor.py"))     # the scan the sentence names
        self.assertIn("def _git_push", read(ROOT, "magnemo", "chest.py"))            # and the push it admits

    def test_what_the_mcp_door_does_prove_is_still_said(self):
        self.assertIn("Agents get four MCP tools. Promotion is not one of them.", read(ROOT, "README.md"))
        self.assertIn("Nothing an agent can call through this server moves a", read(ROOT, "docs", "MCP.md"))
        self.assertIn("Through the MCP server, agent writes NEVER reach canonical stores directly", read(ROOT, "README.md"))


class TestOneTruthInEveryPlace(unittest.TestCase):
    def test_one_python_number(self):
        floor = re.search(r'requires-python\s*=\s*">=(\d+\.\d+)"', read(ROOT, "pyproject.toml")).group(1)
        for name in ("README.md", "CONTRIBUTING.md", "KNOWN_LIMITS.md", "llms-install.md", os.path.join("docs", "MCP.md")):
            said = set(re.findall(r"[Pp]ython\s*(?:>=|≥)?\s*(\d\.\d+)", read(ROOT, name)))
            said -= {"3.9", "3.12"} if name == "README.md" else set()          # the README also names the CI's three Pythons
            self.assertLessEqual(said, {floor}, f"{name} names Python {sorted(said)}; pyproject says {floor}")

    def test_one_client_is_called_tested_and_it_is_the_one_with_a_receipt(self):
        readme = read(ROOT, "README.md")
        tested = re.findall(r"^\*\*([^*]+)\*\* — tested", readme, re.M)
        self.assertEqual(tested, ["Claude Code"])
        self.assertIn("**Claude Desktop** — untested end to end here.", readme)
        self.assertIn("**One client is tested.** Claude Code.", " ".join(read(ROOT, "KNOWN_LIMITS.md").split()))

    def test_the_paste_is_addressed_to_the_client_mount_writes_for(self):
        readme = " ".join(read(ROOT, "README.md").split())
        self.assertNotIn("Cursor, Windsurf, or anything that speaks MCP)", readme)
        self.assertIn("`magnemo mount` step writes `.mcp.json`, the file Claude Code reads", readme)
        cli = read(ROOT, "magnemo", "cli.py")                    # and that is what the code does: one file, .mcp.json by default
        self.assertIn('s.add_argument("--file", default=".mcp.json"', cli)

    def test_no_signature_and_no_wiring_is_claimed(self):
        for name in PAGES:
            text = read(ROOT, name).lower()
            self.assertNotIn("every entry signed", text, name)
            self.assertNotIn("wired together", text, name)


class TestTheWordsLaw(unittest.TestCase):
    """The pages magnemo.ai renders: no "we", no exclamation mark, and the D5 word nowhere."""

    def test_the_rendered_docs_hold_it(self):
        for name in PAGES:
            words = prose(read(ROOT, name))
            self.assertEqual(re.findall(r"\b(?:we|our|ours)\b", words, re.I), [], name)
            self.assertEqual([m for m in re.findall(r"\bus\b", words, re.I) if m != "US"], [], name)
            self.assertNotIn("!", words, name)
            self.assertEqual(re.findall(r"\bhuman\b", words, re.I), [], name)


class TestTheSuiteRunsInPublic(unittest.TestCase):
    WF = os.path.join(SHELF, ".github", "workflows", "test.yml")

    def test_the_workflow_runs_the_whole_suite_on_three_pythons_on_every_push(self):
        wf = read(self.WF)
        self.assertRegex(wf, r"(?m)^on:\n  push:\n  pull_request:\n")
        self.assertIn('python-version: ["3.9", "3.11", "3.12"]', wf)
        self.assertIn("run: python -W ignore -m unittest discover -s tests", wf)
        self.assertIn("fail-fast: false", wf)                     # one Python failing does not hide the others

    def test_it_holds_no_secret_and_can_write_nothing(self):
        wf = read(self.WF)
        self.assertRegex(wf, r"(?m)^permissions:\n  contents: read\n")
        self.assertNotIn("secrets.", wf); self.assertNotIn("pull_request_target", wf)
        self.assertIn("persist-credentials: false", wf)
        uses = re.findall(r"uses:\s*(\S+)", wf)
        self.assertEqual(len(uses), 2)
        for u in uses:                                            # a tag can be moved; a commit cannot
            self.assertRegex(u, r"^actions/(checkout|setup-python)@[0-9a-f]{40}$")
        self.assertIn("runs-on: ubuntu-24.04", wf)                # Python 3.9 is not built for newer runner images

    def test_the_readme_shows_the_runs(self):
        readme = read(ROOT, "README.md")
        self.assertIn("actions/workflows/test.yml/badge.svg", readme)
        self.assertIn("The same suite runs on every push, on Python 3.9, 3.11 and 3.12", readme)


if __name__ == "__main__":
    unittest.main()
