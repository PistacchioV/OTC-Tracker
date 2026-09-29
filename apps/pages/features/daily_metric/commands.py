# -*- coding: utf-8 -*-
"""As escritas do card e a montagem do rascunho (o único "run" que ele tem)."""
from apps.pages.features.daily_metric import domain, queries
from apps.pages.features.daily_metric.infra import mail, persistence


def _routes():
    """Busca ATRASADA (ver `infra/persistence.py`): o snapshot e a história de
    métricas são plataforma — o /pending-confirmation/metrics também as lê."""
    from apps.pages import routes
    return routes


def save_recipients(to, cc, bcc):
    persistence.save_recipients(to, cc, bcc)


def build_draft(ref, to_list, cc_list, bcc_list):
    """(bytes, None) ou (None, erro): o rascunho do dia, com o mês e o dia em
    curso carimbados com a leitura de AGORA (ver `domain.stamp_now`)."""
    R = _routes()
    try:
        rows, source = R._pc_latest_snapshot_rows()
        pivot, totals = queries.pivot(rows)
        hist = R._pc_metrics_history().get('gt30') or {}
        monthly = domain.stamp_now(hist.get('monthly') or [], 'period',
                                   ref.strftime('%Y-%m'), totals['total'])
        daily = domain.stamp_now(hist.get('daily') or [], 'date',
                                 ref.strftime('%Y-%m-%d'), totals['total'])
        recent_m = monthly[-13:]
        month_bars = domain.bar_series(recent_m, 'period', domain.fmt_month_lbl)
        # O gráfico do dia é do MÊS CORRENTE, como o título diz. A série de
        # história vem inteira do disco e ia inteira para o gráfico: com dois
        # meses de snapshot ele já mostrava 01/07 ao lado de 12/08 — e o rótulo
        # `dd/mm` esconde isso, porque as barras continuam parecendo uma
        # sequência. O corte é pelo mês do `ref` (não pelo de hoje), que é o mês
        # que o e-mail inteiro reporta.
        mes_ref = ref.strftime('%Y-%m')
        daily_mes = [d for d in daily if str(d.get('date', '')).startswith(mes_ref)]
        day_bars = domain.bar_series(daily_mes, 'date', domain.fmt_day_lbl)
        latest_m = monthly[-1] if monthly else {}
        prev_m = monthly[-2] if len(monthly) >= 2 else {}
        # O cartão e o `pct` continuam saindo da série COMPLETA: dia-sobre-dia
        # no dia 1º compara com o último dia do mês anterior, que é o dia
        # anterior de verdade. Medir dentro do recorte deixaria o primeiro
        # e-mail do mês sem variação nenhuma.
        latest_d = daily[-1] if daily else {}
        ctx = {'current_total': totals['total'],
               'month_total': latest_m.get('volume'),
               'prev_total': prev_m.get('volume'),
               'latest_pct': latest_m.get('pct'),
               'day_pct': latest_d.get('pct'),
               'day_total': latest_d.get('volume'),
               'month_bars': month_bars, 'day_bars': day_bars,
               'pivot': pivot, 'totals': totals}
    except Exception as e:                                  # noqa: BLE001
        import traceback
        R.log.error('[daily-metric] draft FAILED:\n%s', traceback.format_exc())
        return None, '{}: {}'.format(type(e).__name__, e)
    raw, err = mail.build(ref.strftime('%d/%m/%Y'), ctx, to_list, cc_list, bcc_list)
    if raw is not None:
        R.log.info('[daily-metric] draft built — to=%s cc=%s bcc=%d (%d clients, source=%s)',
                   to_list, cc_list, len(bcc_list), len(pivot), source)
    return raw, err


def build_cgd_draft(ref, to_list, cc_list, bcc_list):
    """(bytes, None) ou (None, erro): o relatório dos CGDs PENDENTES do Track
    Docs, na mesma estrutura do Daily Metric (cabeçalho, números, barras e a
    tabela por grupo econômico), para os mesmos destinatários do card."""
    from apps.pages import cgd_docs
    R = _routes()
    try:
        rows = queries.cgd_rows()
        pivot, totals, stats = queries.cgd_pivot(rows)
        # Barras: os pendentes pelo MÊS DA SOLICITAÇÃO, 12 meses até o `ref` —
        # é de quando vem o estoque. Solicitação mais antiga que a janela conta
        # no total e não aparece em barra nenhuma.
        periodos = []
        for r in rows:
            d = cgd_docs.parse_date(r.get(cgd_docs.AGING_FROM))
            if d:
                periodos.append(d.strftime('%Y-%m'))
        meses = domain.month_series(periodos, ref.strftime('%Y-%m'))
        ctx = {'current_total': totals['total'], 'totals': totals, 'pivot': pivot,
               'clients': stats['clients'], 'avg_aging': stats['avg_aging'],
               'oldest': stats['oldest'],
               'month_bars': domain.bar_series(meses, 'period', domain.fmt_month_lbl),
               'stage_bars': domain.bar_series(
                   [{'stage': s['label'], 'volume': s['value']} for s in stats['stages']],
                   'stage', lambda x: x),
               'older': totals['total'] - sum(m['volume'] for m in meses)}
    except Exception as e:                                  # noqa: BLE001
        import traceback
        R.log.error('[daily-metric-cgd] draft FAILED:\n%s', traceback.format_exc())
        return None, '{}: {}'.format(type(e).__name__, e)
    ref_fmt = ref.strftime('%d/%m/%Y')
    raw, err = mail.build(ref_fmt, ctx, to_list, cc_list, bcc_list,
                          template='pages/email-template-daily-metric-cgd.html',
                          subject=domain.cgd_subject(ref_fmt))
    if raw is not None:
        R.log.info('[daily-metric-cgd] draft built — to=%s cc=%s bcc=%d (%d groups, %d CGDs)',
                   to_list, cc_list, len(bcc_list), len(pivot), totals['total'])
    return raw, err
