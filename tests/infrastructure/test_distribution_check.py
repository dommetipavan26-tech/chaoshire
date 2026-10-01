"""The install gate detects broken identity, dependency, CLI, license and asset metadata."""

import importlib.util
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def checker():
    spec = importlib.util.spec_from_file_location(
        "distribution_check_under_test", ROOT / "scripts/check_distribution.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "source"
    (root / "chaoshire/web/static").mkdir(parents=True)
    (root / "chaoshire/__init__.py").write_text('__version__ = "0.24.0"\n')
    (root / "chaoshire/web/index.html").write_text("<!doctype html><title>Fixture</title>")
    (root / "chaoshire/web/static/chaoshire.js").write_text("const fixture = 1;")
    (root / "backend.py").write_text('"""Fixture entry point."""\n')
    (root / "requirements.txt").write_text("httpx>=0.28.1\n")
    (root / "requirements-postgres.txt").write_text("psycopg2-binary>=2.9.13,<3\n")
    (root / "pyproject.toml").write_text(
        '[tool.setuptools.dynamic.optional-dependencies]\npostgres = {file=["requirements-postgres.txt"]}\n'
    )
    (root / "LICENSE").write_text("Fixture MIT license\n")
    return root


def artifacts(root, directory, *, edit=None, remove=None, extra=None):
    metadata = "\n".join(
        [
            "Metadata-Version: 2.4",
            "Name: chaoshire",
            "Version: 0.24.0",
            "Requires-Python: >=3.11",
            "License-Expression: MIT",
            "Requires-Dist: httpx>=0.28.1",
            "Requires-Dist: psycopg2-binary<3,>=2.9.13; extra == 'postgres'",
            "Provides-Extra: postgres",
            "",
        ]
    )
    files = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    dist = "chaoshire-0.24.0.dist-info/"
    files[dist + "METADATA"] = metadata.encode()
    files[dist + "entry_points.txt"] = b"[console_scripts]\nchaoshire = chaoshire.cli:main\n"
    files[dist + "licenses/LICENSE"] = (root / "LICENSE").read_bytes()
    if edit:
        files.update(edit)
    if remove:
        files.pop(remove)
    if extra:
        files.update(extra)
    wheel = directory / "fixture.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        # Root build/requirement docs belong in the sdist, not runtime wheel.
        for name, body in files.items():
            if name.startswith("chaoshire") or name == "backend.py":
                archive.writestr(name, body)
            elif extra and name in extra:
                archive.writestr(name, body)
    sdist = directory / "fixture.tar.gz"
    with tarfile.open(sdist, "w:gz") as archive:
        for path in root.rglob("*"):
            if path.is_file():
                archive.add(path, arcname="chaoshire-0.24.0/" + path.relative_to(root).as_posix())
    return wheel, sdist


def test_valid_wheel_and_sdist_are_checked_without_importing_source(checker, source, tmp_path):
    wheel, sdist = artifacts(source, tmp_path)
    result = checker.inspect_distributions(wheel, sdist, source)
    assert result == {
        "version": "0.24.0",
        "runtime_files": 4,
        "direct_dependencies": 1,
        "extras": ["postgres"],
    }


@pytest.mark.parametrize(
    "change", ["asset", "version", "dependencies", "extra", "cli", "license", "unsafe"]
)
def test_broken_distributions_fail_usefully(checker, source, tmp_path, change):
    dist = "chaoshire-0.24.0.dist-info/"
    wheel, _ = artifacts(source, tmp_path)
    with zipfile.ZipFile(wheel) as archive:
        meta = archive.read(dist + "METADATA")
    kwargs = {}
    if change == "asset":
        kwargs["edit"] = {"chaoshire/web/static/chaoshire.js": b"stale"}
    elif change == "version":
        kwargs["edit"] = {dist + "METADATA": meta.replace(b"Version: 0.24.0", b"Version: 0.0.0")}
    elif change == "dependencies":
        kwargs["edit"] = {dist + "METADATA": meta.replace(b"httpx>=0.28.1", b"httpx>=0.1")}
    elif change == "extra":
        kwargs["edit"] = {
            dist + "METADATA": meta.replace(
                b"psycopg2-binary<3,>=2.9.13", b"psycopg2-binary<3,>=2.0"
            )
        }
    elif change == "cli":
        kwargs["edit"] = {dist + "entry_points.txt": b"[console_scripts]\nchaoshire = wrong:main\n"}
    elif change == "license":
        kwargs["edit"] = {dist + "licenses/LICENSE": b"wrong"}
    else:
        kwargs["extra"] = {"tests/not-runtime.py": b"unexpected"}
    wheel, sdist = artifacts(source, tmp_path, **kwargs)
    with pytest.raises(ValueError):
        checker.inspect_distributions(wheel, sdist, source)


def test_missing_sdist_asset_and_nonliteral_version_are_rejected(checker, source, tmp_path):
    wheel, sdist = artifacts(source, tmp_path)
    (source / "chaoshire/web/index.html").write_text("updated")
    with pytest.raises(ValueError):
        checker.inspect_distributions(wheel, sdist, source)
    (source / "chaoshire/__init__.py").write_text("import os\n")
    with pytest.raises(ValueError, match="literal"):
        checker.source_version(source)
