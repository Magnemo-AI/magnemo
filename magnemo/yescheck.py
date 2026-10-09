"""magnemo.yescheck — THE YES CHECK: the yes is a person's, and the engine can tell.

The verbs that decide what becomes memory (`yes` · `no` · `clear` · `promote`, their long forms `reject` and
`cleartaint`, and the answers inside `review`) run only when all of this holds:

  1. stdin is a terminal. An agent's shell has none.
  2. MAGNEMO_AGENT is not set. Every MCP server and every seat-run command carries one; a person's terminal does not.
  3. The process is not a child of an MCP server session the engine started.
  4. `--by` names a keyholder in the vault's `trust.humans`. A name that is not there is refused, never defaulted.
     With no `--by`, the first keyholder is used, and only once 1-3 passed.

A refusal is one line that names the gate and the route (the command to type, in the reader's own terminal), and one
line in the trust ledger (`judgment.refused`, with
`catch: yes-check` and `ran_by: refused:<reason>`). It is never silent. The MCP side is unchanged: promotion is not a tool.

ONE OVERRIDE, for a company's own close ritual: `MAGNEMO_YES_RELAY=<keyholder>` lets a terminal session that is not
the keyholder's own carry that keyholder's relayed word. It works only on a terminal, only for a name in
`trust.humans`, only for that name, and the ledger line reads `ran_by: relay:<who ran it>`, so a relay is never
mistaken for the keyholder's own hand. There is no other bypass.

WHAT THIS DOES NOT STOP, said plainly: a program that opens a terminal of its own, clears MAGNEMO_AGENT and names a
keyholder looks like a person to this check. The check stops the plain case, an agent running the command through
its shell tool, and makes every other case leave a line. An agent with your shell and your terminal is still you.
"""
from __future__ import annotations
import os, re, shlex, subprocess, sys
from .config import env, load_config

REFUSED = "judgment.refused"                        # the trust ledger's action class for a yes the engine turned away
SESSION_VAR = "MAGNEMO_MCP_SESSION"                 # set by the MCP server in its own process; its children inherit it
ROUTE = "Type it yourself in a terminal:"         # every refusal ends with this and the command to type
YOURS = {"yes": "yes", "promote": "yes", "review": "yes", "no": "no", "reject": "no", "clear": "clear", "cleartaint": "clear"}
VERBS = ("yes", "no", "clear", "promote", "reject", "cleartaint", "review")
# A process IS the server when the program it runs is: `magnemo-mcp`, `python -m magnemo.mcp`, `magnemo serve`, or
# `python -m magnemo.cli serve`. The words appearing somewhere in another program's arguments (an editor, a shell's -c
# string) do not make it one.
_PY = r"\S*python[\d.]*\s+(?:\S+\s+)*?"
_SERVER = re.compile(r"^(?:" + _PY + r"-m\s+magnemo\.mcp(?:\s|$)|" + _PY + r"-m\s+magnemo\.cli\s+serve(?:\s|$)"
                     r"|(?:\S*python[\d.]*\s+)?(?:\S*/)?magnemo-mcp(?:\s|$)|(?:\S*python[\d.]*\s+)?(?:\S*/)?magnemo\s+serve(?:\s|$))")


NEEDS_BY = ("promote", "reject", "cleartaint")     # the long forms take no default name


def route(verb: str = "yes", argv=None, unlisted: bool = False) -> str:
    """The command to type: the one that was refused, as it was given. When the name it gave is not one the vault
    lists (`unlisted`), that `--by` is left out, or shown as `--by <name>` for a verb that must have one."""
    args = list(argv or [])
    if not args:
        return "magnemo %s <id>" % verb
    kept, skip = [], False
    for a in args:
        if skip:
            skip = False
        elif unlisted and (a == "--by" or a.startswith("--by=")):
            skip = a == "--by"
        else:
            kept.append(shlex.quote(a))
    if unlisted and verb in NEEDS_BY:
        kept.append("--by <name>")
    return "magnemo " + " ".join(kept)


