# 16. Domínio do Produto (Modelo Conceitual do Negócio)

> Esta página define os **conceitos centrais do domínio** e como eles se relacionam — sem falar de FastAPI, SQLite ou arquitetura. É a referência semântica do produto: quando houver dúvida sobre "o que é uma Mudança" ou "qual a diferença entre Publicação e Vigência", a resposta canônica está aqui. O [Modelo de Dados](05-modelo-de-dados.md) é a tradução técnica desta página.

## O ciclo fechado da decisão de crédito

O CreditOps não governa apenas *documentos*; governa o **ciclo de vida das decisões de crédito**. O ciclo completo, com a fase em que cada elo entra no produto:

```
┌────────────────────────────────────────────────────────────────────────┐
│                                                                        │
│  DEMANDA ──► MUDANÇA ──► REVISÃO ──► APROVAÇÃO ──► PUBLICAÇÃO          │
│   (v1)      (rascunho     (MVP)        (MVP)      + VIGÊNCIA (MVP)     │
│              de nova                                    │              │
│              versão, MVP)                               ▼              │
│                                                    IMPLANTAÇÃO         │
│      ▲                                             (referência ao      │
│      │                                              motor, v1)         │
│      │                                                  │              │
│  APRENDIZADO ◄── IMPACTO OBSERVADO ◄── INDICADORES ◄────┘              │
│  (nova demanda)   (30/60/90 dias, v1)   (hipótese, v1)                 │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

O MVP entrega o miolo (mudança → aprovação → vigência) porque sem fonte de verdade nada mais importa. As fases seguintes fecham o ciclo — é o fechamento do ciclo que transforma o produto de "repositório de documentação" em **sistema de gestão do ciclo de vida das decisões de crédito**.

## Conceitos do domínio

### Política
Conjunto de regras de crédito com **identidade estável**: código (`POL-CRD-014`), título, tipo, área dona e responsável. A política é o *contêiner* — quem muda é a versão. A identidade estável é o que permite responder "qual era a regra em 15/03?" e manter referências externas válidas para sempre.

### Mudança
O ato de alterar uma política: **nova versão + justificativa (`change_summary`) + hipótese de impacto (`expected_impact`)**. No modelo do CreditOps, *toda versão a partir da v2 é uma mudança* — não existe mudança fora de versão, nem versão de conteúdo sem justificativa.

> **Decisão de modelagem**: a Mudança **não** substitui a Política como entidade central — as duas são centrais em eixos diferentes. A Política é a âncora de *identidade e vigência* (o que auditoria e operação consultam); a Mudança é a âncora do *processo e do aprendizado* (o que gestão mede). Na prática, a versão (`policy_version`) já **é** a mudança materializada; o que o produto adiciona por fase são as visões e métricas orientadas a mudança: "quais mudanças fizemos no trimestre?", "quanto tempo leva uma alteração?", "quais mudanças melhoraram o resultado?".

### Demanda (Solicitação de Mudança) — v1
O que existe **antes** do rascunho: alguém identifica a necessidade de mudar uma política (novo produto, apontamento de auditoria, deterioração de indicador, oportunidade comercial). A demanda tem solicitante, motivação, prioridade e status próprios, e pode:

- gerar uma ou mais mudanças (versões) em uma ou mais políticas;
- ser rejeitada sem gerar mudança (também é decisão, também fica registrada).

Com a demanda, o lead time passa a ser medível de ponta a ponta: *demanda aberta → versão em vigor*.

### Revisão
Etapa em que um par ou segunda linha examina o rascunho, comenta (ancorado a trechos) e devolve ou avança. Acontece **dentro da mesma versão**, antes do congelamento do conteúdo.

### Aprovação
Decisão formal, datada e não repudiável de um aprovador (que nunca é o autor) sobre uma versão congelada. Rejeição exige justificativa. É **evidência**, não flag: cada decisão é um registro permanente.

### Publicação
Ato que torna uma versão aprovada **oficial**, definindo *quando* ela passa a valer. Publicar ≠ estar em vigor: uma versão pode ser publicada hoje com vigência para o dia 1º do mês seguinte.

### Vigência
Período em que uma versão é *a regra válida da empresa* (`effective_from` → `effective_until`). No máximo uma versão vigente por política. A linha do tempo de vigências é o que permite o time travel ("o que valia em 15/03?").

### Release — v1
Agrupamento nomeado de publicações feitas em conjunto (ex.: "Revisão Q3/2026" contém Política A v7, Política B v12, Política C v5). Permite reconstruir *implantações* — o pacote que foi ao ar junto — e comunicar mudanças à operação como um todo coeso.

### Experimento (Piloto) — v2
Nem toda mudança nasce definitiva. Um experimento é uma **publicação com escopo restrito**: a versão entra em vigor para um recorte declarado (segmento, região, % da esteira, safra), com prazo e critério de sucesso definidos. Ao final, o experimento é **promovido** (nova publicação com escopo total), **ajustado** (nova versão) ou **encerrado** (rollback/arquivamento) — sempre pelo fluxo normal de aprovação.

> **Fronteira**: quem *executa* o champion/challenger é o motor de decisão. O CreditOps **documenta e governa** o experimento: escopo, hipótese, prazo, decisão de promoção e resultado. Isso mantém o produto fora do território de motor/plataforma de A/B.

### Indicador — v1
Métrica de negócio nomeada e padronizada em um **catálogo administrável**. Exemplos típicos de crédito:

| Código | Indicador | Direção desejada |
|---|---|---|
| `aprovacao` | Taxa de aprovação | contextual |
| `conversao` | Conversão de propostas | ↑ |
| `fpd30` / `fpd60` | First Payment Default 30/60 | ↓ |
| `over90` | Atraso > 90 dias | ↓ |
| `perda` | Perda esperada/realizada | ↓ |
| `receita` | Receita da carteira | ↑ |
| `churn` | Cancelamento/atrito | ↓ |

O catálogo existe para que hipóteses e resultados sejam **comparáveis entre mudanças** — texto livre não agrega.

### Hipótese e Impacto Observado — v1
Cada mudança relevante declara uma **hipótese estruturada**: indicador + direção + magnitude esperada (ex.: `aprovacao +3 p.p. no segmento PF`). Após a vigência, o responsável registra o **observado** em janelas de 30/60/90 dias. O sistema **cobra e registra** — não calcula (não é BI). É esse par esperado × observado que responde "quais decisões deram certo?" e transforma o histórico em aprendizado.

### Implementação (Referência ao Motor de Decisão) — v1
Vínculo declarado entre uma versão de política e **onde ela está implementada**: sistema (ex.: PowerCurve, Simplifique, motor interno), artefato (strategy, ruleset, arquivo), nó/caminho e versão do artefato. Permite navegar da documentação à implementação — e responder em auditoria "esta regra aprovada está implementada onde, em qual versão?". No v1 é metadado manual; integração sistêmica (conferência automática) é evolução enterprise.

### Referências entre Políticas (Grafo) — v2
Políticas não são ilhas: a Política PF *usa* o Score X, que *é definido por* outra política; a política de limite *depende de* a de concessão. As referências formam um **grafo dirigido** (política → política, política → artefato nomeado), com dois usos:

1. **Navegação**: do documento para tudo que ele referencia.
2. **Análise de impacto**: "se eu mudar o Score X, quais políticas são afetadas?" — a pergunta que hoje ninguém consegue responder sem reunião.

### Regra Reutilizável (Biblioteca de Regras) — exploratório / enterprise
Ideia: em vez de repetir a "regra de idade mínima" em dez políticas, mantê-la uma vez numa biblioteca e referenciá-la. Elimina duplicação e inconsistência — mas exige modelar regras como objetos estruturados com versionamento e vigência próprios, o que **aproxima perigosamente o produto de um motor de decisão** e multiplica a complexidade de governança (mudar uma regra compartilhada dispara reaprovação de todas as políticas que a usam?).

**Decisão**: fica registrada como direção **exploratória de enterprise**, não como compromisso. Até lá, a dor é mitigada por camadas mais baratas: campos estruturados por tipo (v1), referências entre políticas (v2) e busca full-text. Ver trade-off em [Riscos](13-riscos-e-trade-offs.md).

## Mapa de relacionamentos

```
 DEMANDA (v1) ──0..N──► MUDANÇA (= nova versão da política)
                              │
 POLÍTICA ──1:N── VERSÃO ─────┤
     │               │        ├── HIPÓTESE por INDICADOR (v1)
     │               │        ├── REVISÃO (comentários)
     │               │        ├── APROVAÇÃO (1..N níveis)
     │               │        └── PUBLICAÇÃO ──► VIGÊNCIA
     │               │                │              │
     │               │                ├── RELEASE (v1, agrupa publicações)
     │               │                ├── ESCOPO: total ou piloto/experimento (v2)
     │               │                └── IMPACTO OBSERVADO por INDICADOR,
     │               │                    janelas 30/60/90d (v1)
     │               │
     │               └── IMPLEMENTAÇÃO: sistema/artefato/versão (v1)
     │
     └──► REFERÊNCIAS (grafo, v2): usa / depende de / substitui
              └──► outras POLÍTICAS ou ARTEFATOS (scores, motores, cadastros)
