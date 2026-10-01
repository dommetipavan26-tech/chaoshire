"""Check every version-controlled/new source file without importing application code.

Run after installing requirements-dev.txt (Node.js is needed for JavaScript):
    python scripts/check_repository.py --require-node
    python scripts/check_repository.py --json reports/generated/repository-audit/inventory.json

This is a structural/hygiene check, not a substitute for pytest, type checking,
security scanning, real-browser tests, or a production assessment. Ignored local
state is intentionally excluded. --inventory writes an optional human-readable
file map; generated measurements belong under ignored reports/generated/.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
import tomllib
import zlib
from collections import Counter
from datetime import UTC, datetime
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import yaml
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from packaging.requirements import InvalidRequirement, Requirement

ROOT = Path(__file__).resolve().parents[1]
ROOT_ROLES = {
    "backend.py": "Deployment compatibility entry point",
    "pyproject.toml": "Package metadata and Python quality-tool configuration",
    "Dockerfile": "Non-root runtime container and readiness check",
    "render.yaml": "Render deployment Blueprint (not live deployment evidence)",
    ".env.example": "Documented environment defaults; no real credentials",
    ".gitignore": "Keep local secrets, state and generated output out of Git",
    ".dockerignore": "Keep local state and development assets out of the image",
    "README.md": "Project overview, quick start and current evidence",
    "CHANGELOG.md": "Release history (historical paths are intentional)",
    "CONTRIBUTING.md": "Contributor workflow and responsible-use rules",
    "SECURITY.md": "Security posture, limitations and private reporting",
    "LICENSE": "Project MIT license",
}
GENERATED_PARTS = {
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}
SECRET_SIGNATURES = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
)
MARKDOWN_LINK = re.compile(r"!?\[[^\]\n]*\]\((<[^>]+>|[^\s)]+)(?:\s+[^)]+)?\)")
SITE_ROUTES = {
    "/",
    "/privacy",
    "/terms",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/manifest.webmanifest",
    "/service-worker.js",
    "/robots.txt",
    "/sitemap.xml",
    "/favicon.ico",
    "/social-preview.png",
}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe standard tags, literal `on` keys, and no overwritten YAML mappings."""

    # YAML 1.1 treats GitHub Actions' `on` key as True. Copy the resolvers so
    # this parser can preserve it without mutating PyYAML's global SafeLoader.
    yaml_implicit_resolvers = {
        key: [(tag, regex) for tag, regex in resolvers if tag != "tag:yaml.org,2002:bool"]
        for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
    }

    def construct_mapping(self, node, deep=False):
        mapping = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in mapping:
                raise ValueError(f"Duplicate YAML key at line {key_node.start_mark.line + 1}")
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


