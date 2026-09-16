"""magnemo.cli — the human's door into Magnemo.

Agents get MCP tools; the founder gets this. Promotion lives HERE and only
here — the asymmetry is the protocol.

  python -m magnemo.cli init   <vault-path>
  python -m magnemo.cli review [--batch N] [<vault-path>]   # queue, salience-sorted
  python -m magnemo.cli flag    <note-id> --by NAME     # operator signal (KAIROS)
  python -m magnemo.cli rescore [<vault-path>]          # recompute staged salience
  python -m magnemo.cli bootpack [--scope P] [--class worker|partner] [--actor A]  # BOOT_PACK.md
  python -m magnemo.cli handoff --usage PCT --trigger T [--cut "..."]  # boundary telemetry
  python -m magnemo.cli handoff --report                # every boundary, as a table
  python -m magnemo.cli costs   [<vault-path>]          # foresight counters + baseline
  python -m magnemo.cli stage   TITLE --partition P --store S --source SRC [--body|--file|stdin]  # founder's write path → _staging/
  python -m magnemo.cli doctor  [--mount PATH]* [<vault-path>]  # install/mount/vault checkup (P-10)
  python -m magnemo.cli show    <note-id>  [vault]
  python -m magnemo.cli yes [id-fragment | --all] [--by NAME] [--reason TXT] [vault]   # the gate lift is a word (P-54)
  python -m magnemo.cli no  <id-fragment> --reason TXT [--by NAME] [vault]
  python -m magnemo.cli promote <note-id> --by NAME [--reason TXT] [vault]
  python -m magnemo.cli reject  <note-id> --by NAME --reason TXT   [vault]
  python -m magnemo.cli ledger  [vault]
  python -m magnemo.cli autonomy <actor> [--as-of ISO] [--json] [vault]   # trust scorecard (P-02)
  python -m magnemo.cli trust record <actor> <class> <kind> --by NAME [--reason TXT] [--ref X] [--when ISO]
  python -m magnemo.cli grant <grantee> --classes C[,C] --level N --by KEYHOLDER [--scope] [--condition]* [--kind] [--ref] [--expires]
  python -m magnemo.cli revoke <grant-id> --by KEYHOLDER --reason TXT
  python -m magnemo.cli grants [--actor A] [--as-of ISO]          # every grant and its state
  python -m magnemo.cli gates  [--as-of ISO] [--json]             # the Gate Map (#103)
"""
from __future__ import annotations
import os, sys, argparse, json
from .vault import Vault
from .governance import Governance
from .config import load_config, env
from . import kairos

DEF = env("VAULT", "./vault")


def _gov(path):
    v = Vault(path)
    if not v.exists():
        print(f"No vault at {path}. Run: python -m magnemo.cli init {path}")
        sys.exit(1)
    return Governance(v)


def cmd_init(a):
    v = Vault(a.vault)
    v.init()
    print(f"Vault initialized at {v.root}")
    print("Plain markdown — view it in any editor. Agents connect via the Magnemo MCP server.")
    print()
    print("Next:  magnemo mount    # register the MCP server in this project's .mcp.json")
    print("       magnemo doctor   # verify everything, mount included")


def _fmt_salience(n):
    if n.salience < 0:
        return "salience —  (unscored — run: cli rescore)"
    try:
        c = json.loads(n.salience_components or "{}")
    except json.JSONDecodeError:
        c = {}
    comps = " ".join(f"{k[0].upper()}{c[k]:.2f}" for k in
                     ("consequence", "novelty", "operator", "source") if k in c)
    return f"salience {n.salience:.4f}  [{comps}]"


def cmd_review(a):
    g = _gov(a.vault)
    cfg = load_config(g.vault.root)
    ghosts = g.vault.ghosts()
    if ghosts:
        print(f"  ⚠ {len(ghosts)} ghost(s) in _staging — already canonical, excluded from the queue; "
              f"delete the stale copies: {', '.join(ghosts)}")
    staged = [n for n in g.vault.staged() if n.status == "staged"]
    if not staged:
        print("Review queue is empty. Nothing awaits you.")
        return
    batch = a.batch if a.batch is not None else int(cfg["review"]["batch"])
    queue = kairos.sorted_queue(staged, batch)
    print(f"\n  MAGNEMO REVIEW QUEUE — depth {len(staged)}, "
          f"showing top {len(queue)} by salience (batch cap {batch})\n" + "=" * 60)
    for n in queue:
        print(f"\n[{n.id}]")
        print(f"  {n.title}")
        print(f"  {_fmt_salience(n)}" + (f" · impact {n.impact}" if n.impact else ""))
        print(f"  by {n.author} · {n.written} · → {n.partition}/{n.store} · src {n.source}")
        if n.supersedes:
            print(f"  supersedes: {n.supersedes}")
        preview = n.body[:400].replace("\n", "\n  ")
        print(f"  ---\n  {preview}{'…' if len(n.body) > 400 else ''}")
        while True:
            ans = input("\n  [p]romote / [r]eject / [s]kip / [q]uit > ").strip().lower()
            if ans == "p":
                who = input("  your name: ").strip() or "founder"
                g.promote(n.id, who)
                print(f"  ✓ PROMOTED — canonical in {n.partition}/{n.store}")
                break
            if ans == "r":
                who = input("  your name: ").strip() or "founder"
                why = input("  reason (recorded — rejections teach): ").strip() or "no reason given"
                g.reject(n.id, who, why)
                print("  ✗ REJECTED — recorded to ledger")
                break
            if ans == "s":
                break
            if ans == "q":
                return
    print("\nQueue pass complete.")


def cmd_show(a):
    g = _gov(a.vault)
    print(g.vault.read(a.note_id).to_markdown())


def _queue(g):
    """The review queue in the order `review` shows it: salience desc, id as the tiebreak."""
    return kairos.sorted_queue([n for n in g.vault.staged() if n.status == "staged"])

