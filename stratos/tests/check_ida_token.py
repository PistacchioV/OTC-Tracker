"""Confere o token do IDA no lugar do Kerberos (stratos/src/ida_token.py, §714).

O `stratosblocks` é de mentira (o `fid.get_stratos_fid_token` e o
`solution_fid.token_retrieval`, que conta quantas vezes emitiu), e a rede
também: a "Athena" só responde o JSON com `Authorization: Bearer <válido>` e
responde 401 ao token velho.

  1. a configuração: `host=recurso` por vírgula, o ambiente pelo sufixo;
  2. o cabeçalho só vai ao host com recurso (o BCB vai sem);
  3. o token sai do cache até o TTL, e o 401 pede outro e tenta UMA vez;
  4. FID da solução (`OTC_STRATOS_FID_APP_ID`) × FID do Stratos;
  5. com o proxy: o token por FORA do desvio — o pedido sai pelo proxy com o
     `Authorization` e o `target-server` da Athena;
  6. o `athena_api.get_json_url` de verdade chega ao JSON;
  7. `instala`: sem recurso não troca; com, troca uma vez só, por fora do
     proxy; o diagnóstico nunca mostra o token e devolve o erro cru.

    python stratos/tests/check_ida_token.py
"""
import json
import os
import sys
import tempfile
import types
from urllib.parse import urlsplit

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), 'src'))
sys.path.insert(0, RAIZ)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', tempfile.mkdtemp(prefix='share-root-'))
for k in ('OTC_STRATOS_IDA_RECURSOS', 'OTC_STRATOS_IDA_AMBIENTE', 'OTC_STRATOS_FID_APP_ID',
          'OTC_STRATOS_IDA_TTL_MIN'):
    os.environ.pop(k, None)

import requests                                                   # noqa: E402
from requests.adapters import BaseAdapter                         # noqa: E402
from requests.structures import CaseInsensitiveDict               # noqa: E402

FALHAS = []
ATHENA = 'athena-app.jpmchase.net'
REC = 'JPMC:URI:RS-11111-22222-Athena-PROD'
PROXY = 'proxy.stratos.teste'
PEDIDOS = []
EMITIDOS = []
VALIDO = {'tok': 'tok-1'}


def ok(cond, msg):
    print(('ok    ' if cond else 'FAIL  ') + msg)
    if not cond:
        FALHAS.append(msg)


# ── o stratosblocks de mentira ──────────────────────────────────────────────
def get_stratos_fid_token(recurso, environment=None):
    EMITIDOS.append(('stratos', recurso, environment))
    return 'tok-%d' % len(EMITIDOS)


def token_retrieval(app_id=None, resource_id=None, environment=None):
    EMITIDOS.append(('solucao', resource_id, environment, app_id))
    return types.SimpleNamespace(access_token='tok-%d' % len(EMITIDOS))


sb = types.ModuleType('stratosblocks')
sb_auth = types.ModuleType('stratosblocks.authentication')
sb_fid = types.ModuleType('stratosblocks.authentication.fid')
sb_fid.get_stratos_fid_token = get_stratos_fid_token
sb_sol = types.ModuleType('stratosblocks.authentication.solution_fid')
sb_sol.token_retrieval = token_retrieval
sys.modules.update({'stratosblocks': sb, 'stratosblocks.authentication': sb_auth,
                    'stratosblocks.authentication.fid': sb_fid,
                    'stratosblocks.authentication.solution_fid': sb_sol})

import ida_token as IT                                            # noqa: E402
import proxy_interno as PI                                        # noqa: E402


def get_proxied_url(internal_url, headers=None, files=False):
    p = urlsplit(internal_url)
    cab = dict(headers or {})
    cab['target-server'] = p.hostname
    return ('https://%s%s%s' % (PROXY, p.path, ('?' + p.query) if p.query else ''), cab,
            {'https': 'http://saida.stratos.teste:3128'})


