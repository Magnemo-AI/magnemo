"""magnemo.mcp — the four-verb MCP server.

A stdio Model Context Protocol server that exposes EXACTLY four tools, each
bound to existing magnemo code (nothing reimplemented here):

  retrieve(query, scope?, budget?)   → search.Index        scored, budgeted, rendition-selected
  stage(note, provenance)            → governance.agent_write   the ONLY write verb; _staging only
  bootpack(scope?, class?)           → bootpack.generate   the v0.3 boot pack (worker | partner)
  handoff(usage, trigger, cut?)      → handoff.record      boundary telemetry + staged handoff note

Promotion is NOT a tool — it is the keyholder's act, always: it stays theirs, via the CLI. There is
no shell, no eval, no file tool — least privilege is the surface itself.

Configuration (env):
  MAGNEMO_VAULT       path to the vault root                         (required)
  MAGNEMO_AGENT       calling agent's identity, e.g. "ops-agent"     (default "agent")
  MAGNEMO_PARTITIONS  comma list this agent may WRITE to             (default: all)
  MAGNEMO_SCOPE       comma list this agent may READ from            (default: all)
                    retrieve/bootpack scope must fall inside it — the scope wall.

Run:  MAGNEMO_VAULT=./vault python -m magnemo.mcp
"""
from __future__ import annotations
import os, sys, json
from .transport import Server
from .config import env
from .vault import PARTITIONS, STORES
from .bootpack import CLASSES
from .handoff import TRIGGERS
from . import bootpack, handoff, foresight, kairos

TOOL_NAMES = ("retrieve", "stage", "bootpack", "handoff")

DEFAULT_BUDGET = 4000      # bytes of served payload per retrieve, unless the caller says otherwise
MAX_BUDGET = 32000         # hard ceiling — a budget above this is clamped and the clamp is logged
SNIPPET_CHARS = 240        # "snippet" rendition: per-note body excerpt length


