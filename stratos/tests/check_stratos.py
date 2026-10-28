"""Confere o OTC Tracker montado no template do Stratos, no layout do destino.

Monta num diretório temporário o que o stratos-sync.bat entrega ao
singing-moose-flask — src/solution.py, src/run.py, src/otc_stratos.py e
src/apps/ — e sobe o `solution.py` com um Stratos de MENTIRA (o stratos-blocks
é interno do JPM). O que se confere:

  1. os blocos DO NOT DELETE do solution.py e do run.py são os do template, o
     requirements.txt gerado está em dia e nada cita o proxy on-premise que o
     pre-push scan do `stratos push` recusa;
  2. a subida e o SSO: o import do solution.py volta na hora, e o portão
     responde o health check, a página "starting" e o erro de uma subida que
     quebrou; sem identidade é 403; o master entra num banco vazio; quem não
     tem cadastro vira pedido de acesso; trocar de SID troca a sessão; o Lock
     Screen trava e o SID do SSO destrava; o Logout para na tela de saída sem
     derrubar o login do Stratos; o phonebook: as formas da resposta do
     `get_phonebook_data([sid])` (registro de OUTRO SID levanta); com ele, o
     `awmpy` é a casca dele, o pedido de acesso nasce com nome, e-mail e cargo
     e o master com nome e e-mail; sem phonebook nenhum, o app sobe e o pedido
     leva o nome que o Stratos informa; a raiz dos dados: sem o
     OTC_STRATOS_ROOT ela sai do `get_shared_drive` (o EFS da solução), a
     variável vence, e sem os dois fica no /tmp avisando;
  3. o prefixo: Location, HTML (href/src/action, Speculation Rules), estático,
     cookie no caminho da solução, o shim na página e no /sw.js;
  4. o shim de JavaScript, no node (se houver);
  5. o `exporta_dados.py` (o pacote dos bancos para o Stratos), pelo
     `check_exporta_dados.py` — ele usa por dentro o `recover_duckdb_wal.py` da
     dev, e um helper renomeado lá quebra a exportação sem quebrar a dev;
  6. a ponte do share (`ponte_share.py` + `src/ponte_comum.py`), pelo
     `check_ponte.py`; a chegada dos bancos, `check_pacotes_dados.py`;
  7. a prova das travas no Shared Drive (`src/prova_travas.py`): a rota só do
     master, aqui, e o resto pelo `check_prova_travas.py`;
  8. o e-mail pelo Email block (`src/email_stratos.py`): o código de
     verificação do app montado sai pelo `stratosblocks.email.send`, aqui, e a
     tradução da mensagem pelo `check_email_stratos.py`.
  9. a Athena pelo proxy do Stratos (`src/proxy_interno.py`): o
     `athena_api.build_session` embrulhado na subida, aqui, e o desvio por host
     pelo `check_proxy_interno.py`.
 10. o token do IDA no lugar do Kerberos (`src/ida_token.py`): pelo
     `check_ida_token.py`.
 11. as fotos dos usuários do Shared Drive (`src/fotos_stratos.py`,
     `envia_fotos.py`): pelo `check_fotos_stratos.py`.

    OTC_SHARED_DRIVE_ROOT=/tmp/otc-share python stratos/tests/check_stratos.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types

AQUI = os.path.dirname(os.path.abspath(__file__))
STRATOS = os.path.dirname(AQUI)
RAIZ = os.path.dirname(STRATOS)
BASE = '/76521/otc-tracker-ops-ai-citizen'
MARCA = '########### DO NOT DELETE ###########'

FALHAS = []
EMAILS = []   # o que o Email block de mentira recebeu


def ok(cond, msg):
    print(('ok    ' if cond else 'FAIL  ') + msg)
    if not cond:
        FALHAS.append(msg)


# ── 1. Template ─────────────────────────────────────────────────────────────

# O solution.py do template do Stratos, verbatim. Só os trechos entre as marcas
# DO NOT DELETE e o cabeçalho (até "ADD YOUR OTHER IMPORTS") são conferidos.
TEMPLATE_SOLUTION = '''# file solution.py
# OTEL bootstrap MUST come first — installs the global TracerProvider before
# Flask is imported so its instrumentor can wire into an untraced app.
from stratosblocks.web.otel import bootstrap_otel

bootstrap_otel()

from flask import Flask, session, Response, request
from stratosblocks.authentication.web import StratosAuth, StratosDispatcherMiddleware
from stratosblocks.web.logging import enable_logging
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from opentelemetry import trace
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
import json
########### ADD YOUR OTHER IMPORTS HERE ###########

# Enable logging level. Default is ERROR but can be set to DEBUG, INFO or WARN
# e.g. enable_logging("DEBUG")
logger = enable_logging("INFO")

########### DO NOT DELETE ###########
CONTEXT_ROOT = '/76521/otc-tracker-ops-ai-citizen'

def create_app():
    flask_app = Flask(__name__)
    flask_app.wsgi_app = ProxyFix(flask_app.wsgi_app, x_proto=1)
    flask_app.config['SECRET_KEY'] = "76521-singing-moose-flask"
    flask_app.config['routes_pathname_prefix'] = CONTEXT_ROOT + '/'
    flask_app.wsgi_app = StratosDispatcherMiddleware(flask_app.wsgi_app, DispatcherMiddleware(
        Response('Not Found', status=404),
        {CONTEXT_ROOT: flask_app.wsgi_app}
    ))
    return flask_app

app = create_app()

# Framework instrumentation. Flask instrumentor wires ASGI-style middleware
# into the WSGI app; RequestsInstrumentor auto-traces outbound calls.
FlaskInstrumentor().instrument_app(app)
RequestsInstrumentor().instrument()

stratos_auth = StratosAuth(app, 76521)

@app.before_request
def add_post_body_to_trace():
    try:
        from flask import has_request_context

        if has_request_context() and request.method == 'POST':
            span = trace.get_current_span()
            if span.is_recording():
                try:
                    post_body = request.get_json()
                    if post_body:
                        span.set_attribute('http.request.post_body', json.dumps(post_body))
                except Exception:
                    try:
                        post_data = request.get_data(as_text=True)
                        if post_data:
                            span.set_attribute('http.request.post_body', post_data)
                    except Exception:
                        pass
    except Exception as e:
        logger.debug(f"Could not add POST body to trace: {e}")

########### DO NOT DELETE ###########

########### YOUR CODE MODIFICATIONS SHOULD GO BELOW HERE ###########

########### DO NOT DELETE ###########
@app.route("/actuator/keepalive")
def health():
    return {"status": "up"}

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8443, debug=False)
########### DO NOT DELETE ###########
'''

TEMPLATE_RUN = '''########### DO NOT DELETE ###########
import subprocess
import sys


def main():
    exit_code = subprocess.run(["python", "solution.py"])
    sys.exit(exit_code)


# make testable for build to pass
def startup():
    if __name__ == '__main__':
        main()


startup()

########### DO NOT DELETE ###########
'''


def blocos(texto):
    partes = texto.split(MARCA)
    return [partes[i] for i in range(1, len(partes), 2)]


# A regra do pre-push scan do Stratos ("legacy-proxy"): o proxy on-premise nas
# portas antigas, ou sem porta nenhuma. A 9443 passa. Vale até em comentário.
PROXY_ANTIGO = re.compile(r'proxy\.jpmchase\.net(?::(?:8080|8443|10443)\b|(?![:\d]))', re.I)


def confere_proxy():
    r = subprocess.run(['git', '-C', RAIZ, 'ls-files', 'apps', 'stratos/src', 'stratos/requirements.txt'],
                       capture_output=True, text=True)
    achados = []
    for rel in filter(None, r.stdout.split('\n')):
        try:
            texto = open(os.path.join(RAIZ, rel), encoding='utf-8').read()
        except (UnicodeDecodeError, OSError):
            continue
        achados += ['%s:%d' % (rel, n) for n, linha in enumerate(texto.split('\n'), 1)
                    if PROXY_ANTIGO.search(linha)]
    ok(r.returncode == 0 and not achados,
       'nada cita o proxy on-premise que o scan do stratos push barra %s' % achados[:5])


def confere_template():
    sol = open(os.path.join(STRATOS, 'src', 'solution.py'), encoding='utf-8').read()
    ok(blocos(sol) == blocos(TEMPLATE_SOLUTION) and len(blocos(sol)) == 2,
       'solution.py: os dois blocos DO NOT DELETE identicos ao template')
    corte = '########### ADD YOUR OTHER IMPORTS HERE ###########'
    ok(sol.split(corte)[0] == TEMPLATE_SOLUTION.split(corte)[0],
       'solution.py: cabecalho (bootstrap_otel primeiro) identico ao template')
    run = open(os.path.join(STRATOS, 'src', 'run.py'), encoding='utf-8').read()
    ok(run == TEMPLATE_RUN, 'run.py identico ao template')
    r = subprocess.run([sys.executable, os.path.join(STRATOS, 'build_requirements.py'), '--check'],
                       capture_output=True, text=True)
    ok(r.returncode == 0, 'requirements.txt em dia com o da raiz (' + r.stdout.strip() + ')')


# ── 2/3. Subida com o Stratos de mentira ────────────────────────────────────

PROXY_TESTE = 'http://proxy-do-stratos.teste:3128'


# O phonebook do Stratos (`stratosblocks.utilities.get_phonebook_data`): recebe
# uma LISTA de SIDs e, com um SID, devolve o registro dele (a forma do print
# da documentação).
FONE = {
    'E930179': {'standardID': 'E930179', 'nameFull': 'Giulliano Teste De Luccia',
                'email': 'giulliano.teste@jpmorgan.com',
                'positionName': '1542868: Trading Services Associate I (CWT515) BRAZIL BO'},
    'A123456': {'standardID': 'A123456', 'nameFull': 'Fulana Teste',
                'email': 'fulana.teste@jpmorgan.com', 'positionName': '1: Analyst BRAZIL BO'},
}


# O Shared Drive do Stratos (`stratosblocks.utilities.get_shared_drive`): no
# contêiner devolve o caminho no EFS montado; aqui, uma pasta do tmp do teste.
DRIVE = {'raiz': None, 'pedidos': []}


def _get_shared_drive(path, local_data_dir='data'):
    DRIVE['pedidos'].append(path)
    return os.path.join(DRIVE['raiz'], path)


def _phonebook(sids):
    if not isinstance(sids, list):
        raise TypeError('get_phonebook_data espera uma lista de SIDs')
    return dict(FONE.get(sids[0], {}))


class _Usuario(object):
    def __init__(self, sid):
        self.sid = sid or ''
        self.authorized = bool(sid)
        self.first_name = 'Teste'
        self.last_name = sid or ''


def _stubs(com_phonebook=True):
    from flask import redirect, request, session

    def modulo(nome, **attrs):
        m = types.ModuleType(nome)
        m.__dict__.update(attrs)
        sys.modules[nome] = m
        return m

    class StratosAuth(object):
        # Como o de verdade: o login volta por /login/callback, que guarda a
        # identidade na MESMA sessão Flask do app. Ou um cabeçalho do teste.
        def __init__(self, app, seal):
            self.app, self.seal = app, seal

            @app.route('/login/callback')
            def stratos_login_callback():
                session['stratos_user'] = request.args.get('sid', '')
                return redirect(request.script_root + '/')

        def user(self):
            return _Usuario(request.headers.get('X-Test-SID') or session.get('stratos_user'))

    def dispatcher(app, inner):
        return inner

    modulo('stratosblocks')
    modulo('stratosblocks.web')
    modulo('stratosblocks.web.otel', bootstrap_otel=lambda: None)
    modulo('stratosblocks.web.logging',
           enable_logging=lambda nivel: __import__('logging').getLogger('stratos'))
    def proxy_do_stratos():
        os.environ['HTTP_PROXY'] = os.environ['HTTPS_PROXY'] = PROXY_TESTE

    modulo('stratosblocks.connectivity', configure_proxy_env_vars=proxy_do_stratos)
    modulo('stratosblocks.email', send=lambda **kw: EMAILS.append(kw))
    if com_phonebook:
        modulo('stratosblocks.utilities', get_phonebook_data=_phonebook,
               get_shared_drive=_get_shared_drive,
               get_proxied_url=lambda internal_url, headers=None, files=False: (
                   internal_url, dict(headers or {}), {}))
    modulo('stratosblocks.authentication')
    modulo('stratosblocks.authentication.web', StratosAuth=StratosAuth,
           StratosDispatcherMiddleware=dispatcher)
    try:
        import opentelemetry.instrumentation.flask  # noqa: F401
        import opentelemetry.instrumentation.requests  # noqa: F401
    except ImportError:
        class _Span(object):
            def is_recording(self):
                return False

        class _Noop(object):
            def instrument_app(self, app):
                pass

            def instrument(self):
                pass

        modulo('opentelemetry', trace=types.SimpleNamespace(get_current_span=_Span))
        modulo('opentelemetry.instrumentation')
        modulo('opentelemetry.instrumentation.flask', FlaskInstrumentor=_Noop)
        modulo('opentelemetry.instrumentation.requests', RequestsInstrumentor=_Noop)


def confere_subida(tmp, sem_awmpy):
    src = os.path.join(tmp, 'src')
    os.makedirs(src)
    for nome in ('solution.py', 'run.py', 'otc_stratos.py', 'prova_travas.py', 'email_stratos.py',
                 'pacotes_dados.py', 'proxy_interno.py', 'ida_token.py', 'fotos_stratos.py'):
        shutil.copy(os.path.join(STRATOS, 'src', nome), src)
    os.symlink(os.path.join(RAIZ, 'apps'), os.path.join(src, 'apps'))
    # Com phonebook a raiz sai do Shared Drive (o `get_shared_drive` está no
    # mesmo `stratosblocks.utilities`); sem, do OTC_STRATOS_ROOT.
    if sem_awmpy:
        raiz = os.path.join(tmp, 'otc-root')
        os.environ['OTC_STRATOS_ROOT'] = raiz
    else:
        DRIVE['raiz'] = os.path.join(tmp, 'efs')
        raiz = os.path.join(DRIVE['raiz'], 'otc-tracker')
        os.environ.pop('OTC_STRATOS_ROOT', None)
    os.environ.pop('OTC_SECRET_KEY_FILE', None)
    os.environ.pop('OTC_DATA_DIR', None)
    os.environ.pop('OTC_DATABASE_DIR', None)
    os.environ['OTC_DISABLE_SCHEDULERS'] = '1'
    os.environ['SECRET_KEY'] = 'teste-stratos'
    for nome in ('QUOTES_PROXY', 'HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy'):
        os.environ.pop(nome, None)
    # Sem phonebook: nem o do Stratos nem o `awmpy` — o app tem de subir assim.
    if sem_awmpy:
        sys.modules['awmpy'] = None   # `import awmpy` levanta ImportError
    _stubs(com_phonebook=not sem_awmpy)
    sys.path.insert(0, src)
    os.chdir(src)
    import time
    t0 = time.time()
    import solution
    import otc_stratos

    ok(time.time() - t0 < 5, 'o import do solution.py volta na hora (a subida e em segundo plano)')
    erro = otc_stratos.espera_subida(300)
    ok(erro is None, 'o OTC subiu em segundo plano em %.1fs %s' % (time.time() - t0, (erro or '')[-600:]))
    app = solution.app

    from flask import redirect

    @app.route('/__teste_redirect')
    def teste_redirect():   # um redirect escrito à mão, como há no OTC
        return redirect('/dashboard')

    ok(app.config['DATA_DIR'].startswith(raiz) and app.config['DATABASE_DIR'].startswith(raiz),
       'DATA_DIR e DATABASE_DIR sob a raiz %s (%s)' % (
           'do OTC_STRATOS_ROOT' if sem_awmpy else 'do Shared Drive', app.config['DATABASE_DIR']))
    if not sem_awmpy:
        ok(DRIVE['pedidos'] == ['otc-tracker'], 'a raiz pedida ao get_shared_drive uma vez')
    ok(app.config['FOUR_EYES'] is True, 'maker/checker ligado no Stratos')
    ok(app.root_path == os.path.join(src, 'apps'), 'root_path do app = src/apps')
    from apps.pages import quotes
    ok(quotes.QUOTES_PROXY == '', 'Cotacoes sem o proxy corporativo do desktop')
    from apps.pages import athena_api
    ok(getattr(athena_api.build_session, '_otc_stratos_proxy', False) is (not sem_awmpy),
       'Athena: %s' % ('sem o get_proxied_url, a sessao de sempre' if sem_awmpy
                       else 'a sessao pelo proxy do Stratos (get_proxied_url)'))
    rotas = [nome for nome, _ in quotes._routes()]
    ok(rotas[:1] == ['system proxy ' + PROXY_TESTE],
       'a primeira saida das Cotacoes e o proxy do Stratos %s' % rotas)
    if sem_awmpy:
        ok(getattr(sys.modules.get('awmpy'), '_otc_stratos_stub', False),
           'sem phonebook nenhum: o substituto entra e o app sobe')
    else:
        ok(getattr(sys.modules.get('awmpy'), '_otc_stratos_phonebook', False),
           'o awmpy e a casca do phonebook do Stratos (mesmo com o awmpy instalado)')

    c = app.test_client()
    MASTER = {'X-Test-SID': 'E930179'}

    r = c.get('/actuator/keepalive')
    ok(r.status_code == 404, 'fora do CONTEXT_ROOT: 404 do dispatcher')
    r = c.get(BASE + '/actuator/keepalive')
    ok(r.status_code == 200 and r.get_json() == {'status': 'up'}, 'health sem identidade: 200')

    r = c.get(BASE + '/stratos/whoami')
    ok(r.status_code == 200 and b'not authorized' in r.data, 'whoami fora da ponte de SSO')

    r = c.get(BASE + '/')
    ok(r.status_code == 403, 'sem identidade do Stratos: 403')
    r = c.get(BASE + '/api/user-home/favorites')
    ok(r.status_code == 403 and (r.get_json() or {}).get('code') == 'not_authorized',
       'API sem identidade: 403 JSON com code (nunca 401)')

    from apps.pages import routes
    ok(routes.get_user_by_sid('E930179') is None, 'banco de usuarios nasce vazio')
    r = c.get(BASE + '/', headers=MASTER)
    ok(r.status_code == 302 and r.headers['Location'] == BASE + '/dashboard',
       'master num banco vazio: entra e vai ao dashboard (%s %s)'
       % (r.status_code, r.headers.get('Location')))
    u = routes.get_user_by_sid('E930179') or {}
    ok(u.get('Status') == 'Active', 'master ativado sozinho')
    cookie = c.get_cookie('otc_tracker_session', path=BASE)
    ok(cookie is not None, 'cookie de sessao proprio, no caminho da solucao')

    r = c.get(BASE + '/__teste_redirect', headers=MASTER)
    ok(r.headers.get('Location') == BASE + '/dashboard', 'redirect("/x") ganha a base no Location')

    r = c.get(BASE + '/dashboard', headers=MASTER)
    html = r.get_data(as_text=True)
    ok(r.status_code == 200, 'dashboard 200 para o master')
    ok('window.__OTC_BASE__' in html and html.index('window.__OTC_BASE__') < html.index('</head>'),
       'shim injetado no <head>')
    soltos = re.findall(r'''\s(?:href|src|action)\s*=\s*["']/(?!/|%s)''' % re.escape(BASE[1:]), html)
    ok(not soltos, 'nenhum href/src/action "/x" sem a base no HTML (%d)' % len(soltos))
    ok(('href="%s/static/' % BASE) in html or ('src="%s/static/' % BASE) in html,
       'ASSETS_ROOT com a base')
    if 'speculationrules' in html:
        ok('"href_matches": "%s/logout"' % BASE in html,
           'Speculation Rules: logout continua fora da pre-busca')

    r = c.get(BASE + '/static/js/otc.js')
    ok(r.status_code == 200 and len(r.data) > 1000, 'estatico do OTC servido de src/apps/static')

    r = c.get(BASE + '/sw.js', headers=MASTER)
    corpo = r.get_data(as_text=True)
    ok(r.status_code == 200 and corpo.lstrip().startswith('(function') and BASE in corpo[:400],
       'service worker com o shim da base')

    NOVO = {'X-Test-SID': 'A123456'}
    r = c.get(BASE + '/', headers=NOVO)
    ok(r.status_code == 200 and b'Request Received' in r.data,
       'SID sem cadastro: pedido de acesso registrado')
    ok((routes.get_user_by_sid('A123456') or {}).get('Status') == 'Pending', 'pedido fica Pending')
    novo, master = routes.get_user_by_sid('A123456') or {}, routes.get_user_by_sid('E930179') or {}
    if sem_awmpy:
        ok(novo.get('Name') == 'Teste A123456', 'sem phonebook: o nome que o Stratos informa (%r)'
           % novo.get('Name'))
    else:
        ok(novo.get('Name') == 'Fulana Teste' and novo.get('Email') == 'fulana.teste@jpmorgan.com'
           and novo.get('Role_Description') == FONE['A123456']['positionName'],
           'pedido de acesso com nome, e-mail e cargo do phonebook do Stratos (%r)' % novo)
        ok(master.get('Name') == FONE['E930179']['nameFull']
           and master.get('Email') == FONE['E930179']['email'],
           'o master tambem nasce com o phonebook (%r)' % master.get('Name'))
    r = c.get(BASE + '/api/user-home/favorites', headers=NOVO)
    ok(r.status_code == 403 and (r.get_json() or {}).get('code') == 'account_pending',
       'pendente na API: 403 account_pending')
    r = c.get(BASE + '/', headers=MASTER)
    ok(r.status_code == 302, 'mesmo navegador, SID de volta ao master: sessao reaberta')

    # A prova das travas no Shared Drive (§681, passo B): só do master, pela
    # identidade do Stratos.
    r = c.get(BASE + '/stratos/prova-travas')
    ok(r.status_code == 403 and (r.get_json() or {}).get('code') == 'master_only',
       'prova das travas sem identidade: 403 master_only')
    r = c.get(BASE + '/stratos/prova-travas', headers=NOVO)
    ok(r.status_code == 403, 'prova das travas para quem nao e master: 403')
    r = c.get(BASE + '/stratos/prova-travas', headers=MASTER)
    d = r.get_json() or {}
    ok(r.status_code == 200 and d.get('veredito') == 'as travas valem' and len(d.get('casos') or ()) == 11
       and d.get('pasta', '').startswith(os.path.join(raiz, 'prova-travas')),
       'prova das travas pelo master: as 11 conferencias no drive (%s %s %s)'
       % (r.status_code, d.get('veredito'), d.get('falhas') or d.get('text')))
    ok('erro' not in (d.get('tempos') or {}).get('banco_de_cadastro', {'erro': 1}),
       'a prova mede a abertura de um banco de cadastro pelo duckdb_read (%s)'
       % (d.get('tempos') or {}).get('banco_de_cadastro'))
    r = c.get(BASE + '/stratos/prova-travas?modo=xyz', headers=MASTER)
    ok(r.status_code == 400, 'prova das travas: modo desconhecido e 400')

    # O e-mail: o relay do JPM não responde do contêiner, e o smtplib.SMTP do
    # app inteiro vira o Email block (email_stratos.py).
    import smtplib
    import email_stratos
    ok(smtplib.SMTP is email_stratos.SmtpStratos, 'e-mail: o smtplib.SMTP do app e o Email block')
    with app.app_context():
        enviado = routes.send_verification_email('fulana.teste@jpmorgan.com', '493817', 'Fulana')
    e = EMAILS[-1] if EMAILS else {}
    ok(enviado is True and e.get('recipient') == ['fulana.teste@jpmorgan.com']
       and e.get('sender') == routes.SHARED_MAILBOX and e.get('is_html_message') is True
       and '493817' in re.sub(r'<[^>]+>|\s+', '', e.get('body') or ''),   # um digito por caixa
       'e-mail: o codigo de verificacao sai pelo Email block (%s %r)'
       % (enviado, {k: e.get(k) for k in ('subject', 'recipient', 'sender')}))
    ok([os.path.basename(x) for x in e.get('inline_images') or ()] == ['otc_logo.png']
       and 'cid:otc_logo.png' in (e.get('body') or ''),
       'e-mail: o logo vai como imagem do corpo, com o cid do arquivo')

    # O login de verdade: o SSO devolve no /login/callback, que guarda a
    # identidade na sessão. A ponte não pode barrar o callback nem apagar a
    # chave do Stratos ao abrir (ou trocar) a sessão do OTC.
    # HTTPS, como no Stratos: o cookie de sessão é Secure (ProductionConfig), e
    # por HTTP o cliente não o devolveria.
    sso = app.test_client()
    https = {'base_url': 'https://localhost'}
    r = sso.get(BASE + '/login/callback?sid=E930179&code=x', **https)
    ok(r.status_code == 302, 'o /login/callback do Stratos passa pela ponte (%s)' % r.status_code)
    r = sso.get(BASE + '/dashboard', **https)
    with sso.session_transaction(BASE + '/', **https) as s:
        dentro = dict(s)
    ok(r.status_code == 200 and dentro.get('stratos_user') == 'E930179'
       and dentro.get('user_sid') == 'E930179',
       'pela sessao do Stratos: dashboard 200 e as duas sessoes convivem (%s %s)'
       % (r.status_code, sorted(dentro)))
    sso.get(BASE + '/login/callback?sid=A123456&code=y', **https)
    r = sso.get(BASE + '/dashboard', **https)
    with sso.session_transaction(BASE + '/', **https) as s:
        dentro = dict(s)
    ok(dentro.get('stratos_user') == 'A123456' and not dentro.get('authenticated')
       and b'pending' in r.data,
       'outro SID pelo SSO: a sessao do OTC troca, a do Stratos fica')

    # O menu da foto: Lock Screen e Logout. A ponte devolvia o dashboard nos
    # dois — tirava o `locked` a cada request, e o Logout do OTC
    # (`session.clear()`) levava o login do Stratos junto, e o SSO entrava de novo.
    from urllib.parse import urlsplit

    def onde(resp):
        return urlsplit(resp.headers.get('Location', '')).path

    t = app.test_client()
    t.get(BASE + '/login/callback?sid=E930179&code=z', **https)
    ok(t.get(BASE + '/dashboard', **https).status_code == 200, 'menu: o master entrou pelo SSO')
    r = t.get(BASE + '/lock', **https)
    ok(r.status_code == 302 and onde(r) == BASE + '/auth-2-lock-screen',
       'Lock Screen leva a tela travada (%s %s)' % (r.status_code, onde(r)))
    r = t.get(BASE + '/auth-2-lock-screen', **https)
    ok(r.status_code == 200 and (BASE + '/unlock').encode() in r.data, 'a tela travada abre, com o Unlock')
    r = t.get(BASE + '/dashboard', **https)
    ok(r.status_code == 302 and onde(r) == BASE + '/auth-2-lock-screen',
       'travada, o dashboard volta para a trava')
    r = t.post(BASE + '/unlock', data={'sid': 'A123456'}, **https)
    ok(onde(r) == BASE + '/auth-2-lock-screen' and t.get(BASE + '/dashboard', **https).status_code == 302,
       'o SID de outra pessoa nao destrava')
    r = t.post(BASE + '/unlock', data={'sid': 'e930179'}, **https)
    ok(r.status_code == 302 and onde(r) == BASE + '/dashboard', 'o SID do SSO destrava (%s)' % onde(r))
    ok(t.get(BASE + '/dashboard', **https).status_code == 200, 'destravada, o dashboard abre')

    r = t.get(BASE + '/logout', **https)
    with t.session_transaction(BASE + '/', **https) as s:
        dentro = dict(s)
    ok(r.status_code == 302 and onde(r) == BASE + '/auth-2-sign-in'
       and dentro.get('stratos_user') == 'E930179' and not dentro.get('authenticated')
       and dentro.get('otc_stratos_saiu'),
       'Logout encerra so a sessao do OTC; a do Stratos fica (%s)' % sorted(dentro))
    r = t.get(BASE + '/auth-2-sign-in', **https)
    ok(r.status_code == 200 and b'otc-stratos-saiu' in r.data and b'card-side-img' in r.data
       and (BASE + '/auth-2-sign-in?entrar=1').encode() in r.data,
       'saiu: a tela de saida, com o Sign in again na base')
    r = t.get(BASE + '/dashboard', **https)
    ok(r.status_code == 302 and onde(r) == BASE + '/auth-2-sign-in', 'saiu: o SSO nao reabre a sessao sozinho')
    r = t.get(BASE + '/api/user-home/favorites', **https)
    ok(r.status_code == 401 and (r.get_json() or {}).get('code') == 'signed_out',
       'saiu: a API responde 401 (o session-guard da aba aberta leva a tela de saida)')
    r = t.get(BASE + '/auth-2-sign-in?entrar=1', **https)
    ok(r.status_code == 302 and onde(r) == BASE + '/dashboard', 'Sign in again reabre pelo SSO')
    r = t.get(BASE + '/dashboard', **https)
    with t.session_transaction(BASE + '/', **https) as s:
        dentro = dict(s)
    ok(r.status_code == 200 and dentro.get('user_sid') == 'E930179' and not dentro.get('otc_stratos_saiu'),
       'e o dashboard volta, sem a marca de saida')


# ── 4. O shim no node ───────────────────────────────────────────────────────

NODE_TESTE = r"""
const B = '/76521/otc-tracker-ops-ai-citizen';
const chamadas = [];
globalThis.window = globalThis;
globalThis.location = { origin: 'https://h', assign() {} };
globalThis.fetch = (r) => { chamadas.push(typeof r === 'string' ? r : r.url); return Promise.resolve(); };
function XHR() {}
XHR.prototype.open = function (m, u) { chamadas.push(u); };
globalThis.XMLHttpRequest = XHR;
function El() { this.a = {}; }
El.prototype.setAttribute = function (n, v) { this.a[n] = v; };
El.prototype.getAttribute = function (n) { return this.a[n] || null; };
globalThis.Element = El;
Object.defineProperty(globalThis, 'navigator', { value: {}, configurable: true });
globalThis.history = { pushState(s, t, u) { chamadas.push(u); }, replaceState() {} };
globalThis.document = { documentElement: {} };
globalThis.MutationObserver = function () { this.observe = function () {}; };
eval(require('fs').readFileSync(0, 'utf8'));
const f = window.otcStratosUrl, falhas = [];
function eq(a, b, m) { if (a !== b) falhas.push(m + ': ' + a + ' != ' + b); }
eq(f('/api/x'), B + '/api/x', 'raiz relativa ganha a base');
eq(f(B + '/api/x'), B + '/api/x', 'ja com a base nao duplica');
eq(f('//cdn/x'), '//cdn/x', 'protocolo relativo intacto');
eq(f('api/x'), 'api/x', 'relativo intacto');
eq(f('https://h/api/x'), 'https://h' + B + '/api/x', 'absoluto da mesma origem');
eq(f('https://outro/api/x'), 'https://outro/api/x', 'outra origem intacta');
eq(f('/api/file-interpreter/page-spec?url=' + encodeURIComponent(B + '/new_deals-ndf-vanilla')),
   B + '/api/file-interpreter/page-spec?url=' + encodeURIComponent('/new_deals-ndf-vanilla'),
   'o caminho da pagina como parametro sai sem a base');
