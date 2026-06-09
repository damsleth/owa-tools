# PyInstaller spec: one multicall binary for the whole owa-tools suite.
#
# Built as a onedir bundle named "owa". The release workflow adds a sibling
# symlink for every console-script name (owa-cal, owa-mail, ...), so the
# umbrella's subprocess calls to sibling tools (owa list / owa schema) resolve
# against the same frozen binary. Run from packaging/: `pyinstaller owa.spec`.
from PyInstaller.utils.hooks import collect_submodules, copy_metadata

from owa_core.registry import CONSUMER_TOOLS

# Every package whose submodules must be importable inside the frozen bundle.
# Subtools are imported dynamically (importlib) by the umbrella, so PyInstaller
# cannot discover them statically - collect them explicitly.
_packages = ["owa", "owa_core"] + [n.replace("-", "_") for n in CONSUMER_TOOLS]
hidden = []
for pkg in _packages:
    hidden += collect_submodules(pkg)

# Bundle the installed dist metadata so importlib.metadata.version("owa-tools")
# resolves inside the frozen binary (suite_version() depends on it).
datas = copy_metadata("owa-tools")

a = Analysis(
    ["pyinstaller_entry.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "test", "unittest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="owa",
    console=True,
    strip=False,
    upx=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="owa",
)
