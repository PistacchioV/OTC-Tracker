# -*- coding: utf-8 -*-
"""As leituras do card: a quebra por LOB × banqueiro × empresa e as listas."""
from apps.pages.features.weekly_escalation import domain
from apps.pages.features.weekly_escalation.infra import persistence


def _routes():
    """Busca ATRASADA (ver `infra/persistence.py`): o RefData indexado e o parse
    do aging são plataforma do Pending Confirmation."""
    from apps.pages import routes
    return routes


def blocks(rows):
    """Rows pending >= 30 days, split by LOB (CEM, EDG). Per LOB: bankers sorted
    by total desc, each with a total and a company (client name) breakdown sorted
    by count desc. Banker = RefData BANKER (by SPN, then name), falling back to
    Owner."""
    R = _routes()
    by_spn = R._fxo_refdata_by_spn()
    by_name = R._pc_refdata_by_name()
    data = {lob: {} for lob in domain.LOBS}
    for r in rows:
        a = R._pc_metrics_int(r.get('Aging'))
        if a is None or a < 30:
            continue
        lob_n = R._pc_norm(r.get('LOB', ''))
        lob = 'CEM' if lob_n == 'cem' else ('EDG' if lob_n == 'edg' else None)
        if lob is None:
            continue
        rec = R._pc_refdata_lookup(r, by_spn, by_name)
        banker = str(rec.get('BANKER', '') or r.get('Owner', '') or '').strip() or '(no banker)'
        company = str(r.get('Client', '') or '').strip() or '(no client)'
        b = data[lob].setdefault(banker, {'total': 0, 'companies': {}})
        b['total'] += 1
        b['companies'][company] = b['companies'].get(company, 0) + 1
    out = []
    for lob in domain.LOBS:
        bankers = []
        for banker, bd in sorted(data[lob].items(),
                                 key=lambda kv: (-kv[1]['total'], kv[0].lower())):
            companies = [{'name': c, 'count': n}
                         for c, n in sorted(bd['companies'].items(),
                                            key=lambda kv: (-kv[1], kv[0].lower()))]
            bankers.append({'banker': banker, 'total': bd['total'], 'companies': companies})
        out.append({'lob': lob, 'bankers': bankers, 'total': sum(b['total'] for b in bankers)})
    return out


def recipients():
    return persistence.load_recipients()
