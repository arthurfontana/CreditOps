"""Renderização de Markdown sanitizada.

markdown-it em modo commonmark com html=False: HTML bruto do usuário é
escapado, nunca interpretado — sem XSS por corpo de política/comentário.
"""

from __future__ import annotations

from markdown_it import MarkdownIt

_md = MarkdownIt("commonmark", {"html": False, "linkify": False, "typographer": False})
_md.enable("table")


def render_markdown(text: str) -> str:
    return _md.render(text or "")
