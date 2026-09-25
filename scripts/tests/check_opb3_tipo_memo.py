#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_opb3_tipo_memo.py — a coluna Type do Operations B3 não relê a posição.

O Advanced Export do Operations B3 (01/09 a hoje) falhava em seis dias com
"signal is aborted without reason": cada dia derivava a coluna Type lendo as
TRÊS posições de D-1 inteiras (DPOSICAO-TER, DPOSICAO, DPOSICAO-SWAP), que no
share levam dezenas de segundos frias, e o dia estourava o teto de 60 s.

Prova: o mapa contrato → tipo de cada arquivo fica em memória pelo carimbo
(caminho, mtime, tamanho); a segunda pergunta não lê o arquivo, e arquivo que
MUDOU é lido de novo. E o export passa a aceitar teto por página, com o
Operations B3 declarando 180 s, e uma segunda passada nos dias que falharam.
"""
import io
import os
import sys
import tempfile
from datetime import datetime

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', tempfile.mkdtemp(prefix='share-root-'))
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

from apps.pages.platform import operations_b3 as OB             # noqa: E402
from apps.pages import routes as R                               # noqa: E402
from apps.pages import duck_read                                 # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label +
          ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


class St:
    def __init__(self, m):
        self.st_mtime, self.st_size = m, 10


lidos = []
mtime = {'v': 1.0}
POS = {'NDF': [{'Contrato': 'T1', 'Classe do Ativo Subjacente': 'MOEDA'}],
       'Option': [{'Código IF': 'O1', 'Classe do Ativo Subjacente': 'COMMODITY'}],
       'Swap': [{'Contrato': 'S1', 'Código Identificador': 'EDG'}]}

orig = (OB._store.isfile, OB._store.stat, duck_read.day_records, R._prev_anbima_bizday)
OB._store.isfile = lambda p: True
OB._store.stat = lambda p: St(mtime['v'])
R._prev_anbima_bizday = lambda d: datetime(2026, 9, 24)


def fake_read(p):
    lidos.append(p)
    for cat, rows in POS.items():
        if os.sep + cat + os.sep in p:
            return rows
    return []


duck_read.day_records = fake_read
OB._TIPO_MEMO.clear()
try:
    m1 = OB._opb3_tipo_maps(datetime(2026, 9, 25))
    check('primeira vez le as tres posicoes', len(lidos), 3)
    check('o mapa sai certo', (m1['TER'], m1['OPC'], m1['SWAP']),
          ({'T1': 'MOEDA'}, {'O1': 'COMMODITY'}, {'S1': 'EDG'}))
    m2 = OB._opb3_tipo_maps(datetime(2026, 9, 26))
    check('mesma posicao D-1: nao le de novo', len(lidos), 3)
    check('e responde o mesmo mapa', m2, m1)
    mtime['v'] = 2.0
    OB._opb3_tipo_maps(datetime(2026, 9, 25))
    check('posicao regravada (carimbo novo) e lida de novo', len(lidos), 6)
finally:
    OB._store.isfile, OB._store.stat, duck_read.day_records, R._prev_anbima_bizday = orig
    OB._TIPO_MEMO.clear()

JS = io.open('apps/static/js/export-advanced.js', encoding='utf-8').read()
check('export: teto por pagina', 'timeout: +d.timeout || DAY_TIMEOUT_MS' in JS, True)
check('export: segunda passada nos dias que falharam', 'failed.splice(0, failed.length)' in JS, True)
check('export: abortado diz o tempo, nao "erro de rede"', "e.name === 'AbortError'" in JS, True)
OPJ = io.open('apps/static/js/pages/operations-b3.js', encoding='utf-8').read()
check('Operations B3 declara 180 s', "timeout: 180000" in OPJ, True)

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS: %d' % len(fails)))
sys.exit(1 if fails else 0)
