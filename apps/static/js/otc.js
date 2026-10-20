/* ============================================================================
   otc.js — a interface do OTC Tracker, num arquivo só
   ----------------------------------------------------------------------------
   Carregado pelo footer-scripts.html depois do vendors.min.js (Bootstrap,
   Lucide, SimpleBar, flatpickr). É o par do otc.css: tudo que o CSS não
   enxerga — preferências de aparência, idioma, menu lateral, paleta de
   comandos, o "gel" dos botões, a lente que desliza, a entrada das páginas e
   o Send que só diz "Sent" depois que o servidor confirmou.

   Contratos que as páginas usam e que este arquivo MANTÉM:
     window.otcI18n (applyTranslations/setLanguage), window.applyTranslations,
     [data-translator-lang], window.ins(), window.debounce(),
     window.vrSyncStickyTables(), localStorage __OTC_TRACKER_LANG__,
     otc_topnav_<SID> (atalhos), __OTC_TRACKER_FX__ (modo opaco).

   O que é LÓGICA de página (funil, export, sessão, preview) continua no seu
   módulo; aqui é só a casca e o movimento.
   ========================================================================== */
(function () {
  'use strict';

  var doc = document;
  var root = doc.documentElement;
  var REDUCED_MOTION = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function ready(fn) {
    if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', fn);
    else fn();
  }
  function $$(sel, ctx) { return Array.prototype.slice.call((ctx || doc).querySelectorAll(sel)); }
  function icons() { if (window.lucide && lucide.createIcons) { try { lucide.createIcons(); } catch (e) {} } }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function lang() { try { return localStorage.getItem('__OTC_TRACKER_LANG__') || 'en'; } catch (e) { return 'en'; } }
  // Textos que este arquivo insere depois do load (o I18nManager traduz uma
  // vez só): mapa local, como em toda página da casa.
  var _TRANS = {
    en: { sent: 'Sent', search: 'Search pages…', none: 'No page matches', goto: 'Go to page', pinned: 'Pinned', customize: 'Customize', menu: 'Menu' },
    br: { sent: 'Enviado', search: 'Buscar páginas…', none: 'Nenhuma página encontrada', goto: 'Ir para a página', pinned: 'Fixados', customize: 'Personalizar', menu: 'Menu' },
    es: { sent: 'Enviado', search: 'Buscar páginas…', none: 'Ninguna página encontrada', goto: 'Ir a la página', pinned: 'Fijados', customize: 'Personalizar', menu: 'Menú' }
  };
  function t(k) { var m = _TRANS[lang()] || _TRANS.en; return m[k] || _TRANS.en[k] || k; }

  // ── Globais herdadas do tema antigo (o dashboard.js usa as duas) ──────────
  window.ins = function (v, a) {
    var val = getComputedStyle(root).getPropertyValue('--ins-' + v).trim();
    if (v.indexOf('-rgb') !== -1) return 'rgba(' + val + ', ' + (a == null ? 1 : a) + ')';
    // token que aponta para outro token: o Chart.js precisa da COR resolvida
    if (val.indexOf('var(') === 0 || val.indexOf('color-mix') === 0) {
      var probe = doc.createElement('span');
      probe.style.color = val;
      probe.style.display = 'none';
      doc.body.appendChild(probe);
      val = getComputedStyle(probe).color;
      probe.remove();
    }
    return val;
  };
  window.debounce = function (fn, wait) {
    var to;
    return function () {
      var ctx = this, args = arguments;
      clearTimeout(to);
      to = setTimeout(function () { fn.apply(ctx, args); }, wait);
    };
  };

  // ==========================================================================
  // 1. Aparência: tema, destaque, papel de parede, vidro, modo opaco
  // ==========================================================================
  // O <head> já aplicou os atributos antes do primeiro paint (head-css.html);
  // aqui fica a API para a Aparência e o botão do tema.
  var UI_KEY = '__OTC_TRACKER_UI__';
  var FX_KEY = '__OTC_TRACKER_FX__';
  var mqDark = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

  function readPrefs() {
    var p = {};
    try { p = JSON.parse(localStorage.getItem(UI_KEY) || '{}') || {}; } catch (e) {}
    return {
      theme: p.theme || 'light',
      accent: p.accent || 'blue',
      wall: p.wall || 'ash',
      glass: p.glass || 'tinted'
    };
  }
  function writePrefs(p) { try { localStorage.setItem(UI_KEY, JSON.stringify(p)); } catch (e) {} }
  function effectiveTheme(pref) {
    if (pref === 'auto') return mqDark && mqDark.matches ? 'dark' : 'light';
    return pref === 'dark' ? 'dark' : 'light';
  }
  function applyPrefs(p, animate) {
    var go = function () {
      root.setAttribute('data-bs-theme', effectiveTheme(p.theme));
      if (p.accent && p.accent !== 'blue') root.setAttribute('data-accent', p.accent); else root.removeAttribute('data-accent');
      if (p.wall && p.wall !== 'ash') root.setAttribute('data-wall', p.wall); else root.removeAttribute('data-wall');
      if (p.glass === 'clear') root.setAttribute('data-glass', 'clear'); else root.removeAttribute('data-glass');
    };
    // A troca reavalia a cor de quase todo elemento; sem suprimir as
    // transições a página engasga. Quem anima é o View Transition (cross-fade).
    if (!animate) { go(); return; }
    root.classList.add('otc-theme-switching');
    var done = function () { setTimeout(function () { root.classList.remove('otc-theme-switching'); }, 60); };
    if (doc.startViewTransition && !REDUCED_MOTION) {
      var vt = doc.startViewTransition(go);
      vt.finished.then(done, done);
    } else { go(); done(); }
  }
  var otcUI = {
    get: readPrefs,
    set: function (patch, animate) {
      var p = readPrefs();
      for (var k in patch) if (Object.prototype.hasOwnProperty.call(patch, k)) p[k] = patch[k];
      writePrefs(p);
      applyPrefs(p, animate !== false);
      syncAppearance();
      try { window.dispatchEvent(new CustomEvent('otc:appearance', { detail: p })); } catch (e) {}
      return p;
    },
    fx: function (v) {
      if (v === undefined) { try { return localStorage.getItem(FX_KEY) || 'auto'; } catch (e) { return 'auto'; } }
      try { if (v === 'auto') localStorage.removeItem(FX_KEY); else localStorage.setItem(FX_KEY, v); } catch (e) {}
      decideSolid();
      syncAppearance();
    }
  };
  window.otcUI = otcUI;
  if (mqDark && mqDark.addEventListener) {
    mqDark.addEventListener('change', function () { if (readPrefs().theme === 'auto') applyPrefs(readPrefs(), true); });
  }

  // Modo OPACO: a máquina SEM GPU não paga o vidro. Nas máquinas do JPM o
  // navegador roda com a aceleração desligada, e ~80 backdrop-filter
  // recompositando por software deixam a tela inteira lenta SEM erro nenhum.
  // Sinais, na ordem: preferência gravada ('full' | 'reduced'), WebGL por
  // software ou ausente, Firefox no Windows (o par da mesa). O falso positivo
  // custa estética; o falso negativo, a mesa inteira lenta.
  function softwareGl() {
    try {
      var c = doc.createElement('canvas');
      var gl = c.getContext('webgl') || c.getContext('experimental-webgl');
      if (!gl) return true;
      var ext = gl.getExtension('WEBGL_debug_renderer_info');
      var r = ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
      return /swiftshader|llvmpipe|software|basic render/i.test(String(r || ''));
    } catch (e) { return true; }
  }
  function decideSolid() {
    var pref = String(otcUI.fx() || 'auto').toLowerCase();
    var ua = navigator.userAgent || '';
    var fxWin = /Windows/.test(ua) && /Firefox\//.test(ua);
    var solid;
    if (pref === 'reduced') solid = true;
    else if (pref === 'full') solid = false;
    else {
      // a sonda de WebGL custa: memoizada por sessão (o <head> lê a mesma
      // chave para não piscar vidro na página seguinte)
      var cached = null;
      try { cached = sessionStorage.getItem('__OTC_FX_AUTO__'); } catch (e) {}
      if (cached === null) {
        cached = (fxWin || softwareGl()) ? '1' : '0';
        try { sessionStorage.setItem('__OTC_FX_AUTO__', cached); } catch (e) {}
      }
      solid = cached === '1';
    }
    root.classList.toggle('is-solid', solid);
    return solid;
  }
  decideSolid();

  // ==========================================================================
  // 2. Idioma — o I18nManager de sempre (mesma API, mesmas chaves)
  // ==========================================================================
  function I18nManager() {
    this.selectedLanguage = lang();
    this.langPath = '/static/data/translations/';
    this._cache = {};
  }
  I18nManager.prototype.init = function () {
    var self = this;
    return this.applyTranslations().then(function () {
      self.updateSelected();
      self.bindLanguageSwitchers();
    });
  };
  I18nManager.prototype.loadTranslations = function () {
    var l = this.selectedLanguage, self = this;
    if (this._cache[l]) return Promise.resolve(this._cache[l]);
    return fetch(this.langPath + l + '.json')
      .then(function (r) { if (!r.ok) throw new Error('Failed to load ' + l + '.json'); return r.json(); })
      .then(function (j) { self._cache[l] = j; return j; })
      .catch(function (err) { console.error('Translation load error:', err); return {}; });
  };
  I18nManager.prototype.applyTranslations = function () {
    return this.loadTranslations().then(function (tr) {
      var get = function (obj, path) {
        return path.split('.').reduce(function (acc, k) { return acc && acc[k] != null ? acc[k] : null; }, obj);
      };
      $$('[data-lang]').forEach(function (el) {
        var v = get(tr, el.getAttribute('data-lang'));
        if (!v) return;
        // DataTables 2 embrulha o <th> em .dt-column-title + .dt-column-order:
        // escrever no <th> apagaria os dois, e o export de Excel morreria no
        // `.length` do título nulo. Traduz DENTRO do span.
        var alvo = el.querySelector('.dt-column-title') || el;
        alvo.innerHTML = v;
      });
      $$('[data-lang-placeholder]').forEach(function (el) {
        var v = get(tr, el.getAttribute('data-lang-placeholder'));
        if (v) el.setAttribute('placeholder', v);
      });
      requestAnimationFrame(function () {
        requestAnimationFrame(function () {
          if (window.jQuery && jQuery.fn.dataTable) jQuery.fn.dataTable.tables({ visible: true, api: true }).columns.adjust();
        });
      });
    });
  };
  I18nManager.prototype.setLanguage = function (l) {
    this.selectedLanguage = l;
    try { localStorage.setItem('__OTC_TRACKER_LANG__', l); } catch (e) {}
    var self = this;
    return this.applyTranslations().then(function () {
      self.updateSelected();
      try { window.dispatchEvent(new CustomEvent('otc:language-changed', { detail: l })); } catch (e) {}
    });
  };
  I18nManager.prototype.updateSelected = function () {
    var l = this.selectedLanguage;
    var img = doc.querySelector('[data-translator-lang="' + l + '"] [data-translator-image]');
    var sel = doc.getElementById('selected-language-image');
    if (img && sel) sel.src = img.src;
    $$('[data-translator-lang]').forEach(function (a) { a.classList.toggle('active', a.getAttribute('data-translator-lang') === l); });
    var code = doc.getElementById('selected-language-code');
    if (code) code.textContent = l.toUpperCase();
  };
  I18nManager.prototype.bindLanguageSwitchers = function () {
    var self = this;
    $$('[data-translator-lang]').forEach(function (b) {
      b.addEventListener('click', function () {
        var l = b.getAttribute('data-translator-lang');
        if (l && l !== self.selectedLanguage) self.setLanguage(l);
      });
    });
  };
  window.I18nManager = I18nManager;

  // ==========================================================================
  // 3. Menu lateral: drill-down, lente, atalhos fixados, gaveta
  // ==========================================================================
  var INDEX_PATHS = ['/dashboard', '/'];
  var Nav = { tree: null, open: [], active: null, allowed: null };

  function navSource() { return doc.querySelector('.sidenav-menu .side-nav:not(.dd-panel)'); }

  function parseLevel(ul, parent) {
    var out = [];
    Array.prototype.forEach.call(ul.children, function (li) {
      if (li.hidden) return;
      if (li.classList.contains('side-nav-title')) { out.push({ kind: 'title', li: li }); return; }
      if (!li.classList.contains('side-nav-item')) return;
      var a = li.querySelector(':scope > a');
      if (!a) return;
      var sub = li.querySelector(':scope > .collapse > ul.sub-menu, :scope > ul.sub-menu, :scope > .collapse > .sub-menu');
      var node = {
        li: li, a: a, parent: parent || null,
        href: (a.getAttribute('href') || '').split(/[?#]/)[0].replace(/\/+$/, ''),
        textEl: a.querySelector(':scope > .menu-text')
      };
      if (sub) { node.kind = 'branch'; node.children = parseLevel(sub, node); if (!node.children.some(function (c) { return c.kind !== 'title'; })) return; }
      else node.kind = 'leaf';
      out.push(node);
    });
    // título sem item visível até o próximo título some junto
    return out.filter(function (n, i) {
      if (n.kind !== 'title') return true;
      var nx = out[i + 1];
      return nx && nx.kind !== 'title';
    });
  }
  function labelOf(n) { return n.textEl ? n.textEl.textContent.trim() : (n.a ? n.a.textContent.trim() : ''); }
  function langOf(n) { return n.textEl ? n.textEl.getAttribute('data-lang') : null; }
  function curPath() { return (window.location.pathname || '/').replace(/\/+$/, '') || '/'; }
  function findActive(nodes, p) {
    p = p || curPath();
    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      if (n.kind === 'leaf' && n.href && n.href === p) return n;
      if (n.kind === 'branch') { var f = findActive(n.children, p); if (f) return f; }
    }
    // Subpágina fora do menu (`/projects/PRJ-0001`): acende o item-pai do
    // caminho (`/projects`), subindo um segmento por vez.
    if (p === curPath()) {
      var up = p;
      while ((up = up.replace(/\/[^\/]*$/, '')) && up !== '') {
        var g = findActive(nodes, up);
        if (g) return g;
      }
    }
    return null;
  }
  function leadsTo(branch) {
    var p = Nav.active && Nav.active.parent;
    while (p) { if (p === branch) return true; p = p.parent; }
    return false;
  }
  function levelNodes() { return Nav.open.length ? Nav.open[Nav.open.length - 1].children : Nav.tree; }

  function buildNav() {
    var src = navSource();
    if (!src) return;
    src.classList.add('dd-source-hidden');
    Nav.tree = parseLevel(src, null);
    Nav.active = findActive(Nav.tree);
    Nav.open = [];
    if (Nav.active && INDEX_PATHS.indexOf(curPath()) === -1) {
      var p = Nav.active.parent;
      while (p) { Nav.open.unshift(p); p = p.parent; }
    }
    var host = doc.querySelector('.sidenav-menu .dd-nav');
    if (!host) {
      host = doc.createElement('div');
      host.className = 'dd-nav';
      host.innerHTML = '<div class="dd-crumbs"></div><div class="dd-stage"></div>';
      src.parentNode.insertBefore(host, src.nextSibling);
    }
    Nav.crumbs = host.querySelector('.dd-crumbs');
    Nav.stage = host.querySelector('.dd-stage');
    Nav.stage.innerHTML = '';
    var ul = doc.createElement('ul');
    ul.className = 'side-nav dd-panel dd-current';
    fillPanel(ul);
    Nav.stage.appendChild(ul);
    renderCrumbs();
    icons();
    placeLens(ul, false);
  }

  function fillPanel(ul) {
    ul.innerHTML = '';
    if (Nav.open.length) {
      var parent = Nav.open[Nav.open.length - 1];
      var back = doc.createElement('li');
      back.className = 'side-nav-item dd-back';
      back.innerHTML = '<a href="javascript:void(0)" class="side-nav-link dd-back-link">' +
        '<span class="menu-icon dd-back-icon"><i data-lucide="chevron-left"></i></span>' +
        '<span class="menu-text"' + (langOf(parent) ? ' data-lang="' + esc(langOf(parent)) + '"' : '') + '>' + esc(labelOf(parent)) + '</span></a>';
      back.firstChild.addEventListener('click', function (e) { e.preventDefault(); goTo(Nav.open.length - 2); });
      ul.appendChild(back);
    }
    levelNodes().forEach(function (node) {
      if (node.kind === 'title') { ul.appendChild(node.li.cloneNode(true)); return; }
      var li = node.li.cloneNode(true);
      $$('.collapse, .collapsing, ul.sub-menu', li).forEach(function (n) { n.remove(); });
      if (Nav.open.length) { var mi = li.querySelector('.menu-icon'); if (mi) mi.remove(); }
      var a = li.querySelector(':scope > a');
      a.classList.remove('active');
      if (node.kind === 'branch') {
        a.removeAttribute('data-bs-toggle');
        a.removeAttribute('aria-controls');
        a.setAttribute('href', 'javascript:void(0)');
        a.classList.add('dd-branch');
        if (leadsTo(node)) a.classList.add('active');
        a.addEventListener('click', function (e) { e.preventDefault(); drill(node); });
      } else {
        a.classList.add('dd-leaf');
        if (node === Nav.active) a.classList.add('active');
        // a lente desliza até o item clicado enquanto a página seguinte carrega
        a.addEventListener('click', function () { moveLensTo(ul, a); });
      }
      ul.appendChild(li);
    });
    if (!REDUCED_MOTION) {
      $$(':scope > li', ul).forEach(function (li, i) { li.style.setProperty('--dd-delay', Math.min(i, 9) * 24 + 'ms'); });
    }
  }

  function renderCrumbs() {
    var c = Nav.crumbs;
    c.innerHTML = '';
    var trail = [{ label: t('menu'), lang: null, index: -1 }];
    Nav.open.slice(0, -1).forEach(function (n, i) { trail.push({ label: labelOf(n), lang: langOf(n), index: i }); });
    trail.forEach(function (cr, i) {
      var b = doc.createElement('button');
      b.type = 'button';
      b.className = 'dd-crumb';
      b.innerHTML = cr.lang ? '<span data-lang="' + esc(cr.lang) + '">' + esc(cr.label) + '</span>' : esc(cr.label);
      b.addEventListener('click', function () { goTo(cr.index); });
      c.appendChild(b);
      if (i < trail.length - 1) {
        var s = doc.createElement('span');
        s.className = 'dd-crumb-sep';
        s.innerHTML = '<i data-lucide="chevron-right"></i>';
        c.appendChild(s);
      }
    });
    c.classList.toggle('dd-at-root', Nav.open.length === 0);
  }

  function slide(dir) {
    var out = Nav.stage.querySelector('.dd-panel.dd-current');
    var inc = doc.createElement('ul');
    inc.className = 'side-nav dd-panel';
    fillPanel(inc);
    renderCrumbs();
    if (REDUCED_MOTION || !out) {
      if (out) out.remove();
      inc.classList.add('dd-current');
      Nav.stage.appendChild(inc);
      icons();
      placeLens(inc, false);
      return;
    }
    Nav.stage.style.minHeight = Nav.stage.offsetHeight + 'px';
    out.style.position = 'absolute';
    out.style.top = '0'; out.style.left = '0'; out.style.right = '0';
    out.classList.remove('dd-current');
    inc.classList.add(dir > 0 ? 'dd-enter-right' : 'dd-enter-left', 'dd-stagger');
    Nav.stage.appendChild(inc);
    icons();
    placeLens(inc, false);
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        inc.classList.remove('dd-enter-right', 'dd-enter-left');
        inc.classList.add('dd-current');
        out.classList.add(dir > 0 ? 'dd-exit-left' : 'dd-exit-right');
      });
    });
    var done = false;
    function clean() { if (done) return; done = true; out.remove(); Nav.stage.style.minHeight = ''; }
    out.addEventListener('transitionend', clean, { once: true });
    setTimeout(clean, 400);
    if (window.otcI18n) window.otcI18n.applyTranslations();
  }
  function drill(node) { Nav.open.push(node); slide(1); }
  function goTo(i) { Nav.open = i < 0 ? [] : Nav.open.slice(0, i + 1); slide(-1); }

  // ── A LENTE de gel ────────────────────────────────────────────────────────
  // Posição por mola; no caminho ela ESTICA no eixo do movimento e, ao
  // chegar, achata e balança. Pré-calculado em quadros-chave (WAAPI), só
  // `transform` — nada de layout.
  function lensFor(container) {
    var l = container.querySelector(':scope > .otc-lens');
    if (!l) {
      l = doc.createElement(container.tagName === 'UL' ? 'li' : 'span');
      l.className = 'otc-lens';
      l.setAttribute('role', 'presentation');
      l.setAttribute('aria-hidden', 'true');
      container.insertBefore(l, container.firstChild);
    }
    return l;
  }
  // Posição pelo LAYOUT (offset*), nunca pelo getBoundingClientRect: o item
  // ainda está entrando (o `translate` da animação de entrada, o slide do
  // drill-down) quando a lente é posicionada, e a caixa visual daria a lente
  // deslocada do texto para sempre. O container é posicionado (CSS).
  function rectIn(container, el) {
    var x = 0, y = 0, n = el;
    while (n && n !== container) { x += n.offsetLeft; y += n.offsetTop; n = n.offsetParent; }
    if (n !== container) {                                // fora da cadeia: cai para a caixa visual
      var c = container.getBoundingClientRect(), r = el.getBoundingClientRect();
      return { x: r.left - c.left, y: r.top - c.top, w: r.width, h: r.height };
    }
    return { x: x, y: y, w: el.offsetWidth, h: el.offsetHeight };
  }
  function setLensBox(l, b) {
    l.style.width = b.w + 'px';
    l.style.height = b.h + 'px';
    l.style.transform = 'translate(' + b.x + 'px,' + b.y + 'px)';
    l.dataset.x = b.x; l.dataset.y = b.y; l.dataset.w = b.w; l.dataset.h = b.h;
  }
  function animateLens(l, from, to) {
    if (REDUCED_MOTION || !l.animate) { setLensBox(l, to); return; }
    var dx = to.x - from.x, dy = to.y - from.y;
    var vert = Math.abs(dy) >= Math.abs(dx);
    var dist = Math.abs(vert ? dy : dx);
    var size = vert ? to.h : to.w;
    var k = Math.min(.5, .08 + dist / (size * 6));        // esticão proporcional ao salto
    var sa = 1 + k, sc = 1 / Math.sqrt(sa);
    var st = function (a, c) { return vert ? 'scale(' + c + ',' + a + ')' : 'scale(' + a + ',' + c + ')'; };
    var tr = function (x, y) { return 'translate(' + x + 'px,' + y + 'px) '; };
    var ox = vert ? 0 : Math.sign(dx) * 2.5, oy = vert ? Math.sign(dy) * 2 : 0;
    l.style.width = to.w + 'px';
    l.style.height = to.h + 'px';
    var anim = l.animate([
      { transform: tr(from.x, from.y) + 'scale(1,1)', offset: 0 },
      { transform: tr(from.x + dx * .42, from.y + dy * .42) + st(sa, sc), offset: .22 },
      { transform: tr(to.x + ox, to.y + oy) + st(.92, 1.06), offset: .52 },
      { transform: tr(to.x, to.y) + st(1.012, .988), offset: .7 },
      { transform: tr(to.x, to.y) + st(.996, 1.004), offset: .86 },
      { transform: tr(to.x, to.y) + 'scale(1,1)', offset: 1 }
    ], { duration: 720, easing: 'cubic-bezier(.3,.7,.3,1)' });
    setLensBox(l, to);
    return anim;
  }
  function placeLens(ul, animate) {
    var a = ul.querySelector(':scope > li > a.active');
    var l = ul.querySelector(':scope > .otc-lens');
    if (!a) { if (l) l.style.opacity = '0'; return; }
    l = lensFor(ul);
    l.style.opacity = '1';
    l.style.borderRadius = '22px';
    var b = rectIn(ul, a);
    if (animate && l.dataset.w) animateLens(l, { x: +l.dataset.x, y: +l.dataset.y, w: +l.dataset.w, h: +l.dataset.h }, b);
    else setLensBox(l, b);
  }
  function moveLensTo(ul, a) {
    var l = ul.querySelector(':scope > .otc-lens');
    $$(':scope > li > a.active', ul).forEach(function (x) { x.classList.remove('active'); });
    a.classList.add('active');
    if (!l || !l.dataset.w) { placeLens(ul, false); return; }
    animateLens(l, { x: +l.dataset.x, y: +l.dataset.y, w: +l.dataset.w, h: +l.dataset.h }, rectIn(ul, a));
  }

  // ── Acesso por usuário: o menu mostra só o que a pessoa alcança ──────────
  // (o script do sidenav.html marca os <li hidden>; aqui o drill-down é
  // remontado depois dele, e os atalhos/paleta usam a mesma lista)
  function accessThen(fn) {
    var p = window.otcMeAccess ? window.otcMeAccess() : fetch('/api/me/access', { credentials: 'same-origin' }).then(function (r) { return r.json(); });
    p.then(function (d) {
      if (d && d.success && !d.is_admin && d.configured) {
        var allowed = {};
        (d.pages || []).forEach(function (u) { allowed[u] = 1; });
        if (allowed['/']) allowed['/dashboard'] = 1;
        for (var k in allowed) { if (k.indexOf('/control-panel#') === 0) { allowed['/control-panel'] = 1; break; } }
        Nav.allowed = allowed;
      }
      fn();
    }).catch(function () { fn(); });
  }

  // ── Projetos fixados (a seção "Pinned"), por usuário ─────────────────────
  // Só PROJETOS — a estrela do card e da página do projeto fixa aqui. As
  // páginas fixadas saíram (pedido de 19/10/2026): o menu já as alcança, e a
  // lista de páginas não ficava bem no desenho. Mora no navegador (chave por
  // SID) com o nome e a cor de cada um, e a lista e a página do projeto a
  // ATUALIZAM ao carregar (`otcPins.sync`): renomeado se corrige, apagado sai.
  var PIN_COLORS = ['blue', 'purple', 'pink', 'orange', 'green', 'teal', 'indigo', 'yellow'];
  function pinKey() {
    var box = doc.querySelector('.otc-pinned[data-sid]');
    var sid = box ? (box.getAttribute('data-sid') || '').trim().toUpperCase() : '';
    return 'otc_pinned_projects_' + (sid || 'anon');
  }
  function leaves() {
    var out = [];
    (function walk(nodes, trail) {
      nodes.forEach(function (n) {
        if (n.kind === 'leaf' && n.href && n.href.charAt(0) === '/') {
          out.push({ href: n.href, label: labelOf(n), lang: langOf(n), trail: trail.slice(), node: n });
        } else if (n.kind === 'branch') walk(n.children, trail.concat([labelOf(n)]));
      });
    })(Nav.tree || [], []);
    var seen = {};
    return out.filter(function (o) { if (seen[o.href]) return false; seen[o.href] = 1; return true; });
  }
  function isAllowed(h) { return !Nav.allowed || Nav.allowed[h] === 1; }
  function pinList() {
    try {
      var v = JSON.parse(localStorage.getItem(pinKey()) || '[]');
      if (Array.isArray(v)) return v.filter(function (o) { return o && o.id; });
    } catch (e) {}
    return [];
  }
  function pinSave(list) {
    try { localStorage.setItem(pinKey(), JSON.stringify(list)); } catch (e) {}
    renderPinned();
  }
  function pinEntry(p) {
    return { id: String(p.id), name: String(p.name || p.id), color: PIN_COLORS.indexOf(p.color) !== -1 ? p.color : 'blue' };
  }
  function renderPinned() {
    var box = doc.querySelector('.otc-pinned');
    if (!box) return;
    var list = pinList();
    var label = doc.querySelector('[data-otc-pinned-label]');
    if (label) label.style.display = list.length ? '' : 'none';
    box.style.display = list.length ? '' : 'none';
    var p = curPath();
    box.innerHTML = list.map(function (o) {
      var h = '/projects/' + encodeURIComponent(o.id);
      var c = PIN_COLORS.indexOf(o.color) !== -1 ? o.color : 'blue';
      return '<a href="' + esc(h) + '" style="--pin-hue:var(--otc-' + c + ')"' + (p === h ? ' class="is-active"' : '') + '><span>' + esc(o.name) + '</span></a>';
    }).join('');
  }
  window.otcPins = {
    has: function (id) { return pinList().some(function (o) { return o.id === String(id); }); },
    // fixa ou solta; devolve o estado NOVO (true = fixado)
    toggle: function (p) {
      var list = pinList(), id = String(p.id), i = -1;
      list.forEach(function (o, k) { if (o.id === id) i = k; });
      if (i !== -1) list.splice(i, 1); else list.push(pinEntry(p));
      pinSave(list);
      return i === -1;
    },
    // `projects` = os que a tela acabou de ler; `complete` = é a lista INTEIRA
    // (a página Projects), e aí o fixado que não veio é projeto apagado.
    sync: function (projects, complete) {
      var by = {};
      (projects || []).forEach(function (p) { by[String(p.id)] = p; });
      var list = pinList(), out = [];
      list.forEach(function (o) {
        if (by[o.id]) out.push(pinEntry(by[o.id]));
        else if (!complete) out.push(o);
      });
      if (JSON.stringify(out) !== JSON.stringify(list)) pinSave(out);
    }
  };

  // ── Gaveta: fixado (padrão) ou sobre o conteúdo ──────────────────────────
  var PIN_NAV_KEY = 'otc_nav_pinned';
  function initDrawer() {
    var body = doc.body;
    var bd = doc.createElement('div');
    bd.className = 'otc-nav-backdrop';
    body.appendChild(bd);
    var unpinned = false;
    try { unpinned = localStorage.getItem(PIN_NAV_KEY) === '0'; } catch (e) {}
    body.classList.toggle('otc-nav-unpinned', unpinned);
    var pinState = function () {
      $$('[data-otc-pin]').forEach(function (b) { b.setAttribute('aria-pressed', body.classList.contains('otc-nav-unpinned') ? 'false' : 'true'); });
    };
    pinState();
    var close = function () { body.classList.remove('otc-nav-open'); };
    $$('[data-otc-menu]').forEach(function (b) { b.addEventListener('click', function () { body.classList.toggle('otc-nav-open'); }); });
    $$('[data-otc-pin]').forEach(function (b) {
      b.addEventListener('click', function () {
        var now = !body.classList.contains('otc-nav-unpinned');
        body.classList.toggle('otc-nav-unpinned', now);
        body.classList.remove('otc-nav-open');
        pinState();
        try { localStorage.setItem(PIN_NAV_KEY, now ? '0' : '1'); } catch (e) {}
      });
    });
    bd.addEventListener('click', close);
    doc.addEventListener('keydown', function (e) { if (e.key === 'Escape') close(); });
    var side = doc.querySelector('.sidenav-menu');
    if (side) side.addEventListener('click', function (e) {
      var a = e.target.closest('a[href]');
      var h = a && a.getAttribute('href');
      if (h && h !== '#' && h.indexOf('javascript:') !== 0) close();
    });
  }

  // ==========================================================================
  // 3b. <select>: as opções abrem ABAIXO do campo, na largura dele
  // ==========================================================================
  // O popup nativo do macOS abre POR CIMA do campo (centrado na opção marcada)
  // e o do Windows abre embaixo: a mesma tela mudava de máquina para máquina
  // (pedido de 20/10/2026). O clique num <select> simples abre um menu do tema
  // logo abaixo, na mesma largura. O <select> de verdade continua no lugar: o
  // valor vai para ele e ele dispara o `input`/`change` de sempre — nenhuma
  // tela precisa saber disto. Ficam no nativo: `multiple`/`size`, desabilitado,
  // toque, os selects dos calendários (flatpickr, daterangepicker) e o que
  // estiver dentro de um dropdown, ou marcado `data-native`.
  var SM = null;
  var SM_SKIP = '.flatpickr-calendar, .daterangepicker, .dropdown-menu, [data-native]';
  function smUsable(sel) {
    return sel && !sel.multiple && !(sel.size > 1) && !sel.disabled && !sel.closest(SM_SKIP);
  }
  function smClose() {
    if (!SM) return;
    SM.m.remove();
    SM = null;
  }
  function smPick(i) {
    var sel = SM && SM.sel;
    if (!sel) return;
    smClose();
    if (sel.selectedIndex !== i) {
      sel.selectedIndex = i;
      sel.dispatchEvent(new Event('input', { bubbles: true }));
      sel.dispatchEvent(new Event('change', { bubbles: true }));
    }
    sel.focus();
  }
  function smMark(k) {
    if (!SM) return;
    var items = $$('.dropdown-item:not([disabled])', SM.m);
    if (!items.length) return;
    SM.k = (k + items.length) % items.length;
    items.forEach(function (b, i) { b.classList.toggle('is-kbd', i === SM.k); });
    items[SM.k].scrollIntoView({ block: 'nearest' });
  }
  function smOpen(sel) {
    smClose();
    var html = '';
    var add = function (o) {
      if (o.hidden) return;
      html += '<button type="button" class="dropdown-item' + (o.selected ? ' active' : '') + '"' +
        (o.disabled ? ' disabled' : '') + ' data-i="' + o.index + '" role="option">' + esc(o.text) + '</button>';
    };
    Array.prototype.forEach.call(sel.children, function (n) {
      if (n.tagName === 'OPTGROUP') {
        html += '<h6 class="dropdown-header">' + esc(n.label) + '</h6>';
        Array.prototype.forEach.call(n.children, add);
      } else if (n.tagName === 'OPTION') add(n);
    });
    if (!html) return;
    var m = doc.createElement('div');
    m.className = 'dropdown-menu show otc-select-menu';
    m.setAttribute('role', 'listbox');
    m.innerHTML = html;
    // dentro de modal/SweetAlert o menu nasce DENTRO da janela: no <body>, o
    // clique nele seria um clique fora e fecharia a janela
    (sel.closest('.modal, .swal2-container') || doc.body).appendChild(m);
    var r = sel.getBoundingClientRect();
    var below = window.innerHeight - r.bottom - 12;
    m.style.left = r.left + 'px';
    m.style.top = (r.bottom + 4) + 'px';
    m.style.width = r.width + 'px';
    m.style.minWidth = r.width + 'px';
    m.style.maxHeight = Math.max(160, Math.min(320, below)) + 'px';
    SM = { sel: sel, m: m, k: -1 };
    var act = m.querySelector('.active');
    if (act) act.scrollIntoView({ block: 'nearest' });
    m.addEventListener('mousedown', function (e) { e.preventDefault(); });   // o foco fica no <select>
    m.addEventListener('click', function (e) {
      var b = e.target.closest('.dropdown-item');
      if (b && !b.disabled) smPick(+b.getAttribute('data-i'));
    });
  }
  function initSelectMenus() {
    doc.addEventListener('mousedown', function (e) {
      if (SM && SM.m.contains(e.target)) return;
      var sel = e.target.closest && e.target.closest('select');
      if (e.button !== 0 || !smUsable(sel)) { smClose(); return; }
      e.preventDefault();
      if (SM && SM.sel === sel) { smClose(); sel.focus(); return; }
      sel.focus();
      smOpen(sel);
    }, true);
    doc.addEventListener('touchstart', function () { smClose(); }, { passive: true, capture: true });
    doc.addEventListener('keydown', function (e) {
      var sel = e.target.closest && e.target.closest('select');
      if (SM) {
        if (e.key === 'Escape' || e.key === 'Tab') { smClose(); if (e.key === 'Escape') e.preventDefault(); return; }
        if (e.key === 'ArrowDown') { e.preventDefault(); smMark(SM.k + 1); return; }
        if (e.key === 'ArrowUp') { e.preventDefault(); smMark(SM.k - 1); return; }
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          var items = $$('.dropdown-item:not([disabled])', SM.m);
          if (items[SM.k]) smPick(+items[SM.k].getAttribute('data-i')); else smClose();
          return;
        }
        return;
      }
      // no Mac, espaço e setas abrem o popup nativo: abre o nosso no lugar
      if (smUsable(sel) && (e.key === ' ' || e.key === 'ArrowDown' || e.key === 'ArrowUp') && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        smOpen(sel);
      }
    }, true);
    window.addEventListener('scroll', function (e) { if (SM && !SM.m.contains(e.target)) smClose(); }, true);
    window.addEventListener('resize', smClose);
    window.addEventListener('blur', smClose);
  }

  // ==========================================================================
  // 3c. Vidro com REFRAÇÃO nas placas grandes (o "liquid glass" do Pane)
  // ==========================================================================
  // O desfoque comum (12px + brilho) deixava o vidro claro leitoso: o papel de
  // parede sumia atrás das placas. Aqui cada placa grande ganha um filtro SVG
  // próprio — um mapa de deslocamento desenhado num canvas a partir do retângulo
  // arredondado dela (a faixa da borda puxa o fundo para dentro, como lente),
  // desfoque de 5,5px e saturação 1,7 — aplicado como `backdrop-filter:
  // url(#…)`. O fundo aparece através da placa e entorta nas bordas. Só no
  // Chromium (Chrome/Edge: é onde `backdrop-filter: url()` existe); no modo
  // opaco e nos outros navegadores fica o desfoque do tema (pedido 20/10/2026).
  var LG = { n: 0, svg: null, ro: null, on: false };
  var LG_SEL = '.sidenav-menu, .otc-toolbar, .content-page .card:not(.card .card), .content-page div[class*="-panel"]:not([class*="__"]):not(.tab-pane)';
  var LG_MAX = 28;
  function lgSupported() {
    var ua = navigator.userAgent || '';
    return /Chrome\//.test(ua) && !/Firefox\//.test(ua);
  }
  function lgMap(w, h, r, pad, bezel) {
    var W = w + 2 * pad, H = h + 2 * pad;
    var k = Math.min(1, 320 / Math.max(W, H));          // o feImage estica o mapa: meia resolução basta
    var cw = Math.max(8, Math.round(W * k)), ch = Math.max(8, Math.round(H * k));
    var c = doc.createElement('canvas');
    c.width = cw; c.height = ch;
    var ctx = c.getContext('2d');
    var img = ctx.createImageData(cw, ch), d = img.data;
    var hw = w / 2, hh = h / 2, rr = Math.min(r, hw, hh);
    for (var j = 0; j < ch; j++) {
      for (var i = 0; i < cw; i++) {
        var x = i / k - pad - hw, y = j / k - pad - hh;
        var qx = Math.abs(x) - (hw - rr), qy = Math.abs(y) - (hh - rr);
        var ox = Math.max(qx, 0), oy = Math.max(qy, 0);
        var dist = Math.sqrt(ox * ox + oy * oy) + Math.min(Math.max(qx, qy), 0) - rr;   // < 0 dentro
        var nx = 0, ny = 0, m = 0;
        if (dist < 0 && -dist < bezel) {
          if (qx > 0 && qy > 0) { var L = Math.sqrt(ox * ox + oy * oy) || 1; nx = ox / L; ny = oy / L; }
          else if (qx > qy) nx = 1;
          else ny = 1;
          if (x < 0) nx = -nx;
          if (y < 0) ny = -ny;
          var t = 1 + dist / bezel;                         // 0 no começo da faixa, 1 na borda
          m = t * t;
        }
        var p = (j * cw + i) * 4;
        d[p] = 128 - nx * m * 127;                          // amostra para DENTRO: lente
        d[p + 1] = 128 - ny * m * 127;
        d[p + 2] = 128;
        d[p + 3] = 255;
      }
    }
    ctx.putImageData(img, 0, 0);
    return c.toDataURL();
  }
  function lgApply(el) {
    var r = el.getBoundingClientRect();
    var w = Math.round(r.width), h = Math.round(r.height);
    if (w < 120 || h < 44) return;
    var key = w + 'x' + h;
    if (el.__lgKey === key && el.style.backdropFilter) return;
    el.__lgKey = key;
    var rad = parseFloat(getComputedStyle(el).borderTopLeftRadius) || 24;
    var id = el.__lgId || (el.__lgId = 'otc-lg-' + (++LG.n));
    var pad = 24, bezel = Math.max(10, Math.min(28, Math.min(w, h) / 4));
    var url = lgMap(w, h, rad, pad, bezel);
    var f = doc.getElementById(id);
    if (!f) {
      f = doc.createElementNS('http://www.w3.org/2000/svg', 'filter');
      f.setAttribute('id', id);
      f.setAttribute('filterUnits', 'userSpaceOnUse');
      f.setAttribute('color-interpolation-filters', 'sRGB');
      LG.svg.appendChild(f);
    }
    f.setAttribute('x', -pad); f.setAttribute('y', -pad);
    f.setAttribute('width', w + 2 * pad); f.setAttribute('height', h + 2 * pad);
    f.innerHTML =
      '<feImage result="map" preserveAspectRatio="none" x="' + (-pad) + '" y="' + (-pad) + '" width="' + (w + 2 * pad) + '" height="' + (h + 2 * pad) + '" href="' + url + '"/>' +
      '<feDisplacementMap in="SourceGraphic" in2="map" scale="48" xChannelSelector="R" yChannelSelector="G" result="bent"/>' +
      '<feGaussianBlur in="bent" stdDeviation="5.5" result="frost"/>' +
      '<feColorMatrix in="frost" type="saturate" values="1.7"/>';
    el.style.setProperty('-webkit-backdrop-filter', 'url(#' + id + ')');
    el.style.setProperty('backdrop-filter', 'url(#' + id + ')');
    if (LG.ro) LG.ro.observe(el);
  }
  function lgClear() {
    $$('[style*="backdrop-filter"]').forEach(function (el) {
      if (!el.__lgId) return;
      el.style.removeProperty('backdrop-filter');
      el.style.removeProperty('-webkit-backdrop-filter');
      el.__lgKey = null;
    });
  }
  function lgScan() {
    if (!LG.on || root.classList.contains('is-solid')) { lgClear(); return; }
    var els = $$(LG_SEL).filter(function (el) {
      return el.getClientRects().length > 0 && !el.closest('.modal, .offcanvas, .dropdown-menu');   // fixed: offsetParent é nulo
    });
    els.sort(function (a, b) {
      var ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
      return rb.width * rb.height - ra.width * ra.height;
    });
    els.slice(0, LG_MAX).forEach(lgApply);
  }
  function initLiquidGlass() {
    if (!lgSupported()) return;
    LG.on = true;
    LG.svg = doc.createElementNS('http://www.w3.org/2000/svg', 'svg');
    LG.svg.setAttribute('aria-hidden', 'true');
    LG.svg.setAttribute('width', '0'); LG.svg.setAttribute('height', '0');
    LG.svg.style.cssText = 'position:absolute;width:0;height:0;overflow:hidden;pointer-events:none';
    doc.body.appendChild(LG.svg);
    var again = window.debounce ? window.debounce(lgScan, 180) : lgScan;
    if (window.ResizeObserver) LG.ro = new ResizeObserver(function (ents) {
      ents.forEach(function (en) { if (en.target.__lgId) en.target.__lgKey = null; });
      again();
    });
    // placas que a tela monta depois do load, e o modo opaco ligado/desligado
    var page = doc.querySelector('.content-page');
    if (page && window.MutationObserver) new MutationObserver(again).observe(page, { childList: true, subtree: true });
    new MutationObserver(again).observe(root, { attributes: true, attributeFilter: ['class'] });
    setTimeout(lgScan, 60);
  }

  // ==========================================================================
  // 3d. O aviso de AÇÃO (o do Pane): pílula preta, círculo verde com o check,
  // o texto e o "Undo" — logo abaixo da barra do topo. Para o que a pessoa
  // acabou de fazer (o card movido, a tarefa concluída): `otcToast('Done: X',
  // { undo: fn })`. Some sozinho em 5s; o Undo chama `fn` e fecha.
  // ==========================================================================
  var TOAST_T = { en: 'Undo', br: 'Desfazer', es: 'Deshacer' };
  function otcToast(msg, opts) {
    opts = opts || {};
    var old = doc.querySelector('.otc-toast');
    if (old) old.remove();
    var el = doc.createElement('div');
    el.className = 'otc-toast' + (opts.error ? ' is-error' : '');
    el.setAttribute('role', 'status');
    var lang = 'en';
    try { lang = localStorage.getItem('__OTC_TRACKER_LANG__') || 'en'; } catch (e) {}
    el.innerHTML = '<span class="otc-toast__ico">' + (opts.error
        ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"><path d="M7 7l10 10M17 7L7 17"/></svg>'
        : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>') +
      '</span><span class="otc-toast__msg"></span>' +
      (opts.undo ? '<button type="button" class="otc-toast__undo">' + esc(opts.undoLabel || TOAST_T[lang] || 'Undo') + '</button>' : '');
    el.querySelector('.otc-toast__msg').textContent = String(msg == null ? '' : msg);
    doc.body.appendChild(el);
    var fecha = function () {
      el.classList.add('is-leaving');
      setTimeout(function () { el.remove(); }, 260);
    };
    var timer = setTimeout(fecha, opts.ms || 5000);
    var undo = el.querySelector('.otc-toast__undo');
    if (undo) undo.addEventListener('click', function () { clearTimeout(timer); fecha(); try { opts.undo(); } catch (e) {} });
    el.addEventListener('mouseenter', function () { clearTimeout(timer); });
    el.addEventListener('mouseleave', function () { timer = setTimeout(fecha, 2500); });
    return el;
  }
  window.otcToast = otcToast;

  // ==========================================================================
  // 3e. A ILHA do foco (o "island" do Pane): uma pílula preta sob a barra do
  // topo com o anel e o tempo, em QUALQUER página, enquanto há sessão. O estado
  // fica no localStorage (a ilha conta sem ir ao servidor e acompanha as abas
  // pelo evento `storage`); o SERVIDOR é avisado de cada passo
  // (`/api/user-home/focus`) — é de lá que a User Home soma o foco do dia e os
  // colegas veem "In focus · until 11:30". Acabou o foco: avisa (toast e, com
  // a preferência ligada e a permissão dada, a notificação do sistema), grava a
  // sessão e começa a PAUSA da Settings, que a ilha conta em verde.
  // ==========================================================================
  var FOCUS_KEY = '__OTC_FOCUS__', FOCUS_PREFS_KEY = '__OTC_FOCUS_PREFS__';
  var FOCUS_T = {
    en: { focus: 'Focus', paused: 'Paused', brk: 'Break', done: 'Focus finished', done_brk: 'Focus finished — {n}-minute break', brk_over: 'Break over' },
    br: { focus: 'Foco', paused: 'Pausado', brk: 'Pausa', done: 'Foco concluído', done_brk: 'Foco concluído — pausa de {n} min', brk_over: 'Fim da pausa' },
    es: { focus: 'Foco', paused: 'En pausa', brk: 'Pausa', done: 'Foco terminado', done_brk: 'Foco terminado — pausa de {n} min', brk_over: 'Fin de la pausa' }
  };
  function fT(k, n) {
    var lang = 'en';
    try { lang = localStorage.getItem('__OTC_TRACKER_LANG__') || 'en'; } catch (e) {}
    var m = FOCUS_T[lang] || FOCUS_T.en;
    return String(m[k] || FOCUS_T.en[k] || k).replace('{n}', n);
  }
  function fRead() { try { return JSON.parse(localStorage.getItem(FOCUS_KEY) || 'null'); } catch (e) { return null; } }
  function fWrite(st) {
    try { if (st) localStorage.setItem(FOCUS_KEY, JSON.stringify(st)); else localStorage.removeItem(FOCUS_KEY); } catch (e) {}
    fRender(); fEmit();
  }
  function fPrefs(p) {
    if (p) { try { localStorage.setItem(FOCUS_PREFS_KEY, JSON.stringify(p)); } catch (e) {} return p; }
    try { return JSON.parse(localStorage.getItem(FOCUS_PREFS_KEY) || 'null') || {}; } catch (e) { return {}; }
  }
  function fLeft(st) {
    if (!st) return 0;
    if (st.left != null) return Math.max(0, st.left);
    return Math.max(0, Math.round((st.ends - Date.now()) / 1000));
  }
  var fListeners = [];
  function fEmit() { var st = fRead(); fListeners.forEach(function (cb) { try { cb(st); } catch (e) {} }); }
  function fPost(action, body) {
    var b = { action: action };
    for (var k in (body || {})) if (Object.prototype.hasOwnProperty.call(body, k)) b[k] = body[k];
    return fetch('/api/user-home/focus', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' }, body: JSON.stringify(b)
    }).then(function (r) { return r.json().then(function (d) { if (!r.ok || d.success === false) { var e = new Error(d.text || 'HTTP ' + r.status); e.code = d.code; throw e; } return d; }); });
  }
  // o estado do SERVIDOR vira o da ilha (a User Home chama ao carregar)
  function fAdopt(srv) {
    var cur = fRead();
    if (!srv) { if (cur && cur.kind === 'focus') fWrite(null); return; }
    fWrite({ kind: 'focus', total: (srv.minutes || 25) * 60, title: srv.task_title || '',
             left: srv.paused ? srv.remaining : null, ends: srv.paused ? null : Date.now() + srv.remaining * 1000 });
  }
  var otcFocus = {
    state: fRead, left: function () { return fLeft(fRead()); }, prefs: fPrefs, adopt: fAdopt,
    on: function (cb) { fListeners.push(cb); },
    start: function (minutes, task) {
      task = task || {};
      return fPost('start', { minutes: minutes, task_id: task.task_id || '', project_id: task.project_id || '' })
        .then(function (d) { fAdopt(d.focus); return d; });
    },
    pause: function () { return fPost('pause').then(function (d) { fAdopt(d.focus); return d; }); },
    resume: function () { return fPost('resume').then(function (d) { fAdopt(d.focus); return d; }); },
    end: function () { return fPost('end').then(function (d) { fWrite(null); return d; }); },
    skipBreak: function () { var st = fRead(); if (st && st.kind === 'break') fWrite(null); }
  };
  window.otcFocus = otcFocus;

  var fIsland = null;
  function fRender() {
    if (!fIsland) return;
    var st = fRead();
    if (!st) { fIsland.hidden = true; doc.body.classList.remove('otc-has-island'); return; }
    var left = fLeft(st), total = st.total || 1;
    fIsland.hidden = false;
    doc.body.classList.add('otc-has-island');
    fIsland.classList.toggle('is-break', st.kind === 'break');
    fIsland.classList.toggle('is-paused', st.left != null && st.kind === 'focus');
    fIsland.querySelector('.otc-island__label').textContent = st.kind === 'break' ? fT('brk') : (st.left != null ? fT('paused') : fT('focus'));
    fIsland.querySelector('.otc-island__time').textContent = Math.floor(left / 60) + ':' + ('0' + (left % 60)).slice(-2);
    var c = 2 * Math.PI * 7;
    var bar = fIsland.querySelector('.is-bar');
    bar.setAttribute('stroke-dasharray', c.toFixed(2));
    bar.setAttribute('stroke-dashoffset', (c * (1 - left / total)).toFixed(2));
    fIsland.title = st.title || '';
  }
  function fFinish(st) {
    // uma aba só encerra: a primeira marca o estado, as outras veem a marca
    if (st.finishing && Date.now() - st.finishing < 15000) return;
    st.finishing = Date.now();
    try { localStorage.setItem(FOCUS_KEY, JSON.stringify(st)); } catch (e) {}
    var pr = fPrefs(), brk = parseInt(pr.break_minutes, 10);
    if (!(brk >= 0)) brk = 5;
    fPost('end').catch(function () {}).then(function () {
      if (brk > 0) fWrite({ kind: 'break', total: brk * 60, ends: Date.now() + brk * 60000, left: null });
      else fWrite(null);
      var msg = brk > 0 ? fT('done_brk', brk) : fT('done');
      if (window.otcToast) window.otcToast(msg);
      var want = !pr.notify || pr.notify.focus_finished !== false;
      if (want && 'Notification' in window && Notification.permission === 'granted') {
        try { new Notification('OTC Tracker', { body: msg + (st.title ? ' · ' + st.title : '') }); } catch (e) {}
      }
    });
  }
  function initFocusIsland() {
    if (!doc.querySelector('.otc-toolbar')) return;          // só nas telas com a casca
    fIsland = doc.createElement('a');
    fIsland.className = 'otc-island';
    fIsland.href = '/user-home#focus';
    fIsland.hidden = true;
    fIsland.innerHTML = '<svg viewBox="0 0 18 18" aria-hidden="true"><circle class="is-track" cx="9" cy="9" r="7"/><circle class="is-bar" cx="9" cy="9" r="7"/></svg>' +
      '<span class="otc-island__label"></span><span class="otc-island__time"></span>';
    doc.body.appendChild(fIsland);
    fRender();
    setInterval(function () {
      var st = fRead();
      if (!st) return;
      if (st.left == null && fLeft(st) <= 0) {
        if (st.kind === 'focus') fFinish(st);
        else { fWrite(null); if (window.otcToast) window.otcToast(fT('brk_over')); }
        return;
      }
      fRender(); fEmit();
    }, 1000);
    window.addEventListener('storage', function (e) { if (e.key === FOCUS_KEY) { fRender(); fEmit(); } });
  }

  // ==========================================================================
  // 4. Paleta de comandos (Ctrl+K; no Mac também ⌘K)
  // ==========================================================================
  var Pal = null;
  function norm(s) { return String(s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, ''); }
  function buildPalette() {
    var el = doc.createElement('div');
    el.className = 'otc-palette';
    el.innerHTML =
      '<div class="otc-palette__scrim"></div>' +
      '<div class="otc-palette__box" role="dialog" aria-modal="true">' +
        '<div class="otc-palette__bar"><i data-lucide="search"></i><input type="text" autocomplete="off" spellcheck="false"><kbd>Esc</kbd></div>' +
        '<div class="otc-palette__list" role="listbox"></div>' +
      '</div>';
    doc.body.appendChild(el);
    icons();
    var input = el.querySelector('input'), list = el.querySelector('.otc-palette__list');
    Pal = { el: el, input: input, list: list, items: [], idx: 0 };
    el.querySelector('.otc-palette__scrim').addEventListener('click', closePalette);
    input.addEventListener('input', renderPalette);
    input.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        if (!Pal.items.length) return;
        Pal.idx = (Pal.idx + (e.key === 'ArrowDown' ? 1 : -1) + Pal.items.length) % Pal.items.length;
        markPalette();
      } else if (e.key === 'Enter') {
        e.preventDefault();
        var it = Pal.items[Pal.idx];
        if (it) window.location.href = it.href;
      } else if (e.key === 'Escape') closePalette();
    });
    list.addEventListener('mousemove', function (e) {
      var a = e.target.closest('.otc-palette__item');
      if (!a) return;
      var i = +a.getAttribute('data-i');
      if (i !== Pal.idx) { Pal.idx = i; markPalette(); }
    });
  }
  function renderPalette() {
    var q = norm(Pal.input.value).trim();
    var all = leaves().filter(function (o) { return isAllowed(o.href); });
    var hits = !q ? all : all.filter(function (o) {
      var hay = norm(o.label + ' ' + o.trail.join(' ') + ' ' + o.href);
      return q.split(/\s+/).every(function (w) { return hay.indexOf(w) !== -1; });
    });
    Pal.items = hits.slice(0, 60);
    Pal.idx = 0;
    if (!Pal.items.length) { Pal.list.innerHTML = '<div class="otc-palette__empty">' + esc(t('none')) + '</div>'; return; }
    var html = '', group = null;
    Pal.items.forEach(function (o, i) {
      var g = o.trail[0] || '';
      if (g !== group) { group = g; if (g) html += '<div class="otc-palette__group">' + esc(g) + '</div>'; }
      var icon = (o.node && (function () { var p = o.node; while (p.parent) p = p.parent; var ic = p.li.querySelector(':scope > a .menu-icon [data-lucide], :scope > a .menu-icon svg'); if (!ic) return ''; var m = (ic.getAttribute('class') || '').match(/lucide-([a-z0-9-]+)/); return ic.getAttribute('data-lucide') || (m ? m[1] : ''); })()) || 'file-text';
      html += '<a class="otc-palette__item" href="' + esc(o.href) + '" data-i="' + i + '">' +
        '<span class="ico"><i data-lucide="' + esc(icon) + '"></i></span>' +
        '<span><span class="t">' + esc(o.label) + '</span><br><span class="s">' + esc(o.trail.length ? o.trail.join(' › ') : t('goto')) + '</span></span></a>';
    });
    Pal.list.innerHTML = html;
    icons();
    markPalette();
  }
  function markPalette() {
    $$('.otc-palette__item', Pal.list).forEach(function (a, i) {
      a.classList.toggle('is-active', i === Pal.idx);
      if (i === Pal.idx) a.scrollIntoView({ block: 'nearest' });
    });
  }
  function openPalette() {
    if (!Pal) buildPalette();
    Pal.input.placeholder = t('search');
    Pal.input.value = '';
    Pal.el.classList.add('is-open');
    renderPalette();
    setTimeout(function () { Pal.input.focus(); }, 0);
  }
  function closePalette() { if (Pal) Pal.el.classList.remove('is-open'); }
  window.otcPalette = { open: openPalette, close: closePalette };
  doc.addEventListener('keydown', function (e) {
    if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) { e.preventDefault(); openPalette(); }
  });

  // ==========================================================================
  // 5. Painel de Aparência (offcanvas do customizer.html)
  // ==========================================================================
  var ACCENTS = { blue: '#1f6fe6', purple: '#7b3ff0', pink: '#cf2068', orange: '#c4500f', green: '#167f3d', graphite: '#4a4a54' };
  var WALLS = {
    ash: 'linear-gradient(135deg,#2a2b30,#e4e4e7)', sand: 'linear-gradient(135deg,#3a2a1e,#f6e4d2)', sage: 'linear-gradient(135deg,#1f2c23,#dde9dc)',
    aurora: 'radial-gradient(80% 70% at 10% 100%,#34469e,transparent 70%),radial-gradient(70% 70% at 100% 0,#2b3a8c,transparent 70%),linear-gradient(135deg,#090b1c,#0c0f24)',
    smoke: 'radial-gradient(80% 70% at 10% 100%,#5c5c64,transparent 70%),linear-gradient(135deg,#070708,#2a2a30)',
    tide: 'radial-gradient(80% 70% at 10% 100%,#16c3b0,transparent 70%),radial-gradient(70% 70% at 100% 0,#1d55dc,transparent 70%),linear-gradient(135deg,#03112a,#0d0a2c)',
    bloom: 'radial-gradient(80% 70% at 10% 100%,#d08a2a,transparent 70%),radial-gradient(70% 70% at 100% 0,#c2306c,transparent 70%),linear-gradient(135deg,#130a2b,#2a0c22)',
    ember: 'radial-gradient(80% 70% at 10% 100%,#c98a12,transparent 70%),radial-gradient(70% 70% at 100% 0,#c4501a,transparent 70%),linear-gradient(135deg,#200a04,#2a0a12)',
    grove: 'radial-gradient(80% 70% at 10% 100%,#5e9e1f,transparent 70%),radial-gradient(70% 70% at 100% 0,#1c8f55,transparent 70%),linear-gradient(135deg,#04170e,#041a1e)',
    dusk: 'radial-gradient(80% 70% at 10% 100%,#6a5440,transparent 70%),radial-gradient(70% 70% at 100% 0,#3d425e,transparent 70%),linear-gradient(135deg,#0f1016,#17121c)'
  };
  otcUI.accents = ACCENTS;
  otcUI.walls = WALLS;
  function initAppearance() {
    // TODA lista na página (a gaveta de Aparência e a tela Settings, §632)
    $$('[data-otc-accents]').forEach(function (sw) {
      if (sw.children.length) return;
      sw.innerHTML = Object.keys(ACCENTS).map(function (k) {
        return '<button type="button" class="otc-swatch" data-accent-pick="' + k + '" style="--sw:' + ACCENTS[k] + '" aria-label="' + k + '" title="' + k.charAt(0).toUpperCase() + k.slice(1) + '"></button>';
      }).join('');
    });
    $$('[data-otc-walls]').forEach(function (wl) {
      if (wl.children.length) return;
      wl.innerHTML = Object.keys(WALLS).map(function (k) {
        return '<button type="button" class="otc-wall" data-wall-pick="' + k + '"><span class="art" style="--art:' + WALLS[k] + '"></span>' + k.charAt(0).toUpperCase() + k.slice(1) + '</button>';
      }).join('');
    });
    doc.addEventListener('click', function (e) {
      var a = e.target.closest('[data-accent-pick]');
      if (a) { otcUI.set({ accent: a.getAttribute('data-accent-pick') }, false); return; }
      var w = e.target.closest('[data-wall-pick]');
      if (w) { otcUI.set({ wall: w.getAttribute('data-wall-pick') }, true); return; }
      var th = e.target.closest('[data-theme-pick]');
      if (th) { otcUI.set({ theme: th.getAttribute('data-theme-pick') }, true); return; }
      var g = e.target.closest('[data-glass-pick]');
      if (g) { otcUI.set({ glass: g.getAttribute('data-glass-pick') }, false); return; }
    });
    $$('[data-otc-solid]').forEach(function (solid) {
      solid.addEventListener('change', function () { otcUI.fx(solid.checked ? 'reduced' : 'full'); });
    });
    syncAppearance();
  }
  function syncAppearance() {
    var p = readPrefs();
    $$('[data-accent-pick]').forEach(function (b) { b.classList.toggle('is-on', b.getAttribute('data-accent-pick') === p.accent); });
    $$('[data-wall-pick]').forEach(function (b) { b.classList.toggle('is-on', b.getAttribute('data-wall-pick') === p.wall); });
    $$('[data-theme-pick]').forEach(function (b) { b.classList.toggle('active', b.getAttribute('data-theme-pick') === p.theme); });
    $$('[data-glass-pick]').forEach(function (b) { b.classList.toggle('active', b.getAttribute('data-glass-pick') === p.glass); });
    $$('[data-otc-solid]').forEach(function (solid) { solid.checked = root.classList.contains('is-solid'); });
    $$('.nav[data-otc-seg]').forEach(function (n) { placeSegLens(n, true); });
  }

  // botão de tema da barra (sol/lua): alterna claro/escuro
  function initThemeButton() {
    var b = doc.getElementById('otc-theme-btn');
    if (!b) return;
    b.addEventListener('click', function () {
      otcUI.set({ theme: root.getAttribute('data-bs-theme') === 'dark' ? 'light' : 'dark' }, true);
    });
  }

  // ==========================================================================
  // 6. Segmentos com lente (nav-tabs / nav-pills / [data-otc-seg])
  // ==========================================================================
  function placeSegLens(nav, animate) {
    var a = nav.querySelector('.nav-link.active, .active > .nav-link, button.active, .fc-button-active');
    var l = nav.querySelector(':scope > .otc-lens');
    if (!a || !a.offsetParent) { if (l) l.style.opacity = '0'; return; }
    l = lensFor(nav);
    l.style.opacity = '1';
    var b = rectIn(nav, a);
    l.style.borderRadius = Math.min(b.h / 2, 22) + 'px';
    if (animate && l.dataset.w && (Math.abs(+l.dataset.x - b.x) > 1 || Math.abs(+l.dataset.y - b.y) > 1)) {
      animateLens(l, { x: +l.dataset.x, y: +l.dataset.y, w: +l.dataset.w, h: +l.dataset.h }, b);
    } else setLensBox(l, b);
  }
  // segmentos: abas do Bootstrap, os da Aparência e as visões do FullCalendar
  // (estes nascem DEPOIS do load — o calendário espera os feriados)
  var SEG_SEL = '.nav-tabs, .nav-pills, .nav[data-otc-seg], .fc-header-toolbar .fc-button-group';
  var segRO = window.ResizeObserver ? new ResizeObserver(window.debounce(function () {
    $$('.otc-has-lens').forEach(function (n) { placeSegLens(n, false); });
  }, 60)) : null;
  function initSegments() {
    var navs = $$(SEG_SEL);
    navs.forEach(function (n) {
      if (n.__otcSeg) return;
      n.__otcSeg = true;
      n.classList.add('otc-has-lens');
      placeSegLens(n, false);
      // as telas trocam o `.active` de várias formas (Bootstrap tab, à mão):
      // observar a classe cobre todas
      var mo = new MutationObserver(window.debounce(function () { placeSegLens(n, true); }, 16));
      mo.observe(n, { attributes: true, attributeFilter: ['class'], subtree: true });
    });
    if (segRO) navs.forEach(function (n) { if (!n.__otcSegRO) { n.__otcSegRO = true; segRO.observe(n); } });
  }
  ready(function () {
    if (!window.MutationObserver) return;
    var t = null;
    new MutationObserver(function () {
      if (t) return;
      t = setTimeout(function () { t = null; if (doc.querySelector(SEG_SEL.split(', ').map(function (x) { return x + ':not(.otc-has-lens)'; }).join(', '))) initSegments(); }, 120);
    }).observe(doc.body, { childList: true, subtree: true });
  });

  // ==========================================================================
  // 7. Gel: o botão afunda e volta com mola; o anel do clique
  // ==========================================================================
  var PRESS_SEL = '.btn, .otc-tbtn, .otc-search, .otc-swatch, .otc-wall, .side-nav-link, .nav-link, .otc-menu-btn';
  var pressed = null;
  function pressIn(el) {
    if (!el.animate || REDUCED_MOTION) return;
    if (el.__otcPress) el.__otcPress.cancel();
    el.__otcPress = el.animate([{ scale: '1 1' }, { scale: '1.07 0.9' }], { duration: 130, easing: 'cubic-bezier(.2,.8,.3,1)', fill: 'forwards' });
  }
  function pressOut(el) {
    if (!el.animate || REDUCED_MOTION) return;
    var prev = el.__otcPress;
    var a = el.animate([
      { scale: '1.07 0.9' }, { scale: '0.966 1.048', offset: .16 }, { scale: '1.011 0.984', offset: .38 },
      { scale: '0.996 1.005', offset: .58 }, { scale: '1 1' }
    ], { duration: 520, easing: 'linear' });
    if (prev) prev.cancel();
    el.__otcPress = null;
    a.onfinish = function () { a.cancel(); };
  }
  function ripple(el, e) {
    if (REDUCED_MOTION || !el.classList.contains('btn') || el.matches(SEND_SEL)) return;
    var r = el.getBoundingClientRect();
    var s = doc.createElement('span');
    s.className = 'otc-ripple';
    s.style.left = (e.clientX - r.left) + 'px';
    s.style.top = (e.clientY - r.top) + 'px';
    var hadHost = el.classList.contains('otc-ripple-host');
    el.classList.add('otc-ripple-host');
    el.appendChild(s);
    setTimeout(function () { s.remove(); if (!hadHost && !el.querySelector('.otc-ripple')) el.classList.remove('otc-ripple-host'); }, 820);
  }
  doc.addEventListener('pointerdown', function (e) {
    if (e.button !== 0) return;
    var el = e.target.closest(PRESS_SEL);
    if (!el || el.disabled || el.classList.contains('disabled')) return;
    pressed = el;
    pressIn(el);
    ripple(el, e);
  }, { passive: true });
  function release() { if (pressed) { pressOut(pressed); pressed = null; } }
  doc.addEventListener('pointerup', release, { passive: true });
  doc.addEventListener('pointercancel', release, { passive: true });
  window.addEventListener('blur', release);

  // ==========================================================================
  // 8. Brilho que segue o ponteiro nas placas de vidro (`--mx`/`--my`)
  // ==========================================================================
  var SHEEN_SEL = '.card, .sidenav-menu, .otc-toolbar, .modal-content.liquid-glass, .tl-card, .cp-card, .swal2-popup, .offcanvas, .otc-menu-btn';
  var sheenEl = null, sheenPt = null, sheenRaf = 0;
  doc.addEventListener('pointermove', function (e) {
    if (root.classList.contains('is-solid') || e.pointerType === 'touch') return;
    sheenPt = { x: e.clientX, y: e.clientY, t: e.target };
    if (sheenRaf) return;
    sheenRaf = requestAnimationFrame(function () {
      sheenRaf = 0;
      var el = sheenPt.t && sheenPt.t.closest ? sheenPt.t.closest(SHEEN_SEL) : null;
      if (sheenEl && sheenEl !== el) { sheenEl.style.removeProperty('--mx'); sheenEl.style.removeProperty('--my'); }
      sheenEl = el;
      if (!el) return;
      var r = el.getBoundingClientRect();
      el.style.setProperty('--mx', (sheenPt.x - r.left) + 'px');
      el.style.setProperty('--my', (sheenPt.y - r.top) + 'px');
    });
  }, { passive: true });

  // ==========================================================================
  // 9. Entrada da página: gotas em sequência, título letra a letra
  // ==========================================================================
  var SURFACE_SEL = '.card, .tl-card, .cp-card, .otc-stat, .acc-stat, .ob-stat, div[class*="-widget"]:not([class*="__"]):not(.row), div[class*="-panel"]:not([class*="__"]):not(.row):not(.tab-pane), .page-title-head + .row > [class*="col"] > :not(.card):not(.row)';
  function initEntrance() {
    if (REDUCED_MOTION) return;
    var page = doc.querySelector('.content-page');
    if (!page) return;
    var all = $$(SURFACE_SEL, page).filter(function (el) {
      if (el.closest('.modal, .offcanvas, .dropdown-menu, .dt-container table, [data-otc-noenter]')) return false;
      // só o primeiro nível: placa dentro de placa entra junto com a de fora
      var p = el.parentElement;
      while (p && p !== page) { if (p.__otcSurface) return false; p = p.parentElement; }
      el.__otcSurface = true;
      return true;
    });
    var vh = window.innerHeight, i = 0;
    var io = 'IntersectionObserver' in window ? new IntersectionObserver(function (ents) {
      var k = 0;
      ents.forEach(function (en) {
        if (!en.isIntersecting) return;
        io.unobserve(en.target);
        en.target.style.setProperty('--otc-i', k++);
        en.target.classList.add('otc-enter');
      });
    }, { rootMargin: '0px 0px -6% 0px' }) : null;
    all.forEach(function (el) {
      var top = el.getBoundingClientRect().top;
      if (top < vh || !io) {
        el.style.setProperty('--otc-i', Math.min(i++, 12));
        el.classList.add('otc-enter');
      } else io.observe(el);
      el.addEventListener('animationend', function done(ev) {
        if (ev.target !== el) return;
        el.classList.remove('otc-enter');
        el.removeEventListener('animationend', done);
      });
    });
  }
  function splitTitle() {
    if (REDUCED_MOTION) return;
    var h = doc.querySelector('.content-page .page-title-head h4, .content-page .page-title-head h5');
    if (!h || h.children.length || h.__otcSplit) return;
    var txt = h.textContent;
    if (!txt || txt.length > 60) return;
    h.__otcSplit = true;
    // o texto continua o MESMO (o Advanced Export lê este título como nome
    // de arquivo): só ganha spans, um por letra
    var words = txt.trim().split(/(\s+)/);
    var c = 0;
    h.innerHTML = words.map(function (w) {
      if (/^\s+$/.test(w)) return w;
      return '<span class="otc-title-clip">' + w.split('').map(function (ch) {
        return '<span class="otc-title-char" style="--otc-c:' + (c++) + '">' + esc(ch) + '</span>';
      }).join('') + '</span>';
    }).join('');
  }

  // ==========================================================================
  // 9b. Cards de contagem: o valor CONTA até o novo (do zero na primeira vez)
  // e, quando muda, o card pisca no destaque por 1s — o "flash" do Pane. Vale
  // para o `.otc-stat` do KPI e para os cards de número de TODA tela (os
  // `*-widget__value`, Accrual/MtM, Tracking Docs, recons — pedido de
  // 19/10/2026): quem preenche só troca o texto. O texto final é sempre o que
  // a página escreveu (a formatação dela), a contagem só passa pelos inteiros
  // no caminho. Valor com casa decimal, moeda ou % não conta (só pisca).
  // ==========================================================================
  var STAT_VALUES = '.otc-stat__value, .otc-legend__value[id], [class*="-widget__value"], .acc-stat__value, .ob-stat__n, .widget-val, .im-kpi > b, .im-prev-top > b, .cgd-kpi__n, .cfm-kpi__n, .mc-w__val';
  var STAT_TILES = '.otc-stat, div[class*="-widget"]:not([class*="__"]), .acc-stat, .ob-stat, .recon-widget, .im-kpi, .cgd-kpi, .cfm-kpi, .mc-w';
  function statNumber(txt) {
    return /^-?\d{1,3}(,\d{3})*$|^-?\d+$/.test(txt) ? parseFloat(txt.replace(/[^\d-]/g, '')) : NaN;
  }
  function animateStat(el, quiet) {
    var txt = (el.textContent || '').trim();
    if (txt === el.__otcFrame || txt === el.__otcText) return;   // escrita nossa
    var prev = el.__otcVal, to = statNumber(txt);
    el.__otcText = txt;
    el.__otcVal = isFinite(to) ? to : undefined;
    var anim = (el.__otcAnim || 0) + 1;
    el.__otcAnim = anim;
    if (!isFinite(to)) return;                    // traço do placeholder, texto
    // A PRIMEIRA carga não pisca: o card que nasce com "0" e recebe o número
    // do dia não "mudou" — só o que muda depois pisca.
    var tile = quiet ? null : el.closest(STAT_TILES);
    if (tile && prev !== undefined && prev !== to) {
      tile.classList.remove('is-flash');
      void tile.offsetWidth;                      // reinicia a animação
      tile.classList.add('is-flash');
    }
    var from = prev !== undefined ? prev : 0;
    if (REDUCED_MOTION || from === to) return;
    var dur = prev !== undefined ? 650 : 900, t0 = null;
    function frame(ts) {
      if (el.__otcAnim !== anim) return;          // chegou outro valor no meio
      if (t0 === null) t0 = ts;
      var p = Math.min((ts - t0) / dur, 1), e = 1 - Math.pow(1 - p, 3);
      el.__otcFrame = p < 1 ? Math.round(from + (to - from) * e).toLocaleString('en-US') : txt;
      el.textContent = el.__otcFrame;
      if (p < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }
  function initStats() {
    bindStats();
    // card montado pela tela DEPOIS do load (CGD, Conf. Matching): liga ao nascer
    var page = doc.querySelector('.content-page');
    if (page && window.MutationObserver) {
      new MutationObserver(window.debounce ? window.debounce(bindStats, 60) : bindStats)
        .observe(page, { childList: true, subtree: true });
    }
    doc.addEventListener('animationend', function (e) {
      if (e.animationName === 'otc-stat-ring') e.target.classList.remove('is-flash');
    });
  }
  function bindStats() {
    $$(STAT_VALUES).forEach(function (el) {
      if (el.__otcStat) return;
      el.__otcStat = true;
      new MutationObserver(function () {
        var first = !el.__otcSeen;
        if (first && !(el.textContent || '').trim().match(/^[-–—\s]*$/)) el.__otcSeen = true;
        animateStat(el, first);
      }).observe(el, { childList: true, characterData: true, subtree: true });
      animateStat(el, true);
    });
  }

  // ==========================================================================
  // 10. SEND — o "Contrail"
  // ==========================================================================
  // O avião voa no clique, mas "Sent" só aparece depois que o SERVIDOR
  // respondeu bem: este arquivo correlaciona o clique com os pedidos que a
  // página dispara em seguida (fetch e XHR/jQuery). Se a página abre uma
  // confirmação (Swal) antes de enviar, a janela começa quando ela fecha. Sem
  // pedido nenhum, o botão volta quieto — nada foi enviado.
  var SEND_SEL = '.btn-row-send, .acc-act-send, .btn-send, .otc-send';
  var S = null;                                         // o envio "armado"
  var OK_SVG = '<svg class="otc-send__ok" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>';
  function decorate(btn) {
    if (btn.__otcSend) return;
    btn.__otcSend = true;
    var square = btn.offsetWidth && btn.offsetWidth < 48;
    if (!square) {
      Array.prototype.slice.call(btn.childNodes).forEach(function (n) {
        if (n.nodeType === 3 && n.textContent.trim()) {
          var s = doc.createElement('span');
          s.className = 'otc-send__label';
          s.textContent = n.textContent;
          btn.replaceChild(s, n);
        }
      });
    }
    btn.insertAdjacentHTML('beforeend',
      '<span class="otc-send__fill" aria-hidden="true"></span><span class="otc-send__trail" aria-hidden="true"></span>' +
      '<span class="otc-send__done" aria-hidden="true">' + (square ? OK_SVG : esc(t('sent'))) + '</span>');
  }
  function sendState(btn, cls) {
    btn.classList.remove('is-flying', 'is-sent', 'is-failed', 'is-resetting');
    if (cls) btn.classList.add(cls);
  }
  function fly(st) {
    if (st.flying) return;
    st.flying = true;
    st.t0 = Date.now();
    decorate(st.btn);
    var done = st.btn.querySelector('.otc-send__done');
    if (done && !done.querySelector('svg')) done.textContent = t('sent');
    sendState(st.btn, 'is-flying');
  }
  function finish(st) {
    if (st.finished) return;
    st.finished = true;
    if (S === st) S = null;
    var btn = st.btn;
    var wait = Math.max(0, 900 - (Date.now() - st.t0));     // o voo termina antes do desfecho
    setTimeout(function () {
      if (!st.failed) {
        sendState(btn, 'is-sent');
        setTimeout(function () {
          sendState(btn, 'is-resetting');
          setTimeout(function () { sendState(btn, null); }, 460);
        }, 2200);
      } else {
        btn.style.setProperty('--otc-fill-w', '0%');
        sendState(btn, 'is-failed');
        setTimeout(function () { sendState(btn, null); btn.style.removeProperty('--otc-fill-w'); }, 420);
      }
    }, wait);
  }
  function disarm(st) { if (S === st) S = null; if (st.flying && !st.finished) { st.failed = false; sendState(st.btn, null); } }
  function arm(btn) {
    if (S && !S.finished) disarm(S);
    var st = { btn: btn, pending: 0, any: false, failed: false, flying: false, finished: false, open: Date.now() + 600, deadline: Date.now() + 20000 };
    S = st;
    var inModal = btn.closest('.modal');
    // sem pedido dentro da janela (e sem confirmação aberta): nada a fazer
    setTimeout(function check() {
      if (S !== st || st.any) return;
      if (Date.now() > st.deadline) { disarm(st); return; }
      var deciding = doc.querySelector('.swal2-container.swal2-backdrop-show') ||
        $$('.modal.show').some(function (m) { return m !== inModal; });
      if (deciding) {
        st.open = Date.now() + 600;                      // ainda decidindo
        setTimeout(check, 250);
        return;
      }
      if (Date.now() > st.open) disarm(st);
      else setTimeout(check, 150);
    }, 150);
  }
  function reqStart() {
    var st = S;
    if (!st || st.finished || Date.now() > st.open && !st.pending) return null;
    st.pending++;
    st.any = true;
    fly(st);
    return st;
  }
  function reqEnd(st, ok) {
    if (!st) return;
    if (!ok) st.failed = true;
    st.pending--;
    if (st.pending > 0) return;
    // pedido encadeado (preview → envio) ganha um respiro antes do desfecho
    st.open = Date.now() + 300;
    setTimeout(function () { if (!st.pending) finish(st); }, 300);
  }
  function judgeJson(j) {
    if (!j || typeof j !== 'object') return true;
    if (j.success === false || j.ok === false) return false;
    if (j.error && j.success !== true) return false;
    return true;
  }
  if (window.fetch) {
    var _fetch = window.fetch;
    window.fetch = function () {
      var st = reqStart();
      var p = _fetch.apply(this, arguments);
      if (!st) return p;
      p.then(function (res) {
        var ct = (res.headers && res.headers.get('content-type')) || '';
        if (!res.ok) { reqEnd(st, false); return; }
        if (ct.indexOf('json') === -1) { reqEnd(st, true); return; }
        res.clone().json().then(function (j) { reqEnd(st, judgeJson(j)); }, function () { reqEnd(st, true); });
      }, function () { reqEnd(st, false); });
      return p;
    };
  }
  (function () {
    var X = window.XMLHttpRequest && window.XMLHttpRequest.prototype;
    if (!X) return;
    var _send = X.send;
    X.send = function () {
      var st = reqStart();
      if (st) {
        var xhr = this;
        xhr.addEventListener('loadend', function () {
          var ok = xhr.status >= 200 && xhr.status < 400;
          if (ok && /json/.test(xhr.getResponseHeader('content-type') || '')) {
            try { ok = judgeJson(JSON.parse(xhr.responseText)); } catch (e) {}
          }
          reqEnd(st, ok);
        });
      }
      return _send.apply(this, arguments);
    };
  })();
  // captura: arma ANTES do handler da página disparar o pedido
  doc.addEventListener('click', function (e) {
    var b = e.target.closest(SEND_SEL);
    if (!b || b.disabled || b.classList.contains('disabled') || b.classList.contains('is-flying')) return;
    arm(b);
  }, true);
  window.otcSend = {
    // para a página que quer controlar o desfecho à mão
    start: function (btn) { arm(btn); var st = S; st.any = true; fly(st); return st; },
    done: function (st, ok) { if (!st) return; st.failed = ok === false; finish(st); }
  };

  // ==========================================================================
  // 11. Cabeçalho fixo das tabelas (os offsets de cada linha do <thead>)
  // ==========================================================================
  (function () {
    var seen = typeof WeakSet === 'function' ? new WeakSet() : null;
    var ro = null;
    function sync(table) {
      var head = table.tHead;
      if (!head || !head.rows.length) return;
      var top = 0;
      for (var i = 0; i < head.rows.length; i++) {
        table.style.setProperty('--vr-thead-row' + i, top.toFixed(2) + 'px');
        top += head.rows[i].getBoundingClientRect().height;
      }
    }
    function watch(table) {
      if (seen && seen.has(table)) { sync(table); return; }
      if (seen) seen.add(table);
      sync(table);
      if (ro && table.tHead) ro.observe(table.tHead);
    }
    function scan() { $$('.table-responsive table').forEach(watch); }
    window.vrSyncStickyTables = scan;
    ready(function () {
      if (window.ResizeObserver) {
        ro = new ResizeObserver(function (ents) {
          ents.forEach(function (en) { if (en.target && en.target.parentNode) sync(en.target.parentNode); });
        });
      }
      scan();
      if (window.MutationObserver) {
        var pending = null;
        new MutationObserver(function () {
          if (pending) return;
          pending = setTimeout(function () { pending = null; scan(); }, 200);
        }).observe(doc.body, { childList: true, subtree: true });
      }
      window.addEventListener('resize', function () { $$('.table-responsive table').forEach(sync); });
    });
  })();

  // ==========================================================================
  // 12. Boot
  // ==========================================================================
  function initBootstrapBits() {
    icons();
    if (!window.bootstrap) return;
    $$('[data-bs-toggle="popover"]').forEach(function (el) { new bootstrap.Popover(el); });
    $$('[data-bs-toggle="tooltip"]').forEach(function (el) { bootstrap.Tooltip.getOrCreateInstance(el); });
    $$('.toast').forEach(function (el) { bootstrap.Toast.getOrCreateInstance(el); });
  }
  function initFullscreen() {
    $$('[data-toggle="fullscreen"]').forEach(function (b) {
      b.addEventListener('click', function (e) {
        e.preventDefault();
        if (!doc.fullscreenElement) doc.documentElement.requestFullscreen && doc.documentElement.requestFullscreen();
        else doc.exitFullscreen && doc.exitFullscreen();
      });
    });
  }
  function initToolbarWidth() {
    var bar = doc.querySelector('.app-topbar');
    if (!bar) return;
    var set = function () { root.style.setProperty('--otc-toolbar-w', Math.ceil(bar.getBoundingClientRect().width) + 'px'); };
    set();
    if (window.ResizeObserver) new ResizeObserver(set).observe(bar);
  }

  ready(function () {
    initBootstrapBits();
    initToolbarWidth();
    initThemeButton();
    initAppearance();
    initDrawer();
    initFullscreen();
    $$('[data-otc-palette]').forEach(function (b) { b.addEventListener('click', openPalette); });

    buildNav();
    renderPinned();
    accessThen(function () {
      if (Nav.allowed) buildNav();
      renderPinned();
      if (window.otcI18n) window.otcI18n.applyTranslations();
    });

    initSegments();
    initSelectMenus();
    initFocusIsland();
    initLiquidGlass();
    initEntrance();
    initStats();

    window.otcI18n = new I18nManager();
    window.applyTranslations = function () { return window.otcI18n.applyTranslations(); };
    window.otcI18n.init().then(function () {
      splitTitle();
      // a lente mede o item já traduzido (o texto muda de largura)
      var cur = Nav.stage && Nav.stage.querySelector('.dd-panel.dd-current');
      if (cur) placeLens(cur, false);
      $$('.nav.otc-has-lens').forEach(function (n) { placeSegLens(n, false); });
    });
    window.addEventListener('otc:language-changed', function () { renderCrumbs(); icons(); });
  });
})();
