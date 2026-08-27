# -*- coding: utf-8 -*-
"""A gravação da planilha e o scheduler das 10:45.

O laço roda aqui; quem o SOBE é o wiring do routes (`_schedule_on_start`).
"""
import threading
import time
import traceback
from datetime import timedelta

from apps.pages.features.pcx import domain, queries
from apps.pages.features.pcx.infra import persistence


def _routes():
    """Busca ATRASADA — ver `features/support/infra/persistence.py`."""
    from apps.pages import routes
    return routes


def save(ref=None):
    """Gera e grava a planilha no share. → (n linhas, caminho). Ver as regras
    do nome canônico no docstring de `persistence.save_spreadsheet`."""
    return persistence.save_spreadsheet(queries.rows_at(ref))


def run_manual(ref=None):
    """O botão Run: grava agora e carimba o status como `manual` — com a `ref`
    da foto quando é data anterior, que é o que diz o que está no share."""
    R = _routes()
    n, fp = save(ref)
    persistence.write_status('manual', 'saved:{}'.format(n), R._br_now(), ref)
    return n, fp


def fire_slot(slot, fired):
    """Grava a planilha do slot, se ninguém já gravou e o dia é útil ANBIMA."""
    R = _routes()
    if not R._pcx_is_bizday(fired):
        return False
    if not persistence.claim_slot(slot):
        return False
    try:
        n, fp = save()
        R.log.info('[pending-spreadsheet] %s: %d linha(s) → %s', slot, n, fp)
        persistence.write_status(slot, 'saved:{}'.format(n), fired)
    except Exception as e:                                  # noqa: BLE001
        R.log.error('[pending-spreadsheet] gravação de %s falhou:\n%s',
                  slot, traceback.format_exc())
        persistence.write_status(slot, 'error:{}: {}'.format(type(e).__name__, e), fired)
        persistence.release_slot(slot)
    return True


def scheduler_loop():
    R = _routes()
    hh, mm = domain.time_of(persistence.TIME_RAW)
    while True:
        try:
            # Catch-up a cada volta (mesma mecânica do Deals Monitor): recupera
            # o disparo do dia quando o processo subiu depois do horário — a
            # instância reinicia várias vezes por dia — e RETENTA o slot que
            # falhou e foi devolvido.
            now = R._br_now()
            cand = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if cand <= now:
                slot = '{} {:02d}:{:02d}'.format(now.strftime('%Y-%m-%d'), hh, mm)
                if fire_slot(slot, now):
                    R.log.info('[pending-spreadsheet] disparo de %s recuperado no start', slot)
                nxt = cand + timedelta(days=1)
            else:
                nxt = cand
            now = R._br_now()
            time.sleep(max(1.0, min((nxt - now).total_seconds(), 3600)))
        except Exception:
            R.log.error('[pending-spreadsheet] scheduler error:\n%s', traceback.format_exc())
            time.sleep(60)


_scheduler_started = False
_scheduler_lock = threading.Lock()


def start_scheduler():
    global _scheduler_started
    with _scheduler_lock:
        if _scheduler_started:
            return
        _scheduler_started = True
    threading.Thread(target=scheduler_loop,
                     name='pending-spreadsheet-scheduler', daemon=True).start()
    _routes().log.info('[pending-spreadsheet] scheduler iniciado (%02d:%02d BRT = 19:15 IST · '
                       'dias úteis ANBIMA)', *domain.time_of(persistence.TIME_RAW))
