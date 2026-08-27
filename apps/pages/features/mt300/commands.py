# -*- coding: utf-8 -*-
"""As escritas do card: gravar as listas, enviar a mensagem, o scheduler.

O laço roda aqui; quem o SOBE é o bloco de wiring do `routes.py`
(`_schedule_on_start('mt300', …)`) — mesma razão do `bacc`.
"""
import threading
import time
import traceback
from datetime import timedelta

from apps.pages.features.mt300 import domain, queries
from apps.pages.features.mt300.infra import mail, persistence


def _routes():
    """Busca ATRASADA (ver `infra/persistence.py`): calendário útil, relógio BRT
    e o parse de e-mails são plataforma."""
    from apps.pages import routes
    return routes


def save_recipients(d):
    persistence.save_recipients(d)


def run(ref=None):
    """Uma corrida. Desfechos SEPARADOS: `empty` (nenhuma operação do grupo no
    dia) não é a mesma coisa que `no_recipient` (havia o que mandar e não havia
    para quem)."""
    R = _routes()
    ref = ref or R._br_now()
    rec = persistence.load_recipients()
    to_list = R._parse_emails(rec.get('to'))
    cc_list = [c for c in R._parse_emails(rec.get('cc'))
               if c.lower() not in {t.lower() for t in to_list}]
    rows = queries.rows(ref)
    if not rows:
        return {'sent': False, 'reason': 'empty', 'rows': 0,
                'to': len(to_list), 'cc': len(cc_list)}
    if not to_list:
        return {'sent': False, 'reason': 'no_recipient', 'rows': len(rows),
                'to': 0, 'cc': len(cc_list)}
    res = mail.send(rows, to_list, cc_list, ref)
    if res is True:
        return {'sent': True, 'rows': len(rows), 'to': len(to_list), 'cc': len(cc_list)}
    return {'sent': False, 'reason': 'error', 'error': res, 'rows': len(rows),
            'to': len(to_list), 'cc': len(cc_list)}


def run_manual(payload=None):
    """O botão Run do card: grava as listas que vierem no payload — o botão
    envia o que está na tela —, roda AGORA e, no sucesso, grava o status. NÃO
    consome o claim do disparo das 19:30: o Run é um teste ou um envio fora de
    hora, e queimar o horário faria o e-mail do dia não sair."""
    R = _routes()
    payload = payload or {}
    if 'to' in payload or 'cc' in payload:
        try:
            persistence.save_recipients(payload)
        except Exception:                                   # noqa: BLE001
            R.log.error('[mt300] save recipients failed:\n%s', traceback.format_exc())
    out = run(R._br_now())
    if out['sent']:
        persistence.write_status('sent:{}'.format(out['rows']), R._br_now())
    return out


def fire_slot(slot, fired):
    """Manda o e-mail do slot, se ninguém já mandou e o dia é útil ANBIMA.

    `empty` e `no_recipient` CONSOMEM o slot (nenhum dos dois melhora na
    retentativa: sem operação não há e-mail, e sem destinatário quem resolve é
    o card); erro de envio DEVOLVE o slot para a próxima volta retentar.
    """
    R = _routes()
    if not R._pcx_is_bizday(fired):
        return False
    if not persistence.claim_slot(slot):
        return False
    out = run(fired)
    if out['sent']:
        result = 'sent:{}'.format(out['rows'])
    elif out.get('reason') in ('empty', 'no_recipient'):
        result = out['reason']
    else:
        persistence.release_slot(slot)
        result = 'error'
    R.log.info('[mt300] disparo de %s (BRT): %s', slot, result)
    persistence.write_status(result, fired)
    return True


def scheduler_loop():
    R = _routes()
    while True:
        try:
            hh, mm = domain.TIME
            now = R._br_now()
            cand = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if cand <= now:
                # Catch-up como no Deals Monitor: recupera o disparo do dia
                # quando o processo subiu depois do horário, e RETENTA o que
                # falhou e foi devolvido.
                fire_slot('{} {:02d}:{:02d}'.format(now.strftime('%Y-%m-%d'), hh, mm), now)
                nxt = cand + timedelta(days=1)
            else:
                nxt = cand
            now = R._br_now()
            time.sleep(max(1.0, min((nxt - now).total_seconds(), 3600)))
        except Exception:                                   # noqa: BLE001
            R.log.error('[mt300] scheduler error:\n%s', traceback.format_exc())
            time.sleep(60)


_scheduler_started = False
_scheduler_lock = threading.Lock()


def start_scheduler():
    global _scheduler_started
    with _scheduler_lock:
        if _scheduler_started:
            return
        _scheduler_started = True
    threading.Thread(target=scheduler_loop, name='mt300-scheduler', daemon=True).start()
    _routes().log.info('[mt300] scheduler iniciado (%02d:%02d BRT · dias úteis ANBIMA)',
                       *domain.TIME)
