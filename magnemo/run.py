"""magnemo.run — THE SUBSCRIPTION SOCKET v0: run your agents on the plan you already pay for.

POLICY, IN CODE: the sanctioned door is the Claude Agent SDK, which drives the
user's own Claude Code login. This module never reads, stores, or forwards a
token — the SDK owns auth. No API key of ours exists here. `codex` and `gemini`
are documented stubs that refuse until wired.

A run = an Agent SDK session with the current vault mounted (our four verbs as
MCP tools). Every engine action is STAGED with provenance (agent run-<id>). The
session's usage / plan-limit signal is read and printed as the FUEL line. A cap
exit says why, never silently.
"""
from __future__ import annotations
import os, sys, json, re, hashlib, shutil, subprocess, datetime
from .vault import Vault, now_iso

ENGINES = ("claude", "codex", "gemini")
RUNS_REL = "_ledger/runs.jsonl"
FOUR = ("mcp__magnemo__retrieve", "mcp__magnemo__stage", "mcp__magnemo__bootpack", "mcp__magnemo__handoff")
PRICING_URL = "https://docs.anthropic.com/en/docs/about-claude/pricing"


class RunError(Exception):
    pass


def _runs_path(root):
    return os.path.join(root, RUNS_REL)


def _append(root, e):
    os.makedirs(os.path.dirname(_runs_path(root)), exist_ok=True)
    e = dict(e); e.setdefault("ts", now_iso())
    with open(_runs_path(root), "a", encoding="utf-8") as f:
        f.write(json.dumps(e, sort_keys=True) + "\n")
    return e


def entries(root):
    p = _runs_path(root)
    if not os.path.isfile(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def new_run_id(task: str) -> str:
    return datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S") + "-" + hashlib.sha256(task.encode()).hexdigest()[:6]


def claude_engine(task: str, opts: dict):
    """The real door: the Claude Agent SDK. Yields plain event dicts."""
    try:
        import anyio
        from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, ResultMessage, ToolUseBlock
        try:
            from claude_agent_sdk import RateLimitEvent
        except ImportError:
            RateLimitEvent = None
    except ImportError:
        raise RunError("The Claude Agent SDK is not installed. It is an optional extra — install it with:\n"
                       "    pip install 'magnemo[claude]'\n"
                       "It signs in through your own Claude Code login (the sanctioned door). Magnemo never stores a token.")
    options = ClaudeAgentOptions(
        mcp_servers={"magnemo": {"type": "stdio", "command": sys.executable, "args": ["-m", "magnemo.mcp"], "env": opts["env"]}},
        allowed_tools=list(FOUR) + ["Read", "Glob", "Grep"],
        permission_mode="dontAsk",
        max_turns=opts.get("cap_turns"),
        max_budget_usd=opts.get("cap_usd"),
        cwd=opts.get("cwd"),
        system_prompt={"type": "preset", "preset": "claude_code", "append":
                       "You are running under Magnemo governance. Your memory is the mounted vault: call mcp__magnemo__bootpack first, "
                       "mcp__magnemo__retrieve before acting, and mcp__magnemo__stage to record findings — staging is your ONLY write. "
                       "You cannot promote, grant, or change trust; a human reviews what you stage."},
    )
    events = []

    async def go():
        async for m in query(prompt=task, options=options):
            if isinstance(m, AssistantMessage):
                for b in m.content:
                    if isinstance(b, ToolUseBlock):
                        events.append({"type": "tool_use", "name": b.name})
            elif RateLimitEvent is not None and isinstance(m, RateLimitEvent):
                i = m.rate_limit_info
                events.append({"type": "rate_limit", "status": getattr(i, "status", None), "kind": getattr(i, "rate_limit_type", None),
                               "utilization": getattr(i, "utilization", None), "resets_at": getattr(i, "resets_at", None)})
            elif isinstance(m, ResultMessage):
                u = m.usage or {}
                events.append({"type": "result", "subtype": m.subtype, "is_error": m.is_error, "turns": m.num_turns,
                               "duration_ms": m.duration_ms, "cost_usd": m.total_cost_usd,
                               "tokens_in": (u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0)),
                               "tokens_out": u.get("output_tokens", 0), "result": (m.result or "")[:400],
                               "stop_reason": getattr(m, "stop_reason", None), "terminal_reason": getattr(m, "terminal_reason", None)})
    anyio.run(go)
    return events


