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
  · `awmpy` (phonebook interno), que no servidor não existe. O phonebook do
    Stratos é o `stratosblocks.utilities.get_phonebook_data`, e o `awmpy`
    vira uma casca dele (`_garante_awmpy`).

E a rede: a saída para a internet é pelo proxy do Stratos
(`_proxy_do_stratos`), não pelo proxy corporativo do desktop. E o disco: os
bancos DuckDB moram no Shared Drive (EFS) da solução, que sobrevive ao deploy
(`_raiz_no_shared_drive`), e não no disco do contêiner; e as pastas do share
que o app usa chegam e saem por uma PONTE com a máquina do JPM
(`_ponte_manifestos` aqui, `stratos/ponte_share.py` lá). Se as travas do
app valem nesse drive, a rota `/stratos/prova-travas` responde
(`_rota_prova_travas`, `prova_travas.py`). E o e-mail: o relay SMTP do JPM
não responde do contêiner, e o `smtplib.SMTP` que os 23 senders do app usam
vira o Email block do stratos-blocks (`email_stratos.py`).
E a Athena: host interno do JPM, que da AWS só se alcança pelo proxy do
Stratos (`get_proxied_url`, `proxy_interno.py`), e que no desktop autentica por
Kerberos — aqui, pelo token do IDA do FID (`ida_token.py`, rota `/stratos/ida`).

