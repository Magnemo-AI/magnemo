"""magnemo.doctor — the rename survivor's checkup (P-10; friction notes
20260824-friction-repo-rename-* and -cli-has-no-stage-*).

One verb answers "is this install actually going to work?": the vault is
reachable and writable where it must be, the ledgers parse, the config
loads, and every mount file handed in points at a command and a vault that
exist. Absolute paths die silently when a folder is renamed — P-09 proved
it — so the doctor checks the things a rename breaks.

Read-only by design: the doctor diagnoses, it never repairs.

  magnemo doctor [vault] [--mount PATH]...   # PATH = .mcp.json or its folder
"""
from __future__ import annotations
import os, sys, json

from .vault import Vault, PARTITIONS
from .config import load_config, env as _env, legacy_env_in_use, LEGACY_ENV_PREFIX

OK, WARN, FAIL = "ok", "warn", "FAIL"


def _check(results, level, label, detail=""):
    results.append({"level": level, "label": label, "detail": detail})


def check_python(results):
    _check(results, OK, "python", f"{sys.version.split()[0]} at {sys.executable}")
    if not os.path.exists(sys.prefix):
        _check(results, FAIL, "venv", f"sys.prefix vanished: {sys.prefix}")
    try:
        from importlib.metadata import version
        _check(results, OK, "package", f"magnemo {version('magnemo')}")
    except Exception:
        from . import __version__
        _check(results, WARN, "package",
               f"magnemo {__version__} (source tree, not an installed dist)")


def _repair_skeleton(path):
    """A vault whose empty folders were swept away (rm -rf under the guard leaves only the
    flagged files) gets its skeleton back — nothing else is touched."""
    if os.path.isdir(path) and not os.path.isdir(os.path.join(path, "_staging")) and (
            os.path.isfile(os.path.join(path, "_config", "magnemo.json")) or os.path.isdir(os.path.join(path, "_ledger"))):
        Vault(path).init()
        return True
    return False


def check_vault(results, path):
    if _repair_skeleton(path):
        _check(results, NOTE, "vault", "system folders were missing and have been rebuilt (the flagged files survived; the empty folders did not)")
    v = Vault(path)
    if not v.exists():
        _check(results, FAIL, "vault", f"no vault at {path}")
        return None
    _check(results, OK, "vault", str(v.root))
    for part in v.partitions:
        d = os.path.join(v.root, part)
        if not os.path.isdir(d):
            _check(results, FAIL, f"partition {part}", f"missing: {d}")
    for special, must_write in (("_staging", True), ("_ledger", True),
                                ("_config", False), ("_index", False)):
        d = os.path.join(v.root, special)
        if not os.path.isdir(d):
            _check(results, FAIL, special, f"missing: {d}")
        elif must_write and not os.access(d, os.W_OK):
            _check(results, FAIL, special, f"not writable: {d}")
        else:
            _check(results, OK, special, "present" + (" · writable" if must_write else ""))
    try:
        load_config(v.root)
        _check(results, OK, "config", "loads (defaults fill any gaps)")
    except Exception as e:
        _check(results, FAIL, "config", f"unreadable: {e}")
    return v


def check_ledgers(results, v):
    ldir = os.path.join(v.root, "_ledger")
    if not os.path.isdir(ldir):
        return
    for fn in sorted(os.listdir(ldir)):
        if not fn.endswith(".jsonl"):
            continue
        path, n = os.path.join(ldir, fn), 0
        try:
            with open(path, encoding="utf-8") as f:
                for i, line in enumerate(f, 1):
                    if line.strip():
                        json.loads(line)
                        n += 1
            _check(results, OK, f"ledger {fn}", f"{n} events, all parse")
        except json.JSONDecodeError as e:
            _check(results, FAIL, f"ledger {fn}", f"line {i} unparseable: {e.msg}")


