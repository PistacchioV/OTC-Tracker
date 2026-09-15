"""O Excel exportado nao pode transformar um ID em numero (§477).

O `excelHtml5` do DataTables Buttons grava como NUMERO todo texto que casa
`/^-?\\d+(\\.\\d+)?([eE]-?\\d+)?$/`. Um contrato B3 no formato `26E04610365`
casa — para o Excel e 26 x 10^4610365, que nao cabe em numero nenhum, e a
celula abre como `#NULL!`. So a letra E dispara (`26G…`, `21C…` sao texto),
entao a mesma planilha sai certa numa linha e quebrada na outra, e o dado
nunca teve `#NULL!` — ele nasce dentro do Excel de quem abre o arquivo. Foram
tres rodadas de "sanitizar o #NULL! do dado" (§138, §383, §399) antes de
alguem olhar o TIPO da celula.

O mesmo caminho perde digito: o Excel guarda 15 algarismos, e um ID de 16+
so de digitos volta com o fim zerado.

O que se prende, EXECUTANDO o export de verdade (Chromium do playwright,
plugins locais do repo, download capturado e o `sheet1.xml` lido do zip):

1. `26E04610365` sai como TEXTO (`inlineStr`), nao como `<c t="n">`;
2. um ID de 16 digitos sai como texto; um de ate 15 continua numero;
3. o que E numero de verdade (`1,234.56`, `42`) continua numero — o patch
   nao pode "consertar" a coluna de valor;
4. o `customize` proprio da pagina (a Recon FXO tem um) continua rodando,
   DEPOIS do patch;
5. o botao do Advanced Export (extend por nome, `excelHtml5`) passa pelo
   mesmo caminho.

E, por AST de template, que toda pagina que carrega o `buttons.html5` carrega
o `export-advanced.js` DEPOIS dele — o Buttons copia o `action` na construcao
do botao, e o patch mora no export-advanced: pagina que o carregasse antes,
ou nao carregasse, exportaria o `#NULL!` de novo sem erro nenhum.
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
PAGINAS = os.path.join(ROOT, 'apps', 'templates', 'pages')
PARTIALS = os.path.join(ROOT, 'apps', 'templates', 'partials')

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


# ── 1. A ordem de carga nos templates ───────────────────────────────────────
def _ordem(texto):
    """(linha do buttons.html5, linha do export-advanced) ou None para cada um."""
    def pos(marca):
        m = re.search(marca, texto)
        return texto[:m.start()].count('\n') if m else None
    return pos(r'buttons\.html5\.min\.js'), pos(r'js/export-advanced\.js')


partial_ok = _ordem(io.open(os.path.join(PARTIALS, 'tools-assets-js.html'), encoding='utf-8').read())
check('partial tools-assets-js: export-advanced DEPOIS do buttons.html5',
      partial_ok[0] is not None and partial_ok[1] is not None and partial_ok[1] > partial_ok[0], True)

sem_patch, antes = [], []
for nome in sorted(os.listdir(PAGINAS)):
    if not nome.endswith('.html'):
        continue
    texto = io.open(os.path.join(PAGINAS, nome), encoding='utf-8').read()
    if 'tools-assets-js' in texto:
        continue                                   # o partial ja foi conferido
    b, e = _ordem(texto)
    if b is None:
        continue                                   # pagina sem Excel
    if e is None:
        sem_patch.append(nome)
    elif e < b:
        antes.append(nome)
check('toda pagina com buttons.html5 carrega o export-advanced.js', sem_patch, [])
check('…e carrega DEPOIS do buttons.html5', antes, [])

# Versionamento: sem `?v=` o navegador do JPM segura o JS anterior e o patch
# nao chega (foi o §170 com o otc-fileupload.js).
sem_v = []
for pasta in (PAGINAS, PARTIALS):
    for nome in sorted(os.listdir(pasta)):
        if not nome.endswith('.html'):
            continue
        texto = io.open(os.path.join(pasta, nome), encoding='utf-8').read()
        # `*?`: o primeiro `js/export-advanced.js` do atributo — o segundo e o
        # argumento do proprio asset_v, e casar nele diria que falta o que ha.
        for m in re.finditer(r'src="[^"]*?js/export-advanced\.js([^"]*)"', texto):
            if 'asset_v' not in m.group(1):
                sem_v.append(nome)
                break
check('todo include do export-advanced.js leva asset_v', sem_v, [])

# ── 2. O export de verdade ──────────────────────────────────────────────────
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print(' FAIL playwright nao instalado no venv (pip install playwright && playwright install chromium)')
    fails.append('playwright')
    sys.exit(1)

LINHAS = [
    ['26E04610365', '1,234.56', 'texto', '42'],       # o contrato com E
    ['26G53382860', '-9.10', 'x', '7'],                # contrato com outra letra
    ['1234567890123456', '0.00', 'y', '123456789012345'],   # 16 digitos vs 15
    ['0848007678', '5', 'z', '1e5'],                   # zero a esquerda (o Buttons ja trata)
]


def _src(rel):
    return 'file://' + os.path.join(STATIC, rel)


HTML = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<table id="t"><thead><tr><th>ID</th><th>Valor</th><th>Txt</th><th>N</th></tr></thead><tbody></tbody></table>
<script src="%(jq)s"></script>
<script src="%(dt)s"></script>
<script src="%(btn)s"></script>
<script src="%(jszip)s"></script>
<script src="%(html5)s"></script>
<script src="%(adv)s"></script>
<script>
window.__custRan = 0;
var dt = $('#t').DataTable({ data: %(rows)s, paging: false, order: [] });   // na ordem das linhas
new $.fn.dataTable.Buttons(dt, { buttons: [
    { extend: 'excel', title: 'T', customize: function (x) { window.__custRan += 1;
        window.__custSawText = $('row c[t="inlineStr"] t', x.xl.worksheets['sheet1.xml']).map(function(){return this.textContent;}).get(); } },
    { extend: 'excelHtml5', title: 'T2' }
] });
window.__go = function (i) { dt.button(i).trigger(); };
</script></body></html>""" % {
    'jq': _src('plugins/jquery/jquery.min.js'),
    'dt': _src('plugins/datatables/dataTables.min.js'),
    'btn': _src('plugins/datatables/dataTables.buttons.min.js'),
    'jszip': _src('plugins/datatables/jszip.min.js'),
    'html5': _src('plugins/datatables/buttons.html5.min.js'),
    'adv': _src('js/export-advanced.js'),
    'rows': json.dumps(LINHAS),
}


