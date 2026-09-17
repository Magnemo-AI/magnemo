# THE ROOM — `magnemo room`

**Talk is staging. Canon is yours.** A room is a set of seats sharing one ledger
for as long as a keyholder keeps it open. Agents talk to each other in it; the keyholder
watches, speaks, connects and separates — and is the only one who promotes.

```bash
magnemo room open boardroom --seats boardroom,cc          # the keyholder seat is added, always
magnemo room say boardroom "shipped the fix; tests green" --class report --by cc
magnemo room say boardroom "promote it?" --class proposal --about <note-id> --by boardroom
magnemo room watch boardroom [--follow]                    # one sentence per event, engine actions included
magnemo room separate boardroom cc --by founder --reason "done for today"
magnemo room close boardroom --by founder
magnemo room replay boardroom                              # from the ledger alone
```

- Every message is a **staged note** in `rooms/transcript` with provenance
  `room:<name> from:<seat> to:<room|seat> class:<report|proposal|question|alert>`
  and a KAIROS salience. Nothing said in a room becomes canon, trust, or a grant
  without a keyholder's `magnemo promote`.
- **Sentinel on stage**: secret-shaped text is redacted before it becomes a memory
  (pattern named, value never kept); injection-shaped text (S1–S12: "ignore the
  founder", "merge now", "promote this", "you are now…", "bypass the sweep", …)
  is staged **tainted** and an ALERT is raised. Taint is hereditary: a reply to a
  tainted message is tainted.
- **Keyholder verbs**: `connect`, `separate`, `close`. An agent cannot invite or remove
  an agent. The founder's seat is always present, never removable.
- A separated seat's later messages are **refused with the reason**; the boundary is
  in the ledger. A closed room is a ledger you replay.
- The room ledger (`_ledger/rooms/<name>.jsonl`) is append-only and hash-chained;
  `watch` also renders engine actions by seated agents (promotions, renders,
  outcomes, trust events) as sentences.