class Refused(Exception):
    """A yes that is not a person's. `code` is the short reason the ledger keeps; `why` is the gate; `line()` is the
    one line shown: the gate, then the route."""
    def __init__(self, code: str, why: str):
        self.code, self.why = code, why
        super().__init__(self.line())

    def line(self, verb: str = "yes", argv=None) -> str:
        unlisted = self.code.startswith(("not-a-keyholder:", "relay-names-another:"))
        yours = "This %s is yours. %s %s" % (YOURS.get(verb, "yes"), ROUTE, route(verb, argv, unlisted))
        if self.code == "no-tty":                  # the plain case, in the stranger's words: an agent, a script, a pipe
            return yours
        return "✗ REFUSED — %s. %s" % (self.why, yours)


def _tty(stdin=None) -> bool:
    s = sys.stdin if stdin is None else stdin
    try:
        return bool(s is not None and s.isatty())
    except (AttributeError, ValueError, OSError):
        return False


def under_mcp_session(environ=None, pid: int | None = None) -> bool:
    """True when this process descends from an MCP server the engine started: the server's marker is in the
    environment, or a `magnemo-mcp` process is among the ancestors (read with `ps`; where that fails, the marker and
    the terminal check stand alone)."""
    e = os.environ if environ is None else environ
    if (e.get(SESSION_VAR) or "").strip():
        return True
    try:
        at = os.getppid() if pid is None else pid
        for _ in range(12):
            if at <= 1:
                return False
            out = subprocess.run(["ps", "-o", "ppid=,command=", "-p", str(at)], capture_output=True, text=True, timeout=3).stdout.strip()
            if not out:
                return False
            parent, _, command = out.partition(" ")
            if _SERVER.search(command.strip()):
                return True
            at = int(parent.strip() or 0)
    except (OSError, ValueError, subprocess.SubprocessError):
        return False
    return False


def check(vault_root: str, by: str = "", environ=None, stdin=None, mcp: bool | None = None):
    """Who the yes is recorded for, and whose hand ran it: (by, ran_by). Raises Refused."""
    from . import trust
    cfg = load_config(vault_root)
    humans = list((cfg.get("trust") or {}).get("humans") or [])
    seat = (env("AGENT", "", environ) or "").strip()
    relay = (env("YES_RELAY", "", environ) or "").strip()
    tty = _tty(stdin)
    named = (by or "").strip()
    if under_mcp_session(environ) if mcp is None else mcp:
        raise Refused("mcp-session", "this command was started from inside an MCP server session; promotion is not one of its tools")
    if relay:
        if not tty:
            raise Refused("relay-no-tty", "a relay needs a terminal too: stdin is not a TTY")
        if not trust.is_human(cfg, relay):
            raise Refused("relay-not-a-keyholder:" + relay, f"MAGNEMO_YES_RELAY names '{relay}', who is not a keyholder (trust.humans: {', '.join(humans) or 'none'})")
        if named and named != relay:
            raise Refused("relay-names-another:" + named, f"the relay carries {relay}'s word, and --by names '{named}'")
        ran_by = "relay:" + (seat or "terminal")
        return relay, ran_by
    if seat:
        raise Refused("seat:" + seat, f"MAGNEMO_AGENT is set to '{seat}': a seat ran this, not a person")
    if not tty:
        raise Refused("no-tty", "stdin is not a terminal")
    who = named or (humans[0] if humans else "founder")
    if not trust.is_human(cfg, who):
        raise Refused("not-a-keyholder:" + who, f"'{who}' is not a keyholder (trust.humans: {', '.join(humans) or 'none'})")
    return who, "terminal"


CLASS = {"yes": "yes", "promote": "yes", "review": "yes", "no": "catch", "reject": "catch", "clear": "catch", "cleartaint": "catch"}


def catch(governance, verb: str, target: str, claimed: str, refused: Refused, environ=None, stdin=None) -> None:
    """The refusal's one line in the trust ledger: the engine caught a yes that was not a person's. The action class
    is `judgment.refused` (`class`: `yes` for a refused yes or promote, `catch` for a refused no or clear); it carries
    `catch: yes-check` and `ran_by: refused:<reason>`. Never raises: a refusal that cannot be written is still a refusal."""
    try:
        seat = (env("AGENT", "", environ) or "").strip()
        governance.ledger.record(REFUSED, "refused", seat or "unknown", target or "-", refused.why,
                                 **{"class": CLASS.get(verb, "yes"), "door": "terminal", "claimed": claimed or "", "verb": verb,
                                    "ran_by": "refused:" + refused.code, "tty": _tty(stdin), "catch": "yes-check"})
    except Exception:  # noqa: BLE001
        pass
