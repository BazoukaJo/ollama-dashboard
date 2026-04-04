# UI customization

## Compact mode toggle

The floating **compact mode** button is not included in `index.html` by default (more vertical space for model lists). Styles live in `app/static/css/styles.css` (`.compact-toggle-btn`, `body.compact-mode`).

### Re-enable the button

1. In `app/templates/index.html`, inside `<body>`, add **before** `<div class="container py-3">`:

```html
<button id="compactToggle" class="compact-toggle-btn" type="button" title="Toggle Compact Mode">
    <i class="fas fa-compress"></i>
</button>
```

2. Reload the dashboard. The existing `initializeCompactMode()` logic in `app/static/js/main.js` will attach the click handler.

### Compact layout without the button

Without `#compactToggle`, the page loads **expanded**. `localStorage` `compactMode` is only applied when the toggle exists.

---

## Downloadable models: how many show before “View More”

The first batch of **Downloadable Models** cards is controlled in `app/static/js/main.js`:

- Constant: **`INITIAL_DOWNLOADABLE_VISIBLE`** (default **48**).

Increase or decrease that number and refresh the page (no server restart required for static JS after rebuild/cache-bust).
