# 5. Modelo de Dados

> Esta página é a tradução técnica do [Domínio do Produto](16-dominio-do-produto.md) — leia-o primeiro para entender os conceitos de negócio.

## Princípios

1. **Separação política × versão**: `policy` é o "contêiner" estável (identidade, código, dono); `policy_version` é o conteúdo em um ponto no tempo. Tudo que muda vive na versão.
2. **Imutabilidade**: uma `policy_version` que saiu de Rascunho **nunca mais é alterada** (enforced por aplicação e por trigger no banco). Correção = nova versão.
3. **Eventos, não flags**: aprovação, publicação e vigência são **registros datados** (linhas em tabelas), não booleanos sobrescritos.
4. **Auditoria append-only**: `audit_log` só recebe INSERT.

## Diagrama Entidade-Relacionamento (visão lógica)

```
 area ─────┐
 product ──┼──N:M──┐
 segment ──┘        │
                    ▼
 user ──1:N── policy ──1:N── policy_version ──1:N── approval
                │                  │        ──1:N── comment
                │                  │        ──1:N── attachment
                │                  │        ──1:1── publication ──0:1── impact_record
                │                  │
                │                  └──N:1── release (opcional, v1)
                │
                └── current_version_id (ponteiro para a versão EM VIGOR)

 audit_log (referencia qualquer entidade por tipo+id)
 status_transition (histórico de estados de cada versão)
```

### Extensões do ciclo de mudança (v1/v2)

```
 change_request ──0:N── policy_version ──1:N── impact_metric ──N:1── indicator
      (v1)                                          (v1)              (v1)
                        policy_version ──1:N── implementation_ref (v1)
                        policy ──N:M── policy_reference ──► policy | artefato (v2)
                        publication.rollout_scope: full | pilot (v2)
```

