"""O Export da casa e a linha de filtro sob `scrollX` (§461, §462).

Duas coisas que quebram SEM ERRO NENHUM, e por isso so aparecem quando alguem
da mesa reclama:

1. EXPORT ESCRITO A MAO. O padrao e o DataTables Buttons com os cinco itens
   (Copy · CSV · Excel · Print · PDF) e o Advanced Export no fim. Um CSV montado
   com `new Blob([...], {type:'text/csv'})` diverge do resto do app no primeiro
   acento, no primeiro separador e no primeiro campo com ponto-e-virgula — e
   nasce sem Excel, sem Print e sem PDF, que foi a reclamacao do Trade Level.

2. LINHA DE FILTRO ESCOPADA NO `thead`. Com `scrollX`, o DataTables CLONA o
   cabecalho para o topo rolante e deixa o original debaixo do clone, fora do
   alcance do ponteiro. `$('#tabela thead .filtro input')` liga so o original:
   a pessoa digita no clone e NADA acontece, sem uma linha no console. A
   delegacao tem de ser no CONTAINER (`dt.table().container()`), que cobre as
   duas copias — e o Clear Filters tem de limpar as duas.

O terceiro item e o NOME DO ARQUIVO: quando a mesma pagina exporta mais de uma
tabela, cada chamada precisa de `name` proprio, senao as duas baixam com o
titulo da pagina e ninguem sabe qual e qual.

Como o `check_modal_standard`, este script NAO exige que o app inteiro ja esteja
no padrao: ele PRENDE AS LISTAS abaixo. Tela nova fora do padrao falha; tela da
lista que for corrigida tambem falha, pedindo para sair dela. E assim que a
divida para de crescer sem obrigar a pagar tudo de uma vez.
"""
import io
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
PAGINAS = os.path.join(ROOT, 'apps', 'templates', 'pages')
JS = os.path.join(ROOT, 'apps', 'static', 'js', 'pages')

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def fontes():
    """Todo template de pagina e todo JS de pagina, por nome curto."""
    for pasta, ext in ((PAGINAS, '.html'), (JS, '.js')):
        if not os.path.isdir(pasta):
            continue
        for a in sorted(os.listdir(pasta)):
            if a.endswith(ext):
                yield a, io.open(os.path.join(pasta, a), encoding='utf-8').read()


# ── 1. Export escrito a mao ─────────────────────────────────────────────────
# Pagina que monta o proprio CSV E tem DataTable: o Buttons estava ali do lado.
CSV_NA_MAO = {
    'reconciliation-fxo.html',   # Csv/Copy proprios convivendo com o Advanced Export
    # A grade virou DataTable (o funil de Excel), e o Export segue o do §556:
    # cadastro exporta toda celula como TEXTO e SEM trim ('C ' e codigo B3), o
    # que o Buttons nao faz. Cadastro nao tem dia, entao nao ha Advanced Export.
    'mapping.html',
}

print('=== 1. Export escrito a mao (§461) ===')
achados = set()
for nome, texto in fontes():
    mao = (re.search(r"""type\s*:\s*['"]text/csv""", texto)
           or re.search(r"""download\s*=\s*[^;\n]*\.csv""", texto))
    if mao and '.DataTable(' in texto:
        achados.add(nome)
check('  so as telas conhecidas montam CSV a mao', sorted(achados), sorted(CSV_NA_MAO))

# ── 2. Linha de filtro escopada no thead de tabela scrollX ──────────────────
# Aqui NAO ha lista de excecao de proposito: e um bug silencioso, nao uma divida
# de estilo. Tela com `scrollX: true` nao pode ligar o filtro em `#id thead`.
print('=== 2. Filtro por coluna sob scrollX (§462) ===')
presos = []
for nome, texto in fontes():
    if not re.search(r'scrollX\s*:\s*true', texto):
        continue
    for m in re.finditer(r"""['"]#[\w-]+\s+thead[^'"]*['"]""", texto):
        if 'filter' in m.group(0).lower():
            presos.append('%s %s' % (nome, m.group(0)))
    for _m in re.finditer(r"""\.find\(\s*['"]thead['"]\s*\)\s*\.on\(""", texto):
        presos.append("%s .find('thead').on(" % nome)
