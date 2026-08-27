# -*- coding: utf-8 -*-
"""As leituras do card: o pivô por grupo econômico e as listas."""
from apps.pages.features.daily_metric import domain
from apps.pages.features.daily_metric.infra import persistence


def _routes():
    """Busca ATRASADA (ver `infra/persistence.py`): o RefData indexado, o
    normalizador e o parse do aging são plataforma do Pending Confirmation."""
    from apps.pages import routes
    return routes


def pivot(rows):
    """Per-ECONOMIC-GROUP aging buckets for rows pending >= 30 days (30-59 /
    60-89 / >=90), plus the banker group and the digital-signature (FepWeb/green)
    flag. The economic group, banker and signature type all come from
    RefData.json (matched by SPN, then counterparty name); a group is green when
    RefData marks its signature type DIGITAL. Sorted by total desc. Returns
    (rows[], totals)."""
    R = _routes()
    by_spn = R._fxo_refdata_by_spn()
    by_name = R._pc_refdata_by_name()
    groups = {}
    for r in rows:
        a = R._pc_metrics_int(r.get('Aging'))
        if a is None or a < 30:
            continue
        rec = R._pc_refdata_lookup(r, by_spn, by_name)
        group = (str(rec.get('ECONOMIC GROUP', '') or '').strip()
                 or str(r.get('Economic Group', '') or '').strip()
                 or str(r.get('Client', '') or '').strip()
                 or '(no group)')
        d = groups.setdefault(group, {'b1': 0, 'b2': 0, 'b3': 0, 'banker': '', 'digital': False})
        if a < 60:
            d['b1'] += 1
        elif a < 90:
            d['b2'] += 1
        else:
            d['b3'] += 1
        if not d['banker']:
            d['banker'] = str(rec.get('BANKER', '') or r.get('Owner', '') or '').strip()
        if R._pc_norm(rec.get('SIGNATURE TYPE', '')) == 'digital':
            d['digital'] = True
    out = []
    for group, d in groups.items():
        total = d['b1'] + d['b2'] + d['b3']
        out.append({'group': group, 'b1': d['b1'], 'b2': d['b2'], 'b3': d['b3'],
                    'total': total, 'banker': d['banker'], 'digital': d['digital'],
                    'operations': domain.OPERATIONS})
    out.sort(key=lambda x: (-x['total'], x['group'].lower()))
    totals = {'b1': sum(x['b1'] for x in out), 'b2': sum(x['b2'] for x in out),
              'b3': sum(x['b3'] for x in out), 'total': sum(x['total'] for x in out)}
    return out, totals


def recipients():
    return persistence.load_recipients()
