/* Campo de data — o padrão de TODO datepicker do app (mesa, 22/10/2026).
 *
 * Carregado pelo `partials/footer-scripts.html`, em toda página e ANTES dos
 * scripts dela. Vale para os dois calendários da casa — o flatpickr (direto ou
 * pelo `otcDateField`) e o daterangepicker de data única —, sem a página
 * escrever nada:
 *   · clicar no campo SELECIONA a data inteira: o primeiro dígito já começa a
 *     data nova;
 *   · digita-se só os NÚMEROS e as barras se escrevem sozinhas (`22082026` →
 *     22/08/2026);
 *   · o calendário ACOMPANHA: com dia e mês ele vai ao mês, e com a data
 *     inteira e real ele a escolhe na hora (o código em volta reage como a um
 *     clique no calendário);
 *   · texto pela metade ou data impossível (31/02) volta à última data válida
 *     ao sair do campo — o parse frouxo dos dois plugins leria outra data, sem
 *     erro nenhum;
 *   · o botão TODAY no pé do calendário escolhe a data de hoje.
 *
 * Antes isso morava em dois lugares (a máscara do flatpickr no
 * `export-advanced.js`, a do daterangepicker na Quotes, §508) e só valia onde
 * alguém o tinha ligado à mão. Aqui o picker é reconhecido sozinho: o
 * flatpickr na criação (o `flatpickr()` global é embrulhado) e os dois numa
 * varredura depois da carga e na primeira interação com o campo. O
 * calendário que só aceita data em outro formato (ou com hora) ganha o TODAY
 * e a seleção no clique, sem a máscara de dd/mm/aaaa.
 */
