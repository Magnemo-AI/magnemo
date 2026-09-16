"""magnemo.handoff — Boundary Telemetry.

Every session ends at a boundary: the context wall, a planned stop, a
compaction. Untracked, those boundaries are where continuity silently dies.
So each handoff records two artifacts:

  1. a structured telemetry entry appended to `_ledger/handoffs.jsonl` —
     append-only, machine-readable: usage %, trigger, what was cut, actor;
  2. a provenance-complete handoff note staged for review like any other
     memory candidate — the human-readable baton.

`cli handoff --usage 91 --trigger planned --cut "deferred X" --by NAME`
`cli handoff --report` renders every boundary ever recorded as a table.

DOCTRINE (~90% soft threshold): don't ride to the wall. At ~90% context
usage, write the handoff and stand down — the first recorded datum (Aug 13
2026, 98%, trigger=wall, operator-confirmed) is the scar that set the rule.

The `when` override exists so KNOWN historical boundaries can be recorded
after the fact without falsifying timestamps silently: entries carry
`recorded_at` (actual clock) alongside `ts` (when the boundary happened).
"""
from __future__ import annotations
import os, json
from .vault import Vault, now_iso
from .governance import Governance

TRIGGERS = ("wall", "planned", "compaction", "other")
HANDOFF_FILE = "handoffs.jsonl"


def _path(vault: Vault) -> str:
    return os.path.join(vault.root, "_ledger", HANDOFF_FILE)


def record(vault: Vault, usage_pct: float, trigger: str, cut: str = "",
           actor: str = "operator", when: str = "", source: str = "",
           body_extra: str = "") -> dict:
    """Append one boundary-telemetry entry (append-only) AND stage a
    provenance-complete handoff note. Returns the ledger entry."""
    try:
        usage_pct = float(usage_pct)
    except (TypeError, ValueError):
        raise ValueError(f"usage must be a number, got {usage_pct!r}")
    if not (0.0 <= usage_pct <= 100.0):
        raise ValueError(f"usage out of range [0, 100]: {usage_pct}")
    if trigger not in TRIGGERS:
        raise ValueError(f"unknown trigger: {trigger!r} (must be one of {', '.join(TRIGGERS)})")

    ts = when.strip() or now_iso()
    # P-02 B4: the actor's autonomy at the boundary, at ledger time, BEFORE this
    # handoff's own events land — the next wake inherits the level it left with.
    from . import trust
    levels = trust.levels_summary(trust.scorecard(vault, actor, as_of=trust.ledger_time(vault)))
    gov = Governance(vault)
    note = gov.agent_write(
        title=f"Handoff at {usage_pct:g}% ({trigger})",
        body=(f"BOUNDARY TELEMETRY — where this session stopped, and why\n\n"
              f"- boundary: {ts}\n"
              f"- context usage: {usage_pct:g}%\n"
              f"- trigger: {trigger}\n"
              f"- cut at the boundary: {cut or '(nothing declared cut)'}\n"
              f"- recorded by: {actor}\n"
              f"- autonomy at the boundary: "
              + " · ".join(f"{k} L{levels[k]}" for k in trust.CLASSES) + "\n"
              + (f"\n{body_extra}\n" if body_extra else "")),
        partition=vault.default_target(("dev", "knowledge"))[0], store=vault.default_target(("dev", "knowledge"))[1],
        author=actor,
        source=source or f"handoff/{trigger}@{usage_pct:g}%",
        tags="handoff,telemetry,boundary",
        impact="process",
    )
    entry = {
        "ts": ts,
        "recorded_at": now_iso(),
        "usage_pct": usage_pct,
        "trigger": trigger,
        "cut": cut,
        "actor": actor,
        "note_id": note.id,
        "levels": levels,
    }
    path = _path(vault)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")
    from . import chest
    chest.notify(vault, "handoff")   # THE CHEST (#129): the boundary is a copy event
    return entry


def entries(vault: Vault) -> list:
    """All boundary entries, oldest first (file order — append-only)."""
    path = _path(vault)
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


def report_table(vault: Vault) -> str:
    """Every boundary ever recorded, as a fixed-width table."""
    es = entries(vault)
    if not es:
        return "No handoffs recorded yet."
    header = f"{'boundary ts':<21} {'usage':>6} {'trigger':<11} {'actor':<12} cut"
    lines = [header, "-" * len(header)]
    for e in es:
        cut = (e.get("cut") or "—")
        if len(cut) > 60:
            cut = cut[:59] + "…"
        lines.append(f"{e.get('ts', '?'):<21} {e.get('usage_pct', 0):>5g}% "
                     f"{e.get('trigger', '?'):<11} {e.get('actor', '?'):<12} {cut}")
    n = len(es)
    walls = sum(1 for e in es if e.get("trigger") == "wall")
    avg = sum(float(e.get("usage_pct", 0)) for e in es) / n
    lines.append("")
    lines.append(f"{n} boundary(ies) · {walls} hit the wall · mean usage {avg:.1f}% "
                 f"· doctrine: hand off at ~90%")
    return "\n".join(lines)