def _pick(g, fragment):
    """One staged note whose id contains the fragment; two matches = refuse and list them."""
    hits = [n for n in _queue(g) if fragment in n.id]
    if not hits:
        print(f"no staged note matches {fragment!r}")
        sys.exit(2)
    if len(hits) > 1:
        print(f"{len(hits)} staged notes match {fragment!r} — say which:")
        for n in hits:
            print(f"  {n.id}  {n.title}")
        sys.exit(2)
    return hits[0]

def _by_default(g, by):
    """`--by` defaults to the first keyholder in trust.humans: the yes is the human's."""
    if by:
        return by
    humans = (load_config(g.vault.root).get("trust") or {}).get("humans") or []
    return humans[0] if humans else "founder"

def _ran_by():
    """The hand that ran the command: the agent seat if one is set, else the terminal."""
    return env("AGENT") or "terminal"

def cmd_yes(a):
    """THE GATE LIFT IS A WORD (P-54, the two-yes law). `yes` promotes the top of the
    queue; `yes <fragment>` one note; `yes --all` the whole queue, one ledger entry each.
    Every entry carries ran_by. Promotion stays a CLI verb — never an MCP tool."""
    # `magnemo yes <vault>`: a lone positional that is a directory is the vault, not a fragment
    if a.fragment and a.vault == DEF and os.path.isdir(a.fragment):
        a.vault, a.fragment = a.fragment, ""
    g = _gov(a.vault)
    by = _by_default(g, a.by)
    reason = a.reason or "approved in chat"
    ran_by = _ran_by()
    if a.all:
        targets = _queue(g)
    elif a.fragment:
        targets = [_pick(g, a.fragment)]
    else:
        q = _queue(g)
        if not q:
            print("Review queue is empty. Nothing awaits you.")
            return
        targets = [q[0]]
    if not targets:
        print("Review queue is empty. Nothing awaits you.")
        return
    for n in targets:
        g.promote(n.id, by, reason, ran_by=ran_by)
        print(f"✓ PROMOTED {n.id} — canonical in {n.partition}/{n.store} · by {by} · ran_by {ran_by}")

def cmd_no(a):
    """`no <fragment> --reason TXT`: rejects one staged note. The reason stays required — rejections teach."""
    g = _gov(a.vault)
    n = _pick(g, a.fragment)
    by = _by_default(g, a.by)
    ran_by = _ran_by()
    g.reject(n.id, by, a.reason, ran_by=ran_by)
    print(f"✗ REJECTED {n.id} — recorded to ledger · by {by} · ran_by {ran_by}")

def cmd_promote(a):
    g = _gov(a.vault)
    n = g.promote(a.note_id, a.by, a.reason or "")
    print(f"PROMOTED {n.id} → {n.partition}/{n.store}")


def cmd_reject(a):
    g = _gov(a.vault)
    g.reject(a.note_id, a.by, a.reason)
    print(f"REJECTED {a.note_id} (reason recorded)")


def cmd_outcome(a):
    g = _gov(a.vault)
    touched = g.record_outcome(a.rid, a.verdict, a.by, a.reason or "")
    print(f"{a.verdict.upper()} recorded for receipt {a.rid} — {len(touched)} memories "
          f"{'credited' if a.verdict == 'approved' else 'debited'}: {', '.join(touched)}")


def cmd_flag(a):
    g = _gov(a.vault)
    n = g.flag(a.note_id, a.by, a.reason or "")
    print(f"FLAGGED {n.id} — operator signal set, {_fmt_salience(n)}")


def cmd_rescore(a):
    g = _gov(a.vault)
    touched = g.rescore()
    print(f"Rescored {len(touched)} staged note(s).")
    for n in kairos.sorted_queue(touched):
        print(f"  {n.salience:.4f}  {n.id}")


def cmd_costs(a):
    from . import foresight
    g = _gov(a.vault)
    print(foresight.summary_table(g.vault))


def cmd_stage(a):
    """The founder's terminal write path (P-10). Same gate as every agent:
    routes through Governance.agent_write, lands in _staging/, never touches
    canon. Provenance (--source) is mandatory — paperless notes are refused
    by the parser before the vault ever sees them."""
    from . import foresight
    from .mcp import nearest_duplicate
    g = _gov(a.vault)
    body = a.body
    if a.file:
        with open(a.file, encoding="utf-8") as f:
            body = f.read()
    elif body is None and not sys.stdin.isatty():
        body = sys.stdin.read()
    if not body or not body.strip():
        print("stage: a body is required (--body TEXT, --file PATH, or stdin)")
        sys.exit(2)
    author = a.author or env("AGENT") or "founder"
    # P-54 · THE OPERATOR FLAG, deterministic: a note staged by a human hand (the author is a
    # keyholder in trust.humans) carries the operator tag. No text sniffing.
    tags = a.tags
    from . import trust as _trust
    cfg_ = load_config(g.vault.root)
    if _trust.is_human(cfg_, author):
        otag = (cfg_.get("kairos") or {}).get("operator_tag", "founder-flag")
        tl = [t.strip() for t in tags.split(",") if t.strip()]
        if otag not in tl:
            tl.append(otag)
        tags = ",".join(tl)
    dup = nearest_duplicate(a.title, body, a.partition, g.vault)
    n = g.agent_write(title=a.title, body=body, partition=a.partition,
                      store=a.store, author=author, source=a.source,
                      tags=tags, supersedes=a.supersedes, taint=a.taint,
                      impact=a.impact)
    foresight.log_cost(g.vault, "stage", len(body.encode("utf-8")), {
        "via": "cli", "id": n.id, "agent": author, "partition": a.partition,
        "store": a.store, "salience": n.salience,
        "dup_of": dup["id"] if dup else "", "taint": bool(n.taint)})
    print(f"staged: {n.id}")
    print(f"  {_fmt_salience(n)}")
    if dup:
        print(f"  possible duplicate of: {dup['id']}")
    print(f"  path: _staging/{n.id}.md — awaiting review (cli review)")