def check_mount(results, path):
    """PATH is a .mcp.json or a folder containing one."""
    mf = path if path.endswith(".json") else os.path.join(path, ".mcp.json")
    name = mf
    if not os.path.isfile(mf):
        _check(results, FAIL, f"mount {name}", "no .mcp.json found")
        return
    try:
        with open(mf, encoding="utf-8") as f:
            servers = json.load(f).get("mcpServers", {})
    except json.JSONDecodeError as e:
        _check(results, FAIL, f"mount {name}", f"invalid JSON: {e.msg}")
        return
    if not servers:
        _check(results, WARN, f"mount {name}", "no mcpServers registered")
    for sname, cfg in servers.items():
        cmd = cfg.get("command", "")
        env = cfg.get("env", {})
        _LEGACY_SEEN.update(legacy_env_in_use(env))
        problems = []
        if os.path.sep in cmd:
            if not os.path.isfile(cmd):
                problems.append(f"command missing: {cmd} (renamed folder?)")
            elif not os.access(cmd, os.X_OK):
                problems.append(f"command not executable: {cmd}")
        soft = []
        mv = _env("VAULT", "", env)
        if mv and "${" in mv:
            soft.append(f"MAGNEMO_VAULT uses a variable this checker cannot expand ({mv}) — verify in your agent")
        elif mv and not Vault(mv).exists():
            problems.append(f"MAGNEMO_VAULT has no vault: {mv}")
        pyp = env.get("PYTHONPATH", "")
        if pyp and not os.path.isdir(pyp):
            problems.append(f"PYTHONPATH missing: {pyp}")
        scope = _env("SCOPE", "", env)
        if scope:
            vv = Vault(mv) if (mv and "${" not in mv and Vault(mv).exists()) else None
            good = vv.resolve_scope(scope.split(",")) if vv else [p for p in scope.split(",") if p.strip() in PARTITIONS]
            if not good:
                valid = ", ".join(vv.partitions) if vv else ", ".join(PARTITIONS)
                problems.append(f"MAGNEMO_SCOPE={scope!r} names no valid partition or scope "
                                f"(valid: {valid}; omit to allow all) — the server will refuse to boot")
        if not _env("VAULT", "", env):
            problems.append("MAGNEMO_VAULT not set — the server requires it")
        import shutil as _sh
        if os.path.sep not in cmd and _sh.which(cmd) is None:
            soft.append(f"command not on this shell's PATH: {cmd} — fine if your agent resolves it")
        agent = _env("AGENT", "agent", env)
        walls = _env("PARTITIONS", "all", env)
        if problems:
            _check(results, FAIL, f"mount {name} · {sname}", " · ".join(problems))
        elif soft:
            _check(results, WARN, f"mount {name} · {sname}", " · ".join(soft))
        else:
            _check(results, OK, f"mount {name} · {sname}",
                   f"agent={agent} writes={walls}")


_LEGACY_SEEN: set = set()
NOTE = "note"   # a plain line: neither a warning nor a failure


def run(vault_path: str, mounts: list[str]) -> list[dict]:
    results: list[dict] = []
    _LEGACY_SEEN.clear()
    _LEGACY_SEEN.update(legacy_env_in_use())
    check_python(results)
    v = check_vault(results, vault_path)
    if v is not None:
        check_ledgers(results, v)
        check_drift(results, v)
        check_guard(results, v)
        check_chest(results, v)
    for m in mounts:
        check_mount(results, m)
    if _LEGACY_SEEN:   # exactly once, however many places still say the old name
        _check(results, NOTE, "settings",
               "You're using MEMOS_* settings — they still work; rename them to MAGNEMO_* before 0.7. "
               f"({', '.join(sorted(_LEGACY_SEEN))})")
    return results


