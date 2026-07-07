/* Grade interativa do cineminha — mesma experiência do simulador:
 * clicar liga/desliga a casela (elegibilidade) ou "pinta" o valor
 * selecionado na paleta (oferta). Clique no cabeçalho aplica à linha/
 * coluna inteira. Caselas alteradas vs. a origem ganham contorno azul.
 *
 * Uso: contêiner .cinema-grid com data-config="#idDoScriptJSON" e
 * data-input="#idDoHiddenInput". O JSON: {cinemaType, rowDomain,
 * colDomain, cells, baseline}. O hidden input recebe o cells JSON.
 */
(function () {
  "use strict";

  const SEP = "|";

  function cellValue(type, cells, key) {
    const raw = cells[key];
    if (raw === undefined || raw === null) return type === "eligibility" ? 1 : 0;
    return raw;
  }

  function offerColor(value, max) {
    if (value <= 0) return { bg: "#f8696b", fg: "#7f1d1d" };
    const t = max > 0 ? value / max : 0;
    if (t >= 0.66) return { bg: "#63be7b", fg: "#14532d" };
    if (t >= 0.33) return { bg: "#ffeb84", fg: "#713f12" };
    return { bg: "#f8b76b", fg: "#7c2d12" };
  }

  function initGrid(container) {
    const configEl = document.querySelector(container.dataset.config);
    const input = document.querySelector(container.dataset.input);
    if (!configEl || !input) return;
    const cfg = JSON.parse(configEl.textContent);
    const type = cfg.cinemaType;
    const cells = Object.assign({}, cfg.cells || {});
    const baseline = cfg.baseline; // null = sem origem (nada a destacar)
    const readonly = container.dataset.readonly === "true";

    let paintValue = 1; // valor ativo da paleta (oferta)

    function maxValue() {
      let max = 0;
      cfg.rowDomain.forEach(function (r) {
        cfg.colDomain.forEach(function (c) {
          max = Math.max(max, Number(cellValue(type, cells, r + SEP + c)));
        });
      });
      return max;
    }

    function isChanged(key) {
      if (!baseline) return false;
      return cellValue(type, cells, key) !== cellValue(type, baseline, key);
    }

    function sync() {
      input.value = JSON.stringify(cells);
      const badge = container.querySelector(".cg-changed-count");
      if (badge && baseline) {
        let n = 0;
        cfg.rowDomain.forEach(function (r) {
          cfg.colDomain.forEach(function (c) {
            if (isChanged(r + SEP + c)) n++;
          });
        });
        badge.textContent = n
          ? n + " casela(s) alterada(s) vs. origem"
          : "sem alterações vs. origem";
      }
    }

    function applyCell(key) {
      if (type === "eligibility") {
        cells[key] = cellValue(type, cells, key) >= 1 ? 0 : 1;
      } else {
        cells[key] = paintValue;
      }
    }

    function render() {
      const max = maxValue();
      const table = document.createElement("table");
      table.className = "cinema-matrix";

      const head = table.insertRow();
      const corner = document.createElement("th");
      corner.textContent = (cfg.rowLabel || "") + " \\ " + (cfg.colLabel || "");
      head.appendChild(corner);
      cfg.colDomain.forEach(function (c, j) {
        const th = document.createElement("th");
        th.textContent = c;
        if (!readonly) {
          th.title = "Aplicar à coluna inteira";
          th.style.cursor = "pointer";
          th.addEventListener("click", function () {
            cfg.rowDomain.forEach(function (r) { applyCell(r + SEP + c); });
            render(); sync();
          });
        }
        head.appendChild(th);
      });

      cfg.rowDomain.forEach(function (r) {
        const tr = table.insertRow();
        const th = document.createElement("th");
        th.textContent = r;
        if (!readonly) {
          th.title = "Aplicar à linha inteira";
          th.style.cursor = "pointer";
          th.addEventListener("click", function () {
            cfg.colDomain.forEach(function (c) { applyCell(r + SEP + c); });
            render(); sync();
          });
        }
        tr.appendChild(th);

        cfg.colDomain.forEach(function (c) {
          const key = r + SEP + c;
          const td = tr.insertCell();
          const value = Number(cellValue(type, cells, key));
          if (type === "eligibility") {
            td.textContent = value >= 1 ? "✓" : "✗";
            td.style.background = value >= 1 ? "#63be7b" : "#f8696b";
            td.style.color = "#fff";
          } else {
            td.textContent = String(value);
            const color = offerColor(value, max);
            td.style.background = color.bg;
            td.style.color = color.fg;
          }
          if (isChanged(key)) td.classList.add("cg-changed");
          if (!readonly) {
            td.style.cursor = "pointer";
            td.addEventListener("click", function () {
              applyCell(key);
              render(); sync();
            });
          }
        });
      });

      const holder = container.querySelector(".cg-table");
      holder.innerHTML = "";
      holder.appendChild(table);
    }

    // paleta de valores (só oferta, só edição)
    function renderPalette() {
      if (type === "eligibility" || readonly) return;
      const palette = container.querySelector(".cg-palette");
      if (!palette) return;
      const values = new Set([0]);
      Object.keys(cells).forEach(function (k) { values.add(Number(cells[k])); });
      if (baseline) Object.keys(baseline).forEach(function (k) { values.add(Number(baseline[k])); });
      const sorted = Array.from(values).filter(function (v) { return !isNaN(v); })
        .sort(function (a, b) { return b - a; });
      palette.innerHTML = "<span class='cg-palette-label'>Pintar com:</span>";
      sorted.forEach(function (v) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "cg-swatch" + (v === paintValue ? " active" : "");
        btn.textContent = String(v);
        btn.addEventListener("click", function () {
          paintValue = v;
          renderPalette();
        });
        palette.appendChild(btn);
      });
      const add = document.createElement("input");
      add.type = "number";
      add.step = "any";
      add.min = "0";
      add.placeholder = "novo valor";
      add.className = "cg-new-value";
      add.addEventListener("change", function () {
        const v = Number(add.value);
        if (!isNaN(v) && v >= 0) {
          paintValue = v;
          add.value = "";
          renderPalette();
        }
      });
      palette.appendChild(add);
    }

    render();
    renderPalette();
    sync();
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".cinema-grid").forEach(initGrid);
  });
})();
