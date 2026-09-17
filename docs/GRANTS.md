# GRANTS — permission as data (P-02 B2)

A **grant** is how a keyholder permits an actor to operate at a level in one or
more action classes. It is a structured, append-only ledger record — not a
paragraph in a chat, not a memory file. Standing orders and one-time grants are
the same record with a different `kind`. Revocation is a second record naming
the first. Nothing is edited; the history is the audit.

```
magnemo grant  <grantee> --classes merge-code[,stage] --level 2 --by KEYHOLDER
               [--scope TXT] [--condition TXT]… [--kind standing|one-time]
               [--ref P-01] [--expires ISO] [--reason TXT] [--when ISO]
magnemo revoke <grant-id> --by KEYHOLDER --reason TXT
magnemo grants [--actor A] [--as-of ISO] [--json]
```

`grant` and `revoke` are **keyholder-only**: `--by` must be a name in
`trust.humans`. Anyone else is refused before anything touches disk.

## The record

```json
{"ts": "2026-08-20T00:00:00Z", "action_class": "trust.grant", "verdict": "issued",
 "actor": "The Founder", "subject": "claude-worker", "detail": "Standing Order P-01 …",
 "grant": {"grant_id": "G0001", "grantee": "claude-worker", "classes": ["merge-code"],
           "level": 2, "kind": "standing", "ref": "P-01",
           "scope": "your-org/your-repo · own PRs to main · assigned missions only",
           "conditions": ["…", "…"], "expires": "", "grantor": "The Founder",
           "issued": "2026-08-20T00:00:00Z"},
 "recorded_at": "2026-08-22T05:45:41Z"}
```

| field | meaning |
|---|---|
| `grant_id` | `G0001`, `G0002`, … in issue order |
| `classes` / `level` | what is permitted, and how far (L0–L4, see docs/TRUST.md) |
| `scope` | free text: where this applies (a repo, a mission, a partition) |
| `conditions` | the terms, one line each — what the grantee must keep true |
| `kind` | `standing` (stays active until revoked/expired) or `one-time` (consumed by the first trust event that cites it with `--grant G…`) |
| `ref` | the order it encodes (`P-01`), a PR, a ticket |
| `expires` | optional ISO timestamp |
| `recorded_at` | present when `--when` backdated a known historical grant |

## How a grant takes effect

```
effective_level = min( computed_level , granted_level )
granted_level   = max( class default_grant , levels of ACTIVE grants covering the class )
```

A grant is **active** at a moment when it was issued at or before it, has not
expired, has not been revoked, and (if one-time) has not been consumed.
`magnemo grants` shows every grant with its state: `active · revoked ·
expired · consumed · pending`.

Permission is not trust. A grant raises the ceiling an actor *may* reach; the
ledger record decides whether they *have*. Granted L2 with an empty record is
still L1. Earned L3 with no grant is still the class default. A `violation`
freezes the class at L0 regardless of any grant.

## What no grant can do

- Lift a non-keyholder above **L1 in `promote-canon` or `publish`** — refused at
  issue time, and clamped again at compute time so a hand-edited ledger line
  cannot smuggle a key (there is a test that forges one).
- Lift anyone who is not a declared keyholder to **L4 KEYHOLDER**.

## The genesis grant

P-01 (Standing Order, boardroom, 2026-08-20) is `G0001` in this repo's vault:
`claude-worker` → L2 SUPERVISED in `merge-code`, standing, five conditions, ref
`P-01`, grantor The Founder. It was recorded after the fact with `--when`, so
the line carries both the order's date and the real `recorded_at`. The prose
version in memory is now a mirror; the ledger line is the law.
