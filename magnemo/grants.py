"""magnemo.grants — permission as data (P-02 B2). P-01 becomes code.

A GRANT is a structured, append-only ledger record by which a keyholder
(a human in `trust.humans`) permits an actor to operate at a LEVEL in one
or more ACTION CLASSES, under stated conditions, within a stated scope.
Standing orders and one-time grants are the same record with a different
`kind`. Revocation is a second record that names the first. Nothing is
ever edited.

  effective_level = min(computed_level, granted_level)

where granted_level = max(class default_grant, levels of the actor's ACTIVE
grants covering the class). A grant is active at `as_of` when it was issued
at or before `as_of`, has not expired, has not been revoked, and — for
one-time grants — has not been CONSUMED by a trust event that cites it.

What no grant can do — ever: lift a non-human above L1 in
`promote-canon` or `publish`, or lift anyone to L4 who is not a declared
human. Both are refused at issue time AND clamped at compute time, so a
hand-edited ledger line cannot smuggle a key either.
"""
from __future__ import annotations
from .vault import Vault, now_iso
from .config import load_config
from . import trust

GRANT_EVENT = "trust.grant"
KINDS = ("standing", "one-time")


def _ledger(vault: Vault):
    from .governance import TrustLedger
    return TrustLedger(vault)


def _entries(vault: Vault, entries=None) -> list:
    return entries if entries is not None else trust.ledger_entries(vault)


def records(vault: Vault, entries=None) -> list:
    """Every grant record (issued and revoked), ledger order."""
    return [e for e in _entries(vault, entries) if e.get("action_class") == GRANT_EVENT]


def _next_id(vault: Vault, entries=None) -> str:
    n = sum(1 for e in records(vault, entries) if e.get("verdict") == "issued")
    return f"G{n + 1:04d}"


def issue(vault: Vault, grantee: str, classes: list, level: int, by: str,
          scope: str = "", conditions: list | None = None, kind: str = "standing",
          ref: str = "", expires: str = "", reason: str = "", when: str = "",
          cfg: dict | None = None) -> dict:
    """Keyholder-only. Appends one `trust.grant / issued` record."""
    cfg = cfg or load_config(vault.root)
    if not trust.is_human(cfg, by):
        raise PermissionError(f"REFUSED: '{by}' is not a keyholder (config trust.humans); only humans grant")
    grantee = (grantee or "").strip()
    if not grantee:
        raise ValueError("grantee is required")
    classes = [c.strip() for c in classes if c and c.strip()]
    if not classes:
        raise ValueError("at least one action class is required")
    for c in classes:
        if c not in trust.CLASSES:
            raise ValueError(f"unknown action class: {c!r} (one of {', '.join(trust.CLASSES)})")
    level = int(level)
    if not 0 <= level <= 4:
        raise ValueError("level must be 0..4")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    human_grantee = trust.is_human(cfg, grantee)
    if level >= 4 and not human_grantee:
        raise PermissionError(f"REFUSED: L4 KEYHOLDER is held by declared humans only; '{grantee}' is not one")
    if not human_grantee and level > trust.HUMAN_ONLY_CAP:
        blocked = [c for c in classes if c in trust.HUMAN_ONLY]
        if blocked:
            raise PermissionError(
                f"REFUSED: {', '.join(blocked)} cannot be granted above L{trust.HUMAN_ONLY_CAP} "
                f"to a non-human — human-only forever")
    ts = when.strip() or now_iso()
    grant = {
        "grant_id": _next_id(vault),
        "grantee": grantee, "classes": classes, "level": level,
        "scope": scope or "", "conditions": list(conditions or []),
        "kind": kind, "ref": ref or "", "expires": expires or "",
        "grantor": by, "issued": ts,
    }
    extra = {"grant": grant}
    if when.strip():
        extra["recorded_at"] = now_iso()
    _ledger(vault).record(GRANT_EVENT, "issued", by, grantee, reason, ts=ts, **extra)
    return grant


def revoke(vault: Vault, grant_id: str, by: str, reason: str, when: str = "",
           cfg: dict | None = None) -> dict:
    """Keyholder-only. Appends one `trust.grant / revoked` record naming the grant."""
    cfg = cfg or load_config(vault.root)
    if not trust.is_human(cfg, by):
        raise PermissionError(f"REFUSED: '{by}' is not a keyholder; only humans revoke")
    if not (reason or "").strip():
        raise ValueError("a reason is required — revocations teach")
    target = None
    for e in records(vault):
        if e.get("verdict") == "issued" and e["grant"]["grant_id"] == grant_id:
            target = e["grant"]
        if e.get("verdict") == "revoked" and e.get("grant_id") == grant_id:
            raise ValueError(f"{grant_id} is already revoked")
    if target is None:
        raise FileNotFoundError(f"no grant {grant_id}")
    ts = when.strip() or now_iso()
    extra = {"grant_id": grant_id}
    if when.strip():
        extra["recorded_at"] = now_iso()
    _ledger(vault).record(GRANT_EVENT, "revoked", by, target["grantee"], reason, ts=ts, **extra)
    return {"grant_id": grant_id, "grantee": target["grantee"], "by": by,
            "reason": reason, "ts": ts}


