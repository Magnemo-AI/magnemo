"""Tests for magnemo.mcp — the four-verb MCP server.

B1: the scaffold lists exactly four tools and completes the stdio handshake.
B2: each verb is bound to its existing code; the invariants hold.
B3: the four cascades fire deterministically, with zero model calls.
"""
import os, sys, json, shutil, tempfile, unittest, subprocess
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from magnemo.vault import Vault
from magnemo.governance import Governance
from magnemo import mcp, foresight, handoff

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOUR = ["retrieve", "stage", "bootpack", "handoff"]


def make_server(vault_dir, **env):
    """Construct a MemoryServer against a temp vault with the given env."""
    saved = {k: os.environ.get(k) for k in ("MAGNEMO_VAULT", "MAGNEMO_AGENT", "MAGNEMO_PARTITIONS", "MAGNEMO_SCOPE")}
    for k in saved:
        os.environ.pop(k, None)
    os.environ["MAGNEMO_VAULT"] = vault_dir
    os.environ.update(env)
    try:
        return mcp.MemoryServer()
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def call(server, name, **args):
    """Drive tools/call through the JSON-RPC handler; return (text, isError)."""
    resp = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                          "params": {"name": name, "arguments": args}})
    if "error" in resp:
        return resp["error"]["message"], True
    r = resp["result"]
    return r["content"][0]["text"], r["isError"]


