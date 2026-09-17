# The vault config file — `_config/magnemo.json`

One JSON file per vault, created with defaults by `cli init` (and by
`Vault.init()` when the MCP server first mounts a vault). It is the
founder's file: hand-edit freely. Missing keys fall back to built-in
defaults (`magnemo/config.py`), so a partial file is always valid and
upgrades never break an edited config.

```json
{
  "kairos": {
    "weights":      { "operator": 0.55, "consequence": 0.25, "novelty": 0.12, "source": 0.08 },
    "impact_classes": { "security": 1.0, "money": 0.85, "correctness": 0.7, "process": 0.5, "info": 0.3 },
    "default_impact": "info",
    "source_classes": { "audit": 1.0, "postmortem": 1.0, "incident": 0.9, "gate": 0.7, "review": 0.7 },
    "default_source_weight": 0.3,
    "operator_tag": "founder-flag"
  },
  "review": { "batch": 10 },
  "trust": {
    "weights": { "success": 1.0, "verified": 2.0, "halt": 1.0, "failure": -1.0, "denied": -0.5, "surprise": -3.0 },
    "half_life_days": 90,
    "thresholds": { "1": 0.0, "2": 5.0, "3": 15.0 },
    "classes": {
      "read":          { "floor": 2, "ceiling": 3, "default_grant": 3 },
      "stage":         { "floor": 2, "ceiling": 3, "default_grant": 2 },
      "merge-code":    { "floor": 0, "ceiling": 3, "default_grant": 1 },
      "promote-canon": { "floor": 0, "ceiling": 1, "default_grant": 1 },
      "publish":       { "floor": 0, "ceiling": 1, "default_grant": 1 }
    },
    "humans": ["founder", "The Founder"],
    "gates": [ { "name": "main", "class": "merge-code", "state": "computed", "keyholder": "The Founder", "note": "…" }, "… (six by default, see docs/GATES.md)" ]
  },
  "bootpack": {
    "charter_tag": "charter",
    "open_tag": "open",
    "codex_path": "_codex/CODEX.md",
    "ledger_tail": 10,
    "top_staged": 5
  }
}
```

## `kairos` — deterministic salience at stage time — so you read what mattered first

Every staged note gets `salience = Σ weight × component`, components each
in [0, 1], computed at stage time with **no model calls** — pure functions
of the note, the canon, and this file. Score and raw components are stored
in the note's frontmatter (`salience`, `salience_components`), so every
ranking is auditable from the file alone.

| key | meaning |
|---|---|
| `weights` | The four component weights. **Invariant: `operator` must exceed the sum of the other three** — a founder-flagged note always outranks any unflagged note. Keep this invariant if you retune. |
| `impact_classes` | Consequence value per declared impact class. Agents declare `impact` on `memory_write`; unknown/missing declarations fall back to `default_impact`. Ordering doctrine: security > money > correctness > process > info. |
| `source_classes` | Source-weight tiers. If any keyword appears (case-insensitive substring) in the note's `source` field, the highest matching weight applies; otherwise `default_source_weight` (routine work). Audit and postmortem findings outrank routine runs. |
| `operator_tag` | The tag that carries the operator signal. Set it with `cli flag <note-id> --by NAME` — never by agents on their own notes. |

**Novelty** has no tunable beyond its weight: it is `1 − max similarity`
against existing canon in the same partition, where similarity is the max
of character-trigram Jaccard (title + body) and tag Jaccard. Empty canon ⇒
fully novel. Duplicates of settled truth sink; genuinely new claims rise.

**Unscored notes** (staged before KAIROS) show `salience —` and sort last;
`cli rescore` backfills them. Rescore is also the tool to run after canon
grows enough to shift novelty. Note: rescore rewrites staged files through
the Note model — the H1 line is regenerated from the `title` field (the H1
is derived, the frontmatter is authoritative); unknown frontmatter keys
are preserved verbatim.

## `review`

| key | meaning |
|---|---|
| `batch` | Default batch cap for `cli review`: the queue is presented salience-descending and cut to this many notes per pass. Override per-invocation with `--batch N`. Queue depth is always reported in the header (and by the MCP server on session start, to stderr). |

## `bootpack` — the wake-up document — the agent never starts from nothing

