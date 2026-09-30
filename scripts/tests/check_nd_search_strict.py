#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A busca das telas de New Deals não pode abrir VAZIA quando o banco falha.

O defeito (30/09/2026, Commodities Options na instância): a tabela carregou,
a operação apareceu como `New`, uma gravação mudou o carimbo do dia — e dali
em diante a busca respondia `success: true` sem nenhuma operação. O
`_day_json` engolia QUALQUER exceção da leitura (`except Exception: return
[]`) sem uma linha no log, e a listagem pelo manifest (`_entries_under`)
tirava da lista o banco ocupado/ilegível do mesmo jeito.

Prende:
  1. `_day_json` com a leitura falhando: sem cópia em memória → `[]` (quem não
     pede `strict`) ou a exceção SOBE (`strict=True`); com cópia de um carimbo
     anterior → a cópia, nos dois modos; a falha vai para o log.
  2. Arquivo que sumiu entre a listagem e a leitura (`FileNotFoundError`) é
     ausência: `[]` mesmo em `strict`, sem aviso.
  3. `data_store.day_files(strict=True)` repassa o `strict` ao manifest.
  4. As quatro buscas do New Deals pedem `strict=True` na listagem E na
     leitura.
"""
import logging
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', '/tmp/otc-share')
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')

from apps.pages import data_store                       # noqa: E402
from apps.pages.platform import json_cache as J         # noqa: E402

FAILS = []


def ok(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg)
    if not cond:
        FAILS.append(msg)


class _Log(logging.Handler):
    def __init__(self):
        super().__init__()
        self.msgs = []

    def emit(self, rec):
        self.msgs.append(rec.getMessage())


cap = _Log()
logging.getLogger('otc_tracker').addHandler(cap)

_read_real = data_store.read


def _falha(fp):
    raise data_store.BancoOcupado('/db/new deals.db')


def _sumiu(fp):
    raise FileNotFoundError(fp)


FP = '/x/cache/new deals/Options/Commodities/2026/09/30/20260930_optcomm.json'
FP2 = FP.replace('30_optcomm', '29_optcomm')
try:
    # ── 1. falha sem cópia em memória ────────────────────────────────────────
    J._daycache_forget()
    J._dayjson_aviso.clear()
    data_store.read = _falha
    ok(J._day_json(FP, 1.0, 10) == [], 'sem strict: leitura que falha → [] (comportamento dos outros 30+ chamadores)')
    ok(any('[daycache]' in m and 'BancoOcupado' in m for m in cap.msgs),
       'a falha vai para o LOG (antes não deixava rastro)')
    try:
        J._day_json(FP, 1.0, 10, strict=True)
        ok(False, 'strict: a exceção SOBE')
    except data_store.BancoOcupado:
        ok(True, 'strict: a exceção SOBE (vira 503 pelo tratador global)')

    # ── 1b. falha COM cópia de um carimbo anterior ───────────────────────────
    J._daycache_forget()
    data_store.read = lambda fp: [{'Deal': 'D1', 'Status': 'New'}]
    ok(J._day_json(FP, 1.0, 10) == [{'Deal': 'D1', 'Status': 'New'}], 'leitura boa entra no memo')
    data_store.read = _falha
    antiga = J._day_json(FP, 2.0, 11, strict=True)      # a gravação mudou o carimbo
    ok(antiga == [{'Deal': 'D1', 'Status': 'New'}],
       'carimbo novo + banco falhando → a ÚLTIMA cópia em memória, não a tabela vazia')
    mut = J._day_json(FP, 2.0, 11, mutavel=True)
    mut[0]['Status'] = 'X'
    ok(J._day_json(FP, 2.0, 11)[0]['Status'] == 'New', 'a cópia servida com mutavel=True não contamina o memo')
    J._daycache_forget()
    data_store.read = lambda fp: [{'Deal': 'D2'}]
    J._day_json(FP, 3.0, 12)
    ok(J._day_json(FP, 3.0, 12) == [{'Deal': 'D2'}], 'a falha NÃO grava o memo: o carimbo novo lê de novo quando o banco volta')

    # ── 2. sumiu entre a listagem e a leitura ────────────────────────────────
    cap.msgs.clear()
    J._daycache_forget()
    data_store.read = _sumiu
    ok(J._day_json(FP2, 1.0, 10, strict=True) == [], 'FileNotFoundError é ausência: [] mesmo em strict')
    ok(not any('[daycache]' in m for m in cap.msgs), 'ausência não é aviso')
finally:
    data_store.read = _read_real
    J._daycache_forget()

# ── 3. day_files repassa o strict ao manifest ────────────────────────────────
vistos = []
_eu_real, _mr_real, _dr_real = data_store._entries_under, data_store._managed_dir, data_store.data_root
try:
    # `data_root()` importa o routes, e o import faz as próprias leituras:
    # fixada aqui, a lista `vistos` conta só as chamadas do `day_files`.
    data_store.data_root = lambda: '/x'
    data_store._managed_dir = lambda raiz: 'cache/new deals'
    data_store._entries_under = lambda rel, strict=False: vistos.append(strict) or {}
    list(data_store.day_files('/qualquer', strict=True))
    list(data_store.day_files('/qualquer'))
    ok(vistos == [True, False], 'day_files(strict=True) pede o manifest estrito; sem strict, o de sempre')
finally:
    data_store._entries_under, data_store._managed_dir, data_store.data_root = _eu_real, _mr_real, _dr_real

_man_real, _dbs_real = data_store._manifest, data_store._dbs_under
try:
    data_store._dbs_under = lambda rel: ['/db/a.db']

    def _man(db, strict=False):
        if strict:
            raise data_store.BancoIlegivel(db)
        return {}
    data_store._manifest = _man
    ok(data_store._entries_under('cache') == {}, '_entries_under sem strict: banco ruim some (o de sempre)')
    try:
        data_store._entries_under('cache', strict=True)
        ok(False, '_entries_under strict: ilegível sobe')
    except data_store.BancoIlegivel:
        ok(True, '_entries_under strict: ilegível sobe')
finally:
    data_store._manifest, data_store._dbs_under = _man_real, _dbs_real

# ── 4. as quatro buscas pedem strict nas duas pontas ─────────────────────────
src = open(os.path.join(ROOT, 'apps/pages/features/new_deals/entrypoint.py'), encoding='utf-8').read()
for rota in ('opt-commodities', 'opt-fxo', 'ndf-commodities', '<product>'):
    m = re.search(r"@blueprint\.route\('/api/new-deals/%s/cache/search'.*?\n(?=@blueprint\.route)" % re.escape(rota),
                  src, re.S)
    corpo = m.group(0) if m else ''
    ok(bool(re.search(r'_day_files\(.*strict=True', corpo)), '%s: listagem estrita' % rota)
    ok(bool(re.search(r'_day_json\(.*strict=True', corpo)), '%s: leitura estrita' % rota)

print('\n%d falha(s)' % len(FAILS) if FAILS else '\nOK')
sys.exit(1 if FAILS else 0)
