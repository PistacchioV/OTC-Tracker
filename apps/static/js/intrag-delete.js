/* Delete das telas de Intrag — a linha sai do ARQUIVO, não só da tabela.
 *
 * As quatro páginas (NDF, Option, Swap e DCE Option) apagavam com
 * `table.row().remove()` e mais nada: nenhuma requisição, nenhuma gravação. A
 * linha sumia da tela e voltava no F5, e o "This action cannot be undone" do
 * balão se desfazia com um refresh. Pior: o upsert do import preserva status,
 * maker, checker e Intrag ID da linha que já existe, então apagar tudo e
 * importar de novo devolvia as linhas com o status ANTIGO (Pending em vez de
 * New) — porque elas nunca tinham saído do arquivo.
 *
 * O helper é opt-in e a tela só remove a linha DEPOIS do sucesso: apagar antes
 * é o que criava a diferença entre o que se vê e o que está gravado, que é o
 * defeito inteiro.
 */
(function (w) {
  'use strict';

  // Texto montado em JS não passa pelo I18nManager (ele traduz os [data-lang]
  // uma vez, no load) — daí o mapa local, o padrão da casa.
  var TR = {
    en: { fail: 'Could not delete on the server. Nothing was removed.',
          partial: 'row(s) were not found on the server and stayed as they are.' },
    br: { fail: 'Não foi possível apagar no servidor. Nada foi removido.',
          partial: 'linha(s) não foram encontradas no servidor e continuam como estavam.' },
    es: { fail: 'No se pudo eliminar en el servidor. No se quitó nada.',
          partial: 'fila(s) no se encontraron en el servidor y quedaron como estaban.' }
  };
  function t(k) {
    var l;
    try { l = localStorage.getItem('__OTC_TRACKER_LANG__') || 'en'; } catch (e) { l = 'en'; }
    return (TR[l] || TR.en)[k] || TR.en[k];
  }

  /* otcIntragDelete('dce-opt', [{deal_id, trade_date}, …]) → Promise
   * Resolve com o payload do servidor; rejeita quando nada foi apagado. */
  w.otcIntragDelete = function (family, items) {
    return fetch('/api/intrag/' + encodeURIComponent(family) + '/delete', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items: items || [] })
    }).then(function (r) { return r.json().catch(function () { return null; }); })
      .then(function (d) {
        if (!d || !d.success) {
          throw new Error((d && d.message) || t('fail'));
        }
        return d;
      });
  };

  /* Avisa o que o servidor NÃO achou. Silencioso quando apagou tudo — um
   * balão a cada apagar bem-sucedido é ruído. */
  w.otcIntragDeleteWarn = function (d) {
    var faltou = (d && d.not_found) || [];
    if (!faltou.length || typeof Swal === 'undefined') return;
    Swal.fire({ icon: 'info', title: faltou.length + ' ' + t('partial'),
                text: faltou.join(', '), confirmButtonColor: '#6c757d' });
  };
})(window);
