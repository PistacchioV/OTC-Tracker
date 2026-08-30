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
# O New Deals é repartido até o PRODUTO, que é a folha da árvore.
w('cache/new deals/NDF/Vanilla/2026/07/20260727_ndfvan.json', [{'Deal': 'D0'}])
w('cache/new deals/NDF/Commodities/2026/07/20260727_ndfc.json', [{'Deal': 'D1'}])
w('cache/new deals/Option/FXO/2026/07/20260727_optfxo.json', [{'Deal': 'D2'}])
w('cache/new deals/Swap/Rates/2026/07/20260727_swr.json', [{'Deal': 'D3'}])
w('cache/new deals/Intrag/NDF/2026/07/20260727_ind.json', [{'Deal': 'D4'}])
# Um PRODUTO novo dentro de uma rotina que tem fatias, e um bloco novo um nível
# acima: a poda do 99_outros é por CAMINHO, então os dois caem lá — enquanto
# `new deals/NDF/Vanilla`, que tem fatia, não.
w('cache/new deals/NDF/Asian/2026/07/20260727_as.json', [{'Deal': 'D5'}])
w('cache/new deals/Equity/2026/07/20260727_eq.json', [{'Deal': 'D6'}])
w('cache/b3 files/Swap/2026/07/03/73760_260703_DFLUXO.json', [{'Cod': 'X'}])
w('cache/b3 files/NDF/2026/07/03/73760_260703_DPOSICAO.json', [{'Cod': 'Y'}])
# Uma subpasta que a dev não tem, para provar o `--bloco`: é o caso que ele
# existe para resolver — a instância com mais pasta do que este repositório.
w('cache/b3 files/NDF/Extra/2026/07/03/73760_260703_EXTRA.json', [{'Cod': 'E'}])
w('cache/b3 files/Option/2026/07/03/73760_260703_DPOSICAO.json', [{'Cod': 'Z'}])
w('cache/b3 files/Operations/2026/07/03/ops_20260703.json', [{'Cod': 'W'}])
# O Daily Settlement, como ele é em produção: os arquivos do dia na MESMA pasta,
# cada um de uma fonte, mais os `.meta` que anotam alguns deles.
w('cache/daily settlement/2026/07/28/otm-settlement_20260728.json', [{'Trade Id': '9'}])
w('cache/daily settlement/2026/07/28/otm-settlement_20260728.meta.json', [{'src': 'x'}])
w('cache/daily settlement/2026/07/28/cognos_20260728.json', [{'Trade Id': '8'}])
w('cache/daily settlement/2026/07/28/cognos_20260728.meta.json', [{'src': 'y'}])
w('cache/daily settlement/2026/07/28/ndf-cockpit_20260728.json', [{'Trade Id': '7'}])
w('cache/daily settlement/2026/07/28/operacoes-jpm_20260728.json', [{'Trade Id': '6'}])
w('cache/daily settlement/2026/07/28/br-onshore-settlements_20260728.json', [{'T': '5'}])
w('cache/daily settlement/2026/07/28/eventos-swap-jpm_20260728.json', [{'T': '4'}])
# O `operations-b3` é o arquivo DERIVADO (o merge de JPM + MGT que a página lê);
# os dois `operacoes-*` são as ORIGENS dele, e cada um tem o seu banco. Confundir
# um com o outro é o erro que a lista de fatias existe para não deixar acontecer.
w('cache/daily settlement/2026/07/28/operations-b3_20260728.json', [{'T': '3'}])
w('cache/daily settlement/2026/07/28/operacoes-mgt_20260728.json', [{'T': '3b'}])
w('cache/daily settlement/2026/07/28/eventos-swap-mgt_20260728.json', [{'T': '4b'}])
w('cache/daily settlement/2026/07/28/latam-desk-position_20260728.json', [{'T': '2b'}])
w('cache/daily settlement/2026/07/28/swap-kapital-hybrids_20260728.json', [{'T': '2c'}])
w('cache/daily settlement/2026/07/28/other-products-summary_20260728.json', [{'T': '2'}])
# Uma tag que NENHUMA fatia nomeia: tem de cair no 99_outros, como a rotina e o
# produto novos. A lista de arquivos do Daily Settlement não é fechada.
w('cache/daily settlement/2026/07/28/relatorio-novo_20260728.json', [{'T': '1'}])
w('cache/pending-confirmation/2026/08/27/pending-confirmation_20260827.json', [{'T': '1'}])
w('cache/payrec/2026/08/27/payrec_20260827.json', [{'V': '1'}])
# As reconciliações, como elas são em disco: uma PASTA por recon e a data no
# NOME do arquivo (não em AAAA/MM/DD), mais o ponteiro `_last` que cada uma
# mantém — ele não é um dia e não pode virar tabela.
w('cache/reconciliation/fxo/2026-08-27.json', [{'V': '2'}])
w('cache/reconciliation/fxo/_last.json', {'date': '2026-08-27'})
w('cache/reconciliation/cgd/2026-08-27.json', [{'V': '3'}])
w('cache/reconciliation/payrec/2026-08-27.json', [{'V': '4'}])
# Uma recon que nenhuma fatia nomeia — a lista não é fechada, e o 99_outros a
# cobre pela mesma poda por caminho das rotinas e dos produtos novos.
w('cache/reconciliation/nova/2026-08-27.json', [{'V': '5'}])
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
check('   e o PRODUTO novo dentro de um bloco com fatia, idem',
      'cache/new deals/NDF/Asian.db' in _arvore(OUT_FATIAS))
