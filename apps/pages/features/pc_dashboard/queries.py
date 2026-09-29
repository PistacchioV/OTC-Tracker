# -*- coding: utf-8 -*-
"""As leituras do dashboard: a fila pendente, as faixas e a tabela."""
from apps.pages.features.pc_dashboard import domain

# Um dia de cada faixa, na ordem da tela: a lista sai da MESMA função que grava
# o Status no Pending Confirmation (`_pc_aging_band_label`), nunca de uma cópia
# dos rótulos aqui — mudou lá, muda aqui.
_BAND_PROBES = (0, 10, 20, 30, 60, 90)


def _R():
    """Busca ATRASADA no routes — a fila e as faixas são plataforma."""
    from apps.pages import routes
    return routes


def bands():
    R = _R()
    out = []
    for d in _BAND_PROBES:
        label = R._pc_aging_band_label(d)
        if label not in out:
            out.append(label)
    return out


def _item(row):
    R = _R()
    return {
        'group': str(row.get('Economic Group') or '').strip() or domain.NO_GROUP,
        'owner': str(row.get('Owner') or '').strip(),
        'signature': str(row.get('Signature Type') or '').strip(),
        'quarter': domain.quarter_of(R._parse_date_any(row.get('Trade Date', ''))),
        'status': str(row.get('Pending Status') or '').strip() or '—',
        'band': str(row.get('Status') or '').strip(),
    }


def data(selected=None):
    """A tabela para as faixas `selected` (None = todas) e a contagem de cada
    faixa — a contagem é da fila INTEIRA, para o chip dizer o que ele traz."""
    rows, source = _R()._pc_latest_snapshot_rows()
    items = [_item(r) for r in rows]
    todas = bands()
    contagem = {b: 0 for b in todas}
    for it in items:
        if it['band'] in contagem:
            contagem[it['band']] += 1
    if selected is not None:
        escolhidas = set(selected)
        items = [it for it in items if it['band'] in escolhidas]
    out = domain.pivot(items)
    out['bands'] = [{'label': b, 'count': contagem[b]} for b in todas]
    out['source'] = source
    return out
