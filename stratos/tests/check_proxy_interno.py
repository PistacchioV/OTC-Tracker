"""Confere o desvio dos sistemas internos pelo proxy do Stratos
(stratos/src/proxy_interno.py).

O `get_proxied_url` é de mentira e faz o que a documentação diz: devolve a URL
do proxy, os cabeçalhos com o `target-server` e o `proxies`. A rede também é de
mentira (um adaptador do `requests` montado na sessão): o "proxy" responde pelo
`target-server`, e a Athena manda o pedido para o ADFS antes do JSON.

  1. host da internet (BCB) vai direto, sem `target-server` e sem o proxy;
  2. host interno vai pelo proxy, e os redirecionamentos (absoluto e
     RELATIVO) também, com o cookie do ADFS no salto seguinte; o `resp.url` é
     o endereço interno;
  3. o POST do form_post mantém o `Content-Type` urlencoded;
  4. o `athena_api.get_json_url` de verdade chega ao JSON pela sessão desviada;
  5. `instala`: troca o `athena_api.build_session` (uma vez só); com
     `OTC_STRATOS_PROXY_INTERNO=0` ou sem o `get_proxied_url`, não troca.

    python stratos/tests/check_proxy_interno.py
"""
import email.message
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

import requests                                                   # noqa: E402
from requests.adapters import BaseAdapter                         # noqa: E402
from requests.structures import CaseInsensitiveDict               # noqa: E402

import proxy_interno as PI                                        # noqa: E402

FALHAS = []
PROXY = 'proxy.stratos.teste'
PROXIES = {'https': 'http://saida.stratos.teste:3128'}
PEDIDOS = []


def ok(cond, msg):
    print(('ok    ' if cond else 'FAIL  ') + msg)
    if not cond:
        FALHAS.append(msg)


def get_proxied_url(internal_url, headers=None, files=False):
    p = urlsplit(internal_url)
    cab = dict(headers or {})
    cab['target-server'] = p.hostname
    if not files:
        cab['Content-Type'] = 'application/json'
    return ('https://%s%s%s' % (PROXY, p.path, ('?' + p.query) if p.query else ''), cab, dict(PROXIES))


class _Raw(object):
    def __init__(self, set_cookie=None):
        msg = email.message.Message()
        if set_cookie:
            msg['Set-Cookie'] = set_cookie
        self._original_response = types.SimpleNamespace(msg=msg)

    def close(self):
        pass


class Rede(BaseAdapter):
    """O proxy responde pelo `target-server`; o resto, pelo host da URL."""

    def send(self, request, **kw):
        p = urlsplit(request.url)
        host = request.headers.get('target-server') if p.hostname == PROXY else p.hostname
        PEDIDOS.append({'host_url': p.hostname, 'alvo': host, 'caminho': p.path,
                        'metodo': request.method, 'proxies': kw.get('proxies'),
                        'cabecalhos': dict(request.headers), 'corpo': request.body})
        status, cab, corpo, cookie = 200, {'Content-Type': 'application/json'}, b'{}', None
        if host == 'athena-app.jpmchase.net' and p.path == '/api/trades':
            status, cab, corpo = 302, {'Location': 'https://idp.jpmchase.net/adfs/auth?c=1'}, b''
        elif host == 'idp.jpmchase.net' and p.path == '/adfs/auth':
            status, cab, corpo, cookie = 302, {'Location': '/adfs/fim'}, b'', 'MSIS=abc; Path=/'
        elif host == 'idp.jpmchase.net' and p.path == '/adfs/fim':
            corpo = json.dumps({'cookie': request.headers.get('Cookie', '')}).encode()
        elif host == 'athena-app.jpmchase.net' and p.path == '/adfs/post':
            corpo = json.dumps({'tipo': request.headers.get('Content-Type', '')}).encode()
        elif host == 'api.bcb.gov.br':
            corpo = b'{"bcb": true}'
        r = requests.Response()
        r.status_code = status
        r.headers = CaseInsensitiveDict(cab)
        r._content = corpo
        r._content_consumed = True
        r.url = request.url
        r.request = request
        r.raw = _Raw(cookie)
        r.encoding = 'utf-8'
        return r

    def close(self):
        pass


def sessao():
    s = requests.Session()
    s.trust_env = False
    s.mount('https://', Rede())
    s.mount('http://', Rede())
    return PI.proxia(s, get_proxied_url)


print('== 0. quem é interno ==')
ok(PI.interno('https://athena-app.jpmchase.net/x') and PI.interno('http://athena-reports.jpmchase.net')
   and PI.interno('https://idauatg2.jpmorganchase.com/adfs'), 'os hosts do JPM são internos')
