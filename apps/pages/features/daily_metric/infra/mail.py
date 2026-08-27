# -*- coding: utf-8 -*-
"""O rascunho .eml do Daily Metric — montagem MIME e render, nada de leitura."""
import traceback
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import render_template

from apps.pages.features.daily_metric import domain


def _routes():
    """Busca ATRASADA (ver `infra/persistence.py`)."""
    from apps.pages import routes
    return routes


def build(ref_fmt, ctx, to_list, cc_list, bcc_list):
    """O .eml em bytes, ou (None, erro). `ctx` é o contexto já computado pelo
    comando — este módulo só renderiza e monta o MIME."""
    from email.mime.image import MIMEImage
    R = _routes()
    try:
        # Header gradient: always the inline cid: attachment
        # (_attach_email_gradient below), never a remote URL.
        html = render_template('pages/email-template-daily-metric.html',
                               ref_date_fmt=ref_fmt, grad_url='cid:otc_gradient',
                               current_year=datetime.now().year, **ctx)
        msg = MIMEMultipart('related')
        msg['Subject'] = domain.subject(ref_fmt)
        msg['From'] = R.SHARED_MAILBOX
        if to_list:
            msg['To'] = ', '.join(to_list)
        if cc_list:
            msg['Cc'] = ', '.join(cc_list)
        if bcc_list:
            # Unlike a real delivery (BCC only in the envelope), a draft needs the
            # header so Outlook pre-fills the Bcc field for the person to review.
            msg['Bcc'] = ', '.join(bcc_list)
        msg['X-Unsent'] = '1'               # → Outlook opens the .eml as an editable draft
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
        # Header gradient — referenced by VML so the gradient shows in Outlook
        # (which ignores CSS gradients). Modern clients keep the CSS gradient.
        R._attach_email_gradient(msg)
        return msg.as_bytes(), None
    except Exception as e:                                  # noqa: BLE001
        R.log.error('[daily-metric] draft FAILED:\n%s', traceback.format_exc())
        return None, '{}: {}'.format(type(e).__name__, e)
