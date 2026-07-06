# 7. Versionamento e Histórico

## Modelo mental: "Git para políticas", sem a complexidade do Git

O sistema adota os conceitos do Git que geram valor para negócio e descarta os que geram atrito:

| Conceito Git | No CreditOps | Decisão |
|---|---|---|
| Commit | Versão (`policy_version`) imutável com autor, data e mensagem (`change_summary`) | ✅ adotado |
| Diff | Diff textual entre quaisquer duas versões | ✅ adotado |
| Tag/Release | `release` agrupando publicações (v1) | ✅ adotado |
| Branch/Merge | **Não existe** — um rascunho aberto por política, história linear | ❌ descartado (complexidade sem valor para o público-alvo) |
| Revert | Rollback = roll-forward de conteúdo antigo | ✅ adaptado |
| História reescrita (rebase) | **Proibido por construção** | ❌ descartado |

## O que o sistema registra por versão

| Informação | Onde | Quando |
|---|---|---|
| Versão anterior | `based_on_version_id` + `version_number - 1` | criação do rascunho |
| Versão atual (vigente) | `policy.current_version_id` | transação de vigência |
| Diferença entre versões | calculada on-the-fly com `difflib` (não armazenada — sempre derivável dos snapshots) | exibição |
| Justificativa da alteração | `change_summary` (obrigatória) | submissão |
| Impacto esperado | `expected_impact` (obrigatório) | submissão |
| Data de publicação | `publication.published_at` | publicação |
| Data de vigência | `publication.effective_from` / `effective_until` | publicação / substituição |
| Responsáveis | `created_by`, `approval.approver_id`, `publication.published_by` | cada evento |
| Impacto observado | `impact_record` (v1) | pós-publicação |

### Snapshot vs. delta

Cada versão guarda o **conteúdo completo** (snapshot), não deltas. Justificativa:

- Políticas são textos pequenos (KBs); espaço é irrelevante.
- Leitura de qualquer versão é O(1), sem reconstrução por aplicação de deltas.
- Diffs são calculados sob demanda entre quaisquer pares de versões (não só consecutivas).
- Elimina toda uma classe de bugs de corrupção de histórico.

### Diff legível para negócio

O diff é apresentado em três níveis:

1. **Resumo humano**: o `change_summary` escrito pelo autor (com IA opcional gerando rascunho do resumo a partir do diff).
2. **Diff de campos estruturados** (v1): tabela "campo / valor anterior / valor novo" — ex.: `score mínimo: 620 → 650`. É o formato que o aprovador de negócio realmente lê.
3. **Diff textual do Markdown**: linha a linha, estilo lado a lado, para inspeção detalhada.

## Linha do tempo da política (UI)

```
POL-CRD-014 — Política de Limite PJ                        [EM VIGOR: v7]

v8  ● RASCUNHO      criado por Ana em 02/07/2026
v7  ● EM VIGOR      desde 01/06/2026  │ aprovado por Carlos (28/05) │ publicado por Carlos (29/05)
v6  ○ SUBSTITUÍDA   vigente 01/03/2026 → 31/05/2026 │ rollback para v4
v5  ○ SUBSTITUÍDA   vigente 15/01/2026 → 28/02/2026
v4  ○ SUBSTITUÍDA   vigente 01/10/2025 → 14/01/2026
...
      [comparar versões]  [ver em uma data]  [exportar dossiê]
```

Funções-chave:
- **Comparar quaisquer duas versões** (não só adjacentes).
- **"Ver em uma data"** (time travel): dado D, mostra a versão com `effective_from ≤ D < effective_until`.
- **Exportar dossiê**: pacote com conteúdo, metadados, cadeia de aprovação e trilha de auditoria da política — o entregável de auditoria.

## Numeração e identidade

- `version_number` é sequencial por política (1, 2, 3…) — simples e comunicável ("aprovamos a v7").
- O `code` da política (`POL-CRD-014`) é estável para sempre, mesmo se título/área mudarem (mudanças de metadados são auditadas).
- Referência canônica externa: `POL-CRD-014@v7` (usada em exportações, APIs e citações entre políticas).

## Ciclo esperado × observado

O diferencial de governança do produto — fechar o loop de aprendizado:

1. **Antes** (submissão): autor declara `expected_impact` narrativo (ex.: "redução de aprovação automática em ~8% no segmento MEI, queda projetada de inadimplência 90d de 0,4 p.p.") e, na v1, a **hipótese estruturada por indicador** (`impact_metric`: indicador do catálogo + magnitude esperada — ex.: `fpd60 −0,4 p.p.`).
2. **Depois** (30/60/90 dias — v1): responsável registra o observado — narrativo (`impact_record`) e por indicador/janela (`impact_metric.observed_change`).
3. Dashboard (v1) lista publicações com impacto observado pendente e compara esperado × observado por indicador — respondendo "quais mudanças deram certo?" e "quais pioraram o FPD60?".

O sistema **não calcula** o impacto (não é BI) — ele **cobra e registra** a avaliação, criando disciplina de gestão. Conceitos de indicador e hipótese: [Domínio do Produto](16-dominio-do-produto.md#indicador--v1).
