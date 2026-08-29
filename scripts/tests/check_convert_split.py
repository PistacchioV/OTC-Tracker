#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_convert_split.py — os DOIS splits da carga, e a soma de cada um.

A conversão JSON → DuckDB tem duas entradas, e as duas são repartidas em fatias
para várias pessoas rodarem ao mesmo tempo:

  - `scripts/convert/`     usa o `Config` do app (roda DENTRO do checkout);
  - `scripts/standalone/`  não usa nada do app (roda numa máquina sem o código).

O que este guarda prende:

  1. **os dois splits têm as MESMAS fatias.** A lista de rotinas mora no motor
     (`ROTINAS_CACHE`) justamente para isso; escrita em cada script, uma rotina
     acrescentada num lado ficaria coberta só pelo `99_outros` do outro — e a
     diferença apareceria como uma fatia que demora muito mais do que a irmã,
     nunca como erro.

  2. **a soma das fatias é a carga completa.** É a razão de existir da
     repartição: se um script deixar de cobrir a sua parte, o dado que falta
     some sem erro nenhum.

  3. **as fatias não se pisam.** Duas que escrevessem no mesmo banco
     corromperiam o dado só quando rodassem em paralelo — o caso que ninguém
     reproduz depois.

  4. **o `01_cadastros` não recebe `--meses`** (nenhum daqueles JSONs tem data
     para cortar) e **as fatias de rotina não recebem `--only`** (têm uma etapa
     só).

