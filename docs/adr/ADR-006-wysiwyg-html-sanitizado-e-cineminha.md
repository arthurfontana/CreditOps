# ADR-006: WYSIWYG (HTML sanitizado) e Cineminha como entidade de primeira classe

**Status**: Aceito · **Data**: 2026-07-07 · **Substitui parcialmente**: ADR-005

## Contexto

Os autores de demandas escrevem documentos ricos (negrito, títulos, listas,
tabelas, prints de matrizes) no Word e anexavam o `.docx`. O editor Markdown
em textarea era hostil para esse perfil de usuário, e as matrizes de política
("cineminhas" — interseção de dois eixos de score/grupo com valores de corte)
entravam como imagem de Excel: sem diff, sem trilha, sem reuso.

## Decisão

1. **Editor WYSIWYG (Quill 2, vendorado em `app/web/static`)** para a descrição
   da demanda (`change_request.description_html`) e o corpo da versão
   (`policy_version.body_html`). O HTML é **sanitizado no servidor** com nh3
   (whitelist de tags/atributos, `app/services/richtext.py`) — a garantia
   anti-XSS que antes vinha do `html=False` do markdown-it é preservada.
   Imagens coladas viajam como data URL dentro do HTML (limite de 5MB por
   documento). O CSP libera `style-src 'unsafe-inline'` (cores de matriz e do
   editor); `script-src` continua estrito.
2. **Markdown continua suportado como legado**: `body_md`/`description_md`
   permanecem e são exibidos quando o campo HTML está vazio. Busca (FTS), diff
   e exports usam o **texto extraído** do HTML (`richtext.body_text`) — o hash
   de conteúdo passa a incluir `body_html`, e o trigger de imutabilidade cobre
   a coluna nova.
3. **Cineminha como entidade estruturada** (`app/models/cinema.py`):
   `DecisionVariable` (catálogo de dimensões com domínio padrão ordenado),
   `Cinema` (entrada estável da biblioteca), `CinemaVersion` (snapshot imutável
   da matriz; origem `manual` ou `promotion`) e `CinemaInstance` (cópia de
   trabalho dentro da demanda). Ao entrar em vigor a versão de política
   vinculada à demanda, `workflow_service.make_effective` promove as instâncias
   a novas versões da biblioteca **na mesma transação** (retroalimentação),
   tudo auditado. Instância cuja origem deixou de ser a versão vigente é
   sinalizada como defasada, com re-base opcional que preserva as edições.
4. **Export**: demanda exporta para `.docx` (python-docx — matrizes como
   tabelas nativas coloridas com destaque de caselas alteradas) e visão de
   impressão (CSS print → PDF pelo navegador).

## Consequências

- Experiência "Word do dia a dia" (colar do Word/Excel preserva formatação);
  matrizes deixam de ser prints e ganham diff casela a casela e trilha
  demanda → vigência → biblioteca.
- **Backlog assumido**: o diff de corpo entre versões HTML usa o texto
  extraído — mais fraco que o diff de Markdown (perde formatação). Caminhos
  futuros: diff estrutural de HTML normalizado ou diff visual lado a lado.
- Duas dependências novas e pinadas: `nh3` (sanitização) e `python-docx`
  (export), ambas instaláveis offline via wheelhouse como as demais.