class TestScaffold(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.v = Vault(self.dir); self.v.init()
        self.s = make_server(self.dir)

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_lists_exactly_four_tools(self):
        resp = self.s.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = [t["name"] for t in resp["result"]["tools"]]
        self.assertEqual(names, FOUR)
        for t in resp["result"]["tools"]:
            self.assertIn("inputSchema", t)
            self.assertTrue(t["description"])

    def test_promotion_is_not_a_tool(self):
        names = {t["name"] for t in self.s.tools_spec()}
        for forbidden in ("promote", "reject", "memory_promote", "eval", "exec", "shell", "bash"):
            self.assertNotIn(forbidden, names)

    def test_legacy_and_private_methods_are_not_callable(self):
        # least privilege: inherited legacy verbs exist on the class but are NOT declared → not callable
        for name in ("memory_write", "memory_search", "memory_read", "memory_list_staged",
                     "memory_provenance", "unbound", "_unbound"):
            text, err = call(self.s, name)
            self.assertTrue(err, name)
            self.assertIn("unknown tool", text)

    def test_initialize_handshake(self):
        resp = self.s.handle({"jsonrpc": "2.0", "id": 0, "method": "initialize",
                              "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                         "clientInfo": {"name": "t", "version": "0"}}})
        self.assertEqual(resp["result"]["serverInfo"]["name"], "magnemo")
        self.assertIn("tools", resp["result"]["capabilities"])
        self.assertIsNone(self.s.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))


class TestStdioTransport(unittest.TestCase):
    """The real thing: spawn the server as a subprocess and speak MCP over stdio."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        Vault(self.dir).init()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_connect_and_list_over_stdio(self):
        env = dict(os.environ, MAGNEMO_VAULT=self.dir, MAGNEMO_AGENT="stdio-test")
        msgs = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                        "clientInfo": {"name": "test", "version": "0"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "ping"},
        ]
        p = subprocess.run([sys.executable, "-m", "magnemo.mcp"],
                           input="".join(json.dumps(m) + "\n" for m in msgs),
                           capture_output=True, text=True, cwd=ROOT, env=env, timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        out = [json.loads(l) for l in p.stdout.splitlines() if l.strip()]
        self.assertEqual([o["id"] for o in out], [1, 2, 3])  # notification gets no reply
        self.assertEqual(out[0]["result"]["serverInfo"]["name"], "magnemo")
        self.assertEqual([t["name"] for t in out[1]["result"]["tools"]], FOUR)
        self.assertEqual(out[2]["result"], {})
        # stdout is pure JSON-RPC; diagnostics go to stderr
        self.assertIn("tools=retrieve,stage,bootpack,handoff", p.stderr)


def promote(vault, title, body, partition, store, tags="", impact="info", source="seed"):
    """Test fixture: the HUMAN path to canon (governance.promote) — never an MCP tool."""
    g = Governance(vault)
    n = g.agent_write(title=title, body=body, partition=partition, store=store,
                      author="seed", source=source, tags=tags, impact=impact)
    g.promote(n.id, "founder", "fixture")
    return n


def canon_files(vault_dir):
    out = []
    for p in ("dev", "ops", "shared"):
        for base, _d, files in os.walk(os.path.join(vault_dir, p)):
            out += sorted(os.path.join(base, f) for f in files if f.endswith(".md"))
    return out


GOOD_NOTE = {"title": "Kwik Lube month-end spike",
             "body": "Volumes spike ~35% in the last week of each month. 7 occurrences.",
             "partition": "ops", "store": "knowledge", "impact": "money"}
GOOD_PROV = {"source": "run#1847"}


class TestBindings(unittest.TestCase):
    """B2: each verb reaches its existing implementation and returns what it promises."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.v = Vault(self.dir); self.v.init()
        self.s = make_server(self.dir, MAGNEMO_AGENT="ops-agent")

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_stage_lands_in_staging_with_provenance_and_salience(self):
        text, err = call(self.s, "stage", note=GOOD_NOTE, provenance=GOOD_PROV)
        self.assertFalse(err, text)
        r = json.loads(text)
        n = self.v.read(r["staged"])
        self.assertEqual(n.status, "staged")
        self.assertTrue(os.path.exists(os.path.join(self.dir, "_staging", n.id + ".md")))
        self.assertEqual((n.author, n.source, n.impact), ("ops-agent", "run#1847", "money"))
        self.assertGreater(n.salience, 0)                       # KAIROS ran at stage time
        self.assertEqual(r["salience"], n.salience)
        self.assertIn("consequence", r["salience_components"])
        self.assertIsNone(r["duplicate_of"])

    def test_stage_author_override_and_taint_passthrough(self):
        text, err = call(self.s, "stage", note=dict(GOOD_NOTE, taint="inbound-email"),
                         provenance={"source": "gate#7", "author": "relay"})
        r = json.loads(text)
        n = self.v.read(r["staged"])
        # P-54 · provenance enforced at the door: the seat signs; the caller's name is a claim, kept beside it
        self.assertEqual((n.author, n.extra.get("claimed_author"), n.taint), (self.s.agent, "relay", "inbound-email"))

    def test_retrieve_returns_pointers_and_snippets_with_receipt(self):
        promote(self.v, "Kwik Lube month-end spike", "Volumes spike 35% in the last week of each month.",
                "ops", "knowledge")
        text, err = call(self.s, "retrieve", query="month-end spike")
        self.assertFalse(err, text)
        r = json.loads(text)
        self.assertEqual(r["served"], 1)
        hit = r["results"][0]
        self.assertTrue(hit["pointer"].startswith("mn://ops/knowledge/"))
        self.assertIn("snippet", hit)
        self.assertEqual(r["rendition"], "snippet")
        self.assertFalse(r["truncated"])
        self.assertTrue(r["rid"])
        with open(os.path.join(self.dir, "_ledger", "retrievals.jsonl")) as f:
            self.assertIn(r["rid"], f.read())                    # retrieval receipt written

    def test_retrieve_excludes_staged(self):
        call(self.s, "stage", note=GOOD_NOTE, provenance=GOOD_PROV)
        r = json.loads(call(self.s, "retrieve", query="month-end spike")[0])
        self.assertEqual(r["served"], 0)
        self.assertIn("Staged notes are excluded", r["note"])

    def test_retrieve_snippet_is_not_a_raw_dump(self):
        promote(self.v, "Long note", "spike " * 2000, "ops", "knowledge")
        r = json.loads(call(self.s, "retrieve", query="spike", budget=32000)[0])
        self.assertLessEqual(len(r["results"][0]["snippet"]), mcp.SNIPPET_CHARS + 1)

    def test_bootpack_binds_to_generator(self):
        from magnemo import bootpack
        text, err = call(self.s, "bootpack")
        self.assertFalse(err, text)
        self.assertEqual(text, bootpack.generate(self.v, "worker", None, actor="ops-agent"))  # MCP packs carry the agent's own scorecard (P-02 B4)
        self.assertTrue(text.startswith("# BOOT PACK — magnemo · worker boot"))
        self.assertIn("## THE CHARTER", text)
        partner, _ = call(self.s, "bootpack", **{"class": "partner", "scope": "ops"})
        self.assertIn("partner boot · scope: ops", partner)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "_index", "BOOT_PACK.md")))  # MCP never writes _index

    def test_handoff_binds_to_record(self):
        text, err = call(self.s, "handoff", usage=88, trigger="planned", cut="deferred B4")
        self.assertFalse(err, text)
        r = json.loads(text)
        es = handoff.entries(self.v)
        self.assertEqual(len(es), 1)
        self.assertEqual(es[0], r["recorded"])
        self.assertEqual((es[0]["usage_pct"], es[0]["trigger"], es[0]["cut"], es[0]["actor"]),
                         (88.0, "planned", "deferred B4", "ops-agent"))
        n = self.v.read(es[0]["note_id"])
        self.assertEqual(n.status, "staged")
        self.assertIn("handoff", n.tags)

    def test_handoff_validation_surfaces_as_tool_error(self):
        for bad in ({"usage": 101, "trigger": "wall"}, {"usage": 50, "trigger": "panic"}, {"usage": 50}):
            text, err = call(self.s, "handoff", **bad)
            self.assertTrue(err, bad)
            self.assertTrue(text.startswith("ERROR"), text)
        self.assertEqual(handoff.entries(self.v), [])


