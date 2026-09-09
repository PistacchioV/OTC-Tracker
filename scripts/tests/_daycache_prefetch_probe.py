"""Sonda do `check_daycache` secao 8: CONTA as aberturas de banco.

Roda num processo proprio porque troca `OTC_DATA_DIR`/`OTC_DATABASE_DIR` antes
de importar o `apps.config` — as duas sao lidas no import, e mexer nelas com o
app ja de pe nao mudaria nada. Imprime uma linha `PROBE {json}`.
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

# Um produto de arquivo-dia de verdade, para o `_daily_rel_target` reconhecer.
PROD = os.path.join(RAIZ, 'cache', 'new deals', 'NDF', 'Vanilla')
SUF = '_ndfvanilla.json'
DIAS = 12
POR_DIA = 3

d = dt.date(2026, 3, 2)
feitos = 0
while feitos < DIAS:
    if d.weekday() < 5:
        pasta = os.path.join(PROD, '%04d' % d.year, '%02d' % d.month)
        os.makedirs(pasta, exist_ok=True)
        with open(os.path.join(pasta, d.strftime('%Y%m%d') + SUF), 'w') as fh:
            json.dump([{'Deal': 'D%d-%d' % (feitos, i), 'Client': 'C%d' % i}
                       for i in range(POR_DIA)], fh)
        feitos += 1
    d += dt.timedelta(days=1)

res = {'dias': DIAS}
with app.test_request_context('/'):
    from apps.pages import routes as R
    from apps.pages import json_to_duckdb as core
    from apps.pages import database_access as DA
    from apps.pages import duck_read

    dias = list(R._day_files(PROD, SUF))
    rels = [os.path.relpath(fp, RAIZ).replace(os.sep, '/') for fp, _n, _m, _s in dias]

    # Um dos dias fica FORA do banco de proposito: prefetch e otimizacao, nunca
    # decisao — quem o banco nao responde continua sendo lido do jeito de sempre.
    core.convert_daily_files(RAIZ, os.environ['OTC_DATABASE_DIR'], rels[:-1])
    de_fora = dias[-1]

    abertas = {'n': 0}
    _orig = DA.duckdb_read

    class _Conta(object):
        def __init__(self, *a, **k):
            abertas['n'] += 1
            self._cm = _orig(*a, **k)

        def __enter__(self):
            return self._cm.__enter__()

        def __exit__(self, *a):
            return self._cm.__exit__(*a)

    duck_read.duckdb_read = _Conta

    # ---- sem prefetch: uma abertura por dia ----
    R._daycache_forget()
    abertas['n'] = 0
    res['solo_regs'] = sum(len(R._day_json(fp, mt, sz)) for fp, _n, mt, sz in dias[:-1])
    res['solo_abre'] = abertas['n']

    # ---- com prefetch: uma abertura so ----
    # A conta vai ate o FIM do laco, e nao so ate o prefetch: e o laco que
    # abria o banco uma vez por dia, e parar de contar antes dele daria o
    # numero bonito de um prefetch que nao fez efeito nenhum.
    R._daycache_forget()
    abertas['n'] = 0
    R._day_prefetch(dias[:-1])
    res['lote_regs'] = sum(len(R._day_json(fp, mt, sz)) for fp, _n, mt, sz in dias[:-1])
    res['lote_abre'] = abertas['n']

    # ---- memo quente: nao volta ao banco ----
    abertas['n'] = 0
    R._day_prefetch(dias[:-1])
    res['quente_abre'] = abertas['n']

    # ---- o dia que o banco nao tem continua sendo lido ----
    R._daycache_forget()
    R._day_prefetch([de_fora])
    res['sem_banco_regs'] = len(R._day_json(de_fora[0], de_fora[2], de_fora[3]))

    duck_read.duckdb_read = _orig

print('PROBE ' + json.dumps(res))