def cmd_inbox(a):
    if a.tag is None:
        a.tag = env("AGENT") or "founder"
    """THE INBOX DOOR (P-19): every file dropped in <dir> is STAGED — never promoted —
    with provenance {file, sha256, drop time, author tag}, routed by filename to a
    partition/store (+ render path) from config inbox.routes. Sentinel sweeps each
    drop BEFORE it becomes a memory: a hit is held in <dir>/blocked/, a Sentinel note
    is staged naming file + pattern (never the value), and the chest is blocked."""
    import hashlib, fnmatch, shutil
    from . import chest
    from .vault import Note, now_iso
    g = _gov(a.vault)
    v = g.vault
    cfg = load_config(v.root)
    ib = a.dir or (cfg.get("inbox") or {}).get("dir", "")
    if not ib:
        print("No inbox configured. Pass a folder, or set inbox.dir in _config/magnemo.json.")
        sys.exit(1)
    inbox = os.path.normpath(os.path.join(v.root, ib)) if not os.path.isabs(ib) else ib
    routes = (cfg.get("inbox") or {}).get("routes") or []
    os.makedirs(inbox, exist_ok=True)
    drops = sorted(f for f in os.listdir(inbox) if os.path.isfile(os.path.join(inbox, f)) and not f.startswith("."))
    if not drops:
        print(f"inbox empty: {inbox}")
        return
    staged, held = [], []
    for fn in drops:
        path = os.path.join(inbox, fn)
        route = next((r for r in routes if fnmatch.fnmatch(fn, r.get("match", "*"))), None)
        if route is None:
            print(f"  ? {fn}: no route matches — add one to inbox.routes; left in the inbox")
            continue
        with open(path, "rb") as f:
            raw = f.read()
        sha = hashlib.sha256(raw).hexdigest()
        hits = chest.sweep(inbox, [fn])
        if hits:
            os.makedirs(os.path.join(inbox, "blocked"), exist_ok=True)
            shutil.move(path, os.path.join(inbox, "blocked", fn))
            sid = v.new_id(f"sentinel held {fn}")
            v.stage(Note(id=sid, title=f"Sentinel: '{fn}' held at the inbox door — secret-shaped text ({hits[0][1]})",
                         author="sentinel", written=now_iso(), source=f"inbox:{fn} sha256:{sha} by {a.tag}",
                         status="staged", partition=route["partition"], store=route["store"], impact="security",
                         taint=f"sentinel:{hits[0][1]}",
                         body=(f"The drop `{fn}` was NOT staged: it contains text shaped like a secret "
                               f"(pattern: **{hits[0][1]}**). The value is deliberately not recorded here. "
                               "It is held in the inbox's blocked/ folder; the chest will not conduct a copy "
                               "while it sits there. Move the secret out, delete the held file, drop again.")))
            for d in chest.load(v.root)["destinations"]:
                chest._append(v.root, {"kind": "CHEST_BLOCKED", "destination": d["label"], "trigger": "inbox",
                                        "hits": [{"file": f"inbox/{fn}", "pattern": hits[0][1]}]})
            held.append((fn, hits[0][1], sid))
            continue
        taint = ""
        try:
            text = raw.decode("utf-8")
            body = text
            from .sentinel import sweep_text
            ikind, ipat = sweep_text(text)
            if ikind == "injection":
                taint = f"sentinel:injection:{ipat}"
                aid = v.new_id(f"sentinel alert {fn}")
                v.stage(Note(id=aid, title=f"Sentinel ALERT: '{fn}' carries an instruction-shaped line ({ipat})", author="sentinel",
                             written=now_iso(), source=f"inbox:{fn} sha256:{sha} by {a.tag}", status="staged",
                             partition=route["partition"], store=route["store"], impact="security", taint=taint,
                             body=(f"The drop `{fn}` was staged TAINTED: it contains text shaped like an instruction to an agent "
                                   f"(pattern **{ipat}**). Nothing acts on it; taint travels with anything derived from it; a human clears it.")))
        except UnicodeDecodeError:
            body = f"BINARY RECEIPT\n\n- file: {fn}\n- size: {len(raw)} bytes\n- sha256: {sha}\n\n(binary content lives beside the vault; this memory is its provenance pointer)"
        render = route.get("render", "").replace("{name}", fn)
        title = route.get("title", "{stem}").replace("{stem}", os.path.splitext(fn)[0]).replace("{name}", fn)
        supersedes = ""
        if render:
            prior = [n for n in v.canonical() if (n.extra or {}).get("render") == render]
            if prior:
                supersedes = prior[-1].id
        n = g.agent_write(title=title, body=body, partition=route["partition"], store=route["store"],
                          author=a.tag, source=f"inbox:{fn} sha256:{sha} at {now_iso()} by {a.tag}",
                          tags="inbox", impact=("security" if taint else route.get("impact", "info")), supersedes=supersedes, taint=taint)
        if render:
            n.extra["render"] = render
            v.rewrite(n)
        try:
            os.remove(path)
        except (PermissionError, OSError):
            # the drop is staged; if this environment cannot delete it, set it aside
            # under _staged/ so the next sweep never re-stages it — and keep going
            os.makedirs(os.path.join(inbox, "_staged"), exist_ok=True)
            try:
                shutil.move(path, os.path.join(inbox, "_staged", fn))
            except (PermissionError, OSError):
                pass
        staged.append((fn, n.id))
    for fn, nid in staged:
        print(f"  staged  {fn} → {nid}")
    for fn, pat, sid in held:
        print(f"  HELD    {fn} — secret-shaped text ({pat}); Sentinel note {sid}; chest blocked until it is cleared")
    for fn, nid in staged:
        try:
            nn = v.read(nid)
            if nn.taint:
                print(f"  TAINTED {fn} — {nn.taint}; a Sentinel ALERT note is staged; nothing acts on it")
        except FileNotFoundError:
            pass
    print(f"{len(staged)} staged · {len(held)} held · promote with: magnemo yes")


