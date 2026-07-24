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

  function boot() {
    init();
    markActiveNav();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