check('  nenhum filtro ligado no thead de tabela scrollX', sorted(presos), [])

# O jeito certo, provado nas duas telas que ja passaram por isso.
for nome, marca in (('other-products-swap-vcp.html', 'vcp'), ('reconciliation-cgd.html', 'cgd')):
    texto = io.open(os.path.join(PAGINAS, nome), encoding='utf-8').read()
    check('  %s delega no container da tabela' % nome,
          bool(re.search(r'\.table\(\)\.container\(\)', texto)), True)
    check('  %s tem Clear Filters alcancando as duas copias' % nome,
          bool(re.search(r'container\(\)\)[\s\S]{0,400}?\.find\([^)]*filter', texto, re.I)), True)

# ── 3. O NOME do arquivo exportado (mesa, 21/10/2026) ──────────────────────
# Um padrao so, em toda tabela que exporta:
#     <Pagina ou tabela> - OTC Tracker - OTC Processing System
# Quem decide e o `export-advanced.js`, no clique dos cinco botoes. Cada tela
# inventava o seu (o titulo da aba com "| OTC Tracker - Sistema de Gestao OTC",
# `track-confirmations`, `Unwinds-NDF-FX-20261021`...), e um `title`/`filename`
# escrito na pagina hoje seria ignorado — codigo que mente. O
# `check_export_name.py` EXECUTA o export e confere o arquivo baixado.
print('=== 3. Nome do arquivo (padrao da casa) ===')
SUFIXO = ' - OTC Tracker - OTC Processing System'
XA_SRC = io.open(os.path.join(ROOT, 'apps', 'static', 'js', 'export-advanced.js'), encoding='utf-8').read()
check('  o helper define o sufixo do padrao', ("var EXPORT_SUFFIX = '%s';" % SUFIXO) in XA_SRC, True)
check('  ...e embrulha os cinco botoes',
      "var NAMED_BUTTONS = ['copyHtml5', 'csvHtml5', 'excelHtml5', 'pdfHtml5', 'print'];" in XA_SRC, True)
check('  ...de novo no options.dt (o print que carrega depois)',
      "jQuery(document).on('options.dt', patchNames);" in XA_SRC, True)
check('  ...e expoe o nome para o export que nao e do Buttons',
      'window.otcExportName = exportFile;' in XA_SRC and 'window.otcExportTitle = exportTitle;' in XA_SRC, True)
check('  o Advanced Export nao carimba mais data no nome',
      'flatDay(' not in XA_SRC and 'todayIso(' not in XA_SRC, True)

TIPOS = ('copy', 'copyHtml5', 'csv', 'csvHtml5', 'excel', 'excelHtml5', 'pdf', 'pdfHtml5', 'print')


def _objeto(texto, pos):
    """O objeto `{...}` que contem `pos`, so o primeiro nivel (sub-objetos achatados)."""
    ini = texto.rfind('{', 0, pos)
    prof, i = 0, ini
    while i < len(texto):
        if texto[i] == '{':
            prof += 1
        elif texto[i] == '}':
            prof -= 1
            if prof == 0:
                break
        i += 1
    corpo = texto[ini + 1:i]
    for _ in range(4):
        corpo = re.sub(r'\{[^{}]*\}', '{}', corpo)
    return corpo


escreve = []
for nome, texto in fontes():
    for m in re.finditer(r"""extend\s*:\s*(['"]?)(\w+)\1""", texto):
        if m.group(1) and m.group(2) not in TIPOS:
            continue
        corpo = _objeto(texto, m.start())
        for k in ('title', 'filename'):
            if re.search(r'\b%s\s*:' % k, corpo):
                escreve.append('%s:%d %s' % (nome, texto[:m.start()].count('\n') + 1, k))
check('  nenhuma pagina escreve title/filename num botao de export', escreve, [])