def _celulas(xlsx_path):
    """{ref: (tipo, texto)} do sheet1.xml — tipo 'n' (numero), 'inlineStr' ou ''."""
    with zipfile.ZipFile(xlsx_path) as z:
        xml = z.read('xl/worksheets/sheet1.xml').decode('utf-8')
    out = {}
    for m in re.finditer(r'<c ([^>]*)>(.*?)</c>', xml, re.S):
        attrs, corpo = m.group(1), m.group(2)
        ref = re.search(r'\br="([A-Z]+\d+)"', attrs).group(1)
        t = re.search(r'\bt="([^"]+)"', attrs)
        txt = re.search(r'<(?:v|t)[^>]*>(.*?)</(?:v|t)>', corpo, re.S)
        out[ref] = ((t.group(1) if t else ''), (txt.group(1) if txt else ''))
    return out


tmp = tempfile.mkdtemp(prefix='otc-xlsx-')
harness = os.path.join(tmp, 'h.html')
io.open(harness, 'w', encoding='utf-8').write(HTML)

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(accept_downloads=True)
    erros = []
    pg.on('pageerror', lambda e: erros.append(str(e)))
    pg.goto('file://' + harness)
    check('patch aplicado no load (sonda)', pg.evaluate('!!window.__otcExcelIdsPatched'), True)
    check('sem erro de JS no harness', erros, [])

    with pg.expect_download() as dl:
        pg.evaluate('__go(0)')
    caminho = os.path.join(tmp, 'a.xlsx')
    dl.value.save_as(caminho)
    cel = _celulas(caminho)
    # linha 1 = titulo, 2 = cabecalho, 3.. = dados
    check('26E04610365 sai como TEXTO', cel.get('A3'), ('inlineStr', '26E04610365'))
    check('26G53382860 segue texto', cel.get('A4'), ('inlineStr', '26G53382860'))
    check('16 digitos sai como TEXTO', cel.get('A5'), ('inlineStr', '1234567890123456'))
    check('15 digitos continua NUMERO', cel.get('D5')[1] if cel.get('D5') else None, '123456789012345')
    check('15 digitos: tipo nao e texto', (cel.get('D5') or ('?',))[0] != 'inlineStr', True)
    check('zero a esquerda segue texto (regra do Buttons)', cel.get('A6'), ('inlineStr', '0848007678'))
    check('1,234.56 continua NUMERO', (cel.get('B3') or ('?',))[0] != 'inlineStr', True)
    check('42 continua NUMERO', (cel.get('D3') or ('?', ''))[1], '42')
    check('1e5 (numero legitimo em notacao cientifica) vira texto — e ID neste app',
          cel.get('D6'), ('inlineStr', '1e5'))
    check('customize da pagina rodou UMA vez', pg.evaluate('window.__custRan'), 1)
    check('…e DEPOIS do patch (ja viu o 26E como texto)',
          '26E04610365' in pg.evaluate('window.__custSawText || []'), True)

    with pg.expect_download() as dl2:
        pg.evaluate('__go(1)')
    caminho2 = os.path.join(tmp, 'b.xlsx')
    dl2.value.save_as(caminho2)
    cel2 = _celulas(caminho2)
    check('extend excelHtml5 (o do Advanced Export) tambem', cel2.get('A3'), ('inlineStr', '26E04610365'))
    check('segundo clique nao empilha customize', pg.evaluate('window.__custRan'), 1)
    b.close()

print()
if fails:
    print('FAIL: %d' % len(fails))
    sys.exit(1)
print('ok: tudo passou')
