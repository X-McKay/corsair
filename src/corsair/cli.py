"""`uv run corsair <command>`: the product's commands.

`corsair run --issue-json <file>` investigates one issue end to end (`corsair.investigate`).
"""
import sys


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    if argv[0] == "run":
        from corsair.investigate import main as run
        return run(argv[1:], prog="corsair run")
    if argv[0] == "v2":
        from corsair.v2.cli import main as v2
        return v2(argv[1:])
    print(f"corsair: unknown command {argv[0]!r}; commands: run, v2", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
