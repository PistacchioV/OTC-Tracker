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
# `mapping.html` nao entra porque nao tem DataTable nenhuma (pagina com paginacao
# propria, sem Buttons para chamar) — o teste isenta sozinho, sem lista.
CSV_NA_MAO = {
    'reconciliation-fxo.html',   # Csv/Copy proprios convivendo com o Advanced Export
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

# ── 3. Nome do arquivo quando a pagina exporta mais de uma tabela ───────────
print('=== 3. Nome do arquivo (§461) ===')
DUAS_TABELAS_SEM_NOME = {
    # Quatro tabelas, quatro downloads com o titulo da pagina. Divida registrada.
    'index-b3-results.html': 4,
}
sem_nome = {}
for nome, texto in fontes():
    chamadas = list(re.finditer(r'otcExportAdvanced\(', texto))
    if len(chamadas) < 2:
        continue
    n = 0
    for m in chamadas:
        trecho = texto[m.end():m.end() + 260]
        if 'name:' not in trecho:
            n += 1
    if n >= 2:
        sem_nome[nome] = n
check('  so as telas conhecidas exportam duas tabelas com o mesmo nome',
      sem_nome, DUAS_TABELAS_SEM_NOME)

# As duas telas do §461 carimbam tela + card + data no nome.
for nome, pagina in (('other-products-summary.html', 'Other Products Summary'),
                     ('ndf-summary.html', 'NDF Summary')):
    texto = io.open(os.path.join(PAGINAS, nome), encoding='utf-8').read()
    check('  %s nomeia o arquivo pelo documento' % nome,
          ("EXPORT_PAGE = '%s'" % pagina) in texto and 'EXPORT_CARD' in texto, True)
    check('  %s carimba a data de referencia (AAAAMMDD)' % nome,
          'function refDateFlat()' in texto and 'function expName()' in texto, True)
    check('  %s tem os cinco itens de export' % nome,
          sorted(set(re.findall(r"""data-btn=['"](\w+)['"]""", texto))),
          ['copy', 'csv', 'excel', 'pdf', 'print'])
    check('  %s exporta a celula editavel pelo VALUE' % nome,
          'function opsExportCell(' in texto and 'format: { body: opsExportCell }' in texto, True)

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
XA = io.open(os.path.join(ROOT, 'apps', 'static', 'js', 'export-advanced.js'),
             encoding='utf-8').read()
check('  o helper expoe a mascara', 'window.otcDateMask = dateMask;' in XA, True)
# O campo que se VE e o altInput; mascarar o original nao alcanca quem digita.
check('  e a aplica ao campo VISIVEL', 'if (fp && fp.altInput) dateMask(fp.altInput, fp);' in XA, True)
# So a data inteira e escolha: escrever no picker no meio da digitacao faria o
# campo pular para um dia que ninguem pediu.
check('  so a data INTEIRA e escrita no picker',
      "if (d.length === 8 && fp) fp.setDate(txt, true, 'd/m/Y');" in XA, True)
# Completada, ela vale na hora: o codigo em volta le o ISO do input original, e
# ele so nasceria no blur — clicar direto no Run exportaria o intervalo anterior.
check('  o ISO nao espera o blur', 'fp.setDate(txt' in XA, True)

print()
if fails:
    print('FALHOU (%d):' % len(fails))
    for f in fails:
        print('  -', f)
    sys.exit(1)
print('TUDO OK')
