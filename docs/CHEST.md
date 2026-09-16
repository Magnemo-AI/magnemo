# THE CHEST — `magnemo chest`

**Machines die, the memory doesn't.** A vault is a folder; folders live on disks;
disks die. The chest conducts copies of your vault to up to two places **you
own** — and restores a whole vault onto a new machine.

**The law, in code:** Magnemo *conducts* copies; it never *holds* them. There
is no hosted destination in this feature — the only kinds are `git` (a git
remote you own) and `path` (a folder you own). Nothing secret leaves the
machine. Canon is never overwritten by a copy.

## Two copies, three places
```bash
magnemo chest add git git@github.com:you/vault-copy.git --label laptop-git   # Copy B
magnemo chest add path /Volumes/Drawer/vault-copy --label drawer            # Copy C
magnemo chest push                                                          # first copy, now
magnemo chest status
```
`chest: A ✅ · B ✅ 12m · C ⏳ 3 files` — A is this vault; B and C are your copies.
A missing copy shows `—`: a vault with one copy is told it has one copy.
🔴 = the last push was **blocked by the secret sweep**. 🟠 = the last copy
**failed** (the chest retries on the next event).

## When copies happen (events, never thresholds)
Every **promote**, every resolved **receipt**, every **handoff**, every **10
staged notes**, and at most every **24 hours** (the ceiling). Edit
`_config/chest.json` to change the counts. The sweep cannot be turned off
there — only per push, by a human, on the record:
```bash
magnemo chest push --no-sweep --by "your name"    # writes CHEST_SWEEP_DISABLED to the ledger
```

## Nothing secret leaves the machine
Before every push, Sentinel sweeps the changed files for secret-shaped text
(cloud keys, tokens, private-key blocks, API-token assignments). **Any hit
blocks the push.** A note lands in your review queue naming the file and the
pattern — never the value — and the gauge goes red until a clean push. There
is no auto-redaction: moving a secret out of the vault is your call.

## Restore: the memory surviving
```bash
magnemo mount --from git@github.com:you/vault-copy.git ./vault   # into an EMPTY folder
```
Fetch → verify the ledger chain (a copy whose append-only ledger was edited
or truncated is **refused**, with the reason in plain English) → doctor →
the boot pack. The boot pack produced on the restored machine is
byte-identical to the last one produced on the source.

## Two machines drifted apart: the merge rite
Both copies changed since they last matched? The chest never overwrites
your canon. The other copy's canon changes arrive in **your review queue as
proposals** (provenance `chest:merge from <label>`); you promote or reject.
Ledgers from both sides are unioned in timestamp order with a `CHEST_MERGE`
marker. Taint travels with every note, in every direction.

## The ledger
`_ledger/chest.jsonl` — append-only and hash-chained: `CHEST_PUSH`,
`CHEST_FAIL`, `CHEST_BLOCKED`, `CHEST_MERGE`, `CHEST_SWEEP_DISABLED`.

## Not in v0 (on purpose)
- **No hosted destination of any kind.** Copies go where you own.
- **No encryption at rest.** Your remote is yours; **recommendation:** keep git
  copies in a *private* repository and path copies on an encrypted volume
  (FileVault, LUKS, BitLocker) — the vault is plain markdown by design.
- **No real-time sync.** Events + ceiling. Want faster? Set `on_staged_count` to 1.
- **No merge UI.** Proposals land in staging; `magnemo review` is the UI.
