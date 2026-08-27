# -*- coding: utf-8 -*-
"""A infraestrutura de e-mail compartilhada: o relay, a caixa da mesa, o logo,
o gradiente (no-op documentado), o parse de listas de endereço, o download de
rascunhos .eml e o endereço absoluto dos botões.

Movida VERBATIM do `routes.py` (fase platform/ — CLAUDE.md §10). Os SENDERS
continuam com os donos — os de autenticação no `routes` (login é plataforma
que ainda mora lá) e os das rotinas nas suas features: o que é de todos é o
que está aqui.

Quem stuba SMTP nos testes troca `R.smtplib.SMTP` — e `smtplib` é UM objeto de
módulo, o mesmo para todo mundo que o importa, então o stub alcança qualquer
sender, more ele onde morar. O `APP_PORT` fica no `routes` (é a configuração da
instância, conferida pelo `check_bat_files.py`) e é alcançado por busca
atrasada.
"""
import logging
import os
import re

log = logging.getLogger('otc_tracker')

SMTP_HOST = "mailhost.jpmchase.net"
SMTP_PORT = 25
SHARED_MAILBOX = "otc.tracker@jpmorgan.com"


def _get_logo_path():
    from flask import current_app
    candidates = [
        os.path.join(current_app.root_path, 'static', 'images', 'logo.png'),
        os.path.join(os.path.dirname(current_app.root_path), 'static', 'images', 'logo.png'),
        os.path.join(current_app.root_path, '..', 'static', 'images', 'logo.png'),
    ]
    for path in candidates:
        path = os.path.normpath(path)
        if os.path.exists(path):
            return path
    return None


def _get_email_asset(filename):
    """Resolve an image under static/images (same lookup as the logo) for inline
    e-mail embedding. Returns the path or None."""
    from flask import current_app
    candidates = [
        os.path.join(current_app.root_path, 'static', 'images', filename),
        os.path.join(os.path.dirname(current_app.root_path), 'static', 'images', filename),
        os.path.join(current_app.root_path, '..', 'static', 'images', filename),
    ]
    for path in candidates:
        path = os.path.normpath(path)
        if os.path.exists(path):
            return path
    return None


def _attach_email_gradient(container):
    """No-op mantido pelos ~10 call sites. O cabeçalho dos e-mails NÃO usa mais
    a imagem de gradiente: o <v:rect> do Outlook a pintava ora mais estreito que
    a célula (faixa sólida à direita), ora na largura da janela inteira — o
    partial agora é bgcolor sólido + gradiente CSS (ver
    partials/email-gradient-header.html). Anexar o PNG sem nada referenciando o
    cid faria o Outlook listá-lo como anexo solto em todo e-mail do sistema."""
    return


def _parse_emails(raw):
    """Split a free-text address list (comma / semicolon / whitespace / newline)
    into a clean, de-duplicated list of addresses."""
    out, seen = [], set()
    for p in re.split(r'[,;\s]+', str(raw or '').strip()):
        p = p.strip()
        if p and p.lower() not in seen:
            seen.add(p.lower())
            out.append(p)
    return out


def _email_drafts_response(drafts, zip_name=None):
    """Return the drafts as a downloadable .eml / .zip so the file opens in the
    ACTING user's Outlook (server-side Outlook automation would only ever open on
    the server). From = the logged-in user's e-mail (resolved from their SID)."""
    from flask import make_response, session
    from apps.pages import otc_emails
    fname, mime, data = otc_emails.build_drafts_download(drafts, session.get('user_email'), zip_name=zip_name)
    resp = make_response(data)
    resp.headers['Content-Type'] = mime
    resp.headers['Content-Disposition'] = 'attachment; filename="{}"'.format(fname)
    resp.headers['X-Draft-Count'] = str(len(drafts))
    return resp


def _otc_app_url(path='/'):
    """Endereço ABSOLUTO de uma página do app, para o botão de um e-mail.

    O app nunca precisou disto: todo link até hoje era interno. Um e-mail,
    porém, é lido fora do navegador que abriu o app, então `url_for` (relativo)
    não serve, e `request.url_root` também não — o disparo automático roda numa
    thread sem request, e num Run feito na máquina de desenvolvimento ele
    devolveria `http://localhost:5005`, que é um link morto para quem recebe.

    Por isso o endereço é de CONFIGURAÇÃO (`OTC_TRACKER_URL` no .env). Sem ele
    vale o hostname da máquina na porta em que a instância roda — a **8051**,
    e não a 8050 que estava aqui: o `start-otc-tracker.bat` da pasta Application
    sobe nela, e todo botão de e-mail do app apontava para uma porta em que não
    há nada escutando.
    """
    from apps.pages import routes
    base = (os.getenv('OTC_TRACKER_URL', '') or '').strip().rstrip('/')
    if not base:
        import socket
        try:
            host = socket.gethostname() or 'localhost'
        except Exception:                                   # noqa: BLE001
            host = 'localhost'
        base = 'http://{}:{}'.format(host, os.getenv('OTC_TRACKER_PORT', str(routes.APP_PORT)))
    return base + (path if str(path).startswith('/') else '/' + str(path))
