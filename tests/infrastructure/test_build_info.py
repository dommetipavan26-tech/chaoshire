"""The committed build facts must match a real test run.

``chaoshire/build_info.py`` exists because the landing page used to advertise
v0.21.0 while the package said v0.22.0 and a browser test asserted the stale
value. Most of its numbers are now *derived* from the running package, so they
cannot drift. Two are not: the automated-test count and the coverage percentage
are properties of a test run, so ``scripts/check_build_info.py`` re-derives them
in CI. These tests hold the same line from inside the suite, and also check that
nothing downstream hardcodes a copy.
"""

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
from conftest import operator_client

import chaoshire
from chaoshire.build_info import (
    AUTOMATED_TESTS,
    CHAOS_EXPERIMENTS,
    DEMO_CANDIDATES,
    PACKAGE_COVERAGE,
    REFERENCE_MODELS,
    VERSION,
    build_info,
)
from chaoshire.chaos import CHAOS_TESTS
from chaoshire.data import DEMO_DATA
from chaoshire.models import MODEL_META

REPO_ROOT = Path(__file__).resolve().parents[2]

client = operator_client()


def _load_check_module() -> ModuleType:
    """Load ``scripts/check_build_info.py`` as a module so it can be probed."""
    path = REPO_ROOT / "scripts" / "check_build_info.py"
    spec = importlib.util.spec_from_file_location("check_build_info_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_version_is_the_package_version_and_nothing_else():
    assert VERSION == chaoshire.__version__
    assert re.fullmatch(r"\d+\.\d+\.\d+", VERSION)


def test_derived_counts_cannot_drift():
    assert CHAOS_EXPERIMENTS == len(CHAOS_TESTS)
    assert REFERENCE_MODELS == len(MODEL_META)
    assert DEMO_CANDIDATES == len(DEMO_DATA)
    assert CHAOS_EXPERIMENTS > 0 and REFERENCE_MODELS >= 3 and DEMO_CANDIDATES > 100


def test_the_two_run_dependent_facts_are_wellformed():
    assert isinstance(AUTOMATED_TESTS, int)
    assert AUTOMATED_TESTS >= 100
    assert re.fullmatch(r"\d+\.\d%", PACKAGE_COVERAGE), PACKAGE_COVERAGE
    assert 90.0 <= float(PACKAGE_COVERAGE.rstrip("%")) <= 100.0


def test_build_info_payload_is_what_the_api_serves():
    payload = build_info()
    assert payload == {
        "version": VERSION,
        "automated_tests": AUTOMATED_TESTS,
        "package_coverage": PACKAGE_COVERAGE,
        "chaos_experiments": CHAOS_EXPERIMENTS,
        "reference_models": REFERENCE_MODELS,
        "demo_candidates": DEMO_CANDIDATES,
        "repository_backend": payload["repository_backend"],
        "verification": payload["verification"],
    }
    assert payload["repository_backend"] in ("sqlite", "postgres")
    assert "checked against a real pytest run" in payload["verification"]
    assert client.get("/api/meta").json()["build"] == payload


def test_the_collected_test_count_matches_the_committed_one():
    """The drift guard, run for real.

    Slow, but this is the assertion that stops "169 automated tests" from
    becoming fiction the next time someone deletes a test module.
    """
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "--no-cov",
            "-p",
            "no:cacheprovider",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout[-2000:]
    collected = sum(
        1 for line in completed.stdout.splitlines() if "::" in line and not line.startswith(" ")
    )
    assert collected == AUTOMATED_TESTS


def test_the_check_script_passes_on_a_clean_tree(monkeypatch, capsys):
    """Exit code and message on a tree with no drift.

    ``test_the_collected_test_count_matches_the_committed_one`` already proves the
    real collection agrees with the committed figure, so the count is stubbed here
    to keep the suite from spawning pytest three times.
    """
    checker = _load_check_module()
    monkeypatch.setattr(checker, "collected_test_count", lambda: AUTOMATED_TESTS)
    assert checker.main([]) == 0
    out = capsys.readouterr().out
    assert "build_info OK" in out
    assert f"{AUTOMATED_TESTS} tests" in out
    assert f"coverage {PACKAGE_COVERAGE}" in out


def test_the_check_script_detects_a_stale_count(monkeypatch, capsys):
    """Prove the guard actually fails, rather than trusting that it would.

    The module is loaded from its own path and only its committed constant is
    doctored; the collected-test count still comes from a real pytest run, so a
    genuine mismatch is what makes this exit non-zero.
    """
    checker = _load_check_module()
    monkeypatch.setattr(checker, "AUTOMATED_TESTS", AUTOMATED_TESTS + 1)
    monkeypatch.setattr(checker, "collected_test_count", lambda: AUTOMATED_TESTS)
    assert checker.main([]) == 1
    stderr = capsys.readouterr().err
    assert "build_info drift detected" in stderr
    assert f"AUTOMATED_TESTS is {AUTOMATED_TESTS + 1}" in stderr
    assert f"pytest collects {AUTOMATED_TESTS}" in stderr
    assert "Fix chaoshire/build_info.py" in stderr


def test_the_check_script_detects_stale_coverage(tmp_path, monkeypatch, capsys):
    checker = _load_check_module()
    coverage_json = tmp_path / "coverage.json"
    coverage_json.write_text(json.dumps({"totals": {"percent_covered": 42.4567}}), encoding="utf-8")
    monkeypatch.setattr(checker, "collected_test_count", lambda: AUTOMATED_TESTS)
    assert checker.main(["--coverage-json", str(coverage_json)]) == 1
    stderr = capsys.readouterr().err
    assert f"PACKAGE_COVERAGE is {PACKAGE_COVERAGE} but coverage reports 42.5%" in stderr


def test_the_check_script_accepts_a_matching_coverage_report(tmp_path, monkeypatch, capsys):
    checker = _load_check_module()
    coverage_json = tmp_path / "coverage.json"
    coverage_json.write_text(
        json.dumps({"totals": {"percent_covered": float(PACKAGE_COVERAGE.rstrip("%"))}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(checker, "collected_test_count", lambda: AUTOMATED_TESTS)
    assert checker.main(["--coverage-json", str(coverage_json)]) == 0
    assert "build_info OK" in capsys.readouterr().out


def test_the_check_script_refuses_to_guess_when_coverage_json_is_missing(tmp_path, monkeypatch):
    checker = _load_check_module()
    monkeypatch.setattr(checker, "collected_test_count", lambda: AUTOMATED_TESTS)
    with pytest.raises(SystemExit, match="does not exist"):
        checker.main(["--coverage-json", str(tmp_path / "absent.json")])


#: Living documentation. CHANGELOG.md and docs/planning/TODO.md are historical
#: records: an old entry quoting a past test count is still correct for that release.
DOCUMENTED_FILES = ("README.md", "SECURITY.md", "CONTRIBUTING.md")

TEST_COUNT_PATTERN = re.compile(r"(\d{2,4}) (?:automated )?tests")
COVERAGE_PATTERN = re.compile(r"(\d{2}\.\d)% (?:package )?coverage")


def _living_documentation() -> list[Path]:
    docs = REPO_ROOT / "docs"
    return [
        *(REPO_ROOT / name for name in DOCUMENTED_FILES),
        *(p for p in docs.rglob("*.md") if p != docs / "planning" / "TODO.md"),
    ]


def test_the_readme_quotes_the_same_numbers_and_all_model_variants():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    match = re.search(
        r"\*\*current source\s+baseline\*\*, measured locally, contains \*\*(\d+) tests with ([\d.]+%) package coverage\*\*",
        readme,
    )
    assert match, "README no longer states the current source baseline in the expected form"
    assert int(match.group(1)) == AUTOMATED_TESTS
    assert match.group(2) == PACKAGE_COVERAGE

    # Keep the published table in sync with /api/meta, including the trained fixture.
    model_table = re.search(r"\| Model \(API/CLI ID\) \|.*?(?=\n\n)", readme, re.DOTALL)
    assert model_table, "README needs a table of all selectable models"
    for model_id, metadata in MODEL_META.items():
        assert f"| **{metadata['title']}** (`{model_id}`) |" in model_table.group(0)
    assert model_table.group(0).count("\n| **") == len(MODEL_META)


def test_no_living_document_quotes_a_stale_test_or_coverage_figure():
    """Every current-facing document agrees with a real test run.

    The portfolio case study and evidence documents are the ones reviewers read
    first, and they are the ones that quietly kept saying "98 tests, 97.65%" for
    two releases after that stopped being true.
    """
    stale: list[str] = []
    for document in _living_documentation():
        if not document.exists():
            continue
        text = document.read_text(encoding="utf-8")
        for found in TEST_COUNT_PATTERN.findall(text):
            if int(found) != AUTOMATED_TESTS:
                stale.append(f"{document.name}: {found} tests")
        for found in COVERAGE_PATTERN.findall(text):
            if f"{found}%" != PACKAGE_COVERAGE:
                stale.append(f"{document.name}: {found}% coverage")
    assert not stale, "stale figures: " + "; ".join(sorted(set(stale)))


def test_the_landing_page_reads_the_numbers_instead_of_hardcoding_them():
    """The proof strip is rendered from /api/meta, never baked into the HTML.

    This is the exact failure mode ``build_info.py`` exists to prevent: the page
    once advertised v0.21.0 while the package said v0.22.0, and a browser test
    asserted the stale string, so nothing caught it.
    """
    html = (REPO_ROOT / "chaoshire" / "web" / "index.html").read_text(encoding="utf-8")

    # Every proof card ships an em-dash placeholder and is filled from `build`.
    proof = re.search(r'<div class="proof" id="proof">(.*?)</div>\s*</div>', html, re.DOTALL)
    assert proof, "the landing page no longer has a proof strip"
    for card_id in ("proof-tests", "proof-coverage", "proof-experiments", "proof-version"):
        assert f'id="{card_id}">\u2014<' in proof.group(0), card_id
        assert re.search('id="' + card_id + r'">[^<]*\d', proof.group(0)) is None, card_id

    for expression in (
        "b.automated_tests",
        "b.package_coverage",
        "b.chaos_experiments",
        "b.version",
    ):
        assert expression in html

    # No copy of the values anywhere in the page, in any rendering position.
    assert PACKAGE_COVERAGE not in html
    assert f">{AUTOMATED_TESTS}<" not in html
    assert f"'{AUTOMATED_TESTS}'" not in html
    assert VERSION not in html


def test_coverage_json_is_not_committed():
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "coverage.json" in gitignore


@pytest.mark.parametrize("key", ["version", "automated_tests", "package_coverage"])
def test_meta_exposes_each_build_fact(key):
    assert key in client.get("/api/meta").json()["build"]
