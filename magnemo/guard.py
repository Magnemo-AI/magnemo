"""magnemo.guard — THE GUARD (P-34, #147): the engine between the hand and EVERY file.

"The agent can't delete what it was never allowed to write."

`magnemo guard <vault>` makes the memory physically owner-immutable at the OS
level: every canonical note file and every rendered file gets the immutable flag
(macOS `chflags uchg`; on Linux `chmod a-w`, which is advisory for the owner —
said plainly). Directories stay unflagged so the engine can still ADD canon and
renders; a flagged file refuses overwrite and `rm -rf` even from its owner. The
engine unlocks a file only around its own supersession writes and relocks it.

Beside the vault, agents get a writable `work/` directory. For the body (Claude
Code) the guard writes deny rules into the repo's `.claude/settings.json`:
destructive shell patterns, and any Edit/Write under the vault and the render
root except `inbox/` and `work/`. `guard --off` reverses everything, ledgered,
and is a keyholder verb.

Supersession everywhere: every engine write to an existing render path archives
the prior bytes under `_index/archive/<relpath>/<ts>-<sha12>` (the ledger keeps
the prior hash); a deleted render is re-rendered from canon by `doctor`;
`magnemo restore <path|id> [--to <version>]` brings a version back in one command.
"""
from __future__ import annotations
import os, sys, json, hashlib, subprocess, stat, contextlib
from .vault import Vault, now_iso

STATE_REL = "_index/guard.json"
ARCHIVE_REL = "_index/archive"
DENY_SHELL = ["Bash(rm -rf:*)", "Bash(rm -r:*)", "Bash(rm -fr:*)", "Bash(git push --force:*)", "Bash(git push -f:*)",
              "Bash(git clean:*)", "Bash(chmod:*)", "Bash(chown:*)", "Bash(chflags:*)", "Bash(git reset --hard:*)"]


class GuardError(Exception):
    pass


def _state_path(root): return os.path.join(root, STATE_REL)


def state(root: str) -> dict:
    p = _state_path(root)
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {"active": False}


def active(root: str) -> bool:
    return bool(state(root).get("active"))


def _render_root(v: Vault):
    from .config import load_config
    rr = (load_config(v.root).get("render") or {}).get("root", "")
    return os.path.normpath(os.path.join(v.root, rr)) if rr else None


def guarded_files(v: Vault) -> list:
    """Files the guard flags: canonical note files, and rendered files that exist
    for canonical notes (plus everything under a rendered receipts/ tree)."""
    out = []
    for p in v.partitions:
        for s in v.stores[p]:
            d = os.path.join(v.root, p, s)
            if os.path.isdir(d):
                out += [os.path.join(d, f) for f in os.listdir(d) if f.endswith(".md")]
    cfgdir = os.path.join(v.root, "_config")
    if os.path.isdir(cfgdir):
        out += [os.path.join(cfgdir, f) for f in os.listdir(cfgdir) if f.endswith(".json")]   # the vault's own declarations
    rr = _render_root(v)
    if rr:
        from .governance import Governance
        g = Governance(v)
        for n in v.canonical():
            path = g.render_path(n)
            if path and os.path.isfile(path):
                out.append(path)
    return sorted(set(out))


def ledger_files(v: Vault) -> list:
    """Append-only files: every .jsonl under _ledger (incl. rooms/)."""
    out = []
    ld = os.path.join(v.root, "_ledger")
    for dp, dn, fn in os.walk(ld):
        out += [os.path.join(dp, f) for f in fn if f.endswith(".jsonl")]
    return sorted(out)


def _flag_append(path: str, on: bool) -> bool:
    if sys.platform != "darwin":
        return False
    return _set_flags(path, "uappnd" if on else "nouappnd")


def _flag(path: str, on: bool) -> bool:
    try:
        if sys.platform == "darwin":
            subprocess.run(["chflags", "uchg" if on else "nouchg", path], check=True, capture_output=True)
        else:
            mode = os.stat(path).st_mode
            os.chmod(path, (mode & ~0o222) if on else (mode | 0o200))
        return True
    except (subprocess.CalledProcessError, OSError):
        return False