Não encosta em dado real: origem e destino vão para diretórios temporários.
"""
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)

GERADOR = os.path.join(ROOT, 'scripts', 'build_convert_split.py')
CONVERT = os.path.join(ROOT, 'scripts', 'convert')
STANDALONE = os.path.join(ROOT, 'scripts', 'standalone')
MOTOR = os.path.join(ROOT, 'apps', 'pages', 'json_to_duckdb.py')

fails = []


def check(label, got, exp=True):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label +
          ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def _carregar(nome, path):
    spec = importlib.util.spec_from_file_location(nome, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


motor = _carregar('_motor_jtd', MOTOR)

# ── 1. os dois splits têm as mesmas fatias ──────────────────────────────────
print('\n== 1. os dois splits têm as MESMAS fatias ==')


def _slug(nome):
    return ''.join(c if c.isalnum() else '_' for c in nome.lower()).strip('_')


esperado = ['00_completo.py', '01_cadastros.py']
esperado += ['02_%d_%s.py' % (i, _slug(f))
             for i, (f, _) in enumerate(motor.ROTINAS_CACHE, start=1)]
esperado.append('99_outros.py')

for pasta, nome in ((CONVERT, 'scripts/convert'), (STANDALONE, 'scripts/standalone')):
    achados = sorted(f for f in os.listdir(pasta) if f.endswith('.py'))
    check('%s tem uma fatia por bloco do motor' % nome, achados, sorted(esperado))

# E as do `convert/` são BYTE A BYTE o que o gerador produz — elas são geradas
# justamente porque escritas à mão envelheceriam no dia em que um bloco entrasse
# no ROTINAS_CACHE, que é a mudança que ninguém lembra de propagar.
_gen = _carregar('build_convert_split', GERADOR)
TMP = tempfile.mkdtemp(prefix='cv-gen-')
check('o gerador do convert/ roda sem erro', _gen.main([TMP]), 0)
for arq in sorted(os.listdir(TMP)):
    atual = io.open(os.path.join(CONVERT, arq), encoding='utf-8').read() \
        if os.path.isfile(os.path.join(CONVERT, arq)) else ''
    novo = io.open(os.path.join(TMP, arq), encoding='utf-8').read()
    if atual != novo:
        print('        → rode: python scripts/build_convert_split.py')
    check('%s é byte a byte o que o gerador produz' % arq, atual == novo)
shutil.rmtree(TMP, ignore_errors=True)

# A rotina citada no 99_outros de cada split é a mesma lista, e ela vem do motor.
_cobertas = [f for f, _ in motor.ROTINAS_CACHE]
for pasta, nome in ((CONVERT, 'scripts/convert'), (STANDALONE, 'scripts/standalone')):
    s = io.open(os.path.join(pasta, '99_outros.py'), encoding='utf-8').read()
    check('o 99_outros de %s exclui exatamente as rotinas cobertas' % nome,
          all(("'%s'" % f) in s for f in _cobertas))

# ── 2/3. a soma das fatias é a carga completa, e elas não se pisam ──────────
print('\n== 2. as fatias somam a carga completa (e rodam de verdade) ==')
DATA = tempfile.mkdtemp(prefix='cv-data-')


def w(rel, payload):
    p = os.path.join(DATA, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    io.open(p, 'w', encoding='utf-8').write(json.dumps(payload, ensure_ascii=False))


# Datas dentro da janela padrão não importam aqui: as fatias rodam com
# `--meses 0` porque o que se compara é a ÁRVORE de bancos, não o recorte.
w('cache/new deals/NDF/Vanilla/2026/07/20260727_ndfvan.json', [{'Deal': 'D0'}])
w('cache/new deals/Option/FXO/2026/07/20260727_optfxo.json', [{'Deal': 'D1'}])
w('cache/new deals/Swap/Rates/2026/07/20260727_swr.json', [{'Deal': 'D2'}])
w('cache/new deals/Intrag/NDF/2026/07/20260727_ind.json', [{'Deal': 'D3'}])
# Um bloco NOVO dentro de uma rotina que TEM fatias: a poda do 99_outros é por
# CAMINHO, então ele cai lá — e `new deals/NDF`, que tem fatia, não.
w('cache/new deals/Equity/2026/07/20260727_eq.json', [{'Deal': 'D4'}])
w('cache/b3 files/Swap/2026/07/03/73760_260703_DFLUXO.json', [{'Cod': 'X'}])
w('cache/b3 files/NDF/2026/07/03/73760_260703_DPOSICAO.json', [{'Cod': 'Y'}])
w('cache/b3 files/Option/2026/07/03/73760_260703_DPOSICAO.json', [{'Cod': 'Z'}])
w('cache/b3 files/Operations/2026/07/03/ops_20260703.json', [{'Cod': 'W'}])
w('cache/daily settlement/2026/07/28/otm-settlement_20260728.json', [{'Trade Id': '9'}])
w('cache/pending-confirmation/2026/08/27/pending-confirmation_20260827.json', [{'T': '1'}])
w('cache/payrec/2026/08/27/payrec_20260827.json', [{'V': '1'}])
w('cache/reconciliation/2026/08/27/recon_20260827.json', [{'V': '2'}])
# Uma rotina que NENHUM script nomeia: tem de cair no 99_outros.
w('cache/rotina-nova/2026/07/28/coisa_20260728.json', [{'A': '1'}])
w('mappings/bank-name.json', [{'ID': '341', 'NAME': 'BANCO ITAU S/A'}])
w('holiday-calendars.json', [{'name': 'ANBIMA', 'file': 'anbima.json'}])
w('anbima.json', [{'date': '2026-01-01', 'title': 'Ano Novo', 'calendar': 'ANBIMA'}])

OUT_FATIAS = os.path.join(DATA, 'db-fatias')
OUT_FULL = os.path.join(DATA, 'db-full')


def _rodar(arq, out_dir, extra=()):
    """Em SUBPROCESSO: cada fatia é um `__main__` próprio, e é assim que a
    pessoa a roda. Importar e chamar `run()` pularia justamente o que o
    arquivo tem de seu."""
    cmd = [sys.executable, os.path.join(CONVERT, arq),
           '--data-dir', DATA, '--out-dir', out_dir] + list(extra)
    p = subprocess.run(cmd, capture_output=True, text=True, env=dict(os.environ))
    return p.returncode, (p.stdout + p.stderr)


def _sem_janela(arq):
    """As asserções comparam a ÁRVORE, não o recorte. Na janela padrão as datas
    fixas dos arquivos de teste sairiam dela sozinhas quando o relógio passasse
    de doze meses — um teste que quebra no futuro sem ninguém ter mexido."""
    s = io.open(os.path.join(CONVERT, arq), encoding='utf-8').read()
    return ['--meses', '0'] if "'daily'" in s or '00_completo' in arq else []


fatias = [f for f in esperado if f != '00_completo.py']
for arq in fatias:
    rc, saida = _rodar(arq, OUT_FATIAS, _sem_janela(arq))
    if rc:
        print(saida[-1200:])
    check('%s roda sem erro' % arq, rc, 0)

rc, saida = _rodar('00_completo.py', OUT_FULL, ['--meses', '0'])
if rc:
    print(saida[-1200:])
check('00_completo roda sem erro', rc, 0)


def _arvore(raiz):
    return sorted(os.path.relpath(os.path.join(dp, f), raiz).replace(os.sep, '/')
                  for dp, _d, fs in os.walk(raiz) for f in fs if f.endswith('.db'))


check('a soma das fatias é EXATAMENTE a carga completa',
      _arvore(OUT_FATIAS), _arvore(OUT_FULL))
check('a rotina que nenhum script nomeia foi coberta pelo 99_outros',
      'cache/rotina-nova/coisa.db' in _arvore(OUT_FATIAS))
# A poda do 99_outros é por CAMINHO: um bloco novo DENTRO de uma rotina que já
# tem fatias cai nele. Por primeiro nível, `new deals` estaria excluída inteira
# e o bloco novo ficaria sem conversor nenhum — sem erro, sem banco.
check('e o bloco novo dentro de uma rotina com fatias, também',
      'cache/new deals/Equity.db' in _arvore(OUT_FATIAS))
check('as duas rotinas grandes vieram repartidas por bloco',
      sorted(d for d in _arvore(OUT_FATIAS) if d.startswith('cache/b3 files/')),
      ['cache/b3 files/NDF.db', 'cache/b3 files/Operations.db',
       'cache/b3 files/Option.db', 'cache/b3 files/Swap.db'])

print('\n== 3. as fatias não escrevem no mesmo banco ==')
# Cada fatia sozinha, num destino próprio: o conjunto de bancos de uma não pode
# encostar no da outra. Duas fatias no mesmo arquivo só corromperiam o dado
# quando rodassem em paralelo — o defeito que ninguém reproduz depois.
donos = {}
sobreposto = []
for arq in fatias:
    _out = os.path.join(DATA, 'so-' + arq[:-3])
    _rodar(arq, _out, _sem_janela(arq))
    for db in _arvore(_out):
        if db in donos:
            sobreposto.append((db, donos[db], arq))
        donos[db] = arq
check('nenhum banco é reivindicado por duas fatias', sobreposto, [])

print('\n== 4. os argumentos de cada fatia ==')
rc, saida = _rodar('01_cadastros.py', os.path.join(DATA, 'x'), ['--meses', '0'])
check('o 01_cadastros RECUSA --meses (nao ha data para cortar)', rc != 0)
check('   e diz por quê', 'unrecognized arguments: --meses' in saida)
_UMA = '02_1_new_deals_ndf.py'
rc, saida = _rodar(_UMA, os.path.join(DATA, 'y'), ['--only', 'daily'])
check('a fatia de bloco RECUSA --only (tem uma etapa so)', rc != 0)

# A janela: o padrão vale, e sai declarado.
rc, saida = _rodar(_UMA, os.path.join(DATA, 'z'), ['--dry-run'])
check('a fatia de bloco anuncia a janela padrão de 12 meses',
      'janela : arquivo-dia a partir de' in saida and '(12 meses)' in saida)

# `--bloco` desce mais um nível e SUBSTITUI o escopo — é o que reparte onde a
# instância tem mais pasta do que a dev, sem um arquivo novo.
_OUT_BL = os.path.join(DATA, 'bloco')
rc, saida = _rodar(_UMA, _OUT_BL, ['--meses', '0', '--bloco', 'Vanilla'])
check('--bloco desce mais um nivel', rc, 0)
check('   e converte SO aquele bloco', _arvore(_OUT_BL),
      ['cache/new deals/NDF/Vanilla.db'])
check('   e o escopo impresso é o efetivo, não o da fatia',
      'cache/new deals/NDF/Vanilla' in saida)
rc, saida = _rodar('01_cadastros.py', os.path.join(DATA, 'bl2'), ['--bloco', 'X'])
check('a fatia de cadastros nao aceita --bloco', rc != 0)
rc, saida = _rodar('01_cadastros.py', os.path.join(DATA, 'z2'), ['--dry-run'])
check('e a de cadastros NAO anuncia janela nenhuma', 'janela :' in saida, False)

shutil.rmtree(DATA, ignore_errors=True)

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
