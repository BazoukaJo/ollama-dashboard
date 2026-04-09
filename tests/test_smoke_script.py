"""Run the same in-process checks as scripts/smoke_check.py (no subprocess — Windows-safe)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def test_smoke_check_main_exits_zero():
    path = _ROOT / "scripts" / "smoke_check.py"
    assert path.is_file()
    spec = importlib.util.spec_from_file_location("_smoke_check_exec", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.main() == 0
