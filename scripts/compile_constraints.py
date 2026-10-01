"""Resolve reviewable Linux/CPython constraints, including the isolated build backend.

Install requirements-maintenance.txt, then run:
    python scripts/compile_constraints.py

Constraints pin versions, not credentials, index URLs, or vendored packages.
The 3.12 file can be resolved without a 3.12 interpreter, but only that runtime's
actual CI execution validates it. Library requirements remain compatibility
ranges; use -c constraints/requirements-py311.txt for reproducible development.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = (
    "requirements-dev.txt",
    "requirements-browser.txt",
    "requirements-examples.txt",
    "requirements-postgres.txt",
    "requirements-maintenance.txt",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-version", action="append", choices=["3.11", "3.12"])
    parser.add_argument("--output-dir", type=Path, default=ROOT / "constraints")
    args = parser.parse_args(argv)
    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit("Install requirements-maintenance.txt to use uv constraint resolution.")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    scratch = ROOT / "reports/generated"
    scratch.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "UV_PYTHON_DOWNLOADS": "never"}
    with tempfile.TemporaryDirectory(prefix="constraints-", dir=scratch) as directory:
        requirements = Path(directory) / "all.in"
        build = tomllib.loads((ROOT / "pyproject.toml").read_text())["build-system"]["requires"]
        requirements.write_text(
            "\n".join([*build, *(f"-r {ROOT / name}" for name in MANIFESTS)]) + "\n"
        )
        for version in args.python_version or ["3.11", "3.12"]:
            temporary = Path(directory) / f"py{version}.txt"
            subprocess.run(
                [
                    uv,
                    "pip",
                    "compile",
                    str(requirements),
                    "--python-version",
                    version,
                    "--python-platform",
                    "x86_64-unknown-linux-gnu",
                    "--no-python-downloads",
                    "--no-annotate",
                    "--no-header",
                    "--output-file",
                    str(temporary),
                ],
                cwd=ROOT,
                env=env,
                check=True,
            )
            target = args.output_dir / f"requirements-py{version.replace('.', '')}.txt"
            header = (
                f"# Linux x86_64 / CPython {version}; generated with scripts/compile_constraints.py\n"
                "# Includes runtime, developer, browser, PostgreSQL, maintenance and build-backend versions.\n"
                "# Version constraints, not install inputs or a claim of cross-platform/runtime verification.\n"
                "# Refresh deliberately; rerun security, training, test and distribution gates.\n"
            )
            target.write_text(header + temporary.read_text())
            print(f"Wrote {target.relative_to(ROOT) if target.is_relative_to(ROOT) else target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
