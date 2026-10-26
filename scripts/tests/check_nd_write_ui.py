#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""As seis telas de New Deals não voltam a pintar antes do servidor (§685).

A varredura de 26/10/2026 achou em NDF Vanilla, FWD Start, Other Publisher,
NDF Comm, Opt FXO e Opt Comm o mesmo desenho do Delete do §684 em quase todo
caminho que grava: `fetch(...).catch(console.warn)` e a grade mudada na hora —
Edit ("Saved" com o 409 do servidor), Confirm, Send (o arquivo na B3 e o status
num PATCH solto), Apply Column e Delete em lote. O comportamento é provado no
navegador; este guarda, ESTÁTICO, prende o que não pode voltar:

  1. toda tela carrega o `nd-write.js` (com `asset_v`);
  2. nenhuma gravação em `/cache` termina num `.catch(... console.warn ...)`
     sem ler a resposta, e o "404 → POST da linha inteira" do Send saiu;
  3. o Send não manda mais o PATCH de `Sent` (quem marca é o servidor);
  4. o status do Confirm/Send é o DADO da célula, não o texto do badge (o
     `missing-counterparty.js` o troca por "Missing Counterparty" no DOM);
  5. o Save de edição NA LINHA (`.btn-row-save-edit`, código morto) não volta;
  6. o Edit procura a linha pelo Client ORIGINAL (`editClient`);
  7. o import do dropzone (`otc-fileupload.js`) desfaz o que não gravou.
"""
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
PAGES = ['ndf-vanilla', 'ndf-fwdstart', 'ndf-otherpublisher', 'ndf-commodities', 'opt-fxo',
         'opt-commodities']
fails = []


def check(label, ok):
    print(('  ok  ' if ok else ' FAIL ') + label)
    if not ok:
        fails.append(label)


def ler(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as fh:
        return fh.read()


js = ler('apps/static/js/nd-write.js')
check('nd-write.js tem os três idiomas', all("%s: {" % l in js for l in ('en', 'br', 'es')))

for pg in PAGES:
    src = ler('apps/templates/pages/new_deals-%s.html' % pg)
    print('== %s' % pg)
    check('carrega o nd-write.js com asset_v', "js/nd-write.js?v={{ asset_v('js/nd-write.js') }}" in src)
    check('sem gravação de cache que só loga a falha',
          not re.search(r"console\.warn\('(Cache (PATCH|bulk-delete|DELETE)|Send POST fallback)", src))
    check('o Send não cria a linha que falta (POST de fallback)', 'PATCH 404 → creating missing cache entry' not in src)
    check("o Send não manda PATCH de Sent", not re.search(r"Status:\s*'Sent'\s*\}\)", src))
    check('status do Confirm/Send pelo dado da célula',
          "$(statusNode).find('.badge').text().trim()" not in src
          and "badge.length ? badge.text().trim() : ''" not in src)
    check('sem o Save de edição na linha', ".btn-row-save-edit', function" not in src)
    check('o Edit acha a linha pelo Client original', "data('editClient')" in src)
    check('usa o helper nas gravações', all(f in src for f in ('otcNdWrite(', 'otcNdFail(', 'otcNdPartial(',
                                                                'otcNdSendIssues(')))

up = ler('apps/static/js/pages/otc-fileupload.js')
print('== otc-fileupload.js')
check('o POST do import que falha tira a linha', 'rowApi.remove();' in up and 'importFalhou(' in up)
check('o PATCH do Amend que falha devolve a linha', 'existingRowApi.data(_antes);' in up)

print()
if fails:
    print('%d FALHA(S)' % len(fails))
    sys.exit(1)
print('TUDO OK')
