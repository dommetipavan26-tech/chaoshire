"""Dependency-free native PDF summary renderer."""
import textwrap
from typing import Any


def _pdf_escape(text: object) -> str:
    return str(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _report_lines(audit: dict[str, Any], chaos: dict[str, Any] | None) -> list[str]:
    certificate = audit["certificate"]
    lines = [
        "ChaosHire Audit Report",
        f"Audit: {audit.get('audit_name', 'Reference model audit')}",
        f"ID: {audit.get('audit_id', 'reference-demo')}",
        "",
        f"Candidates: {audit['stats']['candidates']}",
        f"Accepted: {audit['stats']['accepted']}",
        f"Fairness Risk Score: {certificate['total']} / {certificate['grade']}",
        "",
        "Primary attributes",
    ]
    for attribute in audit["attributes"]:
        lines.append(
            f"- {attribute['attribute']}: DI {attribute['disparate_impact']}; "
            f"parity gap {attribute['parity_gap']}; equal opportunity {attribute['eq_opp_gap']}"
        )
    if audit.get("intersections"):
        lines.extend(["", "Intersectional analysis"])
        for attribute in audit["intersections"]:
            lines.append(f"- {attribute['attribute']}: DI {attribute['disparate_impact']}")
    if chaos:
        lines.extend(["", f"Chaos Lab: {chaos['resilience']}/100 ({chaos['experiment_id']})"])
        for test in chaos["tests"]:
            lines.append(f"- {test['name']}: {test['value']} - {test['verdict']}")
    lines.extend(
        [
            "",
            "Interpretation notice",
            "Exploratory technical assessment only. Not legal advice or proof of discrimination.",
            "Synthetic reference results are not findings about a real employer.",
        ]
    )
    wrapped: list[str] = []
    for line in lines:
        wrapped.extend(textwrap.wrap(str(line), width=92) or [""])
    return wrapped


def render_pdf_report(audit: dict[str, Any], chaos: dict[str, Any] | None = None) -> bytes:
    """Render a small standards-compatible PDF using built-in Helvetica."""
    lines = _report_lines(audit, chaos)
    pages = [lines[index : index + 48] for index in range(0, len(lines), 48)] or [[]]
    objects: list[bytes] = []
    # Object numbers: 1 catalog, 2 pages, 3 font, then page/content pairs.
    page_numbers = [4 + index * 2 for index in range(len(pages))]
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{number} 0 R" for number in page_numbers)
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for index, page_lines in enumerate(pages):
        page_number = page_numbers[index]
        content_number = page_number + 1
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_number} 0 R >>".encode()
        )
        commands = ["BT", "/F1 10 Tf", "50 750 Td", "13 TL"]
        for line in page_lines:
            commands.append(f"({_pdf_escape(line)}) Tj")
            commands.append("T*")
        commands.append("ET")
        stream = "\n".join(commands).encode("latin-1", "replace")
        objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode())
        output.extend(obj)
        output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects)+1}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(output)
