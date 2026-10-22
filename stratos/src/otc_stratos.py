"""OTC Tracker no Stratos: a ponte entre o `solution.py` do template e o `apps/`.

O template cria o `app` (Flask), o instrumenta (OpenTelemetry), autentica
(`StratosAuth`) e o serve sob o CONTEXT_ROOT. `mount` pendura o OTC Tracker
INTEIRO nesse mesmo objeto, em vez de servir um segundo app ao lado: assim a
autenticação e o rastreamento do Stratos valem para toda rota do OTC sem
nenhuma delas saber que existe um Stratos.

Três coisas o OTC supõe e o Stratos não dá, e cada uma tem a sua peça aqui:

  · Morar na raiz `/`. O app foi escrito assim (`fetch('/api/...')`,
    `href="/settings"`, ~550 + ~230 lugares), e no Stratos ele mora em
    `/76521/<solução>`. `_prefixa_resposta` reescreve o HTML que sai e injeta
    um shim que corrige as URLs que o JavaScript monta depois.
  · Login próprio (SID + código por e-mail). Aqui quem autentica é o Stratos:
    `_ponte_sso` abre a sessão do OTC a partir da identidade que ele valida.
  · `awmpy` (phonebook interno), que no servidor pode não existir.

Este arquivo, o `solution.py` e o `run.py` existem SÓ na branch
OTC-Tracker-Stratos; o código do app continua nascendo na dev.
"""
import json
import logging
import os
import re
import sys
import types

from flask import jsonify, redirect, render_template, request, session, url_for

log = logging.getLogger('otc_tracker')

# Fora da ponte de SSO: o estático, o health check (o balanceador o chama sem
# identidade nenhuma) e o diagnóstico de identidade do solution.py.
_SEM_SSO = {'static', 'health', 'stratos_whoami'}

# Telas do login próprio. Com o SSO quem chega nelas já está autenticado.
_TELAS_DE_LOGIN = {
    'pages_blueprint.index', 'pages_blueprint.sign_in_page',
    'pages_blueprint.sign_up_page', 'pages_blueprint.two_factor_page',
    'pages_blueprint.lock_screen_page',
}


def mount(app, stratos_auth, context_root):
    """Pendura o OTC Tracker no `app` do template. Chamado uma vez, no import.

    Reproduz o `apps.create_app` sobre um app que já existe, pelas mesmas
    funções dele — duplicar a lógica faria as duas subidas divergirem na
    primeira mudança da dev.
    """
    base = '/' + context_root.strip('/')
    _garante_awmpy()

    import apps as otc
    from apps.config import config_dict
    from apps.pages.database_access import (
        configure_database_access, validate_database_paths,
    )

    # Templates e estático moram em apps/, não ao lado do solution.py: é a raiz
    # que o `Flask(__name__)` do apps/__init__ teria. O loader de templates é
    # calculado na primeira renderização; se algo já o calculou, sai do cache.
    app.root_path = os.path.dirname(os.path.abspath(otc.__file__))
    app.__dict__.pop('jinja_loader', None)

    # Produção: o Stratos é HTTPS (o ProxyFix do template lê o X-Forwarded-Proto),
    # então o cookie seguro do ProductionConfig funciona aqui — na instância do
    # time, que é HTTP, não funcionaria.
    app.config.from_object(config_dict['Production'])
    app.config['SECRET_KEY'] = _chave_de_sessao(otc, app)
    app.config.update(
        # Os ~1.400 `{{ config.ASSETS_ROOT }}` dos templates já saem certos.
        ASSETS_ROOT=base + '/static',
        # O domínio do Stratos é de várias soluções: um cookie `session` no `/`
        # seria disputado com o de qualquer outro app Flask vizinho.
        SESSION_COOKIE_NAME='otc_tracker_session',
        SESSION_COOKIE_PATH=base,
        OTC_LIVE_RELOAD=False,
        TEMPLATES_AUTO_RELOAD=False,
        OTC_STRATOS=True,
        OTC_CONTEXT_ROOT=base,
    )

    otc._require_config_names(app.config)
    configure_database_access(app.config)
    validate_database_paths(tuple(app.config.get('DATABASE_ACCESS_PATHS') or ()))
    otc._seed_data_dir(app)
    otc._warn_wal_pendente()
    otc.register_blueprints(app)

    if os.getenv('OTC_STRATOS_SSO', '1').strip() != '0':
        # Entra no fim da lista do app: depois dos hooks do Stratos (a
        # identidade já validada) e antes dos do blueprint do OTC, que o Flask
        # roda depois de todos os do app.
        app.before_request(_ponte_sso(stratos_auth))
    else:
        log.warning('[stratos] OTC_STRATOS_SSO=0: vale o login proprio do OTC '
                    '(SID + codigo por e-mail)')

    # O primeiro da lista é o ÚLTIMO a rodar (o Flask percorre os after_request
    # de trás para a frente): a reescrita vê o corpo final.
    app.after_request_funcs.setdefault(None, []).insert(0, _prefixa_resposta(base))
    log.warning('[stratos] OTC Tracker montado em %s (dados em %s)',
                base, app.config.get('DATA_DIR'))
    return app


