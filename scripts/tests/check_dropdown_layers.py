"""Menu aberto numa placa fica POR CIMA do resto da placa (mesa, 20/10/2026).

O Export e o Columns do Pending Confirmation abriam POR BAIXO da tabela: dava
para ver as linhas, os botões de ação e a célula selecionada atravessando o
menu, e não dava para ler o que havia nele. O fundo do menu era opaco; o
defeito era de CAMADA.

A placa de vidro (`otc-slab`) desenha a borda de luz (::before) e o brilho
(::after) por pseudo-elemento, e eles iam em `z-index: 0`. Para o conteúdo
ficar por cima, cada FILHO da placa ganhava `position: relative; z-index: 1`
— e com isso o header, o body e o footer do card viravam camadas FECHADAS: o
z-index do menu (2002) só valia dentro do header, e o body, que vem depois no
DOM com o mesmo z-index 1, pintava a tabela inteira por cima dele.

A correção é na raiz: os pseudo-elementos vão a `z-index: -1` (a placa isola
as camadas dela, então o -1 não vaza para trás da tinta) e os filhos ficam
`position: relative` SEM z-index. O que este script prende:

  1. no SCSS e no CSS compilado, nenhum filho de placa volta a ganhar z-index,
     e a borda/brilho estão abaixo do conteúdo;
  2. no Chromium, com o `otc.css` de verdade: um card com o menu aberto no
     header sobre uma tabela no body — cada item do menu é o elemento de cima
     no ponto onde está (o `elementFromPoint`), nos dois temas e no modo
     opaco; e o conteúdo da placa segue por cima do brilho.
"""
import io
import os
import re
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
STATIC = os.path.join(ROOT, 'apps', 'static')
fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '  (got %r, expected %r)' % (got, exp)))
    if not ok:
        fails.append(label)


SCSS = io.open(os.path.join(STATIC, 'scss', 'otc.scss'), encoding='utf-8').read()
CSS = io.open(os.path.join(STATIC, 'css', 'otc.css'), encoding='utf-8').read()

print('=== 1. Borda e brilho abaixo do conteudo; filho de placa sem z-index ===')
for mix in ('otc-rim', 'otc-sheen'):
    corpo = SCSS.split('@mixin %s {' % mix, 1)[1].split('\n}\n', 1)[0]
    check('  %s em z-index -1' % mix, re.search(r'z-index:\s*(-?\d+)', corpo).group(1), '-1')
check('  nenhum "> * { ... z-index: 1 }" no SCSS',
      re.findall(r'>\s*\*\s*\{\s*position:\s*relative;\s*z-index:\s*1;\s*\}', SCSS), [])
check('  nem no CSS compilado',
      re.findall(r'>\s*\*\s*\{\s*position:\s*relative;\s*z-index:\s*1;?\s*\}', CSS), [])

print('=== 2. No Chromium: o menu aberto no header fica por cima do body ===')
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print(' FAIL playwright nao instalado no venv (pip install playwright && playwright install chromium)')
    fails.append('playwright')
    sync_playwright = None

HTML = """<!doctype html><html data-bs-theme="%(theme)s" class="%(cls)s"><head><meta charset="utf-8">
<link rel="stylesheet" href="file://%(static)s/css/vendors.min.css">
<link rel="stylesheet" href="file://%(static)s/css/otc.css">
</head><body style="padding:30px">
<div class="card" style="width:900px">
  <div class="card-header"><div class="dropdown">
    <button class="btn btn-info dropdown-toggle">Export</button>
    <ul class="dropdown-menu show" id="menu" style="position:absolute;top:40px;left:0;display:block">
      <li><a class="dropdown-item" href="#">Copy</a></li><li><a class="dropdown-item" href="#">CSV</a></li>
      <li><a class="dropdown-item" href="#">Excel</a></li><li><a class="dropdown-item" href="#">Print</a></li>
      <li><a class="dropdown-item" href="#">PDF</a></li><li><a class="dropdown-item" href="#">Advanced Export</a></li>
    </ul></div></div>
  <div class="card-body"><div class="table-responsive"><table class="table"><tbody>%(rows)s</tbody></table></div></div>
</div></body></html>"""
ROWS = ''.join('<tr><td><button class="btn btn-danger btn-sm">x</button></td><td>linha %d</td><td>CEM</td></tr>' % i
               for i in range(12))
PROBE = """() => {
  const m = document.getElementById('menu');
  const out = [];
  for (const it of m.querySelectorAll('.dropdown-item')) {
    const r = it.getBoundingClientRect();
    for (const fx of [0.2, 0.8]) {
      const h = document.elementFromPoint(r.left + r.width * fx, r.top + r.height / 2);
      if (!m.contains(h)) out.push(it.textContent + ' coberto por ' + h.tagName + '.' + h.className);
    }
  }
  const td = document.querySelector('.card-body td:nth-child(2)'), rt = td.getBoundingClientRect();
  const cima = document.elementFromPoint(rt.left + 4, rt.top + rt.height / 2);
  return { cobertos: out, conteudo_por_cima: td.contains(cima) };
}"""

if sync_playwright:
    tmp = tempfile.mkdtemp(prefix='ddlayers-')
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={'width': 1100, 'height': 800})
        for theme, cls in (('light', ''), ('dark', ''), ('light', 'is-solid')):
            arq = os.path.join(tmp, '%s-%s.html' % (theme, cls or 'vidro'))
            io.open(arq, 'w', encoding='utf-8').write(HTML % {'theme': theme, 'cls': cls, 'static': STATIC, 'rows': ROWS})
            pg.goto('file://' + arq)
            pg.wait_for_timeout(200)
            r = pg.evaluate(PROBE)
            nome = '%s%s' % (theme, ' opaco' if cls else '')
            check('  [%s] nenhum item do menu coberto' % nome, r['cobertos'], [])
            check('  [%s] o conteudo da placa segue por cima do brilho' % nome, r['conteudo_por_cima'], True)
        b.close()

print()
if fails:
    print('FALHOU (%d):' % len(fails))
    for f in fails:
        print('  -', f)
    sys.exit(1)
print('TUDO OK')
