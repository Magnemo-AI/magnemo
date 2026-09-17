"""magnemo.gates — the Gate Map.

A GATE is a named door onto the vault or the repo. Each gate belongs to one
action class, has a keyholder, and is in exactly one STATE at any moment:

  locked      keyholders only. Nothing computed opens it.
  open        any actor may pass, inside the walls that govern the class
              (scope wall for read, partition wall + review queue for stage).
  delegated   a keyholder has granted non-keyholder actors a level in the gate's
              class; the map names them, their level, and the grant's scope.

Gate definitions are config (`trust.gates`, the founder's file). Their STATE
is derived, deterministically, from the grant ledger at an `as_of`: a gate
whose `state` is "computed" reads as `delegated` while any active grant
covers its class for a non-keyholder actor, else `locked`. `locked` and `open`
gates never change state by computation — only the founder's config edit
moves them, and the keyholder-only classes cannot be moved at all.

`magnemo gates` renders the map; the boot pack carries it under GATES so
every session boots knowing the walls.
"""
from __future__ import annotations
from .vault import Vault, now_iso
from .config import load_config
from . import trust, grants as _grants

STATES = ("locked", "open", "computed")


def definitions(cfg: dict) -> list:
    gs = []
    for g in cfg["trust"].get("gates", []):
        if g.get("class") not in trust.CLASSES:
            continue
        state = g.get("state", "locked")
        if g["class"] in trust.HUMAN_ONLY:
            state = "locked"                        # keyholder-only forever: not a config choice
        gs.append({"name": g["name"], "class": g["class"], "state": state,
                   "keyholder": g.get("keyholder", ""), "note": g.get("note", ""),
                   "paths": list(g.get("paths", []))})
    return gs


def gate_map(vault: Vault, as_of: str | None = None, cfg: dict | None = None,
             entries=None) -> list:
    """Every gate with its derived state, keyholder, last change, and the
    grant history (all grant records whose classes cover the gate's class)."""
    cfg = cfg or load_config(vault.root)
    entries = entries if entries is not None else trust.ledger_entries(vault)
    as_of = as_of or now_iso()
    P = trust._parse_ts
    allg = _grants.status(vault, as_of, entries)
    revokes = {e.get("grant_id"): e for e in entries
               if e.get("action_class") == _grants.GRANT_EVENT and e.get("verdict") == "revoked"
               and P(e.get("ts", "")) <= P(as_of)}
    out = []
    for d in definitions(cfg):
        klass = d["class"]
        hist = [g for g in allg if klass in g["classes"] and g["state"] != "pending"]
        delegated = [g for g in hist if g["state"] == "active"
                     and not trust.is_human(cfg, g["grantee"])]
        if d["state"] == "computed":
            state = "delegated" if delegated else "locked"
        else:
            state = d["state"]
            # a LOCKED or OPEN gate is not moved by grants: a grant covering the
            # class does not open a locked gate (gate-code stays the founder's).
            delegated = []
        last = ""
        for g in hist:
            for ts in (g.get("issued", ""), g.get("revoked", ""), g.get("consumed", "")):
                if ts and P(ts) > P(last):
                    last = ts
        out.append({
            "name": d["name"], "class": klass, "state": state,
            "configured": d["state"], "keyholder": d["keyholder"], "note": d["note"],
            "paths": d["paths"],
            "human_only": klass in trust.HUMAN_ONLY,
            "last_change": last or "genesis",
            "delegations": [{"grant_id": g["grant_id"], "grantee": g["grantee"],
                             "level": g["level"], "scope": g.get("scope", ""),
                             "ref": g.get("ref", ""), "kind": g["kind"]} for g in delegated],
            "grant_history": [{"grant_id": g["grant_id"], "grantee": g["grantee"],
                               "level": g["level"], "state": g["state"],
                               "issued": g.get("issued", ""), "grantor": g.get("grantor", ""),
                               "ref": g.get("ref", "")} for g in hist],
        })
    return out


def render(gmap: list, as_of: str = "") -> str:
    L = [f"GATE MAP" + (f" · as of {as_of}" if as_of else "")]
    L.append("=" * 78)
    L.append(f"{'gate':<12} {'class':<14} {'state':<10} {'keyholder':<22} last change")
    L.append("-" * 78)
    for g in gmap:
        L.append(f"{g['name']:<12} {g['class']:<14} {g['state']:<10} {g['keyholder']:<22} {g['last_change']}"
                 + ("  · keyholder-only (#81)" if g["human_only"] else ""))
        if g["note"]:
            L.append(f"{'':<12} {g['note']}")
        if g["paths"]:
            L.append(f"{'':<12} paths: {', '.join(g['paths'])}")
        for d in g["delegations"]:
            L.append(f"{'':<12} ↳ delegated to {d['grantee']} at L{d['level']} ({d['grant_id']}"
                     + (f", {d['ref']}" if d['ref'] else "") + f", {d['kind']})"
                     + (f" — scope: {d['scope']}" if d['scope'] else ""))
        for h in g["grant_history"]:
            if h["state"] == "active" and any(d["grant_id"] == h["grant_id"] for d in g["delegations"]):
                continue
            L.append(f"{'':<12} · {h['grant_id']} {h['state']}: {h['grantee']} L{h['level']} "
                     f"by {h['grantor']} {h['issued']}" + (f" ({h['ref']})" if h['ref'] else ""))
    L.append("")
    L.append("locked = keyholders only · open = any actor inside the walls · "
             "delegated = a keyholder granted non-keyholders a level (named above)")
    return "\n".join(L)


def bootpack_lines(gmap: list) -> list:
    """The compact GATES section for the boot pack."""
    L = []
    for g in gmap:
        line = f"- **{g['name']}** ({g['class']}): {g['state'].upper()} · keyholder {g['keyholder']}"
        if g["human_only"]:
            line += " · keyholder-only forever (#81)"
        L.append(line)
        for d in g["delegations"]:
            L.append(f"  - delegated to `{d['grantee']}` at L{d['level']} ({d['grant_id']}"
                     + (f", {d['ref']}" if d['ref'] else "") + ")"
                     + (f" — {d['scope']}" if d['scope'] else ""))
        if g["note"]:
            L.append(f"  - {g['note']}")
    return L