# ── Chave de sessão e awmpy ─────────────────────────────────────────────────

def _chave_de_sessao(otc, app):
    """SECRET_KEY do ambiente; sem ela, a do arquivo da máquina do OTC.

    Nunca a do template (`"76521-singing-moose-flask"`): ela está escrita no
    código de toda solução do Stratos, e quem a tem assina um cookie de sessão
    do OTC com o papel que quiser.
    """
    chave = (os.getenv('SECRET_KEY') or '').strip()
    if chave:
        return chave
    chave = otc._persisted_secret_key()
    log.warning('[stratos] SECRET_KEY ausente no ambiente — usando %s. Com mais de '
                'uma task, ou a cada deploy, a sessao se perde (o SSO a reabre, '
                'mas defina SECRET_KEY no task definition).',
                'a do arquivo ' + otc._secret_key_file() if chave
                else 'uma chave aleatoria deste processo')
    return chave or app.config['SECRET_KEY']


def _garante_awmpy():
    """O `routes` importa o `awmpy` no topo; sem ele o app não sobe.

    O phonebook só serve, com o SSO, para completar nome e e-mail de quem pede
    acesso pela primeira vez — e o Stratos já diz o nome. O substituto responde
    "indisponível" e o pedido de acesso segue com o que o Stratos informou.
    """
    try:
        import awmpy  # noqa: F401
    except ImportError:
        stub = types.ModuleType('awmpy')
        stub._otc_stratos_stub = True

        def get_phonebook_data(sid):
            raise RuntimeError('awmpy nao esta instalado neste servidor')

        stub.get_phonebook_data = get_phonebook_data
        sys.modules['awmpy'] = stub
        log.warning('[stratos] awmpy ausente: phonebook indisponivel')


# ── Ponte de SSO: a identidade do Stratos abre a sessão do OTC ──────────────

def _ponte_sso(stratos_auth):
    from apps.pages import routes   # só existe depois do register_blueprints

    def otc_stratos_sso():
        # Pelo ENDPOINT, não pelo caminho: `/static/data/...` é uma rota do
        # OTC que serve RefData e cadastros, e tem de passar pelo SSO.
        if request.endpoint in _SEM_SSO:
            return None
        sid, usuario = _identidade(stratos_auth, routes)
        if not sid:
            session.clear()
            return _negado(403, 'not_authorized',
                           'You are not authorized to view this page.')
        if session.get('authenticated') and \
                (session.get('user_sid') or '').strip().upper() == sid:
            # O IP deixa de ser critério: atrás do proxy do Stratos ele nem é o
            # do usuário, e quem identifica é o SSO. Carimbado a cada request, o
            # `enforce_session_ip` não derruba ninguém. A trava de tela também é
            # do login próprio — destravar pediria o código por e-mail.
            session['session_ip'] = routes.get_client_ip()
            session.pop('locked', None)
        else:
            resposta = _abre_sessao(routes, sid, usuario)
            if resposta is not None:
                return resposta
        if request.endpoint in _TELAS_DE_LOGIN:
            return redirect(url_for('pages_blueprint.dashboard'))
        return None

    return otc_stratos_sso


