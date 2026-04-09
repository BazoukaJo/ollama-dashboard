# Contributing

Thanks for helping improve Ollama Dashboard.

## Before you open a PR

1. **Tests** — From the repo root:

   ```bash
   pip install -r requirements.txt
   python -m pytest -q
   ```

   This includes the in-process smoke checks (`tests/test_smoke_script.py`).

2. **Lint** — Install dev tools and run Ruff (same command CI uses):

   ```bash
   pip install ruff
   ruff check app tests scripts
   ```

   Or: `pip install -r requirements-dev.txt` then `ruff check app tests scripts`.

3. **Manual smoke** (optional):

   ```bash
   python scripts/smoke_check.py
   ```

## Integration / live-server tests

Some files under `tests/` are marked skipped by default (e.g. helpers that expect `http://localhost:5000` or Playwright). They are not part of the default CI matrix.

## Style

- Match existing patterns in the file you edit.
- Prefer small, focused commits and clear PR descriptions.

## Questions

Open a [GitHub issue](https://github.com/bazoukajo/ollama-dashboard/issues) if something is unclear.
