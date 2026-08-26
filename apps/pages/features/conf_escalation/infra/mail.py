# -*- coding: utf-8 -*-
"""Os e-mails da cobrança."""
import smtplib
import traceback
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import render_template

from apps.pages.features.conf_escalation import domain


def _routes():
    """Busca ATRASADA (ver `infra/persistence.py`): o `_otc_app_url` (endereço
    absoluto para botão de e-mail) também é plataforma."""
    from apps.pages import routes
    return routes


def send(subject, scope, rows, to_list, ref, escalation=False):
    """Monta e envia UM e-mail do card. True ou a mensagem do erro.

    O contexto de aplicação envolve a MONTAGEM INTEIRA (não só o
    `render_template`): o `_get_logo_path` lê `current_app.root_path`, e
    envolver só o render troca um "Working outside of application context" por
    outro três linhas abaixo. Dentro do request do botão Run isto é no-op.
    """
    from email.mime.image import MIMEImage
    R = _routes()
    try:
        with R._app_context():
            html = render_template(
                'pages/email-template-confirmations-escalation.html',
                ref_date_fmt=ref.strftime('%d/%m/%Y'), scope=scope, rows=rows,
                escalation=escalation, monitor_url=R._otc_app_url(domain.MONITOR_PATH),
                current_year=datetime.now().year)
            msg = MIMEMultipart('related')
            msg['Subject'] = subject
            msg['From'] = R.SHARED_MAILBOX
            msg['To'] = ', '.join(to_list)
            alt = MIMEMultipart('alternative')
            alt.attach(MIMEText('Please view this report in HTML.', 'plain', 'utf-8'))
            alt.attach(MIMEText(html, 'html', 'utf-8'))
            msg.attach(alt)
            logo_path = R._get_logo_path()
            if logo_path:
                with open(logo_path, 'rb') as f:
                    limg = MIMEImage(f.read())
                limg.add_header('Content-ID', '<otc_logo>')
                limg.add_header('Content-Disposition', 'inline', filename='logo.png')
                msg.attach(limg)
            R._attach_email_gradient(msg)
        with smtplib.SMTP(R.SMTP_HOST, R.SMTP_PORT, timeout=20) as server:
            server.sendmail(R.SHARED_MAILBOX, to_list, msg.as_string())
        R.log.info('[conf-escalation] %s enviado — %d confirmação(ões) · to=%s',
                   scope, len(rows), to_list)
        return True
    except Exception as e:                                  # noqa: BLE001
        R.log.error('[conf-escalation] %s FALHOU:\n%s', scope, traceback.format_exc())
        return '{}: {}'.format(type(e).__name__, e)
