"""O token do IDAnywhere no lugar do Kerberos, para os sistemas internos (§714).

No desktop a Athena autentica por Kerberos: o `athena_api.build_session` põe o
`HttpNegotiateAuth` do `requests-negotiate-sspi`, e o ADFS
(`/adfs/oauth2/authorize/wia`) troca o ticket do Windows pela sessão. No
contêiner do Stratos não há Windows nem ticket: o caminho é o token do IDA
(*bearer*) que o próprio Stratos emite, mandado no `Authorization`.

O Stratos emite o token de duas formas, e a escolha é de QUEM a consulta roda
em nome:

  · do USUÁRIO logado (`UserAuthentication().get_resource_token(recurso)`):
    exige registrar os recursos no `StratosAuth(app, resources=[…])` — e essa
    linha está no bloco DO NOT DELETE do `solution.py`, que o pipeline do
    Stratos confere com o template. Fica para quando o Stratos disser como
    registrar fora do construtor;
  · do FID, a identidade da APLICAÇÃO — é a que serve aos laços de fundo (o
    pull da API de New Deals, a recompra a cada 30 min, o Cockpit), que rodam
    sem ninguém logado. Com `OTC_STRATOS_FID_APP_ID` é o FID PRÓPRIO da solução
    (`solution_fid.token_retrieval`, o recomendado quando o acesso tem de ser
    só desta solução); sem ele, o FID compartilhado do Stratos
    (`fid.get_stratos_fid_token`), que só vale se o dono do dado aceitou TODOS
    os usuários do Stratos.

Configuração (variáveis de ambiente da solução — nada disto é segredo):

  OTC_STRATOS_IDA_RECURSOS   host=recurso, separados por vírgula, ex.:
                             athena-app.jpmchase.net=JPMC:URI:RS-…-PROD
                             (o recurso vem do time da Athena; sem nenhum, a
                             sessão segue como estava e o log avisa)
  OTC_STRATOS_IDA_AMBIENTE   prod | uat (padrão: o sufixo do recurso, -UAT → uat)
  OTC_STRATOS_FID_APP_ID     o app_id da solução (FID próprio); vazio = o
                             FID compartilhado do Stratos
  OTC_STRATOS_IDA_TTL_MIN    minutos até pedir outro token (padrão 45; o
                             Stratos renova o do usuário a cada 50)

O embrulho fica POR FORA do desvio do proxy (`proxy_interno`): ele vê o
endereço da Athena, põe o cabeçalho, e o proxy troca a URL depois. Cada salto
de redirecionamento passa de novo por aqui (o `requests` tira o
`Authorization` quando o host muda, e ele volta se o host novo tem recurso).
O token nunca vai para o log.
"""
import logging
import os
import threading
import time
from urllib.parse import urlsplit

log = logging.getLogger('otc_tracker')

_lock = threading.Lock()
_cache = {}                 # recurso -> (token, obtido_em)


def recursos():
    """`{host: recurso}` do `OTC_STRATOS_IDA_RECURSOS`."""
    out = {}
    for par in (os.getenv('OTC_STRATOS_IDA_RECURSOS') or '').split(','):
        host, _, rec = par.partition('=')
        host, rec = host.strip().lower(), rec.strip()
        if host and rec:
            out[host] = rec
    return out


def ambiente(recurso):
    env = (os.getenv('OTC_STRATOS_IDA_AMBIENTE') or '').strip().lower()
    if env in ('prod', 'uat'):
        return env
    return 'uat' if recurso.upper().endswith('-UAT') else 'prod'


def _ttl():
    try:
        return max(1.0, float(os.getenv('OTC_STRATOS_IDA_TTL_MIN', '45'))) * 60
    except ValueError:
        return 45 * 60


