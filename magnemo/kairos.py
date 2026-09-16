"""magnemo.kairos — KAIROS v1: deterministic salience at stage time.

The crown of the review path: it solves review-scaling: the founder's attention is
the scarcest resource in the loop, so the queue must present what matters
most, first. Every staged note gets a `salience` score computed the moment
it is staged — a weighted sum of four components, each in [0, 1]:

  consequence  the writer's DECLARED impact class
               (security > money > correctness > process > info)
  novelty      1 − max similarity vs existing canon in the same partition,
               where similarity = max(character-trigram Jaccard, tag Jaccard).
               Cheap, exact, offline — NO embeddings, NO model calls.
  operator     1.0 iff the note carries the founder-flag tag
               (`cli flag <id> --by NAME`). Highest single weight by
               configuration invariant: a flagged note beats any unflagged
               note. The operator is the signal.
  source       tiered by the note's `source` field: audit/postmortem work
               outranks routine runs (keyword tiers in config).

salience = Σ weight_i × component_i, weights from the vault config file
(`_config/magnemo.json`, see docs/CONFIG.md). Both the score and the
raw components are stored in note frontmatter — the ranking is auditable
from the file alone.

Deterministic by construction: same note + same canon + same config ⇒ same
score. Zero-LLM writes is house law; this module has no clock, no RNG, no
network, no model.
"""
from __future__ import annotations
import json, re
from .vault import Note

_norm_re = re.compile(r"[^a-z0-9 ]+")


def _normalize(text: str) -> str:
    return " ".join(_norm_re.sub(" ", text.lower()).split())


def trigrams(text: str) -> set:
    """Character trigrams of normalized text."""
    s = _normalize(text)
    if len(s) < 3:
        return {s} if s else set()
    return {s[i:i + 3] for i in range(len(s) - 2)}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    return inter / len(a | b)


def _tagset(note: Note) -> set:
    return {t.strip().lower() for t in note.tags.split(",") if t.strip()}


def consequence(note: Note, cfg: dict) -> float:
    k = cfg["kairos"]
    classes = k["impact_classes"]
    impact = (note.impact or "").strip().lower()
    if impact not in classes:
        impact = k["default_impact"]
    return float(classes[impact])


def novelty(note: Note, canon_notes: list, cfg: dict) -> float:
    """1 − max similarity against existing canon in the same partition.
    Empty canon ⇒ fully novel (1.0)."""
    mine = trigrams(note.title + " " + note.body)
    mytags = _tagset(note)
    max_sim = 0.0
    for c in canon_notes:
        if c.partition != note.partition:
            continue
        sim = _jaccard(mine, trigrams(c.title + " " + c.body))
        tsim = _jaccard(mytags, _tagset(c))
        sim = max(sim, tsim)
        if sim > max_sim:
            max_sim = sim
    return round(1.0 - max_sim, 4)


def operator_signal(note: Note, cfg: dict) -> float:
    tag = cfg["kairos"]["operator_tag"].strip().lower()
    return 1.0 if tag in _tagset(note) else 0.0


def source_weight(note: Note, cfg: dict) -> float:
    k = cfg["kairos"]
    src = (note.source or "").lower()
    best = 0.0
    hit = False
    for kw, w in k["source_classes"].items():
        if kw.lower() in src:
            hit = True
            if float(w) > best:
                best = float(w)
    return best if hit else float(k["default_source_weight"])


def score(note: Note, canon_notes: list, cfg: dict) -> tuple:
    """Returns (salience, components) — components is the raw dict, keys
    in fixed order so the serialized frontmatter is byte-stable."""
    comps = {
        "consequence": round(consequence(note, cfg), 4),
        "novelty": round(novelty(note, canon_notes, cfg), 4),
        "operator": round(operator_signal(note, cfg), 4),
        "source": round(source_weight(note, cfg), 4),
    }
    w = cfg["kairos"]["weights"]
    sal = sum(float(w[k]) * comps[k] for k in comps)
    return round(sal, 4), comps


def apply(note: Note, canon_notes: list, cfg: dict) -> Note:
    """Compute and store salience on the note (mutates + returns it)."""
    sal, comps = score(note, canon_notes, cfg)
    note.salience = sal
    note.salience_components = json.dumps(comps, sort_keys=True)
    return note


def sorted_queue(notes: list, batch: int | None = None) -> list:
    """Review-queue order: salience desc; unscored (salience < 0) last;
    id as the deterministic tiebreak. Optional batch cap."""
    ordered = sorted(notes, key=lambda n: (-n.salience, n.id))
    scored = [n for n in ordered if n.salience >= 0]
    unscored = sorted([n for n in ordered if n.salience < 0], key=lambda n: n.id)
    out = scored + unscored
    if batch is not None and batch > 0:
        out = out[:batch]
    return out
