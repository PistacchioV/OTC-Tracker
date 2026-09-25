/*
 * session-guard.js — a sessão que caiu no meio da página (§557).
 *
 * Desde o §552 a sessão só cai se o IP mudar (VPN que reconecta, troca de
 * rede). A página continua aberta e o clique seguinte bate num /api/* que
 * responde 401 — e cada tela mostrava o texto cru do servidor ("Not
 * authenticated"), sem dizer o que houve nem o que fazer. Aqui o fetch da
 * página é embrulhado UMA vez: 401 de um /api/* do próprio app vira o aviso
 * traduzido e a volta ao login. A promessa da página fica pendente de
 * propósito, para o Swal de erro dela não cobrir este.
 *
 * Só é incluído em página renderizada com sessão (base.html), e carrega no
 * <head>: os fetches da página rodam antes do footer.
 */
(function () {
    'use strict';
    if (!window.fetch || window.__otcSessionGuard) return;
    window.__otcSessionGuard = true;

    var TXT = {
        en: { t: 'Session ended', m: 'Your session was closed (your network address changed). Please sign in again.', b: 'Sign in' },
        br: { t: 'Sessão encerrada', m: 'Sua sessão foi encerrada (o endereço de rede mudou). Entre novamente.', b: 'Entrar' },
        es: { t: 'Sesión finalizada', m: 'Su sesión fue cerrada (la dirección de red cambió). Inicie sesión nuevamente.', b: 'Iniciar sesión' }
    };
    function tr() {
        var l = 'en';
        try { l = localStorage.getItem('__OTC_TRACKER_LANG__') || 'en'; } catch (e) {}
        return TXT[l] || TXT.en;
    }

    var shown = false;
    function toLogin() { window.location.href = '/auth-2-sign-in'; }
    function ended() {
        if (shown) return;
        shown = true;
        var x = tr();
        if (window.Swal) {
            Swal.fire({ icon: 'warning', title: x.t, text: x.m, confirmButtonText: x.b,
                        allowOutsideClick: false }).then(toLogin);
        } else {
            toLogin();
        }
    }

    function isAppApi(input) {
        var url = typeof input === 'string' ? input : (input && input.url) || '';
        try {
            var u = new URL(url, window.location.href);
            return u.origin === window.location.origin && u.pathname.indexOf('/api/') === 0;
        } catch (e) { return false; }
    }

    var orig = window.fetch;
    window.fetch = function (input) {
        var p = orig.apply(this, arguments);
        if (!isAppApi(input)) return p;
        return p.then(function (r) {
            if (r.status !== 401) return r;
            ended();
            return new Promise(function () {});
        });
    };
})();
