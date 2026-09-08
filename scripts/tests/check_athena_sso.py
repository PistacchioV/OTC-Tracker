# -*- coding: utf-8 -*-
"""O SSO Kerberos da Athena falha DIZENDO o que falta, e o pip o instala sozinho.

O `athena_api` importa o `HttpNegotiateAuth` do `requests-negotiate-sspi` dentro
de um try/except e segue com `None` quando ele nao esta la. Isso e certo fora do
Windows — o pacote e de SSPI e nem existe no macOS/Linux. No WINDOWS e o
contrario: sem o handler, a sessao vai para a Athena SEM autenticacao e o ADFS
responde `401 Unauthorized` no `/adfs/oauth2/authorize/wia`, o endpoint de
Windows Integrated Authentication.

Esse 401 chega a tela como uma URL de duas mil letras que nao menciona pacote
nenhum. Nenhuma chamada a Athena pode dar certo enquanto o pacote faltar, entao
seguir em frente troca uma mensagem que RESOLVE por outra que so descreve o
sintoma.

Duas coisas se prendem aqui:

  1. o `requirements.txt` traz a dependencia com MARCADOR de plataforma
     (`sys_platform == "win32"`), do mesmo jeito que o pywin32 logo acima. Ela
     ficou comentada por um tempo, com um "instale na instancia do JPM" ao lado
     — e o passo manual e exatamente o que se esquece num venv novo;
  2. o `build_session` levanta no Windows quando o pacote falta, com uma
     mensagem que cita o pacote, o endpoint e o comando; e NAO levanta fora
     dele, onde a Athena ja e inalcancavel de qualquer modo.
"""
import io
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

falhas = []


def check(rotulo, ok):
    print(('  ok  ' if ok else '  FAIL ') + rotulo)
    if not ok:
        falhas.append(rotulo)


# ── 1. a dependencia esta declarada, e com o marcador ──────────────────────
req = io.open(os.path.join(ROOT, 'requirements.txt'), encoding='utf-8').read()
linhas = [l.strip() for l in req.splitlines()
          if l.strip() and not l.strip().startswith('#')]
sspi = [l for l in linhas if l.lower().startswith('requests-negotiate-sspi')]
check('requests-negotiate-sspi esta declarado (nao comentado)', len(sspi) == 1)
if sspi:
    check('e com o marcador de plataforma do Windows',
          'sys_platform' in sspi[0] and 'win32' in sspi[0])
    try:
        from packaging.requirements import Requirement
        r = Requirement(sspi[0])
        check('o marcador diz SIM no Windows',
              r.marker.evaluate({'sys_platform': 'win32'}) is True)
        check('e NAO no macOS/Linux (o pacote nem existe la)',
              r.marker.evaluate({'sys_platform': 'darwin'}) is False)
    except ImportError:
        print('  --  packaging ausente: avaliacao do marcador pulada')

# ── 2. o build_session fala quando o pacote falta ──────────────────────────
from apps.pages import athena_api as A                     # noqa: E402

_real_auth = A.HttpNegotiateAuth
_real_name = os.name
A.HttpNegotiateAuth = None
try:
    os.name = 'posix'
    subiu = False
    try:
        sessao = A.build_session()
    except RuntimeError:
        subiu = True
    check('fora do Windows NAO levanta (a Athena ja e inalcancavel la)', not subiu)
    check('e a sessao sai sem auth, como antes', sessao.auth is None)

    os.name = 'nt'
    msg = ''
    try:
        A.build_session()
    except RuntimeError as exc:
        msg = str(exc)
    check('no Windows sem o pacote LEVANTA', bool(msg))
    check('a mensagem cita o pacote', 'requests-negotiate-sspi' in msg)
    check('cita o endpoint do 401', '/adfs/oauth2/authorize/wia' in msg)
    check('e diz o comando', 'pip install' in msg)

    # com o pacote presente nada muda — o caminho feliz continua o de sempre
    class _Fake(object):
        def __call__(self, *a, **k):
            return self

    A.HttpNegotiateAuth = _Fake()
    check('com o pacote presente, segue normal', A.build_session().auth is not None)
