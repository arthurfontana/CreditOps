# 8. IA Modular e Opcional

## Princípio

> **A IA é um acelerador plugável. O core funciona 100% sem ela, e nenhuma funcionalidade de governança depende dela.**

Consequências práticas:
- A aplicação sobe e opera sem nenhuma credencial de IA configurada.
- Toda saída de IA é **sugestão** que um humano confirma — IA nunca grava direto em versão, aprovação ou auditoria.
- Trocar de provedor (OpenAI ↔ Claude ↔ Gemini ↔ modelo interno ↔ nenhum) é mudança de **configuração**, não de código.

## Arquitetura do módulo

```
app/services/*  ──emite──►  eventos de domínio / chamadas explícitas de sugestão
                                   │
                          ┌────────▼─────────┐
                          │  ai/service.py    │   fachada única; se provider=none,
                          │  (AIService)      │   toda chamada retorna "indisponível"
                          └────────┬─────────┘
                                   │ interface AIProvider (contrato)
        ┌──────────┬───────────────┼───────────────┬──────────────┐
   ┌────▼───┐ ┌────▼────┐    ┌─────▼─────┐   ┌─────▼─────┐  ┌─────▼────┐
   │ none   │ │ openai  │    │ anthropic │   │  gemini   │  │ internal │
   │(padrão)│ │ adapter │    │  adapter  │   │  adapter  │  │ (OpenAI- │
   └────────┘ └─────────┘    └───────────┘   └───────────┘  │ compat / │
                                                            │ Ollama)  │
                                                            └──────────┘
```

### O contrato (`AIProvider`)

```python
class AIProvider(Protocol):
    def complete(self, prompt: str, *, system: str | None = None,
                 max_tokens: int = 1024) -> AIResult: ...
    def health(self) -> bool: ...
```

Regras do contrato:
- **Uma única primitiva** (`complete`). Casos de uso (resumir, classificar, extrair) são implementados **acima** do provider, em `ai/tasks/`, com prompts versionados em `prompts/runtime/`. Assim o provedor é 100% intercambiável.
- Adapters usam **HTTP puro** (`httpx`) contra as APIs — sem SDKs pesados, menos dependências para aprovar na TI.
- `AIResult` carrega texto + metadados (provedor, modelo, tokens, latência) para custo/telemetria.
- Timeout curto e **fail-soft**: erro de IA vira "sugestão indisponível" na UI, nunca erro de sistema.

### Configuração e credenciais

```toml
# config/settings.toml
[ai]
provider = "none"            # none | openai | anthropic | gemini | internal
model = ""                   # ex.: "claude-sonnet-5"
base_url = ""                # para gateways internos / proxies corporativos
timeout_seconds = 30

[ai.features]                # cada feature liga/desliga individualmente
summarize_diff = false
suggest_tags = false
draft_from_document = false
qa_search = false
```

- **Credenciais nunca vão para o banco nem para o repositório**: somente variável de ambiente (`CREDITOPS_AI_API_KEY`) ou arquivo com permissão restrita referenciado por env (`CREDITOPS_AI_KEY_FILE`).
- `base_url` configurável permite usar **gateways corporativos** (Azure OpenAI, proxies internos, LiteLLM) sem tocar código.
- Log de uso de IA vai para a trilha de auditoria (`ai.suggestion_generated`), incluindo qual texto foi sugerido e se foi aceito — a IA também é auditada.

## Casos de uso (todos opcionais, todos com fallback manual)

| Caso de uso | Sem IA | Com IA | Fase |
|---|---|---|---|
| **Resumo de mudança** | Autor escreve `change_summary` | IA gera rascunho do resumo a partir do diff; autor edita/confirma | v2 |
| **Classificação/tags** | Autor escolhe tags e tipo | IA sugere com base no conteúdo | v2 |
| **Rascunho a partir de legado** | Autor cola/transcreve o documento antigo | IA converte doc legado em Markdown estruturado no template; autor revisa | v2 |
| **Perguntas sobre políticas** | Busca FTS5 | RAG local: FTS5/embeddings selecionam trechos → IA responde citando política e versão | v2/enterprise |
| **Narrativa de auditoria** | Dossiê estruturado | IA redige narrativa cronológica do histórico para o relatório | enterprise |
| **Verificação de consistência** | Revisão humana | IA aponta conflitos entre políticas (ex.: limites contraditórios) | enterprise |

### RAG sem dependência externa

Para "perguntas sobre políticas" em ambiente fechado:
1. **Retrieval**: FTS5 (keyword) já embutido; embeddings opcionais com modelo local (ex.: sentence-transformers) gravados em tabela SQLite — sem serviço de vetor externo.
2. **Generation**: qualquer provider do contrato, inclusive modelo interno via endpoint OpenAI-compatible (Ollama/vLLM).
3. Se não houver modelo de geração: o retrieval sozinho vira "busca melhorada" — ainda útil.

## Como evitar dependência tecnológica

1. **Formato canônico é Markdown + JSON** — legível sem o sistema, exportável a qualquer momento.
2. **Prompts são artefatos versionados** (`prompts/runtime/*.md`), com placeholders documentados — trocar de modelo = reavaliar prompts, não reescrever features.
3. **Uma primitiva, N adapters** — adicionar provedor novo = 1 arquivo de ~50 linhas.
4. **Features individuais desligáveis** — se um provedor degrada, desliga-se a feature, não o sistema.
5. **Nenhum dado sai do ambiente sem configuração explícita** — com `provider = none` (padrão), garantia por construção de que conteúdo de política não vaza para serviço externo. Ativar IA externa exige decisão consciente do admin (e aviso na UI de que o conteúdo será enviado ao provedor X).