def _is_flagged(path: str) -> bool:
    try:
        st = os.stat(path)
    except OSError:
        return False
    if sys.platform == "darwin":
        return bool(getattr(st, "st_flags", 0) & stat.UF_IMMUTABLE)
    return not (st.st_mode & 0o200)


def _flags(path: str) -> int:
    try:
        return getattr(os.stat(path), "st_flags", 0)
    except OSError:
        return 0


def _set_flags(path: str, flags: str) -> bool:
    try:
        if sys.platform == "darwin":
            subprocess.run(["chflags", flags, path], check=True, capture_output=True)
            return True
    except (subprocess.CalledProcessError, OSError):
        return False
    return False


@contextlib.contextmanager
def writable(root: str, path: str):
    """The engine's own door through the wall: unlock ONE file for one write, and put
    back exactly the flags it had (immutable, append-only, or none)."""
    had = _flags(path) if os.path.exists(path) else 0
    immutable = bool(had & stat.UF_IMMUTABLE); appendonly = bool(had & getattr(stat, "UF_APPEND", 0))
    if immutable or appendonly:
        _set_flags(path, "nouchg,nouappnd")
    try:
        yield
    finally:
        if os.path.exists(path):
            if immutable:
                _set_flags(path, "uchg")
            elif appendonly:
                _set_flags(path, "uappnd")


def archive_prior(root: str, relpath: str, data: bytes) -> str:
    """Keep the prior bytes of a render before it is superseded. Returns the archive path."""
    sha = hashlib.sha256(data).hexdigest()
    d = os.path.join(root, ARCHIVE_REL, relpath)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"{now_iso().replace(':', '')}-{sha[:12]}")
    if not os.path.exists(p):
        with open(p, "wb") as f:
            f.write(data)
    return p


def versions(root: str, relpath: str) -> list:
    d = os.path.join(root, ARCHIVE_REL, relpath)
    if not os.path.isdir(d):
        return []
    out = []
    for f in sorted(os.listdir(d)):
        p = os.path.join(d, f)
        with open(p, "rb") as fh:
            data = fh.read()
        out.append({"file": f, "path": p, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data), "ts": f.split("-")[0]})
    return out


def _repo_root(start: str):
    p = os.path.abspath(start)
    while True:
        if os.path.isdir(os.path.join(p, ".git")):
            return p
        q = os.path.dirname(p)
        if q == p:
            return None
        p = q


def deny_rules(repo_root: str, v: Vault) -> list:
    rules = list(DENY_SHELL)
    vault_rel = os.path.relpath(v.root, repo_root).replace(os.sep, "/")
    rules += [f"Edit({vault_rel}/**)", f"Write({vault_rel}/**)", f"Bash(rm:*{vault_rel}*)"]
    rr = _render_root(v)
    if rr:
        rel = os.path.relpath(rr, repo_root).replace(os.sep, "/")
        for sub in sorted(d for d in os.listdir(rr) if os.path.isdir(os.path.join(rr, d)) and d not in ("inbox", "work", "vault", ".git")):
            rules += [f"Edit({rel}/{sub}/**)", f"Write({rel}/{sub}/**)"]
        rules += [f"Edit({rel}/*.md)", f"Write({rel}/*.md)", f"Bash(rm:*{rel}*)"]
    return rules


def write_deny_rules(repo_root: str, v: Vault) -> tuple:
    p = os.path.join(repo_root, ".claude", "settings.json")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    data = {}
    if os.path.isfile(p):
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            raise GuardError(f"{p} is not valid JSON — fix it first; the guard wrote nothing to it.")
    perms = data.setdefault("permissions", {})
    deny = perms.setdefault("deny", [])
    rules = deny_rules(repo_root, v)
    for r in rules:
        if r not in deny:
            deny.append(r)
    data["_magnemo_guard"] = {"vault": os.path.relpath(v.root, repo_root), "written": now_iso(), "rules": rules}
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2); f.write("\n")
    return p, rules


