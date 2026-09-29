# -*- coding: utf-8 -*-
"""A tabela dinâmica do dashboard — pura (nada de banco nem Flask)."""

NO_GROUP = '(no group)'
NO_DATE = '(no date)'


def quarter_of(d):
    """`(ano, trimestre)` de uma data, ou None sem data."""
    if d is None:
        return None
    return (d.year, (d.month - 1) // 3 + 1)


def quarter_label(q):
    """`2026 T1` — o rótulo da imagem da mesa (T de trimestre)."""
    return NO_DATE if q is None else '{} T{}'.format(q[0], q[1])


def pivot(items):
    """`items`: dicts já resolvidos {group, owner, signature, quarter, status}.

    Colunas: trimestres em ordem cronológica (sem data por último) e, dentro de
    cada um, os Pending Status que aparecem nele, em ordem alfabética. Linhas:
    uma por (group, owner, signature), da maior para a menor, e o nome desempata.
    Célula sem pendência é 0 (a tela a desenha vazia)."""
    quarters = {}
    for it in items:
        quarters.setdefault(it['quarter'], set()).add(it['status'])
    ordem = sorted(quarters, key=lambda q: (q is None, q or (0, 0)))
    columns = []
    spans = []
    for q in ordem:
        sts = sorted(quarters[q], key=lambda s: s.lower())
        spans.append({'label': quarter_label(q), 'span': len(sts)})
        columns.extend({'quarter': quarter_label(q), 'status': s} for s in sts)
    index = {(c['quarter'], c['status']): i for i, c in enumerate(columns)}

    linhas = {}
    for it in items:
        chave = (it['group'], it['owner'], it['signature'])
        valores = linhas.setdefault(chave, [0] * len(columns))
        valores[index[(quarter_label(it['quarter']), it['status'])]] += 1
    rows = [{'group': g, 'owner': o, 'signature': s, 'values': v, 'total': sum(v)}
            for (g, o, s), v in linhas.items()]
    rows.sort(key=lambda r: (-r['total'], r['group'].lower(), r['owner'].lower()))
    totals = [sum(r['values'][i] for r in rows) for i in range(len(columns))]
    return {'quarters': spans, 'columns': columns, 'rows': rows,
            'totals': {'values': totals, 'total': sum(totals)},
            'max': max((v for r in rows for v in r['values']), default=0)}
