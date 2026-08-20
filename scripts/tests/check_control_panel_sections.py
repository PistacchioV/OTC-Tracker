#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_control_panel_sections.py — as SEIS secoes do Control Panel.

O painel cresceu ate virar uma parede de dez cards debaixo de um titulo so.
Hoje sao seis secoes (File-Saving, Intraday, Settlement Reporting, Pending
Confirmation, Economic Affirmation e Reference Data), e a secao de cada card e
o DOM: o cabecalho, a `.row.cp-cards` logo abaixo dele, e os cards dentro dela.

O que este script prova:

  1. todo card de `_CONTROL_PANEL_CARDS` esta no template UMA vez, e todo card
     do template esta no registro - card fora do registro e rotina sem dono no
     /page-access, e registro sem card e um checkbox que nao libera nada;
  2. todo card cai dentro de uma secao, e toda secao tem card - cabecalho vazio
     e meia tela de titulo, e card fora de secao nunca some para quem nao tem
     acesso a ele;
  3. os tres rotulos de cada secao (`label`/`title`/`desc`) existem nos TRES
     arquivos de traducao - a chave que falta aparece na tela em ingles cru;
  4. a ORDEM do registro e a da tela, que e o que faz a checklist do
     /page-access se parecer com a pagina que ela libera;
  5. o JS de acesso NAO tem mais o mapa card -> grupo escrito a mao (ele
     envelhecia calado quando um card mudava de secao) e esconde o `.cp-reveal`,
     nao a coluna: a coluna empilhada carrega dois cards, e esconder a coluna
     levava junto o card que a pessoa PODE ver.

Le o template e os JSONs versionados; nao escreve nada.
"""
import io
import json
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', os.path.join(ROOT, 'scripts', 'tests'))

from apps.pages import routes as R                            # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label +
          ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


TPL = io.open(os.path.join(ROOT, 'apps', 'templates', 'pages', 'control-panel.html'),
              encoding='utf-8').read()

# ── A estrutura: cabecalho -> .row.cp-cards -> cards ─────────────────────────
# Cada secao vai do seu `data-cp-hdr` ate o proximo (ou ate o fim do
# page_content). Os cards da secao sao os `data-cp-card` desse trecho.
CORPO = TPL.split('{% block page_content %}', 1)[1].split('{% endblock page_content %}', 1)[0]
marcas = [(m.start(), m.group(1)) for m in re.finditer(r'data-cp-hdr="([^"]+)"', CORPO)]
secoes = []
for i, (pos, key) in enumerate(marcas):
    fim = marcas[i + 1][0] if i + 1 < len(marcas) else len(CORPO)
    trecho = CORPO[pos:fim]
    secoes.append({
        'key': key,
        'lang': (re.search(r'data-lang="cp-sec-([a-z]+)-label"', trecho) or [None, ''])[1]
                if re.search(r'data-lang="cp-sec-([a-z]+)-label"', trecho) else '',
        'cards': re.findall(r'data-cp-card="([^"]+)"', trecho),
        'row': 'class="row g-3 g-xl-4 mb-4 cp-cards"' in trecho,
        'trecho': trecho,
    })

print('\n== 1. registro x template ==')
reg = [c['id'] for c in R._CONTROL_PANEL_CARDS]
no_tpl = re.findall(r'data-cp-card="([^"]+)"', CORPO)
check('o registro tem 13 cards', len(reg), 13)
check('nenhum card repetido no template', sorted(no_tpl), sorted(set(no_tpl)))
check('todo card do registro esta no template', sorted(set(reg) - set(no_tpl)), [])
check('todo card do template esta no registro', sorted(set(no_tpl) - set(reg)), [])
check('e todo id tem um token de acesso',
      sorted(t for t in R._CP_CARD_TOKENS) ==
      sorted('/control-panel#' + i for i in reg), True)

print('\n== 2. toda secao tem card, todo card tem secao ==')
check('o painel tem SEIS secoes', [s['key'] for s in secoes],
      ['filesaving', 'intraday', 'reporting', 'pendingconf', 'affirmation', 'refdata'])
for s in secoes:
    check('%s: tem a .row de cards' % s['key'], s['row'], True)
    check('%s: nao esta vazia' % s['key'], bool(s['cards']), True)
check('a soma dos cards das secoes e o template inteiro',
      sorted(c for s in secoes for c in s['cards']), sorted(no_tpl))

print('\n== 3. os rotulos das secoes nos TRES idiomas ==')
LANGS = {}
for lang in ('en', 'br', 'es'):
    LANGS[lang] = json.load(io.open(
        os.path.join(ROOT, 'apps', 'static', 'data', 'translations', '%s.json' % lang),
        encoding='utf-8'))
for s in secoes:
    sufixo = s['lang']
    check('%s: usa data-lang cp-sec-<x>-label' % s['key'], bool(sufixo), True)
    if not sufixo:
        continue
    for parte in ('label', 'title', 'desc'):
        chave = 'cp-sec-%s-%s' % (sufixo, parte)
        check('   %s existe nos tres idiomas' % chave,
              sorted(l for l in LANGS if not str(LANGS[l].get(chave, '')).strip()), [])
        check('   %s aparece no template' % chave,
              'data-lang="%s"' % chave in s['trecho'], True)

print('\n== 4. a ordem do registro e a da tela ==')
# A checklist do /page-access sai desta lista; fora de ordem, quem concede o
# acesso procura o card numa lista que nao se parece com a pagina.
check('o registro esta na ordem em que os cards aparecem',
      reg, no_tpl)

print('\n== 5. o JS de acesso por card ==')
JS = TPL.split('Per-user card access', 1)[1]
check('nao ha mais mapa card -> grupo escrito a mao', 'CP_GROUP' in JS, False)
check('esconde o .cp-reveal do card, nao a coluna',
      "(card.closest('.cp-reveal') || card).hidden = true" in JS, True)
check('e so depois esconde a coluna que ficou vazia',
      ".cp-cards > [class*=\"col-\"]" in JS, True)
check('a secao do cabecalho sai do DOM (a .row logo abaixo)',
      "hdr.nextElementSibling" in JS and "cp-cards" in JS, True)

# A coluna empilhada e o unico lugar com dois cards; e por causa dela que
# esconder a COLUNA era errado.
empilhadas = re.findall(r'<div class="col[^"]*flex-column[^"]*"[^>]*>((?:(?!<div class="col)[\s\S])*)',
                        CORPO)
check('ha uma coluna empilhada, e ela tem dois cards',
      [len(re.findall(r'data-cp-card="', b)) for b in empilhadas], [2])

print('\nFALHAS: %d' % len(fails))
sys.exit(1 if fails else 0)