class TestInvariants(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.v = Vault(self.dir); self.v.init()

    def tearDown(self):
        shutil.rmtree(self.dir)

    # -- staging is the only write path --
    def test_staging_is_the_only_note_write_path(self):
        promote(self.v, "Existing canon", "ops canon body", "ops", "knowledge")
        before = canon_files(self.dir)
        s = make_server(self.dir)
        for name, args in (("stage", dict(note=GOOD_NOTE, provenance=GOOD_PROV)),
                           ("handoff", dict(usage=90, trigger="planned")),
                           ("bootpack", {}), ("retrieve", dict(query="canon"))):
            text, err = call(s, name, **args)
            self.assertFalse(err, (name, text))
        self.assertEqual(canon_files(self.dir), before)          # canon byte-for-byte same set
        staged = [n for n in self.v.staged() if n.status == "staged"]
        self.assertEqual(len(staged), 2)                         # stage + handoff note, nothing else
        for n in staged:
            self.assertEqual(n.status, "staged")
        # and there is no verb that could move them: promotion is CLI-only
        text, err = call(s, "promote", id=staged[0].id)
        self.assertTrue(err); self.assertIn("unknown tool", text)

    # -- provenance mandatory --
    def test_paperless_and_malformed_notes_refused(self):
        s = make_server(self.dir)
        cases = [
            dict(note=GOOD_NOTE),                                         # no provenance
            dict(note=GOOD_NOTE, provenance={}),                          # empty provenance
            dict(note=GOOD_NOTE, provenance={"source": "   "}),           # blank source
            dict(note=GOOD_NOTE, provenance="run#1"),                     # wrong type
            dict(note=dict(GOOD_NOTE, title=""), provenance=GOOD_PROV),   # no title
            dict(note=dict(GOOD_NOTE, body=" "), provenance=GOOD_PROV),   # no body
            dict(note=dict(GOOD_NOTE, store="clients-x"), provenance=GOOD_PROV),  # bad store
            dict(note=dict(GOOD_NOTE, partition="hr"), provenance=GOOD_PROV),     # bad partition
            dict(note="just text", provenance=GOOD_PROV),
        ]
        for args in cases:
            text, err = call(s, "stage", **args)
            self.assertTrue(err, args)
            self.assertRegex(text, r"REFUSED|ERROR")
        self.assertEqual(os.listdir(os.path.join(self.dir, "_staging")), [])  # nothing landed

    def test_write_partition_wall(self):
        s = make_server(self.dir, MAGNEMO_PARTITIONS="dev")
        text, err = call(s, "stage", note=GOOD_NOTE, provenance=GOOD_PROV)   # ops note
        self.assertTrue(err); self.assertIn("DENIED", text)
        self.assertEqual(os.listdir(os.path.join(self.dir, "_staging")), [])

    # -- scope walls hold --
    def test_dev_scope_cannot_see_ops_only(self):
        promote(self.v, "Ops secret: client pricing", "Acme pays 42 per tonne, ops only.",
                "ops", "clients")
        promote(self.v, "Dev note: pricing module", "The pricing module computes per tonne rates.",
                "dev", "knowledge")
        dev = make_server(self.dir, MAGNEMO_SCOPE="dev")
        r = json.loads(call(dev, "retrieve", query="pricing per tonne")[0])
        self.assertEqual(r["scope"], ["dev"])
        self.assertTrue(all(h["pointer"].startswith("mn://dev/") for h in r["results"]))
        self.assertEqual(r["served"], 1)
        text, err = call(dev, "retrieve", query="pricing", scope="ops")
        self.assertTrue(err); self.assertIn("SCOPE WALL", text)
        text, err = call(dev, "bootpack", scope="ops")
        self.assertTrue(err); self.assertIn("SCOPE WALL", text)
        pack, err = call(dev, "bootpack")                      # omitted scope → the one allowed
        self.assertFalse(err); self.assertIn("scope: dev", pack)
        self.assertNotIn("Acme pays", pack)
        # an unwalled agent sees both
        both = make_server(self.dir)
        r = json.loads(call(both, "retrieve", query="pricing per tonne")[0])
        self.assertEqual(r["served"], 2)

    def test_multi_partition_scope_needs_explicit_bootpack_scope(self):
        s = make_server(self.dir, MAGNEMO_SCOPE="dev,shared")
        text, err = call(s, "bootpack")
        self.assertTrue(err); self.assertIn("name one partition", text)
        text, err = call(s, "bootpack", scope="shared")
        self.assertFalse(err)

    # -- budgets cap payloads with logged truncation --
    def test_budget_caps_payload_and_logs_truncation(self):
        for i in range(8):
            promote(self.v, f"Spike pattern {i}", f"spike spike pattern number {i} " + "detail " * 60,
                    "ops", "knowledge")
        s = make_server(self.dir)
        full = json.loads(call(s, "retrieve", query="spike pattern", k=8, budget=32000)[0])
        self.assertEqual((full["served"], full["truncated"]), (8, False))
        tight = json.loads(call(s, "retrieve", query="spike pattern", k=8, budget=700)[0])
        self.assertTrue(tight["truncated"])
        self.assertLessEqual(tight["payload_bytes"], 700 + 60)  # + the small envelope (rid/meta)
        self.assertLess(tight["served"], 8)
        self.assertEqual(tight["candidates"], 8)
        # pointer rendition kicks in when even one snippet won't fit
        tiny = json.loads(call(s, "retrieve", query="spike pattern", k=8, budget=200)[0])
        self.assertEqual(tiny["rendition"], "pointer")
        for h in tiny["results"]:
            self.assertNotIn("snippet", h); self.assertIn("pointer", h)
        # every served payload is a Foresight event; the truncation is on the record
        es = [e for e in foresight.entries(self.v) if e["kind"] == "retrieval"]
        self.assertEqual(len(es), 3)
        self.assertEqual([e["meta"]["truncated"] for e in es], [False, True, True])
        self.assertEqual(es[1]["meta"]["budget"], 700)
        self.assertEqual(es[2]["meta"]["rendition"], "pointer")
        self.assertEqual(es[1]["bytes"], tight["payload_bytes"])

    def test_budget_is_clamped_and_clamp_is_logged(self):
        s = make_server(self.dir)
        r = json.loads(call(s, "retrieve", query="x", budget=10**9)[0])
        self.assertEqual(r["budget"], mcp.MAX_BUDGET)
        e = foresight.entries(self.v)[-1]
        self.assertEqual((e["meta"]["budget"], e["meta"]["budget_asked"]), (mcp.MAX_BUDGET, 10**9))

    # -- free tier / least privilege --
    def test_free_tier_stdlib_only(self):
        import re
        src = open(os.path.join(ROOT, "magnemo", "mcp.py")).read()
        imports = re.findall(r"^(?:from|import)\s+([\w.]+)", src, re.M)
        for mod in imports:
            top = mod.split(".")[0]
            self.assertTrue(top in ("os", "sys", "json", "__future__") or mod.startswith("."), mod)
        for word in ("requests", "httpx", "openai", "anthropic", "urllib", "socket", "subprocess"):
            self.assertNotIn(word, src)

    def test_least_privilege_surface(self):
        s = make_server(self.dir)
        names = [t["name"] for t in s.tools_spec()]
        self.assertEqual(names, FOUR)
        src = open(os.path.join(ROOT, "magnemo", "mcp.py")).read()
        for forbidden in ("eval(", "exec(", "os.system", "subprocess", "Popen", "__import__"):
            self.assertNotIn(forbidden, src)


class TestCascades(unittest.TestCase):
    """B3. Each verb triggers a fixed chain of deterministic effects. These
    tests assert the WHOLE chain, in order, from one call."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.v = Vault(self.dir); self.v.init()
        self.s = make_server(self.dir, MAGNEMO_AGENT="cascade-agent")

    def tearDown(self):
        shutil.rmtree(self.dir)

    def _costs(self, kind=None):
        return [e for e in foresight.entries(self.v) if kind is None or e["kind"] == kind]

    # stage() → pattern-separation/dup flag → KAIROS salience written → telemetry logged
    def test_stage_cascade(self):
        promote(self.v, "Kwik Lube month-end spike",
                "Volumes spike ~35% in the last week of each month. 7 occurrences.",
                "ops", "knowledge", tags="pattern")
        # 1. a genuinely new note: no dup flag, novelty high
        fresh = json.loads(call(self.s, "stage", provenance=GOOD_PROV, note={
            "title": "Acme pickup window", "body": "Acme accepts deliveries 06:00-14:00 weekdays only.",
            "partition": "ops", "store": "clients", "impact": "process"})[0])
        self.assertIsNone(fresh["duplicate_of"])
        n1 = self.v.read(fresh["staged"])
        self.assertGreaterEqual(n1.salience, 0)
        self.assertNotIn(mcp.DUP_TAG, n1.tags)
        self.assertGreater(fresh["salience_components"]["novelty"], 0.9)
        # 2. a near-duplicate of canon: dup flag set, novelty collapses, salience written, telemetry carries it
        dup = json.loads(call(self.s, "stage", provenance=GOOD_PROV, note=dict(GOOD_NOTE))[0])
        n2 = self.v.read(dup["staged"])
        self.assertTrue(dup["duplicate_of"])
        self.assertGreaterEqual(dup["duplicate_similarity"], mcp.DUP_THRESHOLD)
        self.assertEqual(n2.extra.get("dup_of"), dup["duplicate_of"])      # in frontmatter (auditable)
        self.assertIn(mcp.DUP_TAG, n2.tags)
        self.assertLess(dup["salience_components"]["novelty"], 0.5)
        self.assertEqual(n2.salience, dup["salience"])
        self.assertLess(n2.salience, n1.salience + 0.25)  # consequence(money) alone can't hide a dup
        # 3. a near-duplicate of an already-STAGED note is flagged too (separation within the queue)
        dup2 = json.loads(call(self.s, "stage", provenance=GOOD_PROV, note={
            "title": "Acme pickup window", "body": "Acme accepts deliveries 06:00-14:00 weekdays only!",
            "partition": "ops", "store": "clients"})[0])
        self.assertEqual(dup2["duplicate_of"], fresh["staged"])
        # 4. telemetry: one 'stage' event per call, in order, carrying id/salience/dup
        es = self._costs("stage")
        self.assertEqual([e["meta"]["id"] for e in es], [fresh["staged"], dup["staged"], dup2["staged"]])
        self.assertEqual([e["meta"]["dup_of"] for e in es], ["", dup["duplicate_of"], fresh["staged"]])
        self.assertEqual(es[1]["meta"]["salience"], n2.salience)
        self.assertTrue(all(e["meta"]["via"] == "mcp" for e in es))

    def test_stage_cascade_is_deterministic(self):
        # same vault state + same note ⇒ same salience + same dup verdict (no clock/RNG in the chain)
        promote(self.v, "Canon A", "alpha beta gamma delta epsilon", "dev", "knowledge")
        a = json.loads(call(self.s, "stage", provenance=GOOD_PROV, note={
            "title": "Canon A", "body": "alpha beta gamma delta epsilon zeta",
            "partition": "dev", "store": "knowledge"})[0])
        d2 = tempfile.mkdtemp()
        try:
            v2 = Vault(d2); v2.init()
            promote(v2, "Canon A", "alpha beta gamma delta epsilon", "dev", "knowledge")
            s2 = make_server(d2, MAGNEMO_AGENT="cascade-agent")
            b = json.loads(call(s2, "stage", provenance=GOOD_PROV, note={
                "title": "Canon A", "body": "alpha beta gamma delta epsilon zeta",
                "partition": "dev", "store": "knowledge"})[0])
        finally:
            shutil.rmtree(d2)
        self.assertEqual(a["salience"], b["salience"])
        self.assertEqual(a["salience_components"], b["salience_components"])
        self.assertEqual(a["duplicate_similarity"], b["duplicate_similarity"])

    # retrieve() → scope-gate → budget/rendition select → payload telemetry
    def test_retrieve_cascade(self):
        for i in range(6):
            promote(self.v, f"Ops spike {i}", "spike " * 50 + f"ops {i}", "ops", "knowledge")
        promote(self.v, "Dev spike", "spike " * 50 + "dev", "dev", "knowledge")
        dev = make_server(self.dir, MAGNEMO_AGENT="dev-agent", MAGNEMO_SCOPE="dev")
        # 1. scope gate FIRST: a walled call is refused before any budget work, and logs nothing
        text, err = call(dev, "retrieve", query="spike", scope="ops", budget=300)
        self.assertTrue(err); self.assertIn("SCOPE WALL", text)
        self.assertEqual(self._costs("retrieval"), [])
        self.assertFalse(os.path.exists(os.path.join(self.dir, "_ledger", "retrievals.jsonl")))
        # 2. gate passes → candidates limited to scope → 3. budget/rendition → 4. telemetry
        r = json.loads(call(dev, "retrieve", query="spike", k=10, budget=300)[0])
        self.assertEqual(r["scope"], ["dev"])
        self.assertEqual(r["candidates"], 1)
        self.assertTrue(all(h["pointer"].startswith("mn://dev/") for h in r["results"]))
        self.assertEqual(r["rendition"], "pointer")  # 300 bytes can't hold a 240-char snippet envelope
        self.assertTrue(r["truncated"])
        es = self._costs("retrieval")
        self.assertEqual(len(es), 1)
        m = es[0]["meta"]
        self.assertEqual((m["scope"], m["budget"], m["rendition"], m["truncated"], m["candidates"], m["served"]),
                         ("dev", 300, "pointer", True, 1, 1))
        self.assertEqual(m["rid"], r["rid"]); self.assertEqual(m["agent"], "dev-agent")
        # 5. the unwalled agent sees all 7 and, with room, gets snippets untruncated
        r2 = json.loads(call(self.s, "retrieve", query="spike", k=10, budget=32000)[0])
        self.assertEqual((r2["candidates"], r2["served"], r2["rendition"], r2["truncated"]), (7, 7, "snippet", False))
        self.assertEqual(len(self._costs("retrieval")), 2)

    # bootpack() → Charter + digest + KAIROS-ranked staged (+ inherited handoff)
    def test_bootpack_cascade(self):
        charter = promote(self.v, "The Charter", "Agents stage; humans promote. Canon is read-only.",
                          "shared", "changelog", tags="charter")
        promote(self.v, "Ops fact", "Acme pays per tonne.", "ops", "clients")
        # three staged notes of ascending consequence: the pack must rank them by KAIROS, not by time
        ids = []
        for impact, title in (("info", "Low stakes"), ("security", "Token leak in logs"), ("process", "Mid stakes")):
            r = json.loads(call(self.s, "stage", provenance={"source": "audit#3"}, note={
                "title": title, "body": f"{title} body text {impact}", "partition": "ops",
                "store": "knowledge", "impact": impact})[0])
            ids.append((r["salience"], title))
        pack, err = call(self.s, "bootpack")
        self.assertFalse(err, pack)
        sections = [l for l in pack.splitlines() if l.startswith("## ")]
        self.assertEqual(sections, ["## THE CHARTER", "## GATES", "## YOUR AUTONOMY — cascade-agent", "## CANON DIGEST", "## OPEN THREADS & REVIEW QUEUE",
                                    "## LAST HANDOFF", "## LEDGER TAIL (last 4 of 4)"])  # 2 promotes + 2 derived trust.events (P-02)
        self.assertLess(pack.index("Agents stage; humans promote"), pack.index("## CANON DIGEST"))  # charter verbatim, first
        self.assertIn("**Ops fact** — Acme pays per tonne.", pack)                                      # digest
        queue = pack.split("Top 3 by salience:")[1].split("## LAST HANDOFF")[0]
        order = [l.split("] ", 1)[1].split(" (")[0] for l in queue.strip().splitlines()]
        self.assertEqual(order, [t for _, t in sorted(ids, reverse=True)])                               # KAIROS-ranked
        self.assertEqual(order[0], "Token leak in logs")
        self.assertIn("no boundary recorded yet", pack)
        # telemetry: a bootpack event with the served size
        e = self._costs("bootpack")[-1]
        self.assertEqual(e["bytes"], len(pack.encode("utf-8")))
        self.assertEqual(e["meta"]["via"], "mcp")
        # determinism: second call, same bytes
        self.assertEqual(call(self.s, "bootpack")[0], pack)

    # handoff() → telemetry append → staged note → next bootpack inherits it
    def test_handoff_cascade(self):
        before, _ = call(self.s, "bootpack")
        self.assertIn("no boundary recorded yet", before)
        r = json.loads(call(self.s, "handoff", usage=88, trigger="planned", cut="deferred the README")[0])
        # 1. telemetry appended
        es = handoff.entries(self.v)
        self.assertEqual(len(es), 1)
        self.assertEqual((es[0]["usage_pct"], es[0]["trigger"], es[0]["cut"]), (88.0, "planned", "deferred the README"))
        # 2. staged note, provenance complete, KAIROS-scored
        n = self.v.read(es[0]["note_id"])
        self.assertEqual((n.status, n.author), ("staged", "cascade-agent"))
        self.assertTrue(n.source.startswith("mcp/handoff/"))
        self.assertGreaterEqual(n.salience, 0)
        # 3. the NEXT bootpack inherits it — regardless of queue rank
        after, _ = call(self.s, "bootpack")
        self.assertNotEqual(after, before)
        last = after.split("## LAST HANDOFF")[1].split("## LEDGER TAIL")[0]
        self.assertIn("usage 88%", last)
        self.assertIn("trigger planned", last)
        self.assertIn("deferred the README", last)
        self.assertIn(f"_staging/{n.id}.md", last)
        # a second boundary supersedes the first in the pack; both stay on record
        call(self.s, "handoff", usage=95, trigger="wall")
        third, _ = call(self.s, "bootpack")
        last = third.split("## LAST HANDOFF")[1].split("## LEDGER TAIL")[0]
        self.assertIn("usage 95%", last); self.assertNotIn("usage 88%", last)
        self.assertIn("boundaries on record: 2", last)
        # 4. a fresh server (the next session) sees the same inherited boundary
        nxt = make_server(self.dir, MAGNEMO_AGENT="next-session")
        nxt_pack = call(nxt, "bootpack")[0]
        # P-02 B4: each agent boots with ITS OWN scorecard; everything else is identical
        def strip_own(p):
            head, rest = p.split("## YOUR AUTONOMY — ", 1)
            return head + "## CANON DIGEST" + rest.split("## CANON DIGEST", 1)[1]
        self.assertEqual(strip_own(nxt_pack), strip_own(third))
        self.assertIn("## YOUR AUTONOMY — next-session", nxt_pack)
        self.assertIn("autonomy at the boundary: read L2", nxt_pack.split("## LAST HANDOFF")[1])
        # telemetry: handoff events logged too
        self.assertEqual(len(self._costs("handoff")), 2)

    def test_no_model_calls_anywhere_in_the_chain(self):
        # the entire server path is stdlib + package; nothing in the chain can reach a model
        import re
        for mod in ("mcp", "search", "kairos", "bootpack", "handoff", "foresight", "governance", "vault"):
            src = open(os.path.join(ROOT, "magnemo", mod + ".py")).read()
            for word in ("anthropic", "openai", "requests", "httpx", "urllib", "socket"):
                self.assertNotIn(word, src, (mod, word))


if __name__ == "__main__":
    unittest.main()
