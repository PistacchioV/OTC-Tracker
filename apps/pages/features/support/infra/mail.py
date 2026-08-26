# -*- coding: utf-8 -*-
"""Os dois avisos por e-mail do Support Center: abertura e encerramento.

Os dois são de MELHOR ESFORÇO e devolvem `True` ou a mensagem de erro. O ticket
JÁ está gravado quando isto roda, então uma falha de SMTP (estar fora da rede
JPM, por exemplo) não pode desfazer a criação nem o encerramento — ela só é
registrada e volta para a tela como `email_error`.

O cabeçalho dos dois é o `email-template-ticket-*.html`, e vale a regra da casa:
cor sólida + gradiente CSS, nunca imagem/VML (CLAUDE.md §2).
"""
import os
import smtplib
import traceback
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import render_template


# Ver a nota em `persistence.py`: a busca é LATE porque SMTP_HOST, o logo e o
# gradiente ainda moram no `routes.py`, e porque os testes trocam atributos lá.
def _routes():
    from apps.pages import routes
    return routes


OPS_CC = 'brazil.otc.ops@jpmorgan.com'
# Aviso de ABERTURA: quem trata os tickets é o master, então o e-mail de ticket
# novo vai para ele, com a caixa do OTC Tracker em cópia (o mesmo endereço que
# envia — fica o rastro na caixa compartilhada).
NEW_TO = os.getenv('TICKET_NEW_EMAIL_TO', 'giulliano.luccia@jpmorgan.com')


def _montar(R, assunto, para, cc, template, ticket):
    """A mensagem pronta: HTML, alternativa em texto, logo embutido, gradiente.

    O logo entra como `related` com Content-ID, que é o único jeito de o Outlook
    desktop mostrar imagem sem pedir download.
    """
    from email.mime.image import MIMEImage
    from apps.pages import otc_tickets
    html = render_template(template, ticket=ticket,
                           agent_name=otc_tickets.AGENT_NAME,
                           current_year=datetime.now().year)
    msg = MIMEMultipart('related')
    msg['Subject'] = assunto
    msg['From'] = R.SHARED_MAILBOX
    msg['To'] = para
    msg['Cc'] = cc
    alt = MIMEMultipart('alternative')
    alt.attach(MIMEText('Please view this notification in HTML.', 'plain', 'utf-8'))
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
    return msg


def send_closed(ticket):
    """Encerramento: requester no To, a caixa de OTC Ops em cópia."""
    R = _routes()
    to_addr = (ticket.get('requester_email') or '').strip()
    if not to_addr:
        R.log.warning('[tickets] %s closed without requester e-mail — no notice sent',
                      ticket.get('id'))
        return 'requester has no e-mail on file'
    try:
        msg = _montar(
            R,
            'OTC Tracker — Ticket #{} {}'.format(
                ticket.get('id') or '', (ticket.get('status') or 'Closed').lower()),
            to_addr, OPS_CC, 'pages/email-template-ticket-closed.html', ticket)
        with smtplib.SMTP(R.SMTP_HOST, R.SMTP_PORT, timeout=20) as server:
            server.sendmail(R.SHARED_MAILBOX, [to_addr, OPS_CC], msg.as_string())
        R.log.info('[tickets] closing notice sent for %s to=%s cc=%s',
                   ticket.get('id'), to_addr, OPS_CC)
        return True
    except Exception as e:
        R.log.error('[tickets] closing notice FAILED for %s:\n%s',
                    ticket.get('id'), traceback.format_exc())
        return '{}: {}'.format(type(e).__name__, e)


def send_opened(ticket):
    """Abertura: aviso para quem trata (`NEW_TO`), com a caixa do app em cópia."""
    R = _routes()
    try:
        msg = _montar(
            R,
            'OTC Tracker — Ticket #{} opened by {}'.format(
                ticket.get('id') or '',
                ticket.get('requester_name') or ticket.get('requester_sid') or ''),
            NEW_TO, R.SHARED_MAILBOX, 'pages/email-template-ticket-opened.html', ticket)
        with smtplib.SMTP(R.SMTP_HOST, R.SMTP_PORT, timeout=20) as server:
            server.sendmail(R.SHARED_MAILBOX, [NEW_TO, R.SHARED_MAILBOX], msg.as_string())
        R.log.info('[tickets] opening notice sent for %s to=%s cc=%s',
                   ticket.get('id'), NEW_TO, R.SHARED_MAILBOX)
        return True
    except Exception as e:
        R.log.error('[tickets] opening notice FAILED for %s:\n%s',
                    ticket.get('id'), traceback.format_exc())
        return '{}: {}'.format(type(e).__name__, e)
