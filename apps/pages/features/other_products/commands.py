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


def vcp_send(ref, contratos, sid='', nome=''):
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
    # UM arquivo (VCP_CLIENT.TXT), não um por livro: o nome pedido pela mesa
    # não carrega a LOB, e dois livros no mesmo nome virariam "VCP_CLIENT (1)"
    # sem nada dizendo qual é qual. A separação que resta é por VISÃO, que é de
    # participante diferente (`vcp_file_name`).
    # A chave é o ARQUIVO: a visão mais o tipo do swap. Contra cliente tudo vai
    # no VCP_CLIENT.TXT; no intragrupo (BANCO x LAWTON) cada participante manda
    # o seu — VCP_BANCO.TXT e VCP_LAWTON.TXT.
    por_arquivo = {}
    for f in aceitas:
        intra = _pf.is_intragroup(f['conta_p'], f['conta_c'])
        row = domain.linha_para_arquivo(f['contrato'], f['conta_p'], f['idx_p'], f['conta_c'],
                                        f['idx_c'], f['fator_p'] if f['vcp_p'] else None,
                                        f['fator_c'] if f['vcp_c'] else None)
        for rec in _pf.acc_swap_records(row, today):
            por_arquivo.setdefault((rec['view'], intra), []).append(rec['line'])
    gerados = []
    for (view, intra), linhas in sorted(por_arquivo.items()):
        gerados.extend(_pf.write_view_files(
            {view: linhas}, '', today, evidence_dir=_pf.accrual_source_dir(today),
            name_fn=lambda v, _t, _i=intra: _pf.vcp_file_name(v, _i)))
    if not gerados:
        return {'success': False, 'error': 'No VCP record to send.'}, 400
    nomes = [g['filename'] for g in gerados]
    plural = lambda n, s: '{} {}{}'.format(n, s, '' if n == 1 else 's')   # noqa: E731

    def mudar(data):
        for f in aceitas:
            atual = data.get(f['contrato'].upper()) or {}
            atual.update({'status': 'Sent', 'checker': sid, 'files': nomes,
                          'sent_at': persistence.stamp()})
            atual.setdefault('overrides', {})
            data[f['contrato'].upper()] = atual

    persistence._vcp_factors_update(ref, mudar)
    total = sum(g['count'] for g in gerados)
    # O aviso diz o que a mesa precisa conferir: QUAIS arquivos saíram (o nome
    # é a diferença entre o do cliente e os do intragrupo) e quantos contratos.
    # A ação tem rótulo próprio — 'Accrual Sent' mandava para a página do
    # Accrual quem clicasse, e o arquivo não é o de lá.
    _R()._create_notification(sid, nome, 'VCP Factors Sent', 'Swap VCP',
                              '{} · {} · {}'.format(', '.join(nomes),
                                                    plural(len(aceitas), 'contract'),
                                                    plural(total, 'line'))
                              + _R()._nd_token(ref.strftime('%Y%m%d')))
    return {'success': True, 'files': [{'filename': g['filename'], 'view': g['view'], 'count': g['count']}
                                       for g in gerados],
            'total': total, 'contracts': [f['contrato'] for f in aceitas]}, 200
