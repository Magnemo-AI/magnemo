# THE GUARD — `magnemo guard`

**The agent can't delete what it was never allowed to write.** Sentinel guards the
gate (stage → canon) and the copy (chest push); the Guard puts the engine between
the hand and every file it can reach.

```bash
magnemo guard ./vault                 # raise the wall
magnemo guard --status ./vault
magnemo guard --off --by founder ./vault      # human verb, ledgered
magnemo restore claude/THE_DOCKET.md --versions
magnemo restore claude/THE_DOCKET.md --to 20260905T0812   # or a sha12 prefix; default latest
```

- **OS wall**: every canonical note file and every rendered file gets the
  immutable flag (macOS `chflags uchg`). A flagged file refuses overwrite and
  `rm -rf` even from its owner; directories stay unflagged so the engine can still
  add canon and renders. The engine unlocks a file only around its own supersession
  write and relocks it. On Linux the guard uses `chmod a-w`, which the owner can
  undo — said plainly in `doctor`.
- **work/**: agents get a writable `work/` beside the vault.
- **Body rules**: for Claude Code, the guard writes `permissions.deny` into the
  repo's `.claude/settings.json` — destructive shell patterns (`rm -rf`, `git push
  --force`, `git clean`, `chmod/chown/chflags`, `git reset --hard`) and any
  Edit/Write under the vault and the render root except `inbox/` and `work/`.
  The repo carries them; `doctor` reports them present.
- **Supersession everywhere**: every engine write to an existing render archives
  the prior bytes under `_index/archive/<relpath>/`; the ledger keeps the prior
  hash. A deleted render is re-rendered from canon by `doctor`. `restore` writes a
  version back through the guard and stages it as a founder note superseding the
  current canonical — canon stays human.
- A re-rendered file is reported by `doctor` as a note, not ledgered: canon didn't change, so a restored copy's boot pack stays byte-identical.
- **Straight**: the engine cannot see a shell's failed `rm` — the OS refusal and
  the body's deny rule are that record. If the folder is gone anyway,
  `magnemo mount --from <chest>` is the last line, boot pack byte-identical.

## Git on a guarded machine (read this once)
Git cannot replace an immutable file. On the machine where the guard is ON:
- never `git checkout` a **stale** `main` — it rewrites every unflagged file to the
  old tree while the flagged ones keep the new bytes (a half-old working tree);
- after merging your own branch: `git fetch origin && git checkout -B main origin/main`
  (identical trees → git writes nothing);
- to pull changes that touch guarded files, lower the wall first — `magnemo guard --off
  --by <human>` — pull, then raise it again. The ledger keeps both moves.
- A restored copy inherits the guard's state and relocks its files on its first
  `doctor` pass; a throwaway restore needs `chflags -R nouchg,nouappnd` before `rm`.
