#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_duckdb_standalone.py — as cópias entregues × o motor do app.

Os `scripts/standalone/*.py` são a versão do conversor para rodar numa máquina
SEM o código do OTC Tracker (sem Config, sem import de `apps`, `pip install
duckdb` como requisito único). São VERSIONADOS para ser entregues junto com o
código, e são NOVE cópias de um motor que vive em `apps/pages/json_to_duckdb.py`.

Cópia da mesma regra diverge, e esta já divergiu: por três vezes o motor mudou e
o standalone teve de ser regerado à mão (HANDOFF §331/§333/§334), e na quarta (a
quebra por produto, §336) passou batido — quem o rodasse teria criado os bancos
do desenho VELHO ao lado dos novos, sem erro nenhum.

Este guarda fecha isso: regera em memória com o mesmo gerador e cobra que CADA
arquivo do repo seja byte a byte o resultado. Mexeu no motor e não rodou
`python scripts/build_duckdb_standalone.py`? Reprova aqui, com o comando na
mensagem — em vez de na máquina de quem recebeu o arquivo.

Prova também o que faz deles standalone (nenhuma referência a `apps`, imports só
da biblioteca padrão + duckdb), que o corpo é o do motor a menos da ÚNICA
adaptação prevista, e — o que motiva a repartição — que **a soma das fatias é a
carga completa**: se um script deixar de cobrir a sua parte, o total deixa de
fechar e o teste acusa.
"""
import difflib
import importlib.util
import io
import os
import shutil
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)

GERADOR = os.path.join(ROOT, 'scripts', 'build_duckdb_standalone.py')
PASTA = os.path.join(ROOT, 'scripts', 'standalone')
MOTOR = os.path.join(ROOT, 'apps', 'pages', 'json_to_duckdb.py')

fails = []


def check(label, got, exp=True):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label +
          ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def _ler(path):
    return io.open(path, encoding='utf-8').read()


def _carregar(nome, path):
    spec = importlib.util.spec_from_file_location(nome, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gen = _carregar('build_duckdb_standalone', GERADOR)

# ── 1. as cópias entregues estão em dia com o motor ──────────────────────────
print('\n== 1. as cópias entregues estão em dia com o motor ==')
TMP = tempfile.mkdtemp(prefix='sa-gen-')
check('o gerador roda sem erro', gen.main([TMP]), 0)

esperados = sorted(os.listdir(TMP))
existentes = sorted(f for f in os.listdir(PASTA) if f.endswith('.py'))
check('a pasta tem exatamente os arquivos que o gerador produz',
      existentes, esperados)

for arq in esperados:
    atual = _ler(os.path.join(PASTA, arq)) if arq in existentes else ''
    novo = _ler(os.path.join(TMP, arq))
    if atual != novo:
        d = list(difflib.unified_diff(novo.splitlines(), atual.splitlines(),
                                      'gerado agora', 'scripts/standalone/' + arq,
                                      n=1, lineterm=''))
        print('\n'.join(d[:30]))
        print('        → rode: python scripts/build_duckdb_standalone.py')
    check('%s é byte a byte o que o gerador produz' % arq, atual == novo)

# ── 2. o que faz deles standalone ────────────────────────────────────────────
print('\n== 2. autocontidos: nada de `apps`, nada de Config ==')
_PERMITIDOS = {'argparse', 'datetime', 'duckdb', 'json', 'os', 're', 'sys', 'traceback'}
for arq in existentes:
    s = _ler(os.path.join(PASTA, arq))
    check('%s não importa `apps` nem lê Config' % arq,
          ('from apps' in s or 'apps.pages' in s or 'Config.' in s), False)
    imports = {l.split()[1] for l in s.splitlines()
               if l.startswith('import ') and '.' not in l.split()[1]}
    check('%s só depende da stdlib + duckdb' % arq, imports <= _PERMITIDOS)
check('o cabeçalho avisa que é GERADO',
      all('GERADO por scripts/build_duckdb_standalone.py' in _ler(os.path.join(PASTA, a))
          for a in existentes))

# ── 3. o corpo é o do motor, a menos da adaptação declarada ─────────────────
print('\n== 3. o corpo é o MESMO motor ==')
motor = _ler(MOTOR)
corpo_motor = motor[motor.index('REGISTRY_FILE = '):].rstrip('\n')
check('o seed do app ainda está no motor (a adaptação tem alvo)',
      gen.SEED_APP in corpo_motor)
adaptado = corpo_motor.replace(gen.SEED_APP, gen.SEED_STANDALONE)
# Comparação EXATA contra a constante do gerador, não heurística de palavras:
# o ponto é provar que o gerador não faz mais nada além do que declara.
for arq in existentes:
    s = _ler(os.path.join(PASTA, arq))
    corpo = s[s.index('REGISTRY_FILE = '):s.index('# ── CLI (caminhos fixos')].rstrip('\n')
    check('%s: corpo idêntico ao motor + a adaptação' % arq, corpo == adaptado)

print('\n== 4. a quebra por produto (§336) está nas cópias ==')
_um = _ler(os.path.join(PASTA, '00_completo.py'))
for nome in ('_daily_db_name(rotina_parts', '_tabela_dia(banco_toks',
             '_colisoes', '_drop_legacy_dbs', '_sem_data', 'cache_families'):
    check('o standalone tem o %s de hoje' % nome.split('(')[0], nome in _um)
check('e não sobrou a assinatura antiga',
      '_daily_db_name(familia)' in _um or '_tabela_dia(redundantes' in _um, False)

# ── 5. a SOMA DAS FATIAS é a carga completa ─────────────────────────────────
# É a razão de existir da repartição: se um script deixar de cobrir a sua parte,
# o total deixa de fechar — e o dado que falta some sem erro nenhum.
print('\n== 5. as fatias somam a carga completa (e rodam de verdade) ==')
DATA = tempfile.mkdtemp(prefix='sa-data-')


def w(rel, payload):
    import json as _j
    p = os.path.join(DATA, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    io.open(p, 'w', encoding='utf-8').write(_j.dumps(payload, ensure_ascii=False))


w('cache/new deals/Option/FXO/2026/07/20260727_optfxo.json', [{'Deal': 'D1'}])
w('cache/new deals/NDF/Vanilla/2026/07/20260727_ndfvanilla.json', [{'Deal': 'D2'}])
w('cache/b3 files/Swap/2026/07/03/73760_260703_DFLUXO.json', [{'Cod': 'X'}])
# A rotina que não se ramifica em pastas: o produto sai do NOME do arquivo.
w('cache/daily settlement/2026/07/28/otm-settlement_20260728.json', [{'Trade Id': '9'}])
w('cache/daily settlement/2026/07/28/cognos_20260728.json', [{'Trade Id': '8'}])
w('cache/pending-confirmation/2026/08/27/pending-confirmation_20260827.json', [{'T': '1'}])
# Uma rotina que NENHUM script nomeia: tem de cair no 99_outros.
w('cache/rotina-nova/2026/07/28/coisa_20260728.json', [{'A': '1'}])
w('mappings/bank-name.json', [{'ID': '341', 'NAME': 'BANCO ITAU S/A'}])
w('Subjacente.json', [{'Codigo': 'AAPL34'}])
w('holiday-calendars.json', [{'name': 'ANBIMA', 'file': 'anbima.json'}])
w('anbima.json', [{'date': '2026-01-01', 'title': 'Ano Novo', 'calendar': 'ANBIMA'}])

OUT_FATIAS = os.path.join(DATA, 'db-fatias')
OUT_FULL = os.path.join(DATA, 'db-full')

fatias = [a for a in existentes if a != '00_completo.py']
for arq in fatias:
    mod = _carregar('sa_' + arq[:-3], os.path.join(PASTA, arq))
    rc = mod.main(['--data-dir', DATA, '--out-dir', OUT_FATIAS])
    check('%s roda sem erro' % arq, rc, 0)

mod = _carregar('sa_completo', os.path.join(PASTA, '00_completo.py'))
check('00_completo roda sem erro',
      mod.main(['--data-dir', DATA, '--out-dir', OUT_FULL]), 0)

def _arvore(raiz):
    """Os bancos com o CAMINHO relativo — a pasta db/ espelha a árvore de
    origem, então comparar só o nome do arquivo esconderia a subpasta errada."""
    return sorted(os.path.relpath(os.path.join(dp, f), raiz).replace(os.sep, '/')
                  for dp, _d, fs in os.walk(raiz) for f in fs if f.endswith('.db'))


check('a soma das fatias é EXATAMENTE a carga completa',
      _arvore(OUT_FATIAS), _arvore(OUT_FULL))
_fatias_arvore = _arvore(OUT_FATIAS)
# `rotina-nova` tem UM nível de pasta, então a tag do nome do arquivo vira o
# banco dentro da pasta da rotina — a mesma regra do Daily Settlement.
check('a rotina que nenhum script nomeia foi coberta pelo 99_outros',
      'cache/rotina-nova/coisa.db' in _fatias_arvore)
check('o Daily Settlement quebrou pelo NOME do arquivo, dentro da pasta dele',
      [d for d in _fatias_arvore if d.startswith('cache/daily settlement/')],
      ['cache/daily settlement/cognos.db', 'cache/daily settlement/otm-settlement.db'])
check('a pasta db/ espelha a arvore de cache/',
      [d for d in _fatias_arvore if d.startswith('cache/new deals/')],
      ['cache/new deals/NDF/Vanilla.db', 'cache/new deals/Option/FXO.db'])
check('e ano/mes/dia NAO viram pasta',
      any('/2026/' in d for d in _fatias_arvore), False)
check('os cadastros viraram um banco por JSON, na pasta do JSON',
      [d for d in _fatias_arvore
       if d in ('mappings/bank-name.db', 'Subjacente.db', 'reference_data.db',
                'holiday_calendars.db')],
      ['Subjacente.db', 'holiday_calendars.db', 'mappings/bank-name.db',
       'reference_data.db'])

# Rodar de novo não reconverte nada — a fatia é incremental como a carga toda.
mod = _carregar('sa_nd2', os.path.join(PASTA, '02_1_new_deals.py'))
import contextlib                                              # noqa: E402
_buf = io.StringIO()
with contextlib.redirect_stdout(_buf):
    mod.main(['--data-dir', DATA, '--out-dir', OUT_FATIAS])
check('segunda rodada de uma fatia não reconverte nada',
      'convertidos: 0' in _buf.getvalue())

shutil.rmtree(DATA, ignore_errors=True)
shutil.rmtree(TMP, ignore_errors=True)

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
