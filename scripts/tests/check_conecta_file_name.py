# -*- coding: utf-8 -*-
"""Os arquivos da pasta New do Batch Conecta levam a CONTA da visão no nome
(mesa, 20/10/2026, HANDOFF §646): `73760009.TCO_BANCO.txt`.

  Banco 73760009 · MGT 04880006 · Lawton 00041007 · Atacama 85398005

O que este teste prende:

  1. `_conecta_file_name` tira a conta PRÓPRIA da visão do cadastro
     `b3-accounts` — em qualquer vocabulário dos geradores (a LE, o balde
     `BANCO`, o par de pernas `MGT x CLI`) — e não de um de-para no código;
  2. visão sem conta própria cadastrada RECUSA dizendo qual;
  3. o Opt FXO, que juntava as linhas do Banco e do Lawton num FXO_Banco.txt,
     sai com UM arquivo por visão, cada um com a sua conta;
  4. a recusa vem ANTES do primeiro arquivo: nada é gravado pela metade;
  5. todo código que usa a `CONECTA_NEW_PATH` passa pelo nome com a conta —
     gerador novo que grave na New com o nome cru cai aqui.

Os geradores que já tinham teste (Swap Bullet/Cashflow, Swap VCP, MtM, as
recompras) conferem o nome novo nos testes deles. Não encosta em dado real:
a New num tempfile.
"""
import os, shutil, sys, tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', os.path.join(ROOT, '.check-share'))
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

from apps.pages import routes as R                                   # noqa: E402
from apps import create_app                                          # noqa: E402
from apps.config import DebugConfig                                  # noqa: E402

