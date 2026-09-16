"""magnemo.search — Layer 2: retrieval (Phase 1 = lexical BM25, zero deps).

Canonical-only by default: agents retrieve reviewed truth, not staged claims.
The scoring hook multiplies by note strength, so Phase 2's reinforcement/decay
dynamics change ranking without touching this module's interface. The embedding
upgrade later replaces `score()` behind the same search() signature — designed
as a swap, not a rewrite.
"""
from __future__ import annotations
import math, re, os, json, time, hashlib
from collections import Counter
from .vault import Vault, Note

_tok = re.compile(r"[a-z0-9]{2,}")
K1, B = 1.5, 0.75  # standard BM25 params


def tokenize(text: str) -> list:
    return _tok.findall(text.lower())


class Index:
    def __init__(self, vault: Vault):
        self.vault = vault
        self._notes: list[Note] = []
        self._docs: list[list] = []
        self._df: Counter = Counter()
        self._avgdl: float = 0.0

    def rebuild(self, partition: str | None = None,
                include_staged: bool = False,
                partitions: tuple | None = None) -> int:
        """`partition` selects one partition; `partitions` (a set/tuple) walls the
        index to several — the MCP scope gate. None = vault-wide."""
        self._notes = self.vault.canonical(partition)
        if include_staged:
            self._notes += [n for n in self.vault.staged()
                            if partition is None or n.partition == partition]
        if partitions is not None:
            self._notes = [n for n in self._notes if n.partition in partitions]
        self._docs = [tokenize(n.title + " " + n.tags + " " + n.body)
                      for n in self._notes]
        self._df = Counter()
        for doc in self._docs:
            for t in set(doc):
                self._df[t] += 1
        self._avgdl = (sum(len(d) for d in self._docs) / len(self._docs)) \
            if self._docs else 0.0
        return len(self._notes)

    def _bm25(self, qtokens: list, i: int) -> float:
        doc = self._docs[i]
        if not doc:
            return 0.0
        dl = len(doc)
        tf = Counter(doc)
        N = len(self._docs)
        score = 0.0
        for t in qtokens:
            df = self._df.get(t, 0)
            if df == 0:
                continue
            idf = math.log(1 + (N - df + 0.5) / (df + 0.5))
            f = tf.get(t, 0)
            score += idf * (f * (K1 + 1)) / (f + K1 * (1 - B + B * dl / self._avgdl))
        return score

    def search(self, query: str, k: int = 5, partition: str | None = None,
               max_chars: int = 240, include_tainted: bool = True,
               agent: str = "agent", log_receipt: bool = True,
               partitions: tuple | None = None, log_cost: bool = True) -> dict:
        """Yield-aware, taint-aware, token-budgeted retrieval.

        Ranking = BM25 x strength x yield-ratio x taint-penalty.
        Telos yield: notes that historically informed APPROVED outcomes rank up;
        notes behind denials rank down — retrieval optimizes proven token ROI.
        Returns {"rid", "results", "payload_chars"}: the rid is the retrieval
        RECEIPT id — pass it to `magnemo outcome` when the action resolves, and
        every note in this result set earns credit or debit.
        """
        self.rebuild(partition, partitions=partitions)
        q = tokenize(query)
        scored = []
        for i, n in enumerate(self._notes):
            base = self._bm25(q, i)
            if base <= 0:
                continue
            yield_ratio = (1.0 + n.yield_w) / (1.0 + n.yield_l)   # Telos multiplier
            taint_pen = 0.4 if n.taint else 1.0                    # tainted sinks
            if n.taint and not include_tainted:
                continue
            scored.append((base * max(n.strength, 0.05) * yield_ratio * taint_pen, n))
        scored.sort(key=lambda x: -x[0])
        top = scored[:k]
        results = []
        chars = 0
        for sc, n in top:
            snip = n.body if len(n.body) <= max_chars else n.body[:max_chars] + "\u2026"
            chars += len(snip) + len(n.title)
            r = {"id": n.id, "title": n.title, "score": round(sc, 3),
                 "partition": n.partition, "store": n.store,
                 "yield": f"+{n.yield_w}/-{n.yield_l}", "snippet": snip}
            if n.taint:
                r["taint"] = n.taint
            results.append(r)
        rid = hashlib.sha1(f"{query}{time.time_ns()}".encode()).hexdigest()[:10]
        payload_bytes = len(json.dumps(results).encode("utf-8"))
        if log_receipt and results:
            self._receipt(rid, agent, query, [r["id"] for r in results], chars)
        if log_receipt and log_cost:
            # Foresight counters (#13): every payload served is measured.
            # (log_cost=False lets a caller that re-renders the payload — the
            # MCP budget/rendition step — log the bytes it actually serves.)
            from . import foresight
            foresight.log_cost(self.vault, "retrieval", payload_bytes,
                               {"rid": rid, "agent": agent, "k": k,
                                "results": len(results)})
        return {"rid": rid, "results": results, "payload_chars": chars,
                "payload_bytes": payload_bytes}

    def _receipt(self, rid, agent, query, note_ids, chars):
        d = os.path.join(self.vault.root, "_ledger")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "retrievals.jsonl"), "a") as f:
            f.write(json.dumps({"rid": rid, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                "agent": agent, "query": query, "note_ids": note_ids,
                                "payload_chars": chars}) + "\n")
