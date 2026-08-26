# -*- coding: utf-8 -*-
"""O e-mail da mensagem MT300."""
import smtplib
import traceback
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import render_template

from apps.pages.features.mt300 import domain


def _routes():
    """Busca ATRASADA (ver `infra/persistence.py`): o contexto de aplicação, o
    logo, o cabeçalho de e-mail e os endereços SMTP são plataforma."""
    from apps.pages import routes
    return routes


def send(rows, to_list, cc_list, ref):
    """Monta e envia. True, ou a mensagem do erro.

    O `with _app_context()` envolve a montagem INTEIRA e não só o
    `render_template`: o `_get_logo_path` lê `current_app.root_path`, e envolver
    só o render troca um erro de contexto por outro três linhas abaixo. Dentro do
    request do botão Run é no-op — é por isso que o Run funciona e só o
    automático morreria (CLAUDE.md §7)."""
    from email.mime.image import MIMEImage
    R = _routes()
    try:
        with R._app_context():
            html = render_template('pages/email-template-mt300.html',
                                   ref_date_fmt=ref.strftime('%d/%m/%Y'),
                                   rows=rows, current_year=datetime.now().year)
            msg = MIMEMultipart('related')
            msg['Subject'] = domain.subject(ref)
            msg['From'] = R.SHARED_MAILBOX
            msg['To'] = ', '.join(to_list)
            if cc_list:
                msg['Cc'] = ', '.join(cc_list)
            alt = MIMEMultipart('alternative')
            alt.attach(MIMEText('Please view this message in HTML.', 'plain', 'utf-8'))
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
        with smtplib.SMTP(R.SMTP_HOST, R.SMTP_PORT, timeout=30) as server:
            server.sendmail(R.SHARED_MAILBOX, to_list + cc_list, msg.as_string())
        return True
    except Exception as e:                                  # noqa: BLE001
        R.log.error('[mt300] envio falhou:\n%s', traceback.format_exc())
        return '{}: {}'.format(type(e).__name__, e)
