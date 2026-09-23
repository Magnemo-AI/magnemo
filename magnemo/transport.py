"""magnemo.transport — stdio JSON-RPC plumbing for the MCP server (zero deps).

Speaks Model Context Protocol over stdin/stdout: newline-delimited JSON-RPC 2.0.
Declares NO tools of its own — `magnemo.mcp.MemoryServer` is the one server and
the only tool surface. Least privilege is enforced here: only tools DECLARED by
`tools_spec()` are dispatchable; a private or inherited method never becomes a
tool by accident.

Configuration (env):
  MAGNEMO_VAULT       path to the vault root                 (required)
  MAGNEMO_AGENT       calling agent's identity, e.g. "ops-agent"   (default "agent")
  MAGNEMO_PARTITIONS  comma list this agent may WRITE to     (default: all)
"""
from __future__ import annotations
import sys, os, json, traceback
from .vault import Vault, PARTITIONS
from .governance import Governance
from .search import Index
from .config import env
from . import __version__

PROTOCOL_FALLBACK = "2025-06-18"
SERVER_INFO = {"name": "magnemo", "title": "Magnemo — governed memory for AI agents", "version": __version__}


class Server:
    def __init__(self):
        root = env("VAULT")
        if not root:
            sys.stderr.write("MAGNEMO_VAULT env var is required\n")
            sys.exit(2)
        self.vault = Vault(root)
        if not self.vault.exists():
            self.vault.init()
        self.gov = Governance(self.vault)
        self.index = Index(self.vault)
        self.agent = env("AGENT", "agent")
        wp = env("PARTITIONS", ",".join(self.vault.partitions))
        self.write_partitions = self.vault.resolve_scope(wp.split(",")) or tuple(p.strip() for p in wp.split(",") if p.strip())
        # KAIROS: report review-queue depth at session start (stderr — never
        # pollutes the JSON-RPC channel on stdout).
        depth = sum(1 for n in self.vault.staged() if n.status == "staged")
        sys.stderr.write(f"[magnemo] review queue depth: {depth}\n")

    def tools_spec(self) -> list:
        """The declared tool surface. The transport declares nothing; the server does."""
        return []

    # ---------------- JSON-RPC plumbing ----------------
    def handle(self, msg: dict):
        method = msg.get("method", "")
        mid = msg.get("id")
        if method == "initialize":
            client_ver = (msg.get("params") or {}).get("protocolVersion", PROTOCOL_FALLBACK)
            self._connected((msg.get("params") or {}).get("clientInfo") or {})
            return self._result(mid, {
                "protocolVersion": client_ver,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            })
        if method in ("notifications/initialized", "initialized"):
            return None  # notification: no response
        if method == "ping":
            return self._result(mid, {})
        if method == "tools/list":
            return self._result(mid, {"tools": self.tools_spec()})
        if method == "tools/call":
            p = msg.get("params") or {}
            name = p.get("name", "")
            args = p.get("arguments") or {}
            # Least privilege: only tools DECLARED by tools_spec() are callable.
            declared = {t["name"] for t in self.tools_spec()}
            fn = getattr(self, "t_" + name, None) if name in declared else None
            if fn is None:
                return self._error(mid, -32601, f"unknown tool: {name}")
            try:
                text = fn(args)
                return self._result(mid, {"content": [{"type": "text", "text": text}],
                                          "isError": False})
            except Exception as e:  # tool errors are results, not protocol errors
                return self._result(mid, {"content": [{"type": "text",
                                          "text": f"ERROR: {e}"}], "isError": True})
        if mid is not None:
            return self._error(mid, -32601, f"unknown method: {method}")
        return None

    def _connected(self, client: dict):
        """P-74: one line per MCP session start, so `doctor` can tell a mounted server from one that never connected.
        Never raises into the protocol."""
        try:
            from .vault import now_iso
            d = os.path.join(self.vault.root, "_ledger")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "connections.jsonl"), "a") as f:
                f.write(json.dumps({"ts": now_iso(), "agent": self.agent, "client": str(client.get("name", ""))[:80],
                                    "client_version": str(client.get("version", ""))[:40], "server": __version__}) + "\n")
        except Exception:
            pass

    @staticmethod
    def _result(mid, result):
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    @staticmethod
    def _error(mid, code, message):
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}

    def run(self):
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            try:
                resp = self.handle(msg)
            except Exception:
                traceback.print_exc(file=sys.stderr)
                resp = self._error(msg.get("id"), -32603, "internal error")
            if resp is not None:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
