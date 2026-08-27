# -*- coding: utf-8 -*-
"""O card Pending Confirmations Spreadsheet Metrics ponta a ponta.

O layout da planilha e CONTRATO com o time global (OLEDB, Confirmation_Latam):
aba CONFIRMATIONS, cabecalho na linha 1, as 31 colunas na ordem pedida —
inclusive as VAZIAS, que mantem a posicao das demais. O que ele prende:

  1. **as linhas sao as do chip Pending recomputado** (`_pc_target_category`),
     dedupe por Trade Number atraves dos tres DBs;
  2. **data vira DATA de verdade** (DD/MM/YYYY) e Aging vira numero — texto
     deixaria o Excel do consumidor sem ordenar;
  3. **data anterior le o SNAPSHOT sem recategorizar** (a foto ja e o balde
     daquele dia) e grava no MESMO nome canonico, com a `ref` marcada no
     status; snapshot ausente e 404 dizendo o caminho procurado; futuro e 400;
  4. a gravacao e tmp + os.replace — nunca um xlsx pela metade no share.
"""
import io, json, os, sys, tempfile
from datetime import date, datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

TMP = tempfile.mkdtemp()

from apps.pages import routes as R                          # noqa: E402
from apps import create_app                                 # noqa: E402
from apps.config import DebugConfig                         # noqa: E402

app = create_app(DebugConfig)
app.config['TESTING'] = True

