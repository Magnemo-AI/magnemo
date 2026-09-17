"""magnemo.bootpack — the Boot Pack: one command, a bootable orientation.

The boot pack, the Charter served on every wake,
#68 (Soul Codex — the relationship layer), #87 (worker boots stay lean).

`cli bootpack` renders BOOT_PACK.md from vault state — the document a fresh
session reads FIRST. Section order is doctrine, identical for both classes:

  1. THE CHARTER — verbatim, always first. If no charter has been promoted,
     an explicit placeholder; the Charter is NEVER fabricated.
  2. RELATIONSHIP LAYER — partner class only, and only when a codex exists.
     This section is what makes a spawn a partner instead of a clone; worker
     boots omit it to stay lean.
  3. GATES — the Gate Map: every gate, its state, keyholder,
     and delegations, derived from the grant ledger at LEDGER TIME (the ts of
     the latest ledger entry — never the wall clock, so the pack stays pure).
     Every session boots knowing the walls.
  4. CANON DIGEST — every canonical note: title, one-line summary, stable path.
  5. OPEN THREADS & REVIEW QUEUE — open-tagged notes, staged count, and the
     top staged notes by KAIROS salience.
  6. LAST HANDOFF — the most recent boundary: when, usage,
     trigger, what was cut, and the staged handoff note to read next. This
     is how a handoff is INHERITED by the next wake, deterministically,
     regardless of where the note ranks in the review queue.
  7. LEDGER TAIL — the most recent governance decisions.

THE CODEX SEAM: the relationship layer is sourced through a pluggable
callable (`codex_source() -> str | None`). The default reads one file named
by config (`bootpack.codex_path`, resolved against the vault root). No file,
no section — a partner boot degrades gracefully to worker content. Swap the
callable to source the codex from anywhere else; the pack format never changes.

DETERMINISM: the pack is a pure function of vault state + config + codex.
No clock, no RNG, no model calls — identical state yields identical bytes,
per class. That property is tested and load-bearing (cache-friendliness).
"""
from __future__ import annotations
import os
from .vault import Vault, Note, PARTITIONS, STORES
from .governance import TrustLedger
from .config import load_config
from . import kairos, handoff as _handoff, trust as _trust, gates as _gates

CLASSES = ("worker", "partner")

CHARTER_PLACEHOLDER = (
    "> **CHARTER NOT YET PROMOTED.** No canonical note carries the charter tag.\n"
    "> This placeholder is deliberate — the Charter is never fabricated.\n"
    "> Stage it, review it, promote it; it will be served verbatim here on every wake."
)


def default_codex_source(vault_root: str, cfg: dict):
    """The default codex seam: one markdown file at bootpack.codex_path
    (relative paths resolve against the vault root). Returns its text, or
    None when absent — absence is not an error, it is a worker boot."""
    rel = (cfg.get("bootpack", {}).get("codex_path") or "").strip()
    if not rel:
        return None
    path = rel if os.path.isabs(rel) else os.path.join(vault_root, rel)
    if not os.path.isfile(path):
        return None
    with open(path) as f:
        return f.read()


def _excerpt(body: str, start: str, end: str) -> list:
    """Lines from the first line matching `start` (inclusive) to the first later
    line matching `end` (exclusive). Empty start = from the top; empty end = to the end."""
    import re as _re
    lines = body.splitlines()
    i0 = 0
    if start:
        i0 = next((i for i, l in enumerate(lines) if _re.search(start, l)), None)
        if i0 is None:
            return [f"*(excerpt start not found: {start!r})*"]
    i1 = len(lines)
    if end:
        i1 = next((i for i in range(i0 + 1, len(lines)) if _re.search(end, lines[i])), len(lines))
    return lines[i0:i1]


def _one_liner(body: str, maxlen: int = 120) -> str:
    for line in body.splitlines():
        s = line.strip().lstrip("#>-* ").strip()
        if s:
            return s if len(s) <= maxlen else s[:maxlen - 1] + "…"
    return "(empty)"


def _tagset(n: Note) -> set:
    return {t.strip().lower() for t in n.tags.split(",") if t.strip()}


def _find_charter(canon: list, tag: str):
    hits = sorted([n for n in canon if tag in _tagset(n)], key=lambda n: n.id)
    return hits[0] if hits else None


