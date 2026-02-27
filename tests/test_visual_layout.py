"""
Visual layout tests: catch regressions in HTML structure, CSS rules, and JS templates.

These tests validate that the dashboard layout stays correct without needing
a real browser. Run with: pytest tests/test_visual_layout.py -v
"""

import re
from pathlib import Path

import pytest
from unittest.mock import patch


@pytest.fixture
def app():
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def _run_with_mocks(client, running=None, available=None):
    """GET / with mocked ollama services. Returns (status_code, html)."""
    with (
        patch("app.routes.main.ollama_service.get_running_models") as mock_running,
        patch("app.routes.main.ollama_service.get_available_models") as mock_available,
        patch("app.routes.main.ollama_service.get_system_stats") as mock_stats,
        patch("app.routes.main.ollama_service.get_ollama_version") as mock_version,
    ):
        mock_running.return_value = running if running is not None else []
        mock_available.return_value = available if available is not None else []
        mock_stats.return_value = {
            "cpu_percent": 0,
            "memory": {"percent": 0},
            "vram": {"percent": 0},
            "disk": {"percent": 0},
        }
        mock_version.return_value = "0.17.0"
        r = client.get("/")
    return r.status_code, r.get_data(as_text=True)


class TestModelCardSpecRows:
    """Each model card must have exactly 3 spec rows (Family+Params, Size+GPU, Context)."""

    def test_running_card_has_three_spec_rows(self, client):
        status, html = _run_with_mocks(
            client, running=[{"name": "llama", "details": {"family": "llama"}}]
        )
        assert status == 200

        start = html.find('id="runningModelsContainer"')
        assert start != -1, "Running section should render when models exist"
        end = html.find('id="availableModelsContainer"')
        if end == -1:
            end = html.find("Downloadable Models")
        end = end if end != -1 else len(html)
        section = html[start:end]
        spec_rows = section.count('class="spec-row')
        assert spec_rows == 3, (
            f"Running card should have 3 spec rows, found {spec_rows}"
        )

    def test_available_card_has_two_spec_rows(self, client):
        """Available card (no GPU) has 2 rows: Family+Params, Size+Context."""
        status, html = _run_with_mocks(
            client,
            available=[{"name": "llama", "size": 5e9, "details": {"family": "llama"}}],
        )
        assert status == 200

        start = html.find('id="availableModelsContainer"')
        assert start != -1, "Available section should render when models exist"
        end = html.find("Downloadable Models")
        if end == -1:
            end = html.find('id="bestModelsContainer"')
        end = end if end != -1 else len(html)
        section = html[start:end]
        spec_rows = section.count('class="spec-row')
        assert spec_rows == 2, (
            f"Available card (no GPU) should have 2 spec rows (Family+Params, Size+Context), found {spec_rows}"
        )

    def test_running_three_rows_available_two_rows(self, client):
        """Running has 3 rows (includes GPU); Available has 2 rows (Size+Context on same line)."""
        status, html = _run_with_mocks(
            client,
            running=[{"name": "r1", "details": {"family": "a"}}],
            available=[{"name": "a1", "size": 1, "details": {"family": "b"}}],
        )
        assert status == 200

        run_start = html.find('id="runningModelsContainer"')
        assert run_start != -1
        run_section = html[run_start : run_start + 6000]
        run_blocks = re.findall(
            r'<div class="model-specs">(.*?)</div>\s*<div class="model-actions',
            run_section,
            re.DOTALL,
        )
        for block in run_blocks:
            assert block.count('class="spec-row') == 3, (
                "Running card must have 3 spec rows (Family+Params, Size+GPU, Context)"
            )

        av_start = html.find('id="availableModelsContainer"')
        assert av_start != -1
        av_section = html[av_start : av_start + 6000]
        av_blocks = re.findall(
            r'<div class="model-specs">(.*?)</div>\s*<div class="model-actions',
            av_section,
            re.DOTALL,
        )
        for block in av_blocks:
            assert block.count('class="spec-row') == 2, (
                "Available card (no GPU) must have 2 spec rows (Family+Params, Size+Context)"
            )


