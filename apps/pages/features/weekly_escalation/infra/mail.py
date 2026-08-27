# -*- coding: utf-8 -*-
"""O rascunho .eml da escalação semanal — montagem MIME e render."""
import traceback
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import render_template

from apps.pages.features.weekly_escalation import domain


def _routes():
    """Busca ATRASADA (ver `infra/persistence.py`)."""
    from apps.pages import routes
    return routes


def build(ref_fmt, blocks, to_list, cc_list):
    """O .eml em bytes, ou (None, erro)."""
    from email.mime.image import MIMEImage
    R = _routes()
    try:
        html = render_template('pages/email-template-weekly-escalation.html',
                               ref_date_fmt=ref_fmt, blocks=blocks,
                               current_year=datetime.now().year)
        msg = MIMEMultipart('related')
        msg['Subject'] = domain.subject(ref_fmt)
        msg['From'] = R.SHARED_MAILBOX
        if to_list:
            msg['To'] = ', '.join(to_list)
        if cc_list:
            msg['Cc'] = ', '.join(cc_list)
        msg['X-Unsent'] = '1'               # → Outlook abre o .eml como rascunho editável
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
        return msg.as_bytes(), None
    except Exception as e:                                  # noqa: BLE001
        R.log.error('[weekly-escalation] draft FAILED:\n%s', traceback.format_exc())
        return None, '{}: {}'.format(type(e).__name__, e)
