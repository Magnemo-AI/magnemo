# Magnemo

**Tools gave your agent hands. MCP gave it a nervous system. Magnemo gives it a brain.**

Governed memory for AI agents. Every entry with a receipt. Your agent writes the
draft; nothing is kept until you say yes.

## The one paste
Open your AI (Claude Code, Cursor, Windsurf, or anything that speaks MCP) in any of your project folders, and paste this:

```text
Set up Magnemo in this project:
1. Install it: pip install magnemo. It needs Python 3.11 or newer. If pip can't find it, install uv (curl -LsSf https://astral.sh/uv/install.sh | sh) and then run: uv tool install magnemo
2. Initialize the vault: magnemo init
3. Register the MCP server: run magnemo mount — it writes this project's MCP config itself.
4. Verify: run magnemo doctor and confirm everything passes.
5. Stage the first memory: one line on what this project is, using magnemo stage. Show me the note id.
6. Then tell me the exact command to approve it, and remind me to restart you so the memory mounts.
If anything fails, show me what went wrong and fix it if you can.
```

You'll know it worked — your AI will tell you who it is now.

**For builders.** Magnemo is an MCP server with four tools — `retrieve`, `stage`,
`bootpack`, `handoff` — and a CLI for the human side: review, promote, reject.
It runs on your machine, in plain markdown files you own, with zero network calls
(the `doctor` line proves it). Every promotion is a person's click, recorded with
who wrote the entry, when, and through which gate — memory with a witness. Trust is
computed from that record, never asserted. It mounts beside any memory you already
run (a folder of notes, Obsidian, a RAG stack). Python 3.11+, zero dependencies,
Apache-2.0.

Fresh vault? THE CHARTER section will say it isn't promoted yet — that is the
governance speaking: Magnemo never fabricates canon. Stage a charter, review it,
promote it, and every boot thereafter serves it back verbatim.
(`magnemo` not found after install? pip's script folder isn't on PATH —
`python3 -m magnemo` always works.)

**Open beta — read [KNOWN_LIMITS.md](KNOWN_LIMITS.md) before trusting it with anything you can't lose.** Honest caveats, no fine print.

## Agents draft, people keep — the one rule
Agents get four MCP tools. Promotion is not one of them.

| Actor  | Door                | Can do |
|--------|---------------------|--------|
| Agents | MCP server (stdio)  | `retrieve` canonical memory · `stage` → **staging only, the one write tool** · `bootpack` on wake · `handoff` at the boundary |
| Human  | CLI + git (any editor)| review the queue · **promote / reject** · edit anything · own everything |

## Quick start (open beta)
Five minutes from install to a governed, booted agent. Python 3.11+, zero dependencies.

```bash
# 1 · install — needs Python 3.11 or newer; if pip can't find it, install uv and run: uv tool install magnemo
pip install magnemo

# 2 · create a vault — plain markdown you own; read it in any editor
magnemo init ./vault

# 3 · mount it into your agent (Claude Code / any MCP client) — .mcp.json:
#   {"mcpServers":{"magnemo":{
#     "command":"magnemo-mcp",
#     "env":{"MAGNEMO_VAULT":"/absolute/path/to/vault",
#            "MAGNEMO_AGENT":"my-agent",
#            "MAGNEMO_SCOPE":"ops,shared",
#            "MAGNEMO_PARTITIONS":"ops,shared"}}}}
#   (full tool reference and postures: docs/MCP.md)

# 4 · render the first boot pack — what a fresh session wakes up knowing
magnemo bootpack --stdout

# 5 · checkup — python, vault, config, ledger, and your .mcp.json mount
magnemo doctor --mount .mcp.json
```

Then the loop begins: agents write to staging, you review.
```bash
magnemo yes             # the gate lift is a word: promote the top of the queue (yes <id-fragment> · yes --all)
magnemo no <id> --reason "…"   # reject one — the reason is required; rejections teach
magnemo review          # the interactive queue, when you want to read first
magnemo ledger          # every decision, forever
```
Beta honesty: read [KNOWN_LIMITS.md](KNOWN_LIMITS.md) before you rely on it.

## The vault
```
vault/
  dev/      knowledge/ playbooks/ decisions/ debt/        ← example: a dev team's partition
  ops/      knowledge/ playbooks/ clients/ decisions/ style/  ← example: an ops team's partition
  shared/   tickets/ changelog/                            ← interop bus (gated)
  _staging/   agent writes await review here
  _index/     machine-managed
  _ledger/    trust_ledger.jsonl — append-only, never forgets
```
Every note is markdown with provenance frontmatter (author, written, source,
status, reviewed_by, supersedes, strength). **Provenance is the file format.**