fetch('/api/a'); new XMLHttpRequest().open('GET', '/api/b'); history.pushState({}, '', '/c');
eq(chamadas.join(','), [B + '/api/a', B + '/api/b', B + '/c'].join(','), 'fetch/XHR/history');
const el = new Element(); el.setAttribute('href', '/d'); el.setAttribute('data-x', '/e');
eq(el.a.href, B + '/d', 'setAttribute href'); eq(el.a['data-x'], '/e', 'outro atributo intacto');
if (falhas.length) { console.log(falhas.join('\n')); process.exit(1); }
console.log('shim ok');
"""


def confere_shim():
    node = shutil.which('node')
    if not node:
        print('skip  node ausente: shim de JavaScript nao executado')
        return
    sys.path.insert(0, os.path.join(STRATOS, 'src'))
    import otc_stratos
    js = otc_stratos._SHIM_PAGINA.replace('__BASE_JSON__', json.dumps(BASE))
    r = subprocess.run([node, '-e', NODE_TESTE], input=js, capture_output=True, text=True)
    ok(r.returncode == 0, 'shim de JavaScript (node): ' + (r.stdout + r.stderr).strip()[:400])


def confere_phonebook():
    """A resposta do `get_phonebook_data([sid])` nas formas que ela pode ter."""
    sys.path.insert(0, os.path.join(STRATOS, 'src'))
    import otc_stratos
    reg = otc_stratos._registro_do_phonebook
    um = dict(FONE['A123456'])
    ok(reg(um, 'a123456') is um, 'phonebook: o registro de um SID (a forma do print)')
    ok(reg([FONE['E930179'], um], 'A123456') is um, 'phonebook: lista, achado pelo standardID')
    ok(reg({'A123456': um}, 'A123456') is um, 'phonebook: dict por SID')
    for ruim, desc in (({}, 'vazio'), ([], 'lista vazia'), (None, 'None'),
                       (dict(FONE['E930179']), 'registro de OUTRO SID')):
        try:
            reg(ruim, 'A123456')
            ok(False, 'phonebook: %s levanta' % desc)
        except LookupError:
            ok(True, 'phonebook: %s levanta' % desc)


def confere_shared_drive():
    """A raiz dos dados: Shared Drive, variável, ou /tmp avisando — sem subir o app."""
    sys.path.insert(0, os.path.join(STRATOS, 'src'))
    import otc_stratos
    guardado = {k: os.environ.get(k) for k in ('OTC_STRATOS_ROOT', 'OTC_SECRET_KEY_FILE')}
    util = sys.modules.get('stratosblocks.utilities')
    pai = sys.modules.get('stratosblocks')
    sys.modules.setdefault('stratosblocks', types.ModuleType('stratosblocks'))
    tmp = tempfile.mkdtemp(prefix='otc-drive-')
    cwd = os.getcwd()

    def limpa():
        for k in guardado:
            os.environ.pop(k, None)

    def com_utilities(**attrs):
        m = types.ModuleType('stratosblocks.utilities')
        m.__dict__.update(attrs)
        sys.modules['stratosblocks.utilities'] = m

    try:
        limpa()
        DRIVE.update(raiz=os.path.join(tmp, 'efs'), pedidos=[])
        com_utilities(get_shared_drive=_get_shared_drive)
        raiz = otc_stratos._raiz_no_shared_drive()
        esperado = os.path.join(tmp, 'efs', 'otc-tracker')
        ok(raiz == esperado and os.environ.get('OTC_STRATOS_ROOT') == esperado,
           'drive: sem a variavel, a raiz e a pasta do OTC no Shared Drive')
        ok(os.path.isdir(esperado), 'drive: a pasta e criada')
        ok(os.environ.get('OTC_SECRET_KEY_FILE') == os.path.join(esperado, 'secret_key.txt'),
           'drive: a chave da sessao no drive (sobrevive ao deploy, a mesma em todo worker)')

        limpa()
        os.environ['OTC_STRATOS_ROOT'] = os.path.join(tmp, 'escolhida')
        DRIVE['pedidos'] = []
        raiz = otc_stratos._raiz_no_shared_drive()
        ok(raiz == os.path.join(tmp, 'escolhida') and DRIVE['pedidos'] == [],
           'drive: a variavel vence, e o get_shared_drive nem e chamado')

        limpa()
        os.environ['OTC_SECRET_KEY_FILE'] = '/outro/lugar.txt'
        otc_stratos._raiz_no_shared_drive()
        ok(os.environ.get('OTC_SECRET_KEY_FILE') == '/outro/lugar.txt',
           'drive: OTC_SECRET_KEY_FILE definida vence')

        limpa()
        os.chdir(tmp)
        com_utilities(get_shared_drive=lambda path, local_data_dir='data': os.path.join('data', path))
        raiz = otc_stratos._raiz_no_shared_drive()
        ok(raiz == os.path.join(os.path.realpath(tmp), 'data', 'otc-tracker')
           or raiz == os.path.join(tmp, 'data', 'otc-tracker'),
           'drive: fora do conteiner o caminho relativo vira absoluto (%s)' % raiz)
        os.chdir(cwd)

        for desc, attrs in (('sem o get_shared_drive', {}),
                            ('get_shared_drive que levanta',
                             {'get_shared_drive': lambda **kw: 1 / 0})):
            limpa()
            com_utilities(**attrs)
            raiz = otc_stratos._raiz_no_shared_drive()
            ok(raiz is None and 'OTC_STRATOS_ROOT' not in os.environ,
               'drive: %s, a raiz fica no /tmp do bloco ENV:STRATOS' % desc)
    finally:
        os.chdir(cwd)
        limpa()
        for k, v in guardado.items():
            if v is not None:
                os.environ[k] = v
        if util is None:
            sys.modules.pop('stratosblocks.utilities', None)
        else:
            sys.modules['stratosblocks.utilities'] = util
        if pai is None:
            sys.modules.pop('stratosblocks', None)
        shutil.rmtree(tmp, ignore_errors=True)


def confere_portao():
    """O portão WSGI nos três estados da subida, sem subir o app."""
    import threading
    import time
    from werkzeug.test import Client
    sys.path.insert(0, os.path.join(STRATOS, 'src'))
    import otc_stratos

    chamado = []

    def interno(environ, start_response):
        chamado.append(environ['PATH_INFO'])
        start_response('200 OK', [('Content-Type', 'text/plain')])
        return [b'flask']

    original = otc_stratos._SUBIDA
    otc_stratos._SUBIDA = {'pronto': threading.Event(), 'erro': None, 'inicio': time.time()}
    try:
        c = Client(otc_stratos._portao(interno, BASE))
        r = c.get(BASE + '/actuator/keepalive')
        ok(r.status_code == 200 and r.get_json() == {'status': 'up'} and not chamado,
           'subindo: health 200 sem chamar o Flask')
        r = c.get(BASE + '/dashboard')
        ok(r.status_code == 503 and b'starting' in r.data and b'refresh' in r.data and not chamado,
           'subindo: pagina 503 que se recarrega sozinha')
        r = c.get(BASE + '/api/x')
        ok(r.status_code == 503 and (r.get_json() or {}).get('code') == 'starting',
           'subindo: API 503 JSON com code')
        otc_stratos._SUBIDA['erro'] = 'Traceback ... ValueError: <boom>'
        otc_stratos._SUBIDA['pronto'].set()
        r = c.get(BASE + '/dashboard')
        ok(r.status_code == 503 and b'failed to start' in r.data and b'&lt;boom&gt;' in r.data,
           'quebrou: o erro na tela, escapado')
        r = c.get(BASE + '/actuator/keepalive')
        ok(r.status_code == 200, 'quebrou: health segue 200, para o erro continuar na tela')
        otc_stratos._SUBIDA['erro'] = None
        r = c.get(BASE + '/dashboard')
        ok(r.status_code == 200 and chamado == [BASE + '/dashboard'], 'pronto: tudo vai ao Flask')
    finally:
        otc_stratos._SUBIDA = original


def main():
    if '--filho' in sys.argv:
        # Cada subida importa o app inteiro: roda num processo filho limpo.
        tmp = tempfile.mkdtemp(prefix='otc-stratos-')
        try:
            confere_subida(tmp, sem_awmpy=sys.argv[-1] == '1')
        finally:
            os.chdir(RAIZ)
            shutil.rmtree(tmp, ignore_errors=True)
        return 1 if FALHAS else 0
    confere_template()
    confere_proxy()
    confere_shim()
    confere_phonebook()
    confere_shared_drive()
    confere_portao()
    for sem_awmpy in ('0', '1'):
        r = subprocess.run([sys.executable, os.path.abspath(__file__), '--filho', sem_awmpy])
        ok(r.returncode == 0, 'subida %s phonebook' % ('sem' if sem_awmpy == '1' else 'com'))
    r = subprocess.run([sys.executable, os.path.join(AQUI, 'check_exporta_dados.py')],
                       capture_output=True, text=True)
    for linha in r.stdout.splitlines():
        if linha.startswith('FAIL'):
            print('      exporta: ' + linha)
    ok(r.returncode == 0, 'exporta_dados: o pacote dos bancos para o Stratos')
    r = subprocess.run([sys.executable, os.path.join(AQUI, 'check_pacotes_dados.py')],
                       capture_output=True, text=True)
    for linha in r.stdout.splitlines():
        if linha.startswith('FAIL'):
            print('      pacotes: ' + linha)
    ok(r.returncode == 0, 'chegada dos bancos: envio em partes, conferência, ponteiro e a rota')
    r = subprocess.run([sys.executable, os.path.join(AQUI, 'check_ponte.py')],
                       capture_output=True, text=True)
    for linha in r.stdout.splitlines():
        if linha.startswith('FAIL'):
            print('      ponte: ' + linha)
    ok(r.returncode == 0, 'ponte do share: espelho, travas, alinhar e virada')
    r = subprocess.run([sys.executable, os.path.join(AQUI, 'check_email_stratos.py')],
                       capture_output=True, text=True)
    for linha in r.stdout.splitlines():
        if linha.startswith('FAIL'):
            print('      email: ' + linha)
    ok(r.returncode == 0, 'e-mail: a mensagem do app traduzida para o Email block')
    r = subprocess.run([sys.executable, os.path.join(AQUI, 'check_proxy_interno.py')],
                       capture_output=True, text=True)
    for linha in r.stdout.splitlines():
        if linha.startswith('FAIL'):
            print('      proxy: ' + linha)
    ok(r.returncode == 0, 'Athena pelo proxy do Stratos: desvio por host, redirecionamentos e cookies')
    r = subprocess.run([sys.executable, os.path.join(AQUI, 'check_ida_token.py')],
                       capture_output=True, text=True)
    for linha in r.stdout.splitlines():
        if linha.startswith('FAIL'):
            print('      ida: ' + linha)
    ok(r.returncode == 0, 'Athena com o token do IDA: cabeçalho, cache, 401 e a ordem com o proxy')
    r = subprocess.run([sys.executable, os.path.join(AQUI, 'check_fotos_stratos.py')],
                       capture_output=True, text=True)
    for linha in r.stdout.splitlines():
        if linha.startswith('FAIL'):
            print('      fotos: ' + linha)
    ok(r.returncode == 0, 'fotos dos usuários: o envio e o drive servindo sem caixa')
    r = subprocess.run([sys.executable, os.path.join(AQUI, 'check_prova_travas.py')],
                       capture_output=True, text=True)
    for linha in r.stdout.splitlines():
        if linha.startswith('FAIL'):
            print('      travas: ' + linha)
    ok(r.returncode == 0, 'prova das travas: acusa a trava por processo e segura entre requests')
    print('\n%d falha(s)' % len(FALHAS))
    return 1 if FALHAS else 0


if __name__ == '__main__':
    sys.exit(main())