`cli bootpack [--scope P] [--class worker|partner]` renders `BOOT_PACK.md`
(default location `<vault>/_index/BOOT_PACK.md`; `--stdout` prints instead).
Section order is doctrine: **Charter verbatim first** (explicit placeholder
if unpromoted — never fabricated), relationship layer (partner only), canon
digest, open threads + review queue, ledger tail. The pack is a pure
function of vault state + config: identical state ⇒ identical bytes, per
class.

| key | meaning |
|---|---|
| `charter_tag` | The canonical note carrying this tag is the Charter. A *staged* charter is not served — promotion is what makes it the Charter. |
| `open_tag` | Notes (canonical or staged) carrying this tag are listed as open threads. |
| `codex_path` | The codex seam. A markdown file of voice/lore/relationship, included verbatim as the RELATIONSHIP LAYER in **partner** boots only — this is what makes a spawn a partner, not a clone. Relative paths resolve against the vault root; empty string disables. Absent file ⇒ the partner boot degrades gracefully to worker content. Worker boots never include it (lean by doctrine, #87). The source is pluggable in code: pass any `codex_source() -> str \| None` to `bootpack.generate`. |
| `ledger_tail` | Trailing trust-ledger entries included in the pack. |
| `top_staged` | Top-salience staged titles listed (feeds from KAIROS). |

## `trust` — the arithmetic of earned trust

`score = Σ weight[kind] × 0.5^(age_days / half_life_days)` over an actor's
events in a class after its latest violation; `level` is the highest threshold
met, clamped to the class floor/ceiling. Full operator guide: `docs/TRUST.md`.

| key | meaning |
|---|---|
| `weights` | Per event kind. Positive: `success`, `verified`, `halt`. Negative: `failure`, `denied`, `surprise`. `violation` and `reinstate` have no weight — they reset and unfreeze. |
| `half_life_days` | Every contribution halves after this many days. Trust not exercised fades. |
| `thresholds` | Score needed for L1/L2/L3. L4 (keyholder) is never computed. |
| `classes.<class>.floor` / `.ceiling` | Clamp on the *computed* level. `promote-canon` and `publish` are capped at L1 in code for non-keyholders regardless of what is written here. |
| `classes.<class>.default_grant` | Permission an actor holds with no grant on file. Effective level = min(computed, granted). |
| `humans` | Keyholders. L4 everywhere, not scored. Declaring one is a founder edit of this file. |
| `gates` | The Gate Map (docs/GATES.md): list of `{name, class, state, keyholder, note, paths}`. `state`: `locked` · `open` · `computed` (delegated while an active grant covers the class for a non-keyholder, else locked). Keyholder-only classes always read locked. |

## `partitions` · `scopes` — the vault declares its own shape
A vault is born with `dev · ops · shared`. It may declare its own partitions and
stores instead (the declaration is whole — it replaces the defaults, never
unions with them). `scopes` are aliases for `MAGNEMO_SCOPE` / `MAGNEMO_PARTITIONS`:
```json
"partitions": {"doctrine": ["canon"], "state": ["current"], "missions": ["scoped"], "receipts": ["filed"]},
"scopes": {"svtech": ["doctrine", "state", "missions", "receipts"]}
```
Every surface follows the declaration: the MCP tool schema, scope walls,
`magnemo stage --partition`, the boot pack digest, doctor.

## `render` — the file on disk is the rendered view of a promoted memory
`"render": {"root": ".."}` turns it on. A note carrying a `render:` path
(relative to `<vault>/<root>`) is written there **on promotion**, and the ledger
entry `memory.render` carries the prior file's sha256 — an overwrite is a
receipt, never a loss. `doctor` treats a hand edit to a rendered file as
**drift**: it re-stages the edited body as a note by `founder` that supersedes
the canonical one; promote it to keep the edit.

## `inbox` — the only door
`"inbox": {"dir": "../inbox", "routes": [{"match": "*.md", "partition": "state", "store": "current", "render": "{name}", "title": "{stem}"}]}`
`magnemo inbox --as <tag>` stages every file dropped there (never promotes),
with provenance `inbox:<file> sha256:<hash> at <time> by <tag>`, routed by the
first matching glob. Sentinel sweeps each drop first: a secret-shaped hit is
held in `<dir>/blocked/`, a Sentinel note is staged naming file + pattern
(never the value), and the chest refuses to conduct a copy until the held
file is removed.

## `bootpack.excerpts` — sections lifted from canon
`[{"title": "REV BLOCK", "note": "<canonical note title>", "start": "^## REV", "end": "^## "}]`
Rendered right after the Charter, verbatim, from the canonical note — so a
restored copy boots byte-identically.
