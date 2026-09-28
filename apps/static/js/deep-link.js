/* A data que um LINK manda para a página (§567).
 *
 * O Intraday Monitor aponta cada pendência para a página dela JÁ filtrada na
 * data em questão — a operação de ontem abre a tela de New Deals no Trade Date
 * de ontem, a recon que não rodou abre a recon na data que ela teria rodado.
 * As páginas de New Deals já liam `?tradedate=` (o link do sino); as outras
 * abriam sempre em hoje. Aqui fica a leitura UMA vez: `?tradedate=` ou
 * `?date=`, sempre ISO (AAAA-MM-DD), e a página usa "a data do link, senão o
 * padrão de sempre". Valor malformado é ignorado — a página abre como abria.
 */
(function () {
    'use strict';
    var iso = '';
    try {
        var q = new URLSearchParams(window.location.search);
        iso = q.get('tradedate') || q.get('date') || '';
    } catch (e) { iso = ''; }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) iso = '';
    window.otcLinkIso = function () { return iso; };
    window.otcLinkDmy = function () {
        if (!iso) return '';
        var p = iso.split('-');
        return p[2] + '/' + p[1] + '/' + p[0];
    };
})();
