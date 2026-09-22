# Security

## Reporting
If you find a security problem in Magnemo, write to **hello@magnemo.ai** with what you found, how to reproduce
it, and what you think it lets someone do. Please do not open a public issue for it first.

You will get an acknowledgement within **72 hours**, and a plain answer on what we will do and when. We will
credit you in the release notes if you want that.

## In scope
- The engine (`magnemo/`): the CLI, the vault format, the ledgers, the guard, the chest.
- The MCP server (`magnemo-mcp`): the four tools and the walls around them (staging only, partitions, scope).
- The vault format itself: anything that lets an agent write past staging, alter the ledger, or launder taint.

## Out of scope
- Bugs in the agents or clients that talk to the server (Claude Code, Cursor, Windsurf, Claude Desktop).
- Anything that needs the keyholder's own hand to go wrong (`magnemo yes` on a bad note is a review problem, not a hole).

## What we promise about the software
Zero network calls, zero telemetry, plain files you own — `magnemo doctor` checks the first on every run. If you
can show the engine sending anything anywhere, that is the most serious report we can get.

There is no bounty yet. There is a thank-you, a fix, and your name on it if you want it.