(function () {
    'use strict';
    if (window.otcDateStd) return;

    var TODAY_T = { en: 'Today', br: 'Hoje', es: 'Hoy' };
    function lang() {
        try { return localStorage.getItem('__OTC_TRACKER_LANG__') || 'en'; } catch (e) { return 'en'; }
    }
    function todayLabel() { return TODAY_T[lang()] || TODAY_T.en; }

    function dataReal(dia, mes, ano) {
        var dt = new Date(ano, mes - 1, dia);
        return ano >= 1900 && dt.getFullYear() === ano && dt.getMonth() === mes - 1 && dt.getDate() === dia;
    }
    // só os dígitos, até oito, com as barras no lugar
    function digits(v) { return String(v || '').replace(/\D/g, '').slice(0, 8); }
    function comBarras(d) {
        return d.slice(0, 2) + (d.length > 2 ? '/' + d.slice(2, 4) : '') + (d.length > 4 ? '/' + d.slice(4) : '');
    }
    function selecionaTudo(inp) {
        function selAll() { setTimeout(function () { try { inp.select(); } catch (e) {} }, 0); }
        inp.addEventListener('focus', selAll);
        inp.addEventListener('click', selAll);
    }
    function rodape(onClick) {
        var foot = document.createElement('div');
        foot.className = 'otc-dp-foot';
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'otc-dp-today';
        b.textContent = todayLabel();
        // `mousedown` sem default: o foco fica no campo, e o calendário não
        // fecha antes do clique (os dois fecham no mousedown fora deles)
        b.addEventListener('mousedown', function (e) { e.preventDefault(); });
        b.addEventListener('click', function (e) { e.preventDefault(); onClick(); });
        foot.appendChild(b);
        return foot;
    }

    /* ══════ flatpickr ═════════════════════════════════════════════════════ */
    /* A MÁSCARA (mesa, 22/09/2026). O campo já era editável (`allowInput`), mas
       quem digitava tinha de pôr as duas barras à mão, e um dígito a mais ou
       uma barra esquecida dava um texto que o flatpickr lê no seu parse
       frouxo: `2208/2026` vira uma data QUALQUER, sem erro nenhum.

       Completada, a data é ESCRITA no picker na hora (`setDate`): o valor que o
       código em volta lê é o do input original — em ISO, no `otcDateField` —,
       e ele só nasceria no blur; clicar direto no Run com a data digitada
       exportaria o intervalo anterior. */
    function dateMask(inp, fp) {
        if (!inp || inp._otcMask) return;
        inp._otcMask = 1;
        inp.setAttribute('inputmode', 'numeric');
        inp.setAttribute('maxlength', '10');
        // O clique SELECIONA a data inteira (mesa, 20/10/2026 — a regra da
        // Quotes, §508): o primeiro dígito digitado já começa a data nova, sem
        // apagar a anterior caractere por caractere.
        function selAll() { try { inp.select(); } catch (e) {} }
        inp.addEventListener('focus', selAll);
        inp.addEventListener('click', selAll);
        // O `setDate` DISPARA um `input` no campo do picker. No `otcDateField`
        // esse campo é o original escondido; no flatpickr direto é ESTE, e o
        // evento voltaria aqui — um laço sem fim (o "Maximum call stack" do
        // primeiro teste). A trava segura a volta, e a data que já é a
        // escolhida não é escrita de novo (a página recarregaria duas vezes).
        var escrevendo = false;
        function escolhe(txt) {
            var atual = fp.selectedDates.length ? fp.formatDate(fp.selectedDates[0], 'd/m/Y') : '';
            if (atual === txt) return;
            escrevendo = true;
            try { fp.setDate(txt, true, 'd/m/Y'); } finally { escrevendo = false; }
        }
        inp.addEventListener('input', function () {
            if (escrevendo) return;
            var d = digits(inp.value);
            var txt = comBarras(d);
            if (txt !== inp.value) {
                inp.value = txt;
                try { inp.setSelectionRange(txt.length, txt.length); } catch (e) {}
            }
            if (!fp) return;
            var dia = +d.slice(0, 2), mes = +d.slice(2, 4), ano = +d.slice(4);
            // Só a data INTEIRA e REAL é escolha; o que está pela metade é
            // digitação em curso, e escrevê-la no picker faria o campo pular para
            // um dia que ninguém pediu. 31/02 não é escrita: o parse do flatpickr
            // a levaria a 03/03 sem erro nenhum.
            if (d.length === 8 && dataReal(dia, mes, ano)) { escolhe(txt); return; }
            // Com dia e mês o calendário ACOMPANHA: vai para o mês digitado (no
            // ano digitado, quando ele já está inteiro), sem escolher nada.
            if (d.length >= 4 && mes >= 1 && mes <= 12) {
                fp.jumpToDate(new Date(d.length === 8 ? ano : fp.currentYear, mes - 1, 1));
            }
        });
        // Ao SAIR do campo (ou no Enter), texto pela metade ou data impossível
        // volta à última data válida — o flatpickr relê o texto nesse momento
        // pelo parse frouxo, e `31/02/2026` virava 03/03 calado. Em CAPTURA,
        // para rodar antes do listener dele no mesmo campo. Campo vazio é a
        // pessoa apagando a data, e fica vazio.
        function restaura() {
            if (!fp) return;
            var d = String(inp.value || '').replace(/\D/g, '');
            if (!d || (d.length === 8 && dataReal(+d.slice(0, 2), +d.slice(2, 4), +d.slice(4)))) return;
            inp.value = fp.selectedDates.length ? fp.formatDate(fp.selectedDates[0], 'd/m/Y') : '';
        }
        inp.addEventListener('blur', restaura, true);
        inp.addEventListener('keydown', function (e) { if (e.key === 'Enter') restaura(); }, true);
        // o clique FORA relê o texto antes do blur (o `mousedown` do flatpickr no
        // document): na janela, em captura, a restauração chega antes dele
        function foraDoCampo(e) {
            if (document.activeElement !== inp || e.target === inp) return;
            if (fp && fp.calendarContainer && fp.calendarContainer.contains(e.target)) return;
            restaura();
        }
        window.addEventListener('mousedown', foraDoCampo, true);
        window.addEventListener('touchstart', foraDoCampo, true);
    }

    // o campo que se VÊ: o altInput, quando há, senão o próprio input
    function fpVisivel(fp) { return fp.altInput || fp._input || fp.input; }
    // a máscara de dd/mm/aaaa só cabe no calendário de UMA data, sem hora, que
    // mostra d/m/Y — o resto ganha o TODAY e a seleção no clique
    function fpMascaravel(fp) {
        var c = fp.config || {};
        var fmt = c.altInput ? c.altFormat : c.dateFormat;
        return c.mode === 'single' && !c.enableTime && !c.noCalendar && fmt === 'd/m/Y';
    }
    function enhanceFp(fp) {
        if (!fp || fp._otcStd || !fp.config || fp.config.inline) return;
        fp._otcStd = 1;
        var inp = fpVisivel(fp);
        if (inp && fpMascaravel(fp)) {
            // digitar exige o campo editável; a página que o deixou readonly
            // (`allowInput: false`) só escolhia pelo calendário
            if (!fp.config.allowInput) {
                fp.config.allowInput = true;
                inp.removeAttribute('readonly');
            }
            dateMask(inp, fp);
        } else if (inp && !inp._otcMask) {
            selecionaTudo(inp);
        }
        if (fp.calendarContainer && !fp.config.noCalendar && !fp.calendarContainer.querySelector('.otc-dp-foot')) {
            fp.calendarContainer.appendChild(rodape(function () {
                var hoje = new Date();
                hoje.setHours(0, 0, 0, 0);
                fp.setDate(fp.config.mode === 'range' ? [hoje, hoje] : hoje, true);
                fp.close();
            }));
        }
    }

    /* ══════ daterangepicker (data única) ══════════════════════════════════ */
    /* O mesmo, sobre o daterangepicker (a regra da Quotes, §508): o campo deixa
       de ser readonly, a máscara põe as barras, dia e mês levam o calendário ao
       mês, e a data inteira é escolhida na hora — `clickApply`, o mesmo caminho
       de um clique no dia, então o callback e o `apply.daterangepicker` da
       página rodam como sempre. O `keyup` do plugin relê o texto com parse
       FROUXO e desfaria isso no meio da digitação (`22/0` vira janeiro): sai.
       Texto pela metade volta à data escolhida ao fechar, que é quando o
       próprio plugin reescreve o campo. */
    function drpOf(inp) {
        var $ = window.jQuery;
        if (!$ || !$.fn || !$.fn.daterangepicker || !inp) return null;
        try { return $(inp).data('daterangepicker') || null; } catch (e) { return null; }
    }
    function drpMascaravel(drp) {
        return drp.singleDatePicker && !drp.timePicker && drp.locale && drp.locale.format === 'DD/MM/YYYY';
    }
    function enhanceDrp(inp, drp) {
        if (!inp || !drp || inp._otcStd) return;
        inp._otcStd = 1;
        var m = window.moment;
        if (drpMascaravel(drp) && m) {
            inp.removeAttribute('readonly');
            inp.setAttribute('inputmode', 'numeric');
            inp.setAttribute('maxlength', '10');
            window.jQuery(inp).off('keyup.daterangepicker');
            inp.addEventListener('input', function () {
                var d = digits(inp.value);
                var txt = comBarras(d);
                if (txt !== inp.value) {
                    inp.value = txt;
                    try { inp.setSelectionRange(txt.length, txt.length); } catch (e) {}
                }
                var dia = +d.slice(0, 2), mes = +d.slice(2, 4), ano = +d.slice(4);
                if (d.length === 8 && dataReal(dia, mes, ano)) {
                    var dt = m(txt, 'DD/MM/YYYY', true);
                    // aberto ANTES de mudar a data: o `hide` do apply só chama o
                    // callback da página quando a data difere da que havia no `show`
                    if (!drp.isShowing) drp.show();
                    drp.setStartDate(dt);
                    drp.setEndDate(dt);
                    drp.updateView();
                    drp.clickApply();
                    return;
                }
                if (d.length >= 4 && mes >= 1 && mes <= 12 && drp.isShowing) {
                    var a = d.length === 8 ? ano : drp.leftCalendar.month.year();
                    drp.leftCalendar.month = m([a, mes - 1, 1]);
                    if (drp.rightCalendar) drp.rightCalendar.month = drp.leftCalendar.month.clone().add(1, 'month');
                    drp.updateCalendars();
                }
            });
        }
        selecionaTudo(inp);
        if (drp.container && !drp.container.find('.otc-dp-foot').length) {
            drp.container.append(rodape(function () {
                var hoje = m ? m().startOf('day') : null;
                if (!hoje) return;
                drp.setStartDate(hoje);
                drp.setEndDate(hoje);
                drp.updateView();
                drp.clickApply();
            }));
            if (drp.isShowing) drp.move();
        }
    }

    /* ══════ reconhecimento ════════════════════════════════════════════════ */
    // o flatpickr do campo: o próprio input, ou o original ao lado do altInput
    function fpOf(inp) {
        if (!inp) return null;
        if (inp._flatpickr) return inp._flatpickr;
        var prev = inp.previousElementSibling;
        if (prev && prev._flatpickr && prev._flatpickr.altInput === inp) return prev._flatpickr;
        return null;
    }
    function enhanceInput(inp) {
        if (!inp || inp.tagName !== 'INPUT') return;
        var fp = fpOf(inp);
        if (fp) { enhanceFp(fp); return; }
        var drp = drpOf(inp);
        if (drp) enhanceDrp(inp, drp);
    }
    function varre() {
        Array.prototype.forEach.call(document.querySelectorAll('input'), enhanceInput);
    }

    // o flatpickr na CRIAÇÃO: embrulha o global e o do elemento
    function embrulhaFlatpickr() {
        var orig = window.flatpickr;
        if (typeof orig !== 'function' || orig._otcStd) return;
        function cada(r) {
            if (!r) return;
            if (Array.isArray(r)) r.forEach(enhanceFp); else enhanceFp(r);
        }
        var embrulhado = function () {
            var r = orig.apply(this, arguments);
            try { cada(r); } catch (e) { /* o picker segue funcionando sem o padrão */ }
            return r;
        };
        for (var k in orig) { if (Object.prototype.hasOwnProperty.call(orig, k)) embrulhado[k] = orig[k]; }
        embrulhado._otcStd = 1;
        window.flatpickr = embrulhado;
        if (window.HTMLElement && HTMLElement.prototype.flatpickr) {
            var el = HTMLElement.prototype.flatpickr;
            HTMLElement.prototype.flatpickr = function () {
                var r = el.apply(this, arguments);
                try { cada(r); } catch (e) {}
                return r;
            };
        }
    }
    embrulhaFlatpickr();

    // a primeira interação com o campo (em CAPTURA: antes do picker abrir)
    ['focusin', 'mousedown', 'click'].forEach(function (ev) {
        document.addEventListener(ev, function (e) { enhanceInput(e.target); }, true);
    });
    // e a varredura depois da carga (o picker aberto pelo botão do ícone nunca
    // passa pelo campo), mais o `show` do daterangepicker quando o jQuery chega
    function depoisDaCarga() {
        // a tela que carrega o vendors.min.js DE NOVO refaz o `flatpickr` global
        // sem o embrulho: volta a embrulhar (os já criados vêm pela varredura)
        embrulhaFlatpickr();
        varre();
        var $ = window.jQuery;
        if ($ && !$._otcDateStd) {
            $._otcDateStd = 1;
            $(document).on('show.daterangepicker', function (e, picker) {
                if (picker && picker.element) enhanceDrp(picker.element[0], picker);
            });
        }
    }
    document.addEventListener('DOMContentLoaded', function () { setTimeout(depoisDaCarga, 0); });
    window.addEventListener('load', function () {
        depoisDaCarga();
        setTimeout(depoisDaCarga, 1500);
    });

    window.otcDateMask = dateMask;
    window.otcDateStd = { enhance: enhanceInput, scan: varre, mask: dateMask };
})();
