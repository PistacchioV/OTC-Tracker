"""Sonda do `check_daycache` secao 8: CONTA as aberturas de banco.

Roda num processo proprio porque troca `OTC_DATA_DIR`/`OTC_DATABASE_DIR` antes
de importar o `apps.config` — as duas sao lidas no import, e mexer nelas com o
app ja de pe nao mudaria nada. Imprime uma linha `PROBE {json}`.

DB-only (§434): os dias entram pelo FUNIL (vao direto para o banco do
produto); um dia fica so no DISCO, como legado — o banco nao o enumera, mas a
primeira leitura o importa e responde por ele.
"""
import datetime as dt
import json
import os
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', tempfile.mkdtemp(prefix='share-root-'))
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'
RAIZ = tempfile.mkdtemp(prefix='prefetch-probe-')
os.environ['OTC_DATA_DIR'] = RAIZ
os.environ['OTC_DATABASE_DIR'] = os.path.join(RAIZ, 'db')

from apps import create_app                                # noqa: E402
from apps.config import DebugConfig                        # noqa: E402

app = create_app(DebugConfig)
PROD = os.path.join(RAIZ, 'cache', 'new deals', 'NDF', 'Vanilla')
SUF = '_ndfvanilla.json'
DIAS = 12
POR_DIA = 3
res = {'dias': DIAS}
with app.test_request_context('/'):
    from apps.pages import routes as R
    from apps.pages import data_store as S

    d = dt.date(2026, 3, 2)
    feitos = 0
    caminhos = []
    while feitos < DIAS:
        if d.weekday() < 5:
            fp = os.path.join(PROD, '%04d' % d.year, '%02d' % d.month, d.strftime('%Y%m%d') + SUF)
            payload = [{'Deal': 'D%d-%d' % (feitos, i), 'Client': 'C%d' % i} for i in range(POR_DIA)]
            if feitos < DIAS - 1:
                R._atomic_write_json(fp, payload)          # pelo funil: no banco
            else:
                os.makedirs(os.path.dirname(fp), exist_ok=True)
                with open(fp, 'w', encoding='utf-8') as fh:   # legado: so no disco
                    json.dump(payload, fh)
            caminhos.append(fp)
            feitos += 1
        d += dt.timedelta(days=1)
    dias = list(R._day_files(PROD, SUF))
    assert len(dias) == DIAS - 1, dias
    st = os.stat(caminhos[-1])
    de_fora = (caminhos[-1], os.path.basename(caminhos[-1]), st.st_mtime, st.st_size)

    abertas = {'n': 0}
    _orig = S.duckdb_read

    class _Conta(object):
        def __init__(self, *a, **k):
            abertas['n'] += 1
            self._cm = _orig(*a, **k)

        def __enter__(self):
            return self._cm.__enter__()

        def __exit__(self, *a):
            return self._cm.__exit__(*a)

    S.duckdb_read = _Conta
    # ---- sem prefetch: uma abertura por dia ----
    R._daycache_forget()
    S.memo_forget()
    abertas['n'] = 0
    res['solo_regs'] = sum(len(R._day_json(fp, mt, sz)) for fp, _n, mt, sz in dias)
    res['solo_abre'] = abertas['n']
    # ---- com prefetch: uma abertura so ----
    R._daycache_forget()
    S.memo_forget()
    abertas['n'] = 0
    R._day_prefetch(dias)
    res['lote_regs'] = sum(len(R._day_json(fp, mt, sz)) for fp, _n, mt, sz in dias)
    res['lote_abre'] = abertas['n']
    # ---- memo quente: nao volta ao banco ----
    abertas['n'] = 0
    R._day_prefetch(dias)
    res['quente_abre'] = abertas['n']
    # ---- o dia que o banco nao tem (legado em disco) continua sendo lido ----
    R._daycache_forget()
    R._day_prefetch([de_fora])
    res['sem_banco_regs'] = len(R._day_json(de_fora[0], de_fora[2], de_fora[3]))
    S.duckdb_read = _orig
print('PROBE ' + json.dumps(res))
