"""python -m magnemo — same CLI as the `magnemo` console script.
The fallback that works when pip's script directory is not on PATH."""
from .cli import main

if __name__ == "__main__":
    main()
