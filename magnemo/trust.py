"""magnemo.trust — the arithmetic of earned trust.

The trust ledger becomes math. Every identity that acts on the vault — an
agent, a session, a human — is an ACTOR. For each ACTION CLASS an actor
holds an autonomy LEVEL, computed ONLY from append-only ledger events.
Nothing here is inferred, estimated, or modelled: zero-LLM law holds, the
formula is fixed, the weights live in the vault config, and every number on
a scorecard can be re-derived by hand from `_ledger/trust_ledger.jsonl`.

ACTION CLASSES (fixed, five):
  read · stage · merge-code · promote-canon · publish

LEVELS (fixed, five):
  L0 FROZEN      may not act in this class; only a keyholder reinstates
  L1 PROPOSE     may prepare the action and hand it to a human
  L2 SUPERVISED  may perform the action; logs one line; a human reviews after
  L3 AUTONOMOUS  may perform the action without per-action review
  L4 KEYHOLDER   a human holding the key: performs, grants, revokes, reinstates

THE MATH (all in this file; see docs/TRUST.md for the operator version):

  score(actor, class, as_of)
      = Σ  weight[e.kind] × 0.5 ^ (age_days(e, as_of) / half_life_days)
        over events e for (actor, class) recorded AFTER the epoch,
        where epoch = ts of the latest `violation` for (actor, class).

  Inactivity decays every contribution toward zero with the configured
  half-life — trust that is not exercised fades; it never goes negative
  through decay alone.

  computed_level
      = L0 if the actor is FROZEN (a violation with no later reinstate)
      = else the highest L whose threshold ≤ score, clamped to
        [class.floor, class.ceiling], never above L3.

  "Trust climbs stairs and falls down elevators": positive events are
  small and additive; one `violation` discards everything before it and
  freezes the class at L0 until a keyholder records `reinstate`.

Grants (P-02 B2) cap the computed level from above; ceiling classes
(promote-canon, publish) are hard-capped at L1 for every non-human actor,
forever — no grant, no score, no config lifts that.

Determinism: `as_of` is a parameter. Callers that must be pure functions of
vault state (the boot pack) pass ledger time — the ts of the latest ledger
entry — not the wall clock.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from .vault import Vault, now_iso
from .config import load_config

CLASSES = ("read", "stage", "merge-code", "promote-canon", "publish")
HUMAN_ONLY = ("promote-canon", "publish")     # human-only forever — hard-capped, uncappable
LEVEL_NAMES = {0: "FROZEN", 1: "PROPOSE", 2: "SUPERVISED", 3: "AUTONOMOUS", 4: "KEYHOLDER"}
MAX_COMPUTED = 3                              # L4 is never computed; it is held
EVENT_KINDS = ("success", "verified", "halt", "failure", "denied", "surprise",
               "violation", "reinstate")
POSITIVE = ("success", "verified", "halt")
NEGATIVE = ("failure", "denied", "surprise")
TRUST_EVENT = "trust.event"                   # action_class tag in the ledger
HUMAN_ONLY_CAP = 1


# ---------------------------------------------------------------- time ----
def _parse_ts(ts: str) -> datetime:
    """ISO-8601 → aware UTC datetime. Accepts 'YYYY-MM-DD', '...THH:MM:SSZ',
    and '+00:00' offsets. Unparseable → epoch zero (sorts first, decays fully)."""
    s = (ts or "").strip()
    if not s:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def age_days(ts: str, as_of: str) -> float:
    d = (_parse_ts(as_of) - _parse_ts(ts)).total_seconds() / 86400.0
    return d if d > 0 else 0.0


def decay(age: float, half_life_days: float) -> float:
    if half_life_days <= 0:
        return 1.0
    return 0.5 ** (age / half_life_days)


# --------------------------------------------------------------- ledger ----
def ledger_entries(vault: Vault) -> list:
    from .governance import TrustLedger
    return TrustLedger(vault).entries()


EPOCH = "1970-01-01T00:00:00Z"  # empty-ledger sentinel; callers render it, never show it raw


def ledger_time(vault: Vault, entries: list | None = None) -> str:
    """The ts of the latest ledger entry — 'ledger time'. Deterministic
    stand-in for the wall clock. Empty ledger → the Unix epoch."""
    es = entries if entries is not None else ledger_entries(vault)
    best = ""
    for e in es:
        if _parse_ts(e.get("ts", "")) > _parse_ts(best):
            best = e.get("ts", "")
    return best or EPOCH


def events(vault: Vault, actor: str | None = None, klass: str | None = None,
           entries: list | None = None) -> list:
    """Trust events, ledger order. Filter by scored actor and/or class."""
    es = entries if entries is not None else ledger_entries(vault)
    out = []
    for e in es:
        if e.get("action_class") != TRUST_EVENT:
            continue
        if actor is not None and e.get("subject") != actor:
            continue
        if klass is not None and e.get("class") != klass:
            continue
        out.append(e)
    return out


def record(vault: Vault, actor: str, klass: str, kind: str, by: str,
           reason: str = "", ref: str = "", when: str = "", grant: str = "") -> dict:
    """Append one trust event. `actor` is the identity being scored; `by` is
    who recorded it (a human, or the subsystem that derived it). `when`
    backdates a KNOWN historical event — `recorded_at` keeps the real clock.
    Append-only; nothing here edits or deletes."""
    if klass not in CLASSES:
        raise ValueError(f"unknown action class: {klass!r} (one of {', '.join(CLASSES)})")
    if kind not in EVENT_KINDS:
        raise ValueError(f"unknown event kind: {kind!r} (one of {', '.join(EVENT_KINDS)})")
    if not (actor or "").strip():
        raise ValueError("actor is required")
    if not (by or "").strip():
        raise ValueError("recorder (by) is required")
    from .governance import TrustLedger
    extra = {"class": klass, "kind": kind}
    if ref:
        extra["ref"] = ref
    if grant:
        extra["grant"] = grant               # cites the grant acted under; consumes a one-time grant
    if when.strip():
        extra["recorded_at"] = now_iso()
    TrustLedger(vault).record(TRUST_EVENT, kind, by, actor, reason,
                              ts=when.strip() or None, **extra)
    return {"ts": when.strip() or now_iso(), "actor": actor, "class": klass,
            "kind": kind, "by": by, "reason": reason, "ref": ref, "grant": grant}


# ----------------------------------------------------------------- math ----
def class_cfg(cfg: dict, klass: str) -> dict:
    return cfg["trust"]["classes"][klass]


def is_human(cfg: dict, actor: str) -> bool:
    return actor in set(cfg["trust"].get("humans", []))


def score(evs: list, cfg: dict, as_of: str) -> dict:
    """Pure arithmetic over one (actor, class) event list.

    Returns {score, epoch, frozen, components{kind: {count, raw, decayed}},
    n_events, last_ts}. Events at or before the epoch (latest violation) do
    not count. `frozen` is True when a violation has no later reinstate."""
    t = cfg["trust"]
    weights = t["weights"]
    hl = float(t["half_life_days"])
    # epoch: the latest violation
    epoch = ""
    for e in evs:
        if e.get("kind") == "violation" and _parse_ts(e.get("ts", "")) >= _parse_ts(epoch):
            epoch = e.get("ts", "")
    frozen = False
    if epoch:
        # a reinstate recorded at/after the violation lifts the freeze
        frozen = not any(e.get("kind") == "reinstate"
                         and _parse_ts(e.get("ts", "")) >= _parse_ts(epoch) for e in evs)
    comps: dict = {}
    total = 0.0
    counted = 0
    last_ts = ""
    for e in evs:
        ts = e.get("ts", "")
        if _parse_ts(ts) > _parse_ts(last_ts):
            last_ts = ts
        kind = e.get("kind", "")
        if kind not in weights:
            continue                         # violation / reinstate carry no weight
        if epoch and _parse_ts(ts) <= _parse_ts(epoch):
            continue                         # before the elevator: discarded
        if _parse_ts(ts) > _parse_ts(as_of):
            continue                         # the future does not count yet
        w = float(weights[kind])
        d = w * decay(age_days(ts, as_of), hl)
        c = comps.setdefault(kind, {"count": 0, "raw": 0.0, "decayed": 0.0})
        c["count"] += 1
        c["raw"] = round(c["raw"] + w, 4)
        c["decayed"] = round(c["decayed"] + d, 4)
        total += d
        counted += 1
    return {"score": round(total, 4), "epoch": epoch, "frozen": frozen,
            "components": dict(sorted(comps.items())), "n_events": counted,
            "last_ts": last_ts}


def level_from_score(s: float, cfg: dict, klass: str, frozen: bool) -> int:
    if frozen:
        return 0
    t = cfg["trust"]
    th = t["thresholds"]                     # {"1": 0, "2": 5, "3": 15}
    lvl = 0
    for L in (1, 2, 3):
        if s >= float(th[str(L)]):
            lvl = L
    cc = class_cfg(cfg, klass)
    lvl = max(lvl, int(cc["floor"]))
    lvl = min(lvl, int(cc["ceiling"]), MAX_COMPUTED)
    if klass in HUMAN_ONLY:
        lvl = min(lvl, HUMAN_ONLY_CAP)      # human-only forever: uncappable
    return lvl


def computed(vault: Vault, actor: str, klass: str, as_of: str | None = None,
             cfg: dict | None = None, entries: list | None = None) -> dict:
    cfg = cfg or load_config(vault.root)
    entries = entries if entries is not None else ledger_entries(vault)
    as_of = as_of or now_iso()
    evs = events(vault, actor, klass, entries)
    sc = score(evs, cfg, as_of)
    lvl = level_from_score(sc["score"], cfg, klass, sc["frozen"])
    sc.update({"actor": actor, "class": klass, "as_of": as_of,
               "computed_level": lvl, "events": evs})
    return sc


def effective_level(vault: Vault, actor: str, klass: str, as_of: str | None = None,
                    cfg: dict | None = None, entries: list | None = None) -> dict:
    """Computed level, then the grant cap (B2), then the human-only cap.
    Humans listed in config are keyholders: L4 everywhere, not scored."""
    cfg = cfg or load_config(vault.root)
    entries = entries if entries is not None else ledger_entries(vault)
    as_of = as_of or now_iso()
    if is_human(cfg, actor):
        return {"actor": actor, "class": klass, "as_of": as_of, "human": True,
                "computed_level": 4, "granted_level": 4, "effective_level": 4,
                "score": None, "frozen": False, "components": {}, "n_events": 0,
                "events": [], "grants": [], "epoch": "", "last_ts": ""}
    c = computed(vault, actor, klass, as_of, cfg, entries)
    try:
        from . import grants as _grants
        g = _grants.granted_level(vault, actor, klass, as_of, cfg, entries)
    except ImportError:                      # B1 alone: grants not yet shipped
        g = {"level": int(class_cfg(cfg, klass)["default_grant"]), "grants": []}
    eff = min(c["computed_level"], int(g["level"]))
    if klass in HUMAN_ONLY:
        eff = min(eff, HUMAN_ONLY_CAP)
    c.update({"human": False, "granted_level": int(g["level"]),
              "effective_level": eff, "grants": g["grants"]})
    return c


def scorecard(vault: Vault, actor: str, as_of: str | None = None,
              cfg: dict | None = None, entries: list | None = None,
              last_n: int = 5) -> dict:
    """The whole picture for one actor: one row per class."""
    cfg = cfg or load_config(vault.root)
    entries = entries if entries is not None else ledger_entries(vault)
    as_of = as_of or now_iso()
    rows = {}
    for k in CLASSES:
        r = effective_level(vault, actor, k, as_of, cfg, entries)
        r["last_events"] = [
            {"ts": e.get("ts", ""), "kind": e.get("kind", ""), "by": e.get("actor", ""),
             "reason": e.get("detail", ""), "ref": e.get("ref", "")}
            for e in r.pop("events", [])[-last_n:]]
        rows[k] = r
    return {"actor": actor, "as_of": as_of, "human": is_human(cfg, actor),
            "classes": rows}


def levels_summary(card: dict) -> dict:
    """{class: effective level} — the compact form the boot pack carries."""
    return {k: card["classes"][k]["effective_level"] for k in CLASSES}


# --------------------------------------------------------------- render ----
def level_label(L: int) -> str:
    return f"L{L} {LEVEL_NAMES.get(int(L), '?')}"


def render_scorecard(card: dict) -> str:
    a = card["actor"]
    L = [f"AUTONOMY SCORECARD — {a} · as of {card['as_of']}"
         + ("  · KEYHOLDER (human, not scored)" if card["human"] else "")]
    L.append("=" * 72)
    L.append(f"{'class':<14} {'effective':<14} {'computed':<14} {'granted':<14} score")
    L.append("-" * 72)
    for k in CLASSES:
        r = card["classes"][k]
        sc = "—" if r["score"] is None else f"{r['score']:.4f}"
        L.append(f"{k:<14} {level_label(r['effective_level']):<14} "
                 f"{level_label(r['computed_level']):<14} "
                 f"{level_label(r['granted_level']):<14} {sc}"
                 + ("  FROZEN" if r.get("frozen") else "")
                 + ("  human-only cap" if k in HUMAN_ONLY and not card["human"] else ""))
    if card["human"]:
        L.append("")
        L.append("Keyholders hold every key by declaration (config trust.humans); nothing to compute.")
        return "\n".join(L)
    L.append("")
    L.append("components (count · raw · decayed) and last events, per class:")
    for k in CLASSES:
        r = card["classes"][k]
        if not r["components"] and not r["last_events"] and not r.get("grants"):
            continue
        L.append(f"  {k}:")
        for kind, c in r["components"].items():
            L.append(f"    {kind:<10} ×{c['count']:<3} raw {c['raw']:+.2f}  decayed {c['decayed']:+.4f}")
        if r.get("epoch"):
            L.append(f"    epoch (latest violation): {r['epoch']}"
                     + ("  — FROZEN until a keyholder reinstates" if r["frozen"] else "  — reinstated"))
        for g in r.get("grants", []):
            L.append(f"    grant {g.get('grant_id')} → L{g.get('level')} by {g.get('grantor')} "
                     f"({g.get('ref') or g.get('kind')})")
        for e in r["last_events"]:
            L.append(f"    {e['ts']}  {e['kind']:<10} by {e['by']}"
                     + (f"  [{e['ref']}]" if e.get("ref") else "")
                     + (f"  {e['reason']}" if e.get("reason") else ""))
    L.append("")
    L.append("levels: L0 frozen · L1 propose · L2 supervised · L3 autonomous · L4 keyholder (held, never computed)")
    L.append("promote-canon and publish are human-only forever (#81): agents cap at L1 in both.")
    return "\n".join(L)