## New in v0.2 — the consequence sockets (consequence, taint, token budgets)
- **Retrieval receipts**: every search returns a `rid` and logs which notes it
  served (`_ledger/retrievals.jsonl`) plus the payload size in chars.
- **Outcome recording** (`magnemo outcome <rid> approved|denied --by NAME`): links
  an action's result back to the memories that informed it. Each note accrues
  `yield_w / yield_l` — an earned track record — and **ranking multiplies by
  proven yield**. Memory that pays ranks up; memory that misleads sinks.
- **Taint propagation**: writes from untrusted sources carry `taint:` in
  frontmatter; taint is **hereditary** through supersession and only a human
  clears it (`magnemo cleartaint`). Injection cannot launder itself through
  derivation, and tainted notes are rank-penalized and excludable.
- **Char budgets**: `retrieve(budget=…)` bounds every payload; payload
  size is measured and logged on every retrieval — the instrumentation for the
  token-efficiency benchmark is on by default from day one.

## New in v0.3 — salience-sorted review — so a human reads what mattered first
The founder's attention is the scarcest resource in the loop. Every staged
note now gets a **deterministic salience score at stage time** — no model
calls, no embeddings — stored in frontmatter (`salience` +
`salience_components`) so the ranking is auditable from the file alone:

- **consequence** — the writer's declared impact class
  (security > money > correctness > process > info, via `stage(impact=…)`)
- **novelty** — trigram/tag overlap vs existing canon in the same partition;
  duplicates of settled truth sink, new claims rise
- **operator signal** — `cli flag <note-id> --by NAME`; by config invariant a
  founder-flagged note outranks *any* unflagged note
- **source weight** — audit/postmortem findings outrank routine runs

`cli review` presents the queue salience-descending with score + components,
capped per pass (`--batch N`, default from config), and reports queue depth
up front; the MCP server reports queue depth at session start. `cli rescore`
backfills legacy notes. Weights live in the vault's documented config file —
see [docs/CONFIG.md](docs/CONFIG.md).

## New in v0.3 — the Boot Pack: served on every wake — the agent never starts from nothing
```bash
python -m magnemo.cli bootpack [--scope dev|ops|shared] [--class worker|partner]
```
One command renders `BOOT_PACK.md` — the orientation a fresh session boots
from. Section order is doctrine, for both classes: **(1) the Charter,
verbatim, always first** (an explicit placeholder if not yet promoted — the
Charter is never fabricated); (2) canon digest — every canonical note's
title, one-line summary, and stable path; (3) open threads, staged count,
and the top-5 staged notes by salience; (4) trust-ledger tail.

`--class partner` additionally serves a **RELATIONSHIP LAYER** sourced from
a codex file (voice/lore/relationship — what makes a spawn a partner, not a
clone). Worker boots omit it and stay lean. No codex file, no section: a
partner boot degrades gracefully. The codex source is a pluggable seam —
see [docs/CONFIG.md](docs/CONFIG.md).

The pack is **deterministic**: a pure function of vault state — identical
state yields identical bytes, per class (tested).

## New in v0.3 — Boundary Telemetry — every handoff records where it stopped and why
```bash
python -m magnemo.cli handoff --usage 91 --trigger planned --cut "deferred X" --by NAME
python -m magnemo.cli handoff --report     # every boundary ever, as a table
```
Sessions end at boundaries — the context wall, a planned stop, a compaction —
and untracked boundaries are where continuity silently dies. Each `handoff`
appends a structured telemetry entry to `_ledger/handoffs.jsonl`
(**append-only**: usage %, trigger, what was cut, actor) *and* stages a
provenance-complete handoff note for review like any other memory candidate.
Known historical boundaries can be recorded honestly with `--when`: the entry
keeps both `ts` (when the boundary happened) and `recorded_at` (when it was
written down).

**The ~90% soft-threshold doctrine.** Don't ride to the wall. At ~90% context
usage, write the handoff and stand down — a handoff written *at* the wall is
written in a panic with no room to verify the catch. The first recorded
datum is the scar that set the rule: **Aug 13 2026, 98% usage, trigger=wall**
(operator-confirmed). Everything after ~90% should be boundary work, not new
work; the telemetry exists so the doctrine gets numbers instead of vibes.

