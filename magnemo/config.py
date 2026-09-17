"""magnemo.config — the vault's documented configuration file.

One JSON file per vault: `<vault>/_config/magnemo.json`. Created with
defaults on `cli init`; safe to hand-edit (it is the founder's file). Every
key is documented in docs/CONFIG.md. Unknown keys are preserved; missing
keys fall back to the defaults below, so a partial file is always valid.

Zero dependencies, deterministic: no environment lookups beyond the vault
path, no model calls, no clock reads.
"""
from __future__ import annotations
import os, json, copy

# ---- environment names: MAGNEMO_* is the name. ----------------------------
# COMPATIBILITY, one release: the first dead name, MEMOS_*, is still honored when
# its MAGNEMO_* twin is unset. This is the ONLY place the mapping lives.
# MEMOS_* honored through 0.6.x; removed in 0.7.
ENV_PREFIX = "MAGNEMO_"
LEGACY_ENV_PREFIX = "MEMOS_"
ENV_NAMES = ("VAULT", "AGENT", "SCOPE", "PARTITIONS")


def env(name: str, default=None, environ=None):
    """Read MAGNEMO_<name>; fall back to MEMOS_<name> silently; else default."""
    e = os.environ if environ is None else environ
    v = e.get(ENV_PREFIX + name)
    if v is None:
        v = e.get(LEGACY_ENV_PREFIX + name)
    return default if v is None else v


def legacy_env_in_use(environ=None) -> list:
    """Every MEMOS_* setting present (in a process env or a mount's env dict) —
    the doctor names them once so they get renamed before 0.7."""
    e = os.environ if environ is None else environ
    return sorted(k for k in e if k.startswith(LEGACY_ENV_PREFIX))


CONFIG_DIR = "_config"
CONFIG_FILE = "magnemo.json"
# Pre-ratification vaults (≤ 0.3) carry the config under the old package name.
# Read-only fallback for one release; new vaults always get magnemo.json.
LEGACY_CONFIG_FILES = ("mnemosyneos.json",)

