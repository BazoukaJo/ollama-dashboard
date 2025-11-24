# Developer Notes — Frontend & Model Card Conventions

This file explains conventions used in the frontend and some best practices for adding or modifying UI code in the dashboard.

## Model card DOM conventions

- Each model card (`.model-card`) in both server-rendered templates and JS-rendered HTML includes a `data-model-name` attribute. The value is escaped server-side (Jinja `|e`) or via `escapeHtml()` in JS.
- Use `data-model-name` to find/update the model's card in the DOM instead of relying on indexes or string searching on the `model-title` text. This is more robust if the DOM is re-ordered or model names contain special characters.

Example (Jinja template):

```html
<div class="model-card h-100" data-model-name="{{ model.name | e }}">
  <!-- ... -->
</div>
```

Example (JS rendering):

```js
<div class="model-card h-100" data-model-name="${escapeHtml(model.name)}"> ... </div>
```

## Client-side helpers

The following helper functions are implemented in `app/static/js/main.js` and should be used when adding or editing render/update behavior:

- `escapeHtml(str)` — Safely escape and convert strings for HTML insertion.
- `cssEscape(str)` — Safely prepare a string for use in CSS attribute selectors; prefers `CSS.escape()` if available.

Use `cssEscape` when using attribute selectors that contain arbitrary strings:

```js
const card = container.querySelector(`.model-card[data-model-name="${cssEscape(name)}"]`);
```

## Update functions & patterns

- `updateRunningModelsDisplay` and `updateAvailableModelsDisplay` now locate model cards by `data-model-name`, then update capability icons and other properties such as `model-size`, `model-expires`, and system metrics.
- Split network calls into separate try/catch blocks in `updateModelData()` to avoid a single endpoint failure aborting updates to other parts of the UI.

## Clicking actions & event binding

- `onclick` handlers for template buttons no longer pass raw model name strings. Instead, use dataset lookup:

```html
<button onclick="startModel(this.closest('.model-card').dataset.modelName)">Start</button>
```

- Prefer wiring up events in JS when adding complex behaviors, but the dataset approach works for lightweight markup.

## Testing & UI integration

- The repository includes a skippable Selenium UI test (`tests/test_service_controls_ui.py`) that ensures:
  - Service control buttons don't throw JavaScript errors
  - `data-model-name` lookups succeed for names with special characters
  - Capability icons are toggled correctly
- If you add UI-level behaviors, add an appropriate test to cover the path (Selenium or Playwright).

## Additions / Best Practice Checklist

- Add `data-model-name` for any UI-rendered model card created or modified.
- Escape user/server-provided values with `escapeHtml` for JS inserts and `|e` in Jinja templates.
- Use `cssEscape` for CSS selectors that include dynamic values.
- Avoid passing model names directly as JS string literals in templates (use dataset lookup or use data attributes to access values).

This file is a living document — update it alongside code changes to keep new contributors aligned with established conventions.