def scorecard_lines(vault: Vault, actor: str, as_of: str, cfg: dict, entries: list) -> list:
    """YOUR AUTONOMY: the booting actor's own levels, one line per class,
    at ledger time. The agent always knows its own level (P-02 B4)."""
    card = _trust.scorecard(vault, actor, as_of, cfg, entries, last_n=3)
    L = []
    if card["human"]:
        L.append(f"`{actor}` is a declared keyholder: L4 in every class. Nothing to earn; everything to grant.")
        return L
    L.append("| class | effective | computed | granted | score |")
    L.append("|---|---|---|---|---|")
    for k in _trust.CLASSES:
        r = card["classes"][k]
        flag = " FROZEN" if r.get("frozen") else (" (keyholder-only cap)" if k in _trust.HUMAN_ONLY else "")
        L.append(f"| {k} | **{_trust.level_label(r['effective_level'])}**{flag} | "
                 f"{_trust.level_label(r['computed_level'])} | {_trust.level_label(r['granted_level'])} | "
                 f"{r['score']:.4f} |")
    for k in _trust.CLASSES:
        r = card["classes"][k]
        for g in r.get("grants", []):
            L.append(f"- grant {g['grant_id']} → L{g['level']} in {k}"
                     + (f" ({g['ref']})" if g.get("ref") else "")
                     + (f" — {g['scope']}" if g.get("scope") else ""))
        if r.get("frozen"):
            L.append(f"- **{k} is FROZEN** since {r['epoch']} — a keyholder must `reinstate` before you act there")
    L.append("")
    L.append("effective = min(earned, permitted). L1 = propose and hand to a keyholder; L2 = act and log one line; "
             "L3 = act. Full card: `magnemo autonomy " + actor + "`.")
    return L


