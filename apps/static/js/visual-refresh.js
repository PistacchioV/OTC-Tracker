/* ============================================================================
   visual-refresh.js  —  Animações de entrada por seção (Framer-like)
   ----------------------------------------------------------------------------
   Marca os cards/blocos com .vr-reveal e os revela (adiciona .vr-in) quando
   entram na viewport, em stagger. Não toca em markup existente no servidor:
   aplica as classes no cliente. Respeita prefers-reduced-motion e é seguro
   caso IntersectionObserver não exista.
   ========================================================================== */
(function () {
  "use strict";

  var reduce =
    window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Seletores dos blocos que ganham animação de entrada.
  var SELECTOR = ".content-page .card, .content-page .page-title-head";

  function collect() {
    return Array.prototype.slice.call(document.querySelectorAll(SELECTOR));
  }

  function init() {
    if (reduce || !("IntersectionObserver" in window)) return;

    var items = collect();
    if (!items.length) return;

    // Marca cada bloco e aplica um pequeno delay em stagger por proximidade.
    items.forEach(function (el, i) {
      if (el.classList.contains("vr-reveal")) return;
      el.classList.add("vr-reveal");
      // Stagger suave (limitado) para não atrasar demais páginas com muitos cards.
      el.style.transitionDelay = Math.min(i * 55, 320) + "ms";
    });

    var io = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add("vr-in");
            io.unobserve(entry.target);
          }
        });
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.06 }
    );

    items.forEach(function (el) {
      io.observe(el);
    });

    // Fallback: garante que tudo fique visível após 1.2s (caso algo falhe).
    setTimeout(function () {
      items.forEach(function (el) {
        el.classList.add("vr-in");
      });
    }, 1200);
  }

  // Marca o link ativo do nav central conforme a rota atual.
  function markActiveNav() {
    var path = window.location.pathname || "/";
    var links = document.querySelectorAll(".vr-topnav a[data-vrnav]");
    var best = null;
    var bestLen = -1;
    links.forEach(function (a) {
      var key = a.getAttribute("data-vrnav") || "";
      if (key && (path === key || path.indexOf(key) === 0) && key.length > bestLen) {
        best = a;
        bestLen = key.length;
      }
    });
    if (best) best.classList.add("vr-active");
  }

  // Drawer de navegação: o botão de menu do navbar abre a sidebar completa
  // (com todos os submenus) deslizando sobre o conteúdo.
  function initNavDrawer() {
    var btn = document.getElementById("vr-menu-btn");
    var sidenav = document.querySelector(".sidenav-menu");
    if (!btn || !sidenav) return;

    var backdrop = document.createElement("div");
    backdrop.className = "vr-nav-backdrop";
    document.body.appendChild(backdrop);

    function open() { document.body.classList.add("vr-nav-open"); }
    function close() { document.body.classList.remove("vr-nav-open"); }
    function toggle() { document.body.classList.toggle("vr-nav-open"); }

    // ── Botão de FIXAR (pin): docka a sidebar e encolhe o conteúdo ──
    var PINKEY = "otc_nav_pinned";
    var pinBtn = document.createElement("button");
    pinBtn.className = "vr-pin-btn";
    pinBtn.type = "button";
    pinBtn.title = "Pin / unpin menu";
    pinBtn.setAttribute("aria-label", "Pin menu");
    pinBtn.innerHTML = '<i data-lucide="pin"></i>';
    sidenav.appendChild(pinBtn);
    if (typeof lucide !== "undefined" && lucide.createIcons) lucide.createIcons();

    // Quando dockada, forçamos a sidebar para tamanho fixo "default" para
    // neutralizar o modo nativo "on-hover" (que a deixa colapsada/expandindo
    // no hover) — guardamos o tamanho anterior para restaurar ao desafixar.
    var PREVSIZEKEY = "otc_nav_prevsize";
    var htmlEl = document.documentElement;
    function forceFixedSidenav() {
      var cur = htmlEl.getAttribute("data-sidenav-size") || "default";
      if (cur !== "default") {
        try { localStorage.setItem(PREVSIZEKEY, cur); } catch (e) {}
      }
      htmlEl.setAttribute("data-sidenav-size", "default");
    }
    function restoreSidenavSize() {
      var prev = "";
      try { prev = localStorage.getItem(PREVSIZEKEY) || ""; } catch (e) {}
      if (prev) htmlEl.setAttribute("data-sidenav-size", prev);
    }
    function setPinned(on) {
      document.body.classList.toggle("vr-nav-pinned", on);
      if (on) {
        document.body.classList.remove("vr-nav-open"); // dockada, sem overlay
        forceFixedSidenav();
      } else {
        restoreSidenavSize();
      }
      try { localStorage.setItem(PINKEY, on ? "1" : "0"); } catch (e) {}
    }
    pinBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      setPinned(!document.body.classList.contains("vr-nav-pinned"));
    });
    try {
      if (localStorage.getItem(PINKEY) === "1") {
        document.body.classList.add("vr-nav-pinned");
        forceFixedSidenav();
      }
    } catch (e) {}

    btn.addEventListener("click", toggle);
    backdrop.addEventListener("click", close);
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") close();
    });
    // Fecha ao navegar por um link do menu (leva para outra página).
    sidenav.addEventListener("click", function (e) {
      var a = e.target.closest("a[href]");
      if (!a) return;
      var href = a.getAttribute("href") || "";
      // ignora toggles de submenu (href vazio / javascript:)
      if (href && href !== "#" && href.indexOf("javascript:") !== 0) close();
    });
  }

  // ── Theme toggle (sol/lua) — usa a persistência nativa do app ──────────────
  function initThemeToggle() {
    var btn = document.getElementById("vr-theme-btn");
    if (!btn) return;
    var KEY = "__OTCTRACKER_CONFIG__";
    function setTheme(t) {
      document.documentElement.setAttribute("data-bs-theme", t);
      try {
        var c = JSON.parse(localStorage.getItem(KEY) || "null") || window.config || {};
        c.theme = t;
        localStorage.setItem(KEY, JSON.stringify(c));
        if (window.config) window.config.theme = t;
      } catch (e) {}
    }
    btn.addEventListener("click", function () {
      var cur = document.documentElement.getAttribute("data-bs-theme");
      setTheme(cur === "dark" ? "light" : "dark");
    });
  }

  // ── Nav central: gera dropdowns por seção a partir da sidebar ──────────────
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  // Re-aplica as traduções (default EN nos data-lang) ao conteúdo gerado por JS.
  function applyI18n() {
    try { if (window.otcI18n && window.otcI18n.applyTranslations) window.otcI18n.applyTranslations(); } catch (e) {}
  }
  function textOf(a) {
    var mt = a.querySelector(".menu-text");
    return (mt ? mt.textContent : a.textContent || "").trim();
  }
  function langOf(a) {
    var mt = a.querySelector(".menu-text[data-lang]") || a.querySelector("[data-lang]");
    return mt ? (mt.getAttribute("data-lang") || "") : "";
  }
  function parseItem(li) {
    var a = null;
    // âncora direta do item (não das subvias)
    for (var i = 0; i < li.children.length; i++) {
      if (li.children[i].tagName === "A") { a = li.children[i]; break; }
    }
    // submenu <ul> pode ser filha direta OU estar dentro de <div class="collapse">
    var submenu = null;
    for (var j = 0; j < li.children.length; j++) {
      var ch = li.children[j];
      if (ch.tagName === "UL") { submenu = ch; break; }
      if (ch.tagName === "DIV") {
        var innerUl = ch.querySelector("ul");
        if (innerUl) { submenu = innerUl; break; }
      }
    }
    var href = a ? a.getAttribute("href") : null;
    var isLeaf = !!(href && href.charAt(0) === "/");
    var node = { text: a ? textOf(a) : "", lang: a ? langOf(a) : "", href: isLeaf ? href : null, children: [] };
    if (submenu) {
      Array.prototype.forEach.call(submenu.children, function (c) {
        if (c.classList && c.classList.contains("side-nav-item")) node.children.push(parseItem(c));
      });
    }
    return node;
  }
  function renderNode(node) {
    if (node.href) {
      return '<a href="' + esc(node.href) + '" class="vr-dd-link">' + esc(node.text) + "</a>";
    }
    if (!node.children.length) return "";
    var inner = node.children.map(renderNode).join("");
    if (!inner) return "";
    return '<div class="vr-dd-group"><div class="vr-dd-head">' + esc(node.text) + "</div>" + inner + "</div>";
  }
  function buildTopNav() {
    var container = document.getElementById("vr-topnav");
    var sideNav = document.querySelector(".sidenav-menu .side-nav");
    if (!container || !sideNav) return;

    // agrupa itens de topo por seção (.side-nav-title); pára em "Components"
    // (dali em diante são páginas de template, não do negócio)
    var sections = [];
    var current = null;
    var stopped = false;
    Array.prototype.forEach.call(sideNav.children, function (li) {
      if (!li.classList) return;
      if (li.classList.contains("side-nav-title")) {
        var t = (li.textContent || "").trim();
        if (/^components$|^components /i.test(t) || /componentes/i.test(t)) { stopped = true; current = null; return; }
        if (stopped) return;
        current = { title: t, items: [] };
        sections.push(current);
      } else if (!stopped && current && li.classList.contains("side-nav-item")) {
        current.items.push(parseItem(li));
      }
    });

    var path = window.location.pathname || "/";
    var html = "";
    sections.forEach(function (sec, idx) {
      var body = sec.items.map(renderNode).join("");
      if (!body) return;
      var label = sec.title || "Menu";
      if (/^main$/i.test(label)) label = "Home";
      // seção ativa se a rota atual estiver entre seus links
      var active = body.indexOf('href="' + path + '"') !== -1;
      html +=
        '<div class="vr-dd" data-idx="' + idx + '">' +
          '<button class="vr-dd-btn' + (active ? " vr-active" : "") + '" type="button">' +
            esc(label) + '<i data-lucide="chevron-down"></i>' +
          "</button>" +
          '<div class="vr-dd-menu">' + body + "</div>" +
        "</div>";
    });
    container.innerHTML = html;

    // abre/fecha
    container.querySelectorAll(".vr-dd-btn").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        var dd = btn.parentNode;
        var wasOpen = dd.classList.contains("vr-open");
        container.querySelectorAll(".vr-dd.vr-open").forEach(function (o) { o.classList.remove("vr-open"); });
        if (!wasOpen) dd.classList.add("vr-open");
      });
    });
    document.addEventListener("click", function () {
      container.querySelectorAll(".vr-dd.vr-open").forEach(function (o) { o.classList.remove("vr-open"); });
    });

    if (typeof lucide !== "undefined" && lucide.createIcons) lucide.createIcons();
  }

  // ── Nav central PERSONALIZÁVEL: cada usuário escolhe os atalhos ────────────
  // As opções são construídas a partir da PRÓPRIA sidebar (todas as páginas,
  // com seus grupos e subgrupos), então o editor sempre reflete o menu real.
  function initTopNavCustom() {
    var nav = document.getElementById("vr-topnav");
    if (!nav) return;
    var SID = (nav.getAttribute("data-sid") || "").trim().toUpperCase();
    var KEY = "otc_topnav_" + (SID || "anon");
    var MAX = 7;
    var DEFAULTS = ["/dashboard", "/live-position-ndf", "/pending-confirmation", "/reconciliation-payrec", "/reference-data"];
    var allowed = null; // {href:1} ou null = tudo liberado

    // ── Constrói a árvore de seções/subgrupos/páginas a partir da sidebar ──
    var SECTIONS = null; // [{ title, lang, nodes:[node,...] }]
    var OPTMAP = {};     // href -> { href, text, lang }
    var ORDER = [];      // hrefs em ordem da sidebar (para salvar consistente)

    function pickSource() {
      var lists = document.querySelectorAll(".sidenav-menu .side-nav");
      var best = null, bestN = -1;
      Array.prototype.forEach.call(lists, function (ul) {
        var n = ul.querySelectorAll("a[href^='/']").length;
        if (n > bestN) { bestN = n; best = ul; }
      });
      return best;
    }

    function buildSections() {
      if (SECTIONS) return SECTIONS;
      SECTIONS = [];
      OPTMAP = {}; ORDER = [];
      var src = pickSource();
      if (!src) return SECTIONS;
      var current = null, stopped = false;
      Array.prototype.forEach.call(src.children, function (li) {
        if (!li.classList) return;
        if (li.classList.contains("side-nav-title")) {
          var t = (li.textContent || "").trim();
          if (/^components/i.test(t) || /componentes/i.test(t)) { stopped = true; current = null; return; }
          if (stopped) return;
          current = { title: t, lang: li.getAttribute("data-lang") || "", nodes: [] };
          SECTIONS.push(current);
        } else if (!stopped && current && li.classList.contains("side-nav-item")) {
          current.nodes.push(parseItem(li));
        }
      });
      // indexa todas as folhas (páginas) na ordem da sidebar, guardando o
      // ramo pai (para desambiguar rótulos genéricos no nav de topo).
      function walk(node, parent) {
        if (node.href) {
          if (!OPTMAP[node.href]) {
            OPTMAP[node.href] = {
              href: node.href, text: node.text, lang: node.lang,
              parentText: parent ? parent.text : "", parentLang: parent ? parent.lang : ""
            };
            ORDER.push(node.href);
          }
        } else { node.children.forEach(function (c) { walk(c, node); }); }
      }
      SECTIONS.forEach(function (s) { s.nodes.forEach(function (n) { walk(n, null); }); });
      // conta rótulos duplicados para saber quais precisam do contexto do pai
      var counts = {};
      ORDER.forEach(function (h) { var t = (OPTMAP[h].text || "").toLowerCase(); counts[t] = (counts[t] || 0) + 1; });
      // rótulos ambíguos por si só (precisam do nome do grupo pai)
      var GENERIC = { "main": 1, "summary": 1, "ndf": 1, "option": 1, "options": 1, "swap": 1, "overview": 1, "detail": 1, "list": 1 };
      ORDER.forEach(function (h) {
        var o = OPTMAP[h];
        var t = (o.text || "").toLowerCase();
        var ambiguous = counts[t] > 1 || GENERIC[t] === 1;
        // "Main" isolado fica melhor mostrando só o grupo pai (ex.: Pending Confirmation)
        if (t === "main" && o.parentText) {
          o.disp = [{ text: o.parentText, lang: o.parentLang }];
        } else if (ambiguous && o.parentText) {
          o.disp = [{ text: o.parentText, lang: o.parentLang }, { text: o.text, lang: o.lang }];
        } else {
          o.disp = [{ text: o.text, lang: o.lang }];
        }
      });
      return SECTIONS;
    }

    function optOf(h) { return OPTMAP[h] || null; }
    function isAllowed(h) { return !allowed || allowed[h] === 1; }
    function load() { try { var v = JSON.parse(localStorage.getItem(KEY) || "null"); if (Array.isArray(v)) return v; } catch (e) {} return DEFAULTS.slice(); }
    function saveList(list) { try { localStorage.setItem(KEY, JSON.stringify(list)); } catch (e) {} }

    function render() {
      buildSections();
      var chosen = load().filter(function (h) { return optOf(h) && isAllowed(h); });
      if (!chosen.length) chosen = DEFAULTS.filter(function (h) { return optOf(h) && isAllowed(h); });
      var path = window.location.pathname || "/";
      var html = chosen.map(function (h) {
        var o = optOf(h);
        var active = (path === h || path.indexOf(h) === 0);
        var disp = o.disp || [{ text: o.text, lang: o.lang }];
        var inner = disp.map(function (d, i) {
          var langAttr = d.lang ? ' data-lang="' + esc(d.lang) + '"' : "";
          return (i ? " " : "") + "<span" + langAttr + ">" + esc(d.text) + "</span>";
        }).join("");
        return '<a href="' + esc(h) + '"' + (active ? ' class="vr-active"' : "") + ">" + inner + "</a>";
      }).join("");
      html += '<button class="vr-nav-edit" id="vr-nav-edit" type="button" title="Customize menu" aria-label="Customize menu"><i data-lucide="sliders-horizontal"></i></button>';
      nav.innerHTML = html;
      if (typeof lucide !== "undefined" && lucide.createIcons) lucide.createIcons();
      applyI18n();
      var eb = document.getElementById("vr-nav-edit");
      if (eb) eb.addEventListener("click", openEditor);
    }

    // Renderiza um nó do editor: folha => checkbox; ramo => subgrupo destacado.
    function renderEditNode(node, current, depth) {
      if (node.href) {
        if (!isAllowed(node.href)) return "";
        var on = current.indexOf(node.href) !== -1;
        var langAttr = node.lang ? ' data-lang="' + esc(node.lang) + '"' : "";
        return '<label class="vr-navcfg__item" style="padding-left:' + (10 + depth * 14) + 'px">' +
                 '<input type="checkbox" value="' + esc(node.href) + '"' + (on ? " checked" : "") + ">" +
                 "<span" + langAttr + ">" + esc(node.text) + "</span></label>";
      }
      if (!node.children.length) return "";
      var inner = node.children.map(function (c) { return renderEditNode(c, current, depth + 1); }).join("");
      if (!inner) return "";
      var langAttr2 = node.lang ? ' data-lang="' + esc(node.lang) + '"' : "";
      return '<div class="vr-navcfg__sub" style="padding-left:' + (10 + depth * 14) + 'px"' + langAttr2 + ">" + esc(node.text) + "</div>" + inner;
    }

    function openEditor() {
      buildSections();
      var current = load();
      var groupsHtml = SECTIONS.map(function (sec) {
        var body = sec.nodes.map(function (n) { return renderEditNode(n, current, 0); }).join("");
        if (!body) return "";
        var langAttr = sec.lang ? ' data-lang="' + esc(sec.lang) + '"' : "";
        var label = sec.title || "Menu";
        if (/^main$/i.test(label)) label = "Home";
        return '<div class="vr-navcfg__group"><div class="vr-navcfg__grouphead"' + langAttr + ">" + esc(label) + "</div>" + body + "</div>";
      }).join("");

      var backdrop = document.createElement("div");
      backdrop.className = "vr-navcfg-backdrop";
      var panel = document.createElement("div");
      panel.className = "vr-navcfg";
      panel.innerHTML =
        '<div class="vr-navcfg__head"><span data-lang="vr-cfg-title">Customize menu</span><button class="vr-navcfg__x" type="button" aria-label="Close">&times;</button></div>' +
        '<div class="vr-navcfg__hint" data-lang="vr-cfg-hint">Choose which shortcuts appear at the top (max ' + MAX + ").</div>" +
        '<div class="vr-navcfg__body">' + groupsHtml + "</div>" +
        '<div class="vr-navcfg__foot"><button class="vr-navcfg__reset" type="button" data-lang="vr-cfg-reset">Default</button><span class="vr-navcfg__spacer"></span><span class="vr-navcfg__count"></span><button class="vr-navcfg__cancel" type="button" data-lang="vr-cfg-cancel">Cancel</button><button class="vr-navcfg__save" type="button" data-lang="vr-cfg-save">Save</button></div>';
      document.body.appendChild(backdrop);
      document.body.appendChild(panel);
      applyI18n();

      var countEl = panel.querySelector(".vr-navcfg__count");
      function close() { backdrop.remove(); panel.remove(); document.removeEventListener("keydown", onKey); }
      function onKey(e) { if (e.key === "Escape") close(); }
      function syncMax() {
        var n = panel.querySelectorAll("input[type=checkbox]:checked").length;
        var atMax = n >= MAX;
        panel.querySelectorAll("input[type=checkbox]").forEach(function (cb) { if (!cb.checked) cb.disabled = atMax; });
        if (countEl) countEl.textContent = n + "/" + MAX;
      }
      document.addEventListener("keydown", onKey);
      backdrop.addEventListener("click", close);
      panel.querySelector(".vr-navcfg__x").addEventListener("click", close);
      panel.querySelector(".vr-navcfg__cancel").addEventListener("click", close);
      panel.querySelector(".vr-navcfg__body").addEventListener("change", syncMax);
      panel.querySelector(".vr-navcfg__reset").addEventListener("click", function () {
        panel.querySelectorAll("input[type=checkbox]").forEach(function (cb) { cb.checked = DEFAULTS.indexOf(cb.value) !== -1; });
        syncMax();
      });
      panel.querySelector(".vr-navcfg__save").addEventListener("click", function () {
        var chosen = [];
        ORDER.forEach(function (h) {
          var cb = panel.querySelector('input[value="' + h + '"]');
          if (cb && cb.checked) chosen.push(h);
        });
        saveList(chosen);
        render();
        close();
      });
      syncMax();
    }

    // Filtra pelas páginas que o usuário pode acessar (mesmo critério do megamenu),
    // depois renderiza.
    fetch("/api/me/access", { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d && d.success && !d.is_admin && d.configured) {
          allowed = {};
          (d.pages || []).forEach(function (u) { allowed[u] = 1; });
          if (allowed["/"]) allowed["/dashboard"] = 1;
        }
        render();
      })
      .catch(function () { render(); });
  }

  function boot() {
    init();
    initThemeToggle();
    initTopNavCustom();
    initNavDrawer();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
