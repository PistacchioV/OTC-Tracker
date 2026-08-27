# -*- coding: utf-8 -*-
"""As escritas do card: gravar o Cc e mandar o aviso."""
import traceback

from apps.pages.features.appver.infra import mail, persistence


def _routes():
    """Busca ATRASADA (ver `infra/persistence.py`)."""
    from apps.pages import routes
    return routes


def save_recipients(d):
    persistence.save_recipients(d)


def run(cc_raw=None):
    """Uma corrida. Desfechos SEPARADOS, porque pedem ações diferentes:
    `no_version` (o link.txt não respondeu qual é a versão — publicar de novo) e
    `no_recipient` (ninguém ativo no cadastro — aprovar os usuários)."""
    R = _routes()
    versao, _bruto, erro = persistence.read_link()
    if not versao:
        return {'sent': False, 'reason': 'no_version', 'error': erro,
                'path': persistence.LINK_FILE, 'to': 0}
    usuarios = persistence.active_users()
    if not usuarios:
        return {'sent': False, 'reason': 'no_recipient', 'version': versao, 'to': 0}
    cc_list = [c for c in R._parse_emails(cc_raw if cc_raw is not None
                                          else persistence.load_recipients().get('cc'))
               if c.lower() not in {e.lower() for _, e in usuarios}]
    res = mail.send(versao, usuarios, cc_list)
    if res is True:
        return {'sent': True, 'version': versao, 'to': len(usuarios), 'cc': len(cc_list)}
    return {'sent': False, 'reason': 'error', 'error': res, 'version': versao,
            'to': len(usuarios), 'cc': len(cc_list)}


def run_manual(payload=None):
    """O botão do card: grava o Cc que vier no payload, roda AGORA e grava o
    desfecho no status — inclusive os negativos, porque a linha de status do
    card é onde se descobre por que o aviso não saiu."""
    R = _routes()
    payload = payload or {}
    if 'cc' in payload:
        try:
            persistence.save_recipients(payload)
        except Exception:                                   # noqa: BLE001
            R.log.error('[app-version] save recipients failed:\n%s', traceback.format_exc())
    out = run(payload.get('cc'))
    if out['sent']:
        persistence.write_status('sent:{}:{}'.format(out['version'], out['to']), R._br_now())
    elif out.get('reason') in ('no_version', 'no_recipient'):
        persistence.write_status(out['reason'], R._br_now())
    else:
        persistence.write_status('error', R._br_now())
    return out
