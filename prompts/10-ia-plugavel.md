# Prompt 10 — Módulo de IA plugável (v2, opcional)

> **Anexar ao contexto**: `docs/wiki/08-ia-modular.md` (INTEIRO) e o "Prompt de contexto". Pré-requisitos: prompts 01–09. Esta etapa é OPCIONAL — o sistema está completo sem ela.

---

Implemente o módulo de IA exatamente como especificado na wiki 08.

1. **Contrato** (`app/plugins/ai/base.py`): `AIProvider` (Protocol) com `complete(prompt, *, system=None, max_tokens=1024) -> AIResult` e `health() -> bool`; `AIResult` (dataclass): `text`, `provider`, `model`, `input_tokens`, `output_tokens`, `latency_ms`.

2. **Providers** (`app/plugins/ai/providers/`), todos com `httpx` puro (sem SDKs), timeout de `settings.ai.timeout_seconds`, sem retry além de 1 tentativa:
   - `none.py`: sempre lança `AIUnavailable` — provider padrão;
   - `openai.py`: POST `{base_url}/v1/chat/completions` (compatível também com gateways e Ollama/vLLM via `base_url`);
   - `anthropic.py`: POST `{base_url}/v1/messages` (header `x-api-key`, `anthropic-version`);
   - `gemini.py`: POST `generateContent` da API do Google;
   - `internal.py`: alias de `openai.py` com `base_url` obrigatória (endpoint OpenAI-compatible interno).
   - Credencial: somente `CREDITOPS_AI_API_KEY` ou arquivo apontado por `CREDITOPS_AI_KEY_FILE`. Nunca em banco/log/config commitada.

3. **Fachada** (`app/plugins/ai/service.py`): `AIService` carrega provider conforme `settings.toml [ai]`; expõe `is_enabled(feature)`; toda chamada audita `ai.suggestion_generated` (feature, provider, modelo, tokens, hash do input) e captura exceções → `AIUnavailable`.

4. **Tasks** (`app/plugins/ai/tasks/`) — cada uma carrega seu prompt de `prompts/runtime/` e preenche placeholders:
   - `summarize_diff(diff_text) -> str` (usa `prompts/runtime/summarize_diff.md`);
   - `suggest_tags(body_md, existing_tags) -> list[str]` (`suggest_tags.md`; valide: só tags existentes);
   - `draft_from_document(raw_text, template_md) -> str` (`draft_from_document.md`).

5. **Integração na UI — sempre como sugestão confirmável**:
   - editor de rascunho: botão "Sugerir resumo da mudança" (visível só se feature ligada) → preenche o campo `change_summary` **editável**, com badge "sugerido por IA";
   - idem "Sugerir tags" na edição de metadados (checkboxes pré-marcadas, autor confirma);
   - "Rascunho a partir de documento": admin/autor cola texto legado → gera corpo no template → **sempre cai em draft para revisão humana**;
   - se provider indisponível: botão some ou mostra "IA indisponível" — **nenhum erro de página**;
   - tela admin: configurar provider/modelo/features, botão "testar conexão" (`health()`), aviso destacado: "Ao ativar um provedor externo, o conteúdo das políticas será enviado a <provider>".

6. **Testes** (com `httpx.MockTransport` — sem chamadas reais): provider none desabilita tudo sem quebrar páginas; cada adapter monta request correto e faz parse da resposta; timeout vira `AIUnavailable`; sugestão auditada; `suggest_tags` filtra tags inexistentes; troca de provider por config não exige mudança de código (teste parametrizado sobre os adapters).

**Critérios de aceite**: com `provider="none"` (default) o sistema é idêntico ao do prompt 09; ligando um provider fake (mock server), os 3 botões de sugestão funcionam e tudo fica auditado.