def cmd_guard(a):
    from . import guard
    v = Vault(a.vault)
    if not v.exists():
        print(f"No vault at {a.vault}. Run: magnemo init"); sys.exit(1)
    by = a.by or env("AGENT") or "founder"
    try:
        if a.status:
            print(guard.status_line(v)); return
        if a.off:
            st = guard.off(v, by, a.reason or "")
            print(f"Guard lowered by {by}. Files are writable again; the body's deny rules were removed. Ledgered.")
            return
        st = guard.on(v, by)
        print(f"GUARD ON — {st['files']} files immutable ({st['mode']}). Directories stay open so the engine can add canon and renders.")
        print(f"  agents write in: {st['work_dir']}")
        print(f"  body deny rules: {st['deny_rules']} written to {st['settings'] or '(no git repo above the vault — none written)'}")
        print("  The agent can't delete what it was never allowed to write. Lower it: magnemo guard --off --by <human>")
    except guard.GuardError as e:
        print(str(e)); sys.exit(1)


def cmd_restore(a):
    from . import guard
    v = Vault(a.vault)
    if not v.exists():
        print(f"No vault at {a.vault}. Run: magnemo init"); sys.exit(1)
    by = a.by or env("AGENT") or "founder"
    try:
        if a.versions:
            vers = guard.versions(v.root, a.target)
            print(f"{len(vers)} archived version(s) of {a.target}:")
            for x in vers:
                print(f"  {x['file']}  sha256 {x['sha256'][:12]}  {x['size']} bytes")
            return
        r = guard.restore(v, a.target, to=a.to, by=by)
        print(f"restored {r['path']} ← {r['version']}" + (f" (prior {r['prior_sha256'][:12]} archived)" if r['prior_sha256'] else ""))
        if r["staged"]:
            print(f"  staged {r['staged']} as a founder note superseding the current canonical — promote it to make canon match the disk.")
    except guard.GuardError as e:
        print(str(e)); sys.exit(1)


def cmd_room(a):
    from . import room
    v = Vault(a.vault)
    if not v.exists():
        print(f"No vault at {a.vault}. Run: magnemo init"); sys.exit(1)
    by = a.by or env("AGENT") or "founder"
    try:
        if a.sub == "open":
            e = room.open_room(v, a.room, [s for s in a.seats.split(",") if s.strip()], by)
            print(f"Room '{a.room}' is open — seats: {', '.join(e['seats'])} (human seat: {', '.join(e['human_seats'])}, always present).")
            print(f"Talk is staging; canon is human. Say something: magnemo room say {a.room} \"...\" --class report")
        elif a.sub == "say":
            r = room.say(v, a.room, a.body, a.cls, by, to=a.to or "room", reply_to=a.reply_to or "", about=a.about or "")
            n = r["note"]
            print(f"staged {n.id} ({a.cls}, salience {n.salience:.3f})" + (f" — TAINTED {r['taint']}; ALERT raised, nothing acts on it" if r["alert"] else ""))
        elif a.sub == "connect":
            room.connect(v, a.room, a.seat, by); print(f"{a.seat} is in the room '{a.room}'.")
        elif a.sub == "separate":
            room.separate(v, a.room, a.seat, by, a.reason or ""); print(f"{a.seat} was separated from '{a.room}' — its later messages will be refused; a human seat can bring it back.")
        elif a.sub == "watch":
            import time
            seen = 0
            while True:
                lines = room.transcript(v, a.room)
                for l in lines[seen:]:
                    print(l)
                seen = len(lines)
                if not a.follow:
                    break
                time.sleep(2)
        elif a.sub == "close":
            e = room.close(v, a.room, by); print(f"Room '{a.room}' closed by {by} after {e['messages']} messages — replay it any time: magnemo room replay {a.room}")
        elif a.sub == "replay":
            r = room.replay(v, a.room); st = r["state"]
            print("\n".join(r["transcript"]))
            print(f"-- state from the ledger alone: {'open' if st['open'] else 'closed'} · seats {', '.join(st['seats'])} · {st['messages']} messages · {st['alerts']} alerts")
        elif a.sub == "list":
            for name in room.list_rooms(v):
                st = room.state(v, name); print(f"{name}: {'open' if st['open'] else 'closed'} · seats {', '.join(st['seats'])} · {st['messages']} messages")
    except room.RoomError as e:
        print(str(e)); sys.exit(1)


def cmd_run(a):
    from . import run as _run
    try:
        if a.card:
            print(_run.card(a.vault)); return
        if a.unschedule:
            _run.unschedule(a.vault, a.unschedule); print(f"removed {a.unschedule}"); return
        if not a.task:
            print('magnemo run "<task>" --engine claude [--schedule "<cron>"] [--cap-turns N] [--cap-usd X]   ·   magnemo run --card'); sys.exit(2)
        if a.schedule:
            out = _run.schedule(a.vault, a.task, a.schedule, engine=a.engine, cap_turns=a.cap_turns, cap_usd=a.cap_usd)
            print(f"Scheduled: {out['plain']} — RAIL entry written to {out['rail']}")
            print(f"  {out['kind']} job '{out['label']}' " + ("installed." if out["installed"] else "written but NOT installed" + (": " + out.get("install_note", "") if out.get("install_note") else "") + "."))
            print(f"  Every scheduled run stages; a human promotes. Remove it: magnemo run --unschedule {out['label']}")
            return
        r = _run.run(a.vault, a.task, engine=a.engine, cap_turns=a.cap_turns, cap_usd=a.cap_usd, trigger=a.trigger)
        print(f"RUN {r['run_id']} · agent {r['agent']} · {r['engine_actions']} engine actions · staged {len(r['staged_notes'])} note(s): {', '.join(r['staged_notes']) or '—'}")
        print(r["fuel"])
        print(f"exit: {r['exit_reason']}")
        if r.get("result"):
            print("result: " + r["result"].strip().replace("\n", " ")[:300])
    except _run.RunError as e:
        print(str(e)); sys.exit(1)


