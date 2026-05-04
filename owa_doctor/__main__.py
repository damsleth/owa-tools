"""`python -m owa_doctor` entrypoint."""
import sys

from .cli import main

sys.exit(main())
