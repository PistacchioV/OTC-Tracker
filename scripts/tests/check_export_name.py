"""O nome de todo arquivo exportado e um padrao so (mesa, 21/10/2026).

    <Pagina ou tabela> - OTC Tracker - OTC Processing System

`Reference Data - OTC Tracker - OTC Processing System.xlsx`; no /mapping, o
CADASTRO (`API-Bob Reports Links - …`). Cada tela inventava o seu nome — o
titulo da aba com "| OTC Tracker - Sistema de Gestao OTC" (o padrao do
DataTables Buttons), `track-confirmations`, `Unwinds-NDF-FX-20261021` — e o
arquivo na pasta de downloads nao dizia de onde vinha.

Quem decide e o `export-advanced.js`, no clique. O que se prende aqui,
EXECUTANDO o export de verdade (Chromium do playwright, plugins locais do repo,
download capturado):

1. o nome sai da PAGINA (o `<title>` antes do " | ", com o travessao de
   "Intrag — NDF" virando espaco) e ignora o `title`/`filename` que a pagina
   escreva no botao;
2. o titulo DENTRO do arquivo (a linha 1 do Excel, o h1 do Print) e o mesmo
   texto;
3. o `print` carregado DEPOIS do helper (tickets-list, quotes) tambem passa
   por ele;
4. o `data-export-name` da tabela vence a pagina, e a barra vira hifen no
   NOME (no titulo ela fica);
5. o `name` do `otcExportAdvanced` vira o `data-export-name` (os cinco botoes
   o leem tambem);
6. o Advanced Export nasce com o nome do padrao, SEM data, e respeita o nome
   que a pessoa escrever no campo;
7. `otcExportName`/`otcExportTitle` (o /mapping, a Recon FXO) respondem igual.

O que e estatico (nenhuma pagina escreve `title`/`filename`, cada tabela das
paginas com varias tem rotulo) mora no `check_export_padrao.py` §3.
"""
import io
import json
import os
import re
import sys
import tempfile
import zipfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
STATIC = os.path.join(ROOT, 'apps', 'static')
SUF = ' - OTC Tracker - OTC Processing System'

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print(' FAIL playwright nao instalado no venv (pip install playwright && playwright install chromium)')
    sys.exit(1)


def _src(rel):
    return 'file://' + os.path.join(STATIC, rel)


LINHAS = [['26E04610365', 'ABC'], ['21C00000001', 'DEF']]

HTML = """<!doctype html><html><head><meta charset="utf-8">
<title>Intrag — NDF | OTC Tracker - Sistema de Gestão OTC</title></head><body>
<table id="t1"><thead><tr><th>ID</th><th>Txt</th></tr></thead><tbody></tbody></table>
<table id="t2" data-export-name="API/Bob Reports Links"><thead><tr><th>ID</th><th>Txt</th></tr></thead><tbody></tbody></table>
<table id="t3"><thead><tr><th>ID</th><th>Txt</th></tr></thead><tbody></tbody></table>
<ul id="m1"></ul><ul id="m3"></ul>
<script src="%(jq)s"></script>
<script src="%(dt)s"></script>
<script src="%(btn)s"></script>
<script src="%(jszip)s"></script>
<script src="%(html5)s"></script>
<script src="%(adv)s"></script>
<script src="%(print)s"></script>
<script src="%(pdfmake)s"></script>
<script src="%(vfs)s"></script>
<script src="%(bs)s"></script>
<script>
function mk(id) { return $(id).DataTable({ data: %(rows)s, paging: false, order: [] }); }
var d1 = mk('#t1'), d2 = mk('#t2'), d3 = mk('#t3');
// A pagina TENTA dar nome proprio: o helper tem de ignorar.
new $.fn.dataTable.Buttons(d1, { buttons: [
    { extend: 'excel', title: 'Titulo da pagina', filename: 'nome-da-pagina' },
    { extend: 'csv', title: 'Titulo da pagina' },
    { extend: 'pdf', filename: function () { return 'outro'; } },
    { extend: 'print', title: 'Titulo da pagina', autoPrint: false }
] });
new $.fn.dataTable.Buttons(d2, { buttons: [{ extend: 'csv' }, { extend: 'excel' }, { extend: 'print', autoPrint: false }] });
new $.fn.dataTable.Buttons(d3, { buttons: [{ extend: 'csvHtml5' }] });
otcExportAdvanced('#t1', { menu: '#m1' });
otcExportAdvanced('#t3', { menu: '#m3', name: 'NDF Summary - Trade Level' });
window.__go = function (dt, i) { ({ d1: d1, d2: d2, d3: d3 })[dt].button(i).trigger(); };
</script></body></html>""" % {
    'jq': _src('plugins/jquery/jquery.min.js'),
    'dt': _src('plugins/datatables/dataTables.min.js'),
    'btn': _src('plugins/datatables/dataTables.buttons.min.js'),
    'jszip': _src('plugins/datatables/jszip.min.js'),
    'html5': _src('plugins/datatables/buttons.html5.min.js'),
    'adv': _src('js/export-advanced.js'),
    'print': _src('plugins/datatables/buttons.print.min.js'),
    'pdfmake': _src('plugins/datatables/pdfmake.min.js'),
    'vfs': _src('plugins/datatables/vfs_fonts.js'),
    'bs': _src('plugins/bootstrap/bootstrap.bundle.min.js'),
    'rows': json.dumps(LINHAS),
}


