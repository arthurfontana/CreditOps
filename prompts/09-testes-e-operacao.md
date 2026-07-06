# Prompt 09 — Testes de invariantes, operação e dados de demonstração

> **Anexar ao contexto**: `docs/wiki/12-backlog.md` (épico 7), `docs/wiki/09-seguranca-e-governanca.md` (Continuidade) e o "Prompt de contexto". Pré-requisitos: prompts 01–08.

---

1. **Suíte e2e de invariantes** (`tests/e2e/test_invariants.py`) — os cenários que provam as promessas do produto:
   - **Ciclo de vida completo** com 4 usuários (autor, revisor, aprovador, leitor): criar → submeter → devolver → re-submeter → aprovar → publicar futuro → ativar vigência → nova revisão → publicar → anterior substituída. Verificar em cada passo: status, `current_version_id`, trilha de auditoria e `status_transition`;
   - **Imutabilidade fim-a-fim**: tentar alterar versão publicada por todos os caminhos (service, SQL direto) — tudo falha;
   - **Time travel**: 3 versões com vigências distintas; `version_at` correto para 5 datas incluindo fronteiras;
   - **Rollback**: v3 com problema → rollback para v2 → v4 vigente com conteúdo de v2, v3 superseded, histórico íntegro;
   - **Segregação**: autor não aprova; leitor não edita; admin não aprova;
   - **Rejeição**: preserva comentários, exige justificativa, tudo auditado.

2. **Cobertura**: `pytest --cov=app` ≥ 80% no `app/services/`; adicione ao CI com gate.

3. **Scripts de operação**:
   - `scripts/backup.py`: usa a API de backup do SQLite (cópia consistente com o app rodando) + tar dos anexos + `manifest.json` com SHA-256 de tudo; destino e retenção (default 30 diários) configuráveis;
   - `scripts/restore.py`: restaura de um backup, validando hashes do manifesto antes;
   - `scripts/verify_data.py`: re-calcula `content_hash` de todas as versões congeladas e hashes de anexos; relata divergências (detecção de adulteração);
   - `scripts/seed_demo.py`: cria 3 áreas, 4 produtos, 3 segmentos, 6 usuários (um por papel + extras) senha `demo1234`, e 8 políticas de exemplo realistas de crédito (limite PF, concessão PJ, renegociação, alçadas...) com históricos variados: uma com 4 versões e um rollback, uma aguardando aprovação, uma com vigência futura. Conteúdos em `examples/policies/*.md`.

4. **`docs/runbook.md`**: instalação (incluindo wheelhouse offline), configuração TLS/proxy, backup agendado (cron e Task Scheduler), restore passo a passo, upgrade de versão (git pull + alembic upgrade + restart), troubleshooting (banco travado, migração falhou, sessões inválidas após troca de secret).

5. **Ajustes finais**: rotação de logs (`logging.handlers.RotatingFileHandler` via `config/logging.toml`); headers de segurança (CSP restritiva local, X-Frame-Options DENY, X-Content-Type-Options) como middleware.

**Critérios de aceite**: `seed_demo` + login com cada papel permite demonstrar o produto de ponta a ponta em 10 minutos; backup→restore testado funciona; CI verde com gate de cobertura.
