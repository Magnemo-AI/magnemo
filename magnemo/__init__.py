"""Magnemo — the governed memory layer. Reference implementation of the
Magnemo Protocol. SVTech Inc. · Silver Valley Technologies.
"""


def _read_version() -> str:
    """ONE version: pyproject.toml is the single source. A source checkout reads
    it directly; an installed wheel reads the metadata that was built from it.
    Never a second hand-typed string."""
    import os, re
    pp = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pyproject.toml")
    try:
        with open(pp, encoding="utf-8") as f:
            m = re.search(r'^version\s*=\s*"([^"]+)"', f.read(), re.M)
        if m:
            return m.group(1)
    except OSError:
        pass
    try:
        from importlib.metadata import version, PackageNotFoundError
        try:
            return version("magnemo")
        except PackageNotFoundError:
            pass
    except Exception:
        pass
    return "0+unknown"


__version__ = _read_version()
__codename__ = "First Trust"  # ratified 2026-08-20