class Rede(BaseAdapter):
    def send(self, request, **kw):
        p = urlsplit(request.url)
        host = request.headers.get('target-server') if p.hostname == PROXY else p.hostname
        aut = request.headers.get('Authorization', '')
        PEDIDOS.append({'host_url': p.hostname, 'alvo': host, 'aut': aut})
        status, corpo = 200, b'{"ok": true}'
        if host == ATHENA:
            if aut != 'Bearer ' + VALIDO['tok']:
                status, corpo = 401, b'{"error": "unauthorized"}'
            else:
                corpo = json.dumps({'trades': [1, 2]}).encode()
        r = requests.Response()
        r.status_code = status
        r.headers = CaseInsensitiveDict({'Content-Type': 'application/json'})
        r._content = corpo
        r._content_consumed = True
        r.url = request.url
        r.request = request
        r.encoding = 'utf-8'
        return r

    def close(self):
        pass


def crua():
    s = requests.Session()
    s.trust_env = False
    s.mount('https://', Rede())
    s.mount('http://', Rede())
    return s


def reinicia(valido='tok-1'):
    IT.esquece()
    EMITIDOS.clear()
    PEDIDOS.clear()
    VALIDO['tok'] = valido


print('== 1. a configuração ==')
os.environ['OTC_STRATOS_IDA_RECURSOS'] = (' %s = %s , athena-reports.jpmchase.net=JPMC:URI:RS-3-4-Rep-UAT,'
                                          ' lixo, =sem-host' % (ATHENA.upper(), REC))
ok(IT.recursos() == {ATHENA: REC, 'athena-reports.jpmchase.net': 'JPMC:URI:RS-3-4-Rep-UAT'},
   'host=recurso por vírgula, host em minúsculas, entradas tortas fora (%r)' % IT.recursos())
ok(IT.ambiente(REC) == 'prod' and IT.ambiente('JPMC:URI:RS-3-4-Rep-UAT') == 'uat',
   'o ambiente sai do sufixo')
os.environ['OTC_STRATOS_IDA_AMBIENTE'] = 'uat'
ok(IT.ambiente(REC) == 'uat', 'OTC_STRATOS_IDA_AMBIENTE vence')
del os.environ['OTC_STRATOS_IDA_AMBIENTE']

print('\n== 2. o cabeçalho só no host com recurso ==')
reinicia()
s = IT.autentica(crua(), {ATHENA: REC})
r = s.get('https://%s/api/trades' % ATHENA, timeout=5)
ok(r.json() == {'trades': [1, 2]} and PEDIDOS[-1]['aut'] == 'Bearer tok-1', 'Athena com o Bearer')
s.get('https://api.bcb.gov.br/x', timeout=5)
ok(PEDIDOS[-1]['aut'] == '', 'o BCB sem cabeçalho nenhum')
ok(EMITIDOS == [('stratos', REC, 'prod')], 'FID do Stratos, ambiente prod (%r)' % EMITIDOS)

print('\n== 3. cache, TTL e o 401 ==')
s.get('https://%s/api/trades' % ATHENA, timeout=5)
ok(len(EMITIDOS) == 1, 'a segunda chamada usa o token do cache')
os.environ['OTC_STRATOS_IDA_TTL_MIN'] = '1'
IT._cache[REC] = (IT._cache[REC][0], IT._cache[REC][1] - 61)
VALIDO['tok'] = 'tok-2'
r = s.get('https://%s/api/trades' % ATHENA, timeout=5)
ok(len(EMITIDOS) == 2 and r.status_code == 200, 'passado o TTL, pede outro')
del os.environ['OTC_STRATOS_IDA_TTL_MIN']
VALIDO['tok'] = 'tok-3'                           # o servidor passou a recusar o tok-2
PEDIDOS.clear()
r = s.get('https://%s/api/trades' % ATHENA, timeout=5)
ok(r.status_code == 200 and [p['aut'] for p in PEDIDOS] == ['Bearer tok-2', 'Bearer tok-3'],
   '401: pede outro e tenta UMA vez (%r)' % [p['aut'] for p in PEDIDOS])
