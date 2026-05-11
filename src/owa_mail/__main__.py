"""`python -m owa_mail` entrypoint."""
import sys

from .cli import main

sys.exit(main())