# Pagina com MAIS DE UMA tabela: cada uma diz qual e (`data-export-name`), senao
# as duas baixam com o mesmo nome. "Trade Level" existe nos dois Summaries, por
# isso a pagina vem junto.
ROTULOS = {
    'ndf-summary.html': ['NDF Summary - Settlement Summary', 'NDF Summary - Trade Level'],
    'other-products-summary.html': ['Other Products Summary - Settlement Summary',
                                    'Other Products Summary - Trade Level'],
    'index-b3-results.html': ['Index B3 Results - Underlying Assets', 'Index B3 Results - VCP',
                              'Index B3 Results - Domain', 'Index B3 Results - Swap Index'],
    'intrag-dce-swap.html': ['Intrag DCE Swap - Legs', 'Intrag DCE Swap - Cashflows'],
}
for nome, rotulos in sorted(ROTULOS.items()):
    texto = io.open(os.path.join(PAGINAS, nome), encoding='utf-8').read()
    check('  %s nomeia cada tabela' % nome,
          [r for r in rotulos if ('data-export-name="%s"' % r) not in texto], [])
for nome, pagina in (('accrual-swap.html', 'Swap Accrual'), ('mtm-swap.html', 'Swap MtM')):
    texto = io.open(os.path.join(PAGINAS, nome), encoding='utf-8').read()
    check('  %s nomeia a tabela de cada LOB' % nome,
          ("setAttribute('data-export-name', '%s - ' + lob.name)" % pagina) in texto, True)

# Duas chamadas do Advanced Export na mesma pagina sem rotulo = dois arquivos
# com o mesmo nome. Rotulo e o `name` da chamada ou o `data-export-name`.
sem_nome = {}
for nome, texto in fontes():
    chamadas = list(re.finditer(r'otcExportAdvanced\(', texto))
    if len(chamadas) < 2 or 'data-export-name' in texto:
        continue
    n = sum(1 for m in chamadas if 'name:' not in texto[m.end():m.end() + 260])
    if n >= 2:
        sem_nome[nome] = n
check('  nenhuma pagina exporta duas tabelas com o mesmo nome', sem_nome, {})

# O titulo da pagina e o NOME dela (o `{% block title %}`, em ingles): pagina
# que exporta sem ele baixaria "Export - OTC Tracker - ...".
sem_titulo = []
for nome in sorted(os.listdir(PAGINAS)):
    if not nome.endswith('.html'):
        continue
    texto = io.open(os.path.join(PAGINAS, nome), encoding='utf-8').read()
    if ('buttons.html5' in texto or 'tools-assets-js' in texto or 'otcExportName' in texto) \
            and not re.search(r'{% block title %}\s*\S', texto):
        sem_titulo.append(nome)
check('  toda pagina que exporta tem {% block title %}', sem_titulo, [])

# Os exports que NAO sao do Buttons perguntam o nome ao mesmo helper.
MAPA = io.open(os.path.join(PAGINAS, 'mapping.html'), encoding='utf-8').read()
check('  /mapping: nome = o CADASTRO no padrao (rotulo em ingles)',
      'function exportFile() { return otcExportName(typeOf(CUR).label); }' in MAPA
      and 'function exportTitle() { return otcExportTitle(typeOf(CUR).label); }' in MAPA, True)
check('  /mapping: CSV, Excel e PDF saem com esse nome',
      all(x in MAPA for x in ("exportFile() + '.csv'", "exportFile() + '.xlsx'", "exportFile() + '.pdf'"))
      and 'mapping_' not in MAPA, True)
check('  /mapping carrega o export-advanced.js (o helper do nome)', 'js/export-advanced.js' in MAPA, True)
FXO = io.open(os.path.join(PAGINAS, 'reconciliation-fxo.html'), encoding='utf-8').read()
check('  Recon FXO: o CSV proprio pergunta o nome ao helper', "otcExportName('#fxo-table')" in FXO, True)

# Os CSVs gerados no SERVIDOR (as bases das Tools, as minhas tarefas).
TOOLS = io.open(os.path.join(ROOT, 'apps', 'pages', 'features', 'tools', 'entrypoint.py'), encoding='utf-8').read()
check('  Tools: as tres bases em CSV no padrao',
      ("return '%%s%s.csv' %% tela" % SUFIXO) in TOOLS
      and all(("_nome_export('%s')" % x) in TOOLS for x in ('Term SOFR', 'SOFR Index', 'Euribor')), True)
