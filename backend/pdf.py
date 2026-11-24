"""Dependency-free PDF dossier renderer for SkyScout briefing data."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Sequence, Tuple

PAGE_WIDTH = 595.28
PAGE_HEIGHT = 841.89
MARGIN = 46.0
BOTTOM = 58.0


def _ascii(value: Any) -> str:
    text = "" if value is None else str(value)
    return "".join(char if 32 <= ord(char) < 127 else "?" for char in text)


def _escape(value: Any) -> str:
    return _ascii(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _width(text: str, size: float, bold: bool = False) -> float:
    factor = 1.06 if bold else 1.0
    total = 0.0
    for char in text:
        if char in "iljI.,:;'!|`":
            total += 0.28
        elif char in "MW@%":
            total += 0.88
        elif char.isupper():
            total += 0.68
        elif char.isdigit():
            total += 0.56
        elif char == " ":
            total += 0.3
        else:
            total += 0.52
    return total * size * factor


def _wrap(text: Any, size: float, max_width: float, bold: bool = False) -> List[str]:
    words = _ascii(text).split()
    if not words:
        return [""]
    lines: List[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and _width(candidate, size, bold) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


class PdfDocument:
    def __init__(self) -> None:
        self.pages: List[List[str]] = [[]]
        self.y = PAGE_HEIGHT - 58.0

    def _emit(self, operation: str) -> None:
        self.pages[-1].append(operation)

    def new_page(self) -> None:
        self.pages.append([])
        self.y = PAGE_HEIGHT - 58.0

    def ensure_space(self, height: float) -> None:
        if self.y - height < BOTTOM:
            self.new_page()

    def text(self, x: float, y: float, value: Any, size: float = 10.0, bold: bool = False, color: Tuple[float, float, float] = (0.1, 0.12, 0.18)) -> None:
        font = "/F2" if bold else "/F1"
        red, green, blue = color
        self._emit(
            f"BT {red:.3f} {green:.3f} {blue:.3f} rg {font} {size:.1f} Tf 1 0 0 1 {x:.2f} {y:.2f} Tm ({_escape(value)}) Tj ET"
        )

    def paragraph(self, value: Any, size: float = 9.5, bold: bool = False, gap: float = 4.0) -> None:
        lines = _wrap(value, size, PAGE_WIDTH - 2 * MARGIN, bold)
        height = len(lines) * (size + 3) + gap
        self.ensure_space(height)
        for line in lines:
            self.text(MARGIN, self.y, line, size, bold)
            self.y -= size + 3
        self.y -= gap

    def heading(self, value: Any) -> None:
        self.ensure_space(48)
        self.y -= 6
        self._emit(f"0.31 0.28 0.90 rg {MARGIN:.2f} {self.y - 2:.2f} {PAGE_WIDTH - 2 * MARGIN:.2f} 1.5 re f")
        self.text(MARGIN, self.y - 14, value.upper(), 12.0, True, (0.19, 0.18, 0.45))
        self.y -= 30

    def badge(self, value: Any, color: Tuple[float, float, float]) -> None:
        label = _ascii(value)
        width = _width(label, 9.5, True) + 18
        self.ensure_space(26)
        self._emit(f"{color[0]:.3f} {color[1]:.3f} {color[2]:.3f} rg {MARGIN:.2f} {self.y - 4:.2f} {width:.2f} 18 re f")
        self.text(MARGIN + 9, self.y + 1, label, 9.5, True, (1, 1, 1))
        self.y -= 26

    def bullets(self, values: Sequence[Any], size: float = 9.2) -> None:
        for value in values:
            self.paragraph(f"- {value}", size=size, gap=2)
        self.y -= 4

    def table(self, headers: Sequence[Any], rows: Sequence[Sequence[Any]], widths: Sequence[float]) -> None:
        available = PAGE_WIDTH - 2 * MARGIN
        total = sum(widths)
        scaled = [width * available / total for width in widths]
        header_lines = [_wrap(header, 8.5, width - 10, True) for header, width in zip(headers, scaled)]
        header_height = max(22, max(len(lines) for lines in header_lines) * 11 + 8)

        def draw_header() -> None:
            self.ensure_space(header_height + 24)
            top = self.y
            self._emit(f"0.94 0.95 0.98 rg {MARGIN:.2f} {top - header_height:.2f} {available:.2f} {header_height:.2f} re f")
            x = MARGIN
            for index, lines in enumerate(header_lines):
                line_y = top - 13
                for line in lines:
                    self.text(x + 5, line_y, line, 8.5, True)
                    line_y -= 11
                x += scaled[index]
            self.y = top - header_height

        draw_header()
        for row_index, row in enumerate(rows):
            cell_lines = [_wrap(cell, 8.2, width - 10) for cell, width in zip(row, scaled)]
            line_count = max(len(lines) for lines in cell_lines)
            row_height = max(22, line_count * 10.5 + 8)
            if self.y - row_height < BOTTOM:
                self.new_page()
                draw_header()
            top = self.y
            if row_index % 2 == 0:
                self._emit(f"0.985 0.99 1 rg {MARGIN:.2f} {top - row_height:.2f} {available:.2f} {row_height:.2f} re f")
            x = MARGIN
            for index, lines in enumerate(cell_lines):
                line_y = top - 12
                for line in lines:
                    self.text(x + 5, line_y, line, 8.2)
                    line_y -= 10.5
                x += scaled[index]
            self._emit(f"0.80 0.83 0.88 RG 0.5 w {MARGIN:.2f} {top - row_height:.2f} {available:.2f} {row_height:.2f} re S")
            self.y = top - row_height
        self.y -= 8

    def key_values(self, values: Sequence[Dict[str, Any]]) -> None:
        rows = []
        for item in values:
            value = item.get("value") or item.get("reason") or "Unavailable"
            rows.append([item.get("label", "Field"), value])
        self.table(["Field", "Value"], rows, [1.2, 2.8])

    def bytes(self) -> bytes:
        generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        total = len(self.pages)
        for index, operations in enumerate(self.pages, 1):
            operations.append(f"0.42 0.45 0.50 rg BT /F1 8 Tf 1 0 0 1 {PAGE_WIDTH - 190:.2f} 30 Tm (Generated {_escape(generated_at)} UTC) Tj ET")
            operations.append(f"0.42 0.45 0.50 rg BT /F1 8 Tf 1 0 0 1 {PAGE_WIDTH - MARGIN - 58:.2f} 30 Tm (Page {index} of {total}) Tj ET")
            operations.append("showpage")

        objects: List[bytes] = []
        objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
        kids = " ".join(f"{5 + index * 2} 0 R" for index in range(total))
        objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {total} >>".encode("latin-1"))
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
        for index, operations in enumerate(self.pages):
            page_number = 5 + index * 2
            content_number = page_number + 1
            objects.append(
                (
                    f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH:.2f} {PAGE_HEIGHT:.2f}] "
                    f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content_number} 0 R >>"
                ).encode("latin-1")
            )
            stream = "\n".join(operations).encode("latin-1")
            objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1") + stream + b"\nendstream")

        output = bytearray(b"%PDF-1.4\n")
        offsets = [0]
        for number, body in enumerate(objects, 1):
            offsets.append(len(output))
            output.extend(f"{number} 0 obj\n".encode("latin-1"))
            output.extend(body)
            output.extend(b"\nendobj\n")
        xref_offset = len(output)
        output.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
        output.extend(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            output.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
        output.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("latin-1"))
        return bytes(output)


def _status_color(status: Any) -> Tuple[float, float, float]:
    normalized = str(status or "").upper()
    if normalized == "VERIFIED":
        return (0.02, 0.45, 0.32)
    if normalized == "SIMULATED":
        return (0.66, 0.35, 0.03)
    if normalized == "UNAVAILABLE":
        return (0.55, 0.58, 0.62)
    return (0.14, 0.40, 0.65)


def render_briefing_pdf(briefing: Dict[str, Any], session_id: str = "") -> bytes:
    doc = PdfDocument()
    verification = briefing.get("verification") or {}
    doc.text(MARGIN, doc.y, "SkyScout Travel Dossier", 20, True, (0.19, 0.18, 0.45))
    doc.y -= 22
    doc.text(MARGIN, doc.y, "Autonomous Multi-Agent Flight Planning Platform", 10, False, (0.35, 0.38, 0.45))
    doc.y -= 16
    doc.text(MARGIN, doc.y, f"Document generated: {verification.get('generated_at', datetime.now(timezone.utc).isoformat(timespec='seconds'))} UTC", 8.5)
    doc.y -= 14
    if session_id:
        doc.text(MARGIN, doc.y, f"Session: {_ascii(session_id)[:16]}...", 8.5)
        doc.y -= 14
    doc.badge(f"STATUS: {verification.get('status', 'PREVIEW')}", _status_color(verification.get("status")))
    doc.paragraph("Demo inventory only. This dossier is not a booking, ticket, or airline confirmation.", 9, True)

    doc.heading("Travel summary")
    doc.key_values((briefing.get("summary") or {}).get("fields", []))

    doc.heading("Selected flight information")
    for leg in briefing.get("legs") or []:
        doc.paragraph(f"{leg.get('direction', 'Flight').upper()} LEG", 10, True)
        doc.key_values(leg.get("fields", []))

    doc.heading("Price breakdown")
    doc.key_values((briefing.get("price") or {}).get("fields", []))
    ranking = briefing.get("ranking") or {}
    if ranking.get("fields"):
        doc.heading("Ranking and utility")
        doc.key_values(ranking.get("fields", []))

    doc.heading("Passenger preferences")
    preferences = [item for item in briefing.get("preferences") or [] if item.get("status") == "available"]
    if preferences:
        doc.table(["Preference", "Value"], [[item.get("label", "—"), item.get("value", "—")] for item in preferences], [1.1, 2.9])
    else:
        doc.paragraph("No passenger preferences available.")

    doc.heading("Important travel notes")
    doc.bullets(briefing.get("conditions") or [])

    watcher = briefing.get("watcher") or {}
    doc.heading("Watcher information")
    doc.paragraph(f"Status: {watcher.get('status', 'UNAVAILABLE')}", 9.5, True)
    doc.paragraph(watcher.get("disclosure", "No watcher data available."))
    doc.key_values(watcher.get("fields", []))

    doc.heading("Verification and audit")
    doc.key_values([
        {"label": "Verification status", "value": verification.get("status")},
        {"label": "Inventory verification", "value": verification.get("inventory_status")},
        {"label": "Timestamp", "value": f"{verification.get('timestamp', 'Unavailable')} ({verification.get('timestamp_kind', 'generation')})"},
        {"label": "Source", "value": verification.get("source")},
        {"label": "Data availability", "value": verification.get("data_availability")},
    ])
    doc.paragraph(verification.get("simulation_disclosure", "No live airline verification was performed."), 9, True)
    doc.paragraph("Data sources", 10, True)
    doc.table(
        ["Information", "Source", "Status"],
        [[item.get("item", "—"), item.get("source", "—"), item.get("status", "—")] for item in (briefing.get("audit") or {}).get("sources", [])],
        [1.4, 2.2, 0.8],
    )
    checks = (briefing.get("audit") or {}).get("checks") or []
    if checks:
        doc.paragraph("Grounding checks", 10, True)
        doc.table(
            ["Check", "Result", "Details"],
            [[check.get("name", "—"), "PASS" if check.get("passed") else "FAIL", check.get("details", "—")] for check in checks],
            [1.4, 0.5, 2.5],
        )

    doc.heading("Warnings and unavailable information")
    doc.bullets(briefing.get("warnings") or [])
    missing_groups = briefing.get("missing_groups") or []
    if missing_groups:
        doc.paragraph("Unavailable information by category", 10, True)
        doc.table(
            ["Category", "Type", "Fields"],
            [
                [group.get("group", "Other"), group.get("kind", "required"), ", ".join(group.get("labels") or [])]
                for group in missing_groups
            ],
            [1.3, 0.7, 2.4],
        )
    elif briefing.get("missing"):
        doc.paragraph("Unavailable information", 10, True)
        doc.bullets([f"Unavailable: {label}" for label in briefing["missing"]])
    else:
        doc.paragraph("No missing fields were detected.")
    return doc.bytes()
