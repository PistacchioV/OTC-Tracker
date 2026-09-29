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
        # A LINHA responde primeiro; o RefData é o complemento, não o juiz.
        #
        # A coluna `Signature Type` da linha é preenchida por
        # `_pc_refdata_enrich` em TODO feed que insere no Pending Confirmation,
        # e é ela que a tela mostra. Reresolver aqui pelo RefData criava uma
        # SEGUNDA resposta para a mesma pergunta, e quando as duas discordam
        # quem aparece é a do e-mail — pintada de branco, que a legenda chama
        # de *Manually signed*. Foi o PROLEC em 09/09/2026: SPN e Client da
        # linha batendo com o cadastro, `Pending Digital Signature` na tela, e
        # o relatório dizendo que o cliente assina no papel.
        #
        # A ordem importa nos dois sentidos: linha calada (as antigas, de antes
        # da coluna) continua caindo no RefData — sem isso o grupo inteiro
        # perderia o verde que hoje tem.
        assinatura = (str(r.get('Signature Type', '') or '').strip()
                      or str(rec.get('SIGNATURE TYPE', '') or ''))
        if R._pc_norm(assinatura) == 'digital':
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


def cgd_rows():
    """Os CGDs PENDENTES do Track Docs — a mesma regra do card *Pending* da
    tela (`cgd_docs.outcome`), com o aging já refeito pelo `load_all`."""
    from apps.pages import cgd_docs
    return [r for r in cgd_docs.load_all() if cgd_docs.outcome(r) == 'pending']


def cgd_pivot(rows):
    """Por GRUPO ECONÔMICO (a coluna `Grupo Economico` do Track Docs; sem ela,
    a Razão Social): faixas de aging em dias úteis, as mesas com que o CGD está
    (Legal / OTC / CEM MO — um CGD pode dever a duas), o tipo de assinatura e o
    banker, que sai do RefData pela SPN, como no relatório de confirmações.
    Ordenado do maior total. Devolve (linhas, totais, estatísticas)."""
    from apps.pages import cgd_docs
    R = _routes()
    by_spn = R._fxo_refdata_by_spn()
    by_name = R._pc_refdata_by_name()
    groups = {}
    stages = {s: 0 for s in cgd_docs.STAGES}
    agings = []
    for r in rows:
        rec = R._pc_refdata_lookup({'SPN': r.get('SPN', ''), 'Client': r.get('Razão Social', '')},
                                   by_spn, by_name)
        group = (str(r.get('Grupo Economico', '') or '').strip()
                 or str(rec.get('ECONOMIC GROUP', '') or '').strip()
                 or str(r.get('Razão Social', '') or '').strip()
                 or '(no group)')
        d = groups.setdefault(group, {'b0': 0, 'b1': 0, 'b2': 0, 'b3': 0, 'nd': 0,
                                      'stages': set(), 'signatures': set(), 'banker': '',
                                      'oldest': None})
        aging = r.get('Aging')
        d[domain.cgd_bucket(aging)] += 1
        if isinstance(aging, int):
            agings.append(aging)
            d['oldest'] = aging if d['oldest'] is None else max(d['oldest'], aging)
        etapas, _ = cgd_docs.pending_stages(r)
        for e in etapas:
            d['stages'].add(e)
            stages[e] = stages.get(e, 0) + 1
        sig = str(r.get(cgd_docs.SIGNATURE_COLUMN, '') or '').strip()
        if sig:
            d['signatures'].add(sig)
        if not d['banker']:
            d['banker'] = str(rec.get('BANKER', '') or '').strip()
    out = []
    for group, d in groups.items():
        total = d['b0'] + d['b1'] + d['b2'] + d['b3'] + d['nd']
        out.append({'group': group, 'b0': d['b0'], 'b1': d['b1'], 'b2': d['b2'], 'b3': d['b3'],
                    'nd': d['nd'], 'total': total, 'oldest': d['oldest'],
                    'stages': ', '.join(s for s in cgd_docs.STAGES if s in d['stages']),
                    'signature': ', '.join(sorted(d['signatures'])),
                    'digital': any(R._pc_norm(s) in domain.CGD_DIGITAL for s in d['signatures']),
                    'banker': d['banker'], 'operations': domain.OPERATIONS})
    out.sort(key=lambda x: (-x['total'], -(x['oldest'] or 0), x['group'].lower()))
    totals = {k: sum(x[k] for x in out) for k in ('b0', 'b1', 'b2', 'b3', 'nd', 'total')}
    stats = {'clients': len(out),
             'avg_aging': round(sum(agings) / len(agings), 1) if agings else None,
             'oldest': max(agings) if agings else None,
             'stages': [{'label': s, 'value': stages[s]} for s in cgd_docs.STAGES]}
    return out, totals, stats


def recipients():
    return persistence.load_recipients()