def check_drift(results, v):
    """THE WRITE PATH (P-19): a rendered file edited by hand on disk is DRIFT.
    Founder edits win — re-staged as a note tagged founder, superseding the
    canonical one, so the promotion that keeps the edit carries a receipt."""
    import hashlib as _h
    from .governance import Governance
    from .vault import Note, now_iso
    g = Governance(v)
    drifted = []
    from . import guard as _guard
    # A render belongs to the NEWEST canonical version that renders to that path
    # (the last promotion wrote it). Older canonical versions of the same file are
    # superseded, not drifted — comparing them would re-stage the current render as
    # a phantom "founder edit" on every run.
    last_render = {}   # render rel path → the note id that last rendered it (ledger order = promotion order)
    for e in g.ledger.entries("memory.render"):
        if e.get("detail"):
            last_render[e["detail"]] = e.get("subject")
    owner = {}
    for n in v.canonical():
        path = g.render_path(n)
        if path is None:
            continue
        rel = n.extra.get("render", "")
        key = (1 if last_render.get(rel) == n.id else 0, n.reviewed_at or "", n.written, n.id)
        if path not in owner or key > owner[path][0]:
            owner[path] = (key, n)
    for path, (_key, n) in owner.items():
        if not os.path.exists(path):
            # a deleted render is re-rendered from canon: no delete, only supersede
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with _guard.writable(v.root, path), open(path, "wb") as f:
                f.write((n.body.rstrip("\n") + "\n").encode("utf-8"))
            _guard.relock_new(v)
            # canon did not change, so this is a note, not a ledger event (keeps restored boot packs byte-identical)
            _check(results, NOTE, "guard", f"{n.extra.get('render')} was missing on disk — re-rendered from canon (nothing is deleted, only superseded).")
            continue
        with open(path, "rb") as f:
            disk = f.read()
        text = disk.decode("utf-8", errors="replace")
        if text.rstrip("\n") == n.body.rstrip("\n"):
            continue
        already = [s for s in v.staged() if s.status == "staged" and s.supersedes == n.id
                   and s.body.rstrip("\n") == text.rstrip("\n")]
        if already:
            drifted.append((n.extra.get("render"), already[0].id, "already re-staged"))
            continue
        nid = v.new_id(f"founder edit {n.title}")
        v.stage(Note(id=nid, title=n.title, author="founder", written=now_iso(),
                     source=f"drift:{n.extra.get('render')} sha256:{_h.sha256(disk).hexdigest()}",
                     status="staged", partition=n.partition, store=n.store, body=text,
                     supersedes=n.id, tags="founder-edit", taint=n.taint, impact=n.impact,
                     extra={"render": n.extra.get("render")}))
        drifted.append((n.extra.get("render"), nid, "re-staged"))
    for rel, nid, how in drifted:
        _check(results, NOTE, "drift", f"{rel} was edited on disk — {how} as {nid} (author: founder). "
                                        "Promote it to keep the edit; the ledger keeps the prior hash.")


def check_guard(results, v):
    """THE GUARD (P-34): state, immutable-file count, and whether the body's deny rules are present."""
    from . import guard
    line = guard.status_line(v)
    n_rules, settings = guard.deny_rules_present(v)
    if guard.active(v.root):
        files = guard.guarded_files(v); flagged = sum(1 for p in files if guard._is_flagged(p))
        if flagged < len(files):
            _check(results, WARN, "guard", line + f" — {len(files) - flagged} guarded file(s) are NOT immutable; run `magnemo guard` again")
        elif n_rules == 0:
            _check(results, WARN, "guard", line + " — the body's deny rules are missing from .claude/settings.json")
        else:
            _check(results, OK, "guard", line)
    else:
        _check(results, OK, "guard", line + " — `magnemo guard <vault>` raises the wall")


def check_chest(results, v):
    """THE CHEST (#129): one line, always — a vault with one copy is told it has one copy."""
    from . import chest
    try:
        line = chest.gauge(v.root)
    except chest.ChestError as e:
        _check(results, FAIL, "chest", str(e))
        return
    ok, why = chest.verify_chain(v.root)
    if not ok:
        _check(results, FAIL, "chest", line + " — " + why)
    elif "🔴" in line:
        _check(results, WARN, "chest", line + " — a push was blocked by the secret sweep; the Sentinel note in your review queue names the file and pattern")
    elif "🟠" in line:
        _check(results, WARN, "chest", line + " — the last copy failed; the chest retries on the next event")
    elif "B —" in line and "C —" in line:
        _check(results, WARN, "chest", line + " — this vault exists in ONE place. `magnemo chest add` conducts a copy somewhere you own")
    else:
        _check(results, OK, "chest", line)


def report(results) -> bool:
    """Print the checkup; True when nothing FAILed."""
    width = max(len(r["label"]) for r in results)
    for r in results:
        mark = {"ok": "✓", "warn": "!", "FAIL": "✗", "note": "·"}[r["level"]]
        print(f" {mark} {r['label']:<{width}}  {r['detail']}")
    fails = [r for r in results if r["level"] == FAIL]
    warns = [r for r in results if r["level"] == WARN]
    notes = [r for r in results if r["level"] == NOTE]
    print(f"\nDOCTOR: {len(results) - len(fails) - len(warns) - len(notes)} ok · "
          f"{len(warns)} warn · {len(fails)} fail")
    if fails:
        print("Absolute paths break silently on renames — fix the ✗ lines, "
              "then run the doctor again.")
    return not fails
