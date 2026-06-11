/**
 * Template Name: OTC Tracker - Admin & Dashboard Template
 * By (Author): 
 * Module/App (File Name): Config
 */

(function () {
    const html = document.documentElement;
    const storageKey = "__OTCTRACKER_CONFIG__";
    const savedConfig = localStorage.getItem(storageKey);

    // Default config
    const defaultConfig = {
        skin: "default",                // Theme skin: classic, two, three, four, five, six
        monochrome: false,              // Enable monochrome mode
        theme: "light",                 // App theme: light or dark
        layout: {
            position: "fixed",          // Layout position: fixed or scrollable
            dir: "ltr",                 // Layout direction: ltr or rtl
        },
        topbar: {
            color: "light",             // Apple: parchment topbar
        },
        menu: {
            color: "light",             // Menu color: light, dark, or gray
        },
        sidenav: {
            size: "default",            // Sidebar size: default, collapse, or offcanvas
            user: false,                // Show user info in sidebar: true or false
        },
    };

    function getSystemTheme() {
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? "dark" : "light";
    }

    // Build config from HTML attributes
    const htmlConfig = {
        skin: html.getAttribute("data-skin") || defaultConfig.skin,
        monochrome: html.classList.contains("monochrome") || defaultConfig.monochrome,
        theme: html.getAttribute("data-bs-theme") === 'system'
            ? getSystemTheme()
            : html.getAttribute("data-bs-theme") || (defaultConfig.theme === 'system' ? getSystemTheme() : defaultConfig.theme),
        layout: {
            position: html.getAttribute("data-layout-position") || defaultConfig.layout.position,
            dir: html.getAttribute("dir") || defaultConfig.layout.dir,
        },
        topbar: {
            color: html.getAttribute("data-topbar-color") || defaultConfig.topbar.color,
        },
        menu: {
            color: html.getAttribute("data-menu-color") || defaultConfig.menu.color,
        },
        sidenav: {
            size: html.getAttribute("data-sidenav-size") || defaultConfig.sidenav.size,
            user: html.hasAttribute("data-sidenav-user") || defaultConfig.sidenav.user,
        },
    };

    // Save merged config as defaults globally
    window.defaultConfig = structuredClone(htmlConfig);

    const validSkins = ['default', 'galaxy'];

    function isInvalidConfig(c) {
        if (!c || !c.topbar || !c.menu || !c.layout || !c.sidenav) return true;
        if (!validSkins.includes(c.skin)) return true;
        return false;
    }

    // Load from session if exists, reset only when structurally invalid
    let parsed = savedConfig ? JSON.parse(savedConfig) : null;
    if (isInvalidConfig(parsed)) {
        localStorage.removeItem(storageKey);
        parsed = null;
    }
    let config = parsed || htmlConfig;
    window.config = config;

    // Apply layout attributes immediately
    html.setAttribute("data-skin", config.skin);
    // 'system' = body light + topbar/sidenav dark (not OS-based)
    html.setAttribute("data-bs-theme", config.theme === 'system' ? 'light' : config.theme);
    html.setAttribute("data-menu-color", config.menu.color);
    html.setAttribute("data-topbar-color", config.topbar.color);
    html.setAttribute("data-layout-position", config.layout.position);
    html.setAttribute("dir", config.layout.dir || "ltr");
    html.classList.toggle("monochrome", config.monochrome);

    if (config.sidenav.size) {
        let size = config.sidenav.size;

        if (window.innerWidth <= 767) {
            size = "offcanvas";
        } else if (window.innerWidth <= 1140 && !["offcanvas"].includes(size)) {
            size = "condensed";
        }

        html.setAttribute("data-sidenav-size", size);

        if (config.sidenav.user === true) {
            html.setAttribute("data-sidenav-user", "true");
        } else {
            html.removeAttribute("data-sidenav-user");
        }
    }
})();
