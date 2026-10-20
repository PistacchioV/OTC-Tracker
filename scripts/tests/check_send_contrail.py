"""O Send na cor padrão, com o Contrail por cima — na linha E em lote.

Duas decisões da mesa (20/10/2026, HANDOFF §641/§642):

  * o Send da LINHA fica com a cor dele (o `btn-primary` da regra dos botões
    de ação): a cápsula de tinta escura com avião limão destoava das outras
    três ações. A animação (voo, rastro, o verde do "Sent", o vermelho do
    erro) corre POR CIMA da cor padrão;
  * o Send EM LOTE da barra (as linhas marcadas) tem a MESMA animação, pela
    classe `otc-send-batch` — sem o visual de pílula do `.btn-send`.

O que este script prende:

  1. no SCSS, o Contrail não pinta o botão em repouso (nem fundo nem cor com
     `!important`), e o `.otc-send-batch` está no bloco da animação e FORA da
     regra da pílula;
  2. o `SEND_SEL` do otc.js inclui o lote, e o rótulo em elemento vira
     rótulo da animação;
  3. todo Send em lote das telas leva a classe — os `btnSend*`, o Send do New
     Deals (`data-table-confirm-selected`), o do Swap VCP e o do Other
     Publisher. Tela nova com Send em lote cai aqui;
  4. no Chromium, com o `otc.css` e o `otc.js` de verdade: em repouso o botão
     tem a cor do `btn-primary`; o voo esconde o rótulo; no "Sent" o botão
     inteiro fica verde.
"""
import io
import os
import re
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
STATIC = os.path.join(ROOT, 'apps', 'static')
PAGES = os.path.join(ROOT, 'apps', 'templates', 'pages')
fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '  (got %r, expected %r)' % (got, exp)))
    if not ok:
        fails.append(label)


SCSS = io.open(os.path.join(STATIC, 'scss', 'otc.scss'), encoding='utf-8').read()
JS = io.open(os.path.join(STATIC, 'js', 'otc.js'), encoding='utf-8').read()

print('=== 1. O tema não pinta o Send ===')
ini = SCSS.index('// 6c. SEND')
bloco = SCSS[ini:SCSS.index('@property --otc-fill-w', ini)]
cabeca = bloco[bloco.index('{') + 1: bloco.index('> i, > svg')]
check('  o bloco da animação não força fundo nem cor em repouso',
      re.findall(r'^\s*(background|color)\s*:', cabeca, re.M), [])
check('  nem a tinta escura / avião limão', [c for c in ('#14161b', '#d4f000', 'otc-send-ink', 'otc-send-lime') if c in bloco], [])
seletor = bloco[bloco.index('.btn-row-send'):bloco.index('{')]
check('  o lote está no bloco da animação', '.otc-send-batch' in seletor, True)
pilula = re.search(r'\n(\.btn-send, \.otc-send[^{]*)\{', bloco)
check('  e FORA da regra da pílula (a barra fica como está)',
      bool(pilula) and 'otc-send-batch' not in pilula.group(1), True)

print('=== 2. O otc.js arma o lote ===')
sel = re.search(r"var SEND_SEL = '([^']*)'", JS)
check('  o SEND_SEL inclui .otc-send-batch', bool(sel) and '.otc-send-batch' in sel.group(1), True)
check('  o rótulo em elemento (span data-lang) vira rótulo da animação',
      "n.classList.add('otc-send__label')" in JS, True)