DEFAULTS = {
    # THE VAULT'S SHAPE (P-19): partitions and their stores are the vault's own
    # declaration. These three are the defaults every vault is born with; a
    # vault may declare its own (the boardroom declares doctrine · state ·
    # missions · receipts). `scopes` are read-scope aliases for MAGNEMO_SCOPE.
    "partitions": {
        "dev":    ["knowledge", "playbooks", "decisions", "debt"],
        "ops":    ["knowledge", "playbooks", "clients", "decisions", "style"],
        "shared": ["tickets", "changelog"],
    },
    "scopes": {},
    # RENDER-ON-PROMOTE: when a note carries a `render:` path, promotion writes
    # its body to <vault>/<render.root>/<path> and ledgers the PRIOR file hash.
    # Empty root = off. The file on disk is the rendered view of a promoted memory.
    "render": {"root": ""},
    # THE INBOX DOOR: `magnemo inbox <dir>` stages every drop with provenance
    # and routes it by filename glob to a partition/store (+ render path).
    "inbox": {"dir": "", "routes": []},
    # KAIROS v1 — deterministic salience at stage time.
    "kairos": {
        # Component weights. INVARIANT: weights["operator"] must exceed the
        # sum of all other weights — a founder-flagged note ALWAYS outranks
        # any unflagged note, whatever its other components. The operator is
        # the highest-bandwidth salience signal we have.
        "weights": {
            "operator": 0.55,
            "consequence": 0.25,
            "novelty": 0.12,
            "source": 0.08,
        },
        # Declared impact classes, highest consequence first.
        "impact_classes": {
            "security": 1.0,
            "money": 0.85,
            "correctness": 0.7,
            "process": 0.5,
            "info": 0.3,
        },
        "default_impact": "info",
        # Source-weight tiers: if any keyword appears in the note's `source`
        # field (case-insensitive substring), the highest matching weight
        # applies; otherwise default_source_weight (routine).
        "source_classes": {
            "audit": 1.0,
            "postmortem": 1.0,
            "incident": 0.9,
            "gate": 0.7,
            "review": 0.7,
        },
        "default_source_weight": 0.3,
        # The founder-flag tag. Set via `cli flag <note-id> --by NAME`;
        # its presence is the operator-signal component.
        "operator_tag": "founder-flag",
    },
    # Review queue presentation.
    "review": {
        # Default batch cap for `cli review` (override with --batch N).
        "batch": 10,
    },
    # TRUST — the arithmetic of earned trust.
    # score = Σ weight[kind] × 0.5^(age_days / half_life_days) over events
    # after the latest violation; level = highest threshold met, clamped to
    # the class floor/ceiling. promote-canon and publish are hard-capped at
    # L1 for non-keyholders in code — keyholder-only forever; no key here can lift that.
    "trust": {
        "weights": {
            "success": 1.0,      # an action in the class completed and accepted
            "verified": 2.0,     # a keyholder verified the outcome after the fact
            "halt": 1.0,         # stopped at a ceiling and waited (a halt honored)
            "failure": -1.0,     # rejected / reverted
            "denied": -0.5,      # tried an action a wall refused
            "surprise": -3.0,    # verification failed or deviated from the brief
            # "violation" carries no weight: it is the elevator (reset + freeze);
            # "reinstate" carries no weight: a keyholder lifts the freeze.
        },
        "half_life_days": 90,
        # score ≥ threshold ⇒ level. L0 is "below propose" or frozen.
        "thresholds": {"1": 0.0, "2": 5.0, "3": 15.0},
        # Per class: floor/ceiling clamp the COMPUTED level; default_grant is
        # the permission an actor holds with no grant on file (B2 raises it).
        "classes": {
            "read":          {"floor": 2, "ceiling": 3, "default_grant": 3},
            "stage":         {"floor": 2, "ceiling": 3, "default_grant": 2},
            "merge-code":    {"floor": 0, "ceiling": 3, "default_grant": 1},
            "promote-canon": {"floor": 0, "ceiling": 1, "default_grant": 1},
            "publish":       {"floor": 0, "ceiling": 1, "default_grant": 1},
        },
        # Keyholders: the people who hold every key by declaration. Not scored.
        "humans": ["founder", "The Founder"],
        # THE GATE MAP. state: locked | open | computed.
        # "computed" reads as delegated while an active grant covers the
        # class for a non-keyholder, else locked. Keyholder-only classes are always
        # locked, whatever is written here.
        "gates": [
            {"name": "retrieve", "class": "read", "state": "open",
             "keyholder": "scope wall (MAGNEMO_SCOPE)",
             "note": "canon only; staged notes invisible until promoted"},
            {"name": "staging", "class": "stage", "state": "open",
             "keyholder": "partition wall + review queue",
             "note": "the only write door; provenance mandatory; keyholders review after"},
            {"name": "main", "class": "merge-code", "state": "computed",
             "keyholder": "The Founder",
             "note": "self-merge only at effective L2+ under an active grant; one log line per merge"},
            {"name": "gate-code", "class": "merge-code", "state": "locked",
             "keyholder": "The Founder",
             "note": "the gates do not merge changes to the gates",
             "paths": ["magnemo/trust.py", "magnemo/grants.py", "magnemo/gates.py",
                       "magnemo/governance.py", "magnemo/mcp.py", "magnemo/server.py",
                       "vault/_config/"]},
            {"name": "canon", "class": "promote-canon", "state": "locked",
             "keyholder": "The Founder", "note": "promotion is never a tool"},
            {"name": "publish", "class": "publish", "state": "locked",
             "keyholder": "The Founder",
             "note": "PyPI, npm, tags, releases, repo settings and renames"},
        ],
    },
    # Boot Pack rendering.
    "bootpack": {
        # The canonical note tagged with this is THE CHARTER, served
        # verbatim and first in every boot pack. Never fabricated.
        "charter_tag": "charter",
        # Notes (canonical or staged) tagged with this are open threads.
        "open_tag": "open",
        # The codex seam (partner class only): a markdown file holding
        # voice/lore/relationship. Relative paths resolve against the vault
        # root; empty string disables. Absent file = graceful worker boot.
        "codex_path": "_codex/CODEX.md",
        # EXCERPTS: sections lifted verbatim from CANONICAL NOTES (by title),
        # between a start line (regex, inclusive) and an end line (regex,
        # exclusive). Sourced from the vault, so a restored copy boots identically.
        "excerpts": [],
        # PARTNER EXCERPTS: rendered only for `--class partner` — the fuller read
        # (a whole codex, a baton section) on top of the worker's excerpts.
        "partner_excerpts": [],
        # How many trailing trust-ledger entries the pack includes.
        "ledger_tail": 10,
        # How many top-salience staged titles the pack lists.
        "top_staged": 5,
    },
}


def config_path(vault_root: str) -> str:
    """The config file to READ: magnemo.json, else a legacy-named file if
    that is all the vault has. Writes always target magnemo.json."""
    new = os.path.join(vault_root, CONFIG_DIR, CONFIG_FILE)
    if os.path.exists(new):
        return new
    for legacy in LEGACY_CONFIG_FILES:
        old = os.path.join(vault_root, CONFIG_DIR, legacy)
        if os.path.exists(old):
            return old
    return new


# A vault's own declarations are whole, never unioned with the defaults.
REPLACE_KEYS = ("partitions", "scopes")


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if k in REPLACE_KEYS:
            out[k] = copy.deepcopy(v)
        elif isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(vault_root: str) -> dict:
    """Defaults, overlaid with the vault's config file if present."""
    path = config_path(vault_root)
    if not os.path.exists(path):
        return copy.deepcopy(DEFAULTS)
    try:
        with open(path) as f:
            user = json.load(f)
    except (json.JSONDecodeError, OSError):
        return copy.deepcopy(DEFAULTS)
    if not isinstance(user, dict):
        return copy.deepcopy(DEFAULTS)
    return _merge(DEFAULTS, user)


def ensure_config(vault_root: str) -> str:
    """Write the default config file if none exists (called by vault init).
    Never overwrites a founder-edited file."""
    path = os.path.join(vault_root, CONFIG_DIR, CONFIG_FILE)
    if not os.path.exists(path) and not os.path.exists(config_path(vault_root)):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(DEFAULTS, f, indent=2)
            f.write("\n")
    return path
