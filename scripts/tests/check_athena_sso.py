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

print('FALHOU' if falhas else 'TUDO OK')
sys.exit(1 if falhas else 0)
