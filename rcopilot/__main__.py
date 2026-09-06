"""Allow running as python -m rcopilot."""

from rcopilot.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
