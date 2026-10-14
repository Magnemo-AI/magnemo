"""THE DIALOG YES, the words (drill D5): the first-run paste and the README's top screen say the action in one sentence
and never send anyone to a terminal. The manual names the command line once."""
import os, re, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SENTENCE = "When your agent writes something down, Magnemo asks you in the chat. One click."


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


@unittest.skipUnless(os.path.exists(os.path.join(ROOT, "README.md")), "the docs are not in this tree")
class TestTheWords(unittest.TestCase):
    def setUp(self):
        self.readme = read("README.md")
        self.top = self.readme.split("## Install in your client")[0]                 # everything before the per-client blocks
        self.paste = re.search(r"```text\n(Set up Magnemo in this project:.*?)```", self.readme, re.S).group(1)

    def test_no_terminal_on_the_top_screen_in_the_paste_or_in_the_install_file(self):
        for name, text in (("the README's top screen", self.top), ("the first-run paste", self.paste), ("llms-install.md", read("llms-install.md"))):
            self.assertEqual(re.findall(r"terminal", text, re.I), [], name)

    def test_the_action_is_said_in_the_one_sentence(self):
        self.assertIn(SENTENCE, self.top)
        self.assertLess(self.top.index(SENTENCE), self.top.index("## Install in one paste"))   # above the paste: the first screen
        self.assertTrue(self.readme.startswith("# Magnemo\n**The Memory MCP. Your AI remembers. You keep what matters.**\n\nMagnemo is a Memory for your AI, kept on your computer in plain files."))   # the founder's lines, Oct 12
        self.assertIn("nothing becomes Memory until you approve it, and every Memory shows who wrote it and who approved it.", self.top)
        self.assertLess(self.top.index("pip install magnemo"), self.top.index("Set up Magnemo in this project:"))   # three lines before the paste
        self.assertIn("## Works with", self.top)
        self.assertIn("Magnemo asks you in the chat to approve it. One click.", self.top)

    def test_the_paste_no_longer_asks_for_a_command_to_approve(self):
        self.assertNotIn("command to approve", self.paste); self.assertNotIn("magnemo yes", self.top)
        self.assertIn("restart you", self.paste)                                    # the tools load at the client's start: the one step that is left

    def test_the_command_line_is_named_once_in_the_manual_and_nowhere_above_it(self):
        manual = read("docs", "MCP.md")
        self.assertEqual(manual.count("the command line is the other door"), 1)       # the manual sends a person there in one place
        self.assertNotIn("The CLI is the other door", self.readme)

    def test_the_limit_is_written_down(self):
        limits = " ".join(read("KNOWN_LIMITS.md").split())
        self.assertIn("It stops a wrong thing from becoming memory without a person; it does not stop a wrong thing from being written.", limits)
        self.assertIn("The question in the chat is drawn by your client, not by Magnemo.", limits)
        self.assertIn("under 300 ms", limits)


if __name__ == "__main__":
    unittest.main()
