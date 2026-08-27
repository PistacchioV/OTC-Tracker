# -*- coding: utf-8 -*-
"""A varredura do box e o scheduler.

O botão Import continua existindo e é o caminho manual; isto é o mesmo trabalho
feito sozinho a cada `BOX_SCAN_POLL_MIN` minutos, dentro da janela de importação
da mesa. ⚠️ O caminho manual parseia o e-mail NO NAVEGADOR (otc-fileupload.js);
aqui quem parseia é `otc_boxparse` — duas cópias da MESMA regra, mantidas
honestas pelo `check_boxparse.py` (JS de verdade no JavaScriptCore).

O laço roda aqui; quem o SOBE é o wiring do routes (`_schedule_on_start`).
"""
import os
import threading
import time
import traceback

from apps.pages import otc_boxparse
from apps.pages.features.boxscan import domain, queries
from apps.pages.features.boxscan.infra import persistence

POLL_MIN = int(os.getenv('BOX_SCAN_POLL_MIN', '30') or 30)


def _routes():
    """Busca ATRASADA — ver `features/support/infra/persistence.py`."""
    from apps.pages import routes
    return routes


def pull(product):
    """Uma varredura do box para um produto: lê os e-mails, grava os deals e
    arquiva só o e-mail cujos deals entraram. Devolve o resumo do que aconteceu.

    Levanta EnvironmentError fora do Windows/Outlook — quem chama decide o tom.
    """
    cfg = persistence.PRODUCTS.get(product)
    if not cfg:
        raise ValueError('produto deve ser ndf ou opt (recebido: %r)' % product)
    from apps.pages.otc_boxscan import scan_new_deals_box, archive_email
    R = _routes()

    res = scan_new_deals_box(product)
    emails = res.get('emails') or []
    cancelled = res.get('cancelled') or []
    if not emails:
        return {'emails': 0, 'deals': 0, 'new': 0, 'amended': 0,
                'archived': 0, 'cancelled': len(cancelled)}

    ref_map = queries.refdata_by_accronym()
    subj_idx = queries.subjacente_index()
    maps = queries.commodity_maps()

    total = new_n = amend_n = archived = 0
    for em in emails:
        try:
            deals = otc_boxparse.deals_from_html(
                em.get('html') or '', ref_map, subj_idx,
                domain.MAKER_SID, cfg['layout'], maps)
        except Exception:
            R.log.warning('[boxscan] %s: falha ao parsear %r:\n%s',
                        product, em.get('subject'), traceback.format_exc())
            continue
        if not deals:
            # Sem linha de deal: NÃO arquiva. O e-mail fica no box para alguém
            # olhar — arquivar aqui esconderia um layout que o parser não leu.
            R.log.warning('[boxscan] %s: nenhum deal em %r (e-mail mantido no box)',
                        product, em.get('subject'))
            continue
        n, a = persistence.persist_deals(product, deals)
        total += len(deals)
        new_n += n
        amend_n += a
        if em.get('entry_id'):
            try:
                archive_email(em['entry_id'])
                archived += 1
            except Exception:
                R.log.warning('[boxscan] %s: não consegui arquivar %r:\n%s',
                            product, em.get('subject'), traceback.format_exc())
    if new_n or amend_n:
        bits = []
        if new_n:
            bits.append('{} imported'.format(new_n))
        if amend_n:
            bits.append('{} amended'.format(amend_n))
        R._create_notification(domain.MAKER_SID, 'Box Scan', 'New Deals', cfg['label'],
                             'Outlook box: {} deal(s)'.format(', '.join(bits)))
    R.log.info('[boxscan] %s: %d e-mail(s) · %d deal(s) · novos=%d amendados=%d · '
             'arquivados=%d · cancelamentos apagados do box=%d',
             product, len(emails), total, new_n, amend_n, archived, len(cancelled))
    return {'emails': len(emails), 'deals': total, 'new': new_n,
            'amended': amend_n, 'archived': archived, 'cancelled': len(cancelled)}


def scheduler_loop():
    last_err = {}
    while True:
        time.sleep(max(60, POLL_MIN * 60))
        if not _routes()._import_window_open():
            continue                    # fora do horário da mesa — `_import_window_open`
        for product in persistence.PRODUCTS:
            try:
                pull(product)
                last_err.pop(product, None)
            except EnvironmentError as e:
                # Sem Outlook (host não-Windows): estado esperado, não é falha.
                if last_err.get(product) != str(e):
                    _routes().log.info('[boxscan] %s indisponível: %s', product, e)
                last_err[product] = str(e)
            except Exception as e:                          # noqa: BLE001
                msg = str(e)
                if last_err.get(product) != msg:
                    _routes().log.warning('[boxscan] varredura de %s falhou: %s', product, msg)
                else:
                    _routes().log.debug('[boxscan] varredura de %s falhou de novo: %s', product, msg)
                last_err[product] = msg


_scheduler_started = False
_scheduler_lock = threading.Lock()


def start_scheduler():
    global _scheduler_started
    with _scheduler_lock:
        if _scheduler_started:
            return
        _scheduler_started = True
    threading.Thread(target=scheduler_loop,
                     name='box-scan-scheduler', daemon=True).start()
    R = _routes()
    R.log.info('[boxscan] scheduler do box iniciado (a cada %d min · janela %s BRT '
               '· NDF Comm e Opt Comm)', POLL_MIN, R._import_window_label())
