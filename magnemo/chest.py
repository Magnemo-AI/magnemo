"""magnemo.chest — THE CHEST: "machines die, the memory doesn't."

THE LAW, IN CODE: Magnemo CONDUCTS copies of a vault; it never HOLDS them.
There is no hosted destination in this module — KINDS is the whole universe
("git" = a git remote the user owns · "path" = a folder the user owns), and a
destination of any other kind is refused by construction. Nothing secret
leaves the machine: every push is swept by Sentinel first, and a hit BLOCKS
the push (no auto-redaction — that is a person's judgment). Canon is never
overwritten by a copy: what another copy changed in canon arrives HERE as a
proposal in _staging, and a keyholder promotes it.

Copies are conducted on EVENTS (promote, receipt, handoff, N staged notes)
and a ceiling clock — never on percentage thresholds (#112).

Files this module owns inside the vault:
  _config/chest.json           the plain-text chest config (C1)
  _ledger/chest.jsonl          append-only, hash-chained chest ledger (C3)
  _index/chest/<label>.git     git bookkeeping for a git destination (never copied)
  _index/chest/<label>.manifest.json   what that destination last received
  _index/chest/state.json      staged-note counter for the N trigger
"""
from __future__ import annotations
import os, re, json, hashlib, shutil, subprocess, datetime

# ---------------------------------------------------------------- THE LAW
KINDS = ("git", "path")          # the whole universe of destinations. No hosted kind exists.
MAX_DESTINATIONS = 2
SWEEP = "sentinel"               # not a setting — a constant
CONFIG_FILE = "chest.json"
LEDGER_REL = "_ledger/chest.jsonl"
STATE_REL = "_index/chest"
MANIFEST_NAME = "CHEST_MANIFEST.json"
DEFAULTS = {
    "destinations": [],
    "triggers": {"on_promote": True, "on_receipt": True, "on_handoff": True,
                 "on_staged_count": 10, "ceiling_hours": 24},
    "sweep": SWEEP,
}


class ChestError(Exception):
    """Every message is written for a stranger (#121): plain English, no jargon alone."""


# ---------------------------------------------------------------- clock (mockable for the ceiling drill)
def _now() -> datetime.datetime:
    env = os.environ.get("MAGNEMO_CHEST_NOW", "").strip()
    if env:
        return datetime.datetime.strptime(env, "%Y-%m-%dT%H:%M:%SZ")
    return datetime.datetime.utcnow().replace(microsecond=0)


def _now_iso() -> str:
    return _now().strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- config (C1)
def _cfg_path(root: str) -> str:
    return os.path.join(root, "_config", CONFIG_FILE)


def load(root: str) -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))
    p = _cfg_path(root)
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            user = json.load(f)
        for k, v in user.items():
            if k == "triggers" and isinstance(v, dict):
                cfg["triggers"].update(v)
            elif k != "sweep":
                cfg[k] = v
    cfg["sweep"] = SWEEP  # the sweep cannot be disabled from config. Only per push, at the prompt, ledgered.
    dests = cfg.get("destinations") or []
    if len(dests) > MAX_DESTINATIONS:
        raise ChestError(f"chest.json lists {len(dests)} destinations; the chest conducts at most {MAX_DESTINATIONS} "
                         "(Copy B and Copy C). Remove one.")
    for d in dests:
        if d.get("kind") not in KINDS:
            raise ChestError(f"chest.json destination '{d.get('label', '?')}' has kind '{d.get('kind')}'. "
                             "The chest only conducts copies to places you own: a git remote (kind \"git\") "
                             "or a folder (kind \"path\"). There is no hosted kind.")
    cfg["destinations"] = dests
    return cfg


