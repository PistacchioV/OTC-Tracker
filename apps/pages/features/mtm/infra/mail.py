# -*- coding: utf-8 -*-
"""Os dois e-mails do MtM — o pedido de validação e o aviso de fim de processo."""
import os
import traceback

def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


def _send_mtm_validation_email(subject, html, logo_path, attach_paths):
    """SMTP-only MtM EOM validation e-mail to Brazil OTC Ops, attaching the
    Lawton/Atacama view files. HTML/logo resolved by the caller. Best-effort."""
    from email.mime.image import MIMEImage
    from email.mime.base import MIMEBase
    from email import encoders
    try:
        msg = _R().MIMEMultipart('mixed')
        msg['Subject'] = subject
        msg['From'] = _R().SHARED_MAILBOX
        msg['To'] = _R().CETIP_OTC_OPS_EMAIL
        related = _R().MIMEMultipart('related')
        alt = _R().MIMEMultipart('alternative')
        alt.attach(_R().MIMEText('MtM EOM validation files attached.', 'plain', 'utf-8'))
        alt.attach(_R().MIMEText(html, 'html', 'utf-8'))
        related.attach(alt)
        if logo_path:
            with open(logo_path, 'rb') as f:
                img = MIMEImage(f.read())
            img.add_header('Content-ID', '<otc_logo>')
            img.add_header('Content-Disposition', 'inline', filename='logo.png')
            related.attach(img)
        _R()._attach_email_gradient(related)
        msg.attach(related)
        for path in attach_paths:
            try:
                with open(path, 'rb') as f:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', 'attachment', filename=os.path.basename(path))
                msg.attach(part)
            except Exception:
                _R().log.warning('[mtm] could not attach %s:\n%s', path, traceback.format_exc())
        with _R().smtplib.SMTP(_R().SMTP_HOST, _R().SMTP_PORT, timeout=20) as server:
            server.sendmail(_R().SHARED_MAILBOX, [_R().CETIP_OTC_OPS_EMAIL], msg.as_string())
        _R().log.info('[mtm] validation e-mail sent to %s', _R().CETIP_OTC_OPS_EMAIL)
        return True
    except Exception:
        _R().log.error('[mtm] validation e-mail FAILED:\n%s', traceback.format_exc())
        return False


def _send_mtm_endprocess_email(subject, html, logo_path):
    """SMTP-only MtM EOM final-status e-mail to Brazil OTC Ops. Best-effort."""
    from email.mime.image import MIMEImage
    try:
        msg = _R().MIMEMultipart('mixed')
        msg['Subject'] = subject
        msg['From'] = _R().SHARED_MAILBOX
        msg['To'] = _R().CETIP_OTC_OPS_EMAIL
        msg['Cc'] = ', '.join(_R()._ACC_ENDPROC_CC)               # same From/To/Cc as accrual end-process
        related = _R().MIMEMultipart('related')
        alt = _R().MIMEMultipart('alternative')
        alt.attach(_R().MIMEText('MtM Swap EOM final status.', 'plain', 'utf-8'))
        alt.attach(_R().MIMEText(html, 'html', 'utf-8'))
        related.attach(alt)
        if logo_path:
            with open(logo_path, 'rb') as f:
                img = MIMEImage(f.read())
            img.add_header('Content-ID', '<otc_logo>')
            img.add_header('Content-Disposition', 'inline', filename='logo.png')
            related.attach(img)
        _R()._attach_email_gradient(related)
        msg.attach(related)
        recipients = [_R().CETIP_OTC_OPS_EMAIL] + _R()._ACC_ENDPROC_CC
        with _R().smtplib.SMTP(_R().SMTP_HOST, _R().SMTP_PORT, timeout=20) as server:
            server.sendmail(_R().SHARED_MAILBOX, recipients, msg.as_string())
        _R().log.info('[mtm] end-process e-mail sent to %s (cc %s)', _R().CETIP_OTC_OPS_EMAIL, _R()._ACC_ENDPROC_CC)
        return True
    except Exception:
        _R().log.error('[mtm] end-process e-mail FAILED:\n%s', traceback.format_exc())
        return False
