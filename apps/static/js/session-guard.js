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
 * O mesmo embrulho diz a CÓPIA que falhou (§696, `X-OTC-Mirror-Failed`).
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

    // O espelho que FALHOU (§696): a origem gravou, mas a cópia para o Pending
    // Confirmation, a esteira (Confirmations Track) ou a Intrag não. O servidor
    // diz no cabeçalho `X-OTC-Mirror-Failed` (platform/mirrors.py) e o aviso
    // sai DEPOIS do Swal de sucesso da página — um Swal substitui o outro, e o
    // da página viria por cima deste.
    var MTXT = {
        en: { t: 'Saved — but a copy failed',
              m: 'The operation was saved, but it was NOT copied to: {alvos}. Operations: {refs}. Save it again or tell support (details in the log).',
              rt: 'Deleted — but a copy is still there',
              rm: 'The operation was deleted, but it was NOT removed from: {alvos}. Operations: {refs}. Delete it there or tell support (details in the log).',
              pc: 'Pending Confirmation', mc: 'Confirmations Track', intrag: 'Intrag' },
        br: { t: 'Gravado — mas uma cópia falhou',
              m: 'A operação foi gravada, mas NÃO foi copiada para: {alvos}. Operações: {refs}. Grave de novo ou avise o suporte (detalhes no log).',
              rt: 'Excluído — mas uma cópia ficou',
              rm: 'A operação foi excluída, mas NÃO saiu de: {alvos}. Operações: {refs}. Exclua lá ou avise o suporte (detalhes no log).',
              pc: 'Pending Confirmation', mc: 'Confirmations Track', intrag: 'Intrag' },
        es: { t: 'Guardado — pero una copia falló',
              m: 'La operación fue guardada, pero NO fue copiada a: {alvos}. Operaciones: {refs}. Guárdela de nuevo o avise al soporte (detalles en el log).',
              rt: 'Eliminado — pero una copia quedó',
              rm: 'La operación fue eliminada, pero NO salió de: {alvos}. Operaciones: {refs}. Elimínela allí o avise al soporte (detalles en el log).',
              pc: 'Pending Confirmation', mc: 'Confirmations Track', intrag: 'Intrag' }
    };
    function mtr() {
        var l = 'en';
        try { l = localStorage.getItem('__OTC_TRACKER_LANG__') || 'en'; } catch (e) {}
        return MTXT[l] || MTXT.en;
    }
    var pendentes = [], agendado = false;
    function mirrorFailed(raw) {
        var lst;
        try { lst = JSON.parse(raw); } catch (e) { return; }
        if (!Array.isArray(lst)) return;
        lst.forEach(function (x) {
            if (x && !pendentes.some(function (y) { return y.target === x.target && y.ref === x.ref && y.op === x.op; }))
                pendentes.push(x);
        });
        if (agendado) return;
        agendado = true;
        var tentativas = 0;
        (function mostra() {
            var aberto = window.Swal && Swal.isVisible && Swal.isVisible();
            if (aberto && tentativas++ < 40) { setTimeout(mostra, 500); return; }
            agendado = false;
            var x = mtr(), msgs = [];
            // A cópia que não foi gravada e a remoção que não saiu são frases
            // diferentes: "não foi copiada" para uma exclusão diria o contrário.
            [['', 't', 'm'], ['remove', 'rt', 'rm']].forEach(function (k) {
                var alvos = [], refs = [];
                pendentes.forEach(function (p) {
                    if ((p.op || '') !== k[0]) return;
                    var a = x[p.target] || p.target;
                    if (alvos.indexOf(a) < 0) alvos.push(a);
                    if (refs.indexOf(p.ref) < 0) refs.push(p.ref);
                });
                if (alvos.length) msgs.push({ t: x[k[1]], m: x[k[2]].replace('{alvos}', alvos.join(', '))
                                                              .replace('{refs}', refs.join(', ')) });
            });
            pendentes = [];
            if (!msgs.length) return;
            var msg = msgs.map(function (m) { return m.m; }).join('\n\n');
            if (window.Swal) Swal.fire({ icon: 'warning', title: msgs[0].t, text: msg });
            else if (window.console) console.warn(msg);
        })();
    }

    var orig = window.fetch;
    window.fetch = function (input) {
        var p = orig.apply(this, arguments);
        if (!isAppApi(input)) return p;
        return p.then(function (r) {
            if (r.status !== 401) {
                var mf = r.headers && r.headers.get && r.headers.get('X-OTC-Mirror-Failed');
                if (mf) setTimeout(function () { mirrorFailed(mf); }, 400);
                return r;
            }
            ended();
            return new Promise(function () {});
        });
    };
})();
