/* Editor WYSIWYG (Quill, vendorado) — experiência "Word do dia a dia".
 *
 * Uso: um contêiner .rich-editor com data-input="#idDoHiddenInput" e,
 * opcionalmente, data-autosave-url + data-autosave-field para autosave.
 * O HTML é sincronizado no hidden input a cada mudança (o form envia o
 * conteúdo mesmo em submit normal); a sanitização de verdade é no servidor.
 * Colar do Word/Excel funciona nativamente (Quill converte o clipboard).
 */
(function () {
  "use strict";

  const TOOLBAR = [
    [{ header: [1, 2, 3, false] }],
    ["bold", "italic", "underline", "strike"],
    [{ color: [] }, { background: [] }],
    [{ list: "ordered" }, { list: "bullet" }],
    [{ indent: "-1" }, { indent: "+1" }, { align: [] }],
    ["blockquote", "code-block", "link", "image"],
    ["clean"],
  ];

  // root.innerHTML em vez de getSemanticHTML(): este último troca espaços
  // por &nbsp;, poluindo o HTML salvo e a extração de texto (busca/diff)
  function editorHTML(quill) {
    return quill.root.innerHTML;
  }

  function initEditor(container) {
    const input = document.querySelector(container.dataset.input);
    if (!input || typeof Quill === "undefined") return;

    const quill = new Quill(container, {
      theme: "snow",
      modules: { toolbar: TOOLBAR },
      placeholder: container.dataset.placeholder || "Escreva aqui…",
    });

    // conteúdo inicial vem do hidden input (HTML já sanitizado pelo servidor)
    if (input.value) {
      quill.clipboard.dangerouslyPasteHTML(input.value);
    }

    let dirty = false;
    quill.on("text-change", function () {
      input.value = editorHTML(quill);
      dirty = true;
    });

    // sincroniza também no submit (cinto e suspensório)
    const form = input.form;
    if (form) {
      form.addEventListener("submit", function () {
        input.value = editorHTML(quill);
      });
    }

    // autosave opcional (rascunho de versão): POST periódico do form
    const autosaveUrl = container.dataset.autosaveUrl;
    if (autosaveUrl && form) {
      const indicator = document.getElementById("save-indicator");
      setInterval(function () {
        if (!dirty) return;
        dirty = false;
        input.value = editorHTML(quill);
        fetch(autosaveUrl, {
          method: "POST",
          body: new FormData(form),
          headers: { "HX-Request": "true" },
        })
          .then(function (resp) { return resp.text(); })
          .then(function (html) { if (indicator) indicator.innerHTML = html; })
          .catch(function () {
            if (indicator) indicator.textContent = "falha ao salvar — verifique a conexão";
          });
      }, 30000);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".rich-editor").forEach(initEditor);
  });
})();
