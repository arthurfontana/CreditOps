# 3. MVP e Evolução da Solução

O produto evolui em quatro camadas. Cada camada resolve uma dor completa de ponta a ponta — nunca entregamos "metade de uma funcionalidade em cada fase".

## Racional da ordem

1. **Primeiro o registro** (catálogo + versões): sem fonte única de verdade, nada mais importa.
2. **Depois a governança** (workflow + auditoria): formalizar o que antes era e-mail.
3. **Depois a escala** (permissões finas, integrações, notificações): adoção ampla.
4. **Por fim, o enterprise** (SSO, multi-tenant, IA avançada, APIs de consumo): produto vendável.

Essa ordem também minimiza risco de adoção: o MVP já é útil para **um único time** sem depender de ninguém de fora (TI mínima, sem integração).

---

## Fase MVP — "A fonte de verdade"

**Dor que resolve**: "não sabemos qual é a versão vigente nem quem aprovou".

### Entra

- Catálogo de políticas com metadados (área, produto, segmento, responsável, tags).
- Conteúdo em **Markdown estruturado** com templates.
- **Versionamento imutável**: cada mudança gera nova versão; diff textual entre versões.
- **Workflow essencial**: Rascunho → Em revisão → Em aprovação → Aprovado → Publicado → Em vigor → Substituído/Arquivado, com **Rejeitado** como desvio.
- Papéis fixos: Admin, Autor, Revisor, Aprovador, Leitor.
- Justificativa e impacto esperado obrigatórios na submissão.
- Data de vigência (imediata ou agendada).
- **Trilha de auditoria append-only** de todas as ações.
- Busca full-text (SQLite FTS5).
- Anexos (arquivos guardados no filesystem, com hash).
- Comentários por versão.
- Autenticação local (usuário/senha), sessões, HTTPS atrás de proxy interno.
- Exportação de política/histórico em Markdown + JSON.

### Fica fora (e por quê)

- SSO/LDAP → exige alinhamento com TI; usuário local destrava o piloto.
- Notificações por e-mail → úteis, mas a fila de pendências na home cobre o essencial.
- IA → acelerador, não fundação.
- Editor WYSIWYG rico → Markdown com preview é suficiente e evita complexidade.
- Workflow configurável → o fluxo fixo cobre 90% dos casos; configurabilidade é custo alto.
- API pública de consumo → só faz sentido quando houver consumidores sistêmicos.

### Critério de sucesso do MVP

Um time de crédito consegue: migrar 10 políticas reais, publicar uma alteração com aprovação do gerente e responder a uma pergunta de auditoria sem sair do sistema.

---

## Versão intermediária (v1) — "Governança para valer"

**Dor que resolve**: "o sistema funciona para um time; agora precisa funcionar para a diretoria de crédito inteira".

### Entra

- **Notificações por e-mail** (SMTP corporativo): submissão, aprovação pendente, publicação, rejeição.
- **Permissões por área**: autor da área X não edita política da área Y; aprovador por área/produto.
- **Delegação de aprovação** (férias/ausência) com registro em auditoria.
- **Aprovação em múltiplos níveis** opcional por tipo de política (ex.: alçada — mudanças de limite exigem gerente + superintendente).
- **Releases**: agrupamento de várias políticas publicadas juntas (ex.: "Revisão trimestral Q3").
- **Campos estruturados por tipo de política** (ex.: política de limite tem campos `score_minimo`, `comprometimento_max`) além do corpo em Markdown.
- **Demanda de mudança** (`change_request`): registro do pedido que antecede o rascunho — solicitante, motivação, prioridade, status — ligado às versões que gera. Habilita lead time ponta a ponta (demanda → vigência).
- **Impacto observado**: registro pós-publicação (manual) do efeito real vs. esperado, agora **estruturado por indicador** (catálogo: aprovação, conversão, FPD30/60, over90, perda, receita, churn) com hipótese na submissão e observação em janelas de 30/60/90 dias.
- **Referência de implementação**: vínculo manual da versão publicada ao artefato do motor de decisão (sistema, strategy/ruleset/arquivo, versão, nó) — navegação da documentação à implementação.
- Dashboard de governança: políticas por status, tempo médio de ciclo, políticas sem revisão há > N meses, mudanças por período e esperado × observado por indicador.
- Importador de legado assistido (upload em lote de documentos → cria políticas com anexo original).
- Backup automatizado agendado + verificação de integridade da trilha (hash chain).

### Fica fora

- Multi-tenant, SSO, IA — próximas fases.

---

## Produto completo (v2) — "Plataforma da empresa"

