# UI customization

Browser-side behavior for the dashboard. Static assets load on each request — hard refresh (`Ctrl+F5`) after editing JS/CSS.

---

## Refresh intervals

Set on the main page template (`app/templates/index.html`):

| Attribute | Element | Default | Effect |
|-----------|---------|---------|--------|
| `data-model-poll-interval` | Header meta group | `10` (seconds) | Background refresh of model lists |
| `data-stats-poll-interval` | System Resources block | `1` (second) | CPU / RAM / VRAM / disk sparklines |

Read by `getPollIntervalSec()` and `getStatsPollIntervalSec()` in `app/static/js/main.js`.

---

## Downloadable models list

The first batch of **Downloadable Models** cards is controlled in `app/static/js/main.js`:

- Constant: **`INITIAL_DOWNLOADABLE_VISIBLE`** (default **24**).

Increase or decrease that number and refresh the page.

---

## Ask? modal and side dock

Implemented in `app/static/js/modules/askModalDock.js` (loaded from `index.html`).

| Preference | Storage | Key | Values |
|------------|---------|-----|--------|
| Dock placement | `sessionStorage` | `askModalDockMode` | `center`, `float`, `left`, `right` |
| Split width (side dock) | `sessionStorage` | `askModalDockSplitPct` | Percent of viewport for Ask panel (default ~50) |
| Floating position | `sessionStorage` | `askModalFloatPos` | JSON `{ x, y }` |

Side dock: drag the modal header to snap left or right; drag the **center gutter** to resize. Preferences apply for the current browser session only.

Placeholder opacity for the Ask input is set in `app/static/css/styles.css` (`#askModelInput::placeholder`).

---

## Section collapse state

Persisted in **`localStorage`** (survives browser restarts):

| Key | Section |
|-----|---------|
| `availableModelsSectionCollapsed` | Available Models |
| `downloadableModelsSectionCollapsed` | Downloadable Models |

---

## Theme

Light / dark mode: `app/static/js/theme.js`, persisted under localStorage key **`theme`**.

---

## Capability filters

Filter buttons (reasoning, vision, tools, MoE) hide catalog cards in **Available** and **Downloadable** lists. **Running Models** always stay visible regardless of active filters.

---

## Related docs

- [Complete Guide](GUIDE.md) — proxy, MCP, per-model settings
- [README](../README.md) — screenshots of Ask?, side dock, and modals