Ver o mapa conceitual completo no [Domínio do Produto](16-dominio-do-produto.md#mapa-de-relacionamentos).

## Entidades

### `user` — Responsável
| Campo | Tipo | Notas |
|---|---|---|
| id | uuid pk | |
| username / email | text unique | |
| display_name | text | |
| password_hash | text | argon2; null quando SSO |
| role | enum | `admin`, `author`, `reviewer`, `approver`, `reader` |
| area_id | fk → area | v1: escopo de permissão |
| is_active | bool | desativação lógica; nunca deletar (integridade do histórico) |

### `area` — Área organizacional
`id`, `name`, `code`, `parent_id` (hierarquia opcional), `is_active`.

### `product` — Produto impactado
`id`, `name`, `code`, `is_active`. Ex.: cartão, CDC, consignado, capital de giro.

### `segment` — Segmento
`id`, `name`, `code`, `is_active`. Ex.: PF, PJ, MEI, agro, alta renda.

### `policy` — Política (contêiner estável)
| Campo | Tipo | Notas |
|---|---|---|
| id | uuid pk | |
| code | text unique | ex.: `POL-CRD-014` — gerado sequencial por área |
| title | text | |
| policy_type | enum | `limite`, `concessao`, `renegociacao`, `cobranca`, `score`, `alcada`, `outro` |
| area_id | fk → area | dona da política |
| owner_id | fk → user | responsável de negócio |
| current_version_id | fk → policy_version, nullable | a versão **EM VIGOR**; null antes da 1ª publicação |
| lifecycle_status | enum | `active`, `archived` |
| review_due_at | date, nullable | recertificação (v2) |
| created_at | timestamp | |

Relações N:M: `policy_product`, `policy_segment`, `policy_tag`.

### `policy_version` — Revisão/Versão (imutável após rascunho)
| Campo | Tipo | Notas |
|---|---|---|
| id | uuid pk | |
| policy_id | fk → policy | |
| version_number | int | sequencial por política; atribuído na criação do rascunho |
| status | enum | `draft`, `in_review`, `in_approval`, `approved`, `published`, `effective`, `superseded`, `archived`, `rejected` |
| body_md | text | conteúdo canônico em Markdown |
| structured_fields | json | campos por tipo de política (v1) |
| change_summary | text | **justificativa da alteração** (obrigatória para submeter) |
| expected_impact | text | impacto esperado (obrigatório para submeter) |
| based_on_version_id | fk → policy_version, nullable | de qual versão este rascunho partiu (rastreia rollback: aponta para versão antiga) |
| is_rollback | bool | marca rollbacks para relatórios |
| content_hash | text | SHA-256 de body_md + structured_fields, calculado ao sair de draft |
| created_by | fk → user | autor |
| created_at / submitted_at | timestamp | |

### `status_transition` — Mudança de estado (histórico do workflow)
`id`, `version_id`, `from_status`, `to_status`, `actor_id`, `reason` (obrigatório em rejeição/rollback), `created_at`. Toda transição gera uma linha — o workflow inteiro é reconstruível.

### `approval` — Aprovação
| Campo | Tipo | Notas |
|---|---|---|
| id | uuid pk | |
| version_id | fk | |
| approver_id | fk → user | |
| decision | enum | `approved`, `rejected` |
| level | int | 1 no MVP; multinível na v1 |
| justification | text | obrigatória em rejeição |
| decided_at | timestamp | |
| delegated_from_id | fk → user, nullable | delegação (v1) |

### `publication` — Publicação (evento)
| Campo | Tipo | Notas |
|---|---|---|
| id | uuid pk | |
| version_id | fk unique | uma publicação por versão |
| published_by | fk → user | |
| published_at | timestamp | quando foi publicada |
| effective_from | date | **quando entra em vigor** (≥ published_at) |
| effective_until | date, nullable | preenchida quando substituída |
| release_id | fk → release, nullable | v1 |
| rollout_scope | enum | `full` (padrão) ou `pilot` — publicação-experimento (v2) |
| pilot_description / pilot_ends_at | text / date, nullable | escopo e prazo do piloto (v2); promoção/encerramento seguem o fluxo normal |

> A vigência histórica de qualquer data D é: a versão cuja `effective_from ≤ D < effective_until` (ou `effective_until is null`). Isso responde "o que valia em 15/03?" com uma query.

### `impact_record` — Impacto observado, narrativa (v1)
`id`, `publication_id`, `observed_impact` (text), `metrics` (json livre: ex. inadimplência antes/depois), `recorded_by`, `recorded_at`. Avaliação qualitativa que fecha o ciclo esperado × observado.

### `indicator` — Catálogo de indicadores (v1)
`id`, `code` unique (ex.: `aprovacao`, `conversao`, `fpd30`, `fpd60`, `over90`, `perda`, `receita`, `churn`), `name`, `unit`, `desired_direction` (`up`, `down`, `contextual`), `is_active`. Catálogo administrável — hipóteses e resultados ficam comparáveis entre mudanças (ver [Domínio](16-dominio-do-produto.md#indicador--v1)).

### `impact_metric` — Hipótese e observado por indicador (v1)
| Campo | Tipo | Notas |
|---|---|---|
| id | uuid pk | |
| version_id | fk → policy_version | a mudança que declara a hipótese |
| indicator_id | fk → indicator | |
| expected_change | text | ex.: `+3 p.p. no segmento PF` — declarado na submissão |
| observed_change | text, nullable | preenchido pós-vigência |
| window_days | int | janela da observação: 30, 60 ou 90 |
| recorded_by / recorded_at | fk / timestamp, nullable | |

Uma linha por (indicador, janela). Complementa `expected_impact`/`impact_record` (narrativos) com dados estruturados. O sistema **cobra e registra** — não calcula (não é BI).

### `change_request` — Demanda de mudança (v1)
| Campo | Tipo | Notas |
|---|---|---|
| id | uuid pk | |
| code | text unique | ex.: `DEM-2026-041` |
| title / description_md | text | motivação da demanda |
| requested_by | fk → user | solicitante |
| area_id | fk → area | |
| policy_id | fk → policy, nullable | null quando a demanda é de política nova |
| priority | enum | `low`, `medium`, `high`, `regulatory` |
| status | enum | `open`, `in_progress`, `done`, `rejected` (rejeição com justificativa — também é decisão registrada) |
| created_at / closed_at | timestamp | lead time = demanda aberta → versão em vigor |

`policy_version.change_request_id` (fk nullable, v1) liga a mudança à demanda que a originou. Uma demanda pode gerar N versões (inclusive em políticas diferentes).

### `implementation_ref` — Referência de implementação (v1)
| Campo | Tipo | Notas |
|---|---|---|
| id | uuid pk | |
| version_id | fk → policy_version | |
| system | text | ex.: `PowerCurve`, `Simplifique`, motor interno |
| artifact | text | strategy / ruleset / arquivo |
| artifact_version | text | versão do artefato no motor |
| node_path | text, nullable | nó/caminho dentro do artefato |
| url | text, nullable | link para o sistema de origem |
| deployed_at | date, nullable | |
| registered_by / created_at | fk / timestamp | |

Navegação documentação → implementação; responde em auditoria "esta regra está implementada onde, em qual versão?". No v1 é registro manual; conferência automática é enterprise.

### `policy_reference` — Grafo de referências (v2)
`id`, `from_policy_id` (fk), `to_type` (`policy` | `artifact`), `to_policy_id` (fk nullable), `artifact_name` (text nullable — ex.: "Score Serasa", "Motor Antifraude"), `relation` (`usa`, `depende_de`, `substitui`), `note`, `created_by`, `created_at`. Habilita análise de impacto: "se eu mudar o Score X, quais políticas são afetadas?".

### `comment` — Comentário
`id`, `version_id`, `author_id`, `body_md`, `anchor` (âncora opcional a um trecho/heading), `resolved_at`, `created_at`.

### `attachment` — Anexo
`id`, `version_id`, `filename`, `stored_path`, `sha256`, `size_bytes`, `content_type`, `uploaded_by`, `created_at`. Arquivo no filesystem; hash garante integridade.

### `release` — Release (v1)
`id`, `name` (ex.: "Revisão Q3/2026"), `description`, `created_by`, `published_at`. Agrupa publicações relacionadas.

### `tag`
`id`, `name` unique. N:M com policy.

### `audit_log` — Trilha de auditoria (append-only)
| Campo | Tipo | Notas |
|---|---|---|
| id | integer pk autoincrement | ordem total |
| actor_id | fk → user, nullable | null para ações do sistema (ex.: vigência automática) |
| action | text | `policy.created`, `version.submitted`, `version.approved`, `version.published`, `user.login`, `export.generated`, ... |
| entity_type / entity_id | text / uuid | alvo |
| payload | json | dados relevantes da ação (diff de metadados, justificativa, IP) |
| prev_hash / row_hash | text | hash encadeado (v1): `row_hash = sha256(prev_hash + dados)` — adulteração é detectável |
| created_at | timestamp | |

### `notification` (v1)
Fila persistente de notificações para o plugin de e-mail; permite retry sem perder eventos.

### `setting`
Chave/valor de configuração administrável (nome da empresa, SMTP, plugin de IA ativo etc.). Segredos ficam **fora** do banco (variáveis de ambiente / arquivo protegido).

## Invariantes (regras de integridade)

1. No máximo **uma versão `effective` por política** (índice único parcial).
2. `policy.current_version_id` sempre aponta para a versão `effective` (mantido na mesma transação).
3. Versão fora de `draft` é imutável: `body_md`, `structured_fields`, `change_summary` não podem mudar (trigger `RAISE` no SQLite + validação na aplicação).
4. `audit_log`: sem UPDATE/DELETE (trigger).
5. `version_number` é sequencial e sem lacunas por política.
6. Toda transição de status válida está na whitelist da máquina de estados (ver [Workflow](06-workflow-de-aprovacao.md)); qualquer outra é rejeitada.
7. Usuários nunca são deletados fisicamente (apenas `is_active = false`).

## Glossário

| Termo | Definição |
|---|---|
| **Política** | Conjunto de regras de crédito com identidade estável (código, título, dono) |
| **Versão / Revisão** | Snapshot imutável do conteúdo da política em um ponto do ciclo de vida |
| **Publicação** | Ato formal que torna uma versão aprovada oficial, com data de vigência |
| **Vigência** | Período em que uma versão é a regra válida da empresa |
| **Versão ativa / vigente** | A única versão `effective` de uma política |
| **Substituída** | Versão que já foi vigente e foi trocada por outra |
| **Rollback** | Nova versão cujo conteúdo copia uma versão anterior, com aprovação expressa |
| **Release** | Grupo de publicações feitas em conjunto |
| **Mudança** | Diferença entre duas versões + justificativa + impacto |
| **Demanda** | Solicitação de mudança que antecede o rascunho, com solicitante, motivação e status próprios (v1) |
| **Indicador** | Métrica de negócio padronizada em catálogo (aprovação, FPD60, over90…) usada em hipóteses e resultados (v1) |
| **Hipótese** | Impacto esperado estruturado por indicador, declarado na submissão da mudança (v1) |
| **Experimento / Piloto** | Publicação com escopo restrito, prazo e critério de sucesso; promovida, ajustada ou encerrada pelo fluxo normal (v2) |
| **Implementação** | Referência da versão de política ao artefato do motor de decisão que a implementa (v1) |
| **Referência entre políticas** | Aresta do grafo `usa` / `depende_de` / `substitui` entre políticas e artefatos (v2) |

Definições conceituais completas: [Domínio do Produto](16-dominio-do-produto.md).
