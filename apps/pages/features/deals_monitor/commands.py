# -*- coding: utf-8 -*-
"""As escritas do New Deals Monitor — o envio do aviso de pendências
(19h/19h30 BRT), o disparo com claim de slot, o catch-up de restart e o
scheduler. As leituras vêm de `queries` e os arquivos de `infra/persistence`,
sempre pelo ATRIBUTO do módulo — é o que deixa os espiões do
check_ndm_pending_sched interceptarem cada travessia.
"""
import threading
import time
import traceback
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import render_template

from apps.pages.features.deals_monitor import domain, queries
from apps.pages.features.deals_monitor.infra import persistence


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


def _send_ndm_pending_email(ref, to_list, cc_list):
    """Envia o aviso de pendências do Monitor. Retorna True, 'empty' (nada
    pendente — não manda e-mail) ou a mensagem de erro."""
    from email.mime.image import MIMEImage
    try:
        # O contexto envolve a MONTAGEM INTEIRA, não só o `render_template`: o
        # `_get_logo_path` lê `current_app.root_path` e o gradiente do cabeçalho
        # também passa por aqui. Envolver só o render trocava um "Working outside
        # of application context" por outro, três linhas abaixo. Dentro do
        # request do botão Run isto é no-op (ver `_app_context`).
        with _R()._app_context():
            blocks, grand_total = queries._ndm_pending_blocks(ref)
            if not blocks:
                _R().log.info('[deals-monitor] %s: nada pendente, e-mail não enviado',
                         ref.strftime('%Y-%m-%d'))
                return 'empty'
            ref_fmt = ref.strftime('%d/%m/%Y')
            html = render_template('pages/email-template-deals-monitor.html',
                                   ref_date_fmt=ref_fmt, blocks=blocks,
                                   grand_total=grand_total, current_year=datetime.now().year)
            msg = MIMEMultipart('related')
            msg['Subject'] = 'Pending Action - Deals Monitor'
            msg['From'] = _R().SHARED_MAILBOX
            if to_list:
                msg['To'] = ', '.join(to_list)
            if cc_list:
                msg['Cc'] = ', '.join(cc_list)
            alt = MIMEMultipart('alternative')
            alt.attach(MIMEText('Please view this report in HTML.', 'plain', 'utf-8'))
            alt.attach(MIMEText(html, 'html', 'utf-8'))
            msg.attach(alt)
            logo_path = _R()._get_logo_path()
            if logo_path:
                with open(logo_path, 'rb') as f:
                    limg = MIMEImage(f.read())
                limg.add_header('Content-ID', '<otc_logo>')
                limg.add_header('Content-Disposition', 'inline', filename='logo.png')
                msg.attach(limg)
            _R()._attach_email_gradient(msg)
        with _R().smtplib.SMTP(_R().SMTP_HOST, _R().SMTP_PORT, timeout=20) as server:
            server.sendmail(_R().SHARED_MAILBOX, to_list + cc_list, msg.as_string())
        _R().log.info('[deals-monitor] aviso de pendências enviado — ref=%s · %d item(ns) '
                 'em %d tipo(s) · to=%s cc=%s', ref.strftime('%Y-%m-%d'), grand_total,
                 len(blocks), to_list, cc_list)
        return True
    except Exception as e:                                  # noqa: BLE001
        _R().log.error('[deals-monitor] aviso de pendências FALHOU:\n%s', traceback.format_exc())
        return '{}: {}'.format(type(e).__name__, e)


_ndm_pending_scheduler_started = False

_ndm_pending_scheduler_lock = threading.Lock()


