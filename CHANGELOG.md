# Changelog

## 0.6.3 — THE BLOCK, TRUE TO ITS OWN LAW
The block does what the record says it does. Found by a second agent on a second
machine, told only "you are the first user, run the protocol" (credit: cc-2, whose
patch against the 0.6.1 sdist was the design; re-implemented on main).
- PROVENANCE ENFORCED AT THE DOOR: the `stage` tool's author is the server's seat
  (`MAGNEMO_AGENT`), always. A seat that tries to sign as a human (a keyholder in
  `trust.humans`) is refused with a plain reply and the refusal is ledgered as a
  `stage` denial; a different non-human name is kept in the new provenance field
  `claimed_author` (appended; nothing renamed).
- THE GATE LIFT IS A WORD: `magnemo yes` promotes the top of the queue (the order
  `review` shows), `yes <id-fragment>` one note (two matches = refuse and list),
  `yes --all` the whole queue with one ledger entry per note; `magnemo no <fragment>
  --reason TXT` rejects one (the reason stays required). `--by` defaults to the first
  keyholder; `--reason` to "approved in chat". Every entry these verbs write carries
  `ran_by` — the agent seat if `MAGNEMO_AGENT` is set, else `terminal`: the yes is the
  human's, the hand that ran it is on the record. `promote`/`reject` are unchanged
  (the long form). Promotion is still never an MCP tool: the four tools stay four.
