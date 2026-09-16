"""magnemo.vault — Layer 1: the vault substrate.

Plain markdown notes with provenance frontmatter, arranged in the six-store
partitioned tree from the SVTech Orchestration Blueprint. Human-editable in any editor (the files are yours); machine-accessed
through this module only.

Zero dependencies. The frontmatter format is a strict, tiny YAML subset that
we fully control (key: value, one per line) so parsing is exact and safe.
"""
from __future__ import annotations
import os, re, json, sys, time, hashlib
from dataclasses import dataclass, field, asdict

# ---------------------------------------------------------------- structure
PARTITIONS = ("dev", "ops", "shared")
STORES = {
    "dev":    ("knowledge", "playbooks", "decisions", "debt"),
    "ops":    ("knowledge", "playbooks", "clients", "decisions", "style"),
    "shared": ("tickets", "changelog"),
}
SYSTEM_DIRS = ("_staging", "_index", "_ledger", "_config")

VALID_STATUS = ("staged", "canonical", "rejected", "archived")

FM_OPEN = "---"
FM_KEYS = ("id", "title", "author", "written", "source", "status",
           "reviewed_by", "reviewed_at", "supersedes", "partition", "store",
           "strength", "tags", "taint", "yield_w", "yield_l",
           "impact", "salience", "salience_components")

_slug_re = re.compile(r"[^a-z0-9]+")


def slugify(text: str, maxlen: int = 60) -> str:
    s = _slug_re.sub("-", text.lower()).strip("-")
    return s[:maxlen] or "note"


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------- note model
@dataclass
class Note:
    id: str
    title: str
    author: str            # agent name or "founder"
    written: str           # ISO timestamp
    source: str            # run id / gate id / "manual"
    status: str            # staged | canonical | rejected | archived
    partition: str         # dev | ops | shared
    store: str             # knowledge | playbooks | ...
    body: str = ""
    reviewed_by: str = ""
    reviewed_at: str = ""
    supersedes: str = ""   # id of the note this replaces, if any
    strength: float = 1.0  # retrieval-strength (Phase 2 dynamics; recorded now)
    tags: str = ""         # comma-separated
    taint: str = ""        # non-empty = untrusted lineage (source label); HEREDITARY
    yield_w: int = 0       # Telos: outcomes this note informed that were approved
    yield_l: int = 0       # Telos: outcomes this note informed that were denied/failed
    impact: str = "info"   # KAIROS: declared impact class (security|money|correctness|process|info)
    salience: float = -1.0  # KAIROS: computed at stage time; -1 = unscored (legacy)
    salience_components: str = ""  # KAIROS: JSON dict of raw components (auditable)
    extra: dict = field(default_factory=dict)  # unknown frontmatter keys, preserved verbatim on rewrite

    # -------- serialization: markdown w/ frontmatter --------
    def to_markdown(self) -> str:
        lines = [FM_OPEN]
        d = asdict(self)
        body = d.pop("body")
        extra = d.pop("extra") or {}
        for k in FM_KEYS:
            v = d.get(k, "")
            if isinstance(v, float):
                v = f"{v:.4f}"
            if isinstance(v, bool):
                v = str(v).lower()
            lines.append(f"{k}: {v}")
        for k in sorted(extra):  # unknown keys survive the roundtrip
            lines.append(f"{k}: {extra[k]}")
        lines.append(FM_OPEN)
        lines.append("")
        lines.append(f"# {self.title}")
        lines.append("")
        lines.append(body.rstrip() + "\n")
        return "\n".join(lines)

    @staticmethod
    def from_markdown(text: str) -> "Note":
        if not text.startswith(FM_OPEN):
            raise ValueError("note missing frontmatter")
        try:
            _, fm, rest = text.split(FM_OPEN, 2)
        except ValueError:
            raise ValueError("malformed frontmatter fence")
        meta: dict = {}
        for line in fm.strip().splitlines():
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
        body = rest.lstrip("\n")
        # strip the H1 title line if present (it's derived)
        if body.startswith("# "):
            body = body.split("\n", 1)[1] if "\n" in body else ""
        return Note(
            id=meta.get("id", ""),
            title=meta.get("title", ""),
            author=meta.get("author", "unknown"),
            written=meta.get("written", ""),
            source=meta.get("source", ""),
            status=meta.get("status", "staged"),
            partition=meta.get("partition", ""),
            store=meta.get("store", ""),
            reviewed_by=meta.get("reviewed_by", ""),
            reviewed_at=meta.get("reviewed_at", ""),
            supersedes=meta.get("supersedes", ""),
            strength=float(meta.get("strength", "1.0") or 1.0),
            tags=meta.get("tags", ""),
            taint=meta.get("taint", ""),
            yield_w=int(meta.get("yield_w", "0") or 0),
            yield_l=int(meta.get("yield_l", "0") or 0),
            impact=meta.get("impact", "info") or "info",
            salience=float(meta.get("salience", "-1.0") or -1.0),
            salience_components=meta.get("salience_components", ""),
            extra={k: v for k, v in meta.items() if k not in FM_KEYS},
            body=body.strip("\n"),
        )


