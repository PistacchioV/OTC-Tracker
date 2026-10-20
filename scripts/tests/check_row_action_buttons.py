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
# Desde o rebranding (19/10/2026) a geometria e SO do tema (§8 confere a regra
# `table td .btn.btn-act` do otc.scss). O que se cobra das paginas e nao
# redeclarar o botao: uma regra `.btn-act {` no <style> voltaria a ser a deriva
# que este guarda nasceu para pegar (32x34, icone de 13 px).
for nome, h in HTML.items():
    check('%s: a pagina nao redeclara o .btn-act' % nome,
          bool(re.search(r'(^|[\s,}])\.btn-act\s*\{', h)), False)

print('\n== 2. o icone tem 1rem, e nao os 13 px do tema ==')
for nome, h in HTML.items():
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
        # A cor do balao e do tema (otc.scss §6g, um `@each` por cor).
        check('%s: e o CSS de %s existe no tema' % (nome, cor),
              bool(re.search(r'\.%s \.tooltip-inner' % cor, read('apps/static/css/otc.css'))), True)
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
# Rodape de MODAL: Cancel `ti-x`/DANGER + Save `ti-device-floppy`/success — e
# o par do Add/Edit Row do Intrag DCE Option, a referencia de 2026-09-04. O
# Cancel/SECONDARY e o do modo de edicao NA LINHA (spec .ops-row-act), onde o
# vermelho ao lado quer dizer Delete; no rodape do modal nao ha Delete ao lado.
sv = re.findall(r'<button[^>]*class="btn btn-sm (btn-\w+) btn-act"[^>]*>'
                r'<i class="ti (ti-[\w-]+)"></i></button>', IB)
check('os quatro modais tem o par Cancel/danger + Save/success',
      sv, [('btn-danger', 'ti-x'), ('btn-success', 'ti-device-floppy')] * 4)

print('\n== 8. o padrao vale para o APP INTEIRO (2026-09-04) ==')
# A regra GLOBAL do tema (otc.scss, §6b) e o que faz o squircle alcancar toda
# tabela — inclusive as que nao escrevem regra nenhuma (as quatro do swapchar).
# Ela trava so a GEOMETRIA: `display` sem !important, senao venceria o .d-none
# com que varias telas escondem um botao condicional.
VR = read('apps/static/scss/otc.scss')
bloco = VR.split('table td .btn.btn-act {', 1)[1].split('}', 1)[0] if 'table td .btn.btn-act {' in VR else ''
for prop in ('width: 32px !important', 'height: 32px !important',
             'min-width: 32px !important', 'max-width: 32px !important',
             'min-height: 32px !important', 'max-height: 32px !important',
             'padding: 0 !important', 'border-radius: 10px !important',
             'box-sizing: border-box !important'):
    check('otc.scss: a regra global trava "%s"' % prop, prop in bloco, True)
check('otc.scss: `display` NAO leva !important (o .d-none tem de vencer)',
      'display: inline-flex;' in bloco and 'display: inline-flex !important' not in bloco, True)
check('otc.scss: alcanca as quatro familias de classe',
      all(sel in VR for sel in ('table td .btn.rounded-circle,', 'table td .btn.ops-row-act,',
                                'table td .btn.sc-row-act,', 'table td .btn.btn-act {')), True)
check('otc.scss: o icone e 1rem !important',
      bool(re.search(r'table td \.btn\.btn-act > i \{ font-size: 1rem !important', VR)), True)
# E o markup de TODA celula de acao usa os icones canonicos: Edit e `ti-edit`
# (nao `ti-pencil`), Confirm e `ti-check` (nao `ti-circle-check`), e nenhum
# botao de linha e o `btn-default btn-icon` cinza do tema.
import glob
# `email.html`/`email-details.html` sao a demo do tema comprado, nao telas do app.
DEMO = ('email.html', 'email-details.html')
fontes = sorted(f for f in glob.glob('apps/templates/pages/*.html') + glob.glob('apps/static/js/pages/*.js')
                if os.path.basename(f) not in DEMO)
FAM = r'(?:rounded-circle|ops-row-act|sc-row-act|btn-act)'
ruins = []
for f in fontes:
    for m in re.finditer(r'<(?:a|button)\b[^>]*class="[^"]*\b' + FAM + r'\b[^"]*"[^>]*>\s*<i class="ti (ti-[\w-]+)', read(f)):
        if m.group(1) in ('ti-pencil', 'ti-circle-check'):
            ruins.append((f, m.group(1)))
check('nenhuma celula de acao usa ti-pencil / ti-circle-check', ruins, [])
cinzas = [f for f in fontes if re.search(r'btn-default btn-icon btn-sm[^>]*>\s*<i class="ti ti-(?:eye|edit|check|trash)', read(f))]
check('nenhum botao de linha e o btn-default btn-icon cinza', cinzas, [])
# A COR de cada botao e semantica e vale no app inteiro: Confirm/Approve
# success, Edit info, Delete danger, Send primary, Save success, Cancel
# secondary. Duas telas novas nasceram com o Edit em `btn-warning` (laranja) e
# nada acusou — o guarda so olhava as duas paginas de referencia. Agora ele
# varre todas: a cor errada e a unica coisa que a mesa ve antes de clicar.
CORES = {'confirm': 'btn-success', 'approve': 'btn-success', 'edit': 'btn-info',
         'delete': 'btn-danger', 'send': 'btn-primary', 'save': 'btn-success',
         'cancel': 'btn-secondary'}
fora = []
for f in fontes:
    txt = read(f)
    for m in re.finditer(r'class="btn (btn-[\w-]+) btn-sm[^"]*\bbtn-row-(\w+)\b', txt):
        cor, papel = m.group(1), m.group(2)
        esperada = CORES.get(papel)
        if esperada and cor != esperada:
            fora.append((os.path.basename(f), 'btn-row-' + papel, cor, esperada))
check('a cor de cada botao de linha e a semantica, em TODA pagina', fora, [])

# A referencia: a celula de acao do Intrag DCE Option.
DCE = read('apps/templates/pages/intrag-dce-option.html')
check('Intrag DCE Option: Edit/info ti-edit · Delete/danger ti-trash · Approve/success ti-check · Send/primary ti-brand-telegram',
      re.findall(r'btn (btn-\w+) btn-sm rounded-circle btn-row-\w+" href="#" title="\w+"><i class="ti (ti-[\w-]+)"', DCE),
      [('btn-info', 'ti-edit'), ('btn-danger', 'ti-trash'), ('btn-success', 'ti-check'), ('btn-primary', 'ti-brand-telegram')])

print('\nFALHAS: %d' % len(fails))
sys.exit(1 if fails else 0)
