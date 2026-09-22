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
6. Then tell me the exact command to approve it. After I approve, run magnemo bootpack and tell me what you remember.
If anything fails, show me what went wrong and fix it if you can.
```

You'll know it worked — your AI will tell you who it is now.

**For builders.** Magnemo is an MCP server with four tools — `retrieve`, `stage`,
`bootpack`, `handoff` — and a CLI for your side: review, promote, reject.
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

## Install in your client
One server, said ten ways. Every block below is the same thing: `uvx magnemo-mcp` with `MAGNEMO_VAULT` pointing at
the folder your memory lives in (make one with `magnemo init ./vault`). Tested on this Mac where it says so;
the rest is from each client's own docs and marked untested — corrections welcome, open an issue.

**Claude Code** — tested.
```bash
claude mcp add magnemo -e MAGNEMO_VAULT=/absolute/path/to/vault -- uvx magnemo-mcp
```
(`claude mcp list` shows `magnemo … ✔ Connected`. Add `-s project` to write it into the repo's `.mcp.json` for your team.)

**Claude Desktop** — tested. Download the extension from the latest release —
[magnemo-0.6.4.post1.mcpb](https://github.com/Magnemo-AI/magnemo/releases/latest) — and open it; Claude Desktop asks for the
vault folder and does the rest. (The connectors directory listing follows once it is accepted.)

**Cursor** — untested here (not installed on this Mac); the link and the block follow Cursor's docs.
[![Add to Cursor](https://img.shields.io/badge/Cursor-Add_Magnemo-000000?style=flat-square)](cursor://anysphere.cursor-deeplink/mcp/install?name=magnemo&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJtYWduZW1vLW1jcCJdLCJlbnYiOnsiTUFHTkVNT19WQVVMVCI6Ii9hYnNvbHV0ZS9wYXRoL3RvL3ZhdWx0In19)
Or `~/.cursor/mcp.json` (or `.cursor/mcp.json` in the project):
```json
{
  "mcpServers": {
    "magnemo": {
      "command": "uvx",
      "args": ["magnemo-mcp"],
      "env": { "MAGNEMO_VAULT": "/absolute/path/to/vault" }
    }
  }
}
```

**VS Code / Copilot** — untested here; per VS Code's docs.
[![Install in VS Code](https://img.shields.io/badge/VS_Code-Install_Magnemo-0098FF?style=flat-square&logo=visualstudiocode&logoColor=white)](vscode:mcp/install?%7B%22name%22%3A%22magnemo%22%2C%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22magnemo-mcp%22%5D%2C%22env%22%3A%7B%22MAGNEMO_VAULT%22%3A%22%2Fabsolute%2Fpath%2Fto%2Fvault%22%7D%7D)
Or `.vscode/mcp.json` in the workspace:
```json
{
  "servers": {
    "magnemo": {
      "type": "stdio",
      "command": "uvx",
      "args": ["magnemo-mcp"],
      "env": { "MAGNEMO_VAULT": "/absolute/path/to/vault" }
    }
  }
}
```

**Windsurf** — untested; `~/.codeium/windsurf/mcp_config.json`:
```json
{
  "mcpServers": {
    "magnemo": {
      "command": "uvx",
      "args": ["magnemo-mcp"],
      "env": { "MAGNEMO_VAULT": "/absolute/path/to/vault" }
    }
  }
}
```

**Cline** — untested; Cline → MCP Servers → Configure → `cline_mcp_settings.json`:
```json
{
  "mcpServers": {
    "magnemo": {
      "command": "uvx",
      "args": ["magnemo-mcp"],
      "env": { "MAGNEMO_VAULT": "/absolute/path/to/vault" },
      "disabled": false
    }
  }
}
```

**Continue** — untested; `~/.continue/config.yaml` (or a file in `.continue/mcpServers/`):
```yaml
mcpServers:
  - name: magnemo
    command: uvx
    args: ["magnemo-mcp"]
    env:
      MAGNEMO_VAULT: /absolute/path/to/vault
```

**Gemini CLI** — untested; `~/.gemini/settings.json`:
```json
{
  "mcpServers": {
    "magnemo": {
      "command": "uvx",
      "args": ["magnemo-mcp"],
      "env": { "MAGNEMO_VAULT": "/absolute/path/to/vault" }
    }
  }
}
```

**Codex CLI** — untested; `~/.codex/config.toml`:
```toml
[mcp_servers.magnemo]
command = "uvx"
args = ["magnemo-mcp"]
env = { MAGNEMO_VAULT = "/absolute/path/to/vault" }
```

**Zed** — untested; `settings.json` → `context_servers`:
```json
{
  "context_servers": {
    "magnemo": {
      "source": "custom",
      "command": "uvx",
      "args": ["magnemo-mcp"],
      "env": { "MAGNEMO_VAULT": "/absolute/path/to/vault" }
    }
  }
}
```

**After the install**, the loop is the same everywhere: your agent writes to staging, you review.
```bash
magnemo yes             # promote the top of the queue (yes <id-fragment> · yes --all)
magnemo no <id> --reason "…"   # reject one — the reason is required; rejections teach
magnemo review          # the interactive queue, when you want to read first
magnemo doctor          # python, vault, config, ledger, and the mount — proves the zero-network line too
```
Anything that speaks MCP over stdio mounts the same way. The remote door (ChatGPT and hosted clients) is on its way in 0.7.0.

## Agents draft, people keep — the one rule
Agents get four MCP tools. Promotion is not one of them.

| Actor  | Door                | Can do |
|--------|---------------------|--------|
| Agents | MCP server (stdio)  | `retrieve` canonical memory · `stage` → **staging only, the one write tool** · `bootpack` on wake · `handoff` at the boundary |
| You    | CLI + git (any editor)| review the queue · **promote / reject** · edit anything · own everything |

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

## Privacy
Magnemo runs on your machine and nowhere else. The vault is a folder of plain markdown
files you own and can read in any editor. The engine makes zero network calls — `magnemo
doctor` proves it on every run — so nothing you or your agent writes leaves the computer.
There is no telemetry, no account, no phone-home; the only copies of your memory are the
ones you make yourself (`magnemo chest`), to places you own. The full page:
https://magnemo.ai/privacy

## Guarantees (Phase 1 — Governed Recall)
- Agent writes NEVER reach canonical stores directly — staging only, always.
- Search returns canonical (keyholder-approved) notes only. Staged claims are invisible.
- Partition walls enforced per agent (`MAGNEMO_PARTITIONS`); cross-partition = DENIED.
- Supersession is explicit: old notes archive with a forward link. Nothing deletes.
- Rejections are kept and recorded — rejections teach.
- Every promote/reject lands in the append-only Trust Ledger with actor + reason.

## Tests
```bash
python -m unittest discover -s tests -v     # incl. full MCP round-trips (legacy + four-verb)
# or: pip install -e ".[test]" && pytest
```

## Everything that shipped
Release by release, with the design notes that used to live here: [CHANGELOG.md](CHANGELOG.md).

— Silver Valley Technologies Inc. · Phase 1 of 3 · The memory that learns is
the memory that is governed.

---
`mcp-name: ai.magnemo/magnemo` · [Source](https://github.com/Magnemo-AI/magnemo) · [Security](SECURITY.md) · [Privacy](https://magnemo.ai/privacy)