def _identidade(stratos_auth, routes):
    """(SID em maiúsculas, objeto do Stratos) — SID vazio = não autorizado."""
    try:
        usuario = stratos_auth.user()
    except Exception:                                       # noqa: BLE001
        log.warning('[stratos] stratos_auth.user() falhou', exc_info=True)
        return '', None
    if usuario is None or not getattr(usuario, 'authorized', False):
        return '', usuario
    sid = str(getattr(usuario, 'sid', '') or '').strip().upper()
    if not routes._validate_sid(sid):
        log.warning('[stratos] SID fora do formato vindo do Stratos: %r', sid)
        return '', usuario
    return sid, usuario


def _abre_sessao(routes, sid, usuario):
    """Sessão do OTC para quem o Stratos autenticou; `None` = pode seguir.

    O cadastro continua mandando: papel, páginas e status saem da tabela de
    usuários, como no login próprio. O master (por SID) é ativado sozinho —
    num servidor novo a tabela nasce vazia, e sem ele ninguém aprovaria o
    primeiro acesso.
    """
    session.clear()
    master = sid in routes._MASTER_SIDS
    cadastro = routes.get_user_by_sid(sid)
    if cadastro is None:
        nome = _registra(routes, sid, usuario, ativo=master)
        if not master:
            if request.path.startswith('/api/'):
                return _negado(403, 'account_pending', 'Your access request is pending approval.')
            return render_template('pages/auth-2-success-mail.html',
                                   segment='auth-2-success-mail',
                                   first_name=(nome.split() or [sid])[0])
        cadastro = routes.get_user_by_sid(sid)
    status = cadastro.get('Status') or 'Pending'
    if master and status != 'Active':
        routes.update_user_role_status(sid, cadastro.get('Role') or 'ADMIN', 'Active')
        cadastro = routes.get_user_by_sid(sid)
        status = 'Active'
    if status == 'Inactive':
        return _negado(403, 'account_inactive', 'Your account is inactive. '
                       'Please contact the OTC Tracker administrator.')
    if status != 'Active':
        return _negado(403, 'account_pending', 'Your access request is pending approval.')
    routes._set_session(cadastro)
    log.warning('[stratos] sessao aberta pelo SSO: SID=%s papel=%s', sid, session.get('user_role'))
    return None


def _registra(routes, sid, usuario, ativo):
    """Pedido de acesso de quem ainda não tem cadastro — o `_handle_new_user`
    do login próprio, com o nome do Stratos quando o phonebook não responde."""
    fone = {}
    if not getattr(sys.modules.get('awmpy'), '_otc_stratos_stub', False):
        fone = routes.get_user_data_from_phonebook(sid) or {}
    do_stratos = ' '.join(filter(None, [str(getattr(usuario, 'first_name', '') or '').strip(),
                                        str(getattr(usuario, 'last_name', '') or '').strip()]))
    nome = fone.get('nameFull') or do_stratos or sid
    email = fone.get('email') or str(getattr(usuario, 'email', '') or '')
    cargo = fone.get('positionName') or ''
    routes.insert_new_user(sid, nome, email, cargo, routes.get_client_ip())
    if ativo:
        routes.update_user_role_status(sid, 'ADMIN', 'Active')
    else:
        routes._create_notification(sid, nome, 'Access Request', 'Users',
                                    sid + ' — ' + cargo, target_role='ADMIN')
    log.warning('[stratos] pedido de acesso registrado: SID=%s (%s)', sid,
                'ativo' if ativo else 'pendente')
    return nome


def _negado(status, codigo, texto):
    # 403, nunca 401: no OTC todo 401 de /api/* é "sem sessão" e o
    # session-guard.js manda para o login — que aqui voltaria para cá.
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'code': codigo, 'params': {}, 'text': texto}), status
    return texto, status


# ── Prefixo: o OTC fala em `/x`, o Stratos o serve em `<base>/x` ────────────

