"""Unit checks for actionable live-browser timeout diagnostics."""

from scripts.check_live_site import format_tab_readiness_timeout


def test_tab_timeout_report_identifies_viewport_tab_and_browser_failures() -> None:
    detail = format_tab_readiness_timeout(
        width=1440,
        height=1000,
        tab="history",
        predicate="() => document.querySelector('#tab-history .history-overflow')",
        url="https://chaoshire.example/",
        title="ChaosHire",
        diagnostics={
            "console": ["TypeError: audits is undefined"],
            "page": ["TypeError: Cannot read properties of undefined"],
            "request": ["GET /api/audits (net::ERR_FAILED)"],
        },
        screenshot="reports/generated/live/tab-timeout-1440-history.png",
    )

    assert "1440x1000px tab=history" in detail
    assert "readiness predicate timed out after 60000ms" in detail
    assert "#tab-history .history-overflow" in detail
    assert "TypeError: audits is undefined" in detail
    assert "Cannot read properties of undefined" in detail
    assert "GET /api/audits" in detail
    assert "tab-timeout-1440-history.png" in detail


def test_tab_timeout_report_limits_old_events_and_handles_empty_diagnostics() -> None:
    detail = format_tab_readiness_timeout(
        width=320,
        height=700,
        tab="compare",
        predicate="() => !!document.querySelector('#cmpout .grid')",
        url="https://chaoshire.example/",
        title="ChaosHire",
        diagnostics={"console": [f"error {index}" for index in range(7)]},
        screenshot="capture failed: TimeoutError",
    )

    assert "error 0" not in detail
    assert "error 1" not in detail
    assert "error 2" in detail
    assert "error 6" in detail
    assert "page_errors=[none]" in detail
    assert "failed_requests=[none]" in detail
    assert "capture failed: TimeoutError" in detail