def cmd_chest(a):
    from . import chest
    try:
        if a.sub == "add":
            d = chest.add_destination(a.vault, a.kind, a.target, label=a.label, branch=a.branch)
            slot = "BC"[len(chest.load(a.vault)["destinations"]) - 1]
            print(f"Copy {slot} registered: '{d['label']}' → {d['target']}")
            print("Magnemo will conduct copies here on every promote, receipt, and handoff (and every 10 staged notes,")
            print("or 24h at most). It never holds a copy itself. Every push is swept for secret-shaped text first.")
            print("First copy now: magnemo chest push")
        elif a.sub == "status":
            for line in chest.status_lines(a.vault):
                print(line)
        elif a.sub == "push":
            if a.no_sweep:
                if not a.by:
                    print("--no-sweep is a human decision: add --by <your name>. It is written to the ledger.")
                    sys.exit(2)
                print("SWEEP DISABLED for this push by " + a.by + " — recorded in the ledger.")
            res = chest.push(a.vault, label=a.label, trigger=a.reason, by=a.by, no_sweep=a.no_sweep)
            bad = False
            for r in res:
                print(r["message"])
                bad = bad or r["status"] != "ok"
            print(chest.gauge(a.vault))
            sys.exit(1 if bad else 0)
        elif a.sub == "tick":
            res = chest.tick(a.vault)
            print("ceiling reached — copy conducted." if res else "within the ceiling — nothing to do.")
            print(chest.gauge(a.vault))
    except chest.ChestError as e:
        print(str(e))
        sys.exit(1)


