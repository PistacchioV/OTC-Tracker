# -*- coding: utf-8 -*-
"""O MtM de Swap — a casca da tela (data/latest/comment/edit) e o ciclo da linha.

O que ele prende:

  1. **o zero e canonizado na LEITURA** (`0` vira `0.00` + o comentario padrao,
     gravado de volta): a tabela mostra o valor exato da planilha, e so o
     preview/arquivo gerado sobe o zero para 1 no ultimo decimal (a B3 recusa
     MtM zero). Celula em BRANCO (Missing MtM) fica como esta;
  2. **edit reabre o ciclo**: status Pending, maker = quem editou, checker
     LIMPO; o id (ultima celula) e as quatro de ciclo nao sao editaveis;
  3. comment escreve na ULTIMA celula de dado (len-5);
  4. data sem arquivo do dia devolve `empty` (nao 404): a tela abre vazia.
"""
import io, json, os, sys, tempfile
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

# O MtM mora em features/mtm (nomes preservados no engine).
# O MtM mora em features/mtm, separado em camadas (§321): a raiz do
# arquivo-dia e de `infra/persistence`, os indices de coluna sao do domain.
from apps.pages.features.mtm import domain as BD               # noqa: E402
from apps.pages.features.mtm.infra import persistence as B     # noqa: E402
B.MTM_JSON_ROOT = TMP

NOTIFS = []
R._create_notification = lambda *a, **k: NOTIFS.append(a[2:4])

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
            s['user_name'] = 'Alice'
            s['user_role'] = 'BO'
            s['user_email'] = 'a@x'
            s['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()
    return c


c, anon = cliente(), cliente(auth=False)

print('== 1. sem sessao ==')
check('data -> 401', anon.get('/api/mtm-swap/data').status_code, 401)
check('row/edit -> 401', anon.post('/api/mtm-swap/row/edit').status_code, 401)

print('\n== 2. sem arquivo do dia, a tela abre VAZIA ==')
d = c.get('/api/mtm-swap/data?date=2026-08-20').get_json()
check('empty, nao 404', (d['success'], d.get('empty')), (True, True))

# ── monta o dataset do dia com a forma real: [..., Valor, ..., Comment,
#    status, maker, checker, id] — os indices vem das constantes do modulo.
VIDX, CIDX = BD._MTM_VALOR_IDX, BD._MTM_COMMENT_IDX
ncells = max(VIDX, CIDX) + 2                 # celulas de dado (Comment = ultima)
def linha(rid, valor):
    r = ['c%d' % i for i in range(ncells)]
    r[VIDX] = valor
    r[CIDX] = ''
    r += ['New', '', '', rid]
    return r
DATA = {'tables': {'CEM': [linha('CEM-0', '1,500.00'), linha('CEM-1', '0')]},
        'headers': {}, 'counts': {'CEM': 2}}
pasta = os.path.join(TMP, '2026', '08', '20')
os.makedirs(pasta, exist_ok=True)
io.open(os.path.join(pasta, 'mtm_swap_20260820.json'), 'w', encoding='utf-8').write(json.dumps(DATA))

print('\n== 3. o zero e canonizado na leitura ==')
d = c.get('/api/mtm-swap/data?date=2026-08-20').get_json()
r1 = d['tables']['CEM'][1]
check('0 vira 0.00 com o comentario padrao',
      (r1[VIDX], bool(str(r1[CIDX]).strip())), ('0.00', True))
check('   o valor nao-zero fica como veio', d['tables']['CEM'][0][VIDX], '1,500.00')
no_disco = json.load(io.open(os.path.join(pasta, 'mtm_swap_20260820.json'), encoding='utf-8'))
check('   e a canonizacao foi GRAVADA de volta', no_disco['tables']['CEM'][1][VIDX], '0.00')
check('latest devolve o dia', c.get('/api/mtm-swap/latest').get_json()['date'], '2026-08-20')

print('\n== 4. comment escreve na ultima celula de dado ==')
r = c.post('/api/mtm-swap/row/comment', json={'date': '2026-08-20', 'lob': 'CEM',
                                              'id': 'CEM-0', 'comment': 'ajuste manual'})
check('200', r.status_code, 200)
no_disco = json.load(io.open(os.path.join(pasta, 'mtm_swap_20260820.json'), encoding='utf-8'))
r0 = no_disco['tables']['CEM'][0]
check('   no disco, em len-5', r0[len(r0) - 5], 'ajuste manual')

print('\n== 5. edit reabre o ciclo ==')
novas = ['x%d' % i for i in range(ncells)]
r = c.post('/api/mtm-swap/row/edit', json={'date': '2026-08-20', 'lob': 'CEM',
                                           'id': 'CEM-0', 'cells': novas + ['HACK', 'HACK', 'HACK', 'HACK']})
check('200', r.status_code, 200)
no_disco = json.load(io.open(os.path.join(pasta, 'mtm_swap_20260820.json'), encoding='utf-8'))
r0 = no_disco['tables']['CEM'][0]
check('celulas de dado editadas; ciclo resetado; id intacto',
      (r0[0], r0[-4], r0[-3], r0[-2], r0[-1]), ('x0', 'Pending', 'A111111', '', 'CEM-0'))
r = c.post('/api/mtm-swap/row/edit', json={'date': '2026-08-20', 'lob': 'CEM',
                                           'id': 'NAO-EXISTE', 'cells': []})
check('linha inexistente e 404', r.status_code, 404)

print(('FAIL: %d' % len(fails)) if fails else 'TUDO OK')
sys.exit(1 if fails else 0)
