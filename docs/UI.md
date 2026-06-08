# UI customization

## Downloadable models: how many show before "View More"

The first batch of **Downloadable Models** cards is controlled in `app/static/js/main.js`:

- Constant: **`INITIAL_DOWNLOADABLE_VISIBLE`** (default **48**).

Increase or decrease that number and refresh the page (no server restart required for static JS after rebuild/cache-bust).
