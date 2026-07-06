# 1. Visão Geral

## Título do produto

**CreditOps — Plataforma de Governança de Políticas de Crédito**

Sistema de registro, versionamento, aprovação e auditoria de políticas de crédito. Uma mistura de wiki especializada, controle de versão estilo Git, workflow de aprovação e trilha de auditoria — projetada para rodar em ambiente corporativo restrito com um servidor Python simples.

## Resumo executivo

Em instituições que operam crédito, a política de crédito é o ativo de decisão mais importante e, paradoxalmente, o pior documentado. As regras vivem em planilhas, apresentações, e-mails e na memória das pessoas. Quando um auditor pergunta *"qual era a regra de limite para o segmento PJ em março do ano passado, quem aprovou e por quê?"*, a resposta costuma custar dias de arqueologia — quando existe.

O CreditOps resolve isso com um princípio central: **política de crédito é código de negócio e deve ser tratada como código** — com versões imutáveis, diffs, revisão por pares, aprovação formal, publicação controlada e histórico completo.

O produto entrega:

1. **Catálogo único** de políticas, organizado por área, produto e segmento.
2. **Versionamento imutável**: toda alteração gera uma nova versão; nada é sobrescrito.
3. **Workflow de aprovação** com papéis claros (autor, revisor, aprovador, publicador).
4. **Vigência explícita**: separação entre "aprovado", "publicado" e "em vigor".
5. **Trilha de auditoria** completa, append-only, exportável.
6. **IA opcional e plugável**: resumos, classificação e sugestões quando houver modelo disponível — mas o core funciona 100% sem IA.

A arquitetura mínima é deliberadamente simples: **Python + FastAPI + SQLite + Markdown**, um único processo, sem dependências de SaaS externo. Isso permite começar em um servidor interno qualquer e evoluir, sem reescrita, até uma versão enterprise multi-tenant.

## Problema que resolve

### Sintomas observados em empresas grandes

| Sintoma | Consequência |
|---------|--------------|
| Políticas dispersas em documentos, planilhas, e-mails e chats | Ninguém sabe qual é a versão vigente; decisões baseadas em regra desatualizada |
| Conhecimento na memória das pessoas | Perda de conhecimento em turnover; dependência de indivíduos |
| Alterações sem registro formal | Impossível responder "quem mudou, quando e por quê" em auditoria |
| Aprovação por e-mail ou reunião | Sem evidência estruturada de aprovação; risco regulatório |
| Sem data de vigência clara | Operação aplica regra nova antes da hora, ou regra velha depois da troca |
| Sem medição de impacto | Mudanças de política não são avaliadas contra o resultado real |

### O custo do problema

- **Risco regulatório**: bancos e financeiras respondem a BACEN/auditorias; a incapacidade de reconstruir o histórico decisório é apontamento clássico.
- **Risco operacional**: mesas de crédito aplicando versões divergentes da mesma política.
- **Custo de retrabalho**: horas de analistas reconstruindo histórico em planilhas.
- **Perda de aprendizado**: sem "impacto esperado vs. observado", a empresa não aprende com as próprias decisões de política.

### O que o produto NÃO é

Para manter foco, o CreditOps **não** é:

- Um motor de decisão de crédito (não executa regras em produção; documenta e governa as regras).
- Um BPM genérico (o workflow é especializado no ciclo de vida de política).
- Um DMS/ECM corporativo (anexos existem, mas o documento primário é estruturado).
- Uma ferramenta de BI (métricas de impacto são registradas, não calculadas a partir da carteira).

A fronteira com o motor de decisão é deliberada: o CreditOps é a **fonte de verdade do "porquê" e do "o quê"**; motores e sistemas operacionais consomem a versão vigente (por exportação ou API) e implementam o "como".

## Visão do produto

> **"Toda regra de crédito da empresa tem uma versão vigente única, um histórico completo e uma trilha de aprovação — encontrável em menos de 30 segundos."**

### Pilares

1. **Fonte única de verdade** — se não está no CreditOps, não é política oficial.
2. **Histórico imutável** — versões nunca são editadas ou apagadas; o passado é sempre reconstruível.
3. **Aprovação como evidência** — cada publicação carrega quem criou, quem revisou, quem aprovou e quando, de forma não repudiável.
4. **Simplicidade radical de operação** — um processo Python, um arquivo de banco, backup = copiar uma pasta.
5. **IA como acelerador, nunca como dependência** — tudo que a IA faz pode ser feito manualmente.

### Princípios de design

- **Escrever política deve ser tão fácil quanto escrever um documento** (Markdown estruturado + campos de metadados), senão o time volta para o Word.
- **Ler deve ser mais fácil que perguntar para um colega** (busca rápida, catálogo navegável, "versão vigente" sempre em destaque).
- **Aprovar deve caber em 2 minutos** (fila de pendências do aprovador, diff legível, aprovação com um clique + justificativa).
- **Auditar deve ser autosserviço** (exportação de trilha e histórico sem depender de TI).

### Métricas de sucesso (norte do produto)

| Métrica | Alvo inicial |
|---------|--------------|
| % de políticas de crédito ativas cadastradas no sistema | > 90% em 6 meses |
| Tempo para localizar a versão vigente de uma política | < 30 segundos |
| Tempo para reconstruir histórico de uma política para auditoria | < 5 minutos |
| % de publicações com aprovação registrada no sistema | 100% (por construção) |
| Tempo médio do ciclo rascunho → publicado | Redução de 50% vs. processo por e-mail |

## Objetivos

1. **Centralizar** todas as políticas de crédito em um catálogo único e pesquisável.
2. **Versionar** cada política com histórico imutável e diffs entre versões.
3. **Formalizar** o fluxo de aprovação com papéis, estados e evidências.
4. **Separar** aprovação, publicação e vigência como eventos distintos e datados.
5. **Auditar** toda ação relevante em trilha append-only exportável.
6. **Operar** em infraestrutura mínima (1 servidor Python, sem SaaS obrigatório).
7. **Preparar** o caminho para evolução SaaS sem reescrita (multi-tenant, SSO, integrações).