def cmd_mount(a):
    """Register the magnemo MCP server in a project MCP config (.mcp.json).
    Merges — never clobbers other servers. The one command that makes the
    mount deterministic: no hand-written env vars, no guessed scopes."""
    import shutil
    if getattr(a, "src", ""):
        from . import chest, doctor as _doctor
        try:
            out = chest.restore(a.src, a.vault)
        except chest.ChestError as e:
            print(str(e))
            sys.exit(1)
        print(f"Restored a {out['kind']} copy into {out['vault']} ({out['ledger']}).")
        _doctor.report(out["doctor"])
        print(f"Boot pack: {out['bootpack']}")
        print(f"  sha256 {out['bootpack_sha256']}")
        if not out["doctor_ok"]:
            print("The restore landed but the doctor found a problem above; the MCP mount was not registered.")
            sys.exit(1)
    v = Vault(a.vault)
    if not v.exists():
        print(f"No vault at {a.vault}. Run: magnemo init")
        sys.exit(1)
    target = a.file
    cmd = "magnemo-mcp"
    if shutil.which(cmd) is None:
        cand = os.path.join(os.path.dirname(sys.executable), "magnemo-mcp")
        if os.path.isfile(cand):
            cmd = cand  # venv script not on PATH — pin the absolute path
        else:
            print("warning: magnemo-mcp is not on PATH; writing the bare name — "
                  "your agent must run it from an environment where pip's scripts resolve")
    entry = {"command": cmd, "env": {"MAGNEMO_VAULT": os.path.abspath(v.root)}}
    if a.agent:
        entry["env"]["MAGNEMO_AGENT"] = a.agent
    data = {}
    if os.path.isfile(target):
        try:
            with open(target, encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"{target} is not valid JSON ({e.msg}) — fix it first; nothing written")
            sys.exit(1)
    servers = data.setdefault("mcpServers", {})
    if servers.get("magnemo") == entry:
        print(f"magnemo already registered in {target} — nothing to do")
        return
    servers["magnemo"] = entry
    with open(target, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    print(f"Registered MCP server 'magnemo' in {target}:")
    print(json.dumps({"magnemo": entry}, indent=2))
    print()
    print("Verify:  magnemo doctor")


def cmd_doctor(a):
    from . import doctor
    mounts = a.mount or ([".mcp.json"] if os.path.isfile(".mcp.json") else [])
    results = doctor.run(a.vault, mounts)
    ok = doctor.report(results)
    sys.exit(0 if ok else 1)


def cmd_bootpack(a):
    from . import bootpack, foresight
    g = _gov(a.vault)
    actor = a.actor or env("AGENT") or None
    if a.stdout:
        text = bootpack.generate(g.vault, a.cls, a.scope, actor=actor)
        foresight.log_cost(g.vault, "bootpack",
                           len(text.encode("utf-8")),
                           {"class": a.cls, "scope": a.scope or "all", "to": "stdout",
                            "actor": actor or ""})
        sys.stdout.write(text)
        return
    path, nbytes = bootpack.write(g.vault, a.cls, a.scope, a.out, actor=actor)
    print(f"BOOT_PACK.md written: {path} ({nbytes} bytes, class={a.cls}, "
          f"scope={a.scope or 'all'})")


def cmd_handoff(a):
    from . import handoff
    g = _gov(a.vault)
    if a.report:
        print(handoff.report_table(g.vault))
        return
    if a.usage is None or not a.trigger:
        print("handoff requires --usage <pct> and --trigger <wall|planned|compaction|other> (or --report)")
        sys.exit(2)
    body_extra = ""
    if getattr(a, "body_file", ""):
        with open(a.body_file, encoding="utf-8") as _f:
            body_extra = _f.read()
    e = handoff.record(g.vault, a.usage, a.trigger, a.cut or "",
                       actor=a.by, when=a.when or "", body_extra=body_extra)
    print(f"BOUNDARY RECORDED: {e['ts']} · {e['usage_pct']:g}% · {e['trigger']}")
    print(f"  telemetry → _ledger/handoffs.jsonl (append-only)")
    print(f"  handoff note staged → {e['note_id']}")


def cmd_cleartaint(a):
    g = _gov(a.vault)
    n = g.clear_taint(a.note_id, a.by, a.reason)
    print(f"taint cleared on {n.id} — lineage trusted again")


def cmd_autonomy(a):
    from . import trust
    g = _gov(a.vault)
    card = trust.scorecard(g.vault, a.actor, as_of=a.as_of or None)
    if a.json:
        print(json.dumps(card, indent=2, sort_keys=True))
    else:
        print(trust.render_scorecard(card))


def cmd_trust(a):
    from . import trust
    g = _gov(a.vault)
    if a.sub == "record":
        e = trust.record(g.vault, a.actor, a.klass, a.kind, by=a.by,
                         reason=a.reason or "", ref=a.ref or "", when=a.when or "",
                         grant=a.grant or "")
        print(f"TRUST EVENT RECORDED: {e['ts']} · {e['actor']} · {e['class']} · {e['kind']} · by {e['by']}"
              + (f" · ref {e['ref']}" if e['ref'] else ""))
        if a.kind == "violation":
            print(f"  ⚠ {a.actor} is now FROZEN (L0) in {a.klass} until a keyholder records `reinstate`.")
        return
    if a.sub == "events":
        es = trust.events(g.vault, a.actor or None, a.klass or None)
        if not es:
            print("No trust events on record.")
            return
        for e in es:
            print(f"{e['ts']}  {e.get('subject',''):<16} {e.get('class',''):<14} {e.get('kind',''):<10} "
                  f"by {e.get('actor','')}" + (f"  [{e['ref']}]" if e.get("ref") else "")
                  + (f"  {e['detail']}" if e.get("detail") else ""))


def cmd_grant(a):
    from . import grants
    g = _gov(a.vault)
    rec = grants.issue(g.vault, a.grantee, a.classes.split(","), a.level, by=a.by,
                       scope=a.scope or "", conditions=a.condition or [], kind=a.kind,
                       ref=a.ref or "", expires=a.expires or "", reason=a.reason or "",
                       when=a.when or "")
    print(f"GRANT {rec['grant_id']} ISSUED: {rec['grantee']} → L{rec['level']} in "
          f"{', '.join(rec['classes'])} · {rec['kind']} · by {rec['grantor']}"
          + (f" · ref {rec['ref']}" if rec['ref'] else ""))
    print("  append-only → _ledger/trust_ledger.jsonl · effective = min(computed, granted)")


def cmd_revoke(a):
    from . import grants
    g = _gov(a.vault)
    r = grants.revoke(g.vault, a.grant_id, by=a.by, reason=a.reason, when=a.when or "")
    print(f"GRANT {r['grant_id']} REVOKED for {r['grantee']} by {r['by']}: {r['reason']}")


def cmd_grants(a):
    from . import grants
    g = _gov(a.vault)
    gs = grants.status(g.vault, as_of=a.as_of or None)
    if a.actor:
        gs = [x for x in gs if x["grantee"] == a.actor]
    if a.json:
        print(json.dumps(gs, indent=2, sort_keys=True))
    else:
        print(grants.render(gs))


def cmd_gates(a):
    from . import gates, trust
    g = _gov(a.vault)
    as_of = a.as_of or trust.now_iso()
    gm = gates.gate_map(g.vault, as_of)
    if a.json:
        print(json.dumps(gm, indent=2, sort_keys=True))
    else:
        print(gates.render(gm, as_of))


def cmd_ledger(a):
    g = _gov(a.vault)
    es = g.ledger.entries()
    if not es:
        print("Ledger empty.")
        return
    for e in es:
        print(f"{e['ts']}  {e['action_class']:16s} {e['verdict']:9s} by {e['actor']:12s} → {e['subject']}"
              + (f"  ({e['detail']})" if e.get("detail") else ""))
    rate, n = g.ledger.pass_rate("memory.promote")
    print(f"\nmemory.promote pass-rate: {rate:.0%} over {n} decision(s)")


def main():
    p = argparse.ArgumentParser(prog="magnemo")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init");    s.add_argument("vault", nargs="?", default=DEF); s.set_defaults(f=cmd_init)
    s = sub.add_parser("review");  s.add_argument("vault", nargs="?", default=DEF); s.add_argument("--batch", type=int, default=None, help="max notes this pass (default: config review.batch)"); s.set_defaults(f=cmd_review)
    s = sub.add_parser("flag");    s.add_argument("note_id"); s.add_argument("--by", required=True); s.add_argument("--reason", default=""); s.add_argument("vault", nargs="?", default=DEF); s.set_defaults(f=cmd_flag)
    s = sub.add_parser("rescore"); s.add_argument("vault", nargs="?", default=DEF); s.set_defaults(f=cmd_rescore)
    s = sub.add_parser("handoff"); s.add_argument("--usage", type=float, default=None, help="context usage percent at the boundary"); s.add_argument("--trigger", choices=["wall", "planned", "compaction", "other"], default=None); s.add_argument("--cut", default="", help="what was cut at the boundary"); s.add_argument("--body-file", dest="body_file", default="", help="a file whose text becomes the handoff note body (the boardroom's REV BLOCK)"); s.add_argument("--by", default="operator"); s.add_argument("--when", default="", help="ISO timestamp override for recording a KNOWN historical boundary"); s.add_argument("--report", action="store_true", help="print all recorded handoffs as a table"); s.add_argument("vault", nargs="?", default=DEF); s.set_defaults(f=cmd_handoff)
    s = sub.add_parser("bootpack"); s.add_argument("--scope", default=None, help="a partition this vault declares"); s.add_argument("--class", dest="cls", choices=["worker", "partner"], default="worker", help="worker (default) = the working read; partner = the fuller read: adds bootpack.partner_excerpts (e.g. the whole codex, the baton's roles section) and the codex relationship layer"); s.add_argument("--out", default=None, help="output path (default: <vault>/_index/BOOT_PACK.md)"); s.add_argument("--stdout", action="store_true", help="print the pack instead of writing the file"); s.add_argument("--actor", default="", help="booting actor: adds YOUR AUTONOMY (default: $MAGNEMO_AGENT)"); s.add_argument("vault", nargs="?", default=DEF); s.set_defaults(f=cmd_bootpack)
    s = sub.add_parser("show");    s.add_argument("note_id"); s.add_argument("vault", nargs="?", default=DEF); s.set_defaults(f=cmd_show)
    s = sub.add_parser("yes");     s.add_argument("fragment", nargs="?", default=""); s.add_argument("--all", action="store_true", help="promote the whole queue, one ledger entry per note"); s.add_argument("--by", default="", help="default: the first keyholder in trust.humans"); s.add_argument("--reason", default="", help="default: approved in chat"); s.add_argument("vault", nargs="?", default=DEF); s.set_defaults(f=cmd_yes)
    s = sub.add_parser("no");      s.add_argument("fragment"); s.add_argument("--reason", required=True, help="rejections teach — required"); s.add_argument("--by", default="", help="default: the first keyholder in trust.humans"); s.add_argument("vault", nargs="?", default=DEF); s.set_defaults(f=cmd_no)
    s = sub.add_parser("promote"); s.add_argument("note_id"); s.add_argument("--by", required=True); s.add_argument("--reason", default=""); s.add_argument("vault", nargs="?", default=DEF); s.set_defaults(f=cmd_promote)
    s = sub.add_parser("reject");  s.add_argument("note_id"); s.add_argument("--by", required=True); s.add_argument("--reason", required=True); s.add_argument("vault", nargs="?", default=DEF); s.set_defaults(f=cmd_reject)
    s = sub.add_parser("outcome"); s.add_argument("rid"); s.add_argument("verdict", choices=["approved","denied","failed"]); s.add_argument("--by", required=True); s.add_argument("--reason", default=""); s.add_argument("vault", nargs="?", default=DEF); s.set_defaults(f=cmd_outcome)
    s = sub.add_parser("cleartaint"); s.add_argument("note_id"); s.add_argument("--by", required=True); s.add_argument("--reason", required=True); s.add_argument("vault", nargs="?", default=DEF); s.set_defaults(f=cmd_cleartaint)
    s = sub.add_parser("autonomy"); s.add_argument("actor"); s.add_argument("--as-of", dest="as_of", default="", help="ISO timestamp to score at (default: now)"); s.add_argument("--json", action="store_true"); s.add_argument("vault", nargs="?", default=DEF); s.set_defaults(f=cmd_autonomy)
    s = sub.add_parser("trust");   ts = s.add_subparsers(dest="sub", required=True)
    t = ts.add_parser("record");   t.add_argument("actor"); t.add_argument("klass", metavar="class", choices=["read","stage","merge-code","promote-canon","publish"]); t.add_argument("kind", choices=["success","verified","halt","failure","denied","surprise","violation","reinstate"]); t.add_argument("--by", required=True); t.add_argument("--reason", default=""); t.add_argument("--ref", default="", help="PR number, note id, commit, ..."); t.add_argument("--when", default="", help="ISO timestamp for a KNOWN historical event"); t.add_argument("--grant", default="", help="grant id acted under (consumes a one-time grant)"); t.add_argument("vault", nargs="?", default=DEF)
    t = ts.add_parser("events");   t.add_argument("--actor", default=""); t.add_argument("--class", dest="klass", default=""); t.add_argument("vault", nargs="?", default=DEF)
    s.set_defaults(f=cmd_trust)
    s = sub.add_parser("grant");   s.add_argument("grantee"); s.add_argument("--classes", required=True, help="comma-separated action classes"); s.add_argument("--level", type=int, required=True); s.add_argument("--by", required=True, help="keyholder (config trust.humans)"); s.add_argument("--scope", default=""); s.add_argument("--condition", action="append", help="repeatable"); s.add_argument("--kind", choices=["standing","one-time"], default="standing"); s.add_argument("--ref", default="", help="e.g. P-01"); s.add_argument("--expires", default=""); s.add_argument("--reason", default=""); s.add_argument("--when", default="", help="ISO timestamp for a KNOWN historical grant"); s.add_argument("vault", nargs="?", default=DEF); s.set_defaults(f=cmd_grant)
    s = sub.add_parser("revoke");  s.add_argument("grant_id"); s.add_argument("--by", required=True); s.add_argument("--reason", required=True); s.add_argument("--when", default=""); s.add_argument("vault", nargs="?", default=DEF); s.set_defaults(f=cmd_revoke)
    s = sub.add_parser("grants");  s.add_argument("--actor", default=""); s.add_argument("--as-of", dest="as_of", default=""); s.add_argument("--json", action="store_true"); s.add_argument("vault", nargs="?", default=DEF); s.set_defaults(f=cmd_grants)
    s = sub.add_parser("gates");   s.add_argument("--as-of", dest="as_of", default=""); s.add_argument("--json", action="store_true"); s.add_argument("vault", nargs="?", default=DEF); s.set_defaults(f=cmd_gates)
    s = sub.add_parser("ledger");  s.add_argument("vault", nargs="?", default=DEF); s.set_defaults(f=cmd_ledger)
    s = sub.add_parser("costs");   s.add_argument("vault", nargs="?", default=DEF); s.set_defaults(f=cmd_costs)
    s = sub.add_parser("stage");   s.add_argument("title"); s.add_argument("--body", default=None, help="note body (or --file, or pipe via stdin)"); s.add_argument("--file", default=None, help="read the body from this file"); s.add_argument("--partition", required=True, help="a partition this vault declares"); s.add_argument("--store", required=True); s.add_argument("--source", required=True, help="provenance: run id / audit id / where this came from (mandatory)"); s.add_argument("--author", default="", help="default: $MAGNEMO_AGENT, else 'founder'"); s.add_argument("--tags", default=""); s.add_argument("--impact", choices=["security", "money", "correctness", "process", "info"], default="info"); s.add_argument("--supersedes", default=""); s.add_argument("--taint", default="", help="REQUIRED labelling when content came from an untrusted source"); s.add_argument("vault", nargs="?", default=DEF); s.set_defaults(f=cmd_stage)
    s = sub.add_parser("inbox");   s.add_argument("--dir", default="", help="the drop folder (default: config inbox.dir)"); s.add_argument("--as", dest="tag", default=None, help="author tag: boardroom-session | founder | cc (default: $MAGNEMO_AGENT)"); s.add_argument("vault", nargs="?", default=DEF); s.set_defaults(f=cmd_inbox)
    s = sub.add_parser("guard");   s.add_argument("--off", action="store_true", help="lower the wall (human verb, ledgered)"); s.add_argument("--status", action="store_true"); s.add_argument("--reason", default=""); s.add_argument("--by", default=""); s.add_argument("vault", nargs="?", default=DEF); s.set_defaults(f=cmd_guard)
    s = sub.add_parser("restore"); s.add_argument("target", help="a render path (relative to the render root) or a note id"); s.add_argument("--to", default="latest", help="archived version (ts prefix or sha12); default latest"); s.add_argument("--versions", action="store_true", help="list archived versions"); s.add_argument("--by", default=""); s.add_argument("vault", nargs="?", default=DEF); s.set_defaults(f=cmd_restore)
    s = sub.add_parser("room");    rs_ = s.add_subparsers(dest="sub", required=True)
    for verb, extra in (("open", ("room", "--seats")), ("say", ("room", "body", "--class", "--to", "--reply-to", "--about")), ("connect", ("room", "seat")), ("separate", ("room", "seat", "--reason")), ("watch", ("room", "--follow")), ("close", ("room",)), ("replay", ("room",)), ("list", ())):
        r_ = rs_.add_parser(verb)
        for arg in extra:
            if arg == "--seats": r_.add_argument("--seats", required=True, help="comma list of agent seats; the human seat is added if absent and can never be removed")
            elif arg == "--class": r_.add_argument("--class", dest="cls", choices=["report", "proposal", "question", "alert"], default="report")
            elif arg == "--to": r_.add_argument("--to", default="")
            elif arg == "--reply-to": r_.add_argument("--reply-to", dest="reply_to", default="", help="note id this replies to (taint is inherited)")
            elif arg == "--about": r_.add_argument("--about", default="", help="a staged note id this message proposes about")
            elif arg == "--reason": r_.add_argument("--reason", default="")
            elif arg == "--follow": r_.add_argument("--follow", action="store_true")
            else: r_.add_argument(arg)
        r_.add_argument("--by", default="", help="who is speaking/acting (default: $MAGNEMO_AGENT)"); r_.add_argument("vault", nargs="?", default=DEF)
    s.set_defaults(f=cmd_room)
    s = sub.add_parser("run");     s.add_argument("task", nargs="?", default=""); s.add_argument("--engine", choices=["claude", "codex", "gemini"], default="claude", help="claude = the Claude Agent SDK through your own login (the sanctioned door). codex/gemini: not wired yet"); s.add_argument("--schedule", default="", help="5-field cron: writes a RAIL.md row and installs a launchd (macOS) / cron job"); s.add_argument("--cap-turns", dest="cap_turns", type=int, default=None); s.add_argument("--cap-usd", dest="cap_usd", type=float, default=None); s.add_argument("--trigger", choices=["manual", "schedule"], default="manual"); s.add_argument("--card", action="store_true", help="the value receipt: runs this month · tokens · API list-price avoided"); s.add_argument("--unschedule", default="", help="remove a scheduled job by label"); s.add_argument("vault", nargs="?", default=DEF); s.set_defaults(f=cmd_run)
    s = sub.add_parser("chest");   cs = s.add_subparsers(dest="sub", required=True)
    c = cs.add_parser("add");      c.add_argument("kind", choices=["git", "path"], help="git = a git remote you own · path = a folder you own"); c.add_argument("target"); c.add_argument("--branch", default="main"); c.add_argument("--label", default=""); c.add_argument("vault", nargs="?", default=DEF)
    c = cs.add_parser("status");   c.add_argument("vault", nargs="?", default=DEF)
    c = cs.add_parser("push");     c.add_argument("--reason", default="manual"); c.add_argument("--label", default=None, help="one destination only (default: all)"); c.add_argument("--no-sweep", dest="no_sweep", action="store_true", help="HUMAN ONLY, per push, ledgered: skip the secret sweep"); c.add_argument("--by", default="", help="who is disabling the sweep"); c.add_argument("vault", nargs="?", default=DEF)
    c = cs.add_parser("tick");     c.add_argument("vault", nargs="?", default=DEF)
    s.set_defaults(f=cmd_chest)
    s = sub.add_parser("mount");   s.add_argument("--from", dest="src", default="", help="restore a vault from a copy (git URL or folder) into an EMPTY vault path first"); s.add_argument("--file", default=".mcp.json", help="MCP config to write (default: .mcp.json)"); s.add_argument("--agent", default="", help="agent name recorded on this mount (default: server default)"); s.add_argument("vault", nargs="?", default=DEF); s.set_defaults(f=cmd_mount)
    s = sub.add_parser("doctor");  s.add_argument("--mount", action="append", help="repeatable: a .mcp.json (or its folder) to validate"); s.add_argument("vault", nargs="?", default=DEF); s.set_defaults(f=cmd_doctor)

    a = p.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
