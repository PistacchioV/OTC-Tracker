# -*- coding: utf-8 -*-
"""As escritas do card: gravar as listas, enviar o relatório, o scheduler.

O laço roda aqui, mas quem o SOBE é o `routes.py`: o registro
(`_schedule_on_start('bacc-ea', …)`) fica no bloco de wiring, porque o gancho é
de plataforma e chamá-lo do corpo deste módulo fecharia o ciclo de import.
"""
import threading
import time
import traceback
from datetime import timedelta

from apps.pages.features.bacc import domain
from apps.pages.features.bacc.infra import mail, persistence


def _routes():
    """Busca ATRASADA (ver `infra/persistence.py`): calendário útil, relógio BRT
    e o parse de e-mails são plataforma."""
    from apps.pages import routes
    return routes


def save_recipients(d):
    persistence.save_recipients(d)


def run(ref=None):
    """Uma corrida. Devolve o resumo, com os desfechos separados.

    'no_recipient' (lista de TO em branco) NÃO é a mesma coisa que um envio
    vazio: o segundo é a rotina funcionando num dia sem operação manual, o
    primeiro é um relatório que não saiu de casa. Lista vazia é o único motivo
    de não enviar — a planilha sem linha nenhuma **vai assim mesmo**, porque a
    ausência de operação manual no dia é ela própria a métrica.
    """
    from apps.pages import manual_conf
    R = _routes()
    ref = ref or R._br_now()
    rec = persistence.load_recipients()
    to_list = R._parse_emails(rec.get('to'))
    cc_list = [c for c in R._parse_emails(rec.get('cc')) if c.lower() not in
               {t.lower() for t in to_list}]
    rows = domain.pending(manual_conf.load_all(), manual_conf.STATUS_OK)
    if not to_list:
        return {'sent': False, 'reason': 'no_recipient', 'rows': len(rows),
                'to': 0, 'cc': len(cc_list)}
    res = mail.send(rows, to_list, cc_list, ref)
    if res is True:
        return {'sent': True, 'rows': len(rows), 'to': len(to_list), 'cc': len(cc_list)}
    return {'sent': False, 'reason': 'error', 'error': res, 'rows': len(rows),
            'to': len(to_list), 'cc': len(cc_list)}


def run_manual():
    """O botão Run do card: envia agora e, no sucesso, grava o desfecho como
    slot `manual` — sem tocar no claim do disparo automático (o Run é um teste
    ou um envio fora de hora, e queimar o horário faria o relatório do dia não
    sair)."""
    R = _routes()
    out = run(R._br_now())
    if out['sent']:
        persistence.write_status('manual', 'sent:{}'.format(out['rows']), R._br_now())
    return out


def fire_slot(slot, fired):
    """Manda o e-mail do slot, se ninguém já mandou e o dia é útil ANBIMA.

    `no_recipient` CONSOME o slot (sem destinatário a retentativa não mudaria
    nada — quem resolve isso é o card, não o scheduler); erro de envio DEVOLVE
    o slot, para a próxima volta retentar.
    """
    R = _routes()
    if not R._pcx_is_bizday(fired):
        return False
    if not persistence.claim_slot(slot):
        return False
    out = run(fired)
    if out['sent']:
        result = 'sent:{}'.format(out['rows'])
    elif out.get('reason') == 'no_recipient':
        result = 'no_recipient'
    else:
        result = 'error:' + str(out.get('error') or 'unknown')
        persistence.release_slot(slot)
    R.log.info('[bacc-ea] %s: %s', slot, result)
    persistence.write_status(slot, result, fired)
    return True


def scheduler_loop():
    R = _routes()
    while True:
        try:
            hh, mm = domain.time_of(persistence.TIME_RAW)
            now = R._br_now()
            cand = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if cand <= now:
                # Catch-up a cada volta (mesma mecânica do Deals Monitor):
                # recupera o disparo do dia quando o processo subiu depois do
                # horário e RETENTA o slot que falhou e foi devolvido.
                slot = '{} {:02d}:{:02d}'.format(now.strftime('%Y-%m-%d'), hh, mm)
                if fire_slot(slot, now):
                    R.log.info('[bacc-ea] disparo de %s recuperado no start', slot)
                nxt = cand + timedelta(days=1)
            else:
                nxt = cand
            now = R._br_now()
            time.sleep(max(1.0, min((nxt - now).total_seconds(), 3600)))
        except Exception:                                   # noqa: BLE001
            R.log.error('[bacc-ea] scheduler error:\n%s', traceback.format_exc())
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
                     name='bacc-ea-metrics-scheduler', daemon=True).start()
    _routes().log.info('[bacc-ea] scheduler iniciado (%02d:%02d BRT · dias úteis ANBIMA)',
                       *domain.time_of(persistence.TIME_RAW))
