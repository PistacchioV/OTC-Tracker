# -*- coding: utf-8 -*-
"""Other Products — escritas. Hoje: a edição e o envio dos fatores do Swap VCP
(§452). O arquivo é o MESMO do Accrual (`pu_fator`, o Registro de
Atualização de PU/Fator): uma linha por perna VCP por visão, em
`ACCRUAL_<VIEW>-<LOB>.txt` no Batch Conecta."""
from datetime import datetime

from apps.pages.features.other_products import domain, queries
from apps.pages.features.other_products.infra import persistence
from apps.pages.platform import email_validation as _ev
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


# As colunas da tabela do e-mail: o que o validador confere (fatores e a prova
# real da linha) mais as duas contas, que é por onde se vê de quem é cada ponta.
_VALIDATION_HEADERS = ['Internal ID', 'Contract', 'Counterparty', 'Parte Acct', 'Cparty Acct', 'VBR',
                       'Index Parte', 'Factor Parte', 'Index Cparty', 'Factor Cparty',
                       'Internal Settl.', 'VCP Settl.', 'Difference']


def _n2(v):
    return '' if v is None else '{:,.2f}'.format(float(v))


def _f8(v):
    return '' if v is None else '{:.8f}'.format(float(v))


def _validation_cells(f):
    return [f.get('internal_id', ''), f['contrato'], f.get('contraparte', ''), f.get('conta_p', ''),
            f.get('conta_c', ''), _n2(f.get('vbr')),
            f.get('idx_p', ''), _f8(f['fator_p']) if f.get('vcp_p') else '',
            f.get('idx_c', ''), _f8(f['fator_c']) if f.get('vcp_c') else '',
            _n2(f.get('interno')), _n2(f.get('vcp_liq')), _n2(f.get('diferenca'))]


def _fund_attachments(linhas, today):
    """[(nome, bytes)] — o arquivo de PU/Fator da visão de cada FUNDO, pelo
    MESMO gerador do Send (`pu_fator`), em memória: o anexo é o que o Send
    escreveria, mas nada vai para o Batch Conecta — pedir validação não é
    enviar, e um arquivo a mais na pasta seria um envio que ninguém mandou."""
    por_view = {}
    for f in linhas:
        row = domain.linha_para_arquivo(f['contrato'], f['conta_p'], f['idx_p'], f['conta_c'],
                                        f['idx_c'], f['fator_p'] if f['vcp_p'] else None,
                                        f['fator_c'] if f['vcp_c'] else None)
        for rec in _pf.acc_swap_records(row, today):
            if rec['view'] in _ev.FUND_LES:
                por_view.setdefault(rec['view'], []).append(rec['line'])
    return [(_pf.vcp_file_name(view, True),
             '\n'.join([_pf.acc_swap_header(view, today)] + lines).encode('utf-8'))
            for view, lines in sorted(por_view.items())]


def vcp_email_validation(ref, contratos, sid='', nome=''):
    """Email Validation: pede a outro integrante do time a conferência dos
    fatores das linhas contra INSTITUIÇÃO FINANCEIRA — a tabela no corpo e,
    com Lawton/Atacama numa das pontas, o arquivo da visão do fundo em anexo.

    Sem contratos pedidos vale a página inteira. Linha de cliente fica de fora
    (volta em `skipped`); linha de IF que não pode ir para o arquivo recusa o
    pedido — validar um fator que não existe é validar nada. Não muda status:
    quem envia continua sendo o Send, com o maker/checker de sempre."""
    linhas = {f['contrato'].upper(): f for f in queries.vcp_factor_rows(ref)}
    pedidos = [persistence._chave(c) for c in (contratos or []) if persistence._chave(c)]
    alvo = [linhas[k] for k in pedidos if k in linhas] if pedidos else list(linhas.values())
    if not alvo:
        return {'success': False, 'code': 'no_rows', 'params': {},
                'error': 'No contract to validate.'}, 400
    elegiveis = [f for f in alvo if (f.get('validation') or {}).get('scenario')]
    if not elegiveis:
        return {'success': False, 'code': 'no_if_rows', 'params': {'n': len(alvo)},
                'error': 'None of the {} contract(s) is against a financial institution.'.format(len(alvo))}, 400
    problemas = ['{}: {}'.format(f['contrato'], ', '.join(domain.problemas_para_envio(f)))
                 for f in elegiveis if domain.problemas_para_envio(f)]
    if problemas:
        return {'success': False, 'code': 'blocked', 'params': {}, 'error': 'blocked',
                'problems': problemas}, 400
    today = datetime.now().strftime('%Y%m%d')
    com_fundo = [f for f in elegiveis if f['validation']['scenario'] == _ev.SCENARIO_IF_FUND]
    anexos = _fund_attachments(com_fundo, today)
    _ev.dispatch('Swap VCP', 'interest factor', ref, _VALIDATION_HEADERS,
                 [{'cells': _validation_cells(f), 'scenario': f['validation']} for f in elegiveis],
                 anexos, requester=nome, tag='swap-vcp')
    nomes = [n for n, _ in anexos]
    _R()._create_notification(sid, nome, 'VCP Validation Requested', 'Swap VCP',
                              '{} contract(s){}'.format(len(elegiveis),
                                                        ' · ' + ', '.join(nomes) if nomes else '')
                              + _R()._nd_token(ref.strftime('%Y%m%d')))
    return {'success': True, 'mail': 'queued', 'contracts': [f['contrato'] for f in elegiveis],
            'with_fund': [f['contrato'] for f in com_fundo], 'attached': nomes,
            'skipped': len(alvo) - len(elegiveis)}, 200
