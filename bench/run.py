#!/usr/bin/env python3
"""The in-house bench (P-67): Magnemo alone, this release against the last. Stdlib + the engine. Numbers in the repo,
method open. Run: `make bench` (or `python3 bench/run.py`). Writes bench/results/<version>.md — one table.

What it measures
  recall      200 seeded facts across 20 sessions; after N turns of noise, how many come back on a plain question (top-1, top-3).
              Hallucinated recalls counted separately: a fact that was staged but never approved (a shadow) coming back for its own
              question, or an answer for a question about a fact that was never stored (a decoy).
  wake cost   the boot pack's size at 0 / 100 / 1,000 / 10,000 entries (chars, and the engine's own token estimate: chars/4).
  latency     p50 / p95 for retrieve, stage ("remember"), and boot — cold (a fresh index or a fresh vault read) and warm.
  provenance  % of canonical entries with a signer and ran_by; unsigned entries surfaced at recall (must be 0).

The dataset is bench/seed/facts.json, fixed and versioned; bench/seed/make_seed.py regenerates it from its seed."""
import json, os, shutil, statistics, sys, tempfile, time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import magnemo                                                   # noqa: E402
from magnemo.vault import Vault, Note                            # noqa: E402
from magnemo.governance import Governance                        # noqa: E402
from magnemo.search import Index                                 # noqa: E402
from magnemo import bootpack                                     # noqa: E402

NOISE_TURNS = 20                                                 # noise entries promoted after each session's facts
WAKE_SIZES = (0, 100, 1000, 10000)
REVIEWER = "bench-keyholder"


def pct(xs, p):
    xs = sorted(xs)
    if not xs:
        return 0.0
    k = min(len(xs) - 1, max(0, int(round((p / 100.0) * (len(xs) - 1)))))
    return xs[k]


def ms(seconds):
    return "%.1f ms" % (seconds * 1000.0)


def fresh_vault(where):
    v = Vault(where)
    v.init()
    return v


def stage(g, title, body, source, session):
    return g.agent_write(title=title, body=body, partition="dev", store="knowledge", author="bench-agent",
                         source=source, tags="bench,session-%d" % session)


def run_recall(seed, tmp):
    """Facts staged and approved session by session, noise between; shadows staged and never approved; then the questions."""
    v = fresh_vault(os.path.join(tmp, "recall"))
    g = Governance(v)
    stage_times, promoted = [], {}
    facts_by_session = {}
    for f in seed["facts"]:
        facts_by_session.setdefault(f["session"], []).append(f)
    noise = seed["noise"]
    shadows = {}
    for s in sorted(facts_by_session):
        for f in facts_by_session[s]:
            t0 = time.perf_counter()
            n = stage(g, f["subject"] + " — " + f["question"][:40], f["body"], "bench-session-%d" % s, s)
            stage_times.append(time.perf_counter() - t0)
            g.promote(n.id, REVIEWER, "bench", ran_by="bench")
            promoted[f["id"]] = n.id
        for k in range(NOISE_TURNS):
            n = stage(g, "noise %d/%d" % (s, k), noise[k % len(noise)] + " (turn %d)" % k, "bench-noise-%d" % s, s)
            g.promote(n.id, REVIEWER, "bench", ran_by="bench")
        for sh in seed["shadows"]:
            if (int(sh["id"][1:]) - 1) % 20 == s - 1:
                n = stage(g, sh["subject"] + " fallback", sh["body"], "bench-shadow-%d" % s, s)
                shadows[sh["id"]] = n.id                         # staged, never approved: invisible by law
    idx = Index(v)
    cold = []
    t0 = time.perf_counter(); idx.search("warm up the index", k=3, log_receipt=False, log_cost=False); cold.append(time.perf_counter() - t0)
    top1 = top3 = 0
    surfaced_unsigned = 0
    search_times = []
    for f in seed["facts"]:
        t0 = time.perf_counter()
        r = idx.search(f["question"], k=3, log_receipt=False, log_cost=False)
        search_times.append(time.perf_counter() - t0)
        ids = [x["id"] for x in r["results"]]
        for i in ids:
            n = v.read(i)
            if n.status != "canonical" or not n.reviewed_by:
                surfaced_unsigned += 1
        if ids and ids[0] == promoted[f["id"]]:
            top1 += 1
        if promoted[f["id"]] in ids:
            top3 += 1
    shadow_hits = 0
    for sh in seed["shadows"]:
        r = idx.search(sh["question"], k=3, log_receipt=False, log_cost=False)
        if shadows[sh["id"]] in [x["id"] for x in r["results"]]:
            shadow_hits += 1
    decoy_answers = 0
    for d in seed["decoys"]:
        r = idx.search(d["question"], k=1, log_receipt=False, log_cost=False)
        if r["results"]:
            decoy_answers += 1
    # cold vs warm retrieve: a fresh Index object, first query
    cold_search = []
    for q in [f["question"] for f in seed["facts"][:10]]:
        i2 = Index(v)
        t0 = time.perf_counter(); i2.search(q, k=3, log_receipt=False, log_cost=False); cold_search.append(time.perf_counter() - t0)
    # provenance over canon
    canon = list(v.canonical())
    signed = sum(1 for n in canon if n.reviewed_by)
    return {"facts": len(seed["facts"]), "top1": top1, "top3": top3, "shadow_hits": shadow_hits, "decoy_answers": decoy_answers,
            "decoys": len(seed["decoys"]), "shadows": len(seed["shadows"]), "surfaced_unsigned": surfaced_unsigned,
            "stage_p50": pct(stage_times, 50), "stage_p95": pct(stage_times, 95),
            "search_warm_p50": pct(search_times, 50), "search_warm_p95": pct(search_times, 95),
            "search_cold_p50": pct(cold_search, 50), "search_cold_p95": pct(cold_search, 95),
            "canon": len(canon), "signed": signed, "vault": v}


