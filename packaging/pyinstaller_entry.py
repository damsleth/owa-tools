"""Single multicall entry point for the frozen owa-tools binary.

PyInstaller builds one executable from this module. The name the binary is
invoked as (``argv[0]`` basename) selects which tool's ``main()`` to run,
busybox-style: ``owa``, ``owa-cal``, ``owa-mail``, ... are all symlinks to
the same executable. This mirrors the ``[project.scripts]`` entry points in
pyproject.toml so the frozen bundle behaves exactly like a pip install.

The dispatch table is derived from ``owa_core.registry.CONSUMER_TOOLS`` so it
can never drift from the real list of consumer CLIs.
"""
import importlib
import os
import sys

from owa_core.registry import CONSUMER_TOOLS


def dispatch_table():
    """Map invocation name -> (module, attribute) for every shipped binary."""
    table = {"owa": ("owa.cli", "main")}
    for name in CONSUMER_TOOLS:            # e.g. "owa-cal"
        table[name] = (name.replace("-", "_"), "main")   # -> ("owa_cal", "main")
    return table


def main(argv=None):
    table = dispatch_table()
    prog = os.path.basename(sys.argv[0])
    # Unknown names fall back to the umbrella, which prints usage.
    module_name, attr = table.get(prog, table["owa"])
    module = importlib.import_module(module_name)
    func = getattr(module, attr)
    return func() if argv is None else func(argv)


if __name__ == "__main__":
    sys.exit(main() or 0)
