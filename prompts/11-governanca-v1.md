# Prompt 11 — v1 "Governança para valer"

> **Status: implementado.** Este prompt fica como registro do escopo executado
> e como guia para reimplementação/revisão. Wiki a anexar: 03, 05, 06, 11, 16.

## Contexto

O MVP ("Fonte de verdade") está completo e testado. Esta etapa implementa a
v1 do roadmap (`docs/wiki/11-roadmap.md`): governança para a diretoria
inteira, fechando o ciclo demanda → mudança → vigência → impacto observado
(`docs/wiki/16-dominio-do-produto.md`).

## Entregas (na ordem)

### P0

1. **Hash chain na auditoria**: `audit_service.record` preenche
   `prev_hash`/`row_hash` (`row_hash = sha256(prev_hash + dados canônicos)`);
   `scripts/verify_audit.py` verifica a cadeia inteira (linhas pré-v1 sem
   hash toleradas apenas antes do início da cadeia).
2. **Permissões por área**: usuário com `area_id` atua só em políticas da
   própria área; usuário sem área tem escopo corporativo; leitura continua
   aberta a todos. Aplicar em criação/edição de política, rascunho, revisão
   e todas as transições do workflow (service layer, não só UI).
3. **Notificações por e-mail**: fila persistente (tabela `notification`) +
   plugin SMTP (`app/plugins/notify/email_smtp.py`) carregado por
   configuração; subscribers dos eventos de domínio (submissão, aprovação
   pendente, decisão, publicação, vigência); envio pós-commit com retry
   periódico; senha SMTP apenas em env var. Desligado por padrão.

### P1

4. **Aprovação multinível**: tabela `approval_rule` (níveis exigidos por
   `policy_type`, default 1, admin configura); aprovação sequencial com
   `approval.level`; cada nível exige aprovador diferente; rejeição em
   qualquer nível devolve ao autor; rodada zera ao reentrar em aprovação.
5. **Delegação de aprovação**: tabela `approval_delegation` (janela datada,
   revogável, delegado deve ser outro aprovador); decisão sob delegação
   registra `approval.delegated_from_id`; delegado herda o escopo de área do
   delegante; delegação não burla segregação autor≠aprovador.
6. **Releases**: criação por aprovador/admin; `publication.release_id`
   preenchido na publicação; páginas de listagem e detalhe.
7. **Campos estruturados por tipo** (`app/services/structured_fields.py`):
   definições por `policy_type` (limite, concessão, renegociação, cobrança,
   score, alçada); editáveis no rascunho; entram no `content_hash`; diff de
   campos (`diff_service.field_diff`) na tela de decisão.
8. **Demanda de mudança**: tabela `change_request` (código `DEM-AAAA-NNN`,
   prioridade, status, resolução); vínculo `policy_version.change_request_id`
   no rascunho; rejeição com justificativa; fechamento automático quando a
   versão vinculada entra em vigor; lead time demanda→vigência.
9. **Indicadores + hipótese + impacto observado**: catálogo `indicator`
   (seed: aprovacao, conversao, fpd30, fpd60, over90, perda, receita, churn);
   `impact_metric` com esperado por (indicador, janela 30/60/90d) declarado
   em rascunho e congelado na submissão; observado registrado uma única vez
   após a vigência; fila de cobrança pendente na home e no dashboard;
   `impact_record` narrativo por publicação.

### P2

10. **Referência de implementação**: `implementation_ref`
    (sistema/artefato/versão/nó/URL/data), registro manual em versões
    publicadas.
11. **Dashboard de governança**: versões por status, ciclo médio
    submissão→vigência (90d), lead time médio, publicações por mês,
    políticas paradas > N meses, esperado × observado por indicador.
12. **Importador de legado**: upload em lote; .md/.txt viram corpo do
    rascunho; binários ficam anexados (hash); falha em um arquivo não
    derruba o lote.
13. **Exportação PDF**: plugin `export_pdf` sem dependência externa
    (PDF textual A4), rota `/policies/{id}/export.pdf`.

## Migração

`migrations/versions/0002_v1_governance.py` — idempotente (a 0001 cria o
esquema completo do metadata em bancos novos): cria só as tabelas/colunas
que faltam e faz o seed do catálogo de indicadores.

## Critérios de aceite

- Testes cobrindo: cadeia de hashes (inclusive adulteração), escopo por
  área, multinível (2 níveis, aprovadores distintos, rodadas), delegação
  (registro, revogação, segregação), releases, campos estruturados no hash e
  no diff, demanda (código, vínculo, fechamento automático), hipótese
  congelada na submissão, observado único pós-vigência, cobrança pendente,
  importador (sucesso parcial) e PDF válido.
- `pytest` e `ruff check .` verdes; suíte do MVP intacta.
- **Gate de saída da v1**: 3+ áreas usando; 100% das publicações com trilha;
  auditoria interna valida o dossiê.
