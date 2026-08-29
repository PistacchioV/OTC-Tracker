#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_nd_cache_dirs.py — quem LÊ o cache do New Deals lê onde ele é ESCRITO.

As três páginas genéricas de NDF gravam em `_GENERIC_ND_PRODUCTS[k]['dir']`:
`NDF/Vanilla`, `NDF/FwdStart` e `NDF/OtherPublisher` — **sem espaço**. `FWD
Start` e `Other Publisher` são os RÓTULOS de tela, e o `_dash_product_label`
traduz um no outro.

Os dois viviam misturados. Um docstring antigo dava como exemplo o caminho
`.../NDF/FWD Start/2026/06/file.json`, e daí a grafia com espaço virou "a outra
grafia de pasta em produção" em três leitores — o `_ndf_fwdstart_cached_keys`,
o card de Confirmations do Monitor e o catálogo `_NDM_CARDS`. Ela nunca existiu:
o app grava em `FwdStart` desde o commit que criou a página. Na dev ela chegou a
existir em disco, com nove arquivos `*_ndffwd_mock.json` postos à mão.

Um diretório que não existe não dá erro — ele casa com nada. O custo é uma
leitura a mais por card e, pior, a impressão de que os dois caminhos são
suportados: quem visse a lista escreveria dado no lugar errado achando que
funciona.

Este guarda prende a direção: **quem lê usa exatamente o que o gerador
escreve**. Ele não proíbe uma pasta de compatibilidade — proíbe uma que o
`_GENERIC_ND_PRODUCTS` não conheça, que é o caso em que a compatibilidade é com
uma pasta imaginária.
"""
import io
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)

fails = []


def check(label, got, exp=True):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label +
          ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


from apps.pages import routes as R                              # noqa: E402
from apps.pages.features.deals_monitor import domain as _dm     # noqa: E402

# ── 1. as pastas que o app ESCREVE ──────────────────────────────────────────
print('\n== 1. as pastas que o gerador de NDF escreve ==')
genericas = {os.path.basename(cfg['dir']) for cfg in R._GENERIC_ND_PRODUCTS.values()}
check('as três páginas genéricas gravam sem espaço no nome',
      sorted(genericas), ['FwdStart', 'OtherPublisher', 'Vanilla'])
# O NDF Commodities não é página genérica — tem constante própria —, mas grava
# na mesma árvore e o catálogo do Monitor também o cita.
escritas = genericas | {os.path.basename(R.NDF_COMM_CACHE_DIR)}
check('e o NDF Commodities, que tem constante própria, também',
      sorted(escritas),
      ['Commodities', 'FwdStart', 'OtherPublisher', 'Vanilla'])
check('nenhuma delas grava numa pasta com espaço',
      [n for n in escritas if ' ' in n], [])

# ── 2. o catálogo de cards do Monitor aponta para elas ──────────────────────
print('\n== 2. o catálogo do Monitor aponta para as pastas reais ==')
_ndf_dirs = [d for c in _dm._NDM_CARDS for d in c['dirs'] if d.startswith('NDF/')]
_orfaos = [d for d in _ndf_dirs if d.split('/', 1)[1] not in escritas]
check('nenhum card de NDF genérico cita pasta que ninguém grava', _orfaos, [])
check('o FWD Start aponta para FwdStart, uma grafia só',
      [c['dirs'] for c in _dm._NDM_CARDS if c['key'] == 'ndf-fwdstart'],
      [('NDF/FwdStart',)])
check('e o Other Publisher, idem',
      [c['dirs'] for c in _dm._NDM_CARDS if c['key'] == 'ndf-otherpublisher'],
      [('NDF/OtherPublisher',)])
check('o conjunto que deriva a LE também',
      sorted(_dm._NDM_GENERIC_NDF_DIRS),
      ['NDF/FwdStart', 'NDF/OtherPublisher', 'NDF/Vanilla'])

# ── 3. nenhum LEITOR monta o caminho com espaço ─────────────────────────────
# Só dentro de `os.path.join(...)` e das tuplas `dirs`: é ali que a string vira
# CAMINHO. O `_NDM_TAXONOMY` guarda o mesmo par `('NDF', 'FWD Start')` como
# RÓTULO de tela — varrendo o arquivo inteiro, ele seria acusado, e a "correção"
# seria trocar o rótulo que a mesa lê.
print('\n== 3. nenhum leitor monta a pasta com espaço ==')
_ALVOS = [
    os.path.join(ROOT, 'apps', 'pages', 'routes.py'),
    os.path.join(ROOT, 'apps', 'pages', 'platform', 'new_deals.py'),
    os.path.join(ROOT, 'apps', 'pages', 'features', 'deals_monitor', 'domain.py'),
    os.path.join(ROOT, 'apps', 'pages', 'features', 'deals_monitor', 'queries.py'),
]
# `'NDF', 'FWD Start'` ou `'NDF/FWD Start'` — o segmento SOZINHO entre aspas.
_RX = re.compile(r"""(['"])NDF\1\s*,\s*(['"])(FWD Start|Other Publisher)\2"""
                 r"""|(['"])NDF/(FWD Start|Other Publisher)\4""")
for alvo in _ALVOS:
    if not os.path.isfile(alvo):
        continue
    achados = []
    for linha in io.open(alvo, encoding='utf-8').read().splitlines():
        if 'os.path.join' not in linha and "'dirs'" not in linha:
            continue
        achados += [m.group(0) for m in _RX.finditer(linha)]
    check('%s não monta a pasta com espaço' % os.path.relpath(alvo, ROOT),
          achados, [])

# O `pretty` é o outro lado: ele traduz a pasta no rótulo, e por isso é o único
# lugar em que as duas grafias convivem de propósito.
print('\n== 4. o rótulo continua sendo traduzido da pasta ==')
_dash = io.open(os.path.join(ROOT, 'apps', 'pages', 'routes.py'), encoding='utf-8').read()
check("o _dash_product_label traduz FwdStart -> 'FWD Start'",
      "'FwdStart': 'FWD Start'" in _dash)
check("e OtherPublisher -> 'Other Publisher'",
      "'OtherPublisher': 'Other Publisher'" in _dash)

# ── 5. e a fatia da conversão segue a mesma pasta ───────────────────────────
print('\n== 5. a fatia da conversão usa a pasta real ==')
from apps.pages.json_to_duckdb import ROTINAS_CACHE            # noqa: E402
_blocos = [b for b, _ in ROTINAS_CACHE if b.startswith('new deals/NDF/')]
check('há uma fatia por produto de NDF, sem a pasta imaginária',
      sorted(_blocos),
      ['new deals/NDF/Commodities', 'new deals/NDF/FwdStart',
       'new deals/NDF/OtherPublisher', 'new deals/NDF/Vanilla'])

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