def save(root: str, cfg: dict) -> None:
    os.makedirs(os.path.dirname(_cfg_path(root)), exist_ok=True)
    out = {"destinations": cfg["destinations"], "triggers": cfg["triggers"], "sweep": SWEEP}
    from . import guard
    with guard.writable(root, _cfg_path(root)), open(_cfg_path(root), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
        f.write("\n")


def add_destination(root: str, kind: str, target: str, label: str = "", branch: str = "main") -> dict:
    if kind not in KINDS:
        raise ChestError("The chest only conducts copies to places you own: a git remote (\"git\") or a folder (\"path\"). "
                         f"'{kind}' is not one of them — there is no hosted kind, by law.")
    cfg = load(root)
    if len(cfg["destinations"]) >= MAX_DESTINATIONS:
        raise ChestError("Both copy slots (B and C) are taken. The chest conducts at most two copies; "
                         "remove one in _config/chest.json to add another.")
    if kind == "path":
        target = os.path.abspath(target)
        if os.path.abspath(target).startswith(os.path.abspath(root) + os.sep):
            raise ChestError("A copy inside the vault itself is not a copy. Choose a folder outside the vault "
                             "(an external drive, a synced folder, a second machine).")
    label = label or _default_label(kind, target)
    if any(d["label"] == label for d in cfg["destinations"]):
        raise ChestError(f"A destination labelled '{label}' already exists. Pick another --label.")
    d = {"kind": kind, "target": target, "label": label, "added": _now_iso()}
    if kind == "git":
        d["branch"] = branch or "main"
    cfg["destinations"].append(d)
    save(root, cfg)
    return d


def _default_label(kind: str, target: str) -> str:
    base = target.rstrip("/").split("/")[-1]
    if base.endswith(".git"):
        base = base[:-4]
    return base or kind


# ---------------------------------------------------------------- the vault as files
_SKIP_DIRS = {".git", "__pycache__"}


def _iter_files(root: str):
    root = os.path.abspath(root)
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root).replace(os.sep, "/")
        if rel_dir == ".":
            rel_dir = ""
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS
                             and not (rel_dir == "_index" and d == "chest"))
        for fn in sorted(filenames):
            if fn == ".DS_Store":
                continue
            yield (rel_dir + "/" + fn) if rel_dir else fn


def _sha_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


# Machine-managed telemetry TRAVELS with every copy but is not "memory pending":
# a boot pack write or a retrieval receipt must not make the vault read as
# behind its own copies after every wake. (The chest's own ledger likewise.)
_NOISE_FILES = {LEDGER_REL, "_ledger/costs.jsonl", "_ledger/retrievals.jsonl"}
_NOISE_PREFIXES = ("_index/",)


def _is_noise(rel: str) -> bool:
    return rel in _NOISE_FILES or rel.startswith(_NOISE_PREFIXES)


def travel_files(root: str) -> list:
    """Everything that is conducted to a copy."""
    return list(_iter_files(root))


def snapshot(root: str) -> dict:
    """rel path → sha256 of the MEMORY-bearing files: what pending counts, what the
    tree hash covers, what the sweep must clear before a copy is conducted."""
    return {rel: _sha_file(os.path.join(root, rel)) for rel in _iter_files(root) if not _is_noise(rel)}


def tree_hash(snap: dict) -> str:
    h = hashlib.sha256()
    for rel in sorted(snap):
        h.update(f"{rel}\0{snap[rel]}\n".encode())
    return h.hexdigest()


def _state_dir(root: str) -> str:
    d = os.path.join(root, STATE_REL)
    os.makedirs(d, exist_ok=True)
    return d


def _manifest_path(root: str, label: str) -> str:
    return os.path.join(_state_dir(root), f"{label}.manifest.json")


def _load_manifest(root: str, label: str) -> dict:
    p = _manifest_path(root, label)
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_manifest(root: str, label: str, snap: dict) -> None:
    with open(_manifest_path(root, label), "w", encoding="utf-8") as f:
        json.dump(snap, f, indent=0, sort_keys=True)


def delta(root: str, label: str, snap: dict | None = None) -> tuple:
    snap = snap if snap is not None else snapshot(root)
    man = _load_manifest(root, label)
    changed = [p for p in sorted(snap) if man.get(p) != snap[p]]
    deleted = [p for p in sorted(man) if p not in snap]
    return changed, deleted


def _load_state(root: str) -> dict:
    p = os.path.join(_state_dir(root), "state.json")
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {"staged_since_push": 0}


def _save_state(root: str, st: dict) -> None:
    with open(os.path.join(_state_dir(root), "state.json"), "w", encoding="utf-8") as f:
        json.dump(st, f)


# ---------------------------------------------------------------- Sentinel sweep (C3.1)
PATTERNS = [
    ("aws-access-key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("github-token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}")),
    ("pypi-token", re.compile(r"pypi-[A-Za-z0-9_-]{20,}")),
    ("openai-key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("slack-token", re.compile(r"xox[abpr]-[A-Za-z0-9-]{20,}")),
    ("google-api-key", re.compile(r"AIza[0-9A-Za-z_-]{35}")),
    ("private-key-block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY")),
    ("api-token-assignment", re.compile(r"(?i)\b(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret)\s*[:=]\s*['\"]?[A-Za-z0-9_\-/+=]{16,}")),
]


