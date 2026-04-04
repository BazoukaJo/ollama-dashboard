# UI customization

## Compact mode toggle (disabled by default)

The floating **compact mode** button is **not** rendered on the main dashboard (`index.html`) so more vertical space is available for model lists. All **compact-mode styles** remain in `app/static/css/styles.css` (e.g. `.compact-toggle-btn`, `body.compact-mode`).

### Re-enable the button

1. In `app/templates/index.html`, inside `<body>`, add **before** `<div class="container py-3">`:

```html
<button id="compactToggle" class="compact-toggle-btn" type="button" title="Toggle Compact Mode">
    <i class="fas fa-compress"></i>
</button>
```

2. Reload the dashboard. The existing `initializeCompactMode()` logic in `app/static/js/main.js` will attach the click handler.

### Compact layout without the button

Without `#compactToggle`, the page always loads **expanded** (no `body.compact-mode`). The `compactMode` key is only read when the toggle is present, so you are not stuck in compact layout after removing the button.

---

## Downloadable models: how many show before “View More”

The first batch of **Downloadable Models** cards is controlled in `app/static/js/main.js`:

- Constant: **`INITIAL_DOWNLOADABLE_VISIBLE`** (default **48**).

Increase or decrease that number and refresh the page (no server restart required for static JS after rebuild/cache-bust).