def run_wake(seed, tmp):
    """The boot pack's size and time at 0 / 100 / 1,000 / 10,000 canonical entries."""
    out = []
    v = fresh_vault(os.path.join(tmp, "wake"))
    g = Governance(v)
    have = 0
    bodies = [f["body"] for f in seed["facts"]] + seed["noise"]
    for target in WAKE_SIZES:
        while have < target:
            # the wake test measures the boot pack, not the review path: entries land the way promote lands them
            # (canonical, signed) without the salience pass, the render and the ledger lines — 10,000 of those is an hour
            n = Note(id=v.new_id("entry %d" % have), title="entry %d" % have, author="bench-agent",
                     written=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), source="bench-wake", status="canonical",
                     partition="dev", store="knowledge", body=bodies[have % len(bodies)] + " (#%d)" % have,
                     reviewed_by=REVIEWER, reviewed_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), tags="bench")
            v._place_canonical(n)
            have += 1
        cold, warm = [], []
        for i in range(3):
            t0 = time.perf_counter(); pack = bootpack.generate(v, "worker"); dt = time.perf_counter() - t0
            (cold if i == 0 else warm).append(dt)
        out.append({"entries": target, "chars": len(pack), "tokens": len(pack) // 4, "cold": cold[0], "warm_p50": pct(warm, 50)})
    return out


def main():
    seed = json.load(open(os.path.join(HERE, "seed", "facts.json")))
    tmp = tempfile.mkdtemp(prefix="magnemo-bench-")
    try:
        t_all = time.perf_counter()
        rc = run_recall(seed, tmp)
        wk = run_wake(seed, tmp)
        total = time.perf_counter() - t_all
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    ver = magnemo.__version__
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    canon_pct = (100.0 * rc["signed"] / rc["canon"]) if rc["canon"] else 0.0
    lines = ["# Bench · magnemo %s · %s" % (ver, when),
             "",
             "Seed `bench/seed/facts.json` v%d (seed %d) · %d facts in %d sessions · %d noise turns a session · %d decoys · %d shadows · Python %s · %s"
             % (seed["version"], seed["seed"], rc["facts"], 20, NOISE_TURNS, rc["decoys"], rc["shadows"], sys.version.split()[0], sys.platform),
             "",
             "| measure | value |", "|---|---|",
             "| recall top-1 | %d / %d (%.1f%%) |" % (rc["top1"], rc["facts"], 100.0 * rc["top1"] / rc["facts"]),
             "| recall top-3 | %d / %d (%.1f%%) |" % (rc["top3"], rc["facts"], 100.0 * rc["top3"] / rc["facts"]),
             "| hallucinated recall — a staged, never-approved entry returned for its own question | %d / %d |" % (rc["shadow_hits"], rc["shadows"]),
             "| answers offered for questions about facts never stored (decoys; BM25 returns its best match — the reader decides) | %d / %d |" % (rc["decoy_answers"], rc["decoys"]),
             "| unsigned entries surfaced at recall | %d |" % rc["surfaced_unsigned"],
             "| provenance: canonical entries with a signer | %d / %d (%.1f%%) |" % (rc["signed"], rc["canon"], canon_pct),
             "| retrieve, warm p50 / p95 | %s / %s |" % (ms(rc["search_warm_p50"]), ms(rc["search_warm_p95"])),
             "| retrieve, cold (fresh index) p50 / p95 | %s / %s |" % (ms(rc["search_cold_p50"]), ms(rc["search_cold_p95"])),
             "| stage (\"remember\") p50 / p95 | %s / %s |" % (ms(rc["stage_p50"]), ms(rc["stage_p95"])),
             ] + ["| wake cost at %s entries: boot pack | %s chars · ~%s tokens · cold %s · warm %s |"
                  % ("{:,}".format(w["entries"]), "{:,}".format(w["chars"]), "{:,}".format(w["tokens"]), ms(w["cold"]), ms(w["warm_p50"])) for w in wk] + [
             "| the whole bench | %.1f s |" % total,
             "",
             "Method: `bench/run.py`. Each fact is staged by an agent seat and approved by a keyholder (`ran_by` bench); shadows are staged and never",
             "approved; decoys are never stored. Recall is `Index.search(question, k=3)` on the whole vault. Tokens are the engine's own estimate (chars/4).",
             "Latency is this machine, this run; compare releases on the same machine only."]
    out = os.path.join(HERE, "results", "%s.md" % ver)
    with open(out, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("\nwrote", os.path.relpath(out, ROOT))


if __name__ == "__main__":
    main()