def remove_deny_rules(repo_root: str, v: Vault) -> int:
    p = os.path.join(repo_root, ".claude", "settings.json")
    if not os.path.isfile(p):
        return 0
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    rules = set((data.get("_magnemo_guard") or {}).get("rules") or deny_rules(repo_root, v))
    deny = data.get("permissions", {}).get("deny", [])
    kept = [r for r in deny if r not in rules]
    removed = len(deny) - len(kept)
    if "permissions" in data:
        data["permissions"]["deny"] = kept
    data.pop("_magnemo_guard", None)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2); f.write("\n")
    return removed


def deny_rules_present(v: Vault) -> tuple:
    repo = _repo_root(v.root)
    if not repo:
        return 0, None
    p = os.path.join(repo, ".claude", "settings.json")
    if not os.path.isfile(p):
        return 0, p
    try:
        with open(p, encoding="utf-8") as f:
            deny = json.load(f).get("permissions", {}).get("deny", [])
    except json.JSONDecodeError:
        return 0, p
    want = deny_rules(repo, v)
    return sum(1 for r in want if r in deny), p


def on(v: Vault, by: str) -> dict:
    from .governance import TrustLedger
    root = v.root
    files = guarded_files(v)
    flagged = sum(1 for p in files if _flag(p, True))
    # the archive is immutable by nature; the ledgers are append-only by law
    for dp, dn, fn in os.walk(os.path.join(root, ARCHIVE_REL)):
        for f in fn:
            _flag(os.path.join(dp, f), True)
    appended = sum(1 for p in ledger_files(v) if _flag_append(p, True))
    rr = _render_root(v)
    work = os.path.join(rr or os.path.dirname(root), "work")
    os.makedirs(work, exist_ok=True)
    repo = _repo_root(root)
    settings, rules = (None, [])
    if repo:
        settings, rules = write_deny_rules(repo, v)
    st = {"active": True, "since": now_iso(), "by": by, "mode": "chflags uchg (+uappnd on ledgers)" if sys.platform == "darwin" else "chmod a-w (advisory for the owner on Linux)",
          "files": flagged, "ledgers_append_only": appended, "work_dir": work, "settings": settings, "deny_rules": len(rules)}
    os.makedirs(os.path.dirname(_state_path(root)), exist_ok=True)
    with writable(root, _state_path(root)):
        with open(_state_path(root), "w", encoding="utf-8") as f:
            json.dump(st, f, indent=2)
    _flag(_state_path(root), True)   # the guard's own state is immutable too
    TrustLedger(v).record("guard.on", "armed", by, os.path.basename(root),
                          f"{flagged} files immutable ({st['mode']}) · work/ at {work} · {len(rules)} deny rules in {settings or 'no repo'}")
    return st


def off(v: Vault, by: str, reason: str = "") -> dict:
    from .governance import TrustLedger
    from .room import is_human
    if not is_human(v, by):
        raise GuardError(f"'guard --off' is a keyholder verb — '{by}' is not a keyholder (config trust.humans). "
                         "The wall comes down by a keyholder's hand only.")
    root = v.root
    st = state(root)
    files = guarded_files(v)
    for p in files:
        _flag(p, False)
    for dp, dn, fn in os.walk(os.path.join(root, ARCHIVE_REL)):
        for f in fn:
            _flag(os.path.join(dp, f), False)
    for p in ledger_files(v):
        _flag_append(p, False)
    repo = _repo_root(root)
    removed = remove_deny_rules(repo, v) if repo else 0
    new = {"active": False, "since": now_iso(), "by": by, "prior": st}
    _flag(_state_path(root), False)
    with open(_state_path(root), "w", encoding="utf-8") as f:
        json.dump(new, f, indent=2)
    TrustLedger(v).record("guard.off", "lowered", by, os.path.basename(root),
                          (reason or "guard lowered") + f" · {len(files)} files writable again · {removed} deny rules removed")
    return new