def sweep(root: str, rels) -> list:
    """Returns [(rel, pattern_name)] — the NAME of the pattern, never the value."""
    hits = []
    for rel in rels:
        p = os.path.join(root, rel)
        if not os.path.isfile(p):
            continue
        try:
            with open(p, "rb") as f:
                text = f.read().decode("utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable: nothing to match as text
        for name, rx in PATTERNS:
            if rx.search(text):
                hits.append((rel, name))
    return hits


# ---------------------------------------------------------------- the ledger (C3.3): append-only, hash-chained
def _ledger_path(root: str) -> str:
    return os.path.join(root, LEDGER_REL)


def _read_ledger_lines(root: str) -> list:
    p = _ledger_path(root)
    if not os.path.isfile(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [l.rstrip("\n") for l in f if l.strip()]


def _line_hash(line: str) -> str:
    return hashlib.sha256(line.encode("utf-8")).hexdigest()


def entries(root: str) -> list:
    out = []
    for line in _read_ledger_lines(root):
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            out.append({"kind": "UNPARSEABLE", "raw": line})
    return out


def _append(root: str, entry: dict) -> dict:
    lines = _read_ledger_lines(root)
    entry = dict(entry)
    entry.setdefault("ts", _now_iso())
    entry["prev"] = _line_hash(lines[-1]) if lines else "genesis"
    os.makedirs(os.path.dirname(_ledger_path(root)), exist_ok=True)
    line = json.dumps(entry, sort_keys=True)
    with open(_ledger_path(root), "a", encoding="utf-8") as f:
        f.write(line + "\n")
    entry["_hash"] = _line_hash(line)
    return entry


def verify_chain(root: str) -> tuple:
    """Append-only continuity: every entry's `prev` must be the hash of an entry
    that came before it (the merge rite unions two chains, so the shape is a
    DAG, like git — not a single line). Returns (ok, plain-English reason)."""
    seen = {"genesis"}
    lines = _read_ledger_lines(root)
    for i, line in enumerate(lines, 1):
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            return False, (f"the chest ledger (_ledger/chest.jsonl) has an unreadable line {i}. "
                           "A copy with a damaged ledger is refused, so a broken record can never pose as the real one.")
        for key in ("prev", "prev2"):
            if key in e and e[key] not in seen:
                return False, (f"the chest ledger (_ledger/chest.jsonl) breaks at line {i}: it claims to follow a record "
                               "that isn't there. The chain is append-only, so this copy was edited or truncated after "
                               "it was written. Restore from a copy whose ledger is intact.")
        seen.add(_line_hash(line))
    return True, "ledger chain intact"


# ---------------------------------------------------------------- git plumbing (a git remote the user owns)
def _gitdir(root: str, label: str) -> str:
    return os.path.join(_state_dir(root), f"{label}.git")


def _git(root: str, gitdir: str, *args, check: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run(["git", "--git-dir", gitdir, "--work-tree", os.path.abspath(root), *args],
                       capture_output=True, text=True)
    if check and r.returncode != 0:
        raise ChestError(_plain_git_error(r.stderr))
    return r


def _plain_git_error(stderr: str) -> str:
    s = (stderr or "").strip()
    low = s.lower()
    if "could not read from remote" in low or "could not resolve host" in low or "unable to access" in low:
        return ("the git remote (the place your copy lives) could not be reached — network or address problem. "
                "Your work is not affected; the chest will try again on the next event.")
    if "authentication" in low or "permission denied" in low or "403" in low:
        return ("the git remote (the place your copy lives) refused the login. Fix the credentials for that remote; "
                "your work is not affected and the chest will try again on the next event.")
    if "does not appear to be a git repository" in low or "not found" in low:
        return "the git remote (the place your copy lives) does not exist at that address. Check the URL with `magnemo chest status`."
    return "git reported: " + (s.splitlines()[-1] if s else "an unknown error")


def _ensure_git(root: str, dest: dict) -> str:
    gd = _gitdir(root, dest["label"])
    if not os.path.isdir(gd):
        os.makedirs(os.path.dirname(gd), exist_ok=True)
        subprocess.run(["git", "init", "-q", "--bare", gd], check=True, capture_output=True)
        _git(root, gd, "config", "core.bare", "false")
        _git(root, gd, "config", "core.worktree", os.path.abspath(root))
        _git(root, gd, "config", "user.name", "magnemo chest")
        _git(root, gd, "config", "user.email", "chest@magnemo.local")
        _git(root, gd, "symbolic-ref", "HEAD", f"refs/heads/{dest.get('branch', 'main')}")
        with open(os.path.join(gd, "info", "exclude"), "a", encoding="utf-8") as f:
            f.write("_index/chest/\n.git/\n.DS_Store\n")
    r = _git(root, gd, "remote", "get-url", "chest", check=False)
    if r.returncode != 0:
        _git(root, gd, "remote", "add", "chest", dest["target"])
    elif r.stdout.strip() != dest["target"]:
        _git(root, gd, "remote", "set-url", "chest", dest["target"])
    return gd


def _git_push(root: str, dest: dict, trigger: str, nfiles: int) -> None:
    gd = _ensure_git(root, dest)
    branch = dest.get("branch", "main")
    _git(root, gd, "add", "-A")
    _git(root, gd, "commit", "-q", "--allow-empty", "-m", f"chest: {trigger} · {nfiles} files")
    r = _git(root, gd, "push", "-q", "chest", f"HEAD:refs/heads/{branch}", check=False)
    if r.returncode != 0:
        low = (r.stderr or "").lower()
        if "rejected" in low or "fetch first" in low or "non-fast-forward" in low or "failed to push" in low:
            _reconcile(root, dest, gd)
            _git(root, gd, "push", "-q", "chest", f"HEAD:refs/heads/{branch}")
        else:
            raise ChestError(_plain_git_error(r.stderr))


# ---------------------------------------------------------------- the merge rite (C5)
_EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def _canon_rel(rel: str, root: str | None = None) -> bool:
    parts = rel.split("/")
    from .vault import Vault, PARTITIONS
    P = Vault(root).partitions if root else PARTITIONS
    return len(parts) == 3 and parts[0] in P and parts[2].endswith(".md") and parts[2] != "README.md"


def _union_ledger(local_lines: list, remote_lines: list) -> list:
    seen, out = set(), []
    for line in local_lines + remote_lines:
        if line in seen:
            continue
        seen.add(line)
        out.append(line)

    def ts(line):
        try:
            return json.loads(line).get("ts", "")
        except json.JSONDecodeError:
            return ""
    out.sort(key=ts)  # stable: equal timestamps keep local-then-remote order
    return out


def _reconcile(root: str, dest: dict, gd: str) -> dict:
    """Both copies changed since they last matched. Canon here is never overwritten:
    the other copy's canon changes become PROPOSALS in _staging with provenance
    `chest:merge from <label>`; ledgers are unioned in timestamp order with a
    CHEST_MERGE marker; taint carries. Then one merge commit, two parents."""
    from .vault import Vault, Note
    label = dest["label"]
    branch = dest.get("branch", "main")
    _git(root, gd, "fetch", "-q", "chest", branch)
    base_r = _git(root, gd, "merge-base", "HEAD", "FETCH_HEAD", check=False)
    base = base_r.stdout.strip() if base_r.returncode == 0 else _EMPTY_TREE
    remote_files = _git(root, gd, "ls-tree", "-r", "--name-only", "FETCH_HEAD").stdout.split()
    v = Vault(root)
    canon_ids = v._canonical_ids()
    proposals, unioned, kept = [], [], []
    for rel in remote_files:
        rblob = _git(root, gd, "rev-parse", f"FETCH_HEAD:{rel}").stdout.strip()
        bb = _git(root, gd, "rev-parse", f"{base}:{rel}", check=False)
        bblob = bb.stdout.strip() if bb.returncode == 0 else None
        if rblob == bblob:
            continue  # the other copy didn't change this file
        local_path = os.path.join(root, rel)
        content = _git(root, gd, "show", f"FETCH_HEAD:{rel}").stdout
        if rel.startswith("_ledger/") and rel.endswith(".jsonl"):
            local_lines = []
            if os.path.isfile(local_path):
                with open(local_path, encoding="utf-8") as f:
                    local_lines = [l.rstrip("\n") for l in f if l.strip()]
            merged = _union_ledger(local_lines, [l for l in content.splitlines() if l.strip()])
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            from . import guard as _guard
            with _guard.writable(root, local_path), open(local_path, "w", encoding="utf-8") as f:
                f.write("\n".join(merged) + ("\n" if merged else ""))
            unioned.append(rel)
        elif rel.startswith("_staging/") and rel.endswith(".md"):
            nid = rel.split("/")[-1][:-3]
            if not os.path.exists(local_path) and nid not in canon_ids:
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                with open(local_path, "w", encoding="utf-8") as f:
                    f.write(content)
                proposals.append(nid)
        elif _canon_rel(rel, root):
            try:
                foreign = Note.from_markdown(content)
            except ValueError:
                kept.append(rel)
                continue
            local_exists = os.path.exists(local_path)
            new_id = f"{foreign.id}-merge-{rblob[:8]}"
            if v.find(new_id) is None:
                prop = Note(id=new_id, title=f"MERGE PROPOSAL: {foreign.title}", author=foreign.author,
                            written=_now_iso(), source=f"chest:merge from {label}", status="staged",
                            partition=foreign.partition, store=foreign.store,
                            body=(foreign.body + f"\n\n> Proposed by the chest from copy '{label}': that copy holds a "
                                  f"{'different' if local_exists else 'new'} canonical version of this note. "
                                  "Promote to accept it here; reject to keep what you have. Nothing was overwritten."),
                            supersedes=(foreign.id if local_exists else ""), tags=foreign.tags,
                            taint=foreign.taint, impact=foreign.impact)
                v.stage(prop)
                proposals.append(new_id)
        else:
            kept.append(rel)  # config, index, README: the person at this keyboard rules
    remote_chest = [l for l in _git(root, gd, "show", f"FETCH_HEAD:{LEDGER_REL}", check=False).stdout.splitlines() if l.strip()]
    marker = {"kind": "CHEST_MERGE", "destination": label, "proposals": len(proposals),
              "ledgers_unioned": unioned, "kept_local": len(kept)}
    if remote_chest:
        marker["prev2"] = _line_hash(remote_chest[-1])
    _append(root, marker)
    _git(root, gd, "add", "-A")
    tree = _git(root, gd, "write-tree").stdout.strip()
    head = _git(root, gd, "rev-parse", "HEAD").stdout.strip()
    fetched = _git(root, gd, "rev-parse", "FETCH_HEAD").stdout.strip()
    commit = _git(root, gd, "commit-tree", tree, "-p", head, "-p", fetched,
                  "-m", f"chest: merge from {label} · {len(proposals)} proposals").stdout.strip()
    _git(root, gd, "update-ref", "HEAD", commit)
    return {"proposals": proposals, "unioned": unioned, "kept": kept}


# ---------------------------------------------------------------- path destination: a folder the user owns
def _path_push(root: str, dest: dict, snap: dict, thash: str) -> None:
    target = dest["target"]
    os.makedirs(target, exist_ok=True)
    travel = {rel: snap.get(rel) or _sha_file(os.path.join(root, rel)) for rel in travel_files(root)}
    for rel in travel:
        dst = os.path.join(target, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(os.path.join(root, rel), dst)
    # mirror: what left the vault leaves the copy (the manifest itself stays)
    for dirpath, dirnames, filenames in os.walk(target):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            rel = os.path.relpath(os.path.join(dirpath, fn), target).replace(os.sep, "/")
            if rel != MANIFEST_NAME and rel not in travel:
                os.remove(os.path.join(dirpath, fn))
    manifest = {"vault_hash": thash, "written": _now_iso(),
                "files": [{"path": rel, "size": os.path.getsize(os.path.join(root, rel)), "sha256": travel[rel]}
                          for rel in sorted(travel)]}
    with open(os.path.join(target, MANIFEST_NAME), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1)


# ---------------------------------------------------------------- THE PUSH (C3)
_busy = False


def push(root: str, label: str | None = None, trigger: str = "manual", by: str = "", no_sweep: bool = False) -> list:
    cfg = load(root)
    dests = [d for d in cfg["destinations"] if label is None or d["label"] == label]
    if label is not None and not dests:
        raise ChestError(f"No destination labelled '{label}'. See `magnemo chest status`.")
    if not dests:
        raise ChestError("No copies registered yet. Add one: `magnemo chest add git <url>` or `magnemo chest add path <dir>`.")
    results = [_push_one(root, d, trigger, not no_sweep, by) for d in dests]
    st = _load_state(root)
    st["staged_since_push"] = 0
    _save_state(root, st)
    return results


def _quarantine(root: str) -> list:
    from .config import load_config
    ib = (load_config(root).get("inbox") or {}).get("dir", "")
    if not ib:
        return []
    q = os.path.normpath(os.path.join(root, ib, "blocked"))
    return sorted(os.listdir(q)) if os.path.isdir(q) else []


def _push_one(root: str, dest: dict, trigger: str, sweep_on: bool, by: str) -> dict:
    label = dest["label"]
    held = _quarantine(root) if sweep_on else []
    if held:
        last = [e for e in entries(root) if e.get("destination") == label]
        if not last or last[-1].get("kind") != "CHEST_BLOCKED":
            _append(root, {"kind": "CHEST_BLOCKED", "destination": label, "trigger": trigger,
                           "hits": [{"file": f"inbox/blocked/{f}", "pattern": "held at the door"} for f in held]})
        return {"destination": label, "status": "blocked", "hits": [(f, "quarantine") for f in held],
                "message": (f"PUSH BLOCKED — {len(held)} drop(s) are held in the inbox's blocked/ folder because they "
                            "contain secret-shaped text. Move the secret out and delete them; then push again. "
                            "Nothing left the machine.")}
    snap = snapshot(root)
    changed, deleted = delta(root, label, snap)
    nfiles = len(changed) + len(deleted)
    if sweep_on:
        hits = sweep(root, changed + [f for f in travel_files(root) if _is_noise(f) and f != LEDGER_REL])
        if hits:
            _stage_sentinel_note(root, label, hits)
            _append(root, {"kind": "CHEST_BLOCKED", "destination": label, "trigger": trigger,
                           "hits": [{"file": rel, "pattern": name} for rel, name in hits]})
            return {"destination": label, "status": "blocked", "hits": hits,
                    "message": (f"PUSH BLOCKED — a secret-shaped string was found in {hits[0][0]} "
                                f"(pattern: {hits[0][1]}). Nothing left the machine. A Sentinel note in your review "
                                "queue names the file and the pattern; fix the file, then push again.")}
    else:
        _append(root, {"kind": "CHEST_SWEEP_DISABLED", "destination": label, "trigger": trigger, "by": by or "human"})
    thash = tree_hash(snap)
    _append(root, {"kind": "CHEST_PUSH", "destination": label, "trigger": trigger, "files": nfiles,
                   "sweep": "clean" if sweep_on else "disabled", "hash": thash})
    try:
        if dest["kind"] == "git":
            _git_push(root, dest, trigger, nfiles)
        else:
            _path_push(root, dest, snap, thash)
    except Exception as e:  # noqa: BLE001 — a copy failing must never block the agent's own work
        reason = str(e) if isinstance(e, ChestError) else f"{type(e).__name__}: {e}"
        _append(root, {"kind": "CHEST_FAIL", "destination": label, "trigger": trigger, "reason": reason})
        return {"destination": label, "status": "failed", "message":
                f"Copy to '{label}' failed: {reason} Your work is not affected; the chest will try again on the next event."}
    _save_manifest(root, label, snap)
    return {"destination": label, "status": "ok", "files": nfiles, "hash": thash,
            "message": f"Copy '{label}' is current — {nfiles} files conducted (trigger: {trigger}, sweep: clean)."}


def _stage_sentinel_note(root: str, label: str, hits: list) -> None:
    from .vault import Vault, Note
    v = Vault(root)
    lines = "\n".join(f"- `{rel}` — pattern: **{name}**" for rel, name in hits)
    nid = f"{_now().strftime('%Y%m%d')}-sentinel-push-blocked-{hashlib.sha256(json.dumps(hits).encode()).hexdigest()[:8]}"
    if v.find(nid) is not None:
        return
    v.stage(Note(id=nid, title=f"Sentinel: push to '{label}' blocked — secret-shaped text in {hits[0][0]}",
                 author="sentinel", written=_now_iso(), source="chest:sentinel", status="staged",
                 partition=v.default_target(("shared", "tickets"))[0], store=v.default_target(("shared", "tickets"))[1], impact="security",
                 body=(f"The chest refused to copy the vault to '{label}' because the files below contain text "
                       "shaped like a secret. Nothing left the machine. The value itself is deliberately NOT recorded here.\n\n"
                       f"{lines}\n\nFix the file (move the secret out of the vault), then run `magnemo chest push`.")))


# ---------------------------------------------------------------- events (C2) + the ceiling (TICK)
def notify(vault_or_root, event: str) -> None:
    """Engine event points call this. It never raises and never blocks the caller."""
    global _busy
    if _busy:
        return
    root = getattr(vault_or_root, "root", vault_or_root)
    try:
        _busy = True
        cfg = load(root)
        if not cfg["destinations"]:
            return
        tr = cfg["triggers"]
        trigger = None
        if event == "promote" and tr.get("on_promote", True):
            trigger = "promote"
        elif event == "receipt" and tr.get("on_receipt", True):
            trigger = "receipt"
        elif event == "handoff" and tr.get("on_handoff", True):
            trigger = "handoff"
        elif event == "stage":
            st = _load_state(root)
            st["staged_since_push"] = int(st.get("staged_since_push", 0)) + 1
            _save_state(root, st)
            if st["staged_since_push"] >= int(tr.get("on_staged_count", 10)):
                trigger = "staged_count"
        if trigger:
            push(root, trigger=trigger)
        else:
            tick(root)
    except Exception:  # noqa: BLE001 — the chest must never block the agent's own work
        pass
    finally:
        _busy = False


def last_push_ts(root: str, label: str | None = None) -> str | None:
    out = None
    for e in entries(root):
        if e.get("kind") == "CHEST_PUSH" and (label is None or e.get("destination") == label):
            out = e.get("ts")
    return out


def tick(root: str) -> list:
    """The ceiling clock: if no copy has been conducted within ceiling_hours, push now."""
    cfg = load(root)
    if not cfg["destinations"]:
        return []
    hours = float(cfg["triggers"].get("ceiling_hours", 24))
    marks = [last_push_ts(root)] + [d.get("added") for d in cfg["destinations"]]
    marks = [m for m in marks if m]
    if marks:
        newest = max(marks)
        age = _now() - datetime.datetime.strptime(newest, "%Y-%m-%dT%H:%M:%SZ")
        if age < datetime.timedelta(hours=hours):
            return []
    return push(root, trigger="ceiling")


# ---------------------------------------------------------------- THE GAUGE (C6)
def _age(ts: str) -> str:
    then = datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
    s = int((_now() - then).total_seconds())
    if s < 0:
        s = 0
    if s < 3600:
        return f"{s // 60}m"
    if s < 86400:
        return f"{s // 3600}h"
    return f"{s // 86400}d"


def gauge(root: str, absolute: bool = False) -> str:
    """One line: `chest: A ✅ · B ✅ 12m · C ⏳ 3 files`. A = this vault; B/C = the copies.
    A missing copy shows `—`, never hidden. `absolute=True` prints the last push
    time instead of an age — the boot pack must be byte-identical across machines."""
    try:
        cfg = load(root)
    except ChestError:
        cfg = dict(DEFAULTS)
    ok, _ = verify_chain(root)
    parts = [f"A {'✅' if ok else '⚠ ledger'}"]
    dests = cfg.get("destinations", [])
    ev = entries(root)
    for i, slot in enumerate(("B", "C")):
        if i >= len(dests):
            parts.append(f"{slot} —")
            continue
        d = dests[i]
        mine = [e for e in ev if e.get("destination") == d["label"] and e.get("kind") in ("CHEST_PUSH", "CHEST_FAIL", "CHEST_BLOCKED")]
        last = mine[-1] if mine else None
        if last and last["kind"] == "CHEST_BLOCKED":
            parts.append(f"{slot} 🔴 blocked")
            continue
        if last and last["kind"] == "CHEST_FAIL":
            parts.append(f"{slot} 🟠 failed")
            continue
        changed, deleted = delta(root, d["label"])
        pending = len(changed) + len(deleted)
        if pending:
            parts.append(f"{slot} ⏳ {pending} files")
        elif last:
            parts.append(f"{slot} ✅ {last['ts'] if absolute else _age(last['ts'])}")
        else:
            parts.append(f"{slot} ⏳ never")
    return "chest: " + " · ".join(parts)


def status_lines(root: str) -> list:
    cfg = load(root)
    L = [gauge(root)]
    if not cfg["destinations"]:
        L.append("  no copies yet — this vault exists in ONE place. Add a copy: `magnemo chest add git <url>` or `magnemo chest add path <dir>`")
    for i, d in enumerate(cfg["destinations"]):
        slot = "BC"[i]
        where = d["target"] + (f" (branch {d.get('branch', 'main')})" if d["kind"] == "git" else "")
        lp = last_push_ts(root, d["label"])
        L.append(f"  {slot} · {d['label']} · {d['kind']} → {where}")
        L.append(f"      last copy: {lp or 'never'} · sweep: sentinel (on every push)")
    ok, why = verify_chain(root)
    L.append(f"  ledger: {why}")
    return L


# ---------------------------------------------------------------- THE RESTORE (C4)
def restore(src: str, vault_root: str) -> dict:
    """`magnemo mount --from <git-url | path>`: fetch the copy into an empty folder,
    verify the ledger chain (refuse a broken one), run doctor, emit the boot pack."""
    from . import doctor as _doctor, bootpack as _bootpack
    from .vault import Vault
    vault_root = os.path.abspath(vault_root)
    if os.path.isdir(vault_root) and os.listdir(vault_root):
        raise ChestError(f"'{vault_root}' already has files in it. A restore only writes into an empty folder, "
                         "so it can never overwrite memory you already have. Pick an empty folder, or point --from at a copy "
                         "and let the chest reconverge through your review queue instead.")
    os.makedirs(vault_root, exist_ok=True)
    kind = "path" if (os.path.isdir(src) and os.path.isfile(os.path.join(src, MANIFEST_NAME))) else "git"
    tmp_git = None
    try:
        if kind == "path":
            for dirpath, dirnames, filenames in os.walk(src):
                dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
                for fn in filenames:
                    rel = os.path.relpath(os.path.join(dirpath, fn), src).replace(os.sep, "/")
                    if rel == MANIFEST_NAME:
                        continue
                    dst = os.path.join(vault_root, rel)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(os.path.join(dirpath, fn), dst)
        else:
            tmp_git = os.path.join(_state_dir(vault_root), "_restore.git")
            r = subprocess.run(["git", "clone", "-q", "--bare", src, tmp_git], capture_output=True, text=True)
            if r.returncode != 0:
                raise ChestError("could not fetch the copy: " + _plain_git_error(r.stderr))
            _git(vault_root, tmp_git, "config", "core.bare", "false")
            _git(vault_root, tmp_git, "config", "core.worktree", vault_root)
            _git(vault_root, tmp_git, "config", "user.name", "magnemo chest")
            _git(vault_root, tmp_git, "config", "user.email", "chest@magnemo.local")
            _git(vault_root, tmp_git, "checkout", "-q", "-f", "HEAD", "--", ".")
        if not os.path.isfile(os.path.join(vault_root, "_config", "magnemo.json")):
            raise ChestError("The copy at that address is not a Magnemo vault (no _config/magnemo.json). Nothing was restored.")
        ok, why = verify_chain(vault_root)
        if not ok:
            raise ChestError("Restore refused: " + why)
        v = Vault(vault_root)
        v.init()   # a copy carries files, never empty folders: rebuild the skeleton (idempotent, clobbers nothing)
        cfg = load(vault_root)
        match = next((d for d in cfg["destinations"] if d["kind"] == kind and
                      (d["target"] == src or os.path.abspath(d["target"]) == os.path.abspath(src))), None)
        if match is None:
            match = add_destination(vault_root, kind, src, label=_default_label(kind, src) + "-restored",
                                    branch=(cfg["destinations"][0].get("branch", "main") if cfg["destinations"] else "main"))
        if kind == "git":
            final = _gitdir(vault_root, match["label"])
            if os.path.isdir(final):
                shutil.rmtree(final)
            shutil.move(tmp_git, final)
            tmp_git = None
            with open(os.path.join(final, "info", "exclude"), "a", encoding="utf-8") as f:
                f.write("_index/chest/\n.git/\n.DS_Store\n")
            r = _git(vault_root, final, "remote", "get-url", "chest", check=False)
            if r.returncode != 0:
                _git(vault_root, final, "remote", "add", "chest", src)
        snap = snapshot(vault_root)
        _save_manifest(vault_root, match["label"], snap)
        # The ledger that travelled records what EVERY copy received. Any destination
        # whose last conducted hash equals this tree is current here too — so the
        # gauge on the restored machine tells the same truth the source told.
        here = tree_hash(snap)
        for d in load(vault_root)["destinations"]:
            if d["label"] == match["label"]:
                continue
            last = [e for e in entries(vault_root) if e.get("kind") == "CHEST_PUSH" and e.get("destination") == d["label"]]
            if last and last[-1].get("hash") == here:
                _save_manifest(vault_root, d["label"], snap)
        results = _doctor.run(vault_root, [])
        doctor_ok = not any(x["level"] == _doctor.FAIL for x in results)
        pack_path, _nbytes = _bootpack.write(v)
        with open(pack_path, "rb") as f:
            pack_sha = hashlib.sha256(f.read()).hexdigest()
        return {"kind": kind, "vault": vault_root, "destination": match["label"], "doctor": results,
                "doctor_ok": doctor_ok, "bootpack": pack_path, "bootpack_sha256": pack_sha, "ledger": why}
    except Exception:
        # nothing half-restored is left behind
        if tmp_git and os.path.isdir(tmp_git):
            shutil.rmtree(tmp_git, ignore_errors=True)
        for name in os.listdir(vault_root):
            p = os.path.join(vault_root, name)
            shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.remove(p)
        raise
