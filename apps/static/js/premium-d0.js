/**
 * Prêmio D0 — faixa FIXA acima da grade das páginas de opção (Opt FXO e Opt
 * Commodities) com as operações cujo prêmio (Spot Date) é pago HOJE.
 *
 * Era um Swal disparado no fim do Import da própria página: o deal que entrava
 * pelo box scan (servidor, a cada 30 min) ou pelo import de outra pessoa nunca
 * passava por ali, e o prêmio do dia ficava calado. Aqui a conta sai da GRADE,
 * a cada draw — qualquer que seja o caminho por onde a operação entrou — e a
 * faixa fica na tela enquanto houver prêmio hoje, sem depender de um clique.
 *
 *   otcPremiumD0(table, { spot: 26, deal: 3, client: 10 })
 *
 * `spot`/`deal`/`client` são os índices das colunas no array da linha (os das
 * páginas diferem). O botão da faixa filtra a grade pelo dia de hoje na coluna
 * Spot Date; o segundo clique desfaz.
 */
(function () {
    'use strict';

    function tr(k, fb) { return (typeof window.t === 'function') ? window.t(k, fb) : fb; }
    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }
    function txt(v) { return $('<div>').html(v == null ? '' : String(v)).text().trim(); }
    function parse(s) {
        s = txt(s);
        var br = s.match(/^(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{4})$/);
        if (br) return new Date(+br[3], +br[2] - 1, +br[1]);
        var iso = s.match(/^(\d{4})[\/\-.](\d{1,2})[\/\-.](\d{1,2})$/);
        if (iso) return new Date(+iso[1], +iso[2] - 1, +iso[3]);
        return null;
    }
    function dmy(d) {
        return ('0' + d.getDate()).slice(-2) + '/' + ('0' + (d.getMonth() + 1)).slice(-2) + '/' + d.getFullYear();
    }

    window.otcPremiumD0 = function (table, cols) {
        if (!table || !cols) return;
        var $bar = $('<div class="otc-premium-d0" role="status" hidden>' +
                     '<i class="ti ti-alarm"></i><span class="otc-premium-d0__msg"></span>' +
                     '<button type="button" class="btn btn-sm otc-premium-d0__btn"></button></div>');
        $(table.table().container()).before($bar);
        var filtrando = false;

        function sync() {
            var hoje = new Date(); hoje.setHours(0, 0, 0, 0);
            var deals = [];
            // TODAS as linhas, não a busca aplicada: a faixa diz o que vence
            // hoje no dia, e não só o que o filtro da tela deixou visível.
            table.rows({ search: 'none' }).every(function () {
                var d = this.data();
                var sd = parse(d[cols.spot]);
                if (sd && sd.getTime() === hoje.getTime()) {
                    deals.push(txt(d[cols.deal]) + (cols.client != null && txt(d[cols.client])
                               ? ' · ' + txt(d[cols.client]) : ''));
                }
            });
            if (!deals.length && !filtrando) { $bar.prop('hidden', true); return; }
            var msg = tr('swal-premium-today-text', '{n} operation(s) have a premium payment (Spot Date) due today.')
                        .replace('{n}', deals.length);
            var lista = deals.slice(0, 6).join(', ') + (deals.length > 6 ? ' …' : '');
            $bar.find('.otc-premium-d0__msg').html('<strong>' + esc(tr('swal-premium-today-title', 'Premium Payment Due Today')) +
                '</strong> — ' + esc(msg) + (lista ? ' <span class="otc-premium-d0__list">' + esc(lista) + '</span>' : ''));
            $bar.find('.otc-premium-d0__btn').text(filtrando ? tr('nd-premium-d0-all', 'Show all')
                                                             : tr('nd-premium-d0-show', 'Show them'));
            $bar.prop('hidden', false);
        }

        $bar.on('click', '.otc-premium-d0__btn', function () {
            filtrando = !filtrando;
            var hoje = new Date(); hoje.setHours(0, 0, 0, 0);
            table.column(cols.spot).search(filtrando ? '^' + dmy(hoje).replace(/\//g, '\\/') + '$' : '', true, false).draw();
        });
        table.on('draw.otcPremiumD0', sync);
        sync();
    };
})();
