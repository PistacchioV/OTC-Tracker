"""Confere o `stratos/exporta_dados.py` — o pacote dos dados para o Stratos.

Num share de mentira (tmp), com bancos do ARMAZÉM gravados pelo funil do app,
um DuckDB com dado SÓ no WAL, o SQLite dos comitentes, sobras e o JSON legado:

  1. o pacote leva os bancos SEM WAL, e o dado que só estava no WAL está lá;
  2. lido de volta pelo armazém (processo novo, sem memo), cada payload é o
     que foi gravado — inclusive depois do emagrecimento;
  3. sobras, `.lock`, `_recuperado/`, `translations/` e o JSON legado ficam
     fora (o JSON entra com `--com-json-legado`); o anexo entra;
  4. o manifest bate com os arquivos (bytes e sha256) e o share fica intacto;
  5. banco preso por outra instância sai EM USO e o pacote INCOMPLETO (o CLI
     devolve 1); o `--zip` sai íntegro.

    OTC_SHARED_DRIVE_ROOT=/tmp/otc-share python stratos/tests/check_exporta_dados.py
"""
import hashlib
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import zipfile

AQUI = os.path.dirname(os.path.abspath(__file__))
STRATOS = os.path.dirname(AQUI)
RAIZ = os.path.dirname(STRATOS)
sys.path.insert(0, RAIZ)
sys.path.insert(0, STRATOS)
os.chdir(RAIZ)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', tempfile.mkdtemp(prefix='share-root-'))
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

import duckdb                                               # noqa: E402
from apps.pages import routes as R                         # noqa: E402
import exporta_dados as X                                   # noqa: E402

FALHAS = []


def ok(cond, msg):
    print(('ok    ' if cond else 'FAIL  ') + msg)
    if not cond:
        FALHAS.append(msg)


def sha(caminho):
    return hashlib.sha256(io.open(caminho, 'rb').read()).hexdigest()


def foto(raiz):
    """{rel: sha256} de tudo que não é `.lock` (o `.lock` a camada pode criar)."""
    out = {}
    for pasta, _d, nomes in os.walk(raiz):
        for n in nomes:
            if not n.endswith('.lock'):
                c = os.path.join(pasta, n)
                out[os.path.relpath(c, raiz)] = sha(c)
    return out


TMP = tempfile.mkdtemp(prefix='otc-exporta-')
ORIGEM = os.path.join(TMP, 'share', 'static', 'data')
DESTINO = os.path.join(TMP, 'local')
DB = os.path.join(ORIGEM, 'db')
os.makedirs(DB)

PAYLOADS = {
    'cache/new deals/NDF/Commodities/2026/06/20260615_ndfcomm.json':
        [{'Deal': 'D1', 'TradeDate': '15/06/2026', 'Notional': 1000.5},
         {'Deal': 'D2', 'TradeDate': '15/06/2026', 'Notional': 2, 'Extra': {'a': [1, 2]}}],
    'mappings/bank-name.json': [{'BANK': 'ITAU', 'ALIAS': 'Itaú Unibanco'}],
    'RefData.json': [{'COUNTERPARTY': 'ACME', 'SPN': '123', 'TAX ID': '00.000.000/0001-91'}],
    'control-panel/daily_metric_recipients.json': {'to': ['a@x'], 'cc': []},
}
R._B3_DATA_DIR = ORIGEM
for rel, payload in PAYLOADS.items():
    R._atomic_write_json(os.path.join(ORIGEM, *rel.split('/')), payload)

# Um DuckDB com dado SÓ no WAL: o checkpoint do fechamento desligado.
COM_WAL = os.path.join(DB, 'Users_OTCTracker.db')
con = duckdb.connect(COM_WAL)
con.execute('CREATE TABLE users (sid VARCHAR, role VARCHAR)')
con.execute("INSERT INTO users VALUES ('E930179', 'ADMIN')")
con.execute('CHECKPOINT')
con.execute('PRAGMA disable_checkpoint_on_shutdown')
con.execute("SET checkpoint_threshold = '1GB'")
con.execute("INSERT INTO users VALUES ('A000001', 'BO'), ('B000002', 'MO')")
con.close()