def _prefixa_resposta(base):
    resto = re.escape(base[1:])
    # `/x` que ainda não tem a base: nem `//host` (protocolo relativo) nem o
    # que o `url_for` já gerou com o SCRIPT_NAME.
    sem_base = r'/(?!/|%s(?:[/"\'?#)]|$))' % resto
    atributo = re.compile(
        r'''(\s(?:href|src|action|formaction|poster|data-href|data-src|data-url)\s*=\s*["'])'''
        + sem_base, re.I)
    css_url = re.compile(r'''(url\(\s*["']?)''' + sem_base, re.I)
    # As Speculation Rules do menu excluem `/logout`, `/lock*` e `/api/*` da
    # pré-busca; o padrão é resolvido contra a origem, e sem a base ele deixaria
    # de excluir — o hover num item pré-buscaria o logout.
    especulacao = re.compile(r'''("href_matches"\s*:\s*")''' + sem_base)
    cabeca = re.compile(r'<head(?:\s[^>]*)?>', re.I)
    shim_pagina = '<script>' + _SHIM_PAGINA.replace('__BASE_JSON__', json.dumps(base)) + '</script>'
    shim_sw = _SHIM_SW.replace('__BASE_JSON__', json.dumps(base))
    com_base = base + r'/'

    def com_prefixo(url):
        if url.startswith('/') and not url.startswith('//') and not (
                url == base or url.startswith((base + '/', base + '?', base + '#'))):
            return base + url
        return url

    def otc_stratos_prefixo(response):
        local = response.headers.get('Location')
        if local:
            novo = com_prefixo(local)
            if novo != local:
                response.headers['Location'] = novo
        if response.direct_passthrough or response.is_streamed:
            return response
        if response.mimetype == 'text/html':
            html = response.get_data(as_text=True)
            novo = atributo.sub(r'\1' + com_base, html)
            novo = css_url.sub(r'\1' + com_base, novo)
            novo = especulacao.sub(r'\1' + com_base, novo)
            novo = cabeca.sub(lambda m: m.group(0) + shim_pagina, novo, count=1)
            if novo != html:
                response.set_data(novo)
        elif request.endpoint == 'pages_blueprint.service_worker' and response.status_code == 200:
            response.set_data(shim_sw + response.get_data(as_text=True))
        return response

    return otc_stratos_prefixo


