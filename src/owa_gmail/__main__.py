"""`python -m owa_gmail` entrypoint."""
import sys

from .cli import main

sys.exit(main())
