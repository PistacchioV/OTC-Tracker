# -*- coding: utf-8 -*-
"""check_tools_rede.py — a saída das Tools pelo próprio Windows (HANDOFF §450).

Na instância o proxy responde 407 e a conexão direta expira: a fila do
`requests` morre inteira e a mesa vê `could not fetch BCB series 4389`. A
macro VBA passa pelo WinInet, que autentica no proxy com o usuário logado.
O `rede.obter` ganhou as duas saídas do Windows DEPOIS das do `requests`.

O que se prende (COM simulado — nada sai da máquina):

  1. fora do Windows a fila é a de sempre (nenhuma rota COM);
  2. no Windows, com as rotas do requests mortas, o WinHTTP responde e fica
     MEMORIZADO — a chamada seguinte vai nele primeiro, sem pagar o 407;
  3. um 407 pelo COM é rota ruim (tenta a próxima); um 404 é da fonte (para);
  4. o corpo volta como bytes do `ResponseBody`, e o texto quando não há;
  5. com tudo morto, `ErroRede` lista as tentativas, e o memo é limpo;
  6. o proxy do `SetProxy` é `host:porta`, sem esquema.
"""
import os
import sys
import types

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

falhas = []


def check(rotulo, obtido, esperado):
    ok = obtido == esperado
    print(('  ok  ' if ok else ' FAIL ') + rotulo +
          ('' if ok else '\n        got=%r\n        exp=%r' % (obtido, esperado)))
    if not ok:
        falhas.append(rotulo)


from apps.pages import quotes as _q                                   # noqa: E402
from apps.pages.precificador import rede                              # noqa: E402

# ── o COM de mentira ─────────────────────────────────────────────────────────
COM = {'winhttp': {'status': 200, 'body': b'{"ok":1}', 'raise': None},
       'wininet': {'status': 200, 'body': b'wininet', 'raise': None},
       'chamadas': [], 'proxy': None, 'headers': {}}


class _Req:
    def __init__(self, kind):
        self.kind = kind
        self.Status = COM[kind]['status']
        self.status = COM[kind]['status']
        self.StatusText = 'OK'
        self.statusText = 'OK'

    def SetProxy(self, modo, proxy, bypass=''):
        COM['proxy'] = (modo, proxy)

    def SetTimeouts(self, *a):
        COM['timeouts'] = a

    def Open(self, m, url, assinc):
        COM['chamadas'].append((self.kind, url))
        if COM[self.kind]['raise']:
            raise COM[self.kind]['raise']

    open = Open

    def SetAutoLogonPolicy(self, p):
        COM['autologon'] = p

    def SetRequestHeader(self, k, v):
        COM['headers'][k] = v

    setRequestHeader = SetRequestHeader

    def Send(self, *a):
        pass

    send = Send

    @property
    def ResponseBody(self):
        return COM[self.kind]['body']

    @property
    def ResponseText(self):
        b = COM[self.kind]['body']
        return b.decode('utf-8') if b is not None else ''


def _dispatch(nome):
    return _Req('winhttp' if nome.startswith('WinHttp') else 'wininet')


fake_client = types.ModuleType('win32com.client'); fake_client.Dispatch = _dispatch
fake_win32com = types.ModuleType('win32com'); fake_win32com.client = fake_client
fake_pythoncom = types.ModuleType('pythoncom')
fake_pythoncom.CoInitialize = lambda: None
fake_pythoncom.CoUninitialize = lambda: None
sys.modules['win32com'] = fake_win32com
sys.modules['win32com.client'] = fake_client
sys.modules['pythoncom'] = fake_pythoncom

# as rotas do requests, todas mortas como na instância
_rotas_orig = _q._routes
_sessao_orig = rede._sessao
_uma_orig = rede._uma
_q._routes = lambda: [('proxy http://proxy.jpmchase.net:9443', {'https': 'http://proxy.jpmchase.net:9443'}),
                      ('direct connection', {})]
rede._sessao = lambda proxies: types.SimpleNamespace(close=lambda: None)


def _uma_morta(sessao, metodo, url, cab, dados, timeout):
    raise _q._RouteError('proxy authentication required')


rede._uma = _uma_morta
_q._route_ok['name'] = None

# ─────────────────────────────────────────────────────────────────────────────
print('== 1. fora do Windows nada muda ==')
rede.sys = types.SimpleNamespace(platform='darwin')
check('sem rota COM fora do Windows', rede._rotas_com(), [])
try:
    rede.obter('https://x/api')
    check('tudo morto é ErroRede', False, True)
