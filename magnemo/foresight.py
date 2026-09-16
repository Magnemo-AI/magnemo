"""magnemo.foresight — Foresight counters.

The Cost-of-Remembering benchmark starts with a baseline, and a baseline
starts with counters. Every memory payload served — a retrieval result set,
a boot pack — logs one append-only event to `_ledger/costs.jsonl`:

  {ts, kind, bytes, tokens_est, meta}

`tokens_est` is deliberately rough: bytes / 4, the classic prose heuristic.
It exists to make orders of magnitude visible, not to bill anyone. When a
real tokenizer matters, it swaps in behind the same field name.

`cli costs` summarizes per kind and states the measured baseline — the
number every future optimization (renditions #18, mn:// pointers #25,
adaptive resolution #17) gets judged against.
"""
from __future__ import annotations
import os, json
from .vault import Vault, now_iso

COSTS_FILE = "costs.jsonl"
BYTES_PER_TOKEN = 4  # rough prose heuristic; documented, swappable


def tokens_est(nbytes: int) -> int:
    return round(nbytes / BYTES_PER_TOKEN)


def log_cost(vault: Vault, kind: str, nbytes: int, meta: dict | None = None) -> dict:
    """Append one payload-cost event. Never raises into the serving path —
    a failed counter must not fail a retrieval."""
    entry = {
        "ts": now_iso(),
        "kind": kind,                 # "retrieval" | "bootpack" | future kinds
        "bytes": int(nbytes),
        "tokens_est": tokens_est(int(nbytes)),
        "meta": meta or {},
    }
    try:
        d = os.path.join(vault.root, "_ledger")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, COSTS_FILE), "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass
    return entry


def entries(vault: Vault) -> list:
    path = os.path.join(vault.root, "_ledger", COSTS_FILE)
    if not os.path.exists(path):
        return []
    out = []
    with open(path) as f:
        for line in f:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def summary_table(vault: Vault) -> str:
    """Per-kind payload costs plus the stated baseline."""
    es = entries(vault)
    if not es:
        return ("No cost events recorded yet. Counters log on every retrieval "
                "and bootpack — the baseline starts with the first payload served.")
    kinds: dict = {}
    for e in es:
        k = kinds.setdefault(e.get("kind", "?"), {"n": 0, "bytes": 0, "tokens": 0})
        k["n"] += 1
        k["bytes"] += int(e.get("bytes", 0))
        k["tokens"] += int(e.get("tokens_est", 0))
    header = f"{'kind':<12} {'events':>7} {'total bytes':>12} {'total ~tok':>11} {'mean bytes':>11} {'mean ~tok':>10}"
    lines = ["FORESIGHT COUNTERS — what remembering costs, measured", "",
             header, "-" * len(header)]
    tot_n = tot_b = tot_t = 0
    for kind in sorted(kinds):
        k = kinds[kind]
        tot_n += k["n"]; tot_b += k["bytes"]; tot_t += k["tokens"]
        lines.append(f"{kind:<12} {k['n']:>7} {k['bytes']:>12} {k['tokens']:>11} "
                     f"{k['bytes'] // k['n']:>11} {k['tokens'] // k['n']:>10}")
    lines.append("-" * len(header))
    lines.append(f"{'ALL':<12} {tot_n:>7} {tot_b:>12} {tot_t:>11} "
                 f"{tot_b // tot_n:>11} {tot_t // tot_n:>10}")
    lines.append("")
    baseline = " · ".join(
        f"{kind}: {kinds[kind]['n']} events, mean ~{kinds[kind]['tokens'] // kinds[kind]['n']} tok/event"
        for kind in sorted(kinds))
    lines.append(f"BASELINE (all recorded events): {baseline}")
    lines.append(f"Token estimate is bytes/{BYTES_PER_TOKEN} (rough prose heuristic). "
                 "Every future payload optimization is judged against these numbers.")
    return "\n".join(lines)
