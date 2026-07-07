"""Texto rico (HTML sanitizado) para demandas e versões.

O editor WYSIWYG (Quill, vendorado em app/web/static) grava HTML; este
módulo é a única porta de entrada para persistir esse HTML: sanitiza no
servidor com nh3 (whitelist de tags/atributos — nunca confiar no browser)
e extrai texto plano para busca (FTS), diff e exportações.

Imagens coladas viajam como data URL (base64) dentro do próprio HTML —
autocontido para export e sem endpoint extra de upload. O tamanho total
do documento é limitado (RICHTEXT_MAX_BYTES).

Backlog registrado (docs/adr): diff célula a célula sobre HTML é mais
fraco que sobre Markdown; hoje o diff usa o texto extraído.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

import nh3

from app.services.errors import ValidationFailed

# 5MB de HTML (imagens base64 inclusas) por documento
RICHTEXT_MAX_BYTES = 5 * 1024 * 1024

_ALLOWED_TAGS = {
    "p", "br", "span", "strong", "b", "em", "i", "u", "s", "sub", "sup",
    "h1", "h2", "h3", "h4",
    "ol", "ul", "li",
    "blockquote", "pre", "code",
    "a", "img",
    "table", "thead", "tbody", "tr", "th", "td",
    "hr",
}

_ALLOWED_ATTRS = {
    "*": {"class"},
    "a": {"href", "title"},
    "img": {"src", "alt", "width", "height"},
    "ol": {"start"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
    "li": {"data-list"},  # Quill marca itens ordenados/bullet/check por atributo
    "span": {"style"},
    "p": {"style"},
}

# estilos inline permitidos (cores e alinhamento do Quill) — nada de url()/expression
_STYLE_RE = re.compile(
    r"^(\s*(color|background-color)\s*:\s*(#[0-9a-fA-F]{3,8}|rgb\([\d\s,]+\))\s*;?\s*"
    r"|\s*text-align\s*:\s*(left|right|center|justify)\s*;?\s*)+$"
)

# classes geradas pelo Quill (alinhamento, indent, fonte) — qualquer outra é removida
_CLASS_RE = re.compile(r"^(ql-[a-z0-9-]+)(\s+ql-[a-z0-9-]+)*$")


def _attribute_filter(tag: str, attr: str, value: str) -> str | None:
    if attr == "style":
        return value if _STYLE_RE.match(value) else None
    if attr == "class":
        return value if _CLASS_RE.match(value.strip()) else None
    return value


def sanitize_html(html: str) -> str:
    """Sanitiza HTML do editor. Levanta ValidationFailed se exceder o limite."""
    if not html:
        return ""
    if len(html.encode("utf-8")) > RICHTEXT_MAX_BYTES:
        raise ValidationFailed(
            "documento excede o tamanho máximo de "
            f"{RICHTEXT_MAX_BYTES // (1024 * 1024)}MB — reduza as imagens coladas"
        )
    return nh3.clean(
        html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        # data: para imagens coladas; http/https/mailto para links
        url_schemes={"http", "https", "mailto", "data"},
        attribute_filter=_attribute_filter,
        link_rel="noopener noreferrer",
    )


class _TextExtractor(HTMLParser):
    """Extrai texto plano de HTML preservando quebras por bloco."""

    _BLOCK = {"p", "br", "li", "tr", "h1", "h2", "h3", "h4", "blockquote", "pre", "hr"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self._BLOCK:
            self.parts.append("\n")
        elif tag in ("td", "th"):
            self.parts.append(" | ")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def html_to_text(html: str) -> str:
    """Texto plano de um HTML (para FTS, diff e export texto)."""
    if not html:
        return ""
    extractor = _TextExtractor()
    extractor.feed(html)
    text = "".join(extractor.parts)
    # normaliza espaço em excesso mantendo as quebras de linha
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def body_text(body_html: str | None, body_md: str) -> str:
    """Texto canônico de um documento: HTML (se houver) vence o Markdown legado."""
    if body_html:
        return html_to_text(body_html)
    return body_md or ""