- THE RECORD TELLS THE TRUTH ABOUT ITSELF: the MCP boot line reports `queue=<n>` (and
  `held=<n>`), as the docs always said; the `stage` reply and the `review` footer name
  the word (`magnemo yes`); the README's install line carries the uv fallback the site
  paste has (Python 3.11+; `uv tool install magnemo` if pip can't).
- THE OPERATOR FLAG, deterministic: a note staged by a human hand (the author is a
  keyholder) carries the operator tag automatically; no text sniffing.
No change to gates, action classes, the L1 cap, trust weights, half-life, the ledger's
fields (one appended), the vault layout, config keys, the four tool names, or the boot
pack of an unchanged vault.

## 0.6.2 — THE PUBLIC FACE (metadata release; no engine change) — built Sep 10, pre-flighted, not released
Public face + registry metadata; no engine change. The wheel's code is byte-for-byte
the 0.6.1 engine plus the words strangers read first.
- README opens in plain words: the ladder line, the receipt line, the one paste
  (the same paste as magnemo.ai, verbatim), then the builder's paragraph.
- PyPI summary: "Governed memory for AI agents. Memory with receipts." Project URLs
  (homepage, source, docs, changelog). Source points at github.com/magnemo-ai/magnemo,
  which lights on Source Day.
- MCP tool metadata: plain titles and annotations on the four tools (retrieve and
  bootpack are read-only; nothing is destructive). Registry name
  `io.github.magnemo-ai/magnemo` declared in the README.
- Companion distribution `magnemo-mcp` (metadata only: depends on magnemo, exposes
  the `magnemo-mcp` entry point) so `uvx magnemo-mcp` and the MCP registry's
  `pypi` package resolve to the server directly.
- Order codes and register numbers left this changelog; the words stay.

## 0.6.1 — THE FRONT DOOR
The one-paste install, battle-tested on a machine that never heard of us.
- THE GUARD: `magnemo guard <vault>` makes every canonical note and
  rendered file owner-immutable at the OS level (macOS chflags uchg; Linux chmod,
  advisory), gives agents a writable work/ beside the vault, and writes the
  body's deny rules into the repo's .claude/settings.json; `guard --off` is a
  human verb, ledgered. Supersession everywhere: renders archive the prior bytes
  (_index/archive), deleted renders are re-rendered by doctor, and
  `magnemo restore <path|id> [--to <version>]` brings a version back in one
  command. Sentinel's injection patterns (S1–S13) are shared by rooms and the
  inbox: an instruction-shaped drop is staged tainted with an alert note.
- THE ROOM v0: magnemo room open|say|connect|separate|watch|close|replay|list —
  agents talk in a room a human keeps open; every message is a STAGED note with
  provenance (from_seat, to, class, salience); Sentinel sweeps on stage (secret
  formats + 12 injection patterns); taint is hereditary through replies;
  connect/separate/close are human verbs; the human seat is never removable; a
  closed room replays from its ledger alone. A message may propose, never promote.
- THE SUBSCRIPTION SOCKET v0: magnemo run "<task>" --engine claude runs an
  Agent SDK session through your own Claude login (the sanctioned door; no token is
  ever stored, no key of ours exists) with the vault mounted through the four
  verbs; every action staged with provenance; the FUEL line prints usage and the
  plan-window signal; cap exits say why. --schedule writes a plain-speech RAIL.md
  row and installs a launchd/cron job; --card = runs · tokens · API list-price
  avoided. codex/gemini refuse with "not wired yet". Optional extra: magnemo[claude].
- THE BOARDROOM MOUNT: a vault now declares its own shape
  (`partitions`, `scopes`); promotion can render a note to disk with the
  prior file hash ledgered (`render`); `doctor` re-stages hand edits to
  rendered files as founder drift; `magnemo inbox` is a staging door with
  Sentinel at it; `bootpack.excerpts` lift sections from canon; `handoff
  --body-file`. Engine writers follow the vault's shape. No new MCP tool.
- THE LAST DEAD NAME: the environment variables are MAGNEMO_VAULT,
  MAGNEMO_AGENT, MAGNEMO_SCOPE, MAGNEMO_PARTITIONS. **MEMOS_\* honored through
  0.6.x; removed in 0.7** — if a MAGNEMO_* name is unset and its MEMOS_* twin
  is set, the old value is used silently (one mapping, in `magnemo.config`);
  `magnemo doctor` prints one plain line naming any MEMOS_* still in use.
  Internal register numbers no longer appear in the README or docs.
- THE CHEST ("machines die, the memory doesn't"):
  `magnemo chest add|status|push|tick` conducts copies of the vault to up to
  two places you own (a git remote, a folder) on events — promote, receipt,
  handoff, N staged notes, a 24h ceiling — swept by Sentinel before every
  push (any secret-shaped hit blocks the push, stages a note naming file +
  pattern, never the value). `magnemo mount --from <git|dir>` restores a
  vault: fetch, verify the hash-chained ledger (broken chain refused), doctor,
  boot pack — byte-identical to the source's. Two drifted vaults reconverge
  through staging (foreign canon → proposals, `chest:merge from <label>`;
  ledgers unioned with a CHEST_MERGE marker); canon is never overwritten.
  Gauge line in `doctor` and the boot pack header. No hosted destination
  exists in code. No new MCP tool — the four-verb server stays four.
- PUBLIC FACE HYGIENE: license is Apache-2.0 in the metadata, with
  LICENSE and NOTICE shipped inside the wheel and sdist.
- `mnemosyneos` shim removed.
- ONE server: the legacy five-tool `magnemo-server` console script and
  `magnemo.server` are removed; `magnemo-mcp` (retrieve / stage / bootpack /
  handoff) is the only server. Its stdio plumbing lives in `magnemo.transport`.
- ONE version: `__version__` is read from `pyproject.toml` (source) or package
  metadata (installed) — never a second hand-typed string.
- Front door is Magnemo only: internal character names no longer appear on the
  public face (README, package metadata, docstrings, mount banner).
- NEW `magnemo mount`: registers the MCP server in the project's `.mcp.json`
  itself — absolute vault path, venv-pinned command, merge-never-clobber. The
  step nobody has to guess anymore.
- `magnemo doctor` auto-checks `.mcp.json` when present, and now catches the
  configs that would kill the server at boot (invalid MEMOS_SCOPE, missing
  MEMOS_VAULT) BEFORE your agent trips on them. Agent-environment-dependent
  findings (PATH, ${var} paths) are warnings, not failures.
- A stray file in `_staging` (a .DS_Store, a hand-made note without
  frontmatter) no longer bricks the MCP server at boot — skipped with a
  warning, per file, never silently.
- `python3 -m magnemo` now works — the PATH-failure fallback every agent
  reaches for.
- MEMOS_SCOPE rejection message now names the valid partitions and the fix.
- `magnemo init` prints the two next commands; server identity reports the
  real version (was frozen at 0.5.0).


## 0.6.0 — OPEN BETA — 2026-08-29
Same build as 0.6.0b1, re-versioned without the pre-release marker: pip
prefers stable versions, so the b1 was shadowed by the 0.0.1 name-holder for
anyone running a plain `pip install magnemo`. Beta honesty lives where it
belongs — the 0.x version line, KNOWN_LIMITS.md, and "open beta" on the site.

## 0.6.0b1 — superseded same day — 2026-08-29
The engine goes public: `pip install magnemo` becomes true for everyone.
- First functional release published to PyPI, replacing the 0.0.1 name-holder
  stub. Beta-marked version; the source repo remains private until launch.
- README rebuilt around the stranger's quickstart: install → init → mount →
  first bootpack → doctor, using the installed `magnemo` / `magnemo-mcp`
  entry points end to end.
- **KNOWN_LIMITS.md** added — the honest beta caveats list, shipped in the
  package where a stranger will actually read it.
- Engine code is 0.5.1's, unchanged: the release is the door, not the rooms.

## 0.5.1 — dogfood QoL — 2026-08-24
Customer zero's first friction batch, all four notes answered:
- **`magnemo stage`** — the founder's terminal write path. Same gate as agents
  (`Governance.agent_write`): provenance `--source` mandatory, lands in
  `_staging/` only, KAIROS-scored, duplicate-flagged, Foresight-logged
  (`via: cli`). Body via `--body`, `--file`, or stdin.
- **`magnemo doctor`** — the rename survivor's checkup. Validates python/venv,
  vault reachability + partition/special dirs + writability, config load,
  ledger JSONL integrity, and any `--mount .mcp.json` (command exists,
  `MEMOS_VAULT` reachable). Read-only; exit 1 on any FAIL. Born from the
  mnemosyne→magnemo rename that silently broke every absolute path.
- Fresh-vault bootpack no longer prints the raw epoch ("ledger time
  1970-01-01…"); an empty ledger renders as "before any ledger event (fresh
  vault)". `trust.EPOCH` names the sentinel; determinism unchanged.
- `dist/pypi` rebuilt at the current version (stale 0.0.1 artifacts removed).
  PyPI keeps the 0.0.1 stub until launch; local dist serves dogfood installs.

## 0.5.0 — "First Trust" — 2026-08-22
**The trust ledger is math.** Computed Autonomy, four blocks, merged under
founder authorization. Backfilled merge-code successes for earlier pull requests; `claude-worker` reads
effective L2 SUPERVISED in merge-code under G0001.
- **B1 · Trust ledger math** (`magnemo/trust.py`, docs/TRUST.md). Five action classes
  (read · stage · merge-code · promote-canon · publish), five levels (L0 frozen → L4
  keyholder). Score = Σ weight × 0.5^(age/half-life) over append-only ledger events after
  the latest violation; thresholds → level; class floors/ceilings; `promote-canon` and
  `publish` hard-capped at L1 for non-humans in code. One `violation` resets and
  freezes the class; only a keyholder `reinstate` lifts it. New verbs: `magnemo autonomy
  <actor>` (scorecard), `magnemo trust record|events`. Derived events: promote → success,
  reject → failure (author, `stage`); MCP partition-wall hit → denied. `TrustLedger.record`
  accepts `ts=` and extra keys; the six base keys are unchanged. Config: `trust` block.
- **B2 · Grants as data** (`magnemo/grants.py`, docs/GRANTS.md). `trust.grant` ledger
  records: grantee, classes, level, scope, conditions, kind (standing | one-time), ref,
  expires, grantor; revocation is a second record. Keyholder-only verbs `magnemo grant` /
  `magnemo revoke`; `magnemo grants` shows state (active · revoked · expired · consumed ·
  pending). `effective = min(computed, granted)`; human-only classes and L4 refused at
  issue AND clamped at compute. One-time grants are consumed by the trust event that cites
  them (`trust record … --grant G0001`). **Genesis grant G0001** on record.
- **B3 · The Gate Map** (`magnemo/gates.py`, docs/GATES.md). Six default
  gates in config (`trust.gates`): retrieve · staging · main · gate-code · canon · publish.
  State derived from the grant ledger at `as_of`: `computed` gates read delegated/locked;
  locked and open gates never move by grant; human-only gates cannot be opened by config.
  `magnemo gates [--as-of] [--json]`. Boot pack gains `## GATES` after the Charter,
  rendered at ledger time (pure). LEDGER TAIL count unchanged.
- **B4 · The agent always knows its own level.** `bootpack.generate(..., actor=)` adds
  `## YOUR AUTONOMY — <actor>` after GATES: effective/computed/granted/score per class, active
  grants, FROZEN classes shouted, at ledger time. CLI `bootpack --actor A` (default
  `$MEMOS_AGENT`); MCP `bootpack` always passes `MEMOS_AGENT`. `handoff.record` stores
  `levels` on the ledger entry and in the staged note; LAST HANDOFF renders "autonomy at the
  boundary". Packs for different actors differ only in their own section (tested).

## 0.4.0 — "First Name" — 2026-08-21
**The product is named: Magnemo.** Ratified by the boardroom 2026-08-20 after the full
The name collision gauntlet (PyPI · npm · GitHub · SERP clear; USPTO + CIPO zero hits,
live and dead; magnemo.ai / magnemo.io secured).

- Python package renamed `mnemosyneos` → `magnemo`. All imports, entry points
  (`magnemo`, `magnemo-mcp`, `magnemo-server`), and `python -m magnemo.cli`.
- MCP server identity → `magnemo`. The four tools (`retrieve`, `stage`, `bootpack`,
  `handoff`) and their contracts are unchanged.
- `mnemosyneos` remains as a thin deprecation shim for this release only (removed in 0.5).
- Vault config file is now `_config/magnemo.json`; vaults still carrying
  `_config/mnemosyneos.json` are read transparently (write path always targets the new name).
- `MEMOS_*` environment variables are unchanged — they are the live mount contract.
- The persona **Mnemosyne** keeps her name wherever she is the persona. Historical vault notes
  keep their original wording; history is provenance.

Earlier in 0.4.0 (pre-rename): the four-verb MCP server, cross-session mount gate.

## 0.3.0 — 2026-08-20
salience v1 · Boot Pack + Charter · Boundary Telemetry · Foresight counters.

## 0.2.0
Package `memos` → `mnemosyneos`; Telos sockets (consequence, taint, token budgets).