def generate(vault: Vault, cls: str = "worker", scope: str | None = None,
             cfg: dict | None = None, codex_source=None, actor: str | None = None) -> str:
    """Render the boot pack. Pure: same state in, same bytes out. With
    `actor`, the pack also carries that actor's own autonomy scorecard."""
    if cls not in CLASSES:
        raise ValueError(f"unknown boot class: {cls} (worker|partner)")
    if scope is not None and scope not in vault.partitions:
        raise ValueError(f"unknown scope partition: {scope} (this vault declares: {', '.join(vault.partitions)})")
    cfg = cfg or load_config(vault.root)
    bp = cfg["bootpack"]
    canon_all = vault.canonical()                    # charter search is vault-wide
    canon = vault.canonical(scope) if scope else canon_all
    staged = [n for n in vault.staged() if n.status == "staged"]
    if scope:
        staged = [n for n in staged if n.partition == scope]
    ledger = TrustLedger(vault)

    L = []
    L.append(f"# BOOT PACK — magnemo · {cls} boot · scope: {scope or 'all'}")
    L.append("")
    L.append("Read top to bottom. The Charter governs everything below it.")
    from . import chest
    L.append(chest.gauge(vault.root, absolute=True))   # THE CHEST (#129): every agent sees copy state on wake
    L.append("")

    # ---- 1 · THE CHARTER — verbatim, always first, never fabricated ----
    L.append("## THE CHARTER")
    L.append("")
    charter = _find_charter(canon_all, bp["charter_tag"].strip().lower())
    if charter is None:
        L.append(CHARTER_PLACEHOLDER)
    else:
        L.append(f"*{charter.title}* — `{charter.partition}/{charter.store}/{charter.id}.md`")
        L.append("")
        L.append(charter.body.rstrip())
    L.append("")

    # ---- 1b · EXCERPTS — lifted verbatim from canonical notes (vault-sourced: restores boot identically) ----
    for ex in bp.get("excerpts") or []:
        src = next((n for n in canon_all if n.title == ex.get("note")), None)
        L.append(f"## {ex.get('title', ex.get('note', 'EXCERPT'))}")
        L.append("")
        if src is None:
            L.append(f"*(no canonical note titled '{ex.get('note')}' yet — nothing is fabricated)*")
        else:
            L.extend(_excerpt(src.body, ex.get("start", ""), ex.get("end", "")))
        L.append("")

    # ---- 1c · PARTNER EXCERPTS — partner class only: the fuller read (e.g. the whole codex) ----
    if cls == "partner":
        for ex in bp.get("partner_excerpts") or []:
            src = next((n for n in canon_all if n.title == ex.get("note")), None)
            L.append(f"## {ex.get('title', ex.get('note', 'EXCERPT'))}")
            L.append("")
            if src is None:
                L.append(f"*(no canonical note titled '{ex.get('note')}' yet — nothing is fabricated)*")
            else:
                L.extend(_excerpt(src.body, ex.get("start", ""), ex.get("end", "")))
            L.append("")

    # ---- 2 · RELATIONSHIP LAYER — partner only, codex-sourced ----
    if cls == "partner":
        src = codex_source if codex_source is not None \
            else (lambda: default_codex_source(vault.root, cfg))
        codex = src()
        if codex:
            L.append("## RELATIONSHIP LAYER")
            L.append("")
            L.append("You are booting as a PARTNER, not a clone. "
                     "Voice, lore, and relationship follow — carry them.")
            L.append("")
            L.append(codex.rstrip())
            L.append("")

    # ---- 3 · GATES — the walls, at ledger time ----
    entries = ledger.entries()
    as_of = _trust.ledger_time(vault, entries)
    # Fresh vault: ledger_time's epoch sentinel stays (deterministic maths
    # downstream) but is never SHOWN — a 1970 timestamp reads as a clock bug.
    at = ("before any ledger event (fresh vault)" if as_of == _trust.EPOCH
          else f"at ledger time {as_of}")
    L.append("## GATES")
    L.append("")
    L.append(f"The Gate Map {at}. locked = keyholders only · "
             "open = inside the walls · delegated = granted to the actors named.")
    L.extend(_gates.bootpack_lines(_gates.gate_map(vault, as_of, cfg, entries)))
    L.append("")

    # ---- 3b · YOUR AUTONOMY — the booting actor's own scorecard ----
    if actor:
        L.append(f"## YOUR AUTONOMY — {actor}")
        L.append("")
        L.append(f"Your levels {at}. You always know your own level.")
        L.append("")
        L.extend(scorecard_lines(vault, actor, as_of, cfg, entries))
        L.append("")

    # ---- 4 · CANON DIGEST ----
    L.append("## CANON DIGEST")
    L.append("")
    if not canon:
        L.append("*(no canonical notes in scope yet)*")
    else:
        parts = [scope] if scope else list(vault.partitions)
        for p in parts:
            for s in vault.stores.get(p, ()):
                group = sorted([n for n in canon if n.partition == p and n.store == s],
                               key=lambda n: n.id)
                if not group:
                    continue
                L.append(f"### {p}/{s}")
                for n in group:
                    L.append(f"- **{n.title}** — {_one_liner(n.body)} "
                             f"(`{p}/{s}/{n.id}.md`)")
                L.append("")
        if L[-1] == "":
            L.pop()
    L.append("")

    # ---- 5 · OPEN THREADS & REVIEW QUEUE ----
    L.append("## OPEN THREADS & REVIEW QUEUE")
    L.append("")
    open_tag = bp["open_tag"].strip().lower()
    threads = sorted([n for n in (canon + staged) if open_tag in _tagset(n)],
                     key=lambda n: n.id)
    L.append(f"Open threads: {len(threads)}")
    for n in threads:
        L.append(f"- {n.title} ({n.status}, {n.partition}/{n.store}, `{n.id}`)")
    L.append("")
    L.append(f"Staged notes awaiting review: {len(staged)}")
    top = kairos.sorted_queue(staged, int(bp["top_staged"]))
    if top:
        L.append(f"Top {len(top)} by salience:")
        for i, n in enumerate(top, 1):
            sal = f"{n.salience:.4f}" if n.salience >= 0 else "unscored"
            L.append(f"{i}. [{sal}] {n.title} (`{n.id}`)")
    L.append("")

    # ---- 6 · LAST HANDOFF — the inherited boundary ----
    L.append("## LAST HANDOFF")
    L.append("")
    bounds = _handoff.entries(vault)
    if not bounds:
        L.append("*(no boundary recorded yet — hand off at ~90%, do not ride to the wall)*")
    else:
        e = bounds[-1]
        L.append(f"- boundary: {e.get('ts', '?')} · usage {e.get('usage_pct', 0):g}% · "
                 f"trigger {e.get('trigger', '?')} · by {e.get('actor', '?')}")
        L.append(f"- cut at the boundary: {e.get('cut') or '(nothing declared cut)'}")
        if e.get("note_id"):
            L.append(f"- handoff note: `_staging/{e['note_id']}.md` — read it before acting")
        if e.get("levels"):
            lv = e["levels"]
            L.append("- autonomy at the boundary: " + " · ".join(
                f"{k} L{lv[k]}" for k in _trust.CLASSES if k in lv))
        L.append(f"- boundaries on record: {len(bounds)}")
    L.append("")

    # ---- 7 · LEDGER TAIL ----
    tail_n = int(bp["ledger_tail"])
    total = len(entries)
    entries = entries[-tail_n:]
    L.append(f"## LEDGER TAIL (last {len(entries)} of {total})")
    L.append("")
    if not entries:
        L.append("*(ledger empty)*")
    else:
        for e in entries:
            detail = f"  ({e['detail']})" if e.get("detail") else ""
            L.append(f"- {e['ts']}  {e['action_class']}  {e['verdict']}  "
                     f"by {e['actor']} → {e['subject']}{detail}")
    L.append("")
    return "\n".join(L)


def write(vault: Vault, cls: str = "worker", scope: str | None = None,
          out_path: str | None = None, cfg: dict | None = None,
          codex_source=None, actor: str | None = None) -> tuple:
    """Generate and write BOOT_PACK.md (default: <vault>/_index/BOOT_PACK.md,
    machine-managed). Returns (path, byte_count)."""
    text = generate(vault, cls, scope, cfg, codex_source, actor)
    path = out_path or os.path.join(vault.root, "_index", "BOOT_PACK.md")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    data = text.encode("utf-8")
    with open(path, "wb") as f:
        f.write(data)
    # Foresight counters (#13): a boot pack is a served payload too.
    from . import foresight
    foresight.log_cost(vault, "bootpack", len(data),
                       {"class": cls, "scope": scope or "all", "actor": actor or ""})
    return path, len(data)
