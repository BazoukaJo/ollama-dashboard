# Contributing

Thanks for helping improve Ollama Dashboard.

## Before you open a PR

1. **Python tests** — from the repo root:

   ```bash
   pip install -r requirements.txt
   python -m pytest -q -m "not integration and not playwright"
   ```

   This includes the in-process smoke checks (`tests/test_smoke_script.py`).

2. **JavaScript tests** — same command CI uses:

   ```bash
   node tests/test_ask_message_format.js
   ```

3. **Lint** — install dev tools and run Ruff (same command CI uses):

   ```bash
   pip install ruff
   ruff check app tests scripts ollama_dashboard_cli.py
   ```

   **One-shot local check (Windows):** `scripts\check.bat` runs Ruff, pytest (`-m "not integration"`), and JS tests.

   Or: `pip install -r requirements-dev.txt` then `ruff check app tests scripts ollama_dashboard_cli.py`.

4. **Manual smoke** (optional):

   ```bash
   python scripts/smoke_check.py
   ```

## Integration / live-server tests

Some files under `tests/` are marked skipped by default (e.g. helpers that expect `http://localhost:5000` or Playwright). They are not part of the default CI matrix.

## Style

- Match existing patterns in the file you edit.
- Prefer small, focused commits and clear PR descriptions.
- Keep code comments for non-obvious behavior only; put user-facing and architectural detail in `docs/` or module docstrings.

## Questions

Open a [GitHub issue](https://github.com/bazoukajo/ollama-dashboard/issues) if something is unclear.