# Roda antes de qualquer outro script da página. Corrige, na hora de usar, toda
# URL `/x` que o JavaScript do OTC monta: fetch, XHR (jQuery, DataTables),
# EventSource, sendBeacon, window.open, history, o service worker, os setters de
# href/src/action e o setAttribute. O que entra por innerHTML é corrigido pelo
# MutationObserver, e a navegação por `location.href = '/x'` pela Navigation API
# (Chrome/Edge; no Firefox esse caso fica de fora).
_SHIM_PAGINA = r"""(function () {
  if (window.__OTC_BASE__) return;
  var B = __BASE_JSON__, O = location.origin;
  window.__OTC_BASE__ = B;
  var EB = encodeURIComponent(B + '/'), EBAR = encodeURIComponent('/');
  function has(p) {
    return p === B || p.indexOf(B + '/') === 0 || p.indexOf(B + '?') === 0 || p.indexOf(B + '#') === 0;
  }
  function semBaseNaQuery(u) {
    var i = u.indexOf('?');
    if (i < 0) return u;
    return u.slice(0, i) + u.slice(i).split('=' + EB).join('=' + EBAR).split('=' + B + '/').join('=/');
  }
  function fix(u) {
    if (typeof u !== 'string' || !u) return u;
    if (u.charAt(0) === '/' && u.charAt(1) !== '/') return semBaseNaQuery(has(u) ? u : B + u);
    if (u.indexOf(O + '/') === 0) return O + fix(u.slice(O.length));
    return u;
  }
  function fixAny(u) { return (typeof URL !== 'undefined' && u instanceof URL) ? fix(u.href) : fix(u); }
  window.otcStratosUrl = fix;

  var F = window.fetch;
  if (F) window.fetch = function (r, o) {
    if (r && typeof r === 'object' && !(typeof URL !== 'undefined' && r instanceof URL) && typeof r.url === 'string') {
      var f = fix(r.url);
      if (f !== r.url) r = new Request(f, r);
    } else {
      r = fixAny(r);
    }
    return F.call(this, r, o);
  };
  var XO = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function () {
    var a = Array.prototype.slice.call(arguments);
    a[1] = fixAny(a[1]);
    return XO.apply(this, a);
  };
  ['EventSource', 'Worker', 'SharedWorker'].forEach(function (k) {
    var C = window[k];
    if (!C) return;
    var W = function (u, o) { return new C(fixAny(u), o); };
    W.prototype = C.prototype;
    window[k] = W;
  });
  if (navigator.sendBeacon) {
    var SB = navigator.sendBeacon.bind(navigator);
    navigator.sendBeacon = function (u, d) { return SB(fixAny(u), d); };
  }
  var WO = window.open;
  window.open = function () {
    var a = Array.prototype.slice.call(arguments);
    a[0] = fixAny(a[0]);
    return WO.apply(window, a);
  };
  ['pushState', 'replaceState'].forEach(function (k) {
    var H = history[k];
    history[k] = function () {
      var a = Array.prototype.slice.call(arguments);
      if (a.length > 2) a[2] = fixAny(a[2]);
      return H.apply(history, a);
    };
  });
  if (navigator.serviceWorker && navigator.serviceWorker.register) {
    var SR = navigator.serviceWorker.register.bind(navigator.serviceWorker);
    navigator.serviceWorker.register = function (u, o) {
      if (o && o.scope) o.scope = fixAny(o.scope);
      return SR(fixAny(u), o);
    };
  }

  var NOMES = ['href', 'src', 'action', 'formaction', 'poster'];
  var SA = Element.prototype.setAttribute;
  Element.prototype.setAttribute = function (n, v) {
    if (typeof v === 'string' && NOMES.indexOf(String(n).toLowerCase()) >= 0) v = fix(v);
    return SA.call(this, n, v);
  };
  [['HTMLAnchorElement', 'href'], ['HTMLAreaElement', 'href'], ['HTMLLinkElement', 'href'],
   ['HTMLImageElement', 'src'], ['HTMLScriptElement', 'src'], ['HTMLIFrameElement', 'src'],
   ['HTMLSourceElement', 'src'], ['HTMLMediaElement', 'src'], ['HTMLEmbedElement', 'src'],
   ['HTMLTrackElement', 'src'], ['HTMLInputElement', 'src'], ['HTMLFormElement', 'action'],
   ['HTMLButtonElement', 'formAction'], ['HTMLInputElement', 'formAction'],
   ['HTMLVideoElement', 'poster']].forEach(function (p) {
    var C = window[p[0]], d = C && Object.getOwnPropertyDescriptor(C.prototype, p[1]);
    if (!d || !d.set) return;
    Object.defineProperty(C.prototype, p[1], {
      configurable: true, enumerable: d.enumerable, get: d.get,
      set: function (v) { d.set.call(this, typeof v === 'string' ? fix(v) : v); }
    });
  });

  function fixEl(el) {
    if (!el || el.nodeType !== 1) return;
    for (var i = 0; i < NOMES.length; i++) {
      var v = el.getAttribute(NOMES[i]);
      if (v) { var f = fix(v); if (f !== v) SA.call(el, NOMES[i], f); }
    }
  }
  function scan(raiz) {
    fixEl(raiz);
    if (!raiz.querySelectorAll) return;
    var l = raiz.querySelectorAll('[href],[src],[action],[formaction],[poster]');
    for (var i = 0; i < l.length; i++) fixEl(l[i]);
  }
  new MutationObserver(function (ms) {
    for (var i = 0; i < ms.length; i++) {
      if (ms[i].type === 'attributes') fixEl(ms[i].target);
      else for (var j = 0; j < ms[i].addedNodes.length; j++) scan(ms[i].addedNodes[j]);
    }
  }).observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: NOMES });

  if (window.navigation && navigation.addEventListener) {
    navigation.addEventListener('navigate', function (e) {
      try {
        if (!e.cancelable || e.formData || e.downloadRequest) return;
        var u = new URL(e.destination.url);
        if (u.origin !== O || has(u.pathname)) return;
        e.preventDefault();
        location.assign(fix(u.pathname + u.search) + u.hash);
      } catch (x) {}
    });
  }
})();"""

# O mesmo, no service worker (`/sw.js`): o clique na notificação abre a página
# pelo caminho do aviso, e sem a base ela cairia fora da solução.
_SHIM_SW = r"""(function () {
  var B = __BASE_JSON__;
  function fix(u) {
    return (typeof u === 'string' && u.charAt(0) === '/' && u.charAt(1) !== '/' &&
            u !== B && u.indexOf(B + '/') !== 0) ? B + u : u;
  }
  var c = self.clients, ow = c && c.openWindow;
  if (ow) c.openWindow = function (u) { return ow.call(c, fix(u)); };
  var f = self.fetch;
  if (f) self.fetch = function (r, o) { return f.call(self, fix(r), o); };
})();
"""
