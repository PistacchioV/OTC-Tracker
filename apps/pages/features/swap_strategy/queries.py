# -*- coding: utf-8 -*-
"""Leitura da tela Strategy: o cadastro de estratégias + o Live Position.

Contraparte e LOB NÃO são do arquivo da B3: saem da posição de swap
(`DPOSICAO-SWAP`, a mesma do Swap Characteristics), pelo contrato — e por isso
são calculadas na LEITURA, nunca gravadas: a posição de amanhã manda.
"""
import logging
from datetime import datetime

from apps.pages.features.swap_strategy import domain
from apps.pages.platform import swap_flows as _sf
from apps.pages.platform import swap_strategies as _ss

log = logging.getLogger('otc_tracker')


def _R():
    from apps.pages import routes
    return routes


def store_path():
    return _ss.store_path()


def read_all():
    """A lista gravada (platform `swap_strategies`, a mesma que o Swap
    Calculator lê). Ocupado SOBE: lido como vazio, o import seguinte gravaria
    só o arquivo novo por cima."""
    return _ss.read_all()


def _contraparte(vals, R):
    """A MESMA cascata da coluna do Swap Characteristics: o CPF/CNPJ da
    contraparte pelo Reference Data, depois a conta CETIP direta, e só no fim
    o documento mascarado (que denuncia quem falta cadastrar)."""
    doc = _sf.celula(vals, _sf.POS['doc_cp'])
    if R._swapchar_is_xl_error(doc):
        doc = ''
    nome = R._lp_cpty_name_by_taxid(doc)
    if not nome:
        nome = R._lp_cpty_by_account(_sf.celula(vals, _sf.POS['conta_cp']))
    return nome or R._lp_cpty_by_taxid(doc)


def position_map(ref=None):
    """`({contrato: {counterparty, lob}}, data iso do arquivo lido)`.

    A posição de D-1 ANBIMA, andando até dez dias úteis para trás como as
    outras telas do Live Position. O MESMO contrato pode vir em mais de uma
    visão (Banco × Lawton): fica a primeira que resolve a contraparte."""
    R = _R()
    ref = ref or R._prev_anbima_bizday(datetime.now()).date()
    path, dref = R._swap_day_path(ref, '73760_{}_DPOSICAO-SWAP.json')
    if not path:
        return {}, ''
    try:
        src = R._db_day_records(path) or []
    except Exception as exc:                                  # noqa: BLE001
        log.warning('[swap-strategy] posição ilegível %s: %s', path, exc)
        return {}, ''
    out = {}
    for row in src:
        vals = list(row.values())
        if len(vals) < 120:
            # mock esparso da dev: os poucos campos, resolvidos pelo NOME
            contrato = row.get('Contrato', '')
            ident = row.get('Código Identificador', row.get('Codigo Identificador', ''))
            conta = str(row.get('Contraparte', '') or '').strip()
            cpty = R._lp_cpty_by_taxid(row.get('CPF/CNPJ Cliente Contraparte', '')) or \
                R._lp_cpty_by_account(conta) or conta
        else:
            contrato = _sf.celula(vals, _sf.POS['contrato'])
            ident = _sf.celula(vals, _sf.POS['identificador'])
            cpty = _contraparte(vals, R)
        k = domain.norm_contract(contrato)
        if not k:
            continue
        atual = out.get(k)
        if atual is None or (not atual['counterparty'] and cpty):
            out[k] = {'counterparty': cpty or '',
                      # O TOKEN da LOB (EDG · CEM · CEMHYB · COMM), o vocabulário
                      # do resto do app; sem token a célula fica VAZIA.
                      'lob': R._fcst_lob(ident) or ''}
    return out, R._b3_dref_to_iso(dref)


def entries():
    """As linhas da tela: o cadastro + Status, Contraparte e LOB."""
    rows = read_all()
    pos, source_date = position_map()
    out = []
    for e in rows:
        e = dict(e)
        p = pos.get(domain.norm_contract(e.get('Contract'))) or {}
        e['Status'] = domain.status_of(e)
        e['Counterparty'] = p.get('counterparty', '')
        e['LOB'] = p.get('lob', '')
        e['InPosition'] = bool(p)
        out.append(e)
    return {'entries': out, 'source_date': source_date}
