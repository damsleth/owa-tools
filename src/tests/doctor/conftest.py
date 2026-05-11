"""Shared fixtures for the owa-doctor test suite.

No network. No real tokens. No subprocess to a real owa-piggy.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