UH = io.open(os.path.join(ROOT, 'apps', 'pages', 'features', 'user_home', 'entrypoint.py'), encoding='utf-8').read()
check('  User Home: My Tasks no padrao', ("'My Tasks%s.csv'" % SUFIXO) in UH, True)

# ── 4. O menu de Export completo ───────────────────────────────────────────
# Copy · CSV · Excel · Print · PDF. As telas abaixo nasceram com o menu pela
# metade e continuam assim: a lista impede que a proxima entre junto.
print('=== 4. Os cinco itens do menu (§7) ===')
MENU_INCOMPLETO = {
    'intrag-dce-option.html': ['pdf'],
    'intrag-ndf.html': ['pdf'],
    'intrag-option.html': ['pdf'],
    'intrag-swap.html': ['pdf'],
    'other-products-swap-vcp.html': ['pdf'],
    'reconciliation-fxo.html': ['copy', 'csv'],      # os dois proprios do item 1
    'cognos.js': ['pdf', 'print'],
    'live-position-ndf.js': ['pdf', 'print'],
    'live-position-option.js': ['pdf', 'print'],
    'live-position-swap-characteristics.js': ['pdf', 'print'],
    'ndf-cockpit.js': ['pdf', 'print'],
    'ndf-other-publisher.js': ['pdf', 'print'],
    'operations-b3.js': ['pdf', 'print'],
    'other-products-swap-latamdeskposition.js': ['pdf', 'print'],
    'otm-settlements.js': ['pdf', 'print'],
}
CANON = {'copy': 'copy', 'copyHtml5': 'copy', 'csv': 'csv', 'csvHtml5': 'csv',
         'excel': 'excel', 'excelHtml5': 'excel', 'print': 'print',
         'pdf': 'pdf', 'pdfHtml5': 'pdf'}
incompleto = {}
for nome, texto in fontes():
    if 'dataTable.Buttons' not in texto and 'buttons:' not in texto:
        continue
    tem = set()
    for m in re.findall(r"""extend:\s*['"](\w+)['"]""", texto):
        if m in CANON:
            tem.add(CANON[m])
    for m in re.findall(r"""data-btn=['"](\w+)['"]""", texto):
        if m in CANON:
            tem.add(CANON[m])
    if not tem:
        continue
    falta = [x for x in ('copy', 'csv', 'excel', 'pdf', 'print') if x not in tem]
    if falta:
        incompleto[nome] = falta
check('  so as telas conhecidas tem o menu pela metade', incompleto, MENU_INCOMPLETO)

# ── 5. O campo de data se DIGITA ───────────────────────────────────────────
# Data e SEMPRE dd/mm/aaaa (§7), e o campo do app e o `otcDateField`. Digitar
# nele era pôr as barras a mao: um digito a mais ou uma barra esquecida dava um
# texto que o parse frouxo do flatpickr le como uma data QUALQUER, sem erro
# nenhum. A mascara mora no HELPER — copiada por pagina, ela chega a umas e
# falta noutras, que e a historia do Import laranja da setima tela (§490).
print('=== 5. A mascara de data (dd/mm/aaaa, so os numeros) ===')
# Desde 22/10/2026 a regra e de TODO datepicker do app e mora no `date-std.js`
# (carregado pelo `footer-scripts.html` em toda pagina, antes dos scripts dela):
# o flatpickr (direto ou pelo `otcDateField`) e o daterangepicker de data unica.
DS = io.open(os.path.join(ROOT, 'apps', 'static', 'js', 'date-std.js'), encoding='utf-8').read()
FS = io.open(os.path.join(ROOT, 'apps', 'templates', 'partials', 'footer-scripts.html'), encoding='utf-8').read()
XA = io.open(os.path.join(ROOT, 'apps', 'static', 'js', 'export-advanced.js'),
             encoding='utf-8').read()
check('  o date-std.js e carregado em TODA pagina, depois do otc.js',
      FS.index('js/date-std.js') > FS.index('js/otc.js'), True)
