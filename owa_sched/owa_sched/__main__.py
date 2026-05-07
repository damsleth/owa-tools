"""`python -m owa_sched` entrypoint."""
import sys

from .cli import main

sys.exit(main())
