# -*- coding: utf-8 -*-
"""Live Position › DCE: leitura do arquivo-dia (§729).

O Save CETIP Files grava o DPOSICAOCONTRATODCE em
`cache/b3 files/DCE/AAAA/MM/DD/73760_<AAMMDD>_DPOSICAOCONTRATODCE.json`. A tela
lê esse dia — e, sem arquivo, anda até dez dias úteis para trás, como as outras
Live Position (`source_date` diz de que dia é o lido).
"""
from apps.pages.features.live_positions import domain

DCE_FILE = '73760_{}_DPOSICAOCONTRATODCE.json'


def _R():
    """Busca ATRASADA no routes (feature não importa nome do routes)."""
    from apps.pages import routes
    return routes


def labels():
    return list(_R()._B3_SWAP_HEADERS['dce_contract_position'])


def dce_collect(ref, exact=False):
    R = _R()
    labs = labels()
    path, dref = R._swap_day_path(ref, DCE_FILE, exact=exact, category='DCE')
    vazio = {'widgets': {'total': 0}, 'columns': labs, 'rows': [],
             'source_date': R._b3_dref_to_iso(dref)}
    if not path:
        return vazio
    src = R._db_day_records(path)
    if not src:
        return vazio
    dce = {k: domain.code_table(R._mapping_rows(k), 'REFERENCE CODE', 'DOMAIN')
           for k in domain.DCE_TABLES}
    codes = domain.position_codes(R._mapping_rows('dce-position-codes'))
    assets = domain.asset_table(R._mapping_rows('dce-underlying-asset'))
    rows = []
    for rec in src:
        if not isinstance(rec, dict):
            continue
        # pela POSIÇÃO: com cabeçalho próprio do arquivo os nomes podem não ser
        # os do manual, mas a ordem é a do layout
        vals = list(rec.values())
        vals = (vals + [''] * len(labs))[:len(labs)]
        rows.append(domain.display_row(labs, vals, dce, codes, assets))
    return {'widgets': {'total': len(rows)}, 'columns': labs, 'rows': rows,
            'source_date': R._b3_dref_to_iso(dref)}
