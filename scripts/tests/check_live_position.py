# -*- coding: utf-8 -*-
"""O card Live Position do dashboard — a leitura dos arquivos de posicao da B3.

O card le TRES arquivos-dia (`DPOSICAO-TER`, `DPOSICAO`, `DPOSICAO-SWAP`) e
conta uma operacao por linha. O que este teste prende:

  1. os tres arquivos entram, cada um com o seu classificador de produto;
  2. **o vocabulario de LOB do swap e o MESMO do `_accrual_lob`** — o
     `Codigo Identificador` real da B3 traz QUATRO tokens: `CEM`, `EDG`,
     `CEMHYB` e `COMM` (o `HYB` do grafico e so a EXIBICAO do CEMHYB, pelo
     `liveDisplayLabel`). Ate 11/09/2026 o `_fcst_lob` nao conhecia o `COMM`,
     que o `_accrual_lob` sempre teve: todo swap de mercadoria caia no
     `continue` e sumia do card SEM deixar rastro nenhum, enquanto a mesma
     linha aparecia na Swap Characteristics;
  3. **linha que nao classifica deixa RASTRO** — arquivo achado que conta zero
     era indistinguivel de arquivo ausente, e e por isso que "o KPI nao puxa os
     swaps" virava caca ao bug;
  4. o BANCO agrega todo intragrupo (Lawton/MGT/Atacama somam no bucket dele
     alem do proprio) e os produtos-placeholder aparecem zerados;
  5. o walk-back acha a ultima data COM arquivo em vez de desenhar zeros.
"""
import json, logging, os, sys, tempfile
from datetime import datetime, timedelta, timezone

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


class _Pega(logging.Handler):
    """Guarda as mensagens do logger do app para provar o RASTRO."""

    def __init__(self):
        logging.Handler.__init__(self)
        self.msgs = []

    def emit(self, rec):
        try:
            self.msgs.append(rec.getMessage())
        except Exception:                                   # noqa: BLE001
            pass


_h = _Pega()
logging.getLogger('otc_tracker').addHandler(_h)
logging.getLogger('otc_tracker').setLevel(logging.INFO)

# O card le pelo armazem a partir do B3_JSON_ROOT; apontando a raiz para um tmp,
# as escritas do teste sao as UNICAS que ele enxerga.
R.B3_JSON_ROOT = os.path.join(TMP, 'b3 files')

REF = datetime(2026, 9, 10)
DREF = REF.strftime('%y%m%d')
SUB = R._b3_date_subpath(DREF)


def grava(categoria, nome, linhas):
    d = os.path.join(R.B3_JSON_ROOT, categoria, SUB)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, nome), 'w', encoding='utf-8') as fh:
        json.dump(linhas, fh)


# Um registro por arquivo, com as colunas que o card resolve por nome.
# As contas sao as do `_LIVE_ENTITY_MAP`: 73760.10-2 (Banco), 00041.00-7
# (Lawton), 04880.00-6 (MGT).
grava('NDF', '73760_{}_DPOSICAO-TER.json'.format(DREF), [
    {'Contraparte': '00041.00-7', 'Classe do Ativo': 'TAXA DE CAMBIO'},
    {'Contraparte': '73760.10-2', 'Classe do Ativo': 'COMMODITIES'},
])
grava('Option', '73760_{}_DPOSICAO.json'.format(DREF), [
    {'Contraparte': '04880.00-6', 'Classe do Ativo Subjacente': 'TAXA DE CAMBIO'},
])
# O swap com os QUATRO tokens reais da B3 (CEM / EDG / CEMHYB / COMM), dois
# deles hibridos para provar que caem no mesmo balde, mais uma linha que nao
# classifica de proposito.
grava('Swap', '73760_{}_DPOSICAO-SWAP.json'.format(DREF), [
    {'Contraparte': '73760.10-2', 'Codigo Identificador': 'CEM-2026-3184'},
    {'Contraparte': '00041.00-7', 'Codigo Identificador': 'EDG-2026-8381'},
    {'Contraparte': '04880.00-6', 'Codigo Identificador': 'CEMHYB-2026-0406'},
    {'Contraparte': '73760.10-2', 'Codigo Identificador': 'CEMHYB-2026-7712'},
    {'Contraparte': '73760.10-2', 'Codigo Identificador': 'COMM-2026-5590'},
    {'Contraparte': '73760.10-2', 'Codigo Identificador': 'SEM-TOKEN-0001'},
])

c, anon = cliente(), cliente(auth=False)

print('== 1. sem sessao ==')
check('401', anon.get('/api/dashboard-live-position').status_code, 401)