Este arquivo, o `solution.py` e o `run.py` existem SÓ na branch
OTC-Tracker-Stratos; o código do app continua nascendo na dev.
"""
import html
import json
import logging
import os
import re
import sys
import threading
import time
import traceback
import types

from flask import (flash, jsonify, redirect, render_template, render_template_string, request,
                   session, url_for)

log = logging.getLogger('otc_tracker')

# As chaves que o OTC guarda na sessão. A sessão é UMA para o app inteiro, e o
# StratosAuth guarda a dele ali também: limpar tudo (`session.clear()`) levava
# junto o login do Stratos — e, no meio do /login/callback, o login inteiro.
_CHAVES_OTC = ('authenticated', 'user_sid', 'user_name', 'user_email', 'user_role',
               'user_position', 'session_ip', 'locked', 'pending_sid', 'pending_ip',
               'masked_email', 'masked_phone')

# Telas do login próprio. Com o SSO quem chega nelas já está autenticado. A
# tela TRAVADA não está aqui: o Lock Screen do menu vale no Stratos também.
_TELAS_DE_LOGIN = {
    'pages_blueprint.index', 'pages_blueprint.sign_in_page',
    'pages_blueprint.sign_up_page', 'pages_blueprint.two_factor_page',
}

# Quem clicou em Logout. O Logout do OTC faz `session.clear()` — e com isso
# apagava também o login do StratosAuth; o request seguinte voltava pelo SSO,
# que entra sozinho, e o clique devolvia o dashboard. Aqui sair encerra só a
# sessão do OTC e PARA nela: com esta marca a ponte não reabre a sessão até o
# "Sign in again" (`/auth-2-sign-in?entrar=1`).
_SAIU = 'otc_stratos_saiu'
# O que a tela de saída ainda pede ao blueprint do OTC.
_LIVRE_SEM_SESSAO = {'pages_blueprint.service_worker'}


# A subida do OTC em segundo plano (ver `mount`): pronto, e o erro que a parou.
_SUBIDA = {'pronto': threading.Event(), 'erro': None, 'inicio': time.time()}


def mount(app, stratos_auth, context_root):
    """Pendura o OTC Tracker no `app` do template — em SEGUNDO PLANO.

    O `app.run` do template (bloco DO NOT DELETE) só abre a porta quando o
    módulo inteiro termina, e a subida do OTC — importar o app e semear ~110
    bancos DuckDB num disco vazio — leva segundos numa máquina rápida e minutos
    num contêiner com fração de CPU: o health check do Stratos desistia antes,
    e três deploys foram derrubados a ~2 min 20 s cada. Aqui o `mount` só põe
    um portão na frente do app e volta: a porta abre na hora, o health check
    responde desde o primeiro segundo, as páginas dizem "starting" até o OTC
    ficar pronto, e uma subida que quebra aparece na tela com o erro.
    """
    base = '/' + context_root.strip('/')
    _SUBIDA['inicio'] = time.time()
    app.wsgi_app = _portao(app.wsgi_app, base)
    threading.Thread(target=_sobe, args=(app, stratos_auth, base),
                     name='otc-stratos-boot', daemon=True).start()
    return app


def espera_subida(timeout=None):
    """Bloqueia até o OTC subir (ou quebrar). Devolve o erro, ou None."""
    if not _SUBIDA['pronto'].wait(timeout):
        return 'a subida nao terminou em %ss' % timeout
    return _SUBIDA['erro']


def _sobe(app, stratos_auth, base):
    # O solution.py ainda registra rotas depois do `mount` (o whoami e, por
    # último, o health check do bloco DO NOT DELETE): mexer no url_map ao
    # mesmo tempo seria uma corrida. O health check registrado é a deixa.
    limite = time.time() + 60
    while 'health' not in app.view_functions and time.time() < limite:
        time.sleep(0.05)
    try:
        _monta(app, stratos_auth, base)
    except Exception:                                       # noqa: BLE001
        _SUBIDA['erro'] = traceback.format_exc()
        log.error('[stratos] a subida do OTC Tracker falhou:\n%s', _SUBIDA['erro'])
    else:
        log.warning('[stratos] OTC Tracker pronto em %s, em %.0fs (dados em %s)',
                    base, time.time() - _SUBIDA['inicio'], app.config.get('DATA_DIR'))
    finally:
        _SUBIDA['pronto'].set()


def _monta(app, stratos_auth, base):
    """Reproduz o `apps.create_app` sobre o app do template, pelas mesmas
    funções dele — duplicar a lógica faria as duas subidas divergirem na
    primeira mudança da dev."""
    _proxy_do_stratos()
    _garante_awmpy()
    import email_stratos
    email_stratos.instala()   # o smtplib.SMTP do app vira o Email block (o relay não responde aqui)
    _raiz_no_shared_drive()   # antes do import: o bloco ENV:STRATOS lê a raiz nele

    import apps as otc
    import proxy_interno
    proxy_interno.instala()   # a Athena (host interno do JPM) pelo get_proxied_url do Stratos
    import ida_token
    ida_token.instala()       # e com o token do IDA no lugar do Kerberos (por FORA do proxy)
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
    _ponte_manifestos(app)
    _rota_prova_travas(app, stratos_auth)
    _rota_pacotes(app, stratos_auth)
    _rota_ida(app, stratos_auth)


# ── O portão: o que responde enquanto o OTC sobe ────────────────────────────

_PAGINA_SUBINDO = (
    '<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="5">'
    '<title>OTC Tracker</title><body style="font-family:system-ui,sans-serif;margin:3rem">'
    '<h3>OTC Tracker is starting&hellip;</h3><p>%d s. This page reloads by itself.</p>')
_PAGINA_ERRO = (
    '<!doctype html><meta charset="utf-8"><title>OTC Tracker</title>'
    '<body style="font-family:system-ui,sans-serif;margin:3rem">'
    '<h3>OTC Tracker failed to start</h3><pre style="white-space:pre-wrap">%s</pre>')


def _portao(wsgi, base):
    """WSGI na frente do app: enquanto o OTC sobe, o Flask não é chamado.

    Chamado, ele se daria por iniciado, e o `register_blueprint` da subida
    passaria a ser recusado. Só o health check responde desde já — o mesmo
    `{"status": "up"}` da rota do template, nos dois endereços em que ele pode
    vir. Com a subida QUEBRADA ele segue 200 de propósito: derrubado, o
    contêiner levaria o erro junto e o Stratos voltaria à versão anterior sem
    dizer por quê; de pé, o erro fica na tela de quem abrir a solução.
    """
    saude = (base + '/actuator/keepalive', '/actuator/keepalive')

    def otc_stratos_portao(environ, start_response):
        if _SUBIDA['pronto'].is_set() and _SUBIDA['erro'] is None:
            return wsgi(environ, start_response)
        caminho = environ.get('PATH_INFO') or ''
        status = '503 Service Unavailable'
        if caminho in saude:
            corpo, tipo, status = b'{"status": "up"}', 'application/json', '200 OK'
        elif _SUBIDA['erro'] is not None:
            corpo = (_PAGINA_ERRO % html.escape(_SUBIDA['erro'])).encode('utf-8')
            tipo = 'text/html; charset=utf-8'
        elif caminho.startswith(base + '/api/'):
            corpo = json.dumps({'success': False, 'code': 'starting', 'params': {},
                                'text': 'OTC Tracker is starting.'}).encode('utf-8')
            tipo = 'application/json'
        else:
            corpo = (_PAGINA_SUBINDO % (time.time() - _SUBIDA['inicio'])).encode('utf-8')
            tipo = 'text/html; charset=utf-8'
        start_response(status, [('Content-Type', tipo), ('Content-Length', str(len(corpo))),
                                ('Retry-After', '5'), ('Cache-Control', 'no-store')])
        return [corpo]

    return otc_stratos_portao


# ── Proxy, chave de sessão e awmpy ──────────────────────────────────────────

def _proxy_do_stratos():
    """A saída para a internet (BCB, Yahoo, IBGE, NY Fed) é pelo proxy do Stratos.

    `configure_proxy_env_vars` põe HTTP(S)_PROXY e NO_PROXY no processo — a
    opção C da documentação de conectividade do Stratos —, e o `requests` os
    respeita. As Cotações e as Tools copiam o proxy do sistema para a sessão
    (a rota "system proxy" do `quotes._routes`), e o acham ali. O
    `QUOTES_PROXY` vazio tira da fila o proxy corporativo do desktop, que da
    AWS não responde e custaria o timeout de conexão a cada busca. Roda antes
    do import do `apps`: o `quotes` lê o `QUOTES_PROXY` no import.
    """
    try:
        from stratosblocks.connectivity import configure_proxy_env_vars
    except ImportError:
        log.warning('[stratos] stratosblocks.connectivity ausente: sem proxy de saida')
    else:
        configure_proxy_env_vars()
    os.environ.setdefault('QUOTES_PROXY', '')


# A pasta do OTC dentro do Shared Drive da solução.
_PASTA_NO_DRIVE = 'otc-tracker'


def _raiz_no_shared_drive():
    """Os dados e os bancos moram no Stratos Shared Drive (HANDOFF §681).

    O disco do contêiner some a cada deploy e leva os bancos junto. O Shared
    Drive é o EFS da solução: montado como diretório comum, persiste entre os
    deploys e é o MESMO para todos os web workers — o desenho de hoje, com
    várias instâncias sobre o mesmo `db/`, só que com o EFS no lugar do SMB. É a
    raiz que o bloco ENV:STRATOS do `config.py` lê no `OTC_STRATOS_ROOT`, e por
    isso este passo roda ANTES do `import apps`; o `config.py` não importa o
    `stratosblocks` (a dev nunca o importa).

    A variável definida no ambiente vence, e o `get_shared_drive` só responde
    quando ela falta. Sem os dois, a raiz fica no /tmp do bloco ENV:STRATOS: o
    app sobe, mas o que gravar some no deploy — e o log diz isso.

    A chave da sessão vai para lá também (`OTC_SECRET_KEY_FILE`): o drive é
    privado da solução, e uma chave que sobrevive ao deploy e é a mesma em todo
    worker mantém a sessão de quem está logado. A `SECRET_KEY` do ambiente
    continua vencendo.

    Devolve a raiz, ou None quando ficou no /tmp.
    """
    raiz = (os.getenv('OTC_STRATOS_ROOT') or '').strip()
    origem = 'OTC_STRATOS_ROOT'
    if not raiz:
        try:
            from stratosblocks.utilities import get_shared_drive
        except ImportError:
            log.warning('[stratos] sem OTC_STRATOS_ROOT e sem o get_shared_drive: dados '
                        'no /tmp do conteiner, que somem a cada deploy')
            return None
        try:
            raiz = get_shared_drive(path=_PASTA_NO_DRIVE)
        except Exception:                                   # noqa: BLE001
            log.exception('[stratos] get_shared_drive falhou: dados no /tmp do '
                          'conteiner, que somem a cada deploy')
            return None
        origem = 'Shared Drive'
    # Fora do contêiner o `get_shared_drive` devolve uma pasta RELATIVA (o
    # `local_data_dir`), e o app recusa caminho de banco relativo.
    raiz = os.path.abspath(str(raiz))
    os.makedirs(raiz, exist_ok=True)
    os.environ['OTC_STRATOS_ROOT'] = raiz
    os.environ.setdefault('OTC_SECRET_KEY_FILE', os.path.join(raiz, 'secret_key.txt'))
    log.warning('[stratos] dados em %s (%s)', raiz, origem)
    _dados_do_pacote(raiz)
    return raiz


def _dados_do_pacote(raiz):
    """O pacote ATIVO (HANDOFF §708): com o ponteiro `<raiz>/dados-ativos.txt`
    apontando um pacote conferido, os DADOS e os bancos passam a ser os dele
    (`OTC_DATA_DIR`/`OTC_DATABASE_DIR`, que o bloco ENV:STRATOS lê no import do
    `config.py`). O resto — o `share/` da ponte, a chave da sessão — fica na
    raiz. A variável definida no ambiente vence; ponteiro para pacote que não
    está conferido não vale, e a subida fica em `<raiz>/data` avisando."""
    if (os.getenv('OTC_DATA_DIR') or '').strip() or (os.getenv('OTC_DATABASE_DIR') or '').strip():
        return None
    import pacotes_dados as PD
    data, motivo = PD.dados_ativos(raiz)
    if motivo:
        log.warning('[stratos] ponteiro de dados IGNORADO (%s): dados em %s', motivo,
                    os.path.join(raiz, 'data'))
    if not data:
        return None
    os.environ['OTC_DATA_DIR'] = data
    os.environ['OTC_DATABASE_DIR'] = os.path.join(data, 'db')
    log.warning('[stratos] dados do pacote %s: %s', PD.ativo(raiz), data)
    return data


def _ponte_manifestos(app):
    """A metade da PONTE do share que roda aqui (HANDOFF §683; a regra está no
    `ponte_comum`): uma thread escreve, por pasta, o manifesto do lado do
    Stratos em `<raiz>/ponte/manifesto/` — caminho, mtime e tamanho de cada
    arquivo sob o `SHARED_DRIVE_ROOT` —, que a ponte da máquina do JPM lê numa
    chamada só. Na metade do intervalo da pasta, para a ponte achar o
    manifesto fresco. `OTC_PONTE=0` e o `OTC_DISABLE_SCHEDULERS=1` dos testes a
    desligam. Sem raiz no Shared Drive (o /tmp) não há ponte para quem
    escrever, e ela não sobe."""
    if os.getenv('OTC_PONTE', '1').strip() == '0' or \
            os.getenv('OTC_DISABLE_SCHEDULERS', '').strip() == '1':
        return None
    raiz = (os.getenv('OTC_STRATOS_ROOT') or '').strip()
    share = app.config.get('SHARED_DRIVE_ROOT')
    if not raiz or not share:
        log.warning('[ponte] sem OTC_STRATOS_ROOT: os manifestos da ponte nao sobem')
        return None
    import ponte_comum as P
    pasta_ponte = os.path.join(raiz, 'ponte')
    instancia = P.instancia_do_drive(pasta_ponte)

    def laco():
        proximo, avisado = {}, {}
        while True:
            agora = time.time()
            for p in P.PASTAS:
                if proximo.get(p.slug, 0) > agora:
                    continue
                proximo[p.slug] = agora + max(10, p.intervalo // 2)
                try:
                    P.escreve_manifesto(share, pasta_ponte, p, agora, instancia)
                except Exception as e:                      # noqa: BLE001
                    if agora - avisado.get(p.slug, 0) > 600:
                        avisado[p.slug] = agora
                        log.warning('[ponte] manifesto de %s falhou: %s: %s', p.slug,
                                    type(e).__name__, e)
            time.sleep(5)

    t = threading.Thread(target=laco, name='ponte-manifesto', daemon=True)
    t.start()
    log.warning('[ponte] manifestos em %s (instancia %s)', pasta_ponte, instancia)
    return t


def _rota_prova_travas(app, stratos_auth):
    """`/stratos/prova-travas`, só do master: a prova de que as travas do app
    valem no Shared Drive (HANDOFF §681, passo B; o trabalho é do
    `prova_travas.py`, que roda processos filhos sobre `<raiz>/prova-travas`).

        ?modo=local                       (o padrão) os testes neste contêiner
        ?modo=segurar&segundos=300        deixa as travas presas e volta
        ?modo=conferir[&soltar=1]         tenta pegá-las (vale noutro host)

    Fica fora do blueprint do OTC (como o whoami): quem a autoriza é a
    identidade do Stratos, não a sessão do app. A medida de abertura dos bancos
    vai pelo `duckdb_read`, que respeita as travas dos bancos em uso."""
    from apps.pages import routes
    from apps.pages.database_access import duckdb_read

    def otc_stratos_prova_travas():
        sid, _ = _identidade(stratos_auth, routes)
        if sid not in routes._MASTER_SIDS:
            return jsonify({'success': False, 'code': 'master_only', 'params': {},
                            'text': 'Only the master can run the lock probe.'}), 403
        raiz = (os.getenv('OTC_STRATOS_ROOT') or '').strip()
        if not raiz:
            return jsonify({'success': False, 'code': 'no_shared_drive', 'params': {},
                            'text': 'OTC_STRATOS_ROOT is not set: there is no drive to probe.'}), 409
        import prova_travas as PT
        modo = (request.args.get('modo') or 'local').strip().lower()
        if modo not in ('local', 'segurar', 'conferir'):
            return jsonify({'success': False, 'code': 'bad_mode', 'params': {'modo': modo},
                            'text': 'modo must be local, segurar or conferir.'}), 400
        try:
            segundos = int(request.args.get('segundos') or 300)
        except ValueError:
            segundos = 300
        log.warning('[stratos] prova das travas: modo=%s SID=%s', modo, sid)
        try:
            out = PT.roda(modo, os.path.join(raiz, 'prova-travas'),
                          db_dir=app.config.get('DATABASE_DIR'), abre=duckdb_read,
                          segundos=segundos, soltar=request.args.get('soltar') == '1')
        except Exception as e:                              # noqa: BLE001
            log.exception('[stratos] a prova das travas quebrou')
            return jsonify({'success': False, 'code': 'probe_failed', 'params': {},
                            'text': '%s: %s' % (type(e).__name__, e)}), 500
        out['success'] = True
        return jsonify(out)

    app.add_url_rule('/stratos/prova-travas', 'otc_stratos_prova_travas',
                     otc_stratos_prova_travas)


_CONFERINDO = {}                    # nome → progresso da conferência em curso
_CONFERINDO_LOCK = threading.Lock()

_PAGINA_PACOTES = '''<!doctype html><meta charset="utf-8"><title>OTC Tracker data packages</title>
%(refresh)s<body style="font-family:system-ui,sans-serif;margin:2rem;max-width:1100px">
<h3>Data packages</h3>
<p>Data now: <code>%(dados)s</code>%(nota)s</p>%(msg)s
<table cellpadding="6" style="border-collapse:collapse;font-size:.9rem">
<tr style="text-align:left;border-bottom:1px solid #999"><th>Package</th><th>State</th><th>Files</th>
<th>MB</th><th>duckdb</th><th>Sent</th><th>Checked</th><th></th></tr>%(linhas)s</table>
<p style="color:#666;font-size:.85rem">Check joins the parts and verifies every file against the
manifest (sha256). Activate takes effect on the NEXT restart; the current data stays as it is.</p>'''


def _rota_ida(app, stratos_auth):
    """`/stratos/ida`, só do master: para cada recurso do
    `OTC_STRATOS_IDA_RECURSOS`, se o token do IDA sai (o tamanho, nunca o
    token) e, se não, o erro CRU do stratosblocks — é o que o suporte do
    Stratos pede para rastrear (§714)."""
    from apps.pages import routes

    def otc_stratos_ida():
        sid, _ = _identidade(stratos_auth, routes)
        if sid not in routes._MASTER_SIDS:
            return jsonify({'success': False, 'code': 'master_only', 'params': {},
                            'text': 'Only the master can test the IDA tokens.'}), 403
        import ida_token
        out = ida_token.diagnostico()
        log.warning('[stratos] diagnóstico do IDA: SID=%s %s', sid,
                    ', '.join('%s=%s' % (r['host'], 'ok' if r['ok'] else 'ERRO') for r in out['recursos'])
                    or 'sem recurso configurado')
        out['success'] = True
        return jsonify(out)

    app.add_url_rule('/stratos/ida', 'otc_stratos_ida', otc_stratos_ida)


def _rota_pacotes(app, stratos_auth):
    """`/stratos/pacotes`, só do master: a chegada dos bancos (HANDOFF §681
    passo C, §708; a regra é do `pacotes_dados.py`). GET lista (`?format=json`
    devolve JSON); POST com `acao` = `conferir` | `ativar` | `desativar` e
    `nome`. A conferência lê gigabytes e roda numa thread; a página se
    recarrega enquanto ela anda."""
    from apps.pages import routes
    import pacotes_dados as PD

    def _raiz():
        return (os.getenv('OTC_STRATOS_ROOT') or '').strip()

    def _confere_em_fundo(raiz, nome):
        import duckdb

        def progresso(i, n, caminho):
            with _CONFERINDO_LOCK:
                _CONFERINDO[nome] = {'i': i, 'n': n, 'arquivo': caminho}
        try:
            conf = PD.confere(raiz, nome, duckdb_aqui=duckdb.__version__, progresso=progresso)
            log.warning('[stratos] pacote %s conferido: ok=%s erros=%d', nome, conf['ok'], len(conf['erros']))
        except Exception:                                   # noqa: BLE001
            log.exception('[stratos] a conferência do pacote %s quebrou', nome)
        finally:
            with _CONFERINDO_LOCK:
                _CONFERINDO.pop(nome, None)

    def _pagina(raiz, msg=''):
        pacotes = PD.lista(raiz)
        with _CONFERINDO_LOCK:
            andando = dict(_CONFERINDO)
        esc = html.escape
        linhas = []
        for p in pacotes:
            nome = p['nome']
            if nome in andando:
                a = andando[nome]
                est = 'checking %d/%d' % (a['i'] + 1, a['n'])
            else:
                est = p['estado'] + (' · ACTIVE' if p['ativo'] else '')
            botoes = ''
            if nome not in andando and not p['ativo'] and p['estado'] in ('recebido', 'recusado', 'conferido'):
                botoes += ('<button name="acao" value="conferir">Check</button> ')
            if nome not in andando and not p['ativo'] and p['estado'] == 'conferido':
                botoes += ('<button name="acao" value="ativar">Activate</button>')
            if p['ativo']:
                botoes += ('<button name="acao" value="desativar">Deactivate</button>')
            detalhe = ''.join('<div style="color:#b00">%s</div>' % esc(e) for e in p['erros'][:20])
            detalhe += ''.join('<div style="color:#a60">%s</div>' % esc(e) for e in p['avisos'])
            linhas.append(
                '<tr style="border-bottom:1px solid #ddd;vertical-align:top"><td><code>%s</code>%s</td>'
                '<td>%s</td><td>%d</td><td>%.0f</td><td>%s</td><td>%s</td><td>%s</td>'
                '<td><form method="post" action="/stratos/pacotes"><input type="hidden" name="nome" '
                'value="%s">%s</form></td></tr>'
                % (esc(nome), detalhe, esc(est), p['arquivos'], p['bytes'] / 1048576.0, esc(p['duckdb'] or ''),
                   esc(p['enviado_em'] or ''), esc(p['conferido_em'] or ''), esc(nome), botoes))
        if not linhas:
            linhas.append('<tr><td colspan="8">No package under <code>%s</code>. Send one with '
                          '<code>stratos\\envia_dados.py</code>.</td></tr>' % esc(os.path.join(raiz, PD.PASTA)))
        ativo = PD.ativo(raiz)
        nota = ''
        if ativo and os.path.normpath(app.config.get('DATA_DIR') or '') != os.path.normpath(
                os.path.join(raiz, PD.PASTA, ativo, 'data')):
            nota = ' — <b>restart to switch to %s</b>' % esc(ativo)
        elif not ativo and os.path.normpath(app.config.get('DATA_DIR') or '') != os.path.normpath(
                os.path.join(raiz, 'data')) and (app.config.get('DATA_DIR') or '').startswith(raiz):
            nota = ' — <b>restart to go back to %s</b>' % esc(os.path.join(raiz, 'data'))
        return _PAGINA_PACOTES % {
            'refresh': '<meta http-equiv="refresh" content="5">' if andando else '',
            'dados': esc(app.config.get('DATA_DIR') or ''), 'nota': nota,
            'msg': ('<p style="padding:.5rem;background:#eef">%s</p>' % esc(msg)) if msg else '',
            'linhas': ''.join(linhas)}

    def otc_stratos_pacotes():
        sid, _ = _identidade(stratos_auth, routes)
        if sid not in routes._MASTER_SIDS:
            return jsonify({'success': False, 'code': 'master_only', 'params': {},
                            'text': 'Only the master can manage the data packages.'}), 403
        raiz = _raiz()
        if not raiz:
            return jsonify({'success': False, 'code': 'no_shared_drive', 'params': {},
                            'text': 'OTC_STRATOS_ROOT is not set: there is no drive.'}), 409
        if request.method == 'GET':
            if request.args.get('format') == 'json':
                with _CONFERINDO_LOCK:
                    andando = dict(_CONFERINDO)
                return jsonify({'success': True, 'ativo': PD.ativo(raiz), 'checking': andando,
                                'data_dir': app.config.get('DATA_DIR'), 'pacotes': PD.lista(raiz)})
            return _pagina(raiz)
        acao = (request.form.get('acao') or request.args.get('acao') or '').strip()
        nome = (request.form.get('nome') or request.args.get('nome') or '').strip()
        log.warning('[stratos] pacotes: acao=%s nome=%s SID=%s', acao, nome, sid)
        try:
            if acao == 'conferir':
                PD.estado(raiz, nome)                       # nome válido
                if PD.ativo(raiz) == nome:
                    raise PD.PacoteInvalido('package_active', 'The active package cannot be checked again.')
                with _CONFERINDO_LOCK:
                    if nome in _CONFERINDO:
                        raise PD.PacoteInvalido('already_checking', 'This package is already being checked.')
                    _CONFERINDO[nome] = {'i': 0, 'n': 0, 'arquivo': ''}
                threading.Thread(target=_confere_em_fundo, args=(raiz, nome), daemon=True,
                                 name='pacote-confere').start()
                msg = 'Checking %s.' % nome
            elif acao == 'ativar':
                PD.ativa(raiz, nome)
                msg = '%s is the active package: restart the solution to use it.' % nome
            elif acao == 'desativar':
                PD.desativa(raiz)
                msg = 'No active package: after the restart the data is %s.' % os.path.join(raiz, 'data')
            else:
                raise PD.PacoteInvalido('bad_action', 'acao must be conferir, ativar or desativar.')
        except PD.PacoteInvalido as e:
            if request.args.get('format') == 'json':
                return jsonify({'success': False, 'code': e.code, 'params': e.params, 'text': e.text}), 409
            return _pagina(raiz, e.text), 409
        if request.args.get('format') == 'json':
            return jsonify({'success': True, 'text': msg})
        return _pagina(raiz, msg)

    app.add_url_rule('/stratos/pacotes', 'otc_stratos_pacotes', otc_stratos_pacotes,
                     methods=['GET', 'POST'])


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
    if chave:
        # No Shared Drive (`_raiz_no_shared_drive`) ela sobrevive ao deploy e é
        # a mesma em todo worker; no /tmp, cada deploy desloga todo mundo.
        log.warning('[stratos] SECRET_KEY ausente no ambiente — usando a do arquivo %s',
                    otc._secret_key_file())
        return chave
    log.warning('[stratos] SECRET_KEY ausente e sem arquivo gravavel: chave aleatoria '
                'deste processo. A cada deploy, e entre workers, a sessao se perde (o '
                'SSO a reabre, mas defina SECRET_KEY no task definition).')
    return app.config['SECRET_KEY']


def _garante_awmpy():
    """O `routes` importa o `awmpy` no topo (sem ele o app não sobe), e é pelo
    `awmpy.get_phonebook_data(sid)` que saem o nome, o e-mail e o cargo de quem
    pede acesso pela primeira vez.

    No Stratos o phonebook é o `stratosblocks.utilities.get_phonebook_data`, que
    recebe uma LISTA de SIDs e devolve as mesmas chaves (`nameFull`, `email`,
    `positionName`, `standardID`...). O `awmpy` vira uma casca dele e o `routes`
    não muda. Sem nenhum dos dois, o substituto responde "indisponível" e o
    pedido de acesso segue com o nome que o Stratos informou.
    """
    try:
        from stratosblocks.utilities import get_phonebook_data as do_stratos
    except ImportError:
        do_stratos = None
    if do_stratos is not None:
        casca = types.ModuleType('awmpy')
        casca._otc_stratos_phonebook = True

        def get_phonebook_data(sid):
            return _registro_do_phonebook(do_stratos([sid]), sid)

        casca.get_phonebook_data = get_phonebook_data
        sys.modules['awmpy'] = casca
        log.warning('[stratos] phonebook pelo stratosblocks.utilities')
        return
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


def _registro_do_phonebook(resposta, sid):
    """O registro do SID na resposta do `get_phonebook_data([sid])`. Com um SID
    só, ela vem como o próprio registro (um dict com `standardID`). Lista de
    registros e dict por SID também são aceitos, para o dia em que a forma
    mudar. Registro de OUTRO SID não serve: levanta, e o
    `get_user_data_from_phonebook` do OTC loga e devolve None."""
    alvo = str(sid or '').strip().upper()

    def dele(reg):
        return isinstance(reg, dict) and str(reg.get('standardID') or '').strip().upper() == alvo

    if isinstance(resposta, dict):
        if 'standardID' in resposta or 'nameFull' in resposta:
            if dele(resposta) or not resposta.get('standardID'):
                return resposta
        else:
            for chave, reg in resposta.items():
                if str(chave).strip().upper() == alvo and isinstance(reg, dict):
                    return reg
    elif isinstance(resposta, (list, tuple)):
        for reg in resposta:
            if dele(reg):
                return reg
        if len(resposta) == 1 and isinstance(resposta[0], dict) and not resposta[0].get('standardID'):
            return resposta[0]
    raise LookupError('phonebook do Stratos sem registro para %s' % alvo)


# ── Ponte de SSO: a identidade do Stratos abre a sessão do OTC ──────────────

def _ponte_sso(stratos_auth):
    from apps.pages import routes   # só existe depois do register_blueprints

    def otc_stratos_sso():
        # Só nas rotas do OTC. As do app passam intactas: o estático, o health
        # check (o balanceador o chama sem identidade), o whoami e as do
        # StratosAuth — o /login/callback é onde a identidade NASCE, e barrado
        # ali (era o "not authorized" na volta do SSO) o login não terminava.
        # `/static/data/...` é rota do OTC e passa pela ponte.
        if request.blueprint != 'pages_blueprint':
            return None
        endpoint = request.endpoint
        if endpoint == 'pages_blueprint.logout':
            # Antes da rota do OTC, que faria o `session.clear()`.
            log.warning('[stratos] logout: SID=%s', session.get('user_sid'))
            _limpa_sessao_otc()
            session[_SAIU] = True
            return redirect(url_for('pages_blueprint.sign_in_page'))
        if session.get(_SAIU):
            if endpoint == 'pages_blueprint.sign_in_page' and request.args.get('entrar') == '1':
                session.pop(_SAIU, None)        # segue: a sessão reabre e a tela leva ao dashboard
            elif endpoint in _LIVRE_SEM_SESSAO or _traducao(endpoint):
                return None
            elif request.path.startswith('/api/'):
                # 401 é "sem sessão" para o session-guard.js de uma aba que
                # ficou aberta: ele avisa e leva ao login, que é a tela de saída.
                return jsonify({'success': False, 'code': 'signed_out', 'params': {},
                                'text': 'You have signed out of OTC Tracker.'}), 401
            elif endpoint == 'pages_blueprint.sign_in_page':
                return render_template_string(_PAGINA_SAIU, segment='stratos-signed-out')
            else:
                return redirect(url_for('pages_blueprint.sign_in_page'))
        sid, usuario = _identidade(stratos_auth, routes)
        if not sid:
            _limpa_sessao_otc()
            return _negado(403, 'not_authorized',
                           'You are not authorized to view this page.')
        if session.get('authenticated') and \
                (session.get('user_sid') or '').strip().upper() == sid:
            # O IP deixa de ser critério: atrás do proxy do Stratos ele nem é o
            # do usuário, e quem identifica é o SSO. Carimbado a cada request, o
            # `enforce_session_ip` não derruba ninguém.
            session['session_ip'] = routes.get_client_ip()
            if endpoint == 'pages_blueprint.unlock':
                return _destrava(routes, sid)
        else:
            resposta = _abre_sessao(routes, sid, usuario)
            if resposta is not None:
                return resposta
        if request.endpoint in _TELAS_DE_LOGIN:
            return redirect(url_for('pages_blueprint.dashboard'))
        return None

    return otc_stratos_sso


def _traducao(endpoint):
    """As traduções que a tela de saída pede (`/static/data/translations/...`)."""
    nome = str((request.view_args or {}).get('filename') or '')
    return (endpoint == 'pages_blueprint.static_data_file'
            and nome.startswith('translations/') and '..' not in nome)


def _destrava(routes, sid):
    """O Unlock da tela travada. O do OTC confere o IP gravado no cadastro e, se
    não bate, manda o código por e-mail — atrás do proxy do Stratos o IP não é o
    do usuário e o SMTP da rede não responde, e a tela ficava travada para
    sempre. Aqui basta digitar o SID: o MESMO que o SSO identificou. A trava é
    de privacidade (a tela coberta), não um segundo login."""
    if not session.get('locked'):
        return redirect(url_for('pages_blueprint.dashboard'))
    digitado = request.form.get('sid', '').strip().upper()
    if not routes._validate_sid(digitado):
        flash('Invalid SID format. Must be 1 letter + 6 numbers.', 'error')
        return redirect(url_for('pages_blueprint.lock_screen_page'))
    if digitado != sid:
        log.warning('[stratos] unlock recusado: digitado=%s sessao=%s', digitado, sid)
        flash('This SID does not match the locked account.', 'error')
        return redirect(url_for('pages_blueprint.lock_screen_page'))
    session.pop('locked', None)
    log.warning('[stratos] tela destravada: SID=%s', sid)
    return redirect(url_for('pages_blueprint.dashboard'))


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
    _limpa_sessao_otc()
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


def _limpa_sessao_otc():
    for chave in _CHAVES_OTC:
        session.pop(chave, None)


# A tela de quem saiu: a do pedido de acesso, com um botão só. "Sign in again"
# reabre pelo SSO, sem pedir SID. O texto nasce em inglês e a própria tela o
# traduz por um mapa local, pela língua que o usuário escolheu no app.
_PAGINA_SAIU = """{% extends 'layouts/base.html' %}
{% block title %}Signed Out{% endblock title %}
{% block content %}
<div class="auth-box p-0 w-100">
  <div class="row w-100 g-0">
    <div class="col-md-auto">
      <div class="card auth-box-form border-0 mb-0">
        <div class="card-body min-vh-100 d-flex flex-column justify-content-center">
          <div class="auth-brand mb-0 text-center">
            <a class="logo-dark" href="/"><img alt="dark logo" height="80" src="{{ config.ASSETS_ROOT }}/images/logo-black.png" /></a>
            <a class="logo-light" href="/"><img alt="logo" height="80" src="{{ config.ASSETS_ROOT }}/images/logo.png" /></a>
          </div>
          <div class="mt-auto mx-auto" id="otc-stratos-saiu" style="max-width: 380px;">
            <h4 class="fw-bold text-center mb-2" data-otc-saiu="t">You have signed out</h4>
            <p class="text-muted text-center mb-4" data-otc-saiu="m">Your OTC Tracker session was closed. You are still signed in to Stratos, so signing in again will not ask for your SID.</p>
            <div class="d-grid">
              <a class="btn btn-primary fw-semibold py-2" href="/auth-2-sign-in?entrar=1" data-otc-saiu="b">Sign in again</a>
            </div>
          </div>
          <p class="text-center text-muted mt-auto mb-0">&copy; <script>document.write(new Date().getFullYear())</script> OTC Tracker by <span class="fw-semibold">JPMorganChase &amp; Co.</span></p>
        </div>
      </div>
    </div>
    <div class="col">
      <div class="h-100 position-relative card-side-img rounded-0 overflow-hidden">
        <div class="p-4 card-img-overlay auth-overlay"></div>
      </div>
    </div>
  </div>
</div>
{% endblock content %}
{% block extra_javascript %}
<script>
(function () {
  var T = {
    br: {t: 'Você saiu', m: 'Sua sessão do OTC Tracker foi encerrada. Você continua conectado ao Stratos, então entrar de novo não pede o SID.', b: 'Entrar novamente'},
    es: {t: 'Ha cerrado sesión', m: 'Su sesión de OTC Tracker fue cerrada. Sigue conectado a Stratos, así que volver a entrar no pide el SID.', b: 'Entrar de nuevo'}
  };
  var l = 'en';
  try { l = localStorage.getItem('__OTC_TRACKER_LANG__') || 'en'; } catch (e) {}
  var x = T[l];
  if (!x) return;
  document.querySelectorAll('[data-otc-saiu]').forEach(function (el) {
    el.textContent = x[el.getAttribute('data-otc-saiu')];
  });
})();
</script>
{% endblock extra_javascript %}"""


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
