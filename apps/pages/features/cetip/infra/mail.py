# -*- coding: utf-8 -*-
"""O e-mail da rotina — montagem MIME com o anexo do dia e envio pelo relay."""
import os
import traceback
from datetime import datetime

from flask import render_template


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


def _send_cetip_email(to_list, cc_list, subject, greeting, message_html,
                      ref_date_fmt, saved, dest_folder='', attachments=None, missing=None):
    """Render the CETIP HTML template and send it FROM the OTC Tracker mailbox
    (SHARED_MAILBOX) with the embedded logo (cid:otc_logo) and optional file
    attachments. Best-effort — returns True on success or an error string."""
    from email.mime.image import MIMEImage
    from email.mime.base import MIMEBase
    from email import encoders
    attachments = attachments or []
    missing = missing or []
    try:
        attach_names = [os.path.basename(p) for p in attachments]
        html = render_template(
            'pages/email-template-cetip-saved.html',
            subject=subject, greeting=greeting, message_html=message_html,
            ref_date_fmt=ref_date_fmt, file_count=len(saved), saved_files=saved,
            missing_files=missing, missing_count=len(missing),
            attachment_names=attach_names, dest_folder=dest_folder,
            current_year=datetime.now().year)

        # mixed > [ related > [ alternative > [plain, html], logo ], attachment... ]
        msg = _R().MIMEMultipart('mixed')
        msg['Subject'] = subject
        msg['From'] = _R().SHARED_MAILBOX
        msg['To'] = ', '.join(to_list)
        if cc_list:
            msg['Cc'] = ', '.join(cc_list)

        related = _R().MIMEMultipart('related')
        alt = _R().MIMEMultipart('alternative')
        alt.attach(_R().MIMEText('CETIP files saved.', 'plain', 'utf-8'))
        alt.attach(_R().MIMEText(html, 'html', 'utf-8'))
        related.attach(alt)

        logo_path = _R()._get_logo_path()
        if logo_path:
            with open(logo_path, 'rb') as f:
                img = MIMEImage(f.read())
            img.add_header('Content-ID', '<otc_logo>')
            img.add_header('Content-Disposition', 'inline', filename='logo.png')
            related.attach(img)
        _R()._attach_email_gradient(related)
        msg.attach(related)

        for path in attachments:
            try:
                with open(path, 'rb') as f:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', 'attachment',
                                filename=os.path.basename(path))
                msg.attach(part)
            except Exception:
                _R().log.warning("[cetip] could not attach %s:\n%s", path, traceback.format_exc())

        recipients = list(to_list) + list(cc_list or [])
        with _R().smtplib.SMTP(_R().SMTP_HOST, _R().SMTP_PORT, timeout=20) as server:
            server.sendmail(_R().SHARED_MAILBOX, recipients, msg.as_string())
        _R().log.info("[cetip] e-mail '%s' sent to %s", subject, recipients)
        return True
    except Exception as e:
        _R().log.error("[cetip] e-mail '%s' FAILED:\n%s", subject, traceback.format_exc())
        return '{}: {}'.format(type(e).__name__, e)   # error string surfaced to the UI
