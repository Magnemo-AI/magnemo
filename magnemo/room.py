"""magnemo.room — THE ROOM v0: agents that talk to each other, with the human in the room.

"Talk is staging. Canon is human." A room is a SEAT SET sharing ONE ledger for as
long as a human keeps it open. Every message is a STAGED note with provenance
{from_seat, to, class, salience}; Sentinel sweeps every message on stage (secret
formats + injection patterns); taint is hereditary through replies. A message may
PROPOSE; it can never PROMOTE — no room verb writes canon, trust, or grants.
Connect / separate / close are HUMAN verbs. A human seat is always present and
never removable. A closed room is a ledger you can replay.

Files: rooms/transcript/ (messages, as staged notes) · _ledger/rooms/<room>.jsonl
(the room's own hash-chained ledger).
"""
from __future__ import annotations
import os, re, json, hashlib
from .vault import Vault, now_iso

PARTITION, STORE = "rooms", "transcript"
CLASSES = ("report", "proposal", "question", "alert")

from .sentinel import INJECTION  # S1–S13, shared with the inbox


class RoomError(Exception):
    """Plain English, every time."""


def ensure_partition(v: Vault) -> bool:
    """A room needs a home: declare rooms/transcript if this vault lacks it."""
    if PARTITION in v.partitions:
        return False
    from .config import load_config, config_path
    cfg = load_config(v.root)
    parts = dict(cfg.get("partitions") or {p: list(s) for p, s in v.stores.items()})
    parts[PARTITION] = [STORE]
    cfg["partitions"] = parts
    from . import guard
    with guard.writable(v.root, config_path(v.root)), open(config_path(v.root), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    v._shape = None
    v.init()
    return True


def humans(v: Vault) -> tuple:
    from .config import load_config
    return tuple(h.lower() for h in (load_config(v.root).get("trust", {}).get("humans") or ["founder"]))


def is_human(v: Vault, seat: str) -> bool:
    return seat.strip().lower() in humans(v)


def _ledger_path(v: Vault, room: str) -> str:
    return os.path.join(v.root, "_ledger", "rooms", f"{room}.jsonl")


def _lines(v: Vault, room: str) -> list:
    p = _ledger_path(v, room)
    if not os.path.isfile(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [l.rstrip("\n") for l in f if l.strip()]


def events(v: Vault, room: str) -> list:
    return [json.loads(l) for l in _lines(v, room)]


def _append(v: Vault, room: str, e: dict) -> dict:
    lines = _lines(v, room)
    e = dict(e); e.setdefault("ts", now_iso()); e["room"] = room
    e["prev"] = hashlib.sha256(lines[-1].encode()).hexdigest() if lines else "genesis"
    os.makedirs(os.path.dirname(_ledger_path(v, room)), exist_ok=True)
    with open(_ledger_path(v, room), "a", encoding="utf-8") as f:
        f.write(json.dumps(e, sort_keys=True) + "\n")
    return e


def list_rooms(v: Vault) -> list:
    d = os.path.join(v.root, "_ledger", "rooms")
    return sorted(f[:-6] for f in os.listdir(d) if f.endswith(".jsonl")) if os.path.isdir(d) else []


def state(v: Vault, room: str) -> dict:
    """The room's state is derived ONLY from its ledger — a closed room replays whole."""
    ev = events(v, room)
    if not ev:
        raise RoomError(f"No room named '{room}'. Rooms here: {', '.join(list_rooms(v)) or 'none'}. Open one: magnemo room open <name> --seats <agent,...>")
    st = {"room": room, "open": False, "seats": [], "human_seats": [], "separated": {}, "opened_by": None,
          "opened_at": None, "closed_at": None, "closed_by": None, "messages": 0, "alerts": 0}
    for e in ev:
        k = e["kind"]
        if k == "ROOM_OPEN":
            st.update(open=True, opened_by=e["by"], opened_at=e["ts"], seats=list(e["seats"]), human_seats=list(e["human_seats"]))
        elif k == "SEAT_CONNECT":
            if e["seat"] not in st["seats"]:
                st["seats"].append(e["seat"])
            st["separated"].pop(e["seat"], None)
        elif k == "SEAT_SEPARATE":
            if e["seat"] in st["seats"]:
                st["seats"].remove(e["seat"])
            st["separated"][e["seat"]] = {"at": e["ts"], "by": e["by"], "reason": e.get("reason", "")}
        elif k == "MESSAGE":
            st["messages"] += 1
        elif k == "ALERT":
            st["alerts"] += 1
        elif k == "ROOM_CLOSE":
            st.update(open=False, closed_at=e["ts"], closed_by=e["by"])
    return st


def open_room(v: Vault, room: str, seats, by: str) -> dict:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,40}", room):
        raise RoomError("A room name is lowercase letters, digits, - or _ (e.g. 'boardroom').")
    if events(v, room):
        st = state(v, room)
        raise RoomError(f"Room '{room}' already exists ({'open' if st['open'] else 'closed at ' + str(st['closed_at'])}). Pick another name, or replay it: magnemo room replay {room}")
    ensure_partition(v)
    seats = [s.strip() for s in seats if s.strip()]
    hum = [s for s in seats if is_human(v, s)]
    if not hum:
        founder = next((h for h in ("founder", "The Founder") if h.lower() in humans(v)), humans(v)[0])
        seats.insert(0, founder); hum = [founder]
    if not [s for s in seats if not is_human(v, s)]:
        raise RoomError("A room needs at least one agent seat alongside the human seat (--seats boardroom,cc).")
    return _append(v, room, {"kind": "ROOM_OPEN", "by": by, "seats": seats, "human_seats": hum})


def _require_human(v: Vault, by: str, verb: str):
    if not is_human(v, by):
        raise RoomError(f"'{verb}' is a human verb — '{by}' is not a keyholder (config trust.humans: {', '.join(humans(v))}). "
                        "Agents cannot invite or remove agents; the human seat decides who is in the room.")


def connect(v: Vault, room: str, seat: str, by: str) -> dict:
    _require_human(v, by, "connect")
    st = state(v, room)
    if not st["open"]:
        raise RoomError(f"Room '{room}' was closed at {st['closed_at']} by {st['closed_by']}; a closed room is a ledger you replay, not a room you join.")
    if seat in st["seats"]:
        raise RoomError(f"'{seat}' is already seated in '{room}'.")
    return _append(v, room, {"kind": "SEAT_CONNECT", "seat": seat, "by": by})


def separate(v: Vault, room: str, seat: str, by: str, reason: str = "") -> dict:
    _require_human(v, by, "separate")
    st = state(v, room)
    if is_human(v, seat):
        raise RoomError("The founder's seat is always present and never removable. Mute is allowed; absence is not.")
    if seat not in st["seats"]:
        raise RoomError(f"'{seat}' is not seated in '{room}' (seats: {', '.join(st['seats'])}).")
    return _append(v, room, {"kind": "SEAT_SEPARATE", "seat": seat, "by": by, "reason": reason})


def close(v: Vault, room: str, by: str) -> dict:
    _require_human(v, by, "close")
    st = state(v, room)
    if not st["open"]:
        raise RoomError(f"Room '{room}' is already closed (at {st['closed_at']} by {st['closed_by']}).")
    return _append(v, room, {"kind": "ROOM_CLOSE", "by": by, "messages": st["messages"], "alerts": st["alerts"]})


def _sweep(body: str):
    from .sentinel import sweep_text
    return sweep_text(body)


def say(v: Vault, room: str, body: str, cls: str, frm: str, to: str = "room", reply_to: str = "", about: str = "") -> dict:
    """Stage a message. Never promotes. Sentinel on stage; taint hereditary through replies."""
    from .governance import Governance
    if cls not in CLASSES:
        raise RoomError(f"class must be one of {', '.join(CLASSES)}")
    st = state(v, room)
    if not st["open"]:
        raise RoomError(f"Room '{room}' was closed at {st['closed_at']} by {st['closed_by']} — nothing more can be said in it. Replay it: magnemo room replay {room}")
    if frm not in st["seats"]:
        sep = st["separated"].get(frm)
        if sep:
            raise RoomError(f"'{frm}' was separated from '{room}' at {sep['at']} by {sep['by']}"
                            + (f" ({sep['reason']})" if sep["reason"] else "") + " — later messages are refused. Only a human seat can connect it again.")
        raise RoomError(f"'{frm}' is not seated in '{room}' (seats: {', '.join(st['seats'])}). Ask the human seat to connect it.")
    if to != "room" and to not in st["seats"]:
        raise RoomError(f"'{to}' is not seated in '{room}'.")
    taint = ""
    kind, pat = _sweep(body)
    stored = body
    if kind == "secret":
        stored = f"[REDACTED by Sentinel on stage: secret-shaped text, pattern {pat}. The value never became a memory.]"
        taint = f"sentinel:secret:{pat}"
    elif kind == "injection":
        taint = f"sentinel:injection:{pat}"
    if reply_to:
        try:
            parent = v.read(reply_to)
        except FileNotFoundError:
            raise RoomError(f"reply_to '{reply_to}' is not a note in this vault.")
        if parent.taint and not taint:
            taint = parent.taint  # hereditary: a reply to a tainted message is tainted
    g = Governance(v)
    n = g.agent_write(title=f"[{room}] {cls} from {frm}" + (f" → {to}" if to != "room" else ""),
                      body=stored, partition=PARTITION, store=STORE, author=frm,
                      source=f"room:{room} from:{frm} to:{to} class:{cls}" + (f" reply_to:{reply_to}" if reply_to else "") + (f" about:{about}" if about else ""),
                      tags=f"room,{cls}", impact=("security" if cls == "alert" or taint else "process"), taint=taint)
    n.extra.update({"room": room, "from_seat": frm, "to": to, "class": cls})
    if reply_to:
        n.extra["reply_to"] = reply_to
    if about:
        n.extra["about"] = about
    v.rewrite(n)
    _append(v, room, {"kind": "MESSAGE", "from_seat": frm, "to": to, "class": cls, "note_id": n.id,
                      "salience": round(n.salience, 4), "taint": taint, "reply_to": reply_to, "about": about})
    if kind:
        _append(v, room, {"kind": "ALERT", "from_seat": "sentinel", "about": n.id,
                          "reason": f"{kind} pattern {pat} in a message from {frm} — tainted; nothing in this room acts on it"})
    return {"note": n, "taint": taint, "alert": bool(kind), "pattern": pat}


def _sentence(v: Vault, e: dict) -> str:
    k = e["kind"]
    if k == "ROOM_OPEN":
        return f"{e['by']} opened the room with seats {', '.join(e['seats'])} (human: {', '.join(e['human_seats'])})."
    if k == "SEAT_CONNECT":
        return f"{e['by']} brought {e['seat']} into the room."
    if k == "SEAT_SEPARATE":
        return f"{e['by']} separated {e['seat']}" + (f" — {e['reason']}" if e.get("reason") else "") + "."
    if k == "MESSAGE":
        try:
            first = v.read(e["note_id"]).body.strip().splitlines()[0][:140]
        except Exception:
            first = "(message not readable)"
        tgt = "" if e["to"] == "room" else f" to {e['to']}"
        tainted = " [TAINTED " + e["taint"] + "]" if e.get("taint") else ""
        return f"{e['from_seat']} said{tgt} ({e['class']}): {first}{tainted}"
    if k == "ALERT":
        return f"ALERT — {e['reason']}."
    if k == "ROOM_CLOSE":
        return f"{e['by']} closed the room after {e.get('messages', '?')} messages."
    if k == "ENGINE":
        return e["sentence"]
    return json.dumps(e)


def _engine_actions(v: Vault, seats, since: str) -> list:
    """Engine actions by any seated agent since the room opened, from the vault's ledgers, as sentences."""
    from .governance import TrustLedger
    out = []
    for e in TrustLedger(v).entries():
        if e.get("ts", "") < since or e.get("actor") not in seats:
            continue
        ac, verdict, subj = e.get("action_class", ""), e.get("verdict", ""), e.get("subject", "")
        if ac == "memory.promote":
            out.append((e["ts"], {"kind": "ENGINE", "ts": e["ts"], "sentence": f"{e['actor']} promoted {subj} to canon — {e.get('detail', '')}".rstrip(" —")}))
        elif ac == "memory.render":
            out.append((e["ts"], {"kind": "ENGINE", "ts": e["ts"], "sentence": f"{e['actor']} rendered {e.get('detail', subj)} to disk (prior hash ledgered)."}))
        elif ac == "memory.outcome":
            out.append((e["ts"], {"kind": "ENGINE", "ts": e["ts"], "sentence": f"{e['actor']} recorded outcome '{verdict}' for receipt {subj}."}))
        elif ac.startswith("trust."):
            out.append((e["ts"], {"kind": "ENGINE", "ts": e["ts"], "sentence": f"{e['actor']} recorded a trust event ({verdict}) for {subj}."}))
    return out


def transcript(v: Vault, room: str, with_engine: bool = True) -> list:
    ev = events(v, room)
    if not ev:
        raise RoomError(f"No room named '{room}'.")
    rows = [(e["ts"], e) for e in ev]
    if with_engine:
        st = state(v, room)
        seats = set(st["seats"]) | set(st["separated"]) | set(ev[0]["seats"])
        rows += _engine_actions(v, seats, ev[0]["ts"])
    rows.sort(key=lambda r: r[0])
    return [f"{ts}  {_sentence(v, e)}" for ts, e in rows]


def replay(v: Vault, room: str) -> dict:
    """From the ledger ALONE: the transcript and the final state."""
    return {"state": state(v, room), "transcript": transcript(v, room, with_engine=False)}
