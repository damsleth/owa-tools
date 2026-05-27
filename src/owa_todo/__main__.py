"""`python -m owa_todo` entrypoint."""
import sys

from .cli import main

sys.exit(main())
