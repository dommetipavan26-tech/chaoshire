"""The repository-wide inventory fails usefully instead of promising formal verification."""

import importlib.util
import json
import struct
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def checker():
    spec = importlib.util.spec_from_file_location(
        "repository_check_under_test", REPO_ROOT / "scripts" / "check_repository.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def put(root: Path, path: str, content: str | bytes) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)


@pytest.mark.parametrize(
    ("path", "content", "check"),
    [
        ("module.py", '"""Example module."""\nx = 1\n', "Python AST"),
        ("values.json", '{"example": [1, 2]}', "strict JSON"),
        ("pyproject.toml", '[project]\nname = "test"\n', "TOML parse"),
        ("render.yaml", "services:\n  - name: test\n", "YAML parse/unique keys"),
        ("README.md", "# Example\n[Heading](#example)\n", "relative Markdown links/headings"),
    ],
)
def test_valid_source_formats(checker, tmp_path, path, content, check):
    put(tmp_path, path, content)
    result = checker.inspect_file(tmp_path, path)
    assert result["status"] == "PASS"
    assert check in result["checks"]
    assert result["bytes"] == len(content.encode())
    assert len(result["sha256"]) == 64


@pytest.mark.parametrize(
    ("path", "content"),
    [
        ("bad.py", "def unfinished(\n"),
        ("bad.json", '{"broken": }'),
        ("nonfinite.json", '{"value": NaN}'),
        ("bad.toml", '[project]\nname = "unterminated'),
        ("bad.yaml", "services: first\nservices: duplicate\n"),
    ],
)
def test_bad_syntax_and_duplicate_configuration_fail(checker, tmp_path, path, content):
    put(tmp_path, path, content)
    result = checker.inspect_file(tmp_path, path)
    assert result["status"] == "FAIL"
    assert result["errors"]


def test_workflow_parser_preserves_on_and_requires_permissions(checker, tmp_path):
    path = ".github/workflows/example.yml"
    content = "on: [push]\njobs:\n  test:\n    runs-on: ubuntu-latest\n"
    put(tmp_path, path, content)
    assert checker.inspect_file(tmp_path, path)["status"] == "FAIL"
    put(tmp_path, path, content + "permissions:\n  contents: read\n")
    assert checker.inspect_file(tmp_path, path)["status"] == "PASS"
    mutable = content + "permissions:\n  contents: read\n"
    mutable = mutable.replace(
        "runs-on: ubuntu-latest",
        "runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v7",
    )
    put(tmp_path, path, mutable)
    assert checker.inspect_file(tmp_path, path)["status"] == "FAIL"
    put(tmp_path, path, mutable.replace("@v7", "@" + "a" * 40))
    assert checker.inspect_file(tmp_path, path)["status"] == "PASS"


@pytest.mark.parametrize("target", ["missing.md", "guide.md#missing-heading", "../outside.md"])
def test_bad_relative_document_links_fail(checker, tmp_path, target):
    put(tmp_path, "README.md", f"# Overview\n[Guide]({target})\n")
    put(tmp_path, "guide.md", "# Present heading\n")
    assert checker.inspect_file(tmp_path, "README.md")["status"] == "FAIL"


def test_external_links_are_not_misrepresented_as_network_checks(checker, tmp_path):
    put(tmp_path, "README.md", "# Overview\n[Remote](https://not-fetched.example/a#b)\n")
    result = checker.inspect_file(tmp_path, "README.md")
    assert result["status"] == "PASS"
    assert "relative Markdown links/headings" in result["checks"]


def test_html_anchors_and_packaged_assets_are_checked(checker, tmp_path):
    path = "chaoshire/web/index.html"
    put(tmp_path, "chaoshire/web/static/style.css", "body{color:black}")
    put(
        tmp_path,
        path,
        '<link href="/static/style.css?v=__CSS_VERSION__"><a href="#content">Go</a><main id="content">OK</main>',
    )
    assert checker.inspect_file(tmp_path, path)["status"] == "PASS"
    put(tmp_path, path, '<main id="repeat"></main><aside id="repeat"></aside>')
    assert checker.inspect_file(tmp_path, path)["status"] == "FAIL"
    put(tmp_path, path, '<script src="/static/missing.js"></script>')
    assert checker.inspect_file(tmp_path, path)["status"] == "FAIL"


def test_png_checksum_is_verified(checker, tmp_path):
    source = (REPO_ROOT / "chaoshire/web/static/icons/icon-192.png").read_bytes()
    put(tmp_path, "image.png", source)
    assert checker.inspect_file(tmp_path, "image.png")["status"] == "PASS"
    damaged = bytearray(source)
    damaged[-5] ^= 1
    put(tmp_path, "image.png", damaged)
    assert checker.inspect_file(tmp_path, "image.png")["status"] == "FAIL"


def test_ico_image_bounds_are_verified(checker, tmp_path):
    source = (REPO_ROOT / "chaoshire/web/static/icons/favicon.ico").read_bytes()
    put(tmp_path, "favicon.ico", source)
    assert checker.inspect_file(tmp_path, "favicon.ico")["status"] == "PASS"
    damaged = bytearray(source)
    struct.pack_into("<I", damaged, 18, len(source) + 1)
    put(tmp_path, "favicon.ico", damaged)
    assert checker.inspect_file(tmp_path, "favicon.ico")["status"] == "FAIL"


def test_font_requires_its_license_and_modification_notice(checker, tmp_path):
    source = (REPO_ROOT / "chaoshire/web/static/fonts/besley-latin.woff2").read_bytes()
    put(tmp_path, "font.woff2", source)
    assert checker.inspect_file(tmp_path, "font.woff2")["status"] == "FAIL"
    put(tmp_path, "OFL.txt", "License notice\n")
    put(tmp_path, "SUBSET.txt", "Subset notice\n")
    assert checker.inspect_file(tmp_path, "font.woff2")["status"] == "PASS"


@pytest.mark.parametrize(
    "path", [".env", "data/raw.csv", "reports/generated/out.md", ".venv/module.py"]
)
def test_local_state_is_not_allowed_in_version_control(checker, tmp_path, path):
    put(tmp_path, path, "local state\n")
    assert checker.inspect_file(tmp_path, path)["status"] == "FAIL"


def test_secret_signatures_do_not_echo_the_matched_contents(checker, tmp_path):
    secret_fixture = "-----BEGIN" + " PRIVATE KEY-----\nprivate contents\n"
    put(tmp_path, "credentials.txt", secret_fixture)
    result = checker.inspect_file(tmp_path, "credentials.txt")
    assert result["status"] == "FAIL"
    assert "Potential credential" in result["errors"][0]
    assert secret_fixture not in json.dumps(result)
    assert "private contents" not in json.dumps(result)


def test_missing_node_is_an_explicit_warning_or_required_failure(checker, tmp_path, monkeypatch):
    put(tmp_path, "behavior.js", "const test = 1;\n")
    monkeypatch.setattr(checker.shutil, "which", lambda command: None)
    assert checker.inspect_file(tmp_path, "behavior.js")["status"] == "REVIEW"
    assert checker.inspect_file(tmp_path, "behavior.js", require_node=True)["status"] == "FAIL"


def test_requirement_includes_cannot_be_missing_or_escape_the_repository(checker, tmp_path):
    put(tmp_path, "requirements-dev.txt", "-r requirements.txt\n")
    assert checker.inspect_file(tmp_path, "requirements-dev.txt")["status"] == "FAIL"
    put(tmp_path, "requirements.txt", "fastapi>=0.135.4,<1\n")
    assert checker.inspect_file(tmp_path, "requirements-dev.txt")["status"] == "PASS"
    put(tmp_path, "requirements-dev.txt", "-r ../outside.txt\n")
    assert checker.inspect_file(tmp_path, "requirements-dev.txt")["status"] == "FAIL"


def test_model_digest_is_checked_without_importing_the_model(checker, tmp_path):
    path = "chaoshire/artifacts/trained_model.json"
    model = json.loads((REPO_ROOT / path).read_text(encoding="utf-8"))
    put(tmp_path, path, json.dumps(model))
    assert checker.inspect_file(tmp_path, path)["status"] == "PASS"
    model["coefficients"]["intercept"] += 1
    put(tmp_path, path, json.dumps(model))
    assert checker.inspect_file(tmp_path, path)["status"] == "FAIL"


def test_inventory_escapes_descriptions_and_states_verification_limits(checker, tmp_path):
    put(tmp_path, "example.py", '"""<img src=x> | Untrusted title."""\nx = 1\n')
    report = checker.audit_files(tmp_path, ["example.py", "example.py"])
    assert report["files_checked"] == 1
    markdown = checker.inventory_markdown(report)
    assert "&lt;img src=x&gt; \\| Untrusted title." in markdown
    assert "<img src=x>" not in markdown
    assert "does **not** certify runtime behavior or production security" in markdown


def test_cli_writes_json_and_markdown_and_strict_fails_on_warnings(
    checker, tmp_path, monkeypatch, capsys
):
    put(tmp_path, "unassigned/note.txt", "Unclassified source\n")
    monkeypatch.setattr(checker, "discover_files", lambda root: ["unassigned/note.txt"])
    args = ["--root", str(tmp_path), "--json", "inventory.json", "--inventory", "inventory.md"]
    assert checker.main(args) == 0
    assert json.loads((tmp_path / "inventory.json").read_text())["warnings"] == 1
    assert (tmp_path / "inventory.md").is_file()
    assert checker.main([*args, "--strict"]) == 1
    assert "1 files, 0 errors, 1 warnings" in capsys.readouterr().out


def test_discovery_covers_source_and_excludes_ignored_local_state(checker):
    files = checker.discover_files(REPO_ROOT)
    assert "scripts/check_repository.py" in files
    assert "tests/infrastructure/test_repository_inventory.py" in files
    assert not any(path.startswith((".git/", ".venv/", "reports/generated/")) for path in files)


def test_yaml_does_not_construct_python_objects(checker, tmp_path):
    put(tmp_path, "malicious.yaml", "!!python/object/apply:os.system ['echo should-not-run']\n")
    assert checker.inspect_file(tmp_path, "malicious.yaml")["status"] == "FAIL"


def test_svg_does_not_expand_xml_entities(checker, tmp_path):
    text = '<!DOCTYPE svg [<!ENTITY local "expanded">]><svg xmlns="http://www.w3.org/2000/svg">&local;</svg>'
    put(tmp_path, "diagram.svg", text)
    assert checker.inspect_file(tmp_path, "diagram.svg")["status"] == "FAIL"
