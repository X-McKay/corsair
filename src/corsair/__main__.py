"""Allow `python -m corsair` alongside the installed CLI."""

from corsair.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