```

## Perguntas que o domínio responde (por fase)

| Pergunta | Respondida por | Fase |
|---|---|---|
| Qual é a versão vigente da política X? | Vigência | MVP |
| O que valia em 15/03, quem aprovou e por quê? | Vigência + Aprovação + Mudança | MVP |
| O que mudou entre a v5 e a v7? | Mudança (diff) | MVP |
| Quais mudanças fizemos no último trimestre? | Mudança + Release | v1 |
| Quanto tempo demora uma alteração de política? | Demanda → Vigência (lead time) | v1 |
| A mudança entregou o que prometeu? | Hipótese × Impacto Observado | v1 |
| Onde esta política está implementada, em qual versão? | Implementação | v1 |
| Quais decisões deram certo (e quais pioraram o FPD60)? | Indicadores agregados por mudança | v1/v2 |
| Se eu mudar o Score X, o que é afetado? | Grafo de referências | v2 |
| Este piloto deve ir para produção? | Experimento + Indicadores | v2 |

## Fronteiras do domínio (o que fica fora)

Estas fronteiras protegem o produto de virar outra coisa:

1. **Não executa regras** — motores de decisão implementam; o CreditOps é a fonte do "porquê" e do "o quê", e aponta (via Implementação) para o "como".
2. **Não calcula indicadores** — BI/carteira calculam; o CreditOps registra hipótese e resultado, e cobra a disciplina do ciclo.
3. **Não orquestra processos genéricos** — o workflow é especializado no ciclo de vida de política; não é BPM.
4. **Não modela regras executáveis** — biblioteca de regras estruturadas só se/quando o valor comprovado justificar o custo (exploratório enterprise).
