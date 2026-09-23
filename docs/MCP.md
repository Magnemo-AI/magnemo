# The four-verb MCP server

`magnemo.mcp` is a Model Context Protocol server over stdio. It exposes
**exactly four tools**, each bound to code that already exists in the package.
Nothing is reimplemented; the server is a governed door, not a second brain.

```
retrieve(query, scope?, budget?, k?)   read   → search.Index.search
stage(note, provenance)                WRITE  → governance.agent_write   (the only write verb)
bootpack(scope?, class?)               read   → bootpack.generate
handoff(usage, trigger, cut?)          write* → handoff.record           (* telemetry + staged note)
```

**Promotion is not a tool** — it is your act, always. Nothing an agent can call moves a
note into canon. That asymmetry is the protocol. There is no shell, eval, or
file tool — least privilege is the surface itself.

---

## Install & mount

```bash
pip install -e .                 # zero runtime deps; Python ≥ 3.11
magnemo init ./vault         # once
```

One-line `.mcp.json` (Claude Code reads it from the project root; any MCP client
takes the same shape):

```json
{"mcpServers":{"magnemo":{"command":"python3","args":["-m","magnemo.mcp"],"env":{"MAGNEMO_VAULT":"/abs/path/to/vault","MAGNEMO_AGENT":"my-agent","MAGNEMO_SCOPE":"dev,ops,shared","MAGNEMO_PARTITIONS":"dev,ops,shared"}}}}
```

| env | meaning | default |
|---|---|---|
| `MAGNEMO_VAULT` | vault root (created if missing) | **required** |
| `MAGNEMO_AGENT` | identity stamped on every stage/handoff/receipt | `agent` |
| `MAGNEMO_SCOPE` | partitions this agent may **read** (retrieve / bootpack) — the scope wall | all |
| `MAGNEMO_PARTITIONS` | partitions this agent may **stage into** | all |

Diagnostics go to stderr; stdout is pure JSON-RPC.

---

## The tools

### `retrieve(query, scope?, budget?, k?)`
Canonical memory only — staged notes are invisible until you promote them.
Returns a JSON payload, never a raw dump:

```json
{"rid":"…","scope":["dev"],"budget":4000,"rendition":"snippet","truncated":false,
 "candidates":3,"served":3,
 "results":[{"pointer":"mn://dev/knowledge/<id>","id":"…","title":"…","score":2.1,
             "yield":"+2/-0","snippet":"first 240 chars…"}],
 "payload_bytes":812}
```

- `scope` must lie inside `MAGNEMO_SCOPE`; otherwise `SCOPE WALL` and nothing is logged.
- `budget` (bytes, 200–32 000, default 4 000) is honoured deterministically:
  **snippet → fewer snippets → `mn://` pointers only**. `truncated` tells you it happened.
- `rid` is the retrieval receipt. Cite it with `magnemo outcome <rid> approved|denied`
  and every note that informed the action earns or loses yield.

### `stage(note, provenance)`
The only write verb. Lands in `_staging/` as a **memory candidate**; never touches canon.

```json
{"note":{"title":"…","body":"…","partition":"ops","store":"knowledge",
         "impact":"money","tags":"pattern","taint":"inbound-email"},
 "provenance":{"source":"run#1847","author":"ops-agent"}}
```

Refused before touching disk: missing provenance (**paperless**), blank `source`,
missing title/body/partition/store, unknown store, partition outside `MAGNEMO_PARTITIONS`.
Returns `{staged, salience, salience_components, duplicate_of, duplicate_similarity, taint, bytes}`.

