"""A person's terminal for the drills (P-97): runs a command with stdin on a pseudo-terminal, the way a person's own
shell does. The yes check refuses the human verbs without one, so a drill that plays the keyholder runs through here;
a drill that plays an agent's shell uses a plain subprocess, which has no terminal."""
import os, pty, subprocess


HUMAN_VERBS = ("yes", "no", "clear", "promote", "reject", "cleartaint")


def run(cmd, **kw):
    """subprocess.run(cmd, capture_output=True, text=True, **kw). For a keyholder's verb, stdin is a terminal; for any
    other command it is empty, as before (a command that would wait on a terminal's keys must not hang a drill)."""
    kw.setdefault("timeout", 120)
    if not any(a in HUMAN_VERBS for a in cmd[:4]):
        return subprocess.run(cmd, capture_output=True, text=True, input="", **kw)
    lead, follow = pty.openpty()
    try:
        return subprocess.run(cmd, stdin=follow, capture_output=True, text=True, **kw)
    finally:
        os.close(lead); os.close(follow)
