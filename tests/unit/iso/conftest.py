"""Make the shared ISO strategies importable under pytest's importlib mode.

With ``--import-mode=importlib`` pytest does not add test directories to
``sys.path``, so a sibling helper module is not importable by bare name. Adding
this directory keeps ``import iso_strategies`` working for the ISO test modules.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
