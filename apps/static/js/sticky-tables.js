/**
 * sticky-tables.js — cabeçalho fixo das tabelas (project-wide)
 *
 * O CSS (visual-refresh.css) já deixa cada linha do <thead> sticky e cria o
 * scrollport no pai direto da tabela. O que ele NÃO consegue saber é a partir
 * de que altura a 2ª linha (filtros por coluna) deve grudar: isso depende da
 * altura real da 1ª, que varia por página, por idioma e por header que quebra
 * em duas linhas. Este script mede e publica os offsets como custom properties
 * (--vr-thead-row0/1/2…) na própria tabela.
 *
 * Sem animação de propósito: header fixo é estado, não transição — animar aqui
 * só atrasaria a leitura de uma tabela que o usuário está percorrendo.
 */
(function () {
    'use strict';

    var seen = typeof WeakSet === 'function' ? new WeakSet() : null;
    var ro = null;

    function sync(table) {
        var head = table.tHead;
        if (!head || !head.rows.length) return;
        var top = 0;
        for (var i = 0; i < head.rows.length; i++) {
            table.style.setProperty('--vr-thead-row' + i, top.toFixed(2) + 'px');
            // getBoundingClientRect pega a altura fracionária real; offsetHeight
            // arredonda e acumula um vão de 1px por linha do header.
            top += head.rows[i].getBoundingClientRect().height;
        }
    }

    function watch(table) {
        if (seen && seen.has(table)) { sync(table); return; }
        if (seen) seen.add(table);
        sync(table);
        // O header muda de altura ao esconder/mostrar colunas, ao traduzir a
        // página e ao redimensionar — o ResizeObserver cobre os três sem ficar
        // remedindo a tabela inteira a cada draw do DataTables.
        if (ro && table.tHead) ro.observe(table.tHead);
    }

    function scan() {
        var tables = document.querySelectorAll('.table-responsive table');
        for (var i = 0; i < tables.length; i++) watch(tables[i]);
    }

    function init() {
        if (typeof ResizeObserver === 'function') {
            ro = new ResizeObserver(function (entries) {
                for (var i = 0; i < entries.length; i++) {
                    var head = entries[i].target;
                    if (head && head.parentNode) sync(head.parentNode);
                }
            });
        }
        scan();

        // Tabelas montadas depois (fetch + render, DataTables, troca de aba).
        if (typeof MutationObserver === 'function') {
            var pending = null;
            new MutationObserver(function () {
                if (pending) return;
                pending = setTimeout(function () { pending = null; scan(); }, 200);
            }).observe(document.body, { childList: true, subtree: true });
        }
        window.addEventListener('resize', function () {
            var tables = document.querySelectorAll('.table-responsive table');
            for (var i = 0; i < tables.length; i++) sync(tables[i]);
        });
    }

    // Reexposto para quem monta tabela fora do DOM e precisa forçar a medição.
    window.vrSyncStickyTables = scan;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
}());
