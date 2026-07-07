"""Sanitização e extração de texto do editor WYSIWYG."""

from __future__ import annotations

import pytest

from app.services import richtext
from app.services.errors import ValidationFailed


def test_sanitize_remove_script_e_eventos():
    html = "<p onclick=\"x()\">oi</p><script>alert(1)</script><img src=\"javascript:x\">"
    out = richtext.sanitize_html(html)
    assert "<script" not in out
    assert "onclick" not in out
    assert "javascript:" not in out
    assert "oi" in out


def test_sanitize_preserva_formatacao_e_tabela():
    html = (
        "<h2>Escopo</h2><p><strong>negrito</strong> e <em>itálico</em></p>"
        "<table><tr><th>a</th><td>b</td></tr></table>"
        "<ol><li data-list=\"ordered\">um</li></ol>"
    )
    out = richtext.sanitize_html(html)
    for fragment in ("<h2>", "<strong>", "<em>", "<table>", "<th>", "data-list"):
        assert fragment in out


def test_sanitize_permite_imagem_base64_e_bloqueia_estilo_malicioso():
    html = (
        '<img src="data:image/png;base64,iVBORw0KGgo=" alt="print">'
        '<span style="color:#ff0000">vermelho</span>'
        '<span style="background-image:url(http://x)">x</span>'
    )
    out = richtext.sanitize_html(html)
    assert 'src="data:image/png;base64,iVBORw0KGgo="' in out
    assert "color:#ff0000" in out.replace(" ", "")
    assert "background-image" not in out


def test_sanitize_limite_de_tamanho():
    with pytest.raises(ValidationFailed):
        richtext.sanitize_html("<p>" + "x" * richtext.RICHTEXT_MAX_BYTES + "</p>")


def test_html_to_text_extrai_blocos_e_tabelas():
    html = "<h1>Título</h1><p>linha um</p><table><tr><td>a</td><td>b</td></tr></table>"
    text = richtext.html_to_text(html)
    assert "Título" in text
    assert "linha um" in text
    assert "a | b" in text.replace("| a | b", "a | b")  # células separadas


def test_body_text_prioriza_html():
    assert richtext.body_text("<p>rico</p>", "md legado") == "rico"
    assert richtext.body_text("", "md legado") == "md legado"
    assert richtext.body_text(None, "") == ""
