#!/usr/bin/env python3
"""Legacy entry point — delegates to proxy_smoke_test.py."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.proxy_smoke_test import main  # noqa: E402

if __name__ == '__main__':
    sys.exit(main())
