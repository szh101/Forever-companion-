"""Deterministic local checks; no real screenshot, game process or API request."""
from pathlib import Path
import ast
import sys
import unittest

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
for directory in ("companion", "scripts", "tests"):
    for source in (root / directory).glob("*.py"):
        ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
suite = unittest.defaultTestLoader.discover(str(root / "tests"))
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