print('\n== 2. o vocabulario de LOB e o MESMO nos dois classificadores ==')
# Ate 11/09/2026 o card do dashboard e a Swap Characteristics discordavam sobre
# a mesma string: COMM era LOB para um e nada para o outro. Os dois ultimos sao
# TOLERANCIA DE GRAFIA (`HIBRIDO`, `CEM-HIB`), nao valores que a B3 grava.
for ident in ('CEM-2026-3184', 'EDG-2026-8381', 'CEMHYB-2026-0406',
              'COMM-2026-5590', 'HYB-2026-7712', 'HIB-2026-0009'):
    check('%-18s classifica nos DOIS' % ident,
          (R._fcst_lob(ident) is not None, R._accrual_lob(ident) is not None),
          (True, True))
check('   e o que nao tem token continua sem LOB nos dois (nunca um chute)',
      (R._fcst_lob('SEM-TOKEN-0001'), R._accrual_lob('SEM-TOKEN-0001')), (None, None))
check('   os quatro tokens reais, um balde cada',
      [R._fcst_lob(x) for x in ('CEM-1', 'EDG-1', 'CEMHYB-1', 'COMM-1')],
      ['CEM', 'EDG', 'CEMHYB', 'COMM'])
check('   o hibrido vence o CEM que a propria string do CEMHYB carrega',
      R._fcst_lob('CEMHYB-2026-0406'), 'CEMHYB')
check('   e a grafia solta ainda cai no balde do hibrido (tolerancia)',
      R._fcst_lob('HYB-2026-7712'), R._fcst_lob('CEMHYB-2026-0406'))

print('\n== 3. os tres arquivos entram no card ==')
del _h.msgs[:]
r = c.get('/api/dashboard-live-position?date=2026-09-10')
d = r.get_json()
check('200 na data pedida', (r.status_code, d['ref_date']), (200, '2026-09-10'))
check('os tres arquivos achados',
      sorted((s['label'], s['found']) for s in d['sources']),
      [('NDF', True), ('Options', True), ('Swap', True)])
prod = {p['label']: p['count'] for p in d['by_product']}
check('NDF Moeda / NDF Commodities', (prod['NDF Moeda'], prod['NDF Commodities']), (1, 1))
check('Option FXO', prod['Option FXO'], 1)

print('\n== 4. o swap conta as CINCO linhas com token ==')
check('SWAP CEM', prod.get('SWAP CEM'), 1)
check('SWAP EDG', prod.get('SWAP EDG'), 1)
check('SWAP CEMHYB (os dois hibridos no mesmo balde)', prod.get('SWAP CEMHYB'), 2)
check('SWAP COMM', prod.get('SWAP COMM'), 1)
check('a linha sem token NAO entra (nem como chute)', sum(prod.values()), 8)
check('e o total bate com a soma das barras', d['total'], 8)

print('\n== 5. arquivo achado que nao classifica deixa RASTRO ==')
# Sem o rastro, "swap zerado" e "arquivo ausente" sao a MESMA tela — e foi isso
# que fez o KPI parecer mudo quando o vocabulario de LOB ficou para tras.
check('o log diz quantas linhas ficaram de fora e o valor que nao casou',
      (any('sem LOB' in m for m in _h.msgs),
       any('SEM-TOKEN-0001' in m for m in _h.msgs)), (True, True))

print('\n== 6. o BANCO agrega todo intragrupo ==')
ent = {e['label']: e['count'] for e in d['by_entity']}
# Banco proprio: 1 NDF + 3 swaps (CEM, CEMHYB, COMM; sem-token nao conta) = 4.
# Lawton: 1 NDF + 1 swap = 2. MGT: 1 opcao + 1 swap = 2. O bucket do Banco soma
# os dois por cima do proprio.
check('LAWTON e MGT mantem a contagem propria', (ent['LAWTON'], ent['MGT']), (2, 2))
check('BANCO = o proprio + Lawton + MGT', ent['BANCO'], 4 + 2 + 2)

print('\n== 7. os produtos-placeholder aparecem zerados, nunca somem ==')
for p in R._LIVE_PLACEHOLDER_PRODUCTS:
    check('   %s presente na barra' % p, p in prod, True)

print('\n== 8. sem arquivo na data, o card anda para tras ate achar ==')
r = c.get('/api/dashboard-live-position?date=2026-09-11')
d2 = r.get_json()
check('cai na data COM arquivo, nao em zeros',
      (d2['ref_date'], d2['total']), ('2026-09-10', 8))

print(('FAIL: %d' % len(fails)) if fails else 'TUDO OK')
sys.exit(1 if fails else 0)
