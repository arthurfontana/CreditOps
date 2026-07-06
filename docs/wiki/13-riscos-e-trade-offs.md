# 13. Riscos e Trade-offs

## Riscos de produto/adoção

| Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|
| **Time volta para Word/e-mail** (fricção de escrita) | Alta | Fatal | Templates prontos; editor com preview; importação de legado; piloto com 1 time engajado; patrocínio do gerente de crédito (o aprovador é o maior beneficiado) |
| Sistema vira "cemitério de documentos" (cadastra e não atualiza) | Média | Alto | Filas de pendência visíveis; recertificação periódica (v2); dashboard de políticas paradas (v1) |
| Dupla fonte de verdade durante a transição | Alta | Médio | Cutover formal por área: data a partir da qual "só vale o que está no CreditOps", comunicada pela diretoria |
| Workflow fixo não serve a alguma área | Média | Médio | Fluxo fixo cobre o essencial; multinível na v1; configurável só no enterprise — resistir à parametrização precoce |

## Riscos técnicos

| Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|
| SQLite atingir limite de concorrência | Baixa | Médio | WAL + workload de leitura; SQLAlchemy/Alembic deixam a migração p/ Postgres barata (gatilhos definidos na [arquitetura](04-arquitetura.md)) |
| Perda do arquivo do banco | Baixa | Fatal | Backup diário automatizado + restore testado + manifesto de hashes |
| Adulteração direta do banco por quem tem acesso ao servidor | Baixa | Alto | Hash de conteúdo + hash chain na auditoria (v1) tornam adulteração **detectável**; acesso ao servidor restrito pela TI; enterprise: assinatura digital |
| Dependência de 1 desenvolvedor | Média | Alto | Esta wiki + ADRs + prompts de execução documentam tudo; stack popular (FastAPI/SQLite) |
| Ambiente sem acesso a PyPI | Média | Baixo | Wheelhouse offline documentado no runbook |

## Riscos de governança/segurança

| Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|
| Aprovação "de fachada" (aprova sem ler) | Média | Alto | UX: diff de campos legível na tela de aprovação; auditoria registra tempo entre abertura e decisão (métrica de qualidade, v1) |
| Vazamento via IA externa | Baixa | Alto | IA desligada por padrão; ativação explícita com aviso; opção de provider interno; log de tudo que foi enviado |
| Bypass do sistema (mudança combinada no corredor) | Média | Alto | Problema organizacional: norma interna de que só vale o publicado; o sistema torna o caminho oficial mais fácil que o informal |

## Trade-offs assumidos (decisões conscientes)

| Decisão | Ganho | Custo aceito |
|---|---|---|
| **SQLite, não Postgres** | Zero infraestrutura, backup trivial, instala em qualquer servidor | Sem HA; migração futura (barata via Alembic) |
| **SSR+HTMX, não SPA** | Sem Node/build/CDN; simplicidade; funciona em navegador corporativo antigo | UI menos "rica"; interatividade limitada ao suficiente |
| **História linear, sem branches/merge** | Modelo mental simples para negócio; sem conflitos de merge | Duas alterações simultâneas na mesma política enfileiram (na prática, raro e até desejável para governança) |
| **Snapshot por versão, não delta** | Leitura O(1), zero corrupção de histórico, diff entre quaisquer versões | Duplicação de texto (irrelevante em KBs) |
| **Workflow fixo no MVP** | Entrega rápida, menos bugs, UX previsível | Empresas com fluxo exótico esperam até enterprise |
| **Banco relacional, não Git como storage** | Queries de vigência/auditoria triviais; sem shell-out; permissões finas | Perde ferramentas Git prontas (ver [Alternativas](14-alternativas.md)) |
| **Impacto observado manual, não integrado a BI** | Escopo controlado; sem dependência de dados da carteira | Registro depende de disciplina (mitigado por cobrança na UI) |
| **IA opcional e por sugestão** | Zero dependência, zero vazamento por padrão, aprovável por segurança | Não há automação "mágica"; humano sempre no loop (em governança, isso é requisito, não custo) |