def _emite(recurso):
    """Pede um token novo ao Stratos. Levanta com o erro CRU do stratosblocks."""
    env = ambiente(recurso)
    app_id = (os.getenv('OTC_STRATOS_FID_APP_ID') or '').strip()
    if app_id:
        from stratosblocks.authentication.solution_fid import token_retrieval
        tok = token_retrieval(app_id=app_id, resource_id=recurso, environment=env)
    else:
        from stratosblocks.authentication.fid import get_stratos_fid_token
        tok = get_stratos_fid_token(recurso, environment=env)
    tok = getattr(tok, 'access_token', tok)
    if not tok or not isinstance(tok, str):
        raise RuntimeError('o Stratos não devolveu token para %s (%s)' % (recurso, env))
    return tok


def token(recurso, novo=False):
    """O token do recurso, do cache enquanto não passou o TTL."""
    with _lock:
        ent = _cache.get(recurso)
        if ent and not novo and time.time() - ent[1] < _ttl():
            return ent[0]
    tok = _emite(recurso)
    with _lock:
        _cache[recurso] = (tok, time.time())
    return tok


def esquece(recurso=None):
    with _lock:
        if recurso is None:
            _cache.clear()
        else:
            _cache.pop(recurso, None)


def autentica(sessao, mapa=None):
    """Embrulha o `send` da sessão: pedido a host com recurso leva o
    `Authorization: Bearer`; um 401 pede token novo e tenta UMA vez mais."""
    mapa = recursos() if mapa is None else mapa
    original = sessao.send

    def send(request, **kw):
        host = (urlsplit(request.url or '').hostname or '').lower()
        rec = mapa.get(host)
        if not rec:
            return original(request, **kw)
        pedido = request.copy()
        pedido.headers['Authorization'] = 'Bearer ' + token(rec)
        resp = original(pedido, **kw)
        if resp.status_code == 401:
            log.warning('[stratos] %s respondeu 401 ao token do IDA (%s): pedindo outro',
                        host, rec)
            pedido = request.copy()
            pedido.headers['Authorization'] = 'Bearer ' + token(rec, novo=True)
            resp = original(pedido, **kw)
        return resp

    sessao.send = send
    sessao._otc_stratos_ida = True
    return sessao


def instala():
    """Troca o `athena_api.build_session` por um que devolve a sessão com o
    token, POR FORA do desvio do proxy (chamar depois do
    `proxy_interno.instala`). Sem recurso configurado, nada muda. Devolve se
    instalou."""
    mapa = recursos()
    if not mapa:
        log.warning('[stratos] sem OTC_STRATOS_IDA_RECURSOS: a Athena vai sem token do IDA '
                    '(e sem Kerberos no Linux, o ADFS recusa)')
        return False
    from apps.pages import athena_api
    if getattr(athena_api.build_session, '_otc_stratos_ida', False):
        return True
    anterior = athena_api.build_session

    def build_session():
        return autentica(anterior(), mapa)

    build_session._otc_stratos_ida = True
    build_session._otc_stratos_proxy = getattr(anterior, '_otc_stratos_proxy', False)
    build_session.__wrapped__ = anterior
    athena_api.build_session = build_session
    log.warning('[stratos] token do IDA (%s) para: %s',
                'FID da solução' if (os.getenv('OTC_STRATOS_FID_APP_ID') or '').strip()
                else 'FID do Stratos', ', '.join(sorted(mapa)))
    return True


def diagnostico():
    """Para a rota do master: cada recurso, se o token sai (sem mostrá-lo) e,
    se não, o erro CRU do stratosblocks."""
    out = []
    for host, rec in sorted(recursos().items()):
        item = {'host': host, 'recurso': rec, 'ambiente': ambiente(rec)}
        try:
            tok = token(rec, novo=True)
            item.update(ok=True, tamanho=len(tok))
        except Exception as exc:                            # noqa: BLE001
            item.update(ok=False, erro='%s: %s' % (type(exc).__name__, exc))
        out.append(item)
    return {'fid': 'solucao' if (os.getenv('OTC_STRATOS_FID_APP_ID') or '').strip() else 'stratos',
            'recursos': out}
