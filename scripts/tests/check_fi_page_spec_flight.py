#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A leitura de TODOS os templates do File Interpreter é SINGLE-FLIGHT.

O defeito (30/09/2026, instância): o `GET /api/file-interpreter/page-spec`,
que toda página de New Deals chama ao abrir, varria os ~40 templates — um
banco cada no armazém. Frio, no share, são minutos; e cada aba/F5 que chegava
no meio começava OUTRA varredura, disputando as mesmas travas: três presos de
66 s a 301 s no log, 70+ aberturas cada, cada um com uma thread do waitress.

Prende:
  1. N chamadas simultâneas de `_fi_all_templates` fazem UMA leitura e todas
     levam o mesmo resultado;
  2. terminada a leitura, a chamada seguinte lê de novo (sem TTL: template
     editado vale no request seguinte, como antes);
  3. a exceção do dono chega a quem esperava, e o voo é limpo;
  4. o `page-spec` e o `_fi_variant_key` passam pelo single-flight.
"""
import os
import re
import sys
import threading
import time

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', '/tmp/otc-share')
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')

from apps.pages import routes as R                       # noqa: E402,F401
from apps.pages.platform import file_interpreter as FI  # noqa: E402

FAILS = []


def ok(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg)
    if not cond:
        FAILS.append(msg)


_ler_real = FI._fi_all_templates_ler
chamadas = []


def _lenta(pasta):
    chamadas.append(pasta)
    time.sleep(0.4)
    return [{'key': 'k%d' % len(chamadas)}]


try:
    # ── 1. simultâneas → uma leitura ─────────────────────────────────────────
    FI._fi_all_templates_ler = _lenta
    res = []
    ths = [threading.Thread(target=lambda: res.append(FI._fi_all_templates())) for _ in range(6)]
    for t in ths:
        t.start()
        time.sleep(0.02)
    for t in ths:
        t.join(5)
    ok(len(chamadas) == 1, 'seis chamadas simultâneas → UMA leitura (eram %d)' % len(chamadas))
    ok(len(res) == 6 and all(r == [{'key': 'k1'}] for r in res), 'todas levam o MESMO resultado')
    ok(not FI._fi_all_voo, 'o voo é limpo ao terminar')

    # ── 2. sem TTL: a seguinte lê de novo ────────────────────────────────────
    ok(FI._fi_all_templates() == [{'key': 'k2'}] and len(chamadas) == 2,
       'terminada a leitura, a chamada seguinte lê de novo (edição vale no request seguinte)')

    # ── 3. exceção do dono chega a quem espera ───────────────────────────────
    def _quebra(pasta):
        time.sleep(0.3)
        raise IOError('banco preso')
    FI._fi_all_templates_ler = _quebra
    erros = []

    def _chama():
        try:
            FI._fi_all_templates()
        except IOError as e:
            erros.append(str(e))
    ths = [threading.Thread(target=_chama) for _ in range(3)]
    for t in ths:
        t.start()
        time.sleep(0.02)
    for t in ths:
        t.join(5)
    ok(erros == ['banco preso'] * 3, 'a falha do dono SOBE para quem esperava (não vira lista vazia)')
    ok(not FI._fi_all_voo, 'voo limpo também depois da falha')
    # ── 3b. espera=False: com leitura em voo, FiLendo NA HORA ────────────────
    FI._fi_all_templates_ler = _lenta
    dono = threading.Thread(target=FI._fi_all_templates)
    dono.start()
    time.sleep(0.05)
    t0 = time.monotonic()
    try:
        FI._fi_all_templates(espera=False)
        ok(False, 'espera=False com leitura em voo → FiLendo')
    except FI.FiLendo:
        ok(time.monotonic() - t0 < 0.1, 'espera=False com leitura em voo → FiLendo na hora (não segura a thread)')
    dono.join(5)
finally:
    FI._fi_all_templates_ler = _ler_real

# ── 3c. a leitura PARALELA devolve na ordem das chaves ───────────────────────
_ld, _tc, _w = FI._store.listdir, FI._fi_tpl_cached, FI._FI_READ_WORKERS
try:
    import random
    nomes = ['t%02d.json' % i for i in range(20)] + ['leia-me.txt']
    FI._store.listdir = lambda pasta: list(reversed(nomes))
    ativas, pico = [0], [0]
    trava = threading.Lock()

    def _tpl(k):
        with trava:
            ativas[0] += 1
            pico[0] = max(pico[0], ativas[0])
        time.sleep(random.uniform(0.01, 0.05))
        with trava:
            ativas[0] -= 1
        return None if k == 't07' else {'key': k}
    FI._fi_tpl_cached = _tpl
    FI._FI_READ_WORKERS = 8
    out = FI._fi_all_templates_ler('/x')
    ok([t['key'] for t in out] == ['t%02d' % i for i in range(20) if i != 7],
       'leitura paralela: na ordem do nome, sem o template que não abriu, sem o que não é .json')
    ok(pico[0] > 1, 'as aberturas correm em paralelo (pico %d)' % pico[0])
finally:
    FI._store.listdir, FI._fi_tpl_cached, FI._FI_READ_WORKERS = _ld, _tc, _w

# ── 4. os dois varredores passam por ele ─────────────────────────────────────
ep = open(os.path.join(ROOT, 'apps/pages/features/file_interpreter/entrypoint.py'), encoding='utf-8').read()
m = re.search(r"def api_file_interpreter_page_spec\(\):.*?\n(?=@blueprint\.route)", ep, re.S)
corpo = m.group(0) if m else ''
ok('_fi_all_templates(espera=False)' in corpo and 'listdir' not in corpo, 'page-spec lê pelo single-flight SEM esperar (sem listdir próprio)')
ok('FiLendo' in corpo and '503' in corpo, 'page-spec responde 503 na hora com leitura em voo')
pf = open(os.path.join(ROOT, 'apps/pages/platform/file_interpreter.py'), encoding='utf-8').read()
m = re.search(r"def _fi_variant_key\(.*?\n(?=\ndef )", pf, re.S)
corpo = m.group(0) if m else ''
ok('_fi_all_templates()' in corpo and 'listdir' not in corpo, '_fi_variant_key lê pelo single-flight')

print('\n%d falha(s)' % len(FAILS) if FAILS else '\nOK')
sys.exit(1 if FAILS else 0)
