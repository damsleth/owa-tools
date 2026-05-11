"""Pytest bootstrap: expose `src/` for non-installed packages like `scripts`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