def _ndm_pending_disparar(slot, fired):
    """Manda o aviso de um slot, se ninguém já mandou. True quando o slot era
    deste processo (reivindicado agora).

    Sem destinatário e com falha de envio o slot é DEVOLVIDO: nos dois casos o
    aviso não saiu, e queimar o horário faria o problema desaparecer da fila em
    vez de ser tentado de novo. 'empty' (nada pendente) é desfecho legítimo e
    mantém a reserva — não há o que reenviar."""
    if not persistence._ndm_pending_claim_slot(slot):
        return False
    rec = persistence._load_ndm_pending_recipients()
    to_list, cc_list = _R()._parse_emails(rec['to']), _R()._parse_emails(rec['cc'])
    if not (to_list or cc_list):
        _R().log.warning('[deals-monitor] sem destinatário configurado — aviso pulado')
        persistence._ndm_pending_status_write(slot, 'sem destinatário configurado', fired)
        persistence._ndm_pending_release_slot(slot)
        return True
    res = _send_ndm_pending_email(fired, to_list, cc_list)
    # O resultado vai para o log SEMPRE: quando o aviso não chega, a primeira
    # pergunta é se ele não foi enviado ou se não havia pendência ('empty'), e
    # sem esta linha não dava para saber.
    _R().log.info('[deals-monitor] aviso de %s (BRT): %s', slot,
             'enviado' if res is True else res)
    persistence._ndm_pending_status_write(slot, 'enviado' if res is True else str(res), fired)
    if res is not True and res != 'empty':
        persistence._ndm_pending_release_slot(slot)
    return True


def _ndm_pending_catch_up(times):
    """Slots de HOJE que já passaram e ninguém reivindicou.

    A instância do time é reiniciada várias vezes por dia (o reloader fica
    desligado, então todo pull pede restart). Subindo depois das 19h30, o loop
    dormia até o dia seguinte e o aviso do dia simplesmente não saía — sem erro
    nenhum no log. O arquivo de claim é que garante que isto não vire e-mail
    repetido quando há mais de um restart."""
    now = _R()._br_now()
    for hh, mm in times:
        cand = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if cand > now:
            continue
        slot = '{} {:02d}:{:02d}'.format(now.strftime('%Y-%m-%d'), hh, mm)
        try:
            if _ndm_pending_disparar(slot, now):
                _R().log.info('[deals-monitor] aviso de %s recuperado no start '
                         '(processo subiu depois do horário)', slot)
        except Exception:                              # noqa: BLE001
            _R().log.error('[deals-monitor] catch-up de %s falhou:\n%s',
                      slot, traceback.format_exc())


def _ndm_pending_scheduler_loop():
    times = domain._ndm_pending_times()
    while True:
        try:
            # O catch-up roda a CADA volta, não só no start. Ele só dispara
            # slots de hoje que já passaram e que ninguém reivindicou — então
            # num dia normal não faz nada, e é ele que RETENTA o horário cujo
            # envio falhou e foi devolvido. Sem isto, uma queda de SMTP às 19h00
            # custava o aviso do dia inteiro.
            _ndm_pending_catch_up(times)
            now = _R()._br_now()
            # Próximo horário de hoje que ainda não passou; se todos passaram,
            # o primeiro de amanhã.
            nxt = None
            for hh, mm in times:
                cand = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
                if cand > now:
                    nxt = cand
                    break
            if nxt is None:
                hh, mm = times[0]
                nxt = (now + timedelta(days=1)).replace(hour=hh, minute=mm,
                                                        second=0, microsecond=0)
            time.sleep(max(1.0, (nxt - now).total_seconds()))
            fired = _R()._br_now()
            slot = '{} {:02d}:{:02d}'.format(fired.strftime('%Y-%m-%d'),
                                             nxt.hour, nxt.minute)
            if not _ndm_pending_disparar(slot, fired):
                time.sleep(60)
        except Exception:
            _R().log.error('[deals-monitor] scheduler error:\n%s', traceback.format_exc())
            time.sleep(60)


def _ndm_pending_start_scheduler():
    global _ndm_pending_scheduler_started
    with _ndm_pending_scheduler_lock:
        if _ndm_pending_scheduler_started:
            return
        _ndm_pending_scheduler_started = True
    threading.Thread(target=_ndm_pending_scheduler_loop,
                     name='deals-monitor-pending-scheduler', daemon=True).start()
    _R().log.info('[deals-monitor] scheduler de pendências iniciado (%s BRT · '
             'agora são %s no servidor / %s em Brasília)',
             ', '.join('{:02d}:{:02d}'.format(h, m) for h, m in domain._ndm_pending_times()),
             datetime.now().strftime('%H:%M'), _R()._br_now().strftime('%H:%M'))