print('=== 3. Todo Send em lote das telas leva a classe ===')
faltam, achados = [], 0
for nome in sorted(os.listdir(PAGES)):
    if not nome.endswith('.html'):
        continue
    s = io.open(os.path.join(PAGES, nome), encoding='utf-8').read()
    for m in re.finditer(r'<button\b[^>]*>', s):
        tag = m.group(0)
        if re.search(r'\bid="(btnSend\w*|vcpBulkSend|nopSendBatch)"', tag):
            achados += 1
            if 'otc-send-batch' not in tag:
                faltam.append('%s: %s' % (nome, tag[:90]))
    # O mesmo atributo é um CONFIRM (ti-check) no Pending Confirmation: só é
    # Send o que leva o avião.
    for m in re.finditer(r"confirmBtn\.className = '([^']*)'", s):
        if re.search(r"confirmBtn\.innerHTML = '<i class=\"ti ti-brand-telegram", s):
            achados += 1
            if 'otc-send-batch' not in m.group(1):
                faltam.append('%s: o Send do New Deals' % nome)
check('  os Sends em lote encontrados (19 em 20/10/2026)', achados >= 19, True)
check('  nenhum sem a classe', faltam, [])

print('=== 4. No Chromium: cor padrão em repouso, verde no Sent ===')
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print(' FAIL playwright nao instalado no venv')
    fails.append('playwright')
    sync_playwright = None

HTML = """<!doctype html><html data-bs-theme="%(theme)s"><head><meta charset="utf-8">
<link rel="stylesheet" href="file://%(static)s/css/vendors.min.css">
<link rel="stylesheet" href="file://%(static)s/css/otc.css">
</head><body style="padding:30px">
<button class="btn btn-sm btn-primary bg-gradient btn-toolbar-all otc-send-batch" id="lote" type="button">
  <i class="ti ti-brand-telegram me-1"></i><span data-lang="x">Send</span> (<span id="n">2</span>)</button>
<button class="btn btn-sm btn-primary bg-gradient btn-toolbar-all" id="ref" type="button">Ref</button>
<table class="table"><tbody><tr><td>
  <button class="btn btn-primary btn-sm rounded-circle btn-row-send" id="linha"><i class="ti ti-brand-telegram"></i></button>
  <button class="btn btn-info btn-sm rounded-circle btn-row-edit"><i class="ti ti-edit"></i></button>
</td></tr></tbody></table>
<script src="file://%(static)s/js/otc.js"></script>
</body></html>"""
COR = "id => getComputedStyle(document.getElementById(id)).backgroundColor"

if sync_playwright:
    tmp = tempfile.mkdtemp(prefix='contrail-')
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={'width': 900, 'height': 400})
        for theme in ('light', 'dark'):
            arq = os.path.join(tmp, theme + '.html')
            io.open(arq, 'w', encoding='utf-8').write(HTML % {'theme': theme, 'static': STATIC})
            pg.goto('file://' + arq)
            pg.wait_for_timeout(300)
            ref = pg.evaluate(COR, 'ref')
            check('  [%s] o lote em repouso tem a cor do btn-primary' % theme, pg.evaluate(COR, 'lote'), ref)
            check('  [%s] a linha em repouso tem a cor do btn-primary' % theme, pg.evaluate(COR, 'linha'), ref)
            pg.evaluate("window.__st = otcSend.start(document.getElementById('lote'))")
            pg.wait_for_timeout(700)
            rotulo = pg.evaluate("""() => [...document.querySelectorAll('#lote .otc-send__label')]
                                   .map(e => getComputedStyle(e).opacity)""")
            check('  [%s] no voo o rótulo (span e texto solto) some' % theme,
                  bool(rotulo) and all(float(o) < 0.5 for o in rotulo), True)
            check('  [%s] o contador da página segue no mesmo nó' % theme,
                  pg.evaluate("document.getElementById('n').textContent"), '2')
            pg.evaluate("otcSend.done(window.__st, true)")
            pg.wait_for_timeout(1400)
            check('  [%s] no Sent o botão inteiro fica verde' % theme,
                  pg.evaluate(COR, 'lote'), 'rgb(16, 176, 74)')
        b.close()

print()
if fails:
    print('FALHOU (%d):' % len(fails))
    for f in fails:
        print('  -', f)
    sys.exit(1)
print('TUDO OK')