def stub_engine(name):
    def _engine(task, opts):
        raise RunError(f"{name}: not wired yet. The socket is engine-agnostic by construction — {name} will be a config change, "
                       "not a rebuild — but only --engine claude is live in this release.")
    return _engine


ENGINE_FN = {"claude": claude_engine, "codex": stub_engine("codex"), "gemini": stub_engine("gemini")}


def plain_engine_error(e: Exception) -> str:
    s = str(e)
    low = s.lower()
    if "oauth" in low or "authenticate" in low or "login" in low:
        return ("Claude Code's login on this machine has expired or is missing. Sign in once — run `claude` (or `claude login`) "
                "in a terminal — and run again. Magnemo never stores your token, so it cannot refresh it for you; the SDK owns auth.")
    if "not found" in low and "claude" in low:
        return "the `claude` command was not found on PATH — install Claude Code, then run again."
    if "rate" in low and "limit" in low:
        return "your plan's limit stopped the session — wait for the window to reset, then run again."
    return f"{type(e).__name__}: {s[:220]}"


def fuel_line(res: dict, rl) -> str:
    base = (f"FUEL: {res.get('tokens_in', 0):,} in · {res.get('tokens_out', 0):,} out tokens · {res.get('turns', 0)} turns · "
            f"{(res.get('duration_ms') or 0) / 1000:.1f}s · list-price ${(res.get('cost_usd') or 0):.4f}")
    if rl:
        util = rl.get("utilization")
        pct = f"{util * 100:.0f}% used" if isinstance(util, (int, float)) else "usage not given"
        return base + f" · plan window ({rl.get('kind')}): {rl.get('status')}, {pct}" + (f", resets {rl['resets_at']}" if rl.get("resets_at") else "")
    return base + " · plan window: not reported by the SDK this run"


def exit_reason(res: dict, rl, cap_turns, cap_usd) -> str:
    if rl and rl.get("status") == "rejected":
        return f"plan cap reached ({rl.get('kind')}) — the session was stopped by your plan's limit" + (f"; resets {rl['resets_at']}" if rl.get("resets_at") else "")
    st = (res.get("subtype") or "")
    if "max_turns" in st or (cap_turns and res.get("turns", 0) >= cap_turns):
        return f"turn cap reached ({cap_turns} turns) — stopped by the cap you set"
    if "budget" in st or (cap_usd and (res.get("cost_usd") or 0) >= cap_usd):
        return f"budget cap reached (${cap_usd}) — stopped by the cap you set"
    if res.get("is_error"):
        return f"engine error: {st or 'unknown'} — {res.get('result', '')[:200]}"
    return "completed"


def run(root: str, task: str, engine: str = "claude", cap_turns=None, cap_usd=None,
        trigger: str = "manual", engine_fn=None, cwd=None) -> dict:
    root = os.path.abspath(root)
    v = Vault(root)
    if not v.exists():
        raise RunError(f"No vault at {root}. Run: magnemo init")
    if engine not in ENGINES:
        raise RunError(f"--engine must be one of {', '.join(ENGINES)}")
    rid = new_run_id(task)
    agent = f"run-{rid}"
    _append(root, {"kind": "RUN_START", "run_id": rid, "task": task, "engine": engine, "trigger": trigger,
                   "cap_turns": cap_turns, "cap_usd": cap_usd, "agent": agent})
    fn = engine_fn or ENGINE_FN[engine]
    env = {"MAGNEMO_VAULT": root, "MAGNEMO_AGENT": agent}
    try:
        events = fn(task, {"env": env, "cap_turns": cap_turns, "cap_usd": cap_usd, "cwd": cwd or os.getcwd()})
    except RunError as e:
        _append(root, {"kind": "RUN_END", "run_id": rid, "exit_reason": f"refused: {e}", "engine": engine, "trigger": trigger})
        raise
    except Exception as e:  # noqa: BLE001 — the engine failed; say why, ledger it, never a bare traceback
        reason = plain_engine_error(e)
        _append(root, {"kind": "RUN_END", "run_id": rid, "task": task, "engine": engine, "trigger": trigger,
                       "exit_reason": f"engine error: {reason}", "engine_actions": 0, "staged_notes": []})
        raise RunError(f"The run could not start or finish — {reason}") from None
    res = next((e for e in events if e.get("type") == "result"), {})
    rl = next((e for e in reversed(events) if e.get("type") == "rate_limit"), None)
    actions = [e["name"] for e in events if e.get("type") == "tool_use"]
    staged_calls = sum(1 for a in actions if a == "mcp__magnemo__stage")
    staged_notes = [n.id for n in v.staged() if n.status == "staged" and n.author == agent]
    reason = exit_reason(res, rl, cap_turns, cap_usd)
    end = _append(root, {"kind": "RUN_END", "run_id": rid, "task": task, "engine": engine, "trigger": trigger,
                         "tokens_in": res.get("tokens_in", 0), "tokens_out": res.get("tokens_out", 0),
                         "cost_usd": res.get("cost_usd") or 0.0, "turns": res.get("turns", 0), "duration_ms": res.get("duration_ms", 0),
                         "engine_actions": len(actions), "stage_calls": staged_calls, "staged_notes": staged_notes,
                         "rate_limit": rl, "exit_reason": reason, "fuel": fuel_line(res, rl)})
    from . import chest
    chest.notify(root, "receipt")   # a finished run is a receipt: the chest conducts a copy (per its triggers)
    return {"run_id": rid, "agent": agent, "fuel": end["fuel"], "exit_reason": reason, "staged_notes": staged_notes,
            "engine_actions": len(actions), "result": res.get("result", ""), "end": end}


