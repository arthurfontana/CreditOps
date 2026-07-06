"""Plugin de exportação PDF (v1) — sem dependência externa.

Gera PDF textual (Helvetica, A4) a partir das linhas do documento
exportado em Markdown. Deliberadamente simples: o objetivo é um artefato
imprimível/arquivável para auditoria e circulação, não tipografia rica —
quem precisa de layout usa a exportação Markdown/JSON.
"""

from __future__ import annotations

PAGE_WIDTH = 595  # A4 em pontos
PAGE_HEIGHT = 842
MARGIN = 50
FONT_SIZE = 10
TITLE_SIZE = 14
LEADING = 14
MAX_CHARS = 95  # quebra de linha aproximada para Helvetica 10pt
LINES_PER_PAGE = (PAGE_HEIGHT - 2 * MARGIN) // LEADING


def _escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _wrap(line: str) -> list[str]:
    line = line.rstrip()
    if len(line) <= MAX_CHARS:
        return [line]
    parts: list[str] = []
    while len(line) > MAX_CHARS:
        cut = line.rfind(" ", 0, MAX_CHARS)
        if cut <= 0:
            cut = MAX_CHARS
        parts.append(line[:cut])
        line = line[cut:].lstrip()
    parts.append(line)
    return parts


class PdfExporter:
    """Renderiza título + linhas de texto em um PDF de N páginas."""

    def render(self, title: str, lines: list[str]) -> bytes:
        wrapped: list[str] = []
        for line in lines:
            wrapped.extend(_wrap(line))

        pages: list[list[str]] = []
        current: list[str] = []
        for line in wrapped:
            if len(current) >= LINES_PER_PAGE - 3:  # espaço do título na 1ª página
                pages.append(current)
                current = []
            current.append(line)
        pages.append(current)

        objects: list[bytes] = []  # corpo de cada objeto, índice = nº - 1

        def add(body: bytes) -> int:
            objects.append(body)
            return len(objects)

        font_regular = add(
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
            b"/Encoding /WinAnsiEncoding >>"
        )
        font_bold = add(
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
            b"/Encoding /WinAnsiEncoding >>"
        )

        content_ids: list[int] = []
        for index, page_lines in enumerate(pages):
            chunks = ["BT"]
            y = PAGE_HEIGHT - MARGIN
            if index == 0:
                chunks.append(f"/F2 {TITLE_SIZE} Tf")
                chunks.append(f"1 0 0 1 {MARGIN} {y} Tm")
                chunks.append(f"({_escape(title)}) Tj")
                y -= 2 * LEADING
            chunks.append(f"/F1 {FONT_SIZE} Tf")
            chunks.append(f"1 0 0 1 {MARGIN} {y} Tm")
            chunks.append(f"{LEADING} TL")
            for line in page_lines:
                chunks.append(f"({_escape(line)}) Tj T*")
            chunks.append("ET")
            stream = "\n".join(chunks).encode("cp1252", errors="replace")
            content_ids.append(
                add(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
            )

        # objetos de página apontam para /Pages, cujo id só é conhecido agora
        pages_id = len(objects) + len(pages) + 1
        page_ids = []
        for content_id in content_ids:
            page_ids.append(
                add(
                    (
                        f"<< /Type /Page /Parent {pages_id} 0 R "
                        f"/MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
                        f"/Resources << /Font << /F1 {font_regular} 0 R "
                        f"/F2 {font_bold} 0 R >> >> "
                        f"/Contents {content_id} 0 R >>"
                    ).encode()
                )
            )
        kids = " ".join(f"{pid} 0 R" for pid in page_ids)
        add(f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode())
        catalog_id = add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode())

        out = bytearray(b"%PDF-1.4\n")
        offsets = [0]
        for number, body in enumerate(objects, start=1):
            offsets.append(len(out))
            out += b"%d 0 obj\n" % number
            out += body
            out += b"\nendobj\n"
        xref_pos = len(out)
        out += b"xref\n0 %d\n" % (len(objects) + 1)
        out += b"0000000000 65535 f \n"
        for offset in offsets[1:]:
            out += b"%010d 00000 n \n" % offset
        out += (
            b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objects) + 1, catalog_id, xref_pos)
        )
        return bytes(out)
