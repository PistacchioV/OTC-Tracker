# -*- coding: utf-8 -*-
"""Pending Confirmation: a manutencao das 11:30 re-roteia SEM apagar balde.

A manutencao rele os tres bancos, re-roteia cada linha (backlog quando o Trade
Date passa de 12 meses; ok quando o Pending Status resolve; senao pending) e
REESCREVE os tres. A leitura tolerante da tela le falha como banco vazio — e
uma falha lida como vazio, na vespera de uma reescrita, apaga o balde inteiro
sem erro nenhum. Pending e ok se repovoam pelo uso do app; o backlog e so
historia e nao volta.

O que este teste prende:

 1. o CICLO COMPLETO da linha: a que ficou Ok e depois passou de 12 meses sai
    do ok e entra no backlog; a resolvida recente (ainda fisicamente no
    pending) vai para o ok; a viva fica no pending — e nenhuma linha se perde;
 2. a leitura SEM chip de Status soma os TRES bancos (o backlog aparece na
    tela quando o filtro e removido);
 3. leitura que FALHA aborta a manutencao INTEIRA: devolve None, nada e
    reescrito e as linhas continuam onde estavam (o script standalone traduz o
    None em exit 1);
 4. a tela continua melhor-esforco: `_pc_load_rows` sem strict devolve [] na
    falha (a pagina nao pode sumir porque um arquivo do share esta em uso).

Nao encosta em dado real: os bancos vao para um tempdir via R._PC_DB_DIR.
"""
import os
import sys
import tempfile

os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from apps.pages import routes as R                            # noqa: E402
from apps.pages.platform import pending_confirmation as PC    # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label
          + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def tns(cat):
    return sorted(r.get('Trade Number') for r in R._pc_load_rows(cat))


tmp = tempfile.mkdtemp(prefix='pc-maint-')
_old_dbdir = R._PC_DB_DIR
R._PC_DB_DIR = tmp
try:
    print('== 1. o ciclo pending -> ok -> backlog, sem perder linha ==')
    # A que virou Ok ha meses (mora fisicamente no ok) e cujo Trade Date ja
    # passou de 12 meses — a pergunta de 2026-09-03: ela tem de ir ao backlog.
    PC._pc_insert_into('ok', {'Trade Number': 'TN-OK-VELHA', 'Client': 'A',
                              'Trade Date': '10/01/2024', 'Maturity Date': '10/06/2024',
                              'Pending Status': 'Concluded', 'Status': 'Ok'})
    # A resolvida RECENTE ainda fisicamente no pending (o estado entre a
    # resolucao e a proxima manutencao).
    PC._pc_insert_into('pending', {'Trade Number': 'TN-RESOLVIDA', 'Client': 'B',
                                   'Trade Date': '10/08/2026', 'Maturity Date': '10/08/2027',
                                   'Pending Status': 'Concluded'})
    # A viva.
    PC._pc_insert_into('pending', {'Trade Number': 'TN-VIVA', 'Client': 'C',
                                   'Trade Date': '20/08/2026', 'Maturity Date': '20/08/2027',
                                   'Pending Status': 'Pending Original'})

    buckets = PC._pc_run_daily_maintenance(snapshot=False)
    check('a manutencao devolve os tres baldes', sorted(buckets), ['backlog', 'ok', 'pending'])
    check('Ok com mais de 12 meses foi para o BACKLOG', tns('backlog'), ['TN-OK-VELHA'])
    check('a resolvida recente foi para o OK', tns('ok'), ['TN-RESOLVIDA'])
    check('a viva ficou no PENDING', tns('pending'), ['TN-VIVA'])
    total = tns('backlog') + tns('pending') + tns('ok')
    check('nenhuma linha se perdeu na volta completa', len(total), 3)

    print('\n== 2. sem chip de Status, os TRES bancos respondem ==')
    todos = []
    for cat in ('backlog', 'pending', 'ok'):
        todos += R._pc_load_rows(cat)
    check('a soma traz o backlog junto',
          sorted(r.get('Trade Number') for r in todos),
          ['TN-OK-VELHA', 'TN-RESOLVIDA', 'TN-VIVA'])

    print('\n== 3. leitura que falha ABORTA a manutencao — nada e reescrito ==')
    _orig_read = R.duckdb_read

    def _boom(path, *a, **k):
        if 'backlog' in os.path.basename(str(path)):
            raise RuntimeError('IO Error: file is being used by another process')
        return _orig_read(path, *a, **k)

    R.duckdb_read = _boom
    try:
        resultado = PC._pc_run_daily_maintenance(snapshot=False)
    finally:
        R.duckdb_read = _orig_read
    check('a manutencao devolve None (abortada)', resultado, None)
    check('o backlog NAO foi apagado', tns('backlog'), ['TN-OK-VELHA'])
    check('o pending continua intacto', tns('pending'), ['TN-VIVA'])
    check('o ok continua intacto', tns('ok'), ['TN-RESOLVIDA'])

    print('\n== 4. a TELA segue melhor-esforco na mesma falha ==')
    R.duckdb_read = _boom
    try:
        na_falha = R._pc_load_rows('backlog')
    finally:
        R.duckdb_read = _orig_read
    check('sem strict, a falha vira lista vazia (a pagina nao some)', na_falha, [])
    check('e o script standalone traduz o None em exit 1',
          "sys.exit(1)" in open('scripts/pending_confirmation_daily.py', encoding='utf-8').read()
          and 'buckets is None' in open('scripts/pending_confirmation_daily.py', encoding='utf-8').read(),
          True)
finally:
    R._PC_DB_DIR = _old_dbdir

print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
