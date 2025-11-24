# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

### Removed

- Deprecated global `settings.json` (and related `/api/settings` & migration endpoint). Per-model settings in `model_settings.json` now sole source of configurable defaults.
- Autosave toggle (`model_settings_auto_save`) removed; recommended settings are created automatically when first encountered.
- `/settings` page and button removed; legacy template deleted.

### Fixed

- Capability flags (`has_vision`, `has_tools`, `has_reasoning`) are now guaranteed booleans across `get_available_models` and `get_running_models`.

- Add top-left reload button and spinner
- Add Start/Stop/Restart service buttons with a confirmation modal
- UI robustness: switch to `data-model-name` attribute for model card mapping, added `cssEscape()` and `escapeHtml()` helpers
- Add Playwright-based UI test and GitHub Actions CI workflow
- Move legacy tests into `tests/` and convert script-style tests to pytest assertions
- Update README, Add PR template