check('o New Deals veio repartido até o PRODUTO',
      sorted(d for d in _arvore(OUT_FATIAS) if d.startswith('cache/new deals/')),
      ['cache/new deals/Equity.db', 'cache/new deals/Intrag/NDF.db',
       'cache/new deals/NDF/Asian.db', 'cache/new deals/NDF/Commodities.db',
       'cache/new deals/NDF/Vanilla.db', 'cache/new deals/Option/FXO.db',
       'cache/new deals/Swap/Rates.db'])
check('o Daily Settlement veio repartido por ARQUIVO',
      sorted(d for d in _arvore(OUT_FATIAS) if d.startswith('cache/daily settlement/')),
      ['cache/daily settlement/br-onshore-settlements.db',
       'cache/daily settlement/cognos.db',
       'cache/daily settlement/eventos-swap-jpm.db',
       'cache/daily settlement/eventos-swap-mgt.db',
       'cache/daily settlement/latam-desk-position.db',
       'cache/daily settlement/ndf-cockpit.db',
       'cache/daily settlement/operacoes-jpm.db',
       'cache/daily settlement/operacoes-mgt.db',
       'cache/daily settlement/operations-b3.db',
       'cache/daily settlement/other-products-summary.db',
       'cache/daily settlement/otm-settlement.db',
       'cache/daily settlement/relatorio-novo.db',
       'cache/daily settlement/swap-kapital-hybrids.db'])
# O derivado e as duas origens dele são bancos DISTINTOS — juntá-los faria a
# página Operations B3 e os dois arquivos que a alimentam viverem no mesmo lugar.
check('   e o operations-b3 (derivado) não se confunde com as origens',
      all(('cache/daily settlement/%s.db' % t) in _arvore(OUT_FATIAS)
          for t in ('operations-b3', 'operacoes-jpm', 'operacoes-mgt')))
check('e a tag que nenhuma fatia nomeia caiu no 99_outros',
      'cache/daily settlement/relatorio-novo.db' in _arvore(OUT_FATIAS))
check('e o B3 Files por produto (ali o produto já é o primeiro nível)',
      sorted(d for d in _arvore(OUT_FATIAS) if d.startswith('cache/b3 files/')),
      ['cache/b3 files/NDF.db', 'cache/b3 files/NDF/Extra.db',
       'cache/b3 files/Operations.db', 'cache/b3 files/Option.db',
       'cache/b3 files/Swap.db'])
