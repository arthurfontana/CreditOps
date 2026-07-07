"""Campos estruturados por tipo de política (v1).

Complementam o corpo em Markdown com dados comparáveis entre versões
(ex.: política de limite tem `score_minimo`, `comprometimento_max`).
São opcionais na v1; validação de obrigatoriedade por modelo é v2.

O valor é guardado em `policy_version.structured_fields` (JSON), entra no
`content_hash` e ganha diff próprio (diff_service.field_diff).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.services.errors import ValidationFailed


@dataclass(frozen=True)
class FieldDef:
    name: str
    label: str
    kind: str  # "int" | "decimal" | "text"
    hint: str = ""


FIELD_DEFS: dict[str, list[FieldDef]] = {
    "limite": [
        FieldDef("score_minimo", "Score mínimo", "int"),
        FieldDef("comprometimento_max", "Comprometimento máximo de renda (%)", "decimal"),
        FieldDef("limite_maximo", "Limite máximo (R$)", "decimal"),
        FieldDef("renda_minima", "Renda mínima (R$)", "decimal"),
    ],
    "concessao": [
        FieldDef("score_minimo", "Score mínimo", "int"),
        FieldDef("idade_minima", "Idade mínima (anos)", "int"),
        FieldDef("tempo_relacionamento_min", "Tempo mínimo de relacionamento (meses)", "int"),
        FieldDef("restricao_bureau", "Restrição em bureau", "text", "ex.: sem negativação ativa"),
    ],
    "renegociacao": [
        FieldDef("desconto_max", "Desconto máximo (%)", "decimal"),
        FieldDef("parcelas_max", "Nº máximo de parcelas", "int"),
        FieldDef("carencia_max_dias", "Carência máxima (dias)", "int"),
    ],
    "cobranca": [
        FieldDef("dias_primeiro_acionamento", "Dias até o 1º acionamento", "int"),
        FieldDef("dias_negativacao", "Dias até negativação", "int"),
    ],
    "score": [
        FieldDef("faixa_corte", "Faixa de corte", "text", "ex.: 0-1000, corte em 620"),
        FieldDef("fornecedor", "Fornecedor/modelo", "text"),
    ],
    "alcada": [
        FieldDef("alcada_analista", "Alçada do analista (R$)", "decimal"),
        FieldDef("alcada_gerente", "Alçada do gerente (R$)", "decimal"),
        FieldDef("alcada_superintendente", "Alçada do superintendente (R$)", "decimal"),
    ],
    "outro": [],
}


def defs_for(policy_type: str) -> list[FieldDef]:
    return FIELD_DEFS.get(policy_type, [])


def parse_form(policy_type: str, raw: dict[str, str]) -> str | None:
    """Converte valores de formulário (strings) no JSON canônico da versão.

    Campos vazios ficam de fora; erro de tipo é rejeitado com mensagem clara.
    Retorna None quando nenhum campo foi preenchido.
    """
    values: dict[str, object] = {}
    for field_def in defs_for(policy_type):
        raw_value = (raw.get(field_def.name) or "").strip()
        if not raw_value:
            continue
        if field_def.kind == "int":
            try:
                values[field_def.name] = int(raw_value)
            except ValueError:
                raise ValidationFailed(
                    f"campo '{field_def.label}' deve ser um número inteiro"
                ) from None
        elif field_def.kind == "decimal":
            try:
                values[field_def.name] = float(raw_value.replace(",", "."))
            except ValueError:
                raise ValidationFailed(
                    f"campo '{field_def.label}' deve ser numérico"
                ) from None
        else:
            values[field_def.name] = raw_value
    if not values:
        return None
    return json.dumps(values, ensure_ascii=False, sort_keys=True)


def load(structured_fields: str | None) -> dict[str, object]:
    if not structured_fields:
        return {}
    try:
        data = json.loads(structured_fields)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}
