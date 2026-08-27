# -*- coding: utf-8 -*-
"""A autorização por página e por card: quem é master/admin, a allowlist do
`Page_Access` (com o cache por SID), o registro dos cards do Control Panel e o
pouso seguro de quem foi barrado.

Movida VERBATIM do `routes.py` (fase platform/ — CLAUDE.md §10). Os
`before_request` que APLICAM a regra (`enforce_page_access`,
`enforce_control_panel_cards`) continuam no `routes.py` — registro em
blueprint é casca — chamando o que está aqui pelos aliases.

O ESTADO (`_page_access_cache`) mora aqui e é mutado in place, então o alias
do `routes` continua vivo. O `get_db_connection` é alcançado por busca
atrasada: é a superfície que os testes trocam (`R.DB_PATH = tmp`), e o
`check_unlocked_reads.py` continua barrando estas funções por NOME, onde quer
que morem.
"""
import json
import logging
import os
import re
import threading
import time
import traceback

from flask import session

log = logging.getLogger('otc_tracker')

# Pages everyone can always reach regardless of configuration. The dashboards are
# NOT here — they are grantable like any other page (Main › Dashboards). '/users-profile'
# stays open so a fully-restricted user always has a safe landing (no redirect loop).
_ALWAYS_ALLOWED_PATHS = {'/users-profile', '/page-access'}


def _load_nav_urls():
    """Parse the sidebar template once for every side-nav-link href — the set of
    controllable pages. Robust to markup changes (matches the href only)."""
    try:
        fp = os.path.join(os.path.dirname(__file__), '..', '..', 'templates',
                          'partials', 'sidenav.html')
        with open(fp, encoding='utf-8') as fh:
            html = fh.read()
        urls = set(re.findall(r'<a[^>]*\bhref="(/[^"]+)"[^>]*\bclass="side-nav-link"', html))
        urls |= set(re.findall(r'<a[^>]*\bclass="side-nav-link"[^>]*\bhref="(/[^"]+)"', html))
        return urls - _ALWAYS_ALLOWED_PATHS
    except Exception:
        log.warning('[page-access] could not parse sidenav urls:\n%s', traceback.format_exc())
        return set()


_NAV_URLS = _load_nav_urls()

