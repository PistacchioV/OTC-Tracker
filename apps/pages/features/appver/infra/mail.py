# -*- coding: utf-8 -*-
"""O e-mail do aviso de versão nova."""
import smtplib
import traceback
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import render_template

from apps.pages.features.appver import domain
from apps.pages.features.appver.infra import persistence


def _routes():
    """Busca ATRASADA (ver `infra/persistence.py`)."""
    from apps.pages import routes
    return routes


def send(versao, usuarios, cc_list):
    """Monta e envia UMA mensagem. True, ou o texto do erro.

    Uma mensagem só, com todo mundo no To, e não uma por pessoa: são dezenas de
    destinatários, e N envios transformariam uma falha de SMTP no meio da lista
    em "metade da mesa foi avisada" — desfecho que ninguém consegue reportar nem
    repetir com segurança. Em troca, o corpo não é personalizado.

    O `with _app_context()` envolve a montagem INTEIRA e não só o
    `render_template`: o `_get_logo_path` lê `current_app.root_path` (CLAUDE.md
    §7). Aqui o envio é sempre dentro de um request, então é no-op — fica pelo
    mesmo motivo dos outros: o dia em que alguém agendar esta rotina.
    """
    from email.mime.image import MIMEImage
    R = _routes()
    to_list = [e for _, e in usuarios]
    try:
        with R._app_context():
            html = render_template('pages/email-template-new-version.html',
                                   version=versao,
                                   starter=domain.STARTER,
                                   app_shortcut=persistence.SHORTCUT,
                                   app_shortcut_href=domain.href(persistence.SHORTCUT),
                                   app_local=persistence.local_url(),
                                   current_year=datetime.now().year)
            msg = MIMEMultipart('related')
            msg['Subject'] = domain.subject(versao)
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
        R.log.error('[app-version] envio falhou:\n%s', traceback.format_exc())
        return '{}: {}'.format(type(e).__name__, e)
