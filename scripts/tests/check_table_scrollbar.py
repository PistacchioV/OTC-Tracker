"""A rolagem HORIZONTAL das tabelas é mais grossa que a do resto da casca (§744).

A casca toda tem a barra discreta (`* { scrollbar-width: thin }`), e nas grades
largas ela era difícil de pegar (equipe, 30/10/2026). No Chromium 121+ o
`scrollbar-width` DESLIGA o `::-webkit-scrollbar` do mesmo elemento e o `thin`
não tem meio-termo: o tema devolve o par a `auto` só nos scrollports de tabela
(`.dt-scroll-body`, `.table-responsive`…), onde a altura é a do
`::-webkit-scrollbar` (14 px, polegar de 8 px).

Isso muda TAMBÉM a barra vertical do corpo, e o DataTables (`scrollY`) dá ao
cabeçalho uma folga do tamanho da barra que ele mediu num <div> solto — com a
barra do resto da casca. A folga saía menor que a barra do corpo e, no fim da
rolagem horizontal, o cabeçalho parava 10 px atrás das colunas. O
`excel-filter.js` mede numa sonda com a classe do corpo e corrige a folga, nas
tabelas que já existem quando ele carrega e nas que nascem depois.

O que se prende, EXECUTANDO no Chromium do playwright com o `otc.css` compilado:

1. o scrollport de tabela tem a barra horizontal de 14 px e um <div> qualquer
   segue com a fina (o `scrollbar-width` dele continua `thin`);
2. com `scrollY`, a rolagem máxima do cabeçalho é a do corpo — na tabela criada
   ANTES do helper e na criada DEPOIS;
3. a regra está no `otc.scss` e no `otc.css` compilado.
"""
import io
import json
import os
import re
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
STATIC = os.path.join(ROOT, 'apps', 'static')

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def read(rel):
    return io.open(os.path.join(STATIC, rel), encoding='utf-8').read()


print('\n== 3. a regra no tema e no CSS compilado ==')
SCSS = read('scss/otc.scss')
CSS = read('css/otc.css')
check('o otc.scss lista os scrollports de tabela',
      "$otc-table-scrollports: '.dt-scroll-body, .table-responsive" in SCSS, True)
check('e o otc.css compilado dá 14 px à barra deles',
      bool(re.search(r':is\(\.dt-scroll-body, \.table-responsive[^)]*\)::-webkit-scrollbar \{\s*height: 14px;', CSS)), True)
check('e devolve o par a auto (senão o Chromium ignora o ::-webkit-scrollbar)',
      bool(re.search(r':is\(\.dt-scroll-body[^)]*\) \{\s*scrollbar-width: auto;\s*scrollbar-color: auto;', CSS)), True)

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print(' FAIL playwright ausente no venv')
    sys.exit(1)


def _src(rel):
    return 'file://' + os.path.join(STATIC, rel)


LINHAS = [['L%d' % i] + ['valor %d-%d' % (i, c) for c in range(1, 30)] for i in range(60)]
CABEC = ''.join('<th>Coluna %d</th>' % c for c in range(30))

HTML = """<!doctype html><html data-bs-theme="dark"><head><meta charset="utf-8">
<link rel="stylesheet" href="%(css)s"></head><body style="width:900px">
<div id="solto" style="width:200px;height:60px;overflow:auto"><div style="width:900px;height:20px"></div></div>
<table id="antes" class="table"><thead><tr>%(cab)s</tr></thead><tbody></tbody></table>
<div class="table-responsive" style="width:600px"><table class="table" style="width:1500px"><tbody><tr><td>x</td></tr></tbody></table></div>
<div id="vem-depois"></div>
<script src="%(jq)s"></script>
<script src="%(dt)s"></script>
<script>
var OPTS = { data: %(rows)s, paging: false, order: [], scrollX: true, scrollY: '200px' };
$('#antes').DataTable(OPTS);
</script>
<script src="%(oxf)s"></script>
<script>
$('#vem-depois').append('<table id="depois" class="table"><thead><tr>%(cab)s</tr></thead><tbody></tbody></table>');
$('#depois').DataTable(OPTS);
</script></body></html>""" % {
    'css': _src('css/otc.css'),
    'jq': _src('plugins/jquery/jquery.min.js'),
    'dt': _src('plugins/datatables/dataTables.min.js'),
    'oxf': _src('js/excel-filter.js'),
    'rows': json.dumps(LINHAS),
    'cab': CABEC,
}

MEDE = """id => {
    const t = document.getElementById(id), s = t.closest('.dt-scroll');
    const h = s.querySelector('.dt-scroll-head'), b = s.querySelector('.dt-scroll-body');
    return { hbar: b.offsetHeight - b.clientHeight, vbar: b.offsetWidth - b.clientWidth,
             headMax: h.scrollWidth - h.clientWidth, bodyMax: b.scrollWidth - b.clientWidth };
}"""

tmp = tempfile.mkdtemp(prefix='otc-sb-')
harness = os.path.join(tmp, 'h.html')
io.open(harness, 'w', encoding='utf-8').write(HTML)

with sync_playwright() as p:
    # o headless esconde as barras por padrão (--hide-scrollbars)
    b = p.chromium.launch(ignore_default_args=['--hide-scrollbars'])
    pg = b.new_page(viewport={'width': 1000, 'height': 900})
    erros = []
    pg.on('pageerror', lambda e: erros.append(str(e)))
    pg.goto('file://' + harness)
    pg.wait_for_timeout(600)
    # a largura da tabela muda depois da init (fonte e CSS chegando pelo
    # file://); as páginas reajustam depois de cada draw, e aqui também
    pg.evaluate("() => ['antes', 'depois'].forEach(id => $('#' + id).DataTable().columns.adjust())")
    pg.wait_for_timeout(200)
    check('sem erro de JS no harness', erros, [])

    print('\n== 1. a barra dos scrollports de tabela ==')
    antes = pg.evaluate(MEDE, 'antes')
    depois = pg.evaluate(MEDE, 'depois')
    check('.dt-scroll-body: barra horizontal de 14 px', antes['hbar'], 14)
    check('.table-responsive: barra horizontal de 14 px',
          pg.evaluate("() => { const e = document.querySelector('.table-responsive'); return e.offsetHeight - e.clientHeight; }"), 14)
    check('um <div> fora de tabela segue com a barra fina (scrollbar-width)',
          pg.evaluate("() => getComputedStyle(document.getElementById('solto')).scrollbarWidth"), 'thin')

    print('\n== 2. o cabeçalho rola até o fim junto com o corpo ==')
    check('a tabela tem barra vertical (o caso que pede a folga)', antes['vbar'] > 0, True)
    check('a folga do DataTables é a barra REAL do corpo',
          pg.evaluate("() => ['antes', 'depois'].map(id => $('#' + id).DataTable().settings()[0].oScroll.iBarWidth)"),
          [antes['vbar'], depois['vbar']])
    check('criada ANTES do helper: rolagem máxima do cabeçalho = a do corpo', antes['headMax'], antes['bodyMax'])
    check('criada DEPOIS do helper: rolagem máxima do cabeçalho = a do corpo', depois['headMax'], depois['bodyMax'])
    b.close()

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