def _a1(xlsx_path):
    """O texto da celula A1 (a linha de titulo do Buttons)."""
    with zipfile.ZipFile(xlsx_path) as z:
        xml = z.read('xl/worksheets/sheet1.xml').decode('utf-8')
    m = re.search(r'<c [^>]*r="A1"[^>]*>(.*?)</c>', xml, re.S)
    t = m and re.search(r'<t[^>]*>(.*?)</t>', m.group(1), re.S)
    return t.group(1) if t else None


tmp = tempfile.mkdtemp(prefix='otc-expname-')
harness = os.path.join(tmp, 'h.html')
io.open(harness, 'w', encoding='utf-8').write(HTML)

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(accept_downloads=True)
    erros = []
    pg.on('pageerror', lambda e: erros.append(str(e)))
    pg.goto('file://' + harness)
    check('sem erro de JS no harness', erros, [])

    def baixa(js):
        with pg.expect_download() as dl:
            pg.evaluate(js)
        destino = os.path.join(tmp, dl.value.suggested_filename)
        dl.value.save_as(destino)
        return dl.value.suggested_filename, destino

    print('=== 1-2. A PAGINA, ignorando o nome que ela escreve ===')
    PAG = 'Intrag NDF' + SUF
    nome, arq = baixa("__go('d1', 0)")
    check('Excel: nome do padrao', nome, PAG + '.xlsx')
    check('Excel: a linha de titulo e o mesmo texto', _a1(arq), PAG)
    check('CSV: nome do padrao', baixa("__go('d1', 1)")[0], PAG + '.csv')
    check('PDF: nome do padrao (filename em funcao tambem e ignorado)', baixa("__go('d1', 2)")[0], PAG + '.pdf')

    print('=== 3. O print carregado DEPOIS do helper ===')
    check('o print tambem foi embrulhado',
          pg.evaluate('!!$.fn.dataTable.ext.buttons.print._otcNamed'), True)
    check('...e o copy', pg.evaluate('!!$.fn.dataTable.ext.buttons.copyHtml5._otcNamed'), True)
    with pg.expect_popup() as pop:
        pg.evaluate("__go('d1', 3)")
    janela = pop.value
    janela.wait_for_load_state()
    check('Print: o h1 e o titulo do padrao', janela.evaluate("(document.querySelector('h1')||{}).textContent"), PAG)
    janela.close()

    print('=== 4. O rotulo da TABELA (data-export-name) ===')
    TAB = 'API/Bob Reports Links' + SUF
    check('CSV: a barra vira hifen no nome', baixa("__go('d2', 0)")[0],
          'API-Bob Reports Links' + SUF + '.csv')
    nome, arq = baixa("__go('d2', 1)")
    check('Excel: nome', nome, 'API-Bob Reports Links' + SUF + '.xlsx')
    check('Excel: no titulo a barra fica', _a1(arq), TAB)

    print('=== 5. O name do otcExportAdvanced ===')
    check('vira o data-export-name da tabela',
          pg.evaluate("document.getElementById('t3').getAttribute('data-export-name')"),
          'NDF Summary - Trade Level')
    check('...que os botoes do Buttons leem', baixa("__go('d3', 0)")[0],
          'NDF Summary - Trade Level' + SUF + '.csv')

    print('=== 6. O Advanced Export ===')
    pg.click('#m1 [data-otc-expadv]')
    pg.wait_for_selector('#otcExpAdvModal.show')
    check('o campo nasce com o nome do padrao, sem data', pg.input_value('#xaName'), PAG)
    pg.select_option('#xaFormat', 'excelHtml5')
    nome, arq = baixa("document.getElementById('xaRun').click()")
    check('o arquivo sai com esse nome', nome, PAG + '.xlsx')
    check('...e o titulo do padrao dentro', _a1(arq), PAG)
    pg.wait_for_selector('#otcExpAdvModal', state='hidden')
    pg.click('#m1 [data-otc-expadv]')
    pg.wait_for_selector('#otcExpAdvModal.show')
    pg.fill('#xaName', 'Meu recorte')
    pg.select_option('#xaFormat', 'csvHtml5')
    check('o nome escrito no campo vence o padrao', baixa("document.getElementById('xaRun').click()")[0],
          'Meu recorte.csv')
    pg.wait_for_selector('#otcExpAdvModal', state='hidden')
    pg.click('#m3 [data-otc-expadv]')
    pg.wait_for_selector('#otcExpAdvModal.show')
    check('na tabela com rotulo, o campo nasce com o rotulo', pg.input_value('#xaName'),
          'NDF Summary - Trade Level' + SUF)

    print('=== 7. O helper para o export que nao e do Buttons ===')
    check('otcExportName(rotulo)', pg.evaluate("otcExportName('API/Bob Reports Links')"),
          'API-Bob Reports Links' + SUF)
    check('otcExportTitle(rotulo)', pg.evaluate("otcExportTitle('API/Bob Reports Links')"), TAB)
    check('otcExportName(seletor) le o data-export-name', pg.evaluate("otcExportName('#t2')"),
          'API-Bob Reports Links' + SUF)
    check('otcExportName(seletor sem rotulo) e a pagina', pg.evaluate("otcExportName('#t1')"), PAG)
    check('sem erro de JS no fim', erros, [])
    b.close()

print()
if fails:
    print('FAIL: %d' % len(fails))
    sys.exit(1)
print('ok: tudo passou')