## New in v0.3 — Foresight counters — what memory costs, measured from day one
```bash
python -m magnemo.cli costs      # per-kind payload costs + the stated baseline
```
Every memory payload served — a retrieval result set, a boot pack — logs an
append-only event to `_ledger/costs.jsonl`: bytes plus a rough token
estimate (bytes/4, documented, swappable for a real tokenizer later).
`cli costs` summarizes per kind and **states the measured baseline** — the
number every future payload optimization (renditions, pointers, adaptive
resolution) gets judged against. First datum: a full worker boot of this
repo's vault costs ~465 tokens. A failed counter never fails the retrieval
it was measuring.

## v0.5.0 "First Trust" — the trust ledger is math

Every actor holds a computed autonomy level per action class (read · stage · merge-code ·
promote-canon · publish), derived only from append-only ledger events: `score = Σ weight ×
0.5^(age/half-life)`, thresholds → L0 frozen … L3 autonomous; L4 keyholder is held by humans,
never computed. Grants are ledger records (`magnemo grant`) — a standing order becomes a grant id, so permission is data with a receipt — and the Gate Map
(`magnemo gates`) plus your own scorecard ride every boot pack. `promote-canon` and `publish`
stay human-only forever. Read `docs/TRUST.md`, `docs/GRANTS.md`, `docs/GATES.md`.

## v0.4.0 "First Name" — the product is Magnemo
Ratified 2026-08-20 after the naming gauntlet. Package `magnemo`; CLI `python -m magnemo.cli`
(or `magnemo`); MCP server `magnemo-mcp`. The previous package name is retired.
Full notes: [CHANGELOG.md](CHANGELOG.md).

## New in v0.4 — the four-tool MCP server — the whole agent surface, nothing more
`python -m magnemo.mcp` (or `magnemo-mcp`) exposes **exactly four tools**, each
bound to existing code — `retrieve` · `stage` · `bootpack` · `handoff`. Promotion is not
a tool — promotion is a human act, always. Zero deps, stdio, stdlib only.

```
retrieve ─▶ scope gate ─▶ walled BM25 ─▶ budget/rendition (snippet→pointer) ─▶ cost event
stage    ─▶ provenance check ─▶ dup flag ─▶ salience ─▶ _staging/ ─▶ cost event
bootpack ─▶ Charter ─▶ digest ─▶ salience-ranked queue ─▶ LAST HANDOFF ─▶ ledger tail
handoff  ─▶ handoffs.jsonl ─▶ staged note ─▶ next bootpack inherits it
```

Tested invariants: staging is the only write path · provenance mandatory · scope walls
(`MAGNEMO_SCOPE`) · budgets cap payloads with logged truncation · free tier · least privilege.
Three postures (native / mount-and-govern / gateway), full tool reference and cascade
diagrams: **[docs/MCP.md](docs/MCP.md)**. `magnemo-mcp` is the only server.

## The chest — machines die, the memory doesn't
```bash
magnemo chest add git <url-you-own> --label laptop     # Copy B
magnemo chest add path /Volumes/Drawer/vault --label drawer   # Copy C
magnemo chest push                                     # swept for secrets first, every time
magnemo mount --from <url-or-dir> ./vault              # restore onto a new machine
```
Magnemo *conducts* copies to places you own; it never *holds* them. Full
contract: [docs/CHEST.md](docs/CHEST.md).

## Guarantees (Phase 1 — Governed Recall)
- Agent writes NEVER reach canonical stores directly — staging only, always.
- Search returns canonical (human-reviewed) notes only. Staged claims are invisible.
- Partition walls enforced per agent (`MAGNEMO_PARTITIONS`); cross-partition = DENIED.
- Supersession is explicit: old notes archive with a forward link. Nothing deletes.
- Rejections are kept and recorded — rejections teach.
- Every promote/reject lands in the append-only Trust Ledger with actor + reason.

## Designed-in evolution (do not remove these seams)
- `strength` field + score hook in `search.py` → Phase 2 reinforcement/decay.
- `TrustLedger.pass_rate()` → the L0→L3 graduation math.
- `Index.search()` signature is stable → embedding retrieval swaps in behind it.
- Consolidation/reflection jobs write through `Governance.agent_write` like any
  agent — the sleep cycle inherits the review queue for free.

## Tests
```bash
python -m unittest discover -s tests -v     # incl. full MCP round-trips (legacy + four-verb)
# or: pip install -e ".[test]" && pytest
```

— Silver Valley Technologies Inc. · Phase 1 of 3 · The memory that learns is
the memory that is governed.

---
Registry name: `mcp-name: io.github.magnemo-ai/magnemo` · Source: https://github.com/magnemo-ai/magnemo · Home: https://magnemo.ai
