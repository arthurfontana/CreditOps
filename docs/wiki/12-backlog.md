# 12. Backlog Inicial (MVP)

Formato: épicos → histórias com critérios de aceite resumidos. Ordem = ordem de implementação sugerida (espelha os [prompts de execução](../../prompts/README.md)).

## Épico 1 — Fundação técnica

- **1.1** Como dev, quero o esqueleto FastAPI+SQLite+Alembic rodando com health check, para ter base de desenvolvimento.
  *Aceite*: `uvicorn app.main:app` sobe; `GET /health` responde; `alembic upgrade head` cria o banco; pytest roda no CI.
- **1.2** Como dev, quero o esquema core migrado (todas as tabelas do [modelo de dados](05-modelo-de-dados.md)) com triggers de imutabilidade.
  *Aceite*: UPDATE em versão congelada e UPDATE/DELETE em `audit_log` falham no nível do banco; teste automatizado prova.
- **1.3** Como admin, quero criar o primeiro usuário via CLI (`create-admin`).

## Épico 2 — Autenticação e papéis

- **2.1** Como usuário, quero logar com usuário/senha e ter sessão segura.
  *Aceite*: argon2; cookie HttpOnly/SameSite; bloqueio após 5 falhas; logout; tudo auditado.
- **2.2** Como admin, quero gerenciar usuários e papéis (admin, autor, revisor, aprovador, leitor).
  *Aceite*: desativação lógica (nunca delete); mudanças auditadas com before/after.
- **2.3** Como sistema, quero autorização no service layer.
  *Aceite*: chamada de service com papel errado lança `PermissionDenied`, mesmo sem passar pela UI.

## Épico 3 — Catálogo de políticas

- **3.1** Como admin, quero cadastrar áreas, produtos, segmentos e tags.
- **3.2** Como autor, quero criar política (código auto `POL-<AREA>-NNN`, título, tipo, dona, produtos, segmentos, tags) que nasce com v1 em rascunho.
- **3.3** Como usuário, quero navegar no catálogo com filtros (área, produto, segmento, status, tag) e ver o selo de vigência.
- **3.4** Como usuário, quero busca full-text com resultados ranqueados.
  *Aceite*: FTS5 sobre título, código e corpo da versão vigente; < 500ms.

## Épico 4 — Edição e versões

- **4.1** Como autor, quero editar rascunho em Markdown com preview e salvamento automático.
- **4.2** Como autor, quero "Nova revisão" a partir da vigente (cópia, `based_on`, nº sequencial; só 1 rascunho aberto por política).
- **4.3** Como autor, quero anexar arquivos ao rascunho.
  *Aceite*: lista de extensões, tamanho máx, SHA-256 armazenado, download com `Content-Disposition: attachment`.
- **4.4** Como usuário, quero ver diff entre quaisquer duas versões (lado a lado e unificado).

## Épico 5 — Workflow de aprovação

- **5.1** Como autor, quero submeter para revisão com `change_summary` e `expected_impact` obrigatórios.
  *Aceite*: conteúdo congela hash ao entrar em aprovação; transições fora da whitelist são rejeitadas.
- **5.2** Como revisor, quero comentar (ancorado a seções), devolver para ajustes ou enviar para aprovação.
- **5.3** Como aprovador, quero tela única com diff + justificativa + impacto + comentários, e botões aprovar/rejeitar.
  *Aceite*: autor≠aprovador enforced; rejeição exige justificativa e devolve a rascunho.
- **5.4** Como aprovador, quero publicar com data de vigência (imediata ou futura).
  *Aceite*: na vigência, anterior vira substituída com `effective_until`, `current_version_id` atualiza — transação única; job + verificação lazy.
- **5.5** Como aprovador, quero rollback para versão anterior via fluxo expresso.
  *Aceite*: nova versão `is_rollback`, justificativa obrigatória, histórico linear preservado.
- **5.6** Como usuário, quero minha fila na home (autor: rascunhos/rejeitadas; revisor: a revisar; aprovador: a aprovar/publicar).

## Épico 6 — Histórico e auditoria

- **6.1** Como usuário, quero a linha do tempo da política (todas as versões, estados, datas, responsáveis).
- **6.2** Como auditor, quero "ver em uma data" (time travel).
  *Aceite*: dado D, retorna a versão com `effective_from ≤ D < effective_until`.
- **6.3** Como sistema, quero registrar toda ação relevante na trilha append-only.
  *Aceite*: eventos definidos no [cap. 9](09-seguranca-e-governanca.md); consulta filtrável por entidade/ator/período.
- **6.4** Como auditor, quero exportar dossiê da política (conteúdo + metadados + cadeia de aprovação + trilha) em Markdown+JSON.

## Épico 7 — Operação

- **7.1** Como admin, quero script de backup consistente e runbook de restore.
- **7.2** Como admin, quero `seed_demo.py` com dados fictícios para treinar usuários.
- **7.3** Como dev, quero suíte de testes cobrindo: máquina de estados completa, imutabilidade, segregação de funções, vigência/substituição, time travel.
  *Aceite*: esses cenários são os testes de maior valor do sistema; cobertura do core ≥ 80%.

## Fora do backlog do MVP (registrado para v1+)

Notificações e-mail, permissões por área, multinível, delegação, releases, campos estruturados, impacto observado, dashboard, importador de legado, PDF, SSO, API de consumo, IA. Ver [Roadmap](11-roadmap.md).