def relock_new(v: Vault) -> int:
    """After engine writes created new canon/renders/archives/ledgers, flag them (when active)."""
    if not active(v.root):
        return 0
    n = sum(1 for p in guarded_files(v) if not _is_flagged(p) and _flag(p, True))
    for dp, dn, fn in os.walk(os.path.join(v.root, ARCHIVE_REL)):
        for f in fn:
            p = os.path.join(dp, f)
            if not _is_flagged(p):
                n += _flag(p, True)
    for p in ledger_files(v):
        if not (_flags(p) & getattr(stat, "UF_APPEND", 0)):
            _flag_append(p, True)
    return n


def status_line(v: Vault) -> str:
    st = state(v.root)
    n_rules, settings = deny_rules_present(v)
    if not st.get("active"):
        return f"guard: OFF · deny rules present: {n_rules}" + (f" in {os.path.relpath(settings, v.root)}" if settings else "")
    files = guarded_files(v)
    flagged = sum(1 for p in files if _is_flagged(p))
    return f"guard: ON since {st.get('since')} by {st.get('by')} · {flagged}/{len(files)} files immutable ({st.get('mode')}) · work/ writable · deny rules present: {n_rules}"


def restore(v: Vault, target: str, to: str = "latest", by: str = "founder") -> dict:
    """Bring a version back in one command. `target` = a render path (relative to the
    render root) or a note id. `to` = 'latest' or a sha12/ts prefix from the archive.
    Writes the file through the guard, ledgers memory.restore, and stages the body as a
    founder note superseding the current canonical — canon stays the keyholder's."""
    from .governance import Governance, TrustLedger
    from .vault import Note
    g = Governance(v)
    rr = _render_root(v)
    note = None
    try:
        note = v.read(target)
    except FileNotFoundError:
        pass
    if note is not None:
        relpath = (note.extra or {}).get("render", "")
        if not relpath:
            raise GuardError(f"note {target} has no render path; nothing on disk to restore.")
        body = note.body.rstrip("\n") + "\n"
        version = f"note:{note.id}"
    else:
        relpath = target.replace(os.sep, "/")
        vers = versions(v.root, relpath)
        if not vers:
            raise GuardError(f"No archived versions for '{relpath}'. Versions appear once a render has been superseded at least once; "
                             "if the disk is gone, use `magnemo mount --from <chest>` instead.")
        pick = vers[-1] if to == "latest" else next((x for x in vers if x["file"].startswith(to) or x["sha256"].startswith(to)), None)
        if pick is None:
            raise GuardError(f"No version '{to}' for {relpath}. Available: " + ", ".join(f"{x['file']} ({x['sha256'][:12]})" for x in vers))
        with open(pick["path"], "rb") as f:
            body = f.read().decode("utf-8")
        version = pick["file"]
    if not rr:
        raise GuardError("This vault has no render root (config render.root); there is no file on disk to restore.")
    path = os.path.normpath(os.path.join(rr, relpath))
    prior = None
    if os.path.exists(path):
        with open(path, "rb") as f:
            prior_bytes = f.read()
        prior = hashlib.sha256(prior_bytes).hexdigest()
        archive_prior(v.root, relpath, prior_bytes)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with writable(v.root, path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
    relock_new(v)
    current = [n for n in v.canonical() if (n.extra or {}).get("render") == relpath]
    staged_id = None
    if current and current[-1].body.rstrip("\n") != body.rstrip("\n"):
        nid = v.new_id(f"restore {relpath}")
        v.stage(Note(id=nid, title=current[-1].title, author=by, written=now_iso(),
                     source=f"restore:{relpath} version:{version} by:{by}", status="staged",
                     partition=current[-1].partition, store=current[-1].store, body=body.rstrip("\n"),
                     supersedes=current[-1].id, tags="restore", extra={"render": relpath}))
        staged_id = nid
    TrustLedger(v).record("memory.restore", "restored", by, relpath, f"version {version}",
                          prior_sha256=prior, new_sha256=hashlib.sha256(body.encode()).hexdigest(), staged=staged_id)
    return {"path": path, "version": version, "prior_sha256": prior, "staged": staged_id}
