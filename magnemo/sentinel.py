"""magnemo.sentinel — the shared sweep: secret formats and injection patterns.

Sentinel guards the GATE (stage → canon) and the COPY (chest push). It never
quotes a matched value back; it names the pattern. S1–S13 are the injection
shapes an agent's context can carry; a hit taints the note and raises an alert.
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
