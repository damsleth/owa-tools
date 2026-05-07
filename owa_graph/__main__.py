"""Allow `python -m owa_graph` for the help-smoke step in CI."""
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main() or 0)
