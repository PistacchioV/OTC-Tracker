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
  function textOf(a) {
    var mt = a.querySelector(".menu-text");
    return (mt ? mt.textContent : a.textContent || "").trim();
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
    var node = { text: a ? textOf(a) : "", href: isLeaf ? href : null, children: [] };
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

  function boot() {
    init();
    initThemeToggle();
    markActiveNav();
    initNavDrawer();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
