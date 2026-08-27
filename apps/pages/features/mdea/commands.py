# -*- coding: utf-8 -*-
"""As escritas do card: gravar as listas, os pares de re-booking, enviar, o
scheduler das duas rotinas.

O laço roda aqui; quem o SOBE é o bloco de wiring do `routes.py`
(`_schedule_on_start('manual-deals-ea', …)`) — mesma razão do `bacc`.
"""
import threading
import time
import traceback
from datetime import timedelta

from apps.pages.features.mdea import domain, queries
from apps.pages.features.mdea.infra import mail, persistence


def _routes():
    """Busca ATRASADA (ver `infra/persistence.py`)."""
    from apps.pages import routes
    return routes


def save_recipients(d):
    persistence.save_recipients(d)


def record_rebooks(rebooks, ref):
    """O gancho chamado pelo pull do NDF (routes): grava os pares
    (vanilla ↔ FWD Start) do dia da fixação — ver o docstring do pacote."""
    persistence.record_rebooks(rebooks, ref)


def run(kind, ref=None):
    """Uma corrida de uma rotina. Devolve o resumo com os desfechos SEPARADOS.

    **Lista vazia NÃO envia**, e aqui isso é o contrário do BACC EA Metrics: lá
    a planilha vazia é ela própria a métrica; aqui o e-mail PEDE para excluir as
    operações abaixo do EA automático, e sem operação nenhuma não há o que pedir.
    Um e-mail com a tabela vazia faria quem recebe procurar o que não existe.
    """
    R = _routes()
    ref = ref or R._br_now()
    rec = persistence.load_recipients()
    to_list = R._parse_emails(rec.get('to'))
    cc_list = [c for c in R._parse_emails(rec.get('cc'))
               if c.lower() not in {t.lower() for t in to_list}]
    rows = queries.rows(kind, ref)
    if not rows:
        return {'sent': False, 'reason': 'empty', 'rows': 0,
                'to': len(to_list), 'cc': len(cc_list)}
    if not to_list:
        return {'sent': False, 'reason': 'no_recipient', 'rows': len(rows),
                'to': 0, 'cc': len(cc_list)}
    res = mail.send(kind, rows, to_list, cc_list, ref)
    if res is True:
        return {'sent': True, 'rows': len(rows), 'to': len(to_list), 'cc': len(cc_list)}
    return {'sent': False, 'reason': 'error', 'error': res, 'rows': len(rows),
            'to': len(to_list), 'cc': len(cc_list)}


def run_manual(kind, payload=None):
    """Um dos dois botões Run do card: o TO que está na TELA vale para esta
    corrida e fica gravado — o mesmo contrato do card do CETIP, para o Run não
    usar uma lista antiga. NÃO consome o claim do disparo automático."""
    R = _routes()
    payload = payload or {}
    if 'to' in payload or 'cc' in payload:
        try:
            persistence.save_recipients(payload)
        except Exception:                                   # noqa: BLE001
            R.log.error('[manual-deals-ea] save recipients failed:\n%s', traceback.format_exc())
    out = run(kind, R._br_now())
    if out['sent']:
        persistence.write_status(kind, 'sent:{}'.format(out['rows']), R._br_now())
    return out


def fire_slot(kind, slot, fired):
    """Manda o e-mail do slot, se ninguém já mandou e o dia é útil ANBIMA."""
    R = _routes()
    if not R._pcx_is_bizday(fired):
        return False
    if not persistence.claim_slot(slot):
        return False
    out = run(kind, fired)
    if out['sent']:
        result = 'sent:{}'.format(out['rows'])
    elif out.get('reason') in ('empty', 'no_recipient'):
        # Nenhum dos dois melhora na retentativa: sem operação não há e-mail, e
        # sem destinatário quem resolve é o card. O slot fica consumido.
        result = out['reason']
    else:
        # Falha de envio devolve o slot: a próxima volta do catch-up tenta de novo.
        persistence.release_slot(slot)
        result = 'error'
    R.log.info('[manual-deals-ea] %s de %s (BRT): %s', kind, slot, result)
    persistence.write_status(kind, result, fired)
    return True


def scheduler_loop():
    R = _routes()
    while True:
        try:
            now = R._br_now()
            dia = now.strftime('%Y-%m-%d')
            prox = []
            for kind in domain.KINDS:
                hh, mm = domain.TIME[kind]
                cand = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
                if cand <= now:
                    # Catch-up como no Deals Monitor: recupera o disparo do dia
                    # quando o processo subiu depois do horário (a instância
                    # reinicia várias vezes ao dia) e RETENTA o que falhou.
                    fire_slot(kind, '{} {} {:02d}:{:02d}'.format(dia, kind, hh, mm), now)
                    prox.append(cand + timedelta(days=1))
                else:
                    prox.append(cand)
            now = R._br_now()
            time.sleep(max(1.0, min((min(prox) - now).total_seconds(), 3600)))
        except Exception:                                   # noqa: BLE001
            R.log.error('[manual-deals-ea] scheduler error:\n%s', traceback.format_exc())
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
                     name='manual-deals-ea-scheduler', daemon=True).start()
    _routes().log.info('[manual-deals-ea] scheduler iniciado (Other Publisher %02d:%02d · '
                       'FWD Start %02d:%02d BRT · dias úteis ANBIMA)',
                       *(domain.TIME['otherpub'] + domain.TIME['fwdstart']))
