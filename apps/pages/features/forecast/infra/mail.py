# -*- coding: utf-8 -*-
"""O e-mail do Settlement Forecast.

⚠️ VERRUGA PRESERVADA de propósito (ver check_forecast_api.py): os cabeçalhos
To/Cc levam as listas salvas no card, mas o ENVELOPE (sendmail) vai para
CETIP_OTC_OPS_EMAIL + _ACC_ENDPROC_CC. Consertar é mudança de comportamento —
não pertence à extração.
"""
import smtplib
import traceback
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import render_template


def _routes():
    """Busca ATRASADA — ver `features/support/infra/persistence.py`."""
    from apps.pages import routes
    return routes


def send(payload, images, to_list, cc_list):
    """Render the Settlement Forecast HTML report and e-mail it to the saved
    recipients (TO/CC) with the chart PNGs embedded (cid). `images` maps cid → raw
    PNG bytes. Best-effort — returns True on success or an error string."""
    from email.mime.image import MIMEImage
    R = _routes()
    try:
        html = render_template(
            'pages/email-template-settlement-forecast.html',
            ref_date_fmt=payload['ref_date_fmt'],
            date_labels=payload['date_labels'],
            products=payload['products'],
            entities=payload['entities'],
            col_totals=payload['col_totals'],
            grand_total=payload['grand_total'],
            has_chart_product=bool(images.get('fcst_product')),
            has_chart_entity=bool(images.get('fcst_entity')),
            has_chart_mix=bool(images.get('fcst_mix')),
            current_year=datetime.now().year)

        msg = MIMEMultipart('mixed')
        msg['Subject'] = 'Settlement Forecast'
        msg['From'] = R.SHARED_MAILBOX
        if to_list:
            msg['To'] = ', '.join(to_list)
        if cc_list:
            msg['Cc'] = ', '.join(cc_list)

        related = MIMEMultipart('related')
        alt = MIMEMultipart('alternative')
        alt.attach(MIMEText('Settlement Forecast — please view in HTML.', 'plain', 'utf-8'))
        alt.attach(MIMEText(html, 'html', 'utf-8'))
        related.attach(alt)

        logo_path = R._get_logo_path()
        if logo_path:
            with open(logo_path, 'rb') as f:
                limg = MIMEImage(f.read())
            limg.add_header('Content-ID', '<otc_logo>')
            limg.add_header('Content-Disposition', 'inline', filename='logo.png')
            related.attach(limg)

        R._attach_email_gradient(related)      # Outlook/VML gradient fallback (cid)

        for cid, data in images.items():
            if not data:
                continue
            cimg = MIMEImage(data)
            cimg.add_header('Content-ID', '<{}>'.format(cid))
            cimg.add_header('Content-Disposition', 'inline', filename='{}.png'.format(cid))
            related.attach(cimg)
        msg.attach(related)

        recipients = [R.CETIP_OTC_OPS_EMAIL] + R._ACC_ENDPROC_CC
        with smtplib.SMTP(R.SMTP_HOST, R.SMTP_PORT, timeout=20) as server:
            server.sendmail(R.SHARED_MAILBOX, recipients, msg.as_string())
        R.log.info("[forecast] e-mail sent to %s (cc %s)", R.CETIP_OTC_OPS_EMAIL, R._ACC_ENDPROC_CC)
        return True
    except Exception as e:
        R.log.error("[forecast] e-mail FAILED:\n%s", traceback.format_exc())
        return '{}: {}'.format(type(e).__name__, e)

