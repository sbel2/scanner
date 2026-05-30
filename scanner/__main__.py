"""
scanner — CLI entry point.

Usage:
    python -m scanner init      # First-time setup wizard
    python -m scanner run       # Run the scanner pipeline
    python -m scanner           # Same as 'run' (backward compat)
"""
from __future__ import annotations

import sys


def main():
    args = sys.argv[1:]
    command = args[0] if args else "run"

    if command == "init":
        from .init_cmd import run as init_run
        init_run()
    elif command in ("run", ""):
        from .pipeline import run as pipeline_run
        welcome = "--welcome" in args
        raise SystemExit(pipeline_run(welcome=welcome))
    else:
        print(f"[scanner] Unknown command: {command!r}")
        print("Usage: python -m scanner [init|run]")
        sys.exit(1)


if __name__ == "__main__":
    main()
