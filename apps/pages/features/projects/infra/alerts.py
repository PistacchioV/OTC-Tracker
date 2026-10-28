# -*- coding: utf-8 -*-
"""Os arquivos e o envio dos alertas das iniciativas (§701).

No `control-panel/` (o `_DAILY_METRIC_DIR`, pelo armazém):
  · `initiative_alerts_recipients.json` — o TO (o box) e o CC do card;
  · `initiative_alerts_status.json`     — o desfecho do último disparo;
  · `initiative_alerts_keys.json`       — as CHAVES dos alertas que já saíram
    (cada alerta sai uma vez só; guarda as últimas 5 mil);
  · `initiative_alerts_sent.json`       — o claim do disparo diário.
"""
import os
import smtplib
import traceback
from datetime import datetime
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from apps.pages import data_store as _store  # noqa: E402

BOX_DEFAULT = 'brazil.otc.ops@jpmorgan.com'
_KEEP_KEYS = 5000


def _routes():
    from apps.pages import routes
    return routes


def _f(nome):
    return os.path.join(_routes()._DAILY_METRIC_DIR, nome)


def recipients_file():
    return _f('initiative_alerts_recipients.json')


def status_file():
    return _f('initiative_alerts_status.json')


def keys_file():
    return _f('initiative_alerts_keys.json')


def claim_file():
    return _f('initiative_alerts_sent.json')


def master_email():
    """O e-mail do master no cadastro (o CC padrão do card)."""
    R = _routes()
    for sid in sorted(R._MASTER_SIDS):
        try:
            u = R.get_user_by_sid(sid) or {}
        except Exception:                                   # noqa: BLE001
            u = {}
        if str(u.get('Email') or '').strip():
            return str(u['Email']).strip()
    return ''


def load_recipients():
    """{to, cc}: o salvo, e sem nada salvo o box no TO e o master no CC."""
    try:
        d = _store.read(recipients_file())
    except FileNotFoundError:
        d = None
    except Exception:                                       # noqa: BLE001
        _routes().log.warning('[initiative-alerts] destinatários ilegíveis:\n%s', traceback.format_exc())
        d = None
    if not isinstance(d, dict):
        return {'to': BOX_DEFAULT, 'cc': master_email()}
    return {'to': str(d.get('to') or ''), 'cc': str(d.get('cc') or '')}


def save_recipients(to, cc):
    _routes()._atomic_write_json(recipients_file(), {'to': str(to or '').strip(), 'cc': str(cc or '').strip()})


def load_status():
    try:
        d = _store.read(status_file())
    except Exception:                                       # noqa: BLE001
        return {}
    return d if isinstance(d, dict) else {}


def write_status(result):
    try:
        _routes()._atomic_write_json(status_file(), {
            'result': result, 'at': _routes()._br_now().strftime('%d/%m/%Y %H:%M:%S')})
    except Exception:                                       # noqa: BLE001
        _routes().log.warning('[initiative-alerts] status não gravado:\n%s', traceback.format_exc())


def sent_keys(strict=False):
    """As chaves que já saíram. `strict`: quem vai DISPARAR lê estrito —
    ocupado lido como vazio reenviaria tudo."""
    try:
        d = _store.read(keys_file())
    except FileNotFoundError:
        return set()
    except Exception:
        if strict:
            raise
        return set()
    return set(d if isinstance(d, list) else [])


def mark_sent(keys):
    R = _routes()
    with R._cache_lock:
        atuais = []
        try:
            d = _store.read(keys_file())
            atuais = d if isinstance(d, list) else []
        except FileNotFoundError:
            pass
        novas = atuais + [k for k in keys if k not in set(atuais)]
        R._atomic_write_json(keys_file(), novas[-_KEEP_KEYS:])


def claim(slot):
    R = _routes()
    return R._claim_daily_slot(claim_file(), R._DAILY_METRIC_DIR, slot, 16, 'initiative-alerts')


def release(slot):
    _routes()._release_daily_slot(claim_file(), slot, 'initiative-alerts')


def emails_of(sids):
    """{SID: e-mail} do cadastro, para quem está ativo e tem e-mail."""
    sids = sorted({str(s or '').strip().upper() for s in sids or []} - {''})
    if not sids:
        return {}
    R = _routes()
    conn = R.get_db_connection(readonly=True)
    try:
        linhas = conn.execute(
            'SELECT SID, Email, Status FROM users WHERE UPPER(SID) IN ({})'.format(
                ', '.join('?' for _ in sids)), sids).fetchall()
    finally:
        conn.close()
    return {str(s).strip().upper(): str(e).strip() for s, e, st in linhas
            if str(e or '').strip() and str(st or '').strip().upper() == 'ACTIVE'}


def send(subject, html, to_list, cc_list):
    """Envia pelo relay da casa, do SHARED_MAILBOX, com o timbre (cid) que o
    `_email_shell` pede (o do OTC Tracker, `logo='otc'`). → True ou o motivo (texto)."""
    from apps.pages import otc_emails
    R = _routes()
    if not to_list:
        return 'no_recipient'
    msg = MIMEMultipart('related')
    msg['Subject'] = subject
    msg['From'] = R.SHARED_MAILBOX
    msg['To'] = '; '.join(to_list)
    if cc_list:
        msg['Cc'] = '; '.join(cc_list)
    alt = MIMEMultipart('alternative')
    alt.attach(MIMEText(subject, 'plain', 'utf-8'))
    alt.attach(MIMEText(html, 'html', 'utf-8'))
    msg.attach(alt)
    for cid, nome, dado in otc_emails.logo_parts(html):
        img = MIMEImage(dado)
        img.add_header('Content-ID', '<' + cid + '>')
        img.add_header('Content-Disposition', 'inline', filename=nome)
        msg.attach(img)
    try:
        with smtplib.SMTP(R.SMTP_HOST, R.SMTP_PORT, timeout=30) as server:
            server.sendmail(R.SHARED_MAILBOX, list(to_list) + list(cc_list or []), msg.as_string())
    except Exception as exc:                                # noqa: BLE001
        R.log.warning('[initiative-alerts] envio falhou: %s', exc)
        return '%s: %s' % (type(exc).__name__, exc)
    return True


def now_br():
    return _routes()._br_now() if hasattr(_routes(), '_br_now') else datetime.now()
