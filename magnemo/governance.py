"""magnemo.governance — Layer 3: the Magnemo spine (Phase 1 surface).

The governed write: agents stage; humans promote. Every review action is
recorded to the Trust Ledger. Supersession is explicit and never silent.
"""
from __future__ import annotations
import os as _os
import os, json, time
from .vault import Vault, Note, now_iso
from .config import load_config
from . import kairos

LEDGER_FILE = "trust_ledger.jsonl"


class TrustLedger:
    """v0: an append-only record of every governance event, keyed by action
    class. Phase 1 records; the graduation math (L0→L3) reads this file in a
    later phase. Append-only JSONL — the ledger never forgets."""

    def __init__(self, vault: Vault):
        self.path = os.path.join(vault.root, "_ledger", LEDGER_FILE)

    def record(self, action_class: str, verdict: str, actor: str,
               subject: str, detail: str = "", ts: str | None = None,
               **extra) -> None:
        """Append one entry. The six base keys never change; `extra` keys
        (trust events, grants) ride alongside them. `ts` backdates a KNOWN
        historical event — callers that do so also set `recorded_at`."""
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        entry = {
            "ts": ts or now_iso(),
            "action_class": action_class,   # e.g. "memory.promote" | "trust.event" | "trust.grant"
            "verdict": verdict,             # approved | rejected | <event kind> | issued | revoked
            "actor": actor,                 # who decided / recorded (human or subsystem)
            "subject": subject,             # note id | scored actor | grantee
            "detail": detail,
        }
        entry.update(extra)
        with open(self.path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def entries(self, action_class: str | None = None) -> list:
        if not os.path.exists(self.path):
            return []
        out = []
        with open(self.path) as f:
            for line in f:
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if action_class is None or e.get("action_class") == action_class:
                    out.append(e)
        return out

    def pass_rate(self, action_class: str) -> tuple:
        es = self.entries(action_class)
        if not es:
            return (0.0, 0)
        ok = sum(1 for e in es if e["verdict"] == "approved")
        return (ok / len(es), len(es))


class Governance:
    def __init__(self, vault: Vault):
        self.vault = vault
        self.ledger = TrustLedger(vault)

    # ---------------- agent-facing ----------------
    def agent_write(self, *, title: str, body: str, partition: str, store: str,
                    author: str, source: str, tags: str = "",
                    supersedes: str = "", taint: str = "",
                    impact: str = "info") -> Note:
        """The ONLY write path agents get. Always lands in _staging/.

        KAIROS (v0.3): salience is computed HERE, at stage time — a
        deterministic weighted sum of declared consequence, novelty vs
        canon, operator signal, and source weight. Stored in frontmatter
        so the review queue can present what matters most, first.

        TAINT IS HEREDITARY: if this note supersedes (derives from) a tainted
        note, it inherits the taint automatically — only a human clears a
        lineage (cli: cleartaint). Injection cannot launder itself through
        derivation."""
        self.vault._canonical_dir(partition, store)  # validate target early
        inherited = taint
        if supersedes and not inherited:
            try:
                parent = self.vault.read(supersedes)
                if parent.taint:
                    inherited = parent.taint
            except FileNotFoundError:
                pass
        note = Note(
            id=self.vault.new_id(title),
            title=title, body=body,
            author=author, written=now_iso(), source=source,
            status="staged", partition=partition, store=store,
            tags=tags, supersedes=supersedes, taint=inherited,
            impact=impact,
        )
        cfg = load_config(self.vault.root)
        kairos.apply(note, self.vault.canonical(partition), cfg)
        self.vault.stage(note)
        from . import chest
        chest.notify(self.vault, "stage")      # THE CHEST (#129): counts toward the N trigger
        return note

    # ---------------- KAIROS: operator signal + rescoring ----------------
    def flag(self, note_id: str, reviewer: str, reason: str = "") -> Note:
        """Founder-only: flag a staged note as operator-salient. Adds the
        operator tag and recomputes salience — by config invariant the note
        now outranks every unflagged note in the queue."""
        n = self.vault.read(note_id)
        if n.status != "staged":
            raise ValueError(f"{note_id} is not staged (status={n.status})")
        cfg = load_config(self.vault.root)
        tag = cfg["kairos"]["operator_tag"]
        tags = [t.strip() for t in n.tags.split(",") if t.strip()]
        if tag not in tags:
            tags.append(tag)
        n.tags = ",".join(tags)
        kairos.apply(n, self.vault.canonical(n.partition), cfg)
        self.vault.rewrite(n)
        self.ledger.record("memory.flag", "approved", reviewer, note_id, reason)
        return n

    def rescore(self) -> list:
        """Recompute salience for every staged note (legacy notes staged
        before KAIROS, or after canon has grown and novelty shifted)."""
        cfg = load_config(self.vault.root)
        canon_by_part: dict = {}
        touched = []
        for n in self.vault.staged():
            if n.status != "staged":
                continue
            if n.partition not in canon_by_part:
                try:
                    canon_by_part[n.partition] = self.vault.canonical(n.partition)
                except (KeyError, ValueError):
                    canon_by_part[n.partition] = []
            kairos.apply(n, canon_by_part[n.partition], cfg)
            self.vault.rewrite(n)
            touched.append(n)
        return touched

    # ---------------- Telos: consequence recording ----------------
    def record_outcome(self, rid: str, verdict: str, actor: str,
                       detail: str = "") -> list:
        """Link an action's outcome back to the memories that informed it.
        verdict: 'approved' (credit every note in the retrieval receipt) or
        'denied'/'failed' (debit). This is how individual memories earn a
        track record — retrieval ranking reads these yields on every search."""
        import json as _json, os as _os
        path = _os.path.join(self.vault.root, "_ledger", "retrievals.jsonl")
        receipt = None
        if _os.path.exists(path):
            with open(path) as f:
                for line in f:
                    try:
                        e = _json.loads(line)
                    except _json.JSONDecodeError:
                        continue
                    if e.get("rid") == rid:
                        receipt = e
        if receipt is None:
            raise FileNotFoundError(f"no retrieval receipt {rid}")
        touched = []
        good = verdict == "approved"
        for nid in receipt["note_ids"]:
            try:
                n = self.vault.read(nid)
            except FileNotFoundError:
                continue
            if good:
                n.yield_w += 1
            else:
                n.yield_l += 1
            self.vault.rewrite(n)
            touched.append(nid)
        self.ledger.record("memory.outcome", verdict, actor, rid,
                           detail or f"{len(touched)} notes {'credited' if good else 'debited'}")
        from . import chest
        chest.notify(self.vault, "receipt")    # THE CHEST (#129): a receipt resolved with an outcome
        return touched

    def clear_taint(self, note_id: str, reviewer: str, reason: str) -> Note:
        """Human-only: clear taint on a note after verification."""
        n = self.vault.read(note_id)
        old = n.taint
        n.taint = ""
        n.body += f"\n\n> taint '{old}' CLEARED by {reviewer} on {now_iso()}: {reason}"
        self.vault.rewrite(n)
        self.ledger.record("memory.cleartaint", "approved", reviewer, note_id, reason)
        return n

    # ---------------- human-facing (CLI only; never an MCP tool) ----------------
    def promote(self, note_id: str, reviewer: str, reason: str = "", ran_by: str | None = None) -> Note:
        """`ran_by` (P-54, the two-yes law): the yes is the human's (`reviewer`); the hand
        that ran the command is on the record too, as an appended ledger field."""
        note = self.vault.read(note_id)
        if note.status != "staged":
            raise ValueError(f"{note_id} is not staged (status={note.status})")
        note.status = "canonical"
        note.reviewed_by = reviewer
        note.reviewed_at = now_iso()
        # explicit supersession: archive the old note, link forward
        if note.supersedes:
            try:
                old = self.vault.read(note.supersedes)
                old.status = "archived"
                old.body += f"\n\n> superseded by [[{note.id}]] on {now_iso()}"
                self.vault._place_canonical(old)
            except FileNotFoundError:
                pass  # superseded target already gone; link remains in frontmatter
        self.vault._place_canonical(note)
        self.ledger.record("memory.promote", "approved", reviewer, note_id, reason,
                           **({"ran_by": ran_by} if ran_by else {}))
        self._render(note, reviewer)
        # P-02: a promoted candidate is a verified success for its author in `stage`.
        from . import trust
        trust.record(self.vault, note.author, "stage", "success", by=reviewer,
                     reason=f"promoted {note_id}" + (f": {reason}" if reason else ""),
                     ref=note_id)
        from . import chest
        chest.notify(self.vault, "promote")    # THE CHEST (#129): a canon change is a copy event
        return note

    def render_path(self, note: Note):
        """Where this note's body renders on disk, or None: <vault>/<render.root>/<note.render>."""
        from .config import load_config
        root = (load_config(self.vault.root).get("render") or {}).get("root", "")
        rel = (note.extra or {}).get("render", "")
        if not root or not rel:
            return None
        return _os.path.normpath(_os.path.join(self.vault.root, root, rel))

    def _render(self, note: Note, reviewer: str) -> None:
        """RENDER-ON-PROMOTE (P-19): the file on disk is the rendered view of a
        promoted memory. The prior file's hash is ledgered BEFORE it is replaced —
        an overwrite is a receipt, never a loss."""
        import hashlib as _h
        path = self.render_path(note)
        if path is None:
            return
        from . import guard
        prior, archived = None, None
        if _os.path.exists(path):
            with open(path, "rb") as f:
                prior_bytes = f.read()
            prior = _h.sha256(prior_bytes).hexdigest()
            archived = guard.archive_prior(self.vault.root, note.extra.get("render", ""), prior_bytes)   # SUPERSESSION: the prior body is kept
        data = (note.body.rstrip("\n") + "\n").encode("utf-8")   # a rendered file ends with one newline
        _os.makedirs(_os.path.dirname(path), exist_ok=True)
        with guard.writable(self.vault.root, path):
            with open(path, "wb") as f:
                f.write(data)
        guard.relock_new(self.vault)
        self.ledger.record("memory.render", "rendered", reviewer, note.id, note.extra.get("render", ""),
                           prior_sha256=prior, new_sha256=_h.sha256(data).hexdigest(),
                           archived=(_os.path.relpath(archived, self.vault.root) if archived else None))

    def reject(self, note_id: str, reviewer: str, reason: str, ran_by: str | None = None) -> Note:
        note = self.vault.read(note_id)
        if note.status != "staged":
            raise ValueError(f"{note_id} is not staged (status={note.status})")
        note.status = "rejected"
        note.reviewed_by = reviewer
        note.reviewed_at = now_iso()
        note.body += f"\n\n> REJECTED by {reviewer} on {now_iso()}: {reason}"
        # rejected notes are kept in staging with rejected status: rejections teach
        path = os.path.join(self.vault.root, "_staging", f"{note_id}.md")
        with open(path, "w") as f:
            f.write(note.to_markdown())
        self.ledger.record("memory.promote", "rejected", reviewer, note_id, reason,
                           **({"ran_by": ran_by} if ran_by else {}))
        # P-02: a rejection is a recorded failure for the author in `stage` — rejections teach.
        from . import trust
        trust.record(self.vault, note.author, "stage", "failure", by=reviewer,
                     reason=f"rejected {note_id}: {reason}", ref=note_id)
        return note

    # ---------------- provenance ----------------
    def provenance(self, note_id: str) -> dict:
        n = self.vault.read(note_id)
        chain = []
        cur = n
        seen = set()
        while cur.supersedes and cur.supersedes not in seen:
            seen.add(cur.supersedes)
            try:
                prev = self.vault.read(cur.supersedes)
            except FileNotFoundError:
                break
            chain.append({"id": prev.id, "title": prev.title,
                          "written": prev.written, "status": prev.status})
            cur = prev
        return {
            "id": n.id, "title": n.title, "author": n.author,
            "written": n.written, "source": n.source, "status": n.status,
            "reviewed_by": n.reviewed_by, "reviewed_at": n.reviewed_at,
            "partition": n.partition, "store": n.store,
            "supersession_chain": chain,
            "ledger": self.ledger.entries("memory.promote"),
        }