# O card mora em features/pcx; claim e status pendem da pasta de plataforma
# (routes._DAILY_METRIC_DIR) por busca atrasada.
from apps.pages.features.pcx import commands as PC2, queries as PQ           # noqa: E402
from apps.pages.features.pcx.infra import persistence as PP                  # noqa: E402
B = PP
B.DIR = os.path.join(TMP, 'share')
PCX_rows = PQ.rows
PCX_xlsx = PP.build_xlsx
PCX_disparar = PC2.fire_slot
R._PC_SNAPSHOT_DIR = os.path.join(TMP, 'snap')
R._DAILY_METRIC_DIR = TMP

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def cliente(auth=True):
    c = app.test_client()
    if auth:
        with c.session_transaction() as s:
            s['authenticated'] = True
            s['user_sid'] = 'A111111'
            s['user_name'] = 'Alice Souza'
            s['user_role'] = 'BO'
            s['user_email'] = 'alice.souza@jpmorgan.com'
            s['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()
    return c


c, anon = cliente(), cliente(auth=False)

LINHAS = {
    'backlog': [{'Trade Number': 'T-1', 'Client': 'ACME', 'Aging': '45', 'LOB': 'CEM',
                 'Trade Date': '01/07/2026', 'Status': 'Pending'}],
    'pending': [{'Trade Number': 'T-2', 'Client': 'BETA', 'Aging': '10', 'LOB': 'EDG',
                 'Trade Date': '10/08/2026', 'Status': 'Pending'},
                {'Trade Number': 'T-1', 'Client': 'ACME', 'Aging': '45', 'LOB': 'CEM',
                 'Trade Date': '01/07/2026', 'Status': 'Pending'},     # duplicada: dedupe
                {'Trade Number': 'T-3', 'Client': 'JA-OK', 'Status': 'Ok'}],
    'ok': [],
}
R._pc_load_rows = lambda cat: [dict(r) for r in LINHAS.get(cat, [])]
R._pc_target_category = lambda r: 'ok' if r.get('Status') == 'Ok' else 'pending'
NOTIFS = []
R._create_notification = lambda sid, nome, acao, pagina, msg='': NOTIFS.append((acao, pagina))

print('== 1. sem sessao ==')
check('run -> 401', anon.post('/api/control-panel/pending-spreadsheet/run').status_code, 401)
check('status -> 401', anon.get('/api/control-panel/pending-spreadsheet/status').status_code, 401)

print('\n== 2. as linhas: pending recomputado, dedupe por Trade Number ==')
rows = PCX_rows()
check('T-1 uma vez, T-2, e a Ok fica fora',
      sorted(r['Trade Number'] for r in rows), ['T-1', 'T-2'])

print('\n== 3. o layout da planilha e contrato ==')
ws = PCX_xlsx(rows).active
check('a aba e CONFIRMATIONS', ws.title, 'CONFIRMATIONS')
hdr = [c2.value for c2 in ws[1]]
check('31 colunas, comecando por LOB..Client..Aging', (len(hdr), hdr[:3]),
      (31, ['LOB', 'Client', 'Aging']))
check('   as vazias mantem a posicao (Vias na 17a)', hdr[16], 'Vias')
por = {tuple(c2.value for c2 in ws[1]).index('Trade Number'): None}
i_tn = hdr.index('Trade Number') + 1
i_td = hdr.index('Trade Date') + 1
i_ag = hdr.index('Aging') + 1
linha_t1 = next(i for i in (2, 3) if ws.cell(row=i, column=i_tn).value == 'T-1')
check('data vira DATA com mascara DD/MM/YYYY',
      (isinstance(ws.cell(row=linha_t1, column=i_td).value, datetime),
       ws.cell(row=linha_t1, column=i_td).number_format), (True, 'DD/MM/YYYY'))
check('   e o Aging vira numero', ws.cell(row=linha_t1, column=i_ag).value, 45)

print('\n== 4. o Run de hoje grava no share ==')
r = c.post('/api/control-panel/pending-spreadsheet/run', json={})
d = r.get_json()
fp = os.path.join(B.DIR, 'PENDING - Outstanding Confirmation OTC.xlsx')
check('200 com as 2 linhas, fonte live', (r.status_code, d['rows'], d['source']), (200, 2, 'live'))
check('   o arquivo esta la', os.path.exists(fp), True)
st = json.load(io.open(PP.status_file(), encoding='utf-8'))
check('   status manual sem ref', (st['slot'], st['ref']), ('manual', ''))
check('   e avisa no sino', NOTIFS[-1], ('Pending Spreadsheet Saved', 'Control Panel'))

print('\n== 5. data anterior: snapshot, sem recategorizar ==')
r = c.post('/api/control-panel/pending-spreadsheet/run', json={'date': '2099-01-01'})
check('futuro e 400', (r.status_code, 'future' in r.get_json()['error']), (400, True))
r = c.post('/api/control-panel/pending-spreadsheet/run', json={'date': '2026-08-12'})
check('sem snapshot e 404 dizendo o caminho',
      (r.status_code, 'pending-confirmation_20260812.json' in r.get_json()['error']),
      (404, True))
snap_dir = os.path.join(R._PC_SNAPSHOT_DIR, '2026', '08', '12')
os.makedirs(snap_dir, exist_ok=True)
io.open(os.path.join(snap_dir, 'pending-confirmation_20260812.json'), 'w', encoding='utf-8').write(
    json.dumps([{'Trade Number': 'V-1', 'Client': 'VELHA', 'Status': 'Ok', 'Aging': '99'}]))
r = c.post('/api/control-panel/pending-spreadsheet/run', json={'date': '2026-08-12'})
d = r.get_json()
# A foto JA E o balde pending daquele dia: a linha entra mesmo dizendo Ok hoje.
check('a foto vale como esta (1 linha, fonte snapshot)',
      (r.status_code, d['rows'], d['source'], d['ref_date']), (200, 1, 'snapshot', '12/08/2026'))
st = json.load(io.open(PP.status_file(), encoding='utf-8'))
check('   e o status marca a REF da foto que esta no share', st['ref'], '12/08/2026')

print('\n== 6. o disparo automatico ==')
_biz = R._pcx_is_bizday
R._pcx_is_bizday = lambda d2: True
check('grava e consome o slot', PCX_disparar('2026-08-25 10:45', R._br_now()), True)
check('   repetir nao grava de novo', PCX_disparar('2026-08-25 10:45', R._br_now()), False)
R._pcx_is_bizday = lambda d2: False
check('feriado nao dispara', PCX_disparar('2026-08-26 10:45', R._br_now()), False)
R._pcx_is_bizday = _biz

print('\n== 7. o status responde o proximo horario ==')
d = c.get('/api/control-panel/pending-spreadsheet/status').get_json()
check('tem last, next e o caminho', (bool(d['last']), bool(d['next']), d['path'].endswith('.xlsx')),
      (True, True, True))

print(('FAIL: %d' % len(fails)) if fails else 'TUDO OK')
sys.exit(1 if fails else 0)
