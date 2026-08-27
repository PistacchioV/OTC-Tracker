# -*- coding: utf-8 -*-
"""As regras do relatório — puras."""

OPERATIONS = 'Priscila Babilonia'   # Ops support contact — fixed for now.
MONTH_ABBR = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
              'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def subject(ref_fmt):
    return 'Daily Metric - Outstanding Confirmation Brazil OTC - {}'.format(ref_fmt)


def fmt_month_lbl(period):     # "2025-07" -> "Jul/25"
    try:
        y, m = period.split('-')
        return '{}/{}'.format(MONTH_ABBR[int(m)], y[2:])
    except Exception:                                       # noqa: BLE001
        return period


def fmt_day_lbl(date):         # "2026-07-01" -> "01/07"
    try:
        _, m, dd = date.split('-')
        return '{}/{}'.format(dd, m)
    except Exception:                                       # noqa: BLE001
        return date


def bar_series(items, keyfield, labelfn, maxpx=60):
    """Turn a history slice into bar cells with a pixel height proportional to the
    max value — an email-safe (image/JS-free) bar chart. Each cell: {label,value,h}."""
    vals = [it.get('volume') or 0 for it in items]
    hi = max(vals) if vals else 0
    hi = hi or 1
    return [{'label': labelfn(it[keyfield]), 'value': it.get('volume') or 0,
             'h': max(3, int(round((it.get('volume') or 0) * maxpx / hi)))} for it in items]


def stamp_now(series, key, periodo, total):
    """Carimba a leitura de AGORA no ponto do período em curso e refaz o `pct`.

    A série de história sai dos SNAPSHOTS em disco (o último de cada mês/dia) e o
    e-mail é gerado ao vivo. Sem isto o cartão dizia 177 e a última barra dizia
    167: quem lia não tinha como saber se o +9% ia de 153 para 167 ou para 177.

    Mês e dia em curso não estão fechados — o valor deles é o de agora, que é
    exatamente o que este e-mail reporta, e é o mesmo número que a tabela por
    grupo econômico logo abaixo soma. O `pct` é recalculado contra o ponto
    anterior; sem isso a barra subiria e a variação continuaria a do snapshot,
    trocando uma incoerência por outra.

    Sem ponto para o período em curso a série ganha um — o e-mail do dia 1º de um
    mês novo mostrava a última barra do mês anterior como se fosse a de hoje.
    """
    out = [dict(p) for p in series]
    anterior = out[-2]['volume'] if len(out) >= 2 else None
    if out and out[-1].get(key) == periodo:
        out[-1]['volume'] = total
    else:
        anterior = out[-1]['volume'] if out else None
        out.append({key: periodo, 'volume': total, 'pct': None})
    out[-1]['pct'] = (None if anterior in (None, 0)
                      else int(round((total - anterior) * 100.0 / anterior)))
    return out
