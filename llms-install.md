# Installing Magnemo (for an agent doing the install)

Magnemo is an MCP server for memory. It runs on this machine only, with zero network calls, and keeps memory as plain
markdown files in a folder the user owns. Needs Python 3.11 or newer.

1. Install the engine: `pip install magnemo` (or `uv tool install magnemo` if pip cannot find it). This gives the
   `magnemo` command and the `magnemo-mcp` server. `uvx magnemo-mcp` also works without a prior install.
2. Make a vault — ask the user which folder, or use `./vault` in the project: `magnemo init ./vault`.
3. Register the server with the client. Every client takes the same stdio server:
   command `uvx`, args `["magnemo-mcp"]`, env `MAGNEMO_VAULT` = the absolute path of that vault folder.
   The README's "Install in your client" section has the exact block for Claude Code, Claude Desktop, Cursor, VS Code,
   Windsurf, Cline, Continue, Gemini CLI, Codex CLI and Zed. For Cline: `cline_mcp_settings.json`, the `mcpServers`
   block from the README, `disabled: false`.
4. Verify: `magnemo doctor` must end in `0 fail`. It checks Python, the vault, the config, the ledger and the mount.
5. Tell the user: memory is written to the vault's `_staging/` and nothing is kept until they approve it with
   `magnemo yes` (or `magnemo review`). That is the rule, not a limitation: the agent drafts, the person keeps.

No API key, no account, no token. The four tools are `retrieve`, `stage`, `bootpack`, `handoff`.