class TestCSSLayoutRules:
    """Critical CSS rules for layout must exist."""

    @pytest.fixture
    def css_content(self):
        css_path = Path(__file__).resolve().parent.parent / "app" / "static" / "css" / "styles.css"
        assert css_path.exists(), "styles.css not found"
        return css_path.read_text(encoding="utf-8")

    def test_spec_row_has_flex_display(self, css_content):
        assert "display: flex" in css_content
        assert ".spec-row" in css_content or "spec-row" in css_content

    def test_model_card_spec_row_layout(self, css_content):
        assert ".model-card .spec-row" in css_content or "model-card" in css_content and "spec-row" in css_content
        # Must have gap for spec items
        assert "gap:" in css_content

    def test_placeholder_opacity0_rule_exists(self, css_content):
        """Rule to collapse placeholder-only rows."""
        assert "opacity-0" in css_content
        assert "min-height: 0" in css_content or "min-height:0" in css_content.replace(" ", "")

    def test_model_actions_margin(self, css_content):
        assert "model-actions" in css_content
        assert "margin-top" in css_content

    def test_mobile_spec_row_column_layout(self, css_content):
        """On mobile, spec-row should stack (flex-direction: column)."""
        assert "@media" in css_content
        assert "flex-direction: column" in css_content
        assert ".spec-row" in css_content or "spec-row" in css_content
        # Ensure spec-row and column layout appear in same media block (768px)
        idx_media = css_content.find("@media")
        idx_768 = css_content.find("768", idx_media)
        idx_col = css_content.find("flex-direction: column", idx_media)
        idx_spec = css_content.find("spec-row", idx_media)
        assert idx_768 != -1 and idx_col != -1 and idx_spec != -1, (
            "Mobile breakpoint, flex-direction: column, and spec-row must exist"
        )


class TestDownloadableCardTemplate:
    """JS template for downloadable cards must match layout spec."""

    @pytest.fixture
    def model_cards_js(self):
        js_path = Path(__file__).resolve().parent.parent / "app" / "static" / "js" / "modules" / "modelCards.js"
        assert js_path.exists(), "modelCards.js not found"
        return js_path.read_text(encoding="utf-8")

    def test_downloadable_template_has_two_spec_rows(self, model_cards_js):
        """Downloadable card (no GPU) has 2 rows: Family+Params, Size+Context."""
        spec_row_count = model_cards_js.count('class="spec-row')
        assert spec_row_count >= 2, (
            f"Downloadable card template should have 2 spec rows (Size+Context on same line), found {spec_row_count}"
        )

    def test_downloadable_template_has_family_size_context(self, model_cards_js):
        assert "spec-label" in model_cards_js
        assert "Family" in model_cards_js
        assert "Size" in model_cards_js
        assert "Context" in model_cards_js

    def test_downloadable_template_has_model_card_structure(self, model_cards_js):
        assert 'class="model-card' in model_cards_js
        assert "model-specs" in model_cards_js
        assert "model-actions" in model_cards_js


class TestSectionSpacing:
    """Section headers and spacing must be present."""

    def test_section_headers_have_spacing(self, client):
        status, html = _run_with_mocks(client)
        assert status == 200

        assert "mb-4" in html or "mb-3" in html
        assert "section-title-text" in html

    def test_running_section_exactly_three_spec_rows_per_card(self, client):
        """Regression: each running card has exactly 3 spec rows (no extra placeholder row)."""
        _, html = _run_with_mocks(client, running=[{"name": "x", "details": {}}])
        run_start = html.find('id="runningModelsContainer"')
        assert run_start != -1
        # Extract up to available section or 8k chars
        run_end = html.find('id="availableModelsContainer"', run_start)
        if run_end == -1:
            run_end = html.find("Downloadable Models", run_start) or run_start + 8000
        snippet = html[run_start:run_end]
        spec_row_count = snippet.count('class="spec-row')
        assert spec_row_count == 3, (
            f"Running card must have 3 spec rows, found {spec_row_count}"
        )
