"""Allow `python -m owa` for contract tests and local smoke checks."""
import sys

from .cli import main

if __name__ == '__main__':
    sys.exit(main())
