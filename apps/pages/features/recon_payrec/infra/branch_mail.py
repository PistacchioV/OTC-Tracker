# -*- coding: utf-8 -*-
"""O rascunho .eml da Branch Settlement Reverse Approval — render e MIME."""
from datetime import datetime
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import render_template


def _routes():
    from apps.pages import routes
    return routes


def build(recon_date_fmt, branch, source, dest, to_list, cc_list):
    """O .eml em bytes. Sem `From`: com `X-Unsent` o Outlook abre como rascunho
    na conta de quem baixou — a aprovação é pedida pela pessoa, não pela caixa
    do sistema."""
    R = _routes()
    direction_text = '{} pays {}'.format(source['name'], dest['name'])
    html = render_template('pages/email-template-branch-settlement.html',
                           recon_date_fmt=recon_date_fmt, branch=branch,
                           source=source, dest=dest, direction_text=direction_text,
                           check_ok=abs(branch.get('difference') or 0) < 1.0,
                           current_year=datetime.now().year)
    msg = MIMEMultipart('related')
    msg['Subject'] = 'Branch Settlement Reverse Approval — {} — BRL {:,.2f}'.format(
        recon_date_fmt, abs(branch.get('b2b_net') or 0))
    if to_list:
        msg['To'] = ', '.join(to_list)
    if cc_list:
        msg['Cc'] = ', '.join(cc_list)
    msg['X-Unsent'] = '1'                   # → o Outlook abre como rascunho editável
    alt = MIMEMultipart('alternative')
    alt.attach(MIMEText('Branch Settlement reverse approval for {}. View in an HTML client.'
                        .format(recon_date_fmt), 'plain', 'utf-8'))
    alt.attach(MIMEText(html, 'html', 'utf-8'))
    msg.attach(alt)
    logo_path = R._get_logo_path()
    if logo_path:
        with open(logo_path, 'rb') as f:
            limg = MIMEImage(f.read())
        limg.add_header('Content-ID', '<otc_logo>')
        limg.add_header('Content-Disposition', 'inline', filename='logo.png')
        msg.attach(limg)
    return msg.as_bytes()