check('  ele expoe a mascara', 'window.otcDateMask = dateMask;' in DS, True)
check('  e o export-advanced nao tem copia: o otcDateField usa a dele',
      'function dateMask' not in XA
      and 'if (fp && fp.altInput && window.otcDateMask) window.otcDateMask(fp.altInput, fp);' in XA, True)
# So a data inteira e escolha: escrever no picker no meio da digitacao faria o
# campo pular para um dia que ninguem pediu. E completada ela vale na hora: o
# codigo em volta le o ISO do input original, que so nasceria no blur.
check('  so a data INTEIRA e REAL e escrita no picker',
      "if (d.length === 8 && dataReal(dia, mes, ano)) { escolhe(txt); return; }" in DS
      and "fp.setDate(txt, true, 'd/m/Y')" in DS, True)
# O setDate dispara um `input` no campo do picker; no flatpickr direto ele e o
# visivel, e sem a trava a mascara chamava setDate de novo, sem fim.
check('  a trava contra o laco do setDate (flatpickr sem altInput)',
      'if (escrevendo) return;' in DS and 'if (atual === txt) return;' in DS, True)
# O calendario ACOMPANHA a digitacao: dia e mes levam ao mes, sem escolher nada;
# e o clique seleciona a data inteira, como na Quotes (§508).
check('  dia e mes levam o calendario ao mes', 'fp.jumpToDate(new Date(' in DS, True)
check('  o clique seleciona a data inteira',
      "inp.addEventListener('focus', selAll);" in DS and "inp.addEventListener('click', selAll);" in DS, True)
# 31/02 nao e data: o parse frouxo do flatpickr a leria como 03/03 ao sair do
# campo (no blur E no clique fora, que ele rele antes do blur).
check('  data impossivel/pela metade volta a ultima valida',
      "inp.addEventListener('blur', restaura, true);" in DS
      and "window.addEventListener('mousedown', foraDoCampo, true);" in DS, True)
# O daterangepicker de data unica: a mesma regra, e o keyup FROUXO do plugin sai.
check('  o daterangepicker se digita (o keyup frouxo do plugin sai)',
      "window.jQuery(inp).off('keyup.daterangepicker');" in DS and 'drp.clickApply();' in DS, True)
check('  ...aberto ANTES de a data mudar (senao o callback da pagina nao roda)',
      'if (!drp.isShowing) drp.show();' in DS, True)
# O botao TODAY no pe dos dois calendarios, com o estilo no tema.
CSS = io.open(os.path.join(ROOT, 'apps', 'static', 'css', 'otc.css'), encoding='utf-8').read()
check('  o Today nos dois calendarios',
      'fp.calendarContainer.appendChild(rodape(' in DS and 'drp.container.append(rodape(' in DS, True)
check('  ...com o estilo no tema', '.otc-dp-today' in CSS and '.otc-dp-foot' in CSS, True)
# Ninguem liga o padrao a mao: o flatpickr e embrulhado na criacao, e os dois
# sao reconhecidos na primeira interacao e numa varredura depois da carga.
check('  o padrao se liga sozinho (criacao, interacao, varredura)',
      'window.flatpickr = embrulhado;' in DS and "['focusin', 'mousedown', 'click']" in DS
      and "on('show.daterangepicker'" in DS, True)
# O `type="date"` nativo nao volta: o calendario do SISTEMA nao aceita o Today,
# nao acompanha a digitacao e desenha mm/dd no Windows do JP.
def _sem_comentarios(t):
    # o comentario que EXPLICA por que nao usar o nativo nao e uso
    t = re.sub(r'\{#.*?#\}|<!--.*?-->|/\*.*?\*/', '', t, flags=re.S)
    return re.sub(r'(?m)^\s*//.*$|\s//\s.*$', '', t)
nativos = sorted(n for n, t in fontes() if re.search(r'<input[^>]*type=["\']date["\']', _sem_comentarios(t)))
check('  nenhuma tela com <input type="date">', nativos, [])

print()
if fails:
    print('FALHOU (%d):' % len(fails))
    for f in fails:
        print('  -', f)
    sys.exit(1)
print('TUDO OK')
