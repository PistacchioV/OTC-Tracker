# -*- coding: utf-8 -*-
"""NDF Other Publisher — o Email Validation: a taxa de paridade das linhas
contra INSTITUIÇÃO FINANCEIRA vai por e-mail para outro integrante do time
conferir (tem de casar na B3); com o Lawton numa das pontas, o TAXA_LAWTON
vai em anexo."""
from apps.pages.features.ndf_other_publisher import queries
from apps.pages.platform import email_validation as _ev


def _R():
    from apps.pages import routes
    return routes


def _lawton_attachment(linhas):
    """[(nome, bytes)] — o TAXA_LAWTON.txt das linhas contra o Lawton, pelo
    MESMO gerador do Send (`_ndfop_conecta_fields(swap=True)`), em memória:
    pedir validação não é enviar, e nada vai para o Batch Conecta.

    Só o Lawton: é a única visão espelhada que esta página sabe gerar. Linha
    com outro fundo vai na tabela e volta em `fund_without_file`."""
    R = _R()
    i_c = R._NDFOP_COLUMNS.index('CONTA CONTRAPARTE')
    lines = [''.join(v for _, v in R._ndfop_conecta_fields(cells, swap=True))
             for cells in linhas if R._ndfop_acct8(cells[i_c]) == R._NDFOP_LAWTON]
    if not lines:
        return []
    return [('TAXA_LAWTON.txt',
             '\n'.join([R._ndfop_conecta_header('INTRAGLAWTONFDO')] + lines).encode('utf-8'))]


def email_validation(ref, ids, sid='', nome=''):
    """Sem ids pedidos vale a página inteira. Linha de cliente fica de fora
    (`skipped`); linha de IF sem TX PARIDADE utilizável recusa o pedido, como
    no Send. Não muda status: quem envia continua sendo o Send."""
    R = _R()
    cols = R._NDFOP_COLUMNS
    n = len(cols)
    rows = R._ndfop_collect(ref)['rows']
    cenarios = queries.validation_by_id(rows)
    by_id = {str(r[n + 3]): r[:n] for r in rows}
    pedidos = [str(i or '').strip() for i in (ids or []) if str(i or '').strip()]
    alvo = [i for i in pedidos if i in by_id] if pedidos else list(by_id)
    if not alvo:
        return {'success': False, 'code': 'no_rows', 'params': {},
                'error': 'No row to validate.'}, 400
    elegiveis = [i for i in alvo if cenarios[i]['scenario']]
    if not elegiveis:
        return {'success': False, 'code': 'no_if_rows', 'params': {'n': len(alvo)},
                'error': 'None of the {} row(s) is against a financial institution.'.format(len(alvo))}, 400
    i_stk = cols.index('TX PARIDADE')
    ruins = [i for i in elegiveis if not R._ndfop_rate12(by_id[i][i_stk])]
    if ruins:
        return {'success': False, 'code': 'rate_missing', 'params': {'ids': ', '.join(ruins)},
                'error': 'TX PARIDADE missing/invalid: ' + ', '.join(ruins)}, 400
    com_fundo = [i for i in elegiveis if cenarios[i]['scenario'] == _ev.SCENARIO_IF_FUND]
    anexos = _lawton_attachment([by_id[i] for i in com_fundo])
    i_c = cols.index('CONTA CONTRAPARTE')
    sem_arquivo = [i for i in com_fundo if R._ndfop_acct8(by_id[i][i_c]) != R._NDFOP_LAWTON]
    _ev.dispatch('NDF Other Publisher', 'parity rate (TX PARIDADE)', ref, cols,
                 [{'cells': by_id[i], 'scenario': cenarios[i]} for i in elegiveis],
                 anexos, requester=nome, tag='ndf-other-publisher')
    nomes = [a for a, _ in anexos]
    R._create_notification(sid, nome, 'Validation Requested', R._NOTIF_DS_OTHERPUB,
                           '{} row(s){} ({})'.format(len(elegiveis),
                                                     ' · ' + ', '.join(nomes) if nomes else '',
                                                     ref.strftime('%Y-%m-%d')))
    return {'success': True, 'mail': 'queued', 'ids': elegiveis, 'with_fund': com_fundo,
            'attached': nomes, 'skipped': len(alvo) - len(elegiveis),
            'warnings': ([{'code': 'fund_without_file', 'params': {'ids': ', '.join(sem_arquivo)},
                           'text': 'No fund view file for: ' + ', '.join(sem_arquivo)}]
                         if sem_arquivo else [])}, 200
