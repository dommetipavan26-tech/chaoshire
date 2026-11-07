"""Interactive, dependency-free SVG charts on the dashboard."""

from pathlib import Path

WEB_DIR = Path(__file__).resolve().parents[2] / "chaoshire" / "web"
SCRIPT = (WEB_DIR / "static" / "chaoshire.js").read_text(encoding="utf-8")
STYLES = (WEB_DIR / "static" / "chaoshire.css").read_text(encoding="utf-8")


def test_charts_are_inline_svg_with_tooltips_and_data_table_twins():
    assert "function barChartSVG" in SCRIPT
    assert 'class="chart-svg"' in SCRIPT
    assert "<title>" in SCRIPT  # hover/focus tooltip per bar
    assert 'tabindex="0"' in SCRIPT  # keyboard-focusable bars
    assert "function chartDataTable" in SCRIPT
    assert "Chart data (" in SCRIPT


def test_overview_chart_has_attribute_and_metric_controls():
    assert 'id="fairness-chart"' in SCRIPT
    assert 'id="chart-attribute"' in SCRIPT
    assert 'data-chart-metric="selection_rate"' in SCRIPT
    assert 'data-chart-metric="tpr"' in SCRIPT
    assert "renderFairnessChart" in SCRIPT
    assert "LAST_AUDIT" in SCRIPT


def test_chaos_results_are_charted_next_to_the_cards():
    assert 'id="chaos-chart"' in SCRIPT
    assert "Observed rate by experiment" in SCRIPT


def test_chart_fills_come_from_css_classes_not_inline_styles():
    chart_function = SCRIPT.split("function barChartSVG")[1].split("function chartDataTable")[0]
    assert "style=" not in chart_function  # CSP: no inline style attributes
    for class_name in (".chart-bar.ok", ".chart-bar.bad", ".chart-bar.warn", ".chart-svg"):
        assert class_name in STYLES


def test_history_view_sends_the_audit_access_token():
    assert "X-Audit-Access-Token" in SCRIPT
    assert 'id="history-token"' in SCRIPT
    assert "audit_access_token" in SCRIPT  # shown once in the upload result