ok(not PI.interno('https://api.bcb.gov.br/x') and not PI.interno('https://query1.finance.yahoo.com')
   and not PI.interno('https://evil-jpmchase.net/'), 'BCB, Yahoo e domínio parecido não são')
os.environ['OTC_STRATOS_INTERNOS'] = 'exemplo.interno'
ok(PI.interno('https://a.exemplo.interno/') and not PI.interno('https://athena-app.jpmchase.net/'),
   'OTC_STRATOS_INTERNOS troca a lista')
del os.environ['OTC_STRATOS_INTERNOS']

print('\n== 1. host da internet vai direto ==')
s = sessao()
PEDIDOS.clear()
r = s.get('https://api.bcb.gov.br/dados', timeout=5)
p = PEDIDOS[-1]
ok(r.json() == {'bcb': True} and p['host_url'] == 'api.bcb.gov.br'
   and 'target-server' not in p['cabecalhos'] and p['proxies'] != PROXIES,
   'BCB sem o proxy interno (%r)' % p['proxies'])

print('\n== 2. interno pelo proxy, com os redirecionamentos ==')
PEDIDOS.clear()
r = s.get('https://athena-app.jpmchase.net/api/trades?date=20261027', timeout=5)
ok([q['host_url'] for q in PEDIDOS] == [PROXY] * 3, 'os três saltos pelo proxy (%r)'
   % [q['host_url'] for q in PEDIDOS])
ok([q['alvo'] for q in PEDIDOS] == ['athena-app.jpmchase.net', 'idp.jpmchase.net', 'idp.jpmchase.net'],
   'cada salto com o target-server do SEU host (o relativo inclusive)')
ok(all(q['proxies'] == PROXIES for q in PEDIDOS), 'com o proxies do get_proxied_url')
ok(r.json() == {'cookie': 'MSIS=abc'}, 'o cookie do ADFS vai no salto seguinte (%r)' % r.text)
ok(r.url == 'https://idp.jpmchase.net/adfs/fim' and len(r.history) == 2,
   'resp.url é o endereço interno e o histórico tem os dois saltos (%r)' % r.url)
PEDIDOS.clear()
r = s.get('https://athena-app.jpmchase.net/api/trades', allow_redirects=False, timeout=5)
ok(r.status_code == 302 and len(PEDIDOS) == 1, 'allow_redirects=False não segue')

print('\n== 3. o form_post mantém o Content-Type ==')
r = s.post('https://athena-app.jpmchase.net/adfs/post', data={'code': 'x'}, timeout=5)
ok(r.json() == {'tipo': 'application/x-www-form-urlencoded'}, 'urlencoded (%r)' % r.text)
ok(PEDIDOS[-1]['corpo'] == 'code=x', 'e o corpo intacto')

print('\n== 4. o athena_api de verdade ==')
from apps.pages import athena_api                                 # noqa: E402
PEDIDOS.clear()
dado = athena_api.get_json_url(sessao(), 'https://athena-app.jpmchase.net/api/trades')
ok(dado == {'cookie': 'MSIS=abc'}, 'get_json_url chega ao JSON pela sessão desviada (%r)' % dado)

print('\n== 5. instala ==')
cru = athena_api.build_session
utilidades = types.ModuleType('stratosblocks.utilities')
utilidades.get_proxied_url = get_proxied_url
sys.modules.setdefault('stratosblocks', types.ModuleType('stratosblocks'))
try:
    os.environ['OTC_STRATOS_PROXY_INTERNO'] = '0'
    sys.modules['stratosblocks.utilities'] = utilidades
    ok(PI.instala() is False and athena_api.build_session is cru, 'OTC_STRATOS_PROXY_INTERNO=0 não troca')
    del os.environ['OTC_STRATOS_PROXY_INTERNO']
    sys.modules['stratosblocks.utilities'] = types.ModuleType('stratosblocks.utilities')
    ok(PI.instala() is False and athena_api.build_session is cru, 'sem o get_proxied_url não troca')
    sys.modules['stratosblocks.utilities'] = utilidades
    ok(PI.instala() is True and athena_api.build_session is not cru, 'com ele, troca o build_session')
    trocado = athena_api.build_session
    ok(PI.instala() is True and athena_api.build_session is trocado, 'instalar de novo não embrulha duas vezes')
    s2 = athena_api.build_session()
    ok(getattr(s2, '_otc_stratos_proxy', False) and s2.trust_env is False,
       'a sessão nova tem o desvio e segue com o trust_env desligado')
finally:
    athena_api.build_session = cru
    sys.modules.pop('stratosblocks.utilities', None)

print('\n%d falha(s)' % len(FALHAS))
sys.exit(1 if FALHAS else 0)
