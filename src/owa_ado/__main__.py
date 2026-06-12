"""`python -m owa_ado` entrypoint."""
import sys

from .cli import main

sys.exit(main())