# Control Panel is access-controlled at the card level: instead of the single
# "/control-panel" page grant, each routine card can be granted on its own. Tokens
# are stored in the same allowlist as page URLs ("/control-panel#<id>").
#
# A ORDEM aqui é a da tela, seção por seção — é ela que monta a checklist do
# /page-access, e uma ordem diferente da do painel faz quem concede o acesso
# procurar o card numa lista que não se parece com a página que ele vai liberar.
# O que NÃO pode mudar é o `id`: ele é o token gravado no `Page_Access` de cada
# usuário (`/control-panel#<id>`), então renomeá-lo revoga o acesso em silêncio.
_CONTROL_PANEL_CARDS = [
    # Intraday Routines
    {'id': 'cetip',       'label': 'Save CETIP Files'},
    {'id': 'dealsmonitor', 'label': 'Deals Monitor — Pending Action'},
    {'id': 'confescalation', 'label': 'Confirmations Escalation'},
    # Settlement Reporting
    {'id': 'daily',       'label': 'Save Daily Settlement Files'},
    {'id': 'forecast',    'label': 'Settlement Forecast'},
    # Pending Confirmation Routines
    {'id': 'dailymetric', 'label': 'Daily Metric — Outstanding Confirmation Brazil OTC'},
    {'id': 'pendingspreadsheet', 'label': 'Pending Confirmations Spreadsheet Metrics'},
    {'id': 'weeklyescalation', 'label': 'Pending Confirmation — Weekly Escalation (CEM/EDG)'},
    {'id': 'signaturecollection', 'label': 'Pending Signature Confirmations — Collection'},
    # Economic Affirmation Routines
    {'id': 'manualdealsea', 'label': 'Manual Deals EA'},
    {'id': 'baccea',      'label': 'BACC EA Metrics'},
    {'id': 'mt300',       'label': 'MT300'},
    # Reference Data Routines
    {'id': 'contacts',    'label': 'Update Contacts'},
    # Application
    {'id': 'appversion',  'label': 'New Version Released'},
]
_CP_CARD_TOKENS = {'/control-panel#' + c['id'] for c in _CONTROL_PANEL_CARDS}
# API endpoint → the card it belongs to (for server-side enforcement).
_CP_ENDPOINT_CARD = {
    '/api/control-panel/cetip-settlement': 'cetip',
    '/api/control-panel/cetip-settlement/recipients': 'cetip',
    '/api/control-panel/daily-settlement-save': 'daily',
    '/api/control-panel/settlement-forecast/data': 'forecast',
    '/api/control-panel/settlement-forecast/email': 'forecast',
    '/api/control-panel/settlement-forecast/recipients': 'forecast',
    '/api/control-panel/import-contacts': 'contacts',
    '/api/control-panel/daily-metric/recipients': 'dailymetric',
    '/api/control-panel/daily-metric/run': 'dailymetric',
    '/api/control-panel/weekly-escalation/recipients': 'weeklyescalation',
    '/api/control-panel/weekly-escalation/run': 'weeklyescalation',
    '/api/control-panel/signature-collection/preview': 'signaturecollection',
    '/api/control-panel/signature-collection/generate': 'signaturecollection',
    '/api/control-panel/deals-monitor/recipients': 'dealsmonitor',
    '/api/control-panel/deals-monitor/run': 'dealsmonitor',
    '/api/control-panel/pending-spreadsheet/run': 'pendingspreadsheet',
    '/api/control-panel/pending-spreadsheet/status': 'pendingspreadsheet',
    '/api/control-panel/confirmations-escalation/recipients': 'confescalation',
    '/api/control-panel/confirmations-escalation/run': 'confescalation',
    '/api/control-panel/bacc-ea-metrics/recipients': 'baccea',
    '/api/control-panel/bacc-ea-metrics/run': 'baccea',
    '/api/control-panel/manual-deals-ea/recipients': 'manualdealsea',
    '/api/control-panel/manual-deals-ea/run': 'manualdealsea',
    '/api/control-panel/mt300/recipients': 'mt300',
    '/api/control-panel/mt300/run': 'mt300',
    '/api/control-panel/app-version/recipients': 'appversion',
    '/api/control-panel/app-version/run': 'appversion',
}


def _cp_page_allowed(allowed):
    """True if the user may open the Control Panel page at all (any card granted;
    a legacy whole-page '/control-panel' grant counts as all cards)."""
    return '/control-panel' in allowed or any(t in allowed for t in _CP_CARD_TOKENS)


def _cp_card_allowed(allowed, card_id):
    return '/control-panel' in allowed or ('/control-panel#' + card_id) in allowed


# A allowlist é a consulta mais repetida do app: o `enforce_page_access` a faz em
# TODA navegação e o sino a faz a cada consulta, por aba aberta. Ela quase nunca
# muda — só a tela `/page-access` a escreve —, então cada uma dessas idas ao
# banco relia o mesmo valor. Com o banco no share isso é ida e vida de rede no
# caminho crítico de cada request.
#
# Cache por SID, com invalidação na escrita e um TTL curto por cima. Os dois
# existem por razões diferentes: a invalidação cobre a mudança feita NESTE
# processo (o caso normal, e nele a revogação é imediata) e o TTL cobre a
# instância vizinha que editou o mesmo banco — sem ele, um acesso revogado no
# outro processo valeria pela vida deste. Trinta segundos é o atraso máximo de
# uma revogação vinda de fora, e é o preço de não perguntar ao share a cada
# clique.
_PAGE_ACCESS_TTL = 30.0
_page_access_cache = {}                      # sid → (expira_em, (configured, urls))
_page_access_lock = threading.Lock()


def _page_access_forget(sid=None):
    """Esquece o cache — de um SID, ou inteiro quando `sid` é None."""
    with _page_access_lock:
        if sid is None:
            _page_access_cache.clear()
        else:
            _page_access_cache.pop((sid or '').strip().upper(), None)