SQLITE = os.path.join(DB, 'matching_comitentes.db')
s = sqlite3.connect(SQLITE)
s.execute('CREATE TABLE comitentes (conta TEXT, nome TEXT)')
s.executemany('INSERT INTO comitentes VALUES (?, ?)', [('1', 'A'), ('2', 'B')])
s.commit()
s.close()

SOBRAS = ['db/Users_OTCTracker.db.wal.corrupt-20260726-114807', 'db/x.db.incompatible-bak',
          'db/_recuperado/20260101-000000/velho.db', 'db/_seed_stamp.txt', 'db/_test_subj/t.db',
          'db/a.db.slim', 'translations/en.json', 'tickets/Thumbs.db', 'tickets/~$planilha.xlsx']
for rel in SOBRAS:
    c = os.path.join(ORIGEM, *rel.split('/'))
    os.makedirs(os.path.dirname(c), exist_ok=True)
    io.open(c, 'wb').write(b'sobra')
ANEXO = 'tickets/OTC-0042/print.png'
LEGADO = 'cache/new deals/NDF/Commodities/2024/01/20240102_ndfcomm.json'
for rel, corpo in ((ANEXO, b'\x89PNG...'), (LEGADO, b'[{"Deal": "VELHO"}]')):
    c = os.path.join(ORIGEM, *rel.split('/'))
    os.makedirs(os.path.dirname(c), exist_ok=True)
    io.open(c, 'wb').write(corpo)

ok(os.path.isfile(COM_WAL + '.wal'), 'setup: o banco de usuários tem WAL ao lado')
ANTES = foto(ORIGEM)

print('== 1. o pacote, sem WAL ==')
pacote, man = X.exportar(ORIGEM, DESTINO, carimbo='teste')
data = os.path.join(pacote, 'data')
ok(man['completo'], 'manifest completo')
ok(not man['erros'], 'sem erros: %s' % man['erros'])
wal = [os.path.join(p, n) for p, _d, ns in os.walk(pacote) for n in ns if '.wal' in n]
ok(wal == [], 'nenhum WAL no pacote: %s' % wal)
c = duckdb.connect(os.path.join(data, 'db', 'Users_OTCTracker.db'), read_only=True)
ok(c.execute('SELECT count(*) FROM users').fetchone()[0] == 3, 'o que só estava no WAL entrou')
c.close()
s = sqlite3.connect(os.path.join(data, 'db', 'matching_comitentes.db'))
ok(s.execute('SELECT count(*) FROM comitentes').fetchone()[0] == 2, 'o SQLite foi pelo backup')
s.close()
tipos = {e['caminho']: e['tipo'] for e in man['arquivos']}
ok(tipos.get('data/db/matching_comitentes.db') == 'sqlite'
   and tipos.get('data/db/Users_OTCTracker.db') == 'duckdb', 'motor lido pelo cabeçalho')

print('== 2. lido de volta pelo armazém ==')
# Numa CÓPIA: a camada cria o `.lock` ao lado de cada banco que abre, e o
# pacote tem de seguir sendo exatamente o que o exportador produziu.
LEITURA = os.path.join(TMP, 'leitura')
shutil.copytree(data, LEITURA)
LEITOR = r'''
import json, os, sys
sys.path.insert(0, %r); os.chdir(%r)
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'
from apps.pages import routes as R
from apps.pages import data_store as S
R._B3_DATA_DIR = %r
out = {}
for rel in %r:
    out[rel] = S.read(os.path.join(R._B3_DATA_DIR, *rel.split('/')))
print('@@' + json.dumps(out))
''' % (RAIZ, RAIZ, LEITURA, list(PAYLOADS))
r = subprocess.run([sys.executable, '-c', LEITOR], capture_output=True, text=True)
lido = {}
for linha in r.stdout.splitlines():
    if linha.startswith('@@'):
        lido = json.loads(linha[2:])
if not lido:
    print(r.stdout[-2000:], r.stderr[-2000:])
for rel, payload in PAYLOADS.items():
    got = lido.get(rel)
    if isinstance(got, str):
        got = json.loads(got)
    ok(got == payload, 'volta igual: %s' % rel)
armazem = [e for e in man['arquivos'] if e['tipo'] == 'duckdb' and e['caminho'] != 'data/db/Users_OTCTracker.db']
ok(armazem and all(e.get('manifest', -1) >= 1 for e in armazem),
   'os bancos do armazém vão com o _manifest conferido')

