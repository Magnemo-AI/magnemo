# The in-house bench

Magnemo alone, this release against the last. Numbers in the repo, method open. No competitor rows — run it yourself and tell us.

```bash
make bench            # or: python3 bench/run.py   (stdlib + the engine; ~25 s on a laptop)
```

- `bench/seed/facts.json` — the fixed dataset: 200 facts in 20 sessions, 40 decoys (never stored), 40 shadows (staged, never approved). `bench/seed/make_seed.py` regenerates it from its seed; the file is checked in so every release measures the same thing.
- `bench/run.py` — what it measures: recall (top-1, top-3) on a plain question after noise; hallucinated recall (a staged, never-approved entry coming back; answers offered for questions about facts never stored); the wake cost (the boot pack at 0 / 100 / 1,000 / 10,000 entries); latency p50/p95 for retrieve, stage and boot, cold and warm; provenance (entries with a signer; unsigned entries surfaced at recall, which must be 0).
- `bench/results/<version>.md` — one table per release, written by the run. Compare releases on the same machine only.