def _get_page_access(sid):
    """(configured, urls_set). configured=False → not set yet (full access);
    configured=True → the stored allowlist (possibly empty)."""
    if not sid:
        return (False, set())
    chave = sid.strip().upper()
    agora = time.time()
    with _page_access_lock:
        em_cache = _page_access_cache.get(chave)
    if em_cache and em_cache[0] > agora:
        # Devolve uma CÓPIA do conjunto: o chamador não pode alterar o cache
        # sem querer, e um `allowed.add(...)` numa rota viraria concessão
        # permanente para o processo inteiro.
        configurado, urls = em_cache[1]
        return (configurado, set(urls))
    resposta = _read_page_access(sid)
    with _page_access_lock:
        _page_access_cache[chave] = (agora + _PAGE_ACCESS_TTL, resposta)
    return (resposta[0], set(resposta[1]))


def _read_page_access(sid):
    """A allowlist como está no banco, sem cache."""
    from apps.pages import routes
    try:
        conn = routes.get_db_connection(readonly=True)
        try:
            row = conn.execute("SELECT Page_Access FROM users WHERE SID = ?", [sid]).fetchone()
        finally:
            conn.close()
    except Exception:
        return (False, set())
    raw = ((row[0] if row else '') or '').strip()
    if not raw:
        return (False, set())
    try:
        arr = json.loads(raw)
        if isinstance(arr, list):
            # A tela do File Interpreter mudou de URL (/file-interface →
            # /file-interpreter): o valor antigo gravado no cadastro segue
            # valendo — renomear página não pode revogar acesso em silêncio.
            # O item CGD virou a seção Onboarding, e o mesmo vale para ele.
            _renomeadas = {'/file-interface': '/file-interpreter',
                           '/cgd': '/onboarding'}
            return (True, set(_renomeadas.get(str(u), str(u)) for u in arr))
    except Exception:
        pass
    return (False, set())


def _set_page_access(sid, urls):
    from apps.pages import routes
    conn = routes.get_db_connection()
    try:
        payload = json.dumps(sorted(set(str(u) for u in (urls or []))))
        conn.execute("UPDATE users SET Page_Access = ? WHERE SID = ?", [payload, sid])
        conn.commit()
    finally:
        conn.close()
    # DEPOIS do commit: esquecendo antes, uma leitura concorrente repovoaria o
    # cache com o valor velho e a mudança só valeria daqui a um TTL.
    _page_access_forget(sid)


# Master users: top-of-hierarchy superusers pinned by SID (not by DB role, so the
# capability can't be granted to anyone else through user management). A master is
# always exempt from page-access restrictions and is the only one who can change an
# admin's (or another master's) access.
_MASTER_SIDS = {'E930179'}


def _session_is_master():
    return (session.get('user_sid') or '').strip().upper() in _MASTER_SIDS


def _session_is_admin():
    """Admin-console privileges. Master is a superset of admin."""
    return (session.get('user_role') or '').upper() == 'ADMIN' or _session_is_master()


def _safe_landing(allowed):
    """A page the user is actually allowed to reach — used when a blocked navigation
    is redirected, so it never bounces to a page they also can't see (the dashboards
    are now grantable, so '/dashboard' is not guaranteed). '/users-profile' is the
    always-open last resort."""
    for u in ('/dashboard', '/dashboard-2'):
        if u in allowed:
            return u
    if _cp_page_allowed(allowed):
        return '/control-panel'
    for u in sorted(allowed):
        if u in _NAV_URLS:
            return u
    return '/users-profile'


def _user_can_access_page(url):
    """True if the current session may reach a given sidebar page URL — same rule
    as enforce_page_access, for API endpoints that back a page. enforce_page_access
    skips '/api/' paths, so a mutating API behind a page must re-check here or a
    user without that page granted could call it directly. Master and unconfigured
    users always pass."""
    if _session_is_master():
        return True
    configured, allowed = _get_page_access(session.get('user_sid', ''))
    if not configured:
        return True
    return url in allowed