# ---------------------------------------------------------------- the vault
class Vault:
    """Filesystem operations on a Magnemo vault. All paths validated; no
    traversal outside the vault root, ever."""

    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        self._shape = None

    # -------- the vault's shape: partitions and stores, declared by the vault --------
    @property
    def stores(self) -> dict:
        if self._shape is None:
            from .config import load_config
            pm = load_config(self.root).get("partitions") or {}
            self._shape = {p: tuple(s) for p, s in pm.items()} if pm else {p: tuple(s) for p, s in STORES.items()}
        return self._shape

    @property
    def partitions(self) -> tuple:
        return tuple(self.stores.keys())

    def scopes(self) -> dict:
        from .config import load_config
        return load_config(self.root).get("scopes") or {}

    def default_target(self, prefer: tuple = ("dev", "knowledge")) -> tuple:
        """Where engine-written notes land in THIS vault: the preferred
        partition/store if the vault declares it, else its first partition and
        that partition's first store. Engine writers never assume the trio."""
        p, s = prefer
        if p in self.partitions and s in self.stores[p]:
            return p, s
        p0 = self.partitions[0]
        return p0, self.stores[p0][0]

    def resolve_scope(self, names) -> tuple:
        """Comma list of partitions and/or scope aliases → tuple of partitions."""
        out = []
        for n in names:
            n = n.strip()
            if not n:
                continue
            if n in self.partitions:
                out.append(n)
            elif n in self.scopes():
                out.extend(p for p in self.scopes()[n] if p in self.partitions)
        return tuple(dict.fromkeys(out))

    # -------- lifecycle --------
    def init(self) -> None:
        for d in SYSTEM_DIRS:
            os.makedirs(os.path.join(self.root, d), exist_ok=True)
        from .config import ensure_config
        ensure_config(self.root)
        self._shape = None
        for p in self.partitions:
            for s in self.stores[p]:
                os.makedirs(os.path.join(self.root, p, s), exist_ok=True)
        readme = os.path.join(self.root, "README.md")
        if not os.path.exists(readme):
            with open(readme, "w") as f:
                f.write(VAULT_README)

    def exists(self) -> bool:
        return os.path.isdir(os.path.join(self.root, "_staging"))

    # -------- path discipline --------
    def _canonical_dir(self, partition: str, store: str) -> str:
        if partition not in self.partitions:
            raise ValueError(f"unknown partition: {partition} (this vault declares: {', '.join(self.partitions)})")
        if store not in self.stores[partition]:
            raise ValueError(f"store '{store}' not valid in partition '{partition}' (valid: {', '.join(self.stores[partition])})")
        return os.path.join(self.root, partition, store)

    def _staging_dir(self) -> str:
        return os.path.join(self.root, "_staging")

    def _safe(self, path: str) -> str:
        ap = os.path.abspath(path)
        if not ap.startswith(self.root + os.sep) and ap != self.root:
            raise PermissionError("path escapes vault root")
        return ap

    # -------- id --------
    def new_id(self, title: str) -> str:
        h = hashlib.sha1(f"{title}{time.time_ns()}".encode()).hexdigest()[:8]
        return f"{time.strftime('%Y%m%d')}-{slugify(title, 40)}-{h}"

    # -------- write (ALWAYS to staging) --------
    def stage(self, note: Note) -> str:
        """Agent-facing write. Notes land in _staging/ only. Promotion to a
        canonical store is a separate, human-gated act (governance.promote)."""
        self._canonical_dir(note.partition, note.store)  # validate target early
        note.status = "staged"
        path = self._safe(os.path.join(self._staging_dir(), f"{note.id}.md"))
        with open(path, "w") as f:
            f.write(note.to_markdown())
        return path

    # -------- read --------
    def read(self, note_id: str) -> Note:
        p = self.find(note_id)
        if p is None:
            raise FileNotFoundError(note_id)
        with open(p) as f:
            return Note.from_markdown(f.read())

    def find(self, note_id: str):
        """Locate a note by id. PRECEDENCE IS DELIBERATE: canonical stores are
        searched before _staging, so if a stale staging copy ever reappears
        (a VCS checkout restoring a consumed file — the 2026-08-20 ghost),
        canon wins and the result does not depend on directory walk order."""
        fname = f"{note_id}.md"
        for p in self.partitions:
            for st in self.stores[p]:
                cand = os.path.join(self.root, p, st, fname)
                if os.path.exists(cand):
                    return cand
        cand = os.path.join(self._staging_dir(), fname)
        if os.path.exists(cand):
            return cand
        return None

    def _canonical_ids(self) -> set:
        out = set()
        for p in self.partitions:
            for st in self.stores[p]:
                d = os.path.join(self.root, p, st)
                if os.path.isdir(d):
                    out.update(f[:-3] for f in os.listdir(d) if f.endswith(".md") and f != "README.md")
        return out

    def ghosts(self) -> list:
        """Ids present in _staging that ALSO exist in a canonical store. A
        ghost is never an active candidate; it is a stale copy to be removed
        by a human (or VCS). Reported, never silently deleted."""
        canon = self._canonical_ids()
        d = self._staging_dir()
        return sorted(f[:-3] for f in os.listdir(d) if f.endswith(".md") and f[:-3] in canon)

    # -------- listings --------
    def staged(self) -> list:
        """Notes in _staging. Ghosts (ids already canonical) are excluded —
        a promoted note can never re-enter the review queue, the boot pack's
        top-N, or rescore by way of a stale file. See ghosts()."""
        out = []
        d = self._staging_dir()
        canon = self._canonical_ids()
        for fname in sorted(os.listdir(d)):
            if fname.endswith(".md") and fname[:-3] not in canon:
                with open(os.path.join(d, fname)) as f:
                    try:
                        out.append(Note.from_markdown(f.read()))
                    except ValueError:
                        # a stray non-note file must never brick the queue or
                        # the MCP server boot; reported, never silently eaten
                        sys.stderr.write(f"[magnemo] _staging/{fname}: not a note (no frontmatter) — skipped\n")
        return out

    def canonical(self, partition: str | None = None) -> list:
        out = []
        parts = [partition] if partition else list(self.partitions)
        for p in parts:
            for s in self.stores.get(p, ()):
                d = os.path.join(self.root, p, s)
                if not os.path.isdir(d):
                    continue
                for fname in sorted(os.listdir(d)):
                    if fname.endswith(".md") and fname != "README.md":
                        with open(os.path.join(d, fname)) as f:
                            try:
                                n = Note.from_markdown(f.read())
                            except ValueError:
                                continue
                            if n.status == "canonical":
                                out.append(n)
        return out

    # -------- internal move used by governance --------
    def _place_canonical(self, note: Note) -> str:
        from . import guard
        d = self._canonical_dir(note.partition, note.store)
        path = self._safe(os.path.join(d, f"{note.id}.md"))
        with guard.writable(self.root, path), open(path, "w") as f:
            f.write(note.to_markdown())
        sp = os.path.join(self._staging_dir(), f"{note.id}.md")
        if os.path.exists(sp):
            os.remove(sp)
        return path


    def rewrite(self, note: Note) -> str:
        """Overwrite an existing note wherever it lives (yield/taint updates)."""
        p = self.find(note.id)
        if p is None:
            raise FileNotFoundError(note.id)
        p = self._safe(p)
        from . import guard
        with guard.writable(self.root, p), open(p, "w") as f:
            f.write(note.to_markdown())
        return p


VAULT_README = """# Magnemo Vault

This folder is a Magnemo memory vault — the canonical, human-owned memory of an
agentic operation, governed by the Magnemo Protocol.

- Everything is plain markdown. View it in any editor; you own the files.
- `dev/ ops/ shared/` are the partitions; folders inside are the stores.
- `_staging/` holds agent writes awaiting human review. Review with:
      python -m magnemo.cli review
- Never hand-edit `_index/` or `_ledger/` (machine-managed).
- Every note's frontmatter is its provenance. Provenance is the file format.
"""