def status(vault: Vault, as_of: str | None = None, entries=None) -> list:
    """Every issued grant with its state at `as_of`:
    active | revoked | expired | consumed | pending (issued after as_of)."""
    es = _entries(vault, entries)
    as_of = as_of or now_iso()
    P = trust._parse_ts
    revoked = {}
    for e in es:
        if e.get("action_class") == GRANT_EVENT and e.get("verdict") == "revoked" \
                and P(e.get("ts", "")) <= P(as_of):
            revoked.setdefault(e.get("grant_id"), e)
    consumed = {}
    for e in es:
        if e.get("action_class") == trust.TRUST_EVENT and e.get("grant") \
                and P(e.get("ts", "")) <= P(as_of):
            consumed.setdefault(e["grant"], e)
    out = []
    for e in es:
        if e.get("action_class") != GRANT_EVENT or e.get("verdict") != "issued":
            continue
        g = dict(e["grant"])
        gid = g["grant_id"]
        if P(g.get("issued", "")) > P(as_of):
            g["state"] = "pending"
        elif gid in revoked:
            g["state"] = "revoked"; g["revoked"] = revoked[gid].get("ts", "")
            g["revoke_reason"] = revoked[gid].get("detail", "")
        elif g.get("expires") and P(g["expires"]) <= P(as_of):
            g["state"] = "expired"
        elif g.get("kind") == "one-time" and gid in consumed:
            g["state"] = "consumed"; g["consumed"] = consumed[gid].get("ts", "")
        else:
            g["state"] = "active"
        out.append(g)
    return out


def active(vault: Vault, actor: str | None = None, klass: str | None = None,
           as_of: str | None = None, entries=None) -> list:
    out = []
    for g in status(vault, as_of, entries):
        if g["state"] != "active":
            continue
        if actor is not None and g["grantee"] != actor:
            continue
        if klass is not None and klass not in g["classes"]:
            continue
        out.append(g)
    return out


def granted_level(vault: Vault, actor: str, klass: str, as_of: str | None = None,
                  cfg: dict | None = None, entries=None) -> dict:
    """max(class default, active grants) — clamped by the human-only cap
    at compute time too, so a hand-edited ledger line cannot smuggle a key."""
    cfg = cfg or load_config(vault.root)
    base = int(trust.class_cfg(cfg, klass)["default_grant"])
    gs = active(vault, actor, klass, as_of, entries)
    level = max([base] + [int(g["level"]) for g in gs])
    if not trust.is_human(cfg, actor):
        level = min(level, trust.MAX_COMPUTED)
        if klass in trust.HUMAN_ONLY:
            level = min(level, trust.HUMAN_ONLY_CAP)
    return {"level": level, "grants": gs, "default": base}


def render(grants: list) -> str:
    if not grants:
        return "No grants on record. Permission is the per-class default (config trust.classes.*.default_grant)."
    L = [f"{'id':<6} {'state':<9} {'grantee':<16} {'L':<3} {'classes':<28} {'kind':<9} {'grantor':<14} ref / scope"]
    L.append("-" * len(L[0]))
    for g in grants:
        tail = g.get("ref") or ""
        if g.get("scope"):
            tail += (" · " if tail else "") + g["scope"]
        L.append(f"{g['grant_id']:<6} {g['state']:<9} {g['grantee']:<16} L{g['level']:<2} "
                 f"{','.join(g['classes']):<28} {g['kind']:<9} {g['grantor']:<14} {tail}")
        for c in g.get("conditions", []):
            L.append(f"{'':<6} {'':<9} condition: {c}")
        if g.get("expires"):
            L.append(f"{'':<6} {'':<9} expires: {g['expires']}")
        if g["state"] == "revoked":
            L.append(f"{'':<6} {'':<9} revoked {g.get('revoked')}: {g.get('revoke_reason')}")
        if g["state"] == "consumed":
            L.append(f"{'':<6} {'':<9} consumed {g.get('consumed')}")
    return "\n".join(L)