def card(root: str) -> str:
    month = datetime.datetime.utcnow().strftime("%Y-%m")
    runs = [e for e in entries(root) if e.get("kind") == "RUN_END" and e.get("ts", "").startswith(month) and not str(e.get("exit_reason", "")).startswith("refused")]
    tin = sum(int(e.get("tokens_in", 0)) for e in runs); tout = sum(int(e.get("tokens_out", 0)) for e in runs)
    usd = sum(float(e.get("cost_usd") or 0) for e in runs)
    return (f"runs this month: {len(runs)} · tokens: {tin + tout:,} ({tin:,} in / {tout:,} out) · API list-price avoided: ${usd:.2f}\n"
            f"(list price = the SDK's own per-run cost at published rates, {PRICING_URL}; these runs drew from your plan, not an API key)")


def cron_to_calendar(cron: str) -> dict:
    parts = cron.split()
    if len(parts) != 5:
        raise RunError('--schedule takes a 5-field cron expression, e.g. "0 9 * * 1" (minute hour day month weekday).')
    names = ("Minute", "Hour", "Day", "Month", "Weekday")
    cal = {}
    for name, p in zip(names, parts):
        if p == "*":
            continue
        if not re.fullmatch(r"\d{1,2}", p):
            raise RunError(f"--schedule: the {name.lower()} field '{p}' is not supported yet — v0 takes a single number or * per field "
                           '(ranges and lists come later). Plain example: "0 9 * * *" = every day at 09:00.')
        cal[name] = int(p)
    return cal