VALIDO['tok'] = 'nunca'
PEDIDOS.clear()
r = s.get('https://%s/api/trades' % ATHENA, timeout=5)
ok(r.status_code == 401 and len(PEDIDOS) == 2, 'recusado de novo: devolve o 401, sem laço')

print('\n== 4. FID da solução ==')
reinicia()
os.environ['OTC_STRATOS_FID_APP_ID'] = 'app-76521'
IT.autentica(crua(), {ATHENA: REC}).get('https://%s/api/trades' % ATHENA, timeout=5)
ok(EMITIDOS == [('solucao', REC, 'prod', 'app-76521')], 'token_retrieval com o app_id (%r)' % EMITIDOS)
ok(PEDIDOS[-1]['aut'] == 'Bearer tok-1', 'o access_token do objeto vai no cabeçalho')
del os.environ['OTC_STRATOS_FID_APP_ID']

print('\n== 5. com o proxy: o token por fora ==')
reinicia()
s = IT.autentica(PI.proxia(crua(), get_proxied_url), {ATHENA: REC})
r = s.get('https://%s/api/trades?date=20261028' % ATHENA, timeout=5)
p = PEDIDOS[-1]
ok(r.status_code == 200 and p['host_url'] == PROXY and p['alvo'] == ATHENA and p['aut'] == 'Bearer tok-1',
   'sai pelo proxy com o Authorization e o target-server da Athena (%r)' % p)

print('\n== 6. o athena_api de verdade ==')
from apps.pages import athena_api                                 # noqa: E402
reinicia()
dado = athena_api.get_json_url(IT.autentica(crua(), {ATHENA: REC}), 'https://%s/api/trades' % ATHENA)
ok(dado == {'trades': [1, 2]}, 'get_json_url chega ao JSON com o token (%r)' % dado)

print('\n== 7. instala e diagnóstico ==')
cru = athena_api.build_session
try:
    del os.environ['OTC_STRATOS_IDA_RECURSOS']
    ok(IT.instala() is False and athena_api.build_session is cru, 'sem recurso: não troca')
    os.environ['OTC_STRATOS_IDA_RECURSOS'] = '%s=%s' % (ATHENA, REC)
    sys.modules['stratosblocks.utilities'] = types.SimpleNamespace(get_proxied_url=get_proxied_url)
    PI.instala()
    com_proxy = athena_api.build_session
    ok(IT.instala() is True and athena_api.build_session is not com_proxy, 'com recurso: troca')
    trocado = athena_api.build_session
    ok(IT.instala() is True and athena_api.build_session is trocado, 'de novo: não embrulha duas vezes')
    ok(getattr(trocado, '_otc_stratos_proxy', False), 'e o sinal do proxy continua visível')
    s2 = athena_api.build_session()
    ok(getattr(s2, '_otc_stratos_ida', False) and getattr(s2, '_otc_stratos_proxy', False),
       'a sessão nova tem o token e o desvio')
    reinicia()
    d = IT.diagnostico()
    texto = json.dumps(d)
    ok(d['recursos'][0]['ok'] is True and 'tok-1' not in texto and d['recursos'][0]['tamanho'] == 5,
       'o diagnóstico diz que saiu, sem mostrar o token (%s)' % texto)

    def quebra(recurso, environment=None):
        raise RuntimeError('IDA 403: FID sem acesso ao recurso')
    sb_fid.get_stratos_fid_token = quebra
    d = IT.diagnostico()
    ok(d['recursos'][0]['ok'] is False and 'FID sem acesso' in d['recursos'][0]['erro'],
       'e o erro CRU do stratosblocks quando não sai')
finally:
    athena_api.build_session = cru
    sys.modules.pop('stratosblocks.utilities', None)
    sb_fid.get_stratos_fid_token = get_stratos_fid_token

print('\n%d falha(s)' % len(FALHAS))
sys.exit(1 if FALHAS else 0)