except rede.ErroRede as exc:
    check('tudo morto é ErroRede', 'proxy authentication required' in str(exc), True)
check('e nenhuma chamada COM', COM['chamadas'], [])

# ─────────────────────────────────────────────────────────────────────────────
print('== 2. no Windows o WinHTTP responde e fica memorizado ==')
rede.sys = types.SimpleNamespace(platform='win32')
check('duas rotas COM no Windows', [n for n, _f in rede._rotas_com()], [rede._COM_WINHTTP, rede._COM_WININET])
corpo = rede.obter('https://servicodados.ibge.gov.br/x', timeout=40)
check('o corpo vem do WinHTTP', corpo, b'{"ok":1}')
check('só o WinHTTP foi chamado', COM['chamadas'], [('winhttp', 'https://servicodados.ibge.gov.br/x')])
check('proxy host:porta sem esquema', COM['proxy'], (2, 'proxy.jpmchase.net:9443'))
check('auto-logon sempre', COM.get('autologon'), 0)
check('timeouts em ms (conexão curta, leitura o pedido)', COM.get('timeouts'), (6000, 6000, 40000, 40000))
check('UA e Accept vão no pedido', 'User-Agent' in COM['headers'] and COM['headers'].get('Accept'), '*/*')
check('a rota ficou memorizada', _q._route_ok['name'], rede._COM_WINHTTP)
check('e vai na frente na fila seguinte', rede._tentativas()[0][0], rede._COM_WINHTTP)
COM['chamadas'] = []
rede.obter('https://y')
check('a segunda chamada nem toca o requests', COM['chamadas'], [('winhttp', 'https://y')])

# ─────────────────────────────────────────────────────────────────────────────
print('== 3. 407 pelo COM é rota ruim; 404 é da fonte ==')
COM['chamadas'] = []
COM['winhttp']['status'] = 407
corpo = rede.obter('https://z')
check('o 407 do WinHTTP cai para o WinInet', (corpo, [k for k, _u in COM['chamadas']]),
      (b'wininet', ['winhttp', 'wininet']))
check('e o WinInet passa a ser a memorizada', _q._route_ok['name'], rede._COM_WININET)
COM['winhttp']['status'] = 200
COM['wininet']['status'] = 404
try:
    rede.obter('https://w')
    check('404 da fonte para na hora', False, True)
except rede.ErroRede as exc:
    check('404 da fonte para na hora', exc.status, 404)

# ─────────────────────────────────────────────────────────────────────────────
print('== 4. o corpo ==')
COM['wininet']['status'] = 200
COM['wininet']['body'] = memoryview(b'abc')
check('memoryview vira bytes', rede._corpo_com(_Req('wininet')), b'abc')
COM['wininet']['body'] = None
check('sem ResponseBody vai o texto', rede._corpo_com(_Req('wininet')), b'')
COM['wininet']['body'] = b'wininet'

# ─────────────────────────────────────────────────────────────────────────────
print('== 5. tudo morto ==')
_q._route_ok['name'] = rede._COM_WINHTTP
COM['winhttp']['raise'] = RuntimeError('COM error: WinHttp timeout')
COM['wininet']['raise'] = RuntimeError('COM error: WinInet down')
try:
    rede.obter('https://dead')
    check('tudo morto é ErroRede', False, True)
except rede.ErroRede as exc:
    s = str(exc)
    check('a mensagem lista as quatro tentativas',
          all(t in s for t in ('proxy authentication required', 'winhttp', 'wininet', 'direct connection')), True)
check('e o memo é limpo', _q._route_ok['name'], None)

# ─────────────────────────────────────────────────────────────────────────────
print('== 6. o proxy do WinHTTP ==')
_qp = _q.QUOTES_PROXY
_q.QUOTES_PROXY = 'http://proxy.jpmchase.net:9443/'
check('cadastrado: host:porta', rede._proxy_winhttp(), 'proxy.jpmchase.net:9443')
_q.QUOTES_PROXY = ''
check('sem cadastro e sem sistema: vazio (config do WinHTTP)', rede._proxy_winhttp() in ('',) or ':' in rede._proxy_winhttp(), True)
_q.QUOTES_PROXY = _qp

_q._routes = _rotas_orig
rede._sessao = _sessao_orig
rede._uma = _uma_orig
rede.sys = sys
print()
print('FALHAS: %d' % len(falhas) if falhas else 'tudo ok')
sys.exit(1 if falhas else 0)