# Cada reconciliação tem o SEU banco — e, por isso, a sua fatia: um escopo é
# sempre o caminho do banco que ele produz.
check('cada reconciliação tem o seu banco',
      sorted(d for d in _arvore(OUT_FATIAS) if d.startswith('cache/reconciliation/')),
      ['cache/reconciliation/cgd.db', 'cache/reconciliation/fxo.db',
       'cache/reconciliation/nova.db', 'cache/reconciliation/payrec.db'])
check('   e a recon que nenhuma fatia nomeia caiu no 99_outros',
      'cache/reconciliation/nova.db' in _arvore(OUT_FATIAS))
check('   e o histórico de Pay/Rec continua num banco à parte do cache da recon',
      'cache/payrec.db' in _arvore(OUT_FATIAS))

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
# Pelo SUFIXO, nunca pelo número: a numeração desloca a cada bloco que entra ou
# sai do ROTINAS_CACHE, e este teste não é sobre ela.
_UMA = next(f for f in sorted(os.listdir(CONVERT)) if f.endswith('_b3_files_ndf.py'))
rc, saida = _rodar(_UMA, os.path.join(DATA, 'y'), ['--only', 'daily'])
check('a fatia de bloco RECUSA --only (tem uma etapa so)', rc != 0)

# A janela: o padrão vale, e sai declarado.
rc, saida = _rodar(_UMA, os.path.join(DATA, 'z'), ['--dry-run'])
check('a fatia de bloco anuncia a janela padrão de 12 meses',
      'janela : arquivo-dia a partir de' in saida and '(12 meses)' in saida)

# `--bloco` desce mais um nível e SUBSTITUI o escopo — é o que reparte onde a
# instância tem mais pasta do que a dev, sem um arquivo novo.
_OUT_BL = os.path.join(DATA, 'bloco')
rc, saida = _rodar(_UMA, _OUT_BL, ['--meses', '0', '--bloco', 'Extra'])
check('--bloco desce mais um nivel', rc, 0)
check('   e converte SO aquele bloco', _arvore(_OUT_BL),
      ['cache/b3 files/NDF/Extra.db'])
check('   e o escopo impresso é o efetivo, não o da fatia',
      'cache/b3 files/NDF/Extra' in saida)
rc, saida = _rodar('01_cadastros.py', os.path.join(DATA, 'bl2'), ['--bloco', 'X'])
check('a fatia de cadastros nao aceita --bloco', rc != 0)
rc, saida = _rodar('01_cadastros.py', os.path.join(DATA, 'z2'), ['--dry-run'])
check('e a de cadastros NAO anuncia janela nenhuma', 'janela :' in saida, False)

shutil.rmtree(DATA, ignore_errors=True)

# ── 5. todo arquivo do Daily Settlement tem a SUA fatia ─────────────────────
# Ali quem separa os produtos é o NOME do arquivo, e a lista de nomes é o
# `_DS_IMPORTS` do routes — o registro dos cards de importação. Um card novo
# fica coberto pelo `99_outros` (a rede de segurança faz o seu trabalho), e é
# justamente por isso que a falta não aparece: o dado converte, só que na fatia
# de todo mundo, que é a que ninguém quer esperar. Foi o que aconteceu com o
# `operacoes-mgt`, o `eventos-swap-mgt`, o `latam-desk-position` e o
# `swap-kapital-hybrids`.
print('\n== 5. todo card de importação do Daily Settlement tem fatia própria ==')
from apps.pages import routes as R                                  # noqa: E402
_tags_ds = sorted({s['json'] for s in R._DS_IMPORTS if s.get('json')})
_fatias_ds = {b.split('/')[-1] for b, _ in motor.ROTINAS_CACHE
              if b.startswith('daily settlement/')}
check('nenhum arquivo do Daily Settlement depende do 99_outros',
      [t for t in _tags_ds if t not in _fatias_ds], [])
# O contrário não vale: `operations-b3` e `other-products-summary` são
# DERIVADOS — a rotina os grava sem que exista um card de importação para eles.
check('   e os derivados também têm fatia',
      all(t in _fatias_ds for t in ('operations-b3', 'other-products-summary')))

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
