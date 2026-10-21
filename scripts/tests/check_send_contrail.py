"""O Send na cor padrão, com o Contrail por cima — na linha E em lote — e o
ritmo dos ícones que giram.

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
  4. no Chromium, com o `otc.css` e o `otc.js` de verdade: o botão fica na cor
     do `btn-primary` em repouso, no voo e no "Sent" — a animação do modelo do
     Contrail (§644) corre por cima: o rótulo some, o avião vai na PONTA do
     preenchimento e o "Sent" aparece; nada vira verde;
  5. todo ícone que gira (`ti-spin`, `ti-loader*`, o refresh `.is-busy`, o
     anel do Bootstrap e o `.otc-spin` das telas) gira no MESMO ritmo, 1,2 s
     por volta — a .8 s/.6 s do rebranding ele parecia "maluco" nas máquinas
     do JP (§644); o refresh ocupado vira o arco do loader e o anel pequeno do
     botão tem o tamanho e a cor do texto (§647);
  6. com o MOVIMENTO REDUZIDO (as animações do Windows desligadas, comum nas
     máquinas do JP) o spinner segue girando no ritmo da casa — o `1ms` do
     tema, num giro infinito, eram mil voltas por segundo: cada quadro num
     ângulo qualquer (§647) — e o enfeite infinito roda uma vez e para;
  7. nenhuma tela declara giro infinito próprio: é o `.otc-spin` do tema.
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
check('  nem o verde do Sent trocando a cor do botão',
      [c for c in ('otc-send-ok', '#10b04a', '--otc-gel:', 'background-color: var(--otc-send') if c in bloco], [])
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

print('=== 4. No Chromium: a cor do botão do começo ao fim, o avião na ponta ===')
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
            check('  [%s] no voo o botão segue na cor do btn-primary' % theme,
                  pg.evaluate(COR, 'lote'), ref)
            ponta = pg.evaluate("""() => { const b = document.getElementById('lote'),
                     f = b.querySelector('.otc-send__fill'), r = b.querySelector('.otc-send__rider');
                     if (!f || !r) return null;
                     const fb = f.getBoundingClientRect(), rb = r.getBoundingClientRect();
                     return {fill: fb.width / b.getBoundingClientRect().width,
                             rider: getComputedStyle(r).opacity, gap: rb.left - fb.right}; }""")
            check('  [%s] o avião vai na PONTA do preenchimento' % theme,
                  bool(ponta) and ponta['fill'] > 0.3 and float(ponta['rider']) > 0.5
                  and -2 <= ponta['gap'] <= 6, True)
            pg.evaluate("otcSend.done(window.__st, true)")
            pg.wait_for_timeout(1400)
            check('  [%s] no Sent o botão segue na cor do btn-primary (nada de verde)' % theme,
                  pg.evaluate(COR, 'lote'), ref)
            check('  [%s] e o Sent aparece' % theme,
                  float(pg.evaluate("getComputedStyle(document.querySelector('#lote .otc-send__done')).opacity")) > 0.9,
                  True)
        b.close()

print('=== 5. Os ícones que giram, num ritmo só ===')
# Todo spinner da casa: o ícone da Tabler, o refresh ocupado, o anel do
# Bootstrap (o do botão e o solto) e o `.otc-spin` das telas (§647).
GIRAM = ['a', 'b', 'c', 'd', 'e', 'f']
SPIN_HTML = (
    '<!doctype html><html><head><link rel="stylesheet" href="file://%s/css/vendors.min.css">'
    '<link rel="stylesheet" href="file://%s/css/otc.css"></head><body>'
    '<button class="cp-run-btn"><i class="ti ti-loader-2 ti-spin" id="a"></i></button>'
    '<button class="btn btn-sm btn-icon is-busy"><i class="ti ti-refresh" id="b"></i></button>'
    '<i class="ti ti-loader" id="c"></i>'
    '<button class="btn btn-primary" id="btn"><span class="spinner-border spinner-border-sm me-1" id="d"></span> Loading</button>'
    '<div class="spinner-border" id="e"></div>'
    '<span class="otc-spin" id="f" style="width:14px;height:14px;border:2px solid;border-radius:50%%"></span>'
    '<div id="deco" style="animation: otc-spin 3s linear infinite">enfeite</div>'
    '<div class="otc-enter" id="ent">entrada</div>'
    '<button class="btn btn-primary btn-row-send is-flying" id="voo"><i class="ti ti-brand-telegram"></i></button>'
    '</body></html>')
DUR = "(ids) => ids.map(i => getComputedStyle(document.getElementById(i)).animationDuration)"
REP = "(ids) => ids.map(i => getComputedStyle(document.getElementById(i)).animationIterationCount)"
if sync_playwright:
    arq = os.path.join(tmp, 'spin.html')
    io.open(arq, 'w', encoding='utf-8').write(SPIN_HTML % (STATIC, STATIC))
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.goto('file://' + arq)
        pg.wait_for_timeout(200)
        check('  todo spinner (Tabler, refresh ocupado, anel do Bootstrap, .otc-spin): 1,2 s por volta',
              pg.evaluate(DUR, GIRAM), ['1.2s'] * len(GIRAM))
        check('  o refresh ocupado vira o ARCO do loader (as setas dele são anti-horárias)',
              pg.evaluate("getComputedStyle(document.getElementById('b'), '::before').content"), '""')
        dim = pg.evaluate("""() => { const d = document.getElementById('d'), b = document.getElementById('btn');
            return [getComputedStyle(d).width, getComputedStyle(d).color === getComputedStyle(b).color]; }""")
        check('  o anel pequeno do botão: 1rem e da cor do texto do botão', dim, ['16px', True])
        b.close()

print('=== 6. Movimento reduzido: o spinner segue girando, o enfeite para ===')
# As máquinas do JP têm as animações do Windows desligadas. O `1ms` do bloco
# do movimento reduzido, num giro infinito, eram mil voltas por segundo: cada
# quadro num ângulo qualquer — o "loucão" que não andava no sentido horário.
if sync_playwright:
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(reduced_motion='reduce')
        pg.goto('file://' + arq)
        pg.wait_for_timeout(200)
        check('  todo spinner fica no ritmo da casa', pg.evaluate(DUR, GIRAM), ['1.2s'] * len(GIRAM))
        check('  e segue infinito', pg.evaluate(REP, GIRAM), ['infinite'] * len(GIRAM))
        check('  a animação infinita que é enfeite roda UMA vez, na hora (não pisca)',
              pg.evaluate(DUR, ['deco']) + pg.evaluate(REP, ['deco']), ['0.001s', '1'])
        check('  a entrada do tema mantém o fade curto dela', pg.evaluate(DUR, ['ent']), ['0.15s'])
        check('  e o voo do Send (a espera da resposta) segue no ritmo dele',
              pg.evaluate(DUR, ['voo']), ['0.8s, 1.2s'])
        b.close()

print('=== 7. Tela não declara giro próprio ===')
# Spinner de tela é o `.otc-spin` (ou o ícone da Tabler): keyframes de giro
# próprio ficavam fora do ritmo da casa (.65 s, .7 s, .8 s, 1 s, 1,1 s) e fora
# da exceção do movimento reduzido.
proprios = []
for nome in sorted(os.listdir(PAGES)):
    if not nome.endswith('.html'):
        continue
    txt = io.open(os.path.join(PAGES, nome), encoding='utf-8').read()
    giram = {m.group(1) for m in re.finditer(r'@keyframes\s+([\w-]+)\s*\{((?:[^{}]|\{[^{}]*\})*)\}', txt)
             if 'rotate' in m.group(2)}
    for m in re.finditer(r'animation\s*:\s*([^;}]*)', txt):
        decl = m.group(1)
        if 'infinite' in decl and (any(re.search(r'\b%s\b' % re.escape(k), decl) for k in giram)
                                   or re.search(r'\botc-spin\b', decl)):
            proprios.append('%s: %s' % (nome, decl.strip()))
check('  nenhum giro infinito declarado na tela', proprios, [])

print()
if fails:
    print('FALHOU (%d):' % len(fails))
    for f in fails:
        print('  -', f)
    sys.exit(1)
print('TUDO OK')