def plain_schedule(cron: str) -> str:
    cal = cron_to_calendar(cron)
    when = f"{cal.get('Hour', 0):02d}:{cal.get('Minute', 0):02d}"
    days = {0: "Sunday", 1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday", 7: "Sunday"}
    if "Weekday" in cal:
        return f"every {days.get(cal['Weekday'], cal['Weekday'])} at {when}"
    if "Day" in cal:
        return f"on day {cal['Day']} of each month at {when}"
    if "Hour" in cal:
        return f"every day at {when}"
    if "Minute" in cal:
        return f"every hour at minute {cal['Minute']}"
    return "every minute"


def rail_path(root: str) -> str:
    from .config import load_config
    rr = (load_config(root).get("render") or {}).get("root", "")
    return os.path.normpath(os.path.join(root, rr, "RAIL.md")) if rr else os.path.join(root, "RAIL.md")


def _xml(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def plist_text(label: str, cmd: list, cal: dict, root: str, logdir: str) -> str:
    path_env = os.environ.get("PATH", "/usr/bin:/bin") + ":" + os.path.dirname(shutil.which("claude") or "/usr/local/bin/claude")
    L = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">',
         '<plist version="1.0"><dict>',
         f'  <key>Label</key><string>{label}</string>',
         '  <key>ProgramArguments</key><array>']
    L += [f'    <string>{_xml(c)}</string>' for c in cmd]
    L += ['  </array>', '  <key>StartCalendarInterval</key><dict>']
    L += [f'    <key>{k}</key><integer>{v}</integer>' for k, v in cal.items()]
    L += ['  </dict>',
          f'  <key>EnvironmentVariables</key><dict><key>PATH</key><string>{_xml(path_env)}</string><key>MAGNEMO_VAULT</key><string>{_xml(root)}</string></dict>',
          f'  <key>StandardOutPath</key><string>{_xml(os.path.join(logdir, label + ".out.log"))}</string>',
          f'  <key>StandardErrorPath</key><string>{_xml(os.path.join(logdir, label + ".err.log"))}</string>',
          '</dict></plist>', '']
    return "\n".join(L)


def schedule(root: str, task: str, cron: str, engine: str = "claude", cap_turns=None, cap_usd=None,
             install: bool = True, agents_dir=None) -> dict:
    root = os.path.abspath(root)
    cal = cron_to_calendar(cron)
    slug = re.sub(r"[^a-z0-9]+", "-", task.lower()).strip("-")[:32] or "task"
    label = f"com.magnemo.run.{slug}"
    rp = rail_path(root)
    header = "# RAIL — scheduled runs (plain speech; every run stages, a human promotes)\n\n| trigger | agent | task | cap | approval grain |\n|---|---|---|---|---|\n"
    cap = " · ".join(x for x in ((f"{cap_turns} turns" if cap_turns else ""), (f"${cap_usd}" if cap_usd else "")) if x) or "plan limit only"
    row = f"| {plain_schedule(cron)} (`{cron}`) | run-{slug} · engine {engine} | {task} | {cap} | staged only — a human promotes |\n"
    os.makedirs(os.path.dirname(rp), exist_ok=True)
    existing = open(rp, encoding="utf-8").read() if os.path.isfile(rp) else ""
    with open(rp, "w", encoding="utf-8") as f:
        f.write((existing if existing.startswith("# RAIL") else header + existing) + row)
    cmd = [sys.executable, "-m", "magnemo.cli", "run", task, "--engine", engine, "--trigger", "schedule", root]
    if cap_turns:
        cmd += ["--cap-turns", str(cap_turns)]
    if cap_usd:
        cmd += ["--cap-usd", str(cap_usd)]
    out = {"label": label, "rail": rp, "plain": plain_schedule(cron), "installed": False, "kind": None}
    logdir = os.path.join(root, "_index", "rail"); os.makedirs(logdir, exist_ok=True)
    if sys.platform == "darwin":
        agents = agents_dir or os.path.expanduser("~/Library/LaunchAgents")
        os.makedirs(agents, exist_ok=True)
        plist = os.path.join(agents, label + ".plist")
        with open(plist, "w", encoding="utf-8") as f:
            f.write(plist_text(label, cmd, cal, root, logdir))
        out.update(kind="launchd", plist=plist)
        if install:
            uid = os.getuid()
            subprocess.run(["launchctl", "bootout", f"gui/{uid}/{label}"], capture_output=True)
            r = subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", plist], capture_output=True, text=True)
            out["installed"] = r.returncode == 0
            out["install_note"] = (r.stderr or r.stdout).strip()
    else:
        line = f"{cron} {' '.join(json.dumps(c) if ' ' in c else c for c in cmd)} >> {os.path.join(logdir, label + '.log')} 2>&1  # {label}"
        out.update(kind="cron", line=line)
        if install:
            cur = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
            cur = "\n".join(l for l in cur.splitlines() if label not in l)
            r = subprocess.run(["crontab", "-"], input=(cur + "\n" + line + "\n").lstrip("\n"), text=True, capture_output=True)
            out["installed"] = r.returncode == 0
    _append(root, {"kind": "RUN_SCHEDULED", "label": label, "task": task, "cron": cron, "plain": out["plain"], "engine": engine,
                   "cap_turns": cap_turns, "cap_usd": cap_usd, "installed": out["installed"], "scheduler": out["kind"]})
    return out


def unschedule(root: str, label: str, agents_dir=None) -> bool:
    root = os.path.abspath(root)
    if sys.platform == "darwin":
        agents = agents_dir or os.path.expanduser("~/Library/LaunchAgents")
        plist = os.path.join(agents, label + ".plist")
        subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{label}"], capture_output=True)
        if os.path.isfile(plist):
            os.remove(plist)
    else:
        cur = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
        subprocess.run(["crontab", "-"], input="\n".join(l for l in cur.splitlines() if label not in l) + "\n", text=True, capture_output=True)
    rp = rail_path(root)
    slug = label.split(".")[-1]
    if os.path.isfile(rp):
        rows = open(rp, encoding="utf-8").read().splitlines()
        kept = [r for r in rows if f"run-{slug} " not in r]
        with open(rp, "w", encoding="utf-8") as f:
            f.write("\n".join(kept) + "\n")
    _append(root, {"kind": "RUN_UNSCHEDULED", "label": label})
    return True
