# 14. Alternativas Melhores ou Mais Simples

Análise honesta: em alguns contextos, **não construir o CreditOps é a resposta certa**. Abaixo, as alternativas consideradas, quando escolhê-las e por que a proposta principal ganha no cenário descrito (ambiente restrito + requisitos de governança de crédito).

## A1 — Git + Markdown puro (GitLab/Gitea interno)

**Ideia**: políticas como arquivos `.md` em um repositório; PR = proposta de mudança; merge = aprovação; tags = releases; CODEOWNERS = aprovadores.

- ✅ Versionamento e diff de graça; ferramenta madura; auditável.
- ✅ Custo de desenvolvimento ~zero.
- ❌ **Público-alvo não usa Git**: gerentes de crédito não vão abrir PRs. A adoção morre aqui.
- ❌ Sem conceito de vigência (aprovado ≠ em vigor), sem campos estruturados, sem time travel por data de negócio, sem fila de aprovação amigável.
- **Quando escolher**: time pequeno e tecnicamente fluente (ex.: política mantida por engenheiros de risco). Nesse caso, é imbatível em custo.
- **Meio-termo interessante**: usar Git como *storage* por trás de uma UI própria. Rejeitado (ADR-003): shell-out para Git em servidor Windows corporativo é frágil, e o banco relacional resolve queries de vigência/auditoria que o Git não tem. Mas a **exportação contínua para um repo Git** (espelho somente leitura) é um plugin barato e valioso — melhor dos dois mundos.

## A2 — Wiki corporativa existente (Confluence/SharePoint)

- ✅ Já aprovado pela TI; adoção fácil; busca decente.
- ❌ Versionamento fraco (histórico de página ≠ versões de negócio com vigência); workflow de aprovação inexistente ou plugin pago; trilha de auditoria insuficiente para regulador; "quem aprovou o quê" vira convenção manual de novo.
- **Quando escolher**: se a exigência for só "documentar em um lugar só", sem governança formal. Se a empresa já tem Confluence Premium com workflow, avaliar seriamente antes de construir.

## A3 — SharePoint Lists / Power Apps (low-code Microsoft)

- ✅ Infra já existente em muitas corporações; sem servidor próprio.
- ❌ Imutabilidade e trilha à prova de adulteração são difíceis de garantir; lock-in de plataforma; versionamento de conteúdo longo é ruim; customização degrada rápido.
- **Quando escolher**: empresa 100% Microsoft, TI veta qualquer servidor novo, e requisitos de auditoria são leves.

## A4 — GRC/BPM de mercado (ServiceNow, SAI360, Interact...)

- ✅ Compliance-grade, suporte, auditoria robusta.
- ❌ Custo alto de licença e implantação; meses de projeto; genérico (não entende "política de crédito" como domínio); depende de fornecedor.
- **Quando escolher**: grande banco com orçamento e exigência regulatória pesada já mapeada para uma dessas suítes. O CreditOps compete exatamente onde essas ferramentas são caras demais: departamentos que precisam começar amanhã.

## A5 — "Planilha melhorada" (registro de decisões + pasta organizada)

Um índice controlado (planilha com dono, versão, link, status) + convenção de pastas + ata de aprovação padrão.

- ✅ Custo zero; melhora imediata sobre o caos.
- ❌ Não resolve imutabilidade, diff, vigência nem trilha; degrada com o tempo.
- **Quando escolher**: como **fase -1** enquanto o MVP é construído — e como argumento de baseline para medir o valor do produto.

## Por que a proposta principal vence no cenário-alvo

| Critério | Git puro | Confluence | Low-code | GRC | **CreditOps** |
|---|---|---|---|---|---|
| Adoção por usuário de negócio | ❌ | ✅ | ✅ | ➖ | ✅ |
| Versões imutáveis + diff | ✅ | ➖ | ❌ | ✅ | ✅ |
| Vigência como conceito de 1ª classe | ❌ | ❌ | ➖ | ➖ | ✅ |
| Workflow de aprovação com evidência | ➖ | ❌/💰 | ➖ | ✅ | ✅ |
| Trilha à prova de adulteração | ✅ | ❌ | ❌ | ✅ | ✅ (hash chain) |
| Roda em 1 servidor Python restrito | ✅ | ❌ | ❌ | ❌ | ✅ |
| Custo | ~0 | licenças | licenças | 💰💰💰 | dev interno |
| Evolui para produto/SaaS | ❌ | ❌ | ❌ | — | ✅ |

**Síntese**: a proposta ocupa um vazio real — governança de nível GRC, usabilidade de wiki, custo e pegada de um script Python. As alternativas ou falham na adoção (Git), ou na auditabilidade (wiki/low-code), ou no custo e na restrição de ambiente (GRC).

## Simplificações recomendadas se o escopo apertar

Se for preciso cortar ainda mais que o MVP:
1. **Cortar comentários** (revisão acontece verbalmente; só a decisão é registrada).
2. **Cortar anexos** (links para o DMS corporativo).
3. **Cortar busca FTS** (filtros de catálogo bastam para < 100 políticas).
4. **Nunca cortar**: versões imutáveis, workflow com aprovação registrada, vigência, trilha de auditoria — sem isso o produto não tem razão de existir.
