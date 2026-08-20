#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_row_action_buttons.py — a spec `.ops-row-act` nas paginas que usam
`.btn-act` (Index B3 Results e Reference Data).

O botao de acao de linha e a geometria mais repetida do app: squircle 32x32
TRAVADO com min/max, `padding:0`, `border-radius:10px !important`, icone Tabler
de 1rem, tooltip COLORIDO e a ordem Confirm/success -> Edit/info ->
Delete/danger. Sao duas paginas irmas — mesma familia de tabela, mesma classe —
e as duas tinham a mesma deriva, que nao aparece no console:

  * o icone levava `.fs-13`, classe do TEMA que e `!important` e por isso vencia
    a regra da pagina: 13 px onde o resto do app usa 16. Era o que fazia esses
    botoes parecerem de outra tela;
  * o tamanho travava so a LARGURA. Uma regra de tema com `min-height` em `.btn`
    deixa um botao mais alto que o vizinho, e 32x34 nao e mais um quadrado
    arredondado;
  * no Index B3 Results o balao era o `title` NATIVO do navegador (cinza, com um
    segundo de atraso) e a pagina nao inicializava tooltip nenhum — o
    "Add a new row" simplesmente nao aparecia.

Le os dois templates; nao escreve nada e nao toca em dado real.
"""
import io
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
os.chdir(ROOT)

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label +
          ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def read(rel):
    return io.open(os.path.join(ROOT, rel), encoding='utf-8').read()


PAGES = {
    'Index B3 Results': 'apps/templates/pages/index-b3-results.html',
    'Reference Data':   'apps/templates/pages/reference-data.html',
}
HTML = {nome: read(p) for nome, p in PAGES.items()}

print('\n== 1. o squircle esta travado nos DOIS eixos ==')
for nome, h in HTML.items():
    bloco = h.split('.btn-act {', 1)[1].split('}', 1)[0]
    for prop in ('width:32px', 'height:32px',
                 'min-width:32px', 'max-width:32px',
                 'min-height:32px', 'max-height:32px',
                 'padding:0', 'border-radius:10px !important'):
        check('%s: .btn-act trava "%s"' % (nome, prop), prop in bloco, True)
    # A borda do `.btn` entraria por fora dos 32 px sem isto.
    check('%s: e conta a borda por dentro' % nome, 'box-sizing:border-box' in bloco, True)

print('\n== 2. o icone tem 1rem, e nao os 13 px do tema ==')
for nome, h in HTML.items():
    # `.fs-13` do tema e `!important`; a regra da pagina so vence com o dela.
    check('%s: a regra do icone e !important' % nome,
          bool(re.search(r'\.btn-act\s*>\s*i\s*\{\s*font-size:\s*1rem\s*!important', h)), True)
    # E o markup nao pode reintroduzir a classe.
    icones = re.findall(r'<i class="ti ti-[\w-]+[^"]*"></i>', h)
    check('%s: nenhum icone de acao carrega fs-13' % nome,
          [i for i in icones if 'fs-13' in i], [])

print('\n== 3. ordem e cores por funcao ==')
# Confirm/success -> Edit/info -> Delete/danger. Trocar a cor de um deles e
# trocar o que a pessoa entende ANTES de ler o tooltip.
ESPERADO = [('btn-success', 'ti-check'), ('btn-info', 'ti-edit'), ('btn-danger', 'ti-trash')]
for nome, h in HTML.items():
    trecho = h.split('function actionBtns', 1)[-1] if 'function actionBtns' in h \
        else h.split('btn-rd-confirm', 1)[0][-400:] + h.split('btn-rd-confirm', 1)[1][:1600]
    got = []
    for m in re.finditer(r'class="btn (btn-\w+) btn-sm rounded-circle btn-act[^"]*"[^>]*>'
                         r'<i class="ti (ti-[\w-]+)"', trecho):
        got.append((m.group(1), m.group(2)))
    check('%s: Confirm -> Edit -> Delete, nas cores certas' % nome, got[:3], ESPERADO)

print('\n== 4. tooltip COLORIDO do Bootstrap, nao o title nativo ==')
for nome, h in HTML.items():
    for cor in ('tooltip-success', 'tooltip-info', 'tooltip-danger'):
        check('%s: usa %s' % (nome, cor), 'data-bs-custom-class="%s"' % cor in h, True)
        # O alinhamento em colunas varia entre as paginas, entao a busca e por
        # regex: o que importa e a regra existir, nao a largura do espaco.
        check('%s: e o CSS de %s existe na pagina' % (nome, cor),
              bool(re.search(r'\.%s\s+\.tooltip-inner' % cor, h)), True)
    # `title=` num botao de acao volta a ser o balao cinza do navegador.
    acoes = re.findall(r'<button class="btn btn-\w+ btn-sm rounded-circle btn-act[^>]*>', h)
    check('%s: nenhum botao de acao com title=' % nome,
          [a for a in acoes if 'title="' in a and 'data-bs-title' not in a], [])

print('\n== 5. o Index B3 Results inicializa tooltip ==')
IB = HTML['Index B3 Results']
# Os <td> sao reescritos a cada redraw do DataTables: instanciar num laco no
# load pegaria so as linhas da primeira pagina, e paginar devolveria botoes
# mudos. Por isso a criacao e DELEGADA.
check('a criacao e delegada no hover',
      bool(re.search(r"\$\(document\)\.on\('mouseenter',\s*'\[data-bs-toggle=\"tooltip\"\]'", IB)), True)
check('e mostra o balao na hora (o mouseenter ja passou)',
      'new bootstrap.Tooltip(this, { trigger: \'hover\' }).show()' in IB, True)
check('e esconde no clique (o botao some da tela)',
      bool(re.search(r"\$\(document\)\.on\('click',\s*'\[data-bs-toggle=\"tooltip\"\]'", IB)), True)

print('\n== 6. o wrapper e o padrao da casa ==')
check('Index B3 Results usa d-flex justify-content-center gap-1',
      'edit-actions-wrap d-flex justify-content-center gap-1' in IB, True)
# A regra estava escrita DUAS vezes no mesmo <style> — a segunda so acrescentava
# o justify-content, e a primeira ficava como ruido contraditorio.
check('e a classe nao esta declarada em duplicidade',
      len(re.findall(r'\.edit-actions-wrap\s*\{', IB)), 1)

print('\n== 7. Save e Cancel dos modais ==')
# Spec: Save `ti-device-floppy`/success + Cancel `ti-x`/SECONDARY. O Cancel
# estava em `danger`, que na tabela ao lado quer dizer Delete.
sv = re.findall(r'<button[^>]*class="btn btn-sm (btn-\w+) btn-act"[^>]*>'
                r'<i class="ti (ti-[\w-]+)"></i></button>', IB)
check('os quatro modais tem o par Cancel/secondary + Save/success',
      sv, [('btn-secondary', 'ti-x'), ('btn-success', 'ti-device-floppy')] * 4)

print('\nFALHAS: %d' % len(fails))
sys.exit(1 if fails else 0)