### `bootpack(scope?, class?)`
The document a session reads first. `class` = `worker` (lean) | `partner`
(adds the relationship layer when a codex exists). Sections, in doctrine order:
Charter (verbatim, never fabricated) → **gates** (the Gate Map at ledger time) →
**your autonomy** (the mounting agent's own scorecard, `MAGNEMO_AGENT`) → canon digest → open threads & KAIROS-ranked queue → **last handoff** → ledger tail. Pure function of vault state: same state,
same bytes. The MCP path returns the pack; it never writes `_index/`.

### `handoff(usage, trigger, cut?)`
`trigger ∈ wall|planned|compaction|other`. Appends one entry to
`_ledger/handoffs.jsonl` (with the agent's autonomy `levels` at the boundary) and
stages a provenance-complete handoff note. The next `bootpack` serves it under
`LAST HANDOFF`. Doctrine: hand off at ~88–90%.

---

## Cascades — deterministic, zero model calls

```
stage(note, provenance)
  │
  ├─ validate ──── paperless / malformed ──▶ REFUSED (nothing on disk)
  ├─ write-partition wall ──────────────────▶ DENIED
  ├─ pattern separation: trigram-Jaccard vs in-partition canon + staged queue
  │        ≥ 0.6 → dup_of / dup_sim in frontmatter + `dup-candidate` tag
  ├─ governance.agent_write ─▶ KAIROS salience (consequence·novelty·operator·source) ─▶ _staging/<id>.md
  └─ foresight 'stage' event {id, salience, dup_of, taint}
```

```
retrieve(query, scope?, budget?)
  │
  ├─ scope gate ─── outside MAGNEMO_SCOPE ──▶ SCOPE WALL (no receipt, no cost event)
  ├─ Index.search walled to scope  (BM25 × strength × yield × taint-penalty)  ─▶ receipt rid
  ├─ rendition select to fit budget:  snippet ─▶ truncated snippet ─▶ mn:// pointers
  └─ foresight 'retrieval' event {rid, scope, budget, rendition, truncated, candidates, served}
```

```
bootpack(scope?, class?)
  │
  ├─ scope gate
  ├─ bootpack.generate:  CHARTER (verbatim) ─▶ GATES (ledger time) ─▶ CANON DIGEST ─▶ OPEN THREADS + queue
  │                      ─▶ LAST HANDOFF (from handoffs.jsonl) ─▶ LEDGER TAIL
  └─ foresight 'bootpack' event {class, scope, bytes}
```

```
handoff(usage, trigger, cut?)
  │
  ├─ handoff.record ─▶ _ledger/handoffs.jsonl  (append-only)
  │                 ─▶ governance.agent_write ─▶ _staging/<handoff-note>.md  (KAIROS-scored)
  ├─ foresight 'handoff' event
  └─ next bootpack() — any process, any session — renders it under LAST HANDOFF
```

---

## Invariants (each has a test in `tests/test_mcp.py`)

| invariant | how it holds |
|---|---|
| staging is the only write path | every verb leaves the canon file set byte-identical; `promote` → `unknown tool` |
| provenance mandatory | 9 refusal shapes, none reach disk |
| scope walls | `MAGNEMO_SCOPE=dev` never returns ops-only canon; explicit `scope=ops` → `SCOPE WALL` |
| budgets cap payloads, truncation logged | served ≤ budget; `truncated` in both payload and cost event; clamp at 32 000 logged |
| free tier | `mcp.py` imports stdlib + package only; no network words anywhere in the chain |
| least privilege | exactly four names; dispatch gated to *declared* tools; no eval/exec/shell |

---

## Three postures

**1. Native.** The agent runs with this server mounted and uses the four verbs
directly: `bootpack` on wake, `retrieve` before acting, `stage` what it learned,
`handoff` at ~88%. The vault is the agent's memory. (Claude Code via `.mcp.json`,
any MCP client.)

**2. Mount-and-govern.** The agent already has its own memory (a framework store,
a vector DB, a notes folder). Mount this server *alongside* it and route only the
*governed* moments through the four verbs: candidates worth your review go to
`stage`; decisions the agent must not make alone are `retrieve`d from canon. The
existing store keeps scratch; Magnemo keeps truth. Nothing in the agent's own
memory becomes canon without passing the staging gate.

**3. Gateway.** One server process, many agents, each with its own
`MAGNEMO_AGENT` / `MAGNEMO_SCOPE` / `MAGNEMO_PARTITIONS` — or one process per agent
behind a gateway that sets those per connection. Scope walls give a dev agent
dev, an ops agent ops, and the `shared/` bus to both; receipts, cost events, and
handoff telemetry stay attributable per agent. Promotion still happens in one
place: the founder's CLI.

In every posture the same two things are true: **agents can only stage**, and
**keyholders alone promote**.