print('== 3. o que fica de fora ==')
no_pacote = {e['caminho'][len('data/'):] for e in man['arquivos']}
for rel in SOBRAS:
    ok(rel not in no_pacote and not os.path.exists(os.path.join(data, *rel.split('/'))),
       'fora: %s' % rel)
ok(ANEXO in no_pacote, 'o anexo entra')
ok(LEGADO not in no_pacote, 'o JSON legado fica de fora sem o flag')
ok(any('json legado' in f['motivo'] for f in man['fora']), 'e o manifest diz quantos')
ok(not any(n.endswith('.lock') for _p, _d, ns in os.walk(pacote) for n in ns), 'nenhum .lock')

print('== 4. manifest e share ==')
for e in man['arquivos']:
    c = os.path.join(pacote, *e['caminho'].split('/'))
    ok(os.path.getsize(c) == e['bytes'] and sha(c) == e['sha256'], 'sha256: %s' % e['caminho'])
reais = {os.path.relpath(os.path.join(p, n), pacote).replace(os.sep, '/')
         for p, _d, ns in os.walk(pacote) for n in ns} - {'manifest.json'}
ok(reais == {e['caminho'] for e in man['arquivos']}, 'o pacote tem exatamente o que o manifest diz')
ok(foto(ORIGEM) == ANTES, 'o share ficou intacto (WAL inclusive)')
_p2, man2 = X.exportar(ORIGEM, DESTINO, com_json=True, carimbo='json')
ok('data/' + LEGADO in {e['caminho'] for e in man2['arquivos']}, '--com-json-legado leva o legado')

print('== 5. banco EM USO e o zip ==')
PRONTO = os.path.join(TMP, 'pronto')
SEGURA = r'''
import io, os, sys, time
sys.path.insert(0, %r); os.chdir(%r)
from apps.pages import database_access as DA
t = DA.hold_file_lock(%r, write=True, timeout_seconds=5)
io.open(%r, 'w').write('1')
time.sleep(60)
''' % (RAIZ, RAIZ, COM_WAL, PRONTO)
vizinho = subprocess.Popen([sys.executable, '-c', SEGURA])
try:
    for _ in range(200):
        if os.path.isfile(PRONTO):
            break
        time.sleep(0.1)
    ok(os.path.isfile(PRONTO), 'setup: o vizinho segura a trava exclusiva')
    r = subprocess.run([sys.executable, os.path.join(STRATOS, 'exporta_dados.py'), '--origem', ORIGEM,
                        '--destino', os.path.join(TMP, 'preso'), '--lock-seconds', '1'],
                       capture_output=True, text=True)
    ok(r.returncode == 1, 'o CLI devolve 1 com banco preso')
    ok('EM USO' in r.stdout and 'INCOMPLETO' in r.stdout, 'e diz EM USO / INCOMPLETO')
    mans = [os.path.join(p, n) for p, _d, ns in os.walk(os.path.join(TMP, 'preso')) for n in ns
            if n == 'manifest.json']
    m3 = json.load(io.open(mans[0], encoding='utf-8')) if mans else {}
    ok(m3.get('completo') is False
       and any(p['caminho'] == 'db/Users_OTCTracker.db' for p in m3.get('pulados', [])),
       'manifest INCOMPLETO, com o banco preso em pulados')
finally:
    vizinho.kill()
    vizinho.wait()

r = subprocess.run([sys.executable, os.path.join(STRATOS, 'exporta_dados.py'), '--origem', ORIGEM,
                    '--destino', os.path.join(TMP, 'zip'), '--zip'], capture_output=True, text=True)
ok(r.returncode == 0, 'o CLI com --zip devolve 0')
zips = [os.path.join(p, n) for p, _d, ns in os.walk(os.path.join(TMP, 'zip')) for n in ns
        if n.endswith('.zip')]
if zips:
    with zipfile.ZipFile(zips[0]) as z:
        ok(z.testzip() is None, 'zip íntegro')
        nomes = set(z.namelist())
        ok('manifest.json' in nomes and 'data/db/Users_OTCTracker.db' in nomes, 'zip com manifest e bancos')
else:
    ok(False, 'o --zip gerou o arquivo')

shutil.rmtree(TMP, ignore_errors=True)
print('\n%d falha(s)' % len(FALHAS))
sys.exit(1 if FALHAS else 0)
