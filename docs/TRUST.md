# TRUST — the arithmetic of earned trust

The trust ledger is math. Every identity that acts on the vault — an agent, a
session, a person — is an **actor**. For each **action class** an actor holds an
**autonomy level**, computed from append-only ledger events and nothing else.
No model, no judgment call, no hidden state: every number on a scorecard can be
re-derived by hand from `_ledger/trust_ledger.jsonl` and `_config/magnemo.json`.

```
magnemo autonomy <actor>                       # the scorecard
magnemo trust record <actor> <class> <kind> --by NAME [--reason …] [--ref …] [--when ISO]
magnemo trust events [--actor A] [--class C]   # the raw events, ledger order
```

## Action classes (five, fixed)

| class | what it governs | keyholder-only? |
|---|---|---|
| `read` | retrieve / bootpack (walled by `MAGNEMO_SCOPE`) | no |
| `stage` | writing memory candidates to `_staging/` | no |
| `merge-code` | merging PRs to `main` | no |
| `promote-canon` | moving a note into canon | **yes, forever** |
| `publish` | PyPI / npm / releases / repo settings | **yes, forever** |

## Levels (five, fixed)

| level | name | meaning |
|---|---|---|
| L0 | FROZEN | may not act in this class; only a keyholder reinstates |
| L1 | PROPOSE | may prepare the action and hand it to a keyholder (open the PR, stage the note, request the publish) |
| L2 | SUPERVISED | may perform the action, logging one line per action; a keyholder reviews after |
| L3 | AUTONOMOUS | may perform the action without per-action review; the ledger still records |
| L4 | KEYHOLDER | a person holding the key: performs, grants, revokes, reinstates. **Never computed — held.** |

`promote-canon` and `publish` cap at **L1 for every actor who is not a keyholder**. Not a
config key, not a grant, not a score lifts it — the cap is in code.

## Events (what the ledger records)

| kind | weight (default) | meaning |
|---|---|---|
| `success` | +1.0 | an action in the class completed and was accepted (a merged PR, a promoted candidate) |
| `verified` | +2.0 | a keyholder verified the outcome after the fact |
| `halt` | +1.0 | the actor stopped at a ceiling and waited — a halt honored |
| `failure` | −1.0 | rejected / reverted (a rejected candidate) |
| `denied` | −0.5 | tried an action a wall refused (a partition wall hit via MCP) |
| `surprise` | −3.0 | verification failed or the work deviated from the brief |
| `violation` | *elevator* | acted past a ceiling. Resets the class and freezes it at L0 |
| `reinstate` | *key* | a keyholder lifts the freeze; climbing restarts from zero |

Some events are **derived automatically**, so the ledger fills itself where the
truth is already known:

- `promote` → `success` for the note's author in `stage` (ref = note id)
- `reject` → `failure` for the author in `stage`
- MCP `stage` into a partition outside `MAGNEMO_PARTITIONS` → `denied` in `stage`

Everything else (merges, halts, surprises, violations, reinstatements) is a
keyholder's observation, recorded with `magnemo trust record … --by NAME`. `--when`
backdates a *known* historical event; the entry keeps `recorded_at` with the
real clock so backfills are never silent.

## The formula

```
score(actor, class, as_of) = Σ  weight[e.kind] × 0.5 ^ ( age_days(e) / half_life_days )
                             over events for (actor, class) AFTER the latest violation,
                             with e.ts ≤ as_of

computed_level = L0                             if frozen (violation with no later reinstate)
               = highest L with score ≥ threshold[L]   (L1: 0 · L2: 5 · L3: 15)
                 clamped to [class.floor, class.ceiling], never above L3
               = min(·, L1)                     for promote-canon and publish

effective_level = min(computed_level, granted_level)        (granted: docs/GRANTS.md)
```

**Stairs and elevators.** Positive events are small and additive — five
accepted merges on one day is exactly L2; the same five a day later have decayed
to 4.96 and you are L1 again until the next one lands. One `violation` discards
every event before it and freezes the class at L0; nothing but a keyholder's
`reinstate` lifts it, and the climb restarts from zero. Violations are
per-class: freezing `merge-code` does not touch `stage`.

**Decay.** Every contribution halves every `half_life_days` (default 90).
Trust not exercised fades; decay alone never makes a score negative.

**Floors.** `read` and `stage` floor at L2 — those doors are governed by scope
and partition walls, not by trust; a fresh agent can read in scope and stage for
review on day one. `merge-code` has no floor: a net-negative record is L0 there.

**Keyholders.** Actors listed in `trust.humans` are keyholders: L4 in every class,
not scored. Declaring one is a config edit — the founder's file.

## Reading a scorecard

```
AUTONOMY SCORECARD — claude-worker · as of 2026-08-22T05:41:13Z
class          effective      computed       granted        score
read           L2 SUPERVISED  L2 SUPERVISED  L3 AUTONOMOUS  0.0000
stage          L2 SUPERVISED  L2 SUPERVISED  L2 SUPERVISED  0.0000
merge-code     L1 PROPOSE     L1 PROPOSE     L1 PROPOSE     0.0000
promote-canon  L1 PROPOSE     L1 PROPOSE     L1 PROPOSE     0.0000  keyholder-only cap
publish        L1 PROPOSE     L1 PROPOSE     L1 PROPOSE     0.0000  keyholder-only cap
```

- **computed** is what the actor has *earned* (the ledger).
- **granted** is what a keyholder has *permitted* (grants, or the class default).
- **effective** is the smaller of the two. Permission without a record is still
  L1; a record without permission is still L1. Both must exist to act.

Below the table: per-class components (`count · raw · decayed`), the epoch if a
violation exists, active grants, and the last five events with who recorded
them and why. `--json` gives the same card as data.

## Determinism

`as_of` is a parameter. The CLI defaults to now; anything that must be a pure
function of vault state (the boot pack) scores at **ledger time** — the `ts` of
the latest ledger entry — so identical vault bytes always yield identical
scorecards. There is no clock, RNG, network, or model anywhere in `trust.py`.

## The agent always knows its own level (B4)

- `magnemo bootpack --actor A` (or `MAGNEMO_AGENT` set; the MCP `bootpack` tool
  always passes the mounting agent) adds `## YOUR AUTONOMY — A` right after
  `## GATES`: one row per class, active grants, and any FROZEN class shouted.
  Rendered at ledger time, so the pack stays pure per actor.
- `handoff` records the actor's levels at the boundary on the ledger entry
  (`levels`) and in the staged note; the next boot's `LAST HANDOFF` shows
  "autonomy at the boundary" — the level you left with is the level you wake to.