finally:
    os.name = _real_name
    A.HttpNegotiateAuth = _real_auth

# ── o TRANSPORTE: conexao curta, leitura pelo chamador ───────────────────────
# Kerberos resolvido, o que sobra e o tempo. Sao dois numeros e nao um: a espera
# de CONEXAO e paga quando o host nao responde (VPN fora, endereco errado no
# cadastro), e com um numero so ela custava o mesmo que uma consulta inteira —
# tres minutos para dizer que nao conectou, agora que o relatorio pede 180 s.
print()
print('== o timeout: conexao x leitura ==')
check('a conexao e curta', 0 < A.CONNECT_TIMEOUT <= 30)
check('o getTrades de UM produto le em 30 s', A.REQUEST_TIMEOUT == 30)
check('o RELATORIO le em muito mais', A.REPORT_TIMEOUT >= 120)
check('e o padrao do get_json_url e o do getTrades',
      A._timeout() == (A.CONNECT_TIMEOUT, A.REQUEST_TIMEOUT))
check('quem pede relatorio troca SO a leitura',
      A._timeout(A.REPORT_TIMEOUT) == (A.CONNECT_TIMEOUT, A.REPORT_TIMEOUT))

# O timeout tem de alcancar o POST do replay do ADFS, e nao so o GET: o form_post
# e o hop que dispara a consulta de verdade e volta com os dados, entao e NELE
# que a espera longa e gasta. Foi ali que o `getTradesBySettle` estourou.
_hops = []


class _Resp(object):
    def __init__(self, html):
        self.headers = {'Content-Type': 'text/html' if html else 'application/json'}
        self.text = '<form method="post" action="https://adfs/x"><input name="a" value="1"></form>'

    def raise_for_status(self):
        pass

    def json(self):
        return {'ok': True}


class _Sess(object):
    def get(self, url, params=None, timeout=None):
        _hops.append(('GET', timeout))
        return _Resp(True)

    def post(self, url, data=None, timeout=None):
        _hops.append(('POST', timeout))
        return _Resp(False)


A.get_json_url(_Sess(), 'https://athena/x', timeout=A.REPORT_TIMEOUT)
check('o GET e o POST do replay recebem o MESMO timeout',
      _hops == [('GET', (A.CONNECT_TIMEOUT, A.REPORT_TIMEOUT)),
                ('POST', (A.CONNECT_TIMEOUT, A.REPORT_TIMEOUT))])
del _hops[:]
A.get_json_url(_Sess(), 'https://athena/x')
check('e sem pedido nenhum fica no de getTrades (New Deals intacto)',
      _hops == [('GET', (A.CONNECT_TIMEOUT, A.REQUEST_TIMEOUT)),
                ('POST', (A.CONNECT_TIMEOUT, A.REQUEST_TIMEOUT))])

# `.env` digitado errado nao pode derrubar a subida: este modulo e importado no
# topo do routes, e um ajuste de tempo malformado viraria uma aplicacao que nao
# abre. Cai no padrao e avisa no log (a mesma decisao do IMPORT_POLL_WINDOW).
os.environ['ATHENA_X_TEST'] = 'abc'
check('valor malformado cai no padrao', A._seconds('ATHENA_X_TEST', 42) == 42)
os.environ['ATHENA_X_TEST'] = '0'
check('zero tambem (esperar zero e nao esperar)', A._seconds('ATHENA_X_TEST', 42) == 42)
os.environ['ATHENA_X_TEST'] = '240'
check('e o numero valido vale', A._seconds('ATHENA_X_TEST', 42) == 240)
os.environ.pop('ATHENA_X_TEST', None)
check('ausente devolve o padrao', A._seconds('ATHENA_X_TEST', 42) == 42)

print('FALHOU' if falhas else 'TUDO OK')
sys.exit(1 if falhas else 0)
