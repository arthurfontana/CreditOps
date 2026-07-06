# 2. Personas e Fluxo do Usuário

## Personas

### P1 — Analista de Política de Crédito (autor)
- **Quem é**: analista sênior do time de crédito; escreve e mantém as políticas.
- **Dor atual**: escreve em Word/PowerPoint, controla versão por nome de arquivo (`politica_v3_FINAL_revisado2.docx`), coleta aprovação por e-mail.
- **O que precisa**: editor simples, templates, salvar rascunho, ver diff do que mudou, submeter para revisão sem burocracia.
- **Frequência de uso**: diária/semanal.

### P2 — Gerente de Crédito (aprovador)
- **Quem é**: dono formal da política; responde por ela perante risco, auditoria e regulador.
- **Dor atual**: aprova por e-mail sem ver claramente o que mudou; depois não consegue provar o que aprovou.
- **O que precisa**: fila de pendências, **diff legível entre versão vigente e proposta**, aprovar/rejeitar com justificativa em poucos cliques, delegação em férias.
- **Frequência de uso**: semanal; sessões curtas — a experiência de aprovação deve caber em 2 minutos.

### P3 — Revisor técnico / segunda linha (revisor)
- **Quem é**: par do autor, ou área de riscos/compliance que revisa antes da aprovação formal.
- **O que precisa**: comentar em trechos específicos, solicitar mudanças, marcar revisão como concluída.

### P4 — Operação / Mesa de Crédito (consumidor)
- **Quem é**: quem aplica a política no dia a dia (analistas de concessão, sistemas).
- **Dor atual**: não sabe se a planilha que recebeu é a versão atual.
- **O que precisa**: acesso somente leitura, busca rápida, destaque absoluto da **versão em vigor**, notificação quando uma política que acompanha muda.

### P5 — Auditoria / Compliance (auditor)
- **Quem é**: auditoria interna, compliance, ou auditor externo com acesso supervisionado.
- **O que precisa**: reconstruir o estado de qualquer política em qualquer data ("time travel"), exportar trilha de auditoria, ver cadeia de aprovação de cada publicação.

### P6 — Administrador do sistema (TI / governança)
- **O que precisa**: gestão de usuários e papéis, backup, configuração de áreas/produtos/segmentos, ativação opcional do módulo de IA.

## Fluxos principais

### F1 — Criar e publicar uma nova política (caminho feliz)

```
Autor                    Revisor                Gerente (aprovador)      Sistema
  │                         │                         │                    │
  ├─ cria rascunho ────────►│                         │                    │
  ├─ edita (n iterações)    │                         │                    │
  ├─ submete p/ revisão ───►│                         │                    │
  │                         ├─ comenta/solicita ajustes                    │
  │◄─ ajusta e re-submete ──┤                         │                    │
  │                         ├─ marca revisado ───────►│                    │
  │                         │                         ├─ vê diff + contexto│
  │                         │                         ├─ aprova ──────────►│
  │                         │                         │                    ├─ registra aprovação
  ├─ agenda publicação (data de vigência) ────────────┼───────────────────►│
  │                         │                         │                    ├─ publica versão
  │                         │                         │                    ├─ na data de vigência:
  │                         │                         │                    │   marca EM VIGOR e
  │                         │                         │                    │   substitui a anterior
```

Pontos de atenção de UX:
- O autor nunca "perde" trabalho: rascunho salva automaticamente.
- O aprovador vê **o diff, a justificativa e o impacto esperado** na mesma tela — sem abrir anexos.
- A vigência pode ser imediata na publicação ou agendada para data futura.

### F2 — Alterar uma política vigente

1. Autor abre a política vigente e clica em **"Nova revisão"** → sistema cria um rascunho *a partir de uma cópia da versão vigente* (nunca edita a vigente).
2. Autor edita, preenche **justificativa da alteração** e **impacto esperado** (campos obrigatórios para submeter).
3. Segue o fluxo F1. Ao entrar em vigor, a versão anterior transita automaticamente para **Substituída** — permanece legível no histórico para sempre.

### F3 — Consultar a versão vigente (operação)

1. Usuário busca por título, código, produto, segmento ou tag.
2. Resultado mostra a política com selo **EM VIGOR desde DD/MM/AAAA — v7**.
3. Um clique em "Histórico" mostra a linha do tempo de versões; um clique em qualquer versão mostra o conteúdo daquela época e o diff contra a atual.

### F4 — Rejeição e retrabalho

1. Aprovador rejeita com justificativa obrigatória.
2. Versão volta para **Rascunho** (mantendo comentários e histórico da tentativa).
3. Autor ajusta e re-submete; o número da versão proposta não muda até ser publicada.

### F5 — Rollback

1. Detecta-se problema na política vigente (ex.: regra causou aumento de inadimplência).
2. Usuário com papel de aprovador aciona **Rollback** apontando a versão anterior desejada.
3. O sistema **não apaga nada**: cria uma nova versão cujo conteúdo é cópia da versão alvo, com justificativa obrigatória, e a submete a um fluxo de aprovação **expresso** (aprovação única do gerente).
4. Publicada, ela entra em vigor e a versão problemática vira **Substituída**, com anotação de rollback no histórico.

> Rollback é sempre *roll-forward* de conteúdo antigo: o histórico linear é preservado e a auditoria enxerga exatamente o que aconteceu.

### F6 — Auditoria ("como era em 15/03?")

1. Auditor abre a política → aba "Histórico" → seleciona a data.
2. Sistema mostra a versão que estava em vigor naquela data, com quem aprovou, quando foi publicada e a trilha completa.
3. Botão "Exportar dossiê" gera pacote (Markdown/PDF + JSON de metadados + trilha) para anexar ao papel de trabalho.

## Usabilidade corporativa — requisitos

- **Rápido**: páginas renderizam em < 1s em rede interna; busca com resposta imediata (FTS local).
- **Objetivo**: a home de cada perfil é a sua fila de trabalho (rascunhos do autor, pendências do revisor/aprovador, políticas seguidas pelo consumidor).
- **Fácil de adotar**: importação inicial de documentos legados (Word/PDF como anexo + corpo em Markdown), templates por tipo de política, zero instalação no cliente (web).
- **Sem fricção de login**: integração com o diretório corporativo quando disponível (LDAP/SSO na v2); no MVP, usuário/senha local gerido pelo admin.
- **Notificações**: e-mail interno (SMTP corporativo) para eventos de workflow — opcional e configurável.
