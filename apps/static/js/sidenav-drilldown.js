/**
 * Sidenav drill-down navigation
 * ------------------------------------------------------------------------
 * Replaces the theme's accordion (expand-in-place) behaviour with a
 * master → detail "drill-down": clicking a parent slides the sidenav to show
 * ONLY that parent's children, with a breadcrumb on top to walk back up.
 *
 * The original `ul.side-nav` markup is reused as an immutable data source, so
 * every href, `data-lang` i18n span and lucide icon keeps working and the
 * rows keep the exact theme look (each level is a real `ul.side-nav` again —
 * only its <li> set changes). On load it opens straight to the level that
 * contains the current page and highlights it.
 *
 * Animation follows the Emil Kowalski principles: transform/opacity only
 * (GPU), a strong custom ease-out, ~240ms (drawer-like, occasional),
 * interruptible CSS transitions, and a light entrance stagger that is dropped
 * under prefers-reduced-motion.
 */
(function () {
  'use strict';

  var REDUCED = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Pages that should keep the sidenav at the ROOT level instead of auto-drilling
  // into a submenu (the Dashboards/home page lives directly under a root branch).
  var INDEX_PATHS = ['/dashboard', '/'];

  // Capture the menu NOW — this <script> runs during body parse, before app.js's
  // DOMContentLoaded handler mutates it (Bootstrap collapse .show() flips
  // .collapse↔.collapsing mid-animation, which would corrupt our parse/strip).
  // Building from this pristine clone makes us immune to that race.
  var PRISTINE = (function () {
    var nav = document.querySelector('.side-nav');
    return nav ? nav.cloneNode(true) : null;
  })();

  function ready(fn) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn);
    else fn();
  }

  function whenMenuReady(attempt, fn) {
    var nav = document.querySelector('.side-nav');
    if (nav && nav.children.length) return fn(nav);
    if ((attempt || 0) > 60) return;
    setTimeout(function () { whenMenuReady((attempt || 0) + 1, fn); }, 50);
  }

  function h(tag, cls, html) {
    var el = document.createElement(tag);
    if (cls) el.className = cls;
    if (html != null) el.innerHTML = html;
    return el;
  }

  // ── Tree model (parsed from a detached clone of the original menu) ─────────
  function parseLevel(ul, parent) {
    var nodes = [];
    Array.prototype.forEach.call(ul.children, function (li) {
      if (li.classList.contains('side-nav-title')) {
        nodes.push({ kind: 'title', srcLi: li });
        return;
      }
      if (!li.classList.contains('side-nav-item')) return;
      var a = li.querySelector(':scope > a');
      if (!a) return;
      var sub = li.querySelector(':scope > .collapse > ul.sub-menu, :scope > .collapsing > ul.sub-menu, :scope > ul.sub-menu, :scope > .collapse > .sub-menu');
      var node = {
        srcLi: li, a: a,
        href: (a.getAttribute('href') || '').split(/[?#]/)[0].replace(/\/+$/, ''),
        textEl: a.querySelector(':scope > .menu-text'),
        parent: parent || null,
      };
      if (sub) { node.kind = 'branch'; node.children = parseLevel(sub, node); }
      else { node.kind = 'leaf'; }
      nodes.push(node);
    });
    return nodes;
  }

  function labelOf(node) {
    if (node.textEl) return node.textEl.textContent.trim();
    return (node.a && node.a.textContent.trim()) || '';
  }
  function langOf(node) {
    return node.textEl ? node.textEl.getAttribute('data-lang') : null;
  }

  function SideNavDrill(sideNav) {
    // DECOUPLED from the original menu: the theme (app.js initLeftSidebar +
    // Bootstrap collapse + SimpleBar) keeps operating on the ORIGINAL ul, which
    // we simply hide — so nothing it does can bring the accordion back. Our
    // drill-down lives in its own container built from an immutable clone.
    // Prefer the pristine pre-app.js clone; fall back to the live menu.
    var source = (PRISTINE ? PRISTINE.cloneNode(true) : sideNav.cloneNode(true));
    this.root = parseLevel(source, null);
    this.openPath = [];
    this.currentPathname = window.location.pathname.replace(/\/+$/, '') || '/';

    sideNav.classList.add('dd-source-hidden');       // hide the theme accordion

    var ddNav = h('div', 'dd-nav');
    var crumbs = h('div', 'dd-crumbs');
    var stage = h('div', 'dd-stage');
    ddNav.appendChild(crumbs);
    ddNav.appendChild(stage);
    sideNav.parentNode.insertBefore(ddNav, sideNav.nextSibling);

    this.crumbs = crumbs; this.stage = stage;

    // Open to the active page's level (if any).
    var activeLeaf = this.findActiveLeaf(this.root);
    if (activeLeaf) {
      var chain = [], p = activeLeaf.parent;
      while (p) { chain.unshift(p); p = p.parent; }
      this.openPath = chain;
    }
    this.activeLeaf = activeLeaf;

    // The index/home page (Dashboards) shows the ROOT level with "Dashboards"
    // highlighted — not drilled into its subitems.
    if (INDEX_PATHS.indexOf(this.currentPathname) !== -1) this.openPath = [];

    // First panel is a fresh <ul.side-nav> (inherits 100% of the theme look).
    var first = h('ul', 'side-nav dd-panel dd-current');
    this.fillPanel(first);
    this.stage.appendChild(first);
    this.renderCrumbs();
    this.markRoot();
    this.wire();
  }

  SideNavDrill.prototype.markRoot = function () {
    this.crumbs.classList.toggle('dd-at-root', this.openPath.length === 0);
  };

  SideNavDrill.prototype.findActiveLeaf = function (nodes) {
    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      if (n.kind === 'leaf') {
        if (n.href && n.href === this.currentPathname) return n;
      } else if (n.kind === 'branch') {
        var f = this.findActiveLeaf(n.children);
        if (f) return f;
      }
    }
    return null;
  };

  SideNavDrill.prototype.currentNodes = function () {
    return this.openPath.length ? this.openPath[this.openPath.length - 1].children : this.root;
  };

  SideNavDrill.prototype.branchLeadsToActive = function (node) {
    if (!this.activeLeaf) return false;
    var p = this.activeLeaf.parent;
    while (p) { if (p === node) return true; p = p.parent; }
    return false;
  };

  // ── Fill a <ul.side-nav> panel with the current level's <li> clones ───────
  SideNavDrill.prototype.fillPanel = function (ul) {
    var self = this;
    ul.innerHTML = '';

    // Back row on every non-root level.
    if (this.openPath.length) {
      var parent = this.openPath[this.openPath.length - 1];
      var backLi = h('li', 'side-nav-item dd-back');
      var back = h('a', 'side-nav-link dd-back-link');
      back.href = 'javascript:void(0)';
      back.innerHTML =
        '<span class="menu-icon dd-back-icon"><i data-lucide="chevron-left"></i></span>' +
        '<span class="menu-text">' + escapeHTML(labelOf(parent)) + '</span>';
      var lg = langOf(parent);
      if (lg) back.querySelector('.menu-text').setAttribute('data-lang', lg);
      back.addEventListener('click', function (e) { e.preventDefault(); self.goTo(self.openPath.length - 2); });
      backLi.appendChild(back);
      ul.appendChild(backLi);
    }

    this.currentNodes().forEach(function (node) {
      if (node.kind === 'title') {
        ul.appendChild(node.srcLi.cloneNode(true));
        return;
      }
      var li = node.srcLi.cloneNode(true);           // identical theme markup
      // Drop ALL nested submenu subtrees — this panel shows one level only.
      // (querySelectorAll, any depth, any collapse animation state.)
      Array.prototype.forEach.call(
        li.querySelectorAll('.collapse, .collapsing, ul.sub-menu'),
        function (n) { if (n.parentNode) n.remove(); });

      // Only the ROOT items keep icons; sub-levels (openPath deep) drop them.
      if (self.openPath.length) {
        var mi = li.querySelector('.menu-icon');
        if (mi) mi.remove();
      }

      var a = li.querySelector(':scope > a');
      if (node.kind === 'branch') {
        // Turn the expand toggle into a drill trigger (keep the menu-arrow look).
        a.removeAttribute('data-bs-toggle');
        a.removeAttribute('aria-controls');
        a.setAttribute('href', 'javascript:void(0)');
        a.classList.add('dd-branch');
        if (self.branchLeadsToActive(node)) { a.classList.add('active'); li.classList.add('active'); }
        a.addEventListener('click', function (e) { e.preventDefault(); self.drillInto(node); });
      } else {
        a.classList.add('dd-leaf');
        if (node === self.activeLeaf) { a.classList.add('active'); li.classList.add('active'); }
      }
      ul.appendChild(li);
    });

    this.decorate(ul);
  };

  SideNavDrill.prototype.decorate = function (panel) {
    if (window.lucide && window.lucide.createIcons) window.lucide.createIcons();
    if (window.applyTranslations) { try { window.applyTranslations(); } catch (e) {} }
    if (!REDUCED) {
      var items = panel.querySelectorAll(':scope > li');
      Array.prototype.forEach.call(items, function (r, i) {
        r.style.setProperty('--dd-delay', Math.min(i, 9) * 24 + 'ms');
      });
      panel.classList.add('dd-stagger');
    }
    var active = panel.querySelector('.active.dd-leaf');
    if (active && active.scrollIntoView) { try { active.scrollIntoView({ block: 'nearest' }); } catch (e) {} }
  };

  // ── Breadcrumb ────────────────────────────────────────────────────────────
  SideNavDrill.prototype.renderCrumbs = function () {
    var self = this;
    this.crumbs.innerHTML = '';
    // Trail stops at the PENULTIMATE level: the current level is already named in
    // the "back" row below, so listing it again as the last crumb is redundant.
    // Every crumb shown is therefore a clickable ancestor.
    var trail = [{ label: 'Menu', lang: null, index: -1 }];   // literal (menu-title = "Navigation")
    this.openPath.slice(0, -1).forEach(function (node, i) {
      trail.push({ label: labelOf(node), lang: langOf(node), index: i });
    });
    trail.forEach(function (c, i) {
      var isLast = i === trail.length - 1;
      var inner = c.lang
        ? '<span data-lang="' + escapeAttr(c.lang) + '">' + escapeHTML(c.label) + '</span>'
        : escapeHTML(c.label);
      var crumb = h('button', 'dd-crumb', inner);
      crumb.type = 'button';
      crumb.addEventListener('click', function () { self.goTo(c.index); });
      self.crumbs.appendChild(crumb);
      if (!isLast) self.crumbs.appendChild(h('span', 'dd-crumb-sep', '<i data-lucide="chevron-right"></i>'));
    });
    this.markRoot();
    if (window.lucide && window.lucide.createIcons) window.lucide.createIcons();
    if (window.applyTranslations) { try { window.applyTranslations(); } catch (e) {} }
  };

  // ── Navigation + slide animation ──────────────────────────────────────────
  // direction: 1 = drill in (slide from right), -1 = back (slide from left)
  SideNavDrill.prototype.transition = function (direction) {
    var self = this;
    var outgoing = this.stage.querySelector('.dd-panel.dd-current');

    var incoming = h('ul', 'side-nav dd-panel');
    // Fill BEFORE inserting so height is known / no flash.
    this.fillPanel(incoming);
    this.renderCrumbs();

    if (REDUCED || !outgoing) {
      if (outgoing) outgoing.remove();
      incoming.classList.add('dd-current');
      this.stage.appendChild(incoming);
      this.refreshIcons();                           // lucide scans the live DOM
      return;
    }

    // Freeze outgoing as an absolute overlay so the in-flow incoming panel
    // drives the stage height (no layout/height animation).
    this.stage.style.minHeight = this.stage.offsetHeight + 'px';
    outgoing.style.position = 'absolute';
    outgoing.style.top = '0'; outgoing.style.left = '0'; outgoing.style.right = '0';
    outgoing.classList.remove('dd-current');

    incoming.classList.add(direction > 0 ? 'dd-enter-right' : 'dd-enter-left');
    this.stage.appendChild(incoming);
    this.refreshIcons();                             // convert now that it's in the DOM

    window.requestAnimationFrame(function () {
      window.requestAnimationFrame(function () {
        incoming.classList.remove('dd-enter-right', 'dd-enter-left');
        incoming.classList.add('dd-current');
        outgoing.classList.add(direction > 0 ? 'dd-exit-left' : 'dd-exit-right');
      });
    });

    var done = false;
    function cleanup() {
      if (done) return; done = true;
      if (outgoing.parentNode) outgoing.remove();
      self.stage.style.minHeight = '';
    }
    outgoing.addEventListener('transitionend', cleanup, { once: true });
    setTimeout(cleanup, 380);
  };

  // lucide.createIcons() scans the live document, so it must run AFTER a panel is
  // attached — otherwise a freshly-built panel's <i data-lucide> stay unconverted
  // (invisible). fillPanel/renderCrumbs run it too, but pre-attach during a slide.
  SideNavDrill.prototype.refreshIcons = function () {
    if (window.lucide && window.lucide.createIcons) window.lucide.createIcons();
  };

  SideNavDrill.prototype.drillInto = function (node) {
    this.openPath.push(node);
    this.transition(1);
  };
  SideNavDrill.prototype.goTo = function (index) {
    this.openPath = index < 0 ? [] : this.openPath.slice(0, index + 1);
    this.transition(-1);
  };

  SideNavDrill.prototype.wire = function () {
    var self = this;
    window.addEventListener('otc:language-changed', function () {
      self.renderCrumbs();
      if (window.applyTranslations) { try { window.applyTranslations(); } catch (e) {} }
    });
  };

  function escapeHTML(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function escapeAttr(s) { return escapeHTML(s); }

  ready(function () {
    whenMenuReady(0, function (sideNav) {
      if (sideNav.__ddInit) return;
      sideNav.__ddInit = true;
      try { new SideNavDrill(sideNav); }
      catch (e) {                                    // fail safe: restore the theme menu
        sideNav.classList.remove('dd-source-hidden');
        var dn = sideNav.parentNode && sideNav.parentNode.querySelector('.dd-nav');
        if (dn) dn.remove();
      }
    });
  });
})();
