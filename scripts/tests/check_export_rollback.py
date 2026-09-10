"""check_export_rollback.py — o ROLLBACK do §434 (`scripts/export_duckdb_to_json.py`)
reconstrói do banco, EXATO, cada forma de payload que o armazém guarda.

Achado na varredura de 09/09/2026: o script escolhia como tabela do caminho
"o primeiro target que não termina em __raw" — num payload-OBJETO isso é o
`__meta`, o `ler_payload` procurava `__meta__raw`, e o rollback dizia "sem
canal de reconstrução" (control-panel) ou devolvia uma LISTA das sub-tabelas
(templates do File Interpreter). Nada prendia. O que se prova, em tempfile:
  1. arquivo-dia (lista), dataset (lista), cadastro do /mapping, RefData,
     objeto (recipients/status do control-panel, template do File
     Interpreter), `.meta.json`, ponteiro `_last` e calendário voltam IGUAIS;
  2. o que já está igual no disco não é reescrito; `--force` reescreve;
  3. `--only` limita à subárvore.
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', tempfile.mkdtemp(prefix='share-root-'))
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

from apps.pages import routes as R                         # noqa: E402
from apps.pages import data_store as S                     # noqa: E402

fails = []


def check(label, got, exp=True):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


TMP = tempfile.mkdtemp(prefix='otc-rollback-')
R._B3_DATA_DIR = TMP
DB = os.path.join(TMP, 'db')
OUT = os.path.join(TMP, 'export')

_spec = importlib.util.spec_from_file_location('export_duckdb_to_json',
                                               os.path.join(ROOT, 'scripts', 'export_duckdb_to_json.py'))
EXP = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(EXP)

PAYLOADS = {
    'cache/new deals/NDF/Commodities/2026/06/20260615_ndfcomm.json':
        [{'Deal': 'D1', 'TradeDate': '15/06/2026', 'Notional': 1000.5, 'Extra': None},
         {'Deal': 'D2', 'TradeDate': '15/06/2026', 'Notional': 2, 'Extra': {'a': [1, 2]}}],
    'mappings/bank-name.json': [{'BANK': 'ITAU', 'ALIAS': 'Itaú Unibanco'}, {'BANK': 'BB', 'ALIAS': ''}],
    'RefData.json': [{'COUNTERPARTY': 'ACME', 'SPN': '123', 'TAX ID': '00.000.000/0001-91'}],
    'control-panel/daily_metric_recipients.json': {'to': ['a@x', 'b@x'], 'cc': [], 'updated': '2026-09-09T10:00:00'},
    'control-panel/bacc_ea_metrics_sent.json': ['2026-09-08 16:00', '2026-09-09 16:00'],
    'file-interpreter/antecipacao-opcao.json':
        {'key': 'antecipacao-opcao', 'name': 'Antecipação de Opção', 'blocks': [
            {'id': 'header', 'fields': [{'name': 'X', 'source': 'Fixed', 'value': ''}]},
            {'id': 'body', 'fields': []}], 'version': 3},
    'cache/daily settlement/2026/09/24/ndf-cockpit_20260924.meta.json': {'updated': '10:11:12', 'source': 'api'},
    'cache/reconciliation/payrec/_last.json': {'date': '2026-07-06', 'file': 'payrec_status_20260706.json'},
    'cache/reconciliation/payrec/2026-07-06.json': {'rows': [{'k': 1}], 'summary': {'ok': 1, 'nok': 0}},
    'holiday-calendars.json': [{'name': 'Brazil', 'file': 'brazil.json', 'color': '#123456', 'slug': 'brazil'}],
    'brazil.json': [{'date': '2026-11-20', 'title': 'Consciência Negra'}, {'date': '2026-12-25', 'title': 'Natal'}],
}
for rel, payload in PAYLOADS.items():
    R._atomic_write_json(os.path.join(TMP, *rel.split('/')), payload)
check('setup: nenhum JSON no disco', [p for p in PAYLOADS if os.path.isfile(os.path.join(TMP, *p.split('/')))], [])

print('== 1. cada forma volta IGUAL ==')
st = EXP.exportar(DB, OUT)
check('sem erros', st['erros'], [])
for rel, payload in PAYLOADS.items():
    alvo = os.path.join(OUT, *rel.split('/'))
    if not os.path.isfile(alvo):
        check('exportou ' + rel, False)
        continue
    with open(alvo, encoding='utf-8') as fh:
        volta = json.load(fh)
    if rel == 'brazil.json':                                 # calendário: a tabela tipada
        volta = [{'date': r['date'], 'title': r['title']} for r in volta]
    check('igual: ' + rel, volta, payload)
check('e nada a mais', sorted(os.path.relpath(os.path.join(d, f), OUT).replace(os.sep, '/')
                              for d, _ds, fs in os.walk(OUT) for f in fs if f.endswith('.json')),
      sorted(PAYLOADS))

print('\n== 2. igual no disco nao reescreve; --force reescreve ==')
st2 = EXP.exportar(DB, OUT)
check('segunda rodada: 0 escritos', st2['escritos'], 0)
check('   e todos iguais', st2['iguais'], len(PAYLOADS))
st3 = EXP.exportar(DB, OUT, force=True)
check('--force reescreve todos', st3['escritos'], len(PAYLOADS))

print('\n== 3. --only limita a subarvore ==')
OUT2 = os.path.join(TMP, 'export2')
st4 = EXP.exportar(DB, OUT2, only='control-panel')
check('so o control-panel', sorted(os.listdir(os.path.join(OUT2, 'control-panel'))),
      ['bacc_ea_metrics_sent.json', 'daily_metric_recipients.json'])
check('   e nada fora dele', sorted(os.listdir(OUT2)), ['control-panel'])

shutil.rmtree(TMP, ignore_errors=True)
print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