**Dor que resolve**: "outras diretorias querem usar; TI exige integração com o diretório; sistemas precisam consumir a versão vigente".

### Entra

- **SSO corporativo** (LDAP/Active Directory, SAML/OIDC quando disponível).
- **API REST de consumo** (somente leitura, com tokens de serviço): sistemas buscam a versão vigente de uma política de forma programática.
- **Webhooks/exportação agendada** para motores de decisão e data lake.
- **Módulo de IA plugável** (ver [IA Modular](08-ia-modular.md)): resumo de mudanças, classificação, sugestão de tags, chat de perguntas sobre políticas (RAG local).
- **Revisão periódica obrigatória**: políticas com prazo de validade/recertificação; alertas de vencimento.
- **Modelos de documento por tipo** com validação de campos obrigatórios.
- Comparação entre políticas (não só entre versões).
- **Grafo de referências entre políticas** (`usa` / `depende_de` / `substitui`, incluindo artefatos como scores e motores) com análise de impacto: "se eu mudar o Score X, quais políticas são afetadas?".
- **Publicação-experimento (piloto)**: vigência com escopo restrito declarado (segmento, região, % da esteira), prazo e critério de sucesso; promoção a produção, ajuste ou encerramento seguem o fluxo normal de aprovação. O motor executa o teste; o CreditOps o documenta e governa.
- Trilhas de leitura obrigatória ("ciência da operação"): registro de quem leu a política vigente.

### Fica fora

- Multi-tenant SaaS.

---

## Versão ideal / Enterprise — "Produto"

**Dor que resolve**: transformar a solução interna em produto SaaS/on-prem vendável.

### Entra

- **Multi-tenant** com isolamento de dados por cliente (ou instância dedicada on-prem — modelo "single-tenant gerenciado" costuma ser mais aceito por bancos).
- Postgres como banco padrão (migração transparente — ver [Arquitetura](04-arquitetura.md)).
- Workflow configurável por tenant (estados e alçadas parametrizáveis).
- Assinatura digital de aprovações (ICP-Brasil / certificado corporativo) para não-repúdio forte.
- Relatórios regulatórios prontos (dossiê de auditoria com um clique).
- Alta disponibilidade, observabilidade (métricas, logs estruturados), SLA.
- Marketplace de provedores de IA (OpenAI, Anthropic, Gemini, Azure OpenAI, modelos locais via Ollama/vLLM).
- Mobile/responsivo completo para aprovação em trânsito.
- **Exploratório — biblioteca de regras reutilizáveis**: regras compartilhadas entre políticas com versionamento próprio. Só entra se o valor comprovado justificar o custo — aproxima o produto de um motor de decisão (ver [Domínio do Produto](16-dominio-do-produto.md#regra-reutilizável-biblioteca-de-regras--exploratório--enterprise) e [Riscos](13-riscos-e-trade-offs.md)).
- Conferência automática de implantação: integração com motores para validar que a versão vigente documentada é a implementada.

---

## Resumo comparativo

| Capacidade | MVP | v1 | v2 | Enterprise |
|---|---|---|---|---|
| Catálogo + versões imutáveis | ✅ | ✅ | ✅ | ✅ |
| Workflow fixo de aprovação | ✅ | ✅ | ✅ | ✅ |
| Trilha de auditoria | ✅ | ✅ (hash chain) | ✅ | ✅ (assinatura) |
| Diff entre versões | ✅ texto | ✅ texto+campos | ✅ | ✅ |
| Permissões | papéis globais | por área | por área | configurável |
| Notificações | — | e-mail | e-mail | e-mail/chat |
| Aprovação multinível | — | ✅ | ✅ | configurável |
| Releases | — | ✅ | ✅ | ✅ |
| Demanda de mudança | — | ✅ | ✅ | ✅ |
| Impacto observado | — | ✅ manual | ✅ | ✅ + integração BI |
| Indicadores estruturados (hipótese × observado) | — | ✅ | ✅ | ✅ + integração BI |
| Referência de implementação (motor) | — | ✅ manual | ✅ | ✅ conferência automática |
| Grafo de referências / análise de impacto | — | — | ✅ | ✅ |
| Experimento / piloto | — | — | ✅ | ✅ |
| Biblioteca de regras reutilizáveis | — | — | — | 🔎 exploratório |
| SSO/LDAP | — | — | ✅ | ✅ |
| API de consumo | — | — | ✅ | ✅ |
| IA | — | — | ✅ plugável | ✅ marketplace |
| Multi-tenant | — | — | — | ✅ |
| Banco | SQLite | SQLite | SQLite ou Postgres | Postgres |
