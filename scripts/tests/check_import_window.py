#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_import_window.py — a janela dos schedulers de importacao (08:00-20:00).

As tres rotinas que trazem operacao de fora — a API de NDF, a de FXO e a
varredura do box de commodities — mantiveram o INTERVALO de cada uma (20, 60 e
30 min) e passaram a so agir dentro da janela. Fora dela o tique acontece e nao
faz nada: a mesa nao booka de madrugada, e cada poll era uma ida a Athena, ou
uma abertura do Outlook, para importar zero operacao.

O que este script prova:

  1. `_parse_hhmm_window` entende o formato e RECUSA o que nao entende
     devolvendo None — que e o que mantem a janela sempre aberta;
  2. `_import_window_open` inclui as DUAS pontas (as 20h em ponto ainda
     importam) e atravessa a meia-noite quando o fim vem antes do comeco;
  3. a janela sem cadastro devolve sempre True — um .env malformado nao pode
     desligar a importacao do dia em silencio;
  4. os tres loops consultam a janela: o `continue` esta ANTES do try, senao o
     poll de madrugada acontece do mesmo jeito.

Nao toca em rede, Outlook nem disco.
"""
import ast
import os
import sys
from datetime import datetime

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', os.path.join(ROOT, 'scripts', 'tests'))

from apps.pages import routes as R                            # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label +
          ('' if ok else '  got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def at(hh, mm=0):
    return datetime(2026, 8, 20, hh, mm)


print('\n== 1. o cadastro da janela ==')
check('o padrao e das 8h as 20h', R._parse_hhmm_window('08:00-20:00'), (480, 1200))
check('minuto quebrado', R._parse_hhmm_window('08:30-19:45'), (510, 1185))
check('sem minutos', R._parse_hhmm_window('8-20'), (480, 1200))
check('com espaco', R._parse_hhmm_window(' 08:00 - 20:00 '), (480, 1200))
for ruim in ('', '08:00', 'manha-noite', '25:00-20:00', '08:70-20:00', None):
    check('valor invalido (%r) desliga a janela' % (ruim,),
          R._parse_hhmm_window(ruim), None)

print('\n== 2. o padrao do app e 08:00-20:00 ==')
check('a janela do modulo', R._IMPORT_WINDOW, (480, 1200))
check('o rotulo do log', R._import_window_label(), '08:00-20:00')

print('\n== 3. quem passa e quem nao passa ==')
FECHADO = [at(0), at(6), at(7, 59), at(20, 1), at(21), at(23, 59)]
ABERTO = [at(8), at(8, 1), at(12), at(19, 59), at(20)]
for t in ABERTO:
    check('%s importa' % t.strftime('%H:%M'), R._import_window_open(t), True)
for t in FECHADO:
    check('%s NAO importa' % t.strftime('%H:%M'), R._import_window_open(t), False)

# As pontas sao inclusivas de proposito: "das 8h as 20h" tem de deixar passar o
# tique das 20h em ponto — o intervalo de cada scheduler nao e alinhado com a
# hora cheia, e cortar em 19:59 perderia a ultima varredura do dia.
check('as 8h em ponto e a primeira', R._import_window_open(at(8)), True)
check('as 20h em ponto e a ultima', R._import_window_open(at(20)), True)

print('\n== 4. janela virada e janela ausente ==')
_orig = R._IMPORT_WINDOW
try:
    R._IMPORT_WINDOW = R._parse_hhmm_window('20:00-08:00')
    check('vira a meia-noite: 23h abre', R._import_window_open(at(23)), True)
    check('vira a meia-noite: 03h abre', R._import_window_open(at(3)), True)
    check('vira a meia-noite: 12h fecha', R._import_window_open(at(12)), False)

    R._IMPORT_WINDOW = None
    check('sem janela, sempre aberta (03h)', R._import_window_open(at(3)), True)
    check('sem janela, sempre aberta (23h)', R._import_window_open(at(23)), True)
    check('sem janela, o log diz 24h', R._import_window_label(), '24h')
finally:
    R._IMPORT_WINDOW = _orig

print('\n== 5. os tres loops consultam a janela ==')
# Por AST, e nao por grep: o que importa e o `continue` guardado pela janela
# estar no CORPO do while, antes do trabalho — dentro do try ele ja teria
# custado o poll.
# O laco do box mora em features/boxscan/commands.py desde a extracao — os dois
# arquivos entram na mesma varredura.
LOOPS = {'_fxo_api_scheduler_loop': 'API de FXO',
         '_ndf_api_scheduler_loop': 'API de NDF',
         'scheduler_loop': 'box de commodities'}
achados = {}
for arq in (os.path.join(ROOT, 'apps', 'pages', 'routes.py'),
            os.path.join(ROOT, 'apps', 'pages', 'features', 'boxscan', 'commands.py')):
    tree = ast.parse(open(arq, encoding='utf-8').read())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in LOOPS:
            achados.setdefault(node.name, node)

for nome, rotulo in LOOPS.items():
    fn = achados.get(nome)
    check('%s: o loop existe' % rotulo, fn is not None, True)
    if fn is None:
        continue
    whiles = [n for n in fn.body if isinstance(n, ast.While)]
    check('%s: tem o while do scheduler' % rotulo, len(whiles) == 1, True)
    if not whiles:
        continue
    corpo = whiles[0].body
    guarda = None
    for i, stmt in enumerate(corpo):
        if not isinstance(stmt, ast.If):
            continue
        # O nome pode ser chamada direta (`_import_window_open()`, no routes) ou
        # busca atrasada (`_routes()._import_window_open()`, nas features).
        chamadas = []
        for n in ast.walk(stmt.test):
            if isinstance(n, ast.Call):
                if isinstance(n.func, ast.Name):
                    chamadas.append(n.func.id)
                elif isinstance(n.func, ast.Attribute):
                    chamadas.append(n.func.attr)
        if '_import_window_open' in chamadas:
            guarda = (i, stmt)
            break
    check('%s: consulta _import_window_open' % rotulo, guarda is not None, True)
    if guarda is None:
        continue
    i, stmt = guarda
    check('%s: pula o tique com continue' % rotulo,
          any(isinstance(n, ast.Continue) for n in stmt.body), True)
    # O trabalho vem DEPOIS da guarda.
    trabalho = [j for j, n in enumerate(corpo)
                if isinstance(n, (ast.Try, ast.For))]
    check('%s: a guarda vem antes do trabalho' % rotulo,
          bool(trabalho) and i < min(trabalho), True)

print('\nFALHAS: %d' % len(fails))
sys.exit(1 if fails else 0)
