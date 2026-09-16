# GATES — the Gate Map

A **gate** is a named door onto the vault or the repo. Each belongs to one
action class, has a keyholder, and is in exactly one state at any moment.
`magnemo gates` renders the map; every boot pack carries it under `## GATES`,
so a session never has to guess where the walls are.

```
magnemo gates [--as-of ISO] [--json]
```

## States

| state | meaning |
|---|---|
| `locked` | keyholders only (humans). Nothing computed and no grant opens it. |
| `open` | any actor may pass, inside the walls that govern the class — the scope wall for `read`, the partition wall and review queue for `stage`. |
| `delegated` | a keyholder has granted non-human actors a level in the gate's class. The map names them, their level, the grant id, and its scope. |

## The default map

| gate | class | configured | keyholder | note |
|---|---|---|---|---|
| `retrieve` | read | open | scope wall (`MAGNEMO_SCOPE`) | canon only; staged notes invisible until promoted |
| `staging` | stage | open | partition wall + review queue | the only write door; provenance mandatory; humans review after |
| `main` | merge-code | **computed** | The Founder | self-merge only at effective L2+ under an active grant; one log line per merge |
| `gate-code` | merge-code | locked | The Founder | *the gates do not merge changes to the gates* — `trust.py`, `grants.py`, `gates.py`, `governance.py`, `mcp.py`, `server.py`, `vault/_config/` |
| `canon` | promote-canon | locked | The Founder | promotion is never a tool · human-only forever |
| `publish` | publish | locked | The Founder | PyPI, npm, tags, releases, repo settings and renames · human-only forever |

Definitions live in config (`trust.gates`, the founder's file: name, class,
state, keyholder, note, paths). Two things config cannot do: open a human-only
gate (read back as `locked` whatever is written), or make a locked gate honour
a grant — a grant on `merge-code` delegates `main`, never `gate-code`.

## How state is derived

A gate configured `computed` reads as **delegated** while any *active* grant
(docs/GRANTS.md) covers its class for a non-human actor at `as_of`; otherwise
**locked**. Grants to declared humans are not delegations — humans already hold
the key. `locked` and `open` gates never change by computation; only a founder
config edit moves them.

`last change` is the latest issue / revoke / consume timestamp among grants
covering the class, or `genesis` when none exist. `grant history` lists every
grant covering the class with its state, so a locked gate still shows the
grants that were *tried* against it.

## In the boot pack

`## GATES` sits directly after the Charter (and the relationship layer, for
partner boots) and before the canon digest. It is rendered at **ledger time** —
the timestamp of the latest ledger entry — never the wall clock, so the pack
remains a pure function of vault bytes: same vault, same pack.

```
## GATES

The Gate Map at ledger time 2026-08-20T10:16:26Z. …
- **main** (merge-code): DELEGATED · keyholder The Founder
  - delegated to `claude-worker` at L2 under grant `G0001` — own PRs to main · assigned missions only (a standing order, recorded as a grant so the permission has a receipt)
  - self-merge only at effective L2+ under an active grant; one log line per merge
- **gate-code** (merge-code): LOCKED · keyholder The Founder
  - the gates do not merge changes to the gates
- **canon** (promote-canon): LOCKED · keyholder The Founder · human-only forever
```

A session reading this knows, before it reads a single memory: which doors are
open, which are its own by grant, and which will never be.
