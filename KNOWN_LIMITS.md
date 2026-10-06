# KNOWN LIMITS — open beta (0.6.x)

Honesty is the product. These are the current edges, stated plainly. Every one
of them is a roadmap item, not a surprise left for you to find.

- **The yes is not checked yet.** Promotion is not an MCP tool, and that is
  the wall today. `magnemo yes` itself takes no credential: anything that can
  run a command in your shell, your agent included if you gave it one, can
  promote a note, and the ledger records the name it was given, or the first
  keyholder's name when none is given. A keyholder
  check on the CLI is the next engine work.
- **Beta software.** The engine runs its maker's company daily, but you are
  early. Expect rough edges in exactly the places this file names.
- **One client is tested.** Claude Code. Every other client's block in the
  README is written from that client's own docs and marked untested.
  `magnemo mount` writes `.mcp.json`, the file Claude Code reads; other
  clients take their config by hand.
- **Local and single-machine.** The vault is plain markdown on one disk.
  Multi-machine continuity works the way git works — you sync the vault
  yourself (git is the tested path). There is no hosted sync service.
- **Keyword retrieval, not embeddings.** Search is walled BM25 over your
  vault. It is fast, deterministic, and auditable — and it will miss
  paraphrases that a semantic index would catch. The `Index.search()` seam
  exists so embedding retrieval can swap in behind the same wall later.
- **The review queue is a terminal.** `magnemo review` is a CLI. There is no
  web or app interface yet; viewers are windows, not foundations, and the
  markdown is readable in any editor today.
- **Trust math is young.** Autonomy levels are computed from a real
  append-only ledger, but the weights, half-lives, and thresholds are v1 and
  will be tuned. `promote-canon` and `publish` are hard-capped keyholder-only in
  code — that part is doctrine, not a tunable.
- **MCP over stdio only.** The server speaks stdio to local MCP clients
  (Claude Code, Claude Desktop, anything that speaks MCP). No HTTP/SSE
  transport yet.
- **Token counts are estimates.** Payload cost telemetry estimates tokens as
  bytes/4 (documented in the code). The seam accepts a real tokenizer later;
  the trend lines are honest, the absolute numbers are approximate.
- **Vault format may evolve before 1.0.** Notes are plain markdown with
  frontmatter, so your data is never trapped — but tooling-level migrations
  between beta versions may be needed. Breaking changes will be listed in the
  CHANGELOG with migration notes.
- **Python 3.11+ required.** Zero runtime dependencies, standard library
  only. Primary development and dogfood happen on macOS/Linux; Windows path
  handling is untested territory this release.

Found an edge not on this list? That is exactly the kind of receipt wanted here —
the beta channel at [magnemo.ai](https://magnemo.ai).
