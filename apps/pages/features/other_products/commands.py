# -*- coding: utf-8 -*-
"""Other Products — escritas. Hoje: a edição e o envio dos fatores do Swap VCP
(§452). O arquivo é o MESMO do Accrual (`pu_fator`, o Registro de
Atualização de PU/Fator): uma linha por perna VCP por visão, em
`ACCRUAL_<VIEW>-<LOB>.txt` no Batch Conecta."""
from datetime import datetime

from apps.pages.features.other_products import domain, queries
from apps.pages.features.other_products.infra import persistence
from apps.pages.platform import pu_fator as _pf


def _R():
    from apps.pages import routes
    return routes


def vcp_factors_edit(ref, contrato, campos, sid=''):
    """Grava o que a mesa editou (campo a campo; vazio APAGA a edição e o
    calculado volta). A linha volta para `New` com o maker: quem edita não é
    quem envia."""
    key = persistence._chave(contrato)
    if not key:
        return {'success': False, 'error': 'Contract missing.'}, 400
    limpos = {}
    for k in domain.CAMPOS_EDITAVEIS:
        if k not in campos:
            continue
        v = campos.get(k)
        if v in (None, ''):
            continue
        if k == 'tipo':
            limpos[k] = str(v).strip()
        else:
            n = domain.num(v)
            if n is None:
                return {'success': False, 'error': '{}: "{}" is not a number.'.format(k, v)}, 400
            limpos[k] = n

    def mudar(data):
        atual = data.get(key) or {}
        atual.update({'overrides': limpos, 'status': 'New', 'maker': sid, 'checker': '',
                      'updated': persistence.stamp()})
        data[key] = atual

    persistence._vcp_factors_update(ref, mudar)
    linha = next((f for f in queries.vcp_factor_rows(ref) if f['contrato'].upper() == key), None)
    return {'success': True, 'row': linha}, 200


def vcp_send(ref, contratos, sid=''):
    """Gera o arquivo de PU/Fator para os contratos pedidos (um lote), marca
    `Sent` e devolve os arquivos. Recusa o LOTE inteiro quando alguma linha
    não pode ir — meio lote na B3 é pior que nenhum."""
    pedidos = [persistence._chave(c) for c in (contratos or []) if persistence._chave(c)]
    if not pedidos:
        return {'success': False, 'error': 'Select at least one contract.'}, 400
    linhas = {f['contrato'].upper(): f for f in queries.vcp_factor_rows(ref)}
    problemas, aceitas = [], []
    for key in pedidos:
        f = linhas.get(key)
        if not f:
            problemas.append('{}: not on the page'.format(key))
            continue
        if f.get('maker') and f['maker'] == sid:
            problemas.append('{}: a different user must send a row you edited'.format(key))
            continue
        ruins = domain.problemas_para_envio(f)
        if ruins:
            problemas.append('{}: {}'.format(key, ', '.join(ruins)))
            continue
        aceitas.append(f)
    if problemas:
        return {'success': False, 'error': 'blocked', 'problems': problemas}, 400
    today = datetime.now().strftime('%Y%m%d')
    por_lob = {}
    for f in aceitas:
        row = domain.linha_para_arquivo(f['contrato'], f['conta_p'], f['idx_p'], f['conta_c'],
                                        f['idx_c'], f['fator_p'] if f['vcp_p'] else None,
                                        f['fator_c'] if f['vcp_c'] else None)
        for rec in _pf.acc_swap_records(row, today):
            por_lob.setdefault(f['lob'], {}).setdefault(rec['view'], []).append(rec['line'])
    gerados = []
    for lob, by_view in por_lob.items():
        tag = _pf.LOB_TAG.get(lob, str(lob).upper())
        gerados.extend(_pf.write_view_files(by_view, tag, today,
                                            evidence_dir=_pf.accrual_source_dir(today)))
    if not gerados:
        return {'success': False, 'error': 'No VCP record to send.'}, 400
    nomes = [g['filename'] for g in gerados]

    def mudar(data):
        for f in aceitas:
            atual = data.get(f['contrato'].upper()) or {}
            atual.update({'status': 'Sent', 'checker': sid, 'files': nomes,
                          'sent_at': persistence.stamp()})
            atual.setdefault('overrides', {})
            data[f['contrato'].upper()] = atual

    persistence._vcp_factors_update(ref, mudar)
    total = sum(g['count'] for g in gerados)
    _R()._create_notification(sid, '', 'Accrual Sent', 'Swap VCP',
                              '{} contract(s) · {} file(s), {} line(s)'.format(len(aceitas), len(gerados), total)
                              + _R()._nd_token(ref.strftime('%Y%m%d')))
    return {'success': True, 'files': [{'filename': g['filename'], 'view': g['view'], 'count': g['count']}
                                       for g in gerados],
            'total': total, 'contracts': [f['contrato'] for f in aceitas]}, 200