def tools_spec(vault=None) -> list:
    """The four verbs. With a vault, the schema enums reflect THAT vault's declared
    partitions and stores; without one, the defaults every vault is born with."""
    P = tuple(vault.partitions) if vault is not None else PARTITIONS
    S = dict(vault.stores) if vault is not None else STORES
    return [
        {
            "name": "retrieve",
            "title": "Look something up in memory",
            "annotations": {"title": "Look something up in memory", "readOnlyHint": True,
                            "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
            "description": (
                "Retrieve canonical (keyholder-approved) memory relevant to a query. Returns a "
                "scored, BUDGETED payload: mn:// pointers plus snippet renditions, never raw "
                "dumps. Scope is partition-walled; payload size is logged to the Foresight "
                "counters. Cite the returned rid when the action resolves."),
            "inputSchema": {"type": "object", "properties": {
                "query": {"type": "string", "description": "what you need to remember"},
                "scope": {"type": "string", "enum": list(P),
                          "description": "partition to search (must be inside this agent's MAGNEMO_SCOPE)"},
                "budget": {"type": "integer", "minimum": 200, "maximum": MAX_BUDGET,
                           "default": DEFAULT_BUDGET,
                           "description": "max payload bytes; results are truncated/downgraded to fit and the truncation is logged"},
                "k": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
            }, "required": ["query"]},
        },
        {
            "name": "stage",
            "title": "Draft an entry for a person to review",
            "annotations": {"title": "Draft an entry for a person to review", "readOnlyHint": False,
                            "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
            "description": (
                "Stage a memory candidate for KEYHOLDER review. This is the only write verb: "
                "the note lands in _staging/ with mandatory provenance and never touches "
                "canon. Returns the staged id, its salience, and a duplicate flag. "
                "Malformed or paperless (no provenance) notes are refused."),
            "inputSchema": {"type": "object", "properties": {
                "note": {"type": "object", "properties": {
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "partition": {"type": "string", "enum": list(P)},
                    "store": {"type": "string",
                              "description": "store within the partition: " + "; ".join(
                                  f"{p}: {', '.join(S[p])}" for p in P)},
                    "tags": {"type": "string", "description": "comma-separated"},
                    "supersedes": {"type": "string", "description": "id of the note this replaces"},
                    "impact": {"type": "string",
                               "enum": ["security", "money", "correctness", "process", "info"],
                               "description": "declared impact class (consequence). Default: info"},
                    "taint": {"type": "string",
                              "description": "REQUIRED when content originates from an untrusted source — label it"},
                }, "required": ["title", "body", "partition", "store"]},
                "provenance": {"type": "object", "properties": {
                    "source": {"type": "string",
                               "description": "run id / gate id / audit id — where this knowledge came from"},
                    "author": {"type": "string",
                               "description": "defaults to this server's MAGNEMO_AGENT identity"},
                }, "required": ["source"]},
            }, "required": ["note", "provenance"]},
        },
        {
            "name": "bootpack",
            "title": "Read what this agent wakes up knowing",
            "annotations": {"title": "Read what this agent wakes up knowing", "readOnlyHint": True,
                            "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
            "description": (
                "The boot pack: Charter first (verbatim, never fabricated), then the Gate "
                "Map, YOUR AUTONOMY (this agent's own trust levels), canon digest, open "
                "threads, salience-ranked review queue, last handoff, ledger tail. Read it "
                "FIRST on every wake. Deterministic: same vault state, same bytes."),
            "inputSchema": {"type": "object", "properties": {
                "scope": {"type": "string", "enum": list(P),
                          "description": "partition to orient on (must be inside MAGNEMO_SCOPE)"},
                "class": {"type": "string", "enum": list(CLASSES), "default": "worker",
                          "description": "worker = lean; partner = adds the relationship layer when a codex exists"},
            }},
        },
        {
            "name": "handoff",
            "title": "Record where this session stopped",
            "annotations": {"title": "Record where this session stopped", "readOnlyHint": False,
                            "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
            "description": (
                "Record a session boundary: appends telemetry (usage %, trigger, what was "
                "cut) to the append-only handoffs ledger AND stages a provenance-complete "
                "handoff note. The next bootpack inherits it. Doctrine: hand off at ~88-90%, "
                "do not ride to the wall."),
            "inputSchema": {"type": "object", "properties": {
                "usage": {"type": "number", "minimum": 0, "maximum": 100,
                          "description": "context usage percent at the boundary"},
                "trigger": {"type": "string", "enum": list(TRIGGERS)},
                "cut": {"type": "string", "description": "what was cut / deferred at the boundary"},
            }, "required": ["usage", "trigger"]},
        },
    ]


class MemoryServer(Server):
    """Four verbs, bound to existing code. Inherits the JSON-RPC/stdio
    plumbing from transport.Server; declares the one tool surface."""

    def __init__(self):
        super().__init__()
        rs = env("SCOPE", ",".join(self.vault.partitions))
        self.read_scope = self.vault.resolve_scope(rs.split(","))
        if not self.read_scope:
            sys.stderr.write(f"MAGNEMO_SCOPE={rs!r} names no valid partition or scope — "
                             f"valid: {', '.join(self.vault.partitions)}"
                             f"{' · aliases: ' + ', '.join(self.vault.scopes()) if self.vault.scopes() else ''}"
                             " (unset MAGNEMO_SCOPE to allow all)\n")
            sys.exit(2)
        # P-54: the record tells the truth about itself — the queue depth at session start, as the docs say
        try:
            _q = [n for n in self.vault.staged() if n.status == "staged"]
            _h = [n for n in self.vault.staged() if n.status == "held"]
            _qs = f" queue={len(_q)}" + (f" held={len(_h)}" if _h else "")
        except Exception:
            _qs = ""
        sys.stderr.write(f"[magnemo.mcp] agent={self.agent} read_scope={','.join(self.read_scope)} "
                         f"write_partitions={','.join(self.write_partitions)} tools={','.join(TOOL_NAMES)}{_qs}\n")

    def tools_spec(self) -> list:
        return tools_spec(self.vault)

    # ---------------- scope wall (read side) ----------------
    def _gate_scope(self, scope, verb: str):
        """Resolve the partition filter for a read verb. Explicit scope must be
        inside MAGNEMO_SCOPE; omitted scope means "everything I'm allowed"."""
        if scope is not None:
            if scope not in self.vault.partitions:
                raise ValueError(f"unknown scope: {scope!r} (one of {', '.join(self.vault.partitions)})")
            if scope not in self.read_scope:
                raise PermissionError(
                    f"SCOPE WALL: agent '{self.agent}' may not {verb} partition '{scope}'. "
                    f"Read scope: {', '.join(self.read_scope)}")
            return (scope,)
        return tuple(self.read_scope)

    # ---------------- retrieve ----------------
    def t_retrieve(self, a):
        query = (a.get("query") or "").strip()
        if not query:
            raise ValueError("retrieve requires a non-empty query")
        parts = self._gate_scope(a.get("scope"), "retrieve")
        k = max(1, min(int(a.get("k", 5)), 20))
        asked = int(a.get("budget", DEFAULT_BUDGET))
        budget = max(200, min(asked, MAX_BUDGET))
        # Candidate set from the existing index: scope-walled, receipt logged,
        # cost NOT logged here — the served (post-budget) payload is what counts.
        out = self.index.search(query, k, None, max_chars=SNIPPET_CHARS,
                                agent=self.agent, log_receipt=True,
                                partitions=None if set(parts) == set(self.vault.partitions) else parts,
                                log_cost=False)
        rendered, rendition, truncated = select_rendition(out["results"], budget)
        payload = {
            "rid": out["rid"], "query": query,
            "scope": list(parts), "budget": budget,
            "rendition": rendition, "truncated": truncated,
            "candidates": len(out["results"]), "served": len(rendered),
            "results": rendered,
        }
        text = json.dumps(payload, indent=1)
        nbytes = len(text.encode("utf-8"))
        payload["payload_bytes"] = nbytes
        foresight.log_cost(self.vault, "retrieval", nbytes, {
            "via": "mcp", "rid": out["rid"], "agent": self.agent, "k": k,
            "scope": ",".join(parts), "budget": budget, "budget_asked": asked,
            "rendition": rendition, "truncated": truncated,
            "candidates": len(out["results"]), "served": len(rendered)})
        if not rendered:
            payload["note"] = ("No canonical memory matches in scope. Staged notes are "
                               "excluded until a keyholder promotes them.")
        return json.dumps(payload, indent=1)

    # ---------------- stage ----------------
    def t_stage(self, a):
        note = a.get("note")
        prov = a.get("provenance")
        if not isinstance(note, dict):
            raise ValueError("REFUSED: 'note' must be an object")
        if not isinstance(prov, dict):
            raise ValueError("REFUSED: paperless note — 'provenance' object is mandatory")
        source = (prov.get("source") or "").strip()
        if not source:
            raise ValueError("REFUSED: paperless note — provenance.source is mandatory "
                             "(run id / gate id / audit id)")
        # P-54 · PROVENANCE ENFORCED AT THE DOOR: the author of an MCP stage is the seat
        # (MAGNEMO_AGENT), always. A seat may not sign as a keyholder; a different non-keyholder
        # name is kept as `claimed_author` (an appended provenance field), never as the author.
        claimed = (prov.get("author") or "").strip()
        author = self.agent
        if claimed:
            from .config import load_config as _lc
            from . import trust as _trust
            if _trust.is_human(_lc(self.vault.root), claimed):
                try:
                    _trust.record(self.vault, self.agent, "stage", "denied", by="magnemo.mcp",
                                  reason=f"an agent seat cannot sign as a keyholder: claimed author {claimed!r}")
                except Exception:
                    pass
                raise PermissionError(
                    f"REFUSED: an agent seat cannot sign as a keyholder ({claimed!r}); "
                    "say who directed it in `source`")
        title = (note.get("title") or "").strip()
        body = (note.get("body") or "").strip()
        part = note.get("partition")
        store = note.get("store")
        missing = [k for k, v in (("title", title), ("body", body),
                                  ("partition", part), ("store", store)) if not v]
        if missing:
            raise ValueError(f"REFUSED: malformed note — missing {', '.join(missing)}")
        if part not in self.vault.partitions:
            raise ValueError(f"REFUSED: unknown partition {part!r}")
        if store not in self.vault.stores[part]:
            raise ValueError(f"REFUSED: store {store!r} is not valid in partition "
                             f"'{part}' (valid: {', '.join(self.vault.stores[part])})")
        if part not in self.write_partitions:
            # P-02: a wall hit is a recorded `denied` event for this agent in `stage`
            # — small, decaying, and visible on the scorecard. Never raises into the refusal.
            try:
                from . import trust
                trust.record(self.vault, self.agent, "stage", "denied", by="magnemo.mcp",
                             reason=f"partition wall: tried to stage into '{part}'")
            except Exception:
                pass
            raise PermissionError(
                f"DENIED: agent '{self.agent}' may not stage into partition '{part}'. "
                f"Write partitions: {', '.join(self.write_partitions)}")
        impact = note.get("impact") or "info"
        # Pattern separation: is this a near-duplicate of something already
        # known (canon in-partition) or already waiting (staged)?
        dup = nearest_duplicate(title, body, part, self.vault)
        # The ONLY write path: governance.agent_write → vault.stage → _staging/.
        # KAIROS salience is computed inside agent_write, at stage time.
        n = self.gov.agent_write(
            title=title, body=body, partition=part, store=store,
            author=author, source=source, tags=note.get("tags", "") or "",
            supersedes=note.get("supersedes", "") or "", taint=note.get("taint", "") or "",
            impact=impact)
        if claimed and claimed != author:
            n.extra["claimed_author"] = claimed
            self.vault.rewrite(n)
        if dup:
            n.extra["dup_of"] = dup["id"]
            n.extra["dup_sim"] = f"{dup['sim']:.4f}"
            tags = [t.strip() for t in n.tags.split(",") if t.strip()]
            if DUP_TAG not in tags:
                tags.append(DUP_TAG)
            n.tags = ",".join(tags)
            self.vault.rewrite(n)
        nbytes = len(n.to_markdown().encode("utf-8"))
        foresight.log_cost(self.vault, "stage", nbytes, {
            "via": "mcp", "id": n.id, "agent": author, "partition": part, "store": store,
            "salience": n.salience, "dup_of": dup["id"] if dup else "",
            "taint": bool(n.taint)})
        return json.dumps({
            "staged": n.id, "status": n.status, "path": f"_staging/{n.id}.md",
            "salience": n.salience, "salience_components": json.loads(n.salience_components or "{}"),
            "duplicate_of": dup["id"] if dup else None,
            "duplicate_similarity": round(dup["sim"], 4) if dup else None,
            "taint": n.taint or None,
            "bytes": nbytes,
            "note": "Awaits KEYHOLDER review: magnemo yes (or magnemo review). "
                    "Not canonical; will not appear in retrieve until promoted.",
        }, indent=1)

    # ---------------- bootpack ----------------
    def t_bootpack(self, a):
        cls = a.get("class") or "worker"
        if cls not in CLASSES:
            raise ValueError(f"unknown class: {cls!r} (worker|partner)")
        scope = a.get("scope")
        parts = self._gate_scope(scope, "boot on")
        if scope is None and set(parts) != set(self.vault.partitions):
            if len(parts) == 1:
                scope = parts[0]
            else:
                raise ValueError(f"this agent's read scope is {','.join(parts)}; "
                                 "name one partition as scope")
        text = bootpack.generate(self.vault, cls, scope, actor=self.agent)
        foresight.log_cost(self.vault, "bootpack", len(text.encode("utf-8")),
                           {"via": "mcp", "class": cls, "scope": scope or "all",
                            "agent": self.agent, "to": "mcp"})
        return text

    # ---------------- handoff ----------------
    def t_handoff(self, a):
        if "usage" not in a or not a.get("trigger"):
            raise ValueError("handoff requires usage (0-100) and trigger "
                             f"({'|'.join(TRIGGERS)})")
        cut = (a.get("cut") or "").strip()
        e = handoff.record(self.vault, a["usage"], a["trigger"], cut,
                           actor=self.agent, source=f"mcp/handoff/{a['trigger']}")
        foresight.log_cost(self.vault, "handoff", len(json.dumps(e).encode("utf-8")),
                           {"via": "mcp", "agent": self.agent, "note_id": e["note_id"],
                            "usage_pct": e["usage_pct"], "trigger": e["trigger"]})
        return json.dumps({
            "recorded": e, "telemetry": "_ledger/handoffs.jsonl (append-only)",
            "staged_note": f"_staging/{e['note_id']}.md",
            "note": "The next bootpack inherits this boundary (LAST HANDOFF section).",
        }, indent=1)


# ---------------- deterministic helpers (no clock, no RNG, no model) ----------------
DUP_TAG = "dup-candidate"
DUP_THRESHOLD = 0.6   # trigram-Jaccard; above this the note is flagged as a near-duplicate


def nearest_duplicate(title: str, body: str, partition: str, vault) -> dict | None:
    """Pattern separation: the most similar existing note (canon in the same
    partition, or any staged note) above DUP_THRESHOLD. Uses the KAIROS
    trigram machinery — same algorithm that feeds the novelty component."""
    mine = kairos.trigrams(title + " " + body)
    best = None
    pool = [n for n in vault.canonical(partition)] + \
           [n for n in vault.staged() if n.status == "staged"]
    for c in pool:
        sim = kairos._jaccard(mine, kairos.trigrams(c.title + " " + c.body))
        if sim >= DUP_THRESHOLD and (best is None or sim > best["sim"]):
            best = {"id": c.id, "sim": sim, "status": c.status}
    return best


def pointer(r: dict) -> str:
    """mn:// pointer: a stable address, not a payload."""
    return f"mn://{r['partition']}/{r['store']}/{r['id']}"


def select_rendition(results: list, budget: int) -> tuple:
    """Fit the result set into `budget` bytes, deterministically:
      1. 'snippet'  — pointer + title + score + snippet, all results
      2. 'snippet'  — drop lowest-ranked results until it fits
      3. 'pointer'  — pointers only (id/title/score/yield), dropping from the tail if needed
    Returns (rendered, rendition, truncated)."""
    def snip(r):
        d = {"pointer": pointer(r), "id": r["id"], "title": r["title"],
             "score": r["score"], "yield": r["yield"], "snippet": r["snippet"]}
        if r.get("taint"):
            d["taint"] = r["taint"]
        return d

    def ptr(r):
        d = {"pointer": pointer(r), "id": r["id"], "title": r["title"],
             "score": r["score"], "yield": r["yield"]}
        if r.get("taint"):
            d["taint"] = r["taint"]
        return d

    def size(items):
        return len(json.dumps(items, indent=1).encode("utf-8"))

    full = [snip(r) for r in results]
    if size(full) <= budget:
        return full, "snippet", False
    for cut in range(len(full) - 1, 0, -1):
        if size(full[:cut]) <= budget:
            return full[:cut], "snippet", True
    ptrs = [ptr(r) for r in results]
    for cut in range(len(ptrs), 0, -1):
        if size(ptrs[:cut]) <= budget:
            return ptrs[:cut], "pointer", True
    return [], "pointer", True


def main():
    MemoryServer().run()


if __name__ == "__main__":
    main()