app = create_app(DebugConfig)
app.config['TESTING'] = True

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def cliente():
    c = app.test_client()
    with c.session_transaction() as s:
        s['authenticated'] = True
        s['user_sid'] = 'A111111'
        s['user_name'] = 'Alice Souza'
        s['user_role'] = 'BO'
        s['session_ip'] = '127.0.0.1'
        s['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()
    return c


CONTAS = [
    {'LE': 'JPM', 'ACCOUNT': '73760.00-9', 'ACCOUNT TYPE': 'OWN', 'SIMPLIFIED NAME': 'JPMORGANBM'},
    {'LE': 'JPM', 'ACCOUNT': '73760.10-2', 'ACCOUNT TYPE': 'CLIENT 1', 'SIMPLIFIED NAME': 'JPMORGANBM'},
    {'LE': 'MGT', 'ACCOUNT': '04880.10-9', 'ACCOUNT TYPE': 'CLIENT 1', 'SIMPLIFIED NAME': 'MORGANBC'},
    {'LE': 'MGT', 'ACCOUNT': '04880.00-6', 'ACCOUNT TYPE': 'OWN', 'SIMPLIFIED NAME': 'MORGANBC'},
    {'LE': 'LAWTON', 'ACCOUNT': '00041.00-7', 'ACCOUNT TYPE': 'OWN', 'SIMPLIFIED NAME': 'INTRAGLAWTONFDO'},
    {'LE': 'ATACAMA', 'ACCOUNT': '85398.00-5', 'ACCOUNT TYPE': 'OWN', 'SIMPLIFIED NAME': 'INTRAGATACAMAFDO'},
]
orig_rows = R._mapping_rows


def _rows(contas):
    def _f(key, *a, **kw):
        return [dict(c) for c in contas] if key == 'b3-accounts' else orig_rows(key, *a, **kw)
    return _f


print('== 1. a conta da visão sai do b3-accounts ==')
R._mapping_rows = _rows(CONTAS)
try:
    check('as quatro entidades, pela conta PRÓPRIA (não a guarda-chuva)',
          [R._conecta_file_name(v, 'X.txt') for v in ('JPM', 'MGT', 'LAWTON', 'ATACAMA')],
          ['73760009.X.txt', '04880006.X.txt', '00041007.X.txt', '85398005.X.txt'])
    check('o balde da CETIP (BANCO) e o par de pernas (a perna da esquerda)',
          [R._conecta_file_name(v, 'T.txt') for v in ('BANCO', 'MGT x CLI', 'lawton × jpm', 'JPM x ATACAMA')],
          ['73760009.T.txt', '04880006.T.txt', '00041007.T.txt', '73760009.T.txt'])
    R._mapping_rows = _rows([dict(c, ACCOUNT='99999.00-1') if c['LE'] == 'MGT' and c['ACCOUNT TYPE'] == 'OWN'
                             else c for c in CONTAS])
    check('a conta editada no cadastro vale (não há número no código)',
          R._conecta_file_name('MGT', 'T.txt'), '99999001.T.txt')

    print('\n== 2. sem conta própria, recusa dizendo qual ==')
    R._mapping_rows = _rows([c for c in CONTAS if c['LE'] != 'LAWTON'])
    try:
        R._conecta_file_name('LAWTON', 'T.txt')
        check('recusa', False, True)
    except ValueError as exc:
        check('recusa nomeando a LE e o cadastro',
              ("'LAWTON'" in str(exc), 'B3 Accounts' in str(exc)), (True, True))
finally:
    R._mapping_rows = orig_rows

print('\n== 3. Opt FXO: um arquivo por visão ==')
tmp = tempfile.mkdtemp(prefix='check-conecta-')
orig = (R.CONECTA_NEW_PATH, R._create_notification)
R.CONECTA_NEW_PATH = tmp
R._create_notification = lambda *a, **kw: None
DEALS = [{'Deal': 'D1', 'Client': 'CLIENTE QUALQUER SA', 'TradeDate': '2026-10-20'},
         {'Deal': 'D2', 'Client': 'BANCO J.P MORGAN S.A', 'TradeDate': '2026-10-20'}]
try:
    R._mapping_rows = _rows(CONTAS)
    c = cliente()
    r = c.post('/api/new-deals/opt-fxo/send-conecta', json={'deals': DEALS})
    d = r.get_json() or {}
    check('o envio responde 200', (r.status_code, d.get('ok')), (200, True))
    check('as linhas do Banco e as do Lawton em arquivos separados, cada um com a sua conta',
          sorted(os.listdir(tmp)), ['00041007.FXO_Lawton.txt', '73760009.FXO_Banco.txt'])
    check('a resposta diz os nomes da New', sorted(d.get('files') or []),
          ['00041007.FXO_Lawton.txt', '73760009.FXO_Banco.txt'])
    linhas = {n: open(os.path.join(tmp, n), encoding='utf-8').read().split('\n') for n in os.listdir(tmp)}
    check('cada arquivo: header + a linha da sua visão',
          {n: len(v) for n, v in linhas.items()},
          {'00041007.FXO_Lawton.txt': 2, '73760009.FXO_Banco.txt': 2})
    t = linhas['00041007.FXO_Lawton.txt'][1].split(';')
    check('a linha do Lawton tem o Lawton como parte (campo 4) e o Banco como contraparte (7)',
          (t[3], t[6]), ('00041007', '73760009'))
    r = c.post('/api/new-deals/opt-fxo/send-conecta', json={'deals': DEALS, 'download': True})
    check('o download (preview) segue com o nome do documento, sem a conta',
          sorted(f['filename'] for f in (r.get_json() or {}).get('files', [])),
          ['FXO_Banco.txt', 'FXO_Lawton.txt'])

    print('\n== 4. a recusa vem antes do primeiro arquivo ==')
    shutil.rmtree(tmp)
    os.makedirs(tmp)
    R._mapping_rows = _rows([c for c in CONTAS if c['LE'] != 'LAWTON'])
    r = c.post('/api/new-deals/opt-fxo/send-conecta', json={'deals': DEALS})
    d = r.get_json() or {}
    check('o lote é recusado dizendo o Lawton', (r.status_code, "'LAWTON'" in str(d.get('error'))),
          (500, True))
    check('e nem o arquivo do Banco foi gravado', os.listdir(tmp), [])
finally:
    R._mapping_rows = orig_rows
    R.CONECTA_NEW_PATH, R._create_notification = orig
    shutil.rmtree(tmp, ignore_errors=True)

print('\n== 5. todo gerador da New passa pelo nome com a conta ==')
import ast                                                           # noqa: E402
PAGES = os.path.join(ROOT, 'apps', 'pages')
NOMEADORES = {'_conecta_file_name', '_mtm_new_name'}
usa, crus = [], []
for raiz, _d, arqs in os.walk(PAGES):
    for nome in arqs:
        if not nome.endswith('.py') or ' ' in nome:      # `routes 2.py`: cópia do macOS
            continue
        caminho = os.path.join(raiz, nome)
        arvore = ast.parse(open(caminho, encoding='utf-8').read())
        lidos = [n for n in ast.walk(arvore)
                 # `Config.CONECTA_NEW_PATH` é a DEFINIÇÃO (routes.py), não uso.
                 if (isinstance(n, ast.Attribute) and n.attr == 'CONECTA_NEW_PATH'
                     and isinstance(n.ctx, ast.Load)
                     and getattr(n.value, 'id', None) != 'Config')
                 or (isinstance(n, ast.Name) and n.id == 'CONECTA_NEW_PATH'
                     and isinstance(n.ctx, ast.Load))]
        if not lidos:
            continue
        rel = os.path.relpath(caminho, ROOT)
        usa.append(rel)
        chamados = {getattr(n.func, 'attr', getattr(n.func, 'id', None))
                    for n in ast.walk(arvore) if isinstance(n, ast.Call)}
        if not chamados & NOMEADORES:
            crus.append(rel)
check('os geradores da New foram achados (9 em 20/10/2026)', len(usa) >= 9, True)
check('nenhum grava na New sem a conta no nome', crus, [])

print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
