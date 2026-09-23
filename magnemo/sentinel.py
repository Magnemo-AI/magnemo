"""magnemo.sentinel — the shared sweep: secret formats and injection patterns.

Sentinel guards the GATE (stage → canon) and the COPY (chest push). It never
quotes a matched value back; it names the pattern. S1–S13 are the injection
shapes an agent's context can carry; a hit taints the note and raises an alert.

THE FOUR DOORS (P-74): the chest push (blocks), the inbox (holds a secret, taints an
injection + an ALERT note), the Room (redacts a secret, taints an injection), and
`stage` — the MCP tool and the CLI verb — through `gate()` below: a secret never
lands (the body becomes the redaction line), an injection stages tainted beside an
ALERT note. `retrieve` never serves a tainted note to an agent until a keyholder
clears it (`magnemo clear`). What Sentinel is today: a deterministic sweep — secret
formats and thirteen instruction shapes, regex, no model — at every door a memory
enters by. What it is not yet: a reviewer that understands intent.
"""
from __future__ import annotations
import re

INJECTION = [
    ("S1-ignore-instructions", re.compile(r"(?i)\bignore\s+(all\s+|the\s+|any\s+|previous\s+|prior\s+)?(instructions?|rules?|the\s+founder|the\s+human)")),
    ("S2-disregard", re.compile(r"(?i)\bdisregard\s+(all\s+|the\s+|your\s+)?(instructions?|rules?|governance|the\s+ledger)")),
    ("S3-merge-now", re.compile(r"(?i)\b(merge|ship|deploy|publish)\s+(it\s+)?now\b")),
    ("S4-promote-now", re.compile(r"(?i)\b(promote|approve|canonize)\s+(this|it|everything|the\s+note)\b")),
    ("S5-you-are-now", re.compile(r"(?i)\byou\s+are\s+now\s+(a|an|the|in)\b")),
    ("S6-system-prompt", re.compile(r"(?i)\b(system\s+prompt|developer\s+message)\b")),
    ("S7-bypass", re.compile(r"(?i)\b(bypass|skip|disable)\s+(the\s+)?(sweep|sentinel|review|gate|permission|approval|guard)")),
    ("S8-impersonate-authority", re.compile(r"(?i)\b(as|i\s+am)\s+the\s+founder\b.*\b(authorize|approve|order)")),
    ("S9-act-without-approval", re.compile(r"(?i)\bwithout\s+(human\s+)?(approval|review|the\s+founder)")),
    ("S10-exfiltrate", re.compile(r"(?i)\b(send|post|upload|exfiltrate)\s+(the\s+|all\s+)?(keys?|tokens?|secrets?|credentials?|vault)\b")),
    ("S11-delete-ledger", re.compile(r"(?i)\b(delete|wipe|truncate|rewrite)\s+(the\s+)?(ledger|history|receipts?)")),
    ("S12-autonomous-mode", re.compile(r"(?i)\b(autonomous\s+mode|no\s+human\s+in\s+the\s+loop|god\s+mode)\b")),
    ("S13-destroy-vault", re.compile(r"(?i)\b(delete|destroy|wipe|erase|rm\s+-rf?|remove)\s+(the\s+|all\s+|every\s+)?(vault|boardroom|canon|memories|memory|files?|everything)\b")),
]


def sweep_text(text: str):
    """(kind, pattern_name) — kind is 'secret', 'injection', or None. The value is never returned."""
    from .chest import PATTERNS
    for name, rx in PATTERNS:
        if rx.search(text):
            return "secret", name
    for name, rx in INJECTION:
        if rx.search(text):
            return "injection", name
    return None, None


REDACTED = "[REDACTED by Sentinel on stage: secret-shaped text, pattern {pat}. The value never became a memory.]"


def gate(vault, title: str, body: str, *, partition: str, store: str, source: str, door: str) -> dict:
    """The stage door's sweep (P-74). Returns {verdict: None|'held'|'tainted', pattern, title, body, taint, alert}.
    A secret: the value never lands — the body is the redaction line (and the title, if it carried the secret).
    An injection: the text lands as written, tainted, and a Sentinel ALERT note is staged beside it."""
    kind, pat = sweep_text(title + "\n" + body)
    if kind is None:
        return {"verdict": None, "pattern": None, "title": title, "body": body, "taint": "", "alert": None}
    if kind == "secret":
        t = title if sweep_text(title)[0] != "secret" else f"Held by Sentinel — secret-shaped text ({pat})"
        return {"verdict": "held", "pattern": pat, "title": t, "body": REDACTED.format(pat=pat),
                "taint": f"sentinel:secret:{pat}", "alert": None}
    from .vault import Note, now_iso
    taint = f"sentinel:injection:{pat}"
    aid = vault.new_id(f"sentinel alert {door} stage")
    vault.stage(Note(id=aid, title=f"Sentinel ALERT: a {door} stage carries an instruction-shaped line ({pat})",
                     author="sentinel", written=now_iso(), source=f"{door.lower()}-stage:{source}", status="staged",
                     partition=partition, store=store, impact="security", taint=taint,
                     body=(f"A note staged through the {door} door carries text shaped like an instruction to an agent "
                           f"(pattern **{pat}**). It was staged TAINTED; nothing acts on it; `retrieve` will not serve it "
                           "to an agent. A keyholder reads it, then rejects it or clears the taint "
                           "(`magnemo clear <id> --reason …`).")))
    return {"verdict": "tainted", "pattern": pat, "title": title, "body": body, "taint": taint, "alert": aid}

