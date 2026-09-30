"""`python -m owa_gdrive` entrypoint."""
import sys

from .cli import main

sys.exit(main())