class PageStructure(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.append(values["id"])
        if tag in {"a", "link", "img", "script"}:
            for attribute in ("href", "src"):
                if values.get(attribute):
                    self.links.append(values[attribute])


def discover_files(root: Path) -> list[str]:
    """Include uncommitted new source; do not traverse caches, .git or ignored state."""
    git = shutil.which("git")
    if git is None:
        raise OSError("git is unavailable")
    completed = subprocess.run(
        [git, "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        capture_output=True,
        check=True,
    )
    return sorted(set(completed.stdout.decode("utf-8").split("\0")) - {""})


def category(path: str) -> str:
    parts = Path(path).parts
    if len(parts) == 1:
        return "Root configuration and community"
    if parts[0] == "constraints":
        return "Dependency constraints"
    if parts[0] == ".github":
        return "Automation"
    if parts[0] == "chaoshire":
        return (
            "Web assets"
            if parts[1] == "web"
            else "Model artifact"
            if parts[1] == "artifacts"
            else "Application"
        )
    if parts[0] == "tests":
        return "Tests: " + (parts[1] if len(parts) > 2 else "shared fixtures")
    if parts[0] == "docs":
        return "Documentation: " + (parts[1] if len(parts) > 2 else "index")
    return {"scripts": "Maintenance scripts", "examples": "Integration examples"}.get(
        parts[0], "Unassigned"
    )


def role(path: str) -> str:
    if path in ROOT_ROLES:
        return ROOT_ROLES[path]
    if Path(path).name.startswith("requirements"):
        purpose = Path(path).stem.removeprefix("requirements").strip("-").replace("-", " ")
        return f"Dependency manifest: {purpose}" if purpose else "Runtime dependency manifest"
    if path.startswith(".github/workflows/"):
        return Path(path).stem.replace("-", " ").title() + " GitHub Actions workflow"
    if path == ".github/dependabot.yml":
        return "Scheduled Python and GitHub Actions dependency updates"
    if path.endswith((".png", ".ico")):
        return (
            "Portfolio screenshot"
            if path.startswith("docs/")
            else "Browser icon or social-sharing image"
        )
    if path.endswith(".woff2"):
        return "Self-hosted heading font; OFL license alongside it"
    if path.endswith(".css"):
        return "Responsive styles, typography and accessibility states"
    if path.endswith(".js"):
        return "Dashboard behavior; markup and styles live in separate files"
    return Path(path).name.replace("_", " ").replace("-", " ")


def markdown_anchors(text: str) -> set[str]:
    anchors: set[str] = set()
    duplicates: Counter[str] = Counter()
    fenced = False
    for line in text.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
        if fenced:
            continue
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if match:
            heading = re.sub(r"<[^>]*>", "", match.group(1)).lower()
            heading = re.sub(r"[^\w\- ]", "", heading).replace(" ", "-")
            number = duplicates[heading]
            duplicates[heading] += 1
            anchors.add(heading + (f"-{number}" if number else ""))
    return anchors


def check_markdown_links(root: Path, file: Path, text: str) -> None:
    # The explicit link syntax is checked; historical plain-code path mentions
    # in CHANGELOG/TODO are not rewritten or treated as current references.
    without_code = re.sub(r"```.*?```|~~~.*?~~~", "", text, flags=re.DOTALL)
    for match in MARKDOWN_LINK.finditer(without_code):
        target = match.group(1).strip("<>")
        parts = urlsplit(target)
        if parts.scheme or parts.netloc:
            continue  # Network availability and external anchors are separate checks.
        destination = (file.parent / unquote(parts.path)).resolve() if parts.path else file
        if not destination.is_relative_to(root.resolve()):
            raise ValueError("Relative Markdown link escapes the repository")
        if not destination.exists():
            raise ValueError(f"Broken relative Markdown link: {target}")
        if parts.fragment and destination.suffix == ".md":
            if unquote(parts.fragment) not in markdown_anchors(
                destination.read_text(encoding="utf-8")
            ):
                raise ValueError(f"Unknown Markdown heading: {target}")


def check_site_reference(root: Path, reference: str, ids: list[str] | None = None) -> None:
    reference = reference.replace("__PUBLIC_ORIGIN__", "")
    if reference.startswith("#"):
        if ids is not None and reference[1:] not in ids:
            raise ValueError(f"Unknown HTML anchor: {reference}")
        return
    parts = urlsplit(reference)
    if parts.scheme or parts.netloc:
        return
    path = unquote(parts.path)
    if path.startswith("/static/"):
        file = root / "chaoshire" / "web" / "static" / path.removeprefix("/static/")
    elif path.startswith("/icons/"):
        file = root / "chaoshire" / "web" / "static" / "icons" / path.removeprefix("/icons/")
    elif path in SITE_ROUTES or path.startswith("/api/"):
        return
    else:
        raise ValueError(f"Unknown site route or relative asset: {reference}")
    if (
        not file.resolve().is_relative_to((root / "chaoshire" / "web" / "static").resolve())
        or not file.is_file()
    ):
        raise ValueError(f"Missing or unsafe packaged asset: {reference}")


def check_png(data: bytes) -> tuple[int, int]:
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("Invalid PNG signature")
    offset = 8
    size = None
    seen_data = False
    while offset + 12 <= len(data):
        length = struct.unpack_from(">I", data, offset)[0]
        end = offset + 12 + length
        if end > len(data):
            raise ValueError("Truncated PNG chunk")
        kind = data[offset + 4 : offset + 8]
        content = data[offset + 8 : end - 4]
        checksum = struct.unpack_from(">I", data, end - 4)[0]
        if zlib.crc32(kind + content) & 0xFFFFFFFF != checksum:
            raise ValueError("PNG chunk checksum mismatch")
        if kind == b"IHDR":
            if offset != 8 or len(content) != 13:
                raise ValueError("Invalid PNG dimensions header")
            size = struct.unpack_from(">II", content)
            if not all(size):
                raise ValueError("PNG dimensions must be positive")
        elif kind == b"IDAT":
            seen_data = True
        elif kind == b"IEND":
            if length or end != len(data) or size is None or not seen_data:
                raise ValueError("Invalid PNG end/data structure")
            return size
        offset = end
    raise ValueError("Missing PNG end chunk")


def check_ico(data: bytes) -> None:
    if len(data) < 6 or data[:4] != b"\x00\x00\x01\x00":
        raise ValueError("Invalid ICO header")
    count = struct.unpack_from("<H", data, 4)[0]
    directory_end = 6 + 16 * count
    if not count or len(data) < directory_end:
        raise ValueError("Truncated/empty ICO directory")
    for index in range(count):
        length, offset = struct.unpack_from("<II", data, 6 + index * 16 + 8)
        if not length or offset < directory_end or offset + length > len(data):
            raise ValueError("Invalid ICO image bounds")
        if data[offset : offset + 8] == PNG_SIGNATURE:
            check_png(data[offset : offset + length])


def reject_nonfinite(value: str) -> None:
    raise ValueError(f"Non-finite JSON constant: {value}")


def inspect_file(root: Path, path: str, *, require_node: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": path,
        "category": category(path),
        "role": role(path),
        "checks": [],
        "errors": [],
        "warnings": [],
    }
    file = root / path
    try:
        if not file.resolve().is_relative_to(root.resolve()) or not file.is_file():
            raise ValueError("Missing file or path outside the repository")
        if (
            GENERATED_PARTS.intersection(file.relative_to(root).parts)
            or path.startswith(("data/", "reports/generated/", "build/", "dist/", "release/"))
            or file.suffix in {".db", ".pyc"}
            or file.name in {".env", ".coverage", "coverage.json"}
            or (file.name.startswith(".env.") and file.name != ".env.example")
        ):
            raise ValueError(
                "Local state, secrets or generated output must not be version-controlled"
            )
        data = file.read_bytes()
        result.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        if not data:
            raise ValueError("Empty file")
        if len(data) > 5_000_000:
            result["warnings"].append("Large tracked file: review external storage/LFS policy")
        suffix = file.suffix
        if suffix == ".png":
            result["dimensions"] = check_png(data)
            result["checks"].append("PNG chunks/CRC/dimensions")
        elif suffix == ".ico":
            check_ico(data)
            result["checks"].append("ICO directory/image bounds")
        elif suffix == ".woff2":
            if (
                len(data) < 48
                or data[:4] != b"wOF2"
                or struct.unpack_from(">I", data, 8)[0] != len(data)
            ):
                raise ValueError("Invalid WOFF2 header/length")
            for notice in ("OFL.txt", "SUBSET.txt"):
                if not (file.parent / notice).is_file():
                    raise ValueError("Missing font license/modification notice")
            result["checks"].append("WOFF2 header/length/license notices")
        else:
            text = data.decode("utf-8")
            result["checks"].append("UTF-8/nonempty")
            if any(pattern.search(text) for pattern in SECRET_SIGNATURES):
                raise ValueError("Potential credential/private-key signature; review privately")
            result["checks"].append("limited secret-signature scan")
            if suffix == ".py":
                tree = ast.parse(text, filename=path)
                doc = ast.get_docstring(tree)
                if doc:
                    result["role"] = doc.splitlines()[0]
                result["checks"].append("Python AST")
            elif suffix == ".json":
                payload = json.loads(text, parse_constant=reject_nonfinite)
                result["checks"].append("strict JSON")
                if path == "chaoshire/artifacts/trained_model.json":
                    coefficients = {
                        key: float(value) for key, value in payload["coefficients"].items()
                    }
                    canonical = json.dumps(
                        coefficients, sort_keys=True, separators=(",", ":"), allow_nan=False
                    ).encode()
                    if (
                        payload["coefficient_digest"]
                        != "sha256:" + hashlib.sha256(canonical).hexdigest()
                    ):
                        raise ValueError("Trained-model coefficient digest mismatch")
                    result["checks"].append("model coefficient digest")
            elif suffix == ".toml":
                tomllib.loads(text)
                result["checks"].append("TOML parse")
            elif suffix in {".yml", ".yaml"}:
                loader = UniqueKeyLoader(text)
                try:
                    payload = loader.get_single_data()
                finally:
                    loader.dispose()
                if not isinstance(payload, dict):
                    raise ValueError("YAML configuration must be a mapping")
                if (
                    path.startswith(".github/workflows/")
                    and not {"on", "jobs", "permissions"} <= payload.keys()
                ):
                    raise ValueError("Workflow is missing triggers, jobs or explicit permissions")
                if path.startswith(".github/workflows/"):
                    for job in payload["jobs"].values():
                        for step in job.get("steps", []):
                            action = step.get("uses", "")
                            if (
                                action
                                and not action.startswith("./")
                                and re.fullmatch(r"[^@]+@[0-9a-f]{40}", action) is None
                            ):
                                raise ValueError(
                                    "External workflow Actions must be pinned to full commit IDs"
                                )
                    result["checks"].append("immutable external Action refs")
                result["checks"].append("YAML parse/unique keys")
            elif suffix == ".md":
                check_markdown_links(root, file, text)
                result["checks"].append("relative Markdown links/headings")
                heading = re.search(r"^# (.+)$", text, re.MULTILINE)
                if heading:
                    result["role"] = heading.group(1)
            elif suffix == ".html":
                parser = PageStructure()
                parser.feed(text)
                if len(parser.ids) != len(set(parser.ids)):
                    raise ValueError("Duplicate static HTML ids")
                for link in parser.links:
                    check_site_reference(root, link, parser.ids)
                result["checks"].append("HTML ids/anchors/local assets")
            elif suffix == ".css":
                for reference in re.findall(r"url\(['\"]?([^)'\"]+)['\"]?\)", text):
                    check_site_reference(root, reference)
                result["checks"].append("CSS asset references")
            elif suffix == ".svg":
                if ElementTree.fromstring(text).tag != "{http://www.w3.org/2000/svg}svg":
                    raise ValueError("Expected an SVG root element")
                result["checks"].append("SVG XML parse")
            elif suffix == ".js":
                node = shutil.which("node")
                if node:
                    checked = subprocess.run(
                        [node, "--check", str(file)], capture_output=True, text=True, check=False
                    )
                    if checked.returncode:
                        raise ValueError(
                            "JavaScript syntax check failed (run node --check for details)"
                        )
                    result["checks"].append("Node.js syntax")
                elif require_node:
                    raise ValueError("Node.js is required to check JavaScript syntax")
                else:
                    result["warnings"].append(
                        "JavaScript syntax NOT checked: Node.js is unavailable"
                    )
            elif file.name.startswith("requirements"):
                for line in text.splitlines():
                    line = line.split(" #", 1)[0].strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("-r "):
                        included = (file.parent / line[3:].strip()).resolve()
                        if not included.is_relative_to(root.resolve()) or not included.is_file():
                            raise ValueError("Missing/unsafe included requirements file")
                    else:
                        Requirement(line)
                result["checks"].append("requirement syntax/includes")
        if result["category"] == "Unassigned":
            result["warnings"].append("Assign this file to an existing documented directory")
    except (
        OSError,
        ValueError,
        SyntaxError,
        KeyError,
        TypeError,
        struct.error,
        InvalidRequirement,
        yaml.YAMLError,
        ElementTree.ParseError,
        DefusedXmlException,
    ) as error:
        if isinstance(error, SyntaxError):
            detail = f"Python syntax error at line {error.lineno}: {error.msg}"
        elif isinstance(error, yaml.YAMLError):
            detail = "Invalid YAML (run its parser for details)"
        else:
            detail = str(error)
        result["errors"].append(detail)
    result["status"] = "FAIL" if result["errors"] else "REVIEW" if result["warnings"] else "PASS"
    return result


def audit_files(root: Path, paths: list[str], *, require_node: bool = False) -> dict[str, Any]:
    files = [inspect_file(root, path, require_node=require_node) for path in sorted(set(paths))]
    return {
        "scope": "tracked and non-ignored new files; structural checks only, not formal verification",
        "generated_at": datetime.now(UTC).isoformat(),
        "files_checked": len(files),
        "errors": sum(len(file["errors"]) for file in files),
        "warnings": sum(len(file["warnings"]) for file in files),
        "categories": dict(sorted(Counter(file["category"] for file in files).items())),
        "files": files,
    }


def inventory_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Repository file inventory",
        "",
        "Every tracked/non-ignored new source file is listed below with its responsibility and structural checks.",
        "PASS here means those checks passed; it does **not** certify runtime behavior or production security.",
        "See [the dated repository audit](REPOSITORY-AUDIT.md) for executed tests, findings and next updates.",
        "",
        "Regenerate from the repository root with:",
        "",
        "```bash",
        "python scripts/check_repository.py --require-node --inventory docs/operations/REPOSITORY-INVENTORY.md",
        "```",
        "",
        f"Files checked: **{report['files_checked']}**.",
        "",
    ]
    for group in report["categories"]:
        lines.extend(
            [
                f"## {group}",
                "",
                "| File | Responsibility | Structural checks | Result |",
                "|---|---|---|---|",
            ]
        )
        for file in report["files"]:
            if file["category"] != group:
                continue
            description = escape(file["role"]).replace("|", "\\|")
            checks = "; ".join(file["checks"]).replace("|", "\\|")
            path = escape(file["path"]).replace("`", "&#96;").replace("|", "\\|")
            lines.append(f"| `{path}` | {description} | {checks} | {file['status']} |")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--require-node", action="store_true")
    parser.add_argument(
        "--strict", action="store_true", help="fail on review warnings as well as errors"
    )
    parser.add_argument(
        "--json",
        type=Path,
        help="optional machine-readable inventory (normally reports/generated/)",
    )
    parser.add_argument("--inventory", type=Path, help="optional Markdown file map")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        paths = discover_files(root)
    except (OSError, subprocess.CalledProcessError):
        print(
            "Could not inventory files: run inside a Git checkout with git installed.",
            file=sys.stderr,
        )
        return 2
    report = audit_files(root, paths, require_node=args.require_node)
    if args.inventory:
        target = args.inventory if args.inventory.is_absolute() else root / args.inventory
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(inventory_markdown(report), encoding="utf-8")
    if args.json:
        target = args.json if args.json.is_absolute() else root / args.json
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for file in report["files"]:
        for issue in file["errors"] + file["warnings"]:
            print(f"{file['status']} {file['path']}: {issue}")
    print(
        f"Repository checks: {report['files_checked']} files, {report['errors']} errors, {report['warnings']} warnings"
    )
    return 1 if report["errors"] or (args.strict and report["warnings"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
