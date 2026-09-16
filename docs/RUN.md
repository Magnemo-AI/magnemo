# THE SUBSCRIPTION SOCKET — `magnemo run`

Run your agents on the plan you already pay for. The **sanctioned door** is the
Claude Agent SDK, which signs in through your own Claude Code login. Magnemo never
reads, stores, or forwards a token; no API key of ours exists here.

```bash
pip install 'magnemo[claude]'                               # the optional extra
magnemo run "read the boot pack and stage a one-line status" --engine claude
magnemo run "..." --cap-turns 8 --cap-usd 0.50              # caps exit with the reason, never silently
magnemo run "..." --schedule "0 9 * * 1"                    # RAIL.md row + launchd/cron job (v0: a number or * per field)
magnemo run --card                                          # runs this month · tokens · API list-price avoided
```

- The session has the vault mounted through the four verbs (`retrieve`, `stage`,
  `bootpack`, `handoff`) plus read-only file tools; permission mode denies anything
  else without prompting. Every engine action is **staged** by agent `run-<id>`
  with provenance; a run never promotes.
- **FUEL line**: tokens in/out, turns, seconds, the SDK's list-price cost, and the
  plan window the CLI reports (`five_hour` / `seven_day`, status
  `allowed` / `allowed_warning` / `rejected`, utilization, reset time).
- **Caps**: `--cap-turns`, `--cap-usd`, and the plan's own limit — a run stopped by
  any of them prints the reason and ledgers it (`_ledger/runs.jsonl`).
- **Schedule**: `RAIL.md` gets a plain-speech row (trigger · agent · task · cap ·
  approval grain); macOS gets a `~/Library/LaunchAgents/com.magnemo.run.*` job,
  Linux a crontab line, both calling this same command with `--trigger schedule`.
  Remove with `--unschedule <label>`.
- **Engines**: `claude` is live; `codex` and `gemini` are documented stubs that
  refuse with "not wired yet" — the socket is engine-agnostic by construction.
- **Policy receipt**: Anthropic's help center allows Claude plans with the Agent
  SDK and headless Claude Code; pasting a subscription OAuth token into another
  harness is a Consumer-Terms violation. This module does the former and
  structurally cannot do the latter. Re-verify the policy page at each release.
