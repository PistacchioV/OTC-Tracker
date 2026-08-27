# -*- coding: utf-8 -*-
"""As escritas do card: gravar as listas, disparar a cobrança, o scheduler.

O laço roda aqui; quem o SOBE é o bloco de wiring do `routes.py`
(`_schedule_on_start('conf-escalation', …)`) — mesma razão do `bacc`.
"""
import threading
import time
import traceback
from datetime import timedelta

from apps.pages.features.conf_escalation import domain, queries
from apps.pages.features.conf_escalation.infra import mail, persistence


def _routes():
    """Busca ATRASADA (ver `infra/persistence.py`)."""
    from apps.pages import routes
    return routes


def save_recipients(d):
    persistence.save_recipients(d)


def _deliver(out, subject, scope, rows, raw_to, ref, escalation=False):
    """Um envio, com os dois motivos de NÃO enviar registrados no resumo.

    'empty' (nada parado) e 'no_recipient' (lista em branco) são desfechos
    diferentes e o card precisa distingui-los: o primeiro é a rotina rodando
    bem, o segundo é cobrança que não saiu de casa.
    """
    if not rows:
        out['skipped'].append({'scope': scope, 'subject': subject, 'reason': 'empty'})
        return
    to_list = _routes()._parse_emails(raw_to)
    if not to_list:
        out['skipped'].append({'scope': scope, 'subject': subject,
                               'reason': 'no_recipient'})
        return
    res = mail.send(subject, scope, rows, to_list, ref, escalation)
    if res is True:
        out['sent'].append({'scope': scope, 'subject': subject,
                            'rows': len(rows), 'to': len(to_list)})
    else:
        out['errors'].append({'scope': scope, 'subject': subject, 'error': res})


def run(mode='routine', ref=None):
    """Roda um modo e devolve o resumo.

    'routine' = o pacote de segunda/quinta (OTC + MO + os grupos de FO);
    'escalation' = só a escalação; 'both' = os dois; 'otc', 'mo' e
    'fo-<grupo>' = um e-mail só, que é o que o Run individual de cada item
    manda.

    O resumo é ESTRUTURADO (o que saiu, o que foi pulado e por quê) porque a
    frase é montada na tela, no idioma da aplicação — servidor manda a lista,
    não a frase.
    """
    R = _routes()
    ref = ref or R._br_now()
    rec = persistence.load_recipients()
    # O prazo é medido no MESMO dia que o e-mail carimba no cabeçalho. Medindo
    # contra o relógio e imprimindo o `ref`, um disparo remarcado sairia dizendo
    # uma data e pintando o vencido de outra — e a escalação, que é escolhida
    # pela luz do SLA, levaria uma fila que não é a do dia do relatório.
    otc, mo, grupos, esc, sem_grupo = queries.snapshot(
        ref.date() if hasattr(ref, 'date') else ref)
    out = {'sent': [], 'skipped': [], 'errors': [], 'unmatched': sem_grupo}
    if sem_grupo:
        R.log.warning('[conf-escalation] Pending FO sem grupo cadastrado: %s',
                      ', '.join(sem_grupo))
    rotina = mode in ('routine', 'both')
    if rotina or mode == 'otc':
        _deliver(out, domain.SUBJECT_OTC, 'OTC Ops · Pending OTC', otc,
                 rec['otc_to'], ref)
    if rotina or mode == 'mo':
        _deliver(out, domain.SUBJECT_MO, 'Sales Support · MO', mo, rec['sales_to'], ref)
    for g in grupos:
        if rotina or mode == 'fo-' + g['id']:
            # Lista PRÓPRIA do grupo: quem recebe a fila do EDG Corporate Swap
            # não é quem recebe a do EDG Swap.
            _deliver(out, g['subject'], 'Front Office · ' + g['label'],
                     g['rows'], rec.get(g['rec'], ''), ref)
    if mode in ('escalation', 'both'):
        _deliver(out, domain.SUBJECT_MO, 'Escalation · MO', esc,
                 rec['sales_escalation'], ref, escalation=True)
    return out


def run_manual(mode):
    """O Run do card: dispara agora, mesmo fora de segunda/quinta e mesmo em
    feriado — quem clicou decidiu. NÃO consome o claim do automático, e o
    desfecho entra na FAMÍLIA do modo ('escalation' ou 'routine'), não numa
    chave por botão: o card mostra duas linhas de status, e uma chave
    'fo-edg-swap' ficaria gravada sem ninguém para lê-la."""
    R = _routes()
    out = run(mode, R._br_now())
    persistence.write_status(
        'escalation' if mode == 'escalation' else 'routine', 'manual',
        ('error:' + '; '.join(e['error'] for e in out['errors'])) if out['errors']
        else ('sent:{}'.format(sum(s['rows'] for s in out['sent']))
              if out['sent'] else 'empty'), R._br_now())
    return out


def fire_slot(mode, slot, fired):
    """Manda o que o modo pede, se ninguém já mandou. True = o slot era deste
    processo.

    Só o ERRO devolve o slot: 'empty' (nada parado) é desfecho legítimo e não
    há o que reenviar, e sem destinatário o e-mail não sairia na retentativa
    também — quem resolve isso é o card, não o scheduler."""
    R = _routes()
    if not persistence.claim_slot(slot):
        return False
    out = run(mode, fired)
    if out['errors']:
        result = 'error:' + '; '.join(e['error'] for e in out['errors'])
        persistence.release_slot(slot)
    elif out['sent']:
        result = 'sent:{}'.format(sum(s['rows'] for s in out['sent']))
    elif any(s['reason'] == 'no_recipient' for s in out['skipped']):
        result = 'no_recipient'
    else:
        result = 'empty'
    R.log.info('[conf-escalation] %s de %s (BRT): %s', mode, slot, result)
    persistence.write_status(mode, slot, result, fired)
    return True


def scheduler_loop():
    R = _routes()
    while True:
        try:
            hh, mm = domain.time_of(persistence.TIME_RAW)
            now = R._br_now()
            cand = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if cand <= now:
                # Catch-up a cada volta, como no Deals Monitor: recupera o
                # disparo do dia quando o processo subiu depois do horário (a
                # instância reinicia várias vezes ao dia) e RETENTA o slot cujo
                # envio falhou e foi devolvido.
                dia = now.strftime('%Y-%m-%d')
                if R._pcx_is_bizday(now):
                    if queries.is_routine_day(now):
                        fire_slot('routine', '{} {:02d}:{:02d} routine'.format(dia, hh, mm), now)
                    fire_slot('escalation', '{} {:02d}:{:02d} escalation'.format(dia, hh, mm), now)
                nxt = cand + timedelta(days=1)
            else:
                nxt = cand
            now = R._br_now()
            time.sleep(max(1.0, min((nxt - now).total_seconds(), 3600)))
        except Exception:                                   # noqa: BLE001
            R.log.error('[conf-escalation] scheduler error:\n%s', traceback.format_exc())
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
                     name='conf-escalation-scheduler', daemon=True).start()
    _routes().log.info('[conf-escalation] scheduler iniciado (%02d:%02d BRT · rotina seg/qui, '
                       'escalação todo dia útil ANBIMA)',
                       *domain.time_of(persistence.TIME_RAW))
