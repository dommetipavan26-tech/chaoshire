"""Verify distribution metadata/data and smoke a fresh runtime-only wheel installation.

Run after `python -m build`:
    python scripts/check_distribution.py --wheel dist/chaoshire-*.whl --sdist dist/chaoshire-*.tar.gz

Uses an isolated venv and working directory, never an editable install, and
clears application integration variables in the child before any imports.
No live PostgreSQL/vendor/webhook services or production state are contacted.
Generated environments/reports remain in ignored reports/generated/.
"""

from __future__ import annotations

import argparse
import ast
import configparser
import email
import json
import os
import subprocess
import tarfile
import tempfile
import tomllib
import venv
import zipfile
from pathlib import Path
from typing import Any

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]
ASSET_SUFFIXES = {".py", ".json", ".html", ".css", ".js", ".png", ".woff2", ".ico", ".txt"}


def source_version(root: Path = ROOT) -> str:
    tree = ast.parse((root / "chaoshire/__init__.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets
        ):
            return str(ast.literal_eval(node.value))
    raise ValueError("Package version is not a literal __version__ assignment")


def requirements(path: Path) -> list[Requirement]:
    return [
        Requirement(line.strip())
        for line in path.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def inspect_distributions(wheel: Path, sdist: Path | None, root: Path = ROOT) -> dict[str, Any]:
    version = source_version(root)
    expected = [
        p.relative_to(root).as_posix()
        for p in (root / "chaoshire").rglob("*")
        if p.is_file() and p.suffix in ASSET_SUFFIXES and "__pycache__" not in p.parts
    ]
    expected.append("backend.py")
    with zipfile.ZipFile(wheel) as archive:
        if archive.testzip() is not None:
            raise ValueError("Wheel contains a corrupt ZIP entry")
        names = archive.namelist()
        if any(
            name.startswith(("tests/", "docs/", "scripts/", "reports/", ".venv/"))
            or ".." in Path(name).parts
            or name.startswith("/")
            for name in names
        ):
            raise ValueError("Wheel contains non-runtime or unsafe file paths")
        for name in expected:
            if archive.read(name) != (root / name).read_bytes():
                raise ValueError(f"Missing or stale runtime file in wheel: {name}")
        metadata_name = f"chaoshire-{version}.dist-info/METADATA"
        meta = email.message_from_bytes(archive.read(metadata_name))
        if (
            meta["Name"] != "chaoshire"
            or meta["Version"] != version
            or meta["Requires-Python"] != ">=3.11"
            or meta["License-Expression"] != "MIT"
        ):
            raise ValueError("Distribution identity, Python floor or license metadata is wrong")
        all_requirements = [Requirement(value) for value in meta.get_all("Requires-Dist", [])]
        direct = {r for r in all_requirements if r.marker is None}
        if direct != set(requirements(root / "requirements.txt")):
            raise ValueError("Wheel runtime dependency declarations do not match requirements.txt")
        project = tomllib.loads((root / "pyproject.toml").read_text())
        extras = project["tool"]["setuptools"]["dynamic"]["optional-dependencies"]
        for extra, definition in extras.items():
            declared = []
            for filename in definition["file"]:
                declared.extend(requirements(root / filename))
            provided = {
                Requirement(str(r).split(";", 1)[0].strip())
                for r in all_requirements
                if r.marker is not None and r.marker.evaluate({"extra": extra})
            }
            if provided != set(declared):
                raise ValueError(f"Wheel extra '{extra}' does not match its manifest")
        entrypoints = configparser.ConfigParser()
        entrypoints.read_string(
            archive.read(f"chaoshire-{version}.dist-info/entry_points.txt").decode()
        )
        if entrypoints["console_scripts"].get("chaoshire") != "chaoshire.cli:main":
            raise ValueError("Console CLI entry point is missing")
        if (
            archive.read(f"chaoshire-{version}.dist-info/licenses/LICENSE")
            != (root / "LICENSE").read_bytes()
        ):
            raise ValueError("Wheel license file is missing or stale")
    if sdist is not None:
        with tarfile.open(sdist) as archive:
            for name in [
                *expected,
                "requirements.txt",
                *(f for extra in extras.values() for f in extra["file"]),
            ]:
                member = archive.extractfile(f"chaoshire-{version}/{name}")
                if member is None or member.read() != (root / name).read_bytes():
                    raise ValueError(f"Missing or stale source-distribution file: {name}")
    return {
        "version": version,
        "runtime_files": len(expected),
        "direct_dependencies": len(direct),
        "extras": sorted(extras),
    }


SMOKE = r"""
import copy, importlib.metadata, importlib.util, json, os, subprocess, sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
expected_version = sys.argv[2]
assert not any(k.startswith("CHAOSHIRE_REMOTE") or k == "CHAOSHIRE_DATABASE_URL" for k in os.environ)
os.environ.update(CHAOSHIRE_DB_BACKEND="sqlite", CHAOSHIRE_DB_PATH=str(Path.cwd()/"smoke.db"), CHAOSHIRE_RATE_LIMIT_PER_MINUTE="0", CHAOSHIRE_WRITE_RATE_LIMIT_PER_MINUTE="0", CHAOSHIRE_API_KEY="distribution-test-key")
import chaoshire, backend
from chaoshire.app import app
from chaoshire.evidence import verify_evidence_bundle
from chaoshire.training import load_artifact
from fastapi.testclient import TestClient
assert Path(chaoshire.__file__).resolve().is_relative_to(root)
assert chaoshire.__version__ == importlib.metadata.version("chaoshire") == expected_version
assert backend.app is app
assert importlib.util.find_spec("sklearn") is None
assert importlib.util.find_spec("pytest") is None
assert importlib.util.find_spec("psycopg2") is None
load_artifact()
with TestClient(app) as client:
    for path in ("/", "/privacy", "/terms", "/api/ready", "/api/meta", "/api/demo", "/static/chaoshire.css", "/static/chaoshire.js", "/static/fonts/besley-latin.woff2", "/icons/icon-192.png", "/favicon.ico", "/social-preview.png", "/service-worker.js"):
        r=client.get(path)
        assert r.status_code == 200, (path,r.status_code)
    assert "__JS_VERSION__" not in client.get("/").text
    assert client.get("/api/meta").json()["build"]["version"] == expected_version
    for model,total in (("legacy",32),("fair",84),("trained",80)):
        assert client.get("/api/audit",params={"model":model}).json()["certificate"]["total"] == total
    bad=client.post("/api/evidence/verify",json={"bundle":{"payload":{},"integrity":{"digest":"é"}}})
    assert bad.status_code == 200 and bad.json()["valid"] is False
console = root / ("Scripts/chaoshire.exe" if os.name=="nt" else "bin/chaoshire")
def command(args, code=0):
    r=subprocess.run([str(console),*args],capture_output=True,text=True)
    assert r.returncode==code,(args,r.returncode,r.stdout,r.stderr)
    return r
command(["--help"])
assert json.loads(command(["gate","--baseline","legacy","--candidate","trained"]).stdout)["passed"]
assert not json.loads(command(["gate","--baseline","fair","--candidate","trained"],1).stdout)["passed"]
command(["review","--model","legacy"])
command(["report","--model","trained","--output","audit.html"])
assert "80" in Path("audit.html").read_text()
command(["report","--model","trained","--format","pdf","--output","audit.pdf"])
assert Path("audit.pdf").read_bytes().startswith(b"%PDF")
command(["evidence","--model","trained","--output","evidence.json"])
bundle=json.loads(Path("evidence.json").read_text())
assert verify_evidence_bundle(bundle)["valid"]
bundle["payload"]["audit"]["certificate"]["total"]+=1
assert not verify_evidence_bundle(bundle)["valid"]
assert subprocess.run([sys.executable,"-m","chaoshire","--help"],capture_output=True).returncode==0
print("Installed-wheel smoke PASS: isolated import/cwd, runtime-only deps, assets/model, backend, console/module CLI, gates, HTML/PDF and evidence")
"""


def smoke_install(wheel: Path, constraints: Path | None, version: str, work_root: Path) -> None:
    work_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="installed-wheel-", dir=work_root) as directory:
        workspace = Path(directory)
        environment = workspace / "venv"
        venv.create(environment, with_pip=True, system_site_packages=False)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        install = [str(python), "-m", "pip", "install", "--disable-pip-version-check", str(wheel)]
        if constraints:
            install.extend(["--constraint", str(constraints)])
        subprocess.run(install, cwd=workspace, check=True)
        subprocess.run([str(python), "-m", "pip", "check"], cwd=workspace, check=True)
        smoke = workspace / "smoke.py"
        smoke.write_text(SMOKE)
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("CHAOSHIRE_", "RENDER_"))
            and key not in {"PYTHONPATH", "PYTHONHOME"}
        }
        subprocess.run(
            [str(python), str(smoke), str(environment), version], cwd=workspace, env=env, check=True
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--sdist", type=Path)
    parser.add_argument("--constraints", type=Path)
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument(
        "--work-dir", type=Path, default=ROOT / "reports/generated/distribution-check"
    )
    args = parser.parse_args(argv)
    result = inspect_distributions(
        args.wheel.resolve(), args.sdist.resolve() if args.sdist else None
    )
    print("Distribution metadata/assets PASS:", json.dumps(result), flush=True)
    if not args.metadata_only:
        smoke_install(
            args.wheel.resolve(),
            args.constraints.resolve() if args.constraints else None,
            result["version"],
            args.work_dir.resolve(),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
