# -*- coding: utf-8 -*-
"""Toda tabela do app centraliza cabecalho E valores (CLAUDE.md §3).

Nao ha regra GLOBAL de centralizacao: o `visual-refresh.css` centraliza so os
campos da linha de filtro, e o `streamflow.css` nao declara `text-align` em
lugar nenhum. Cada tela declara a sua -- e e por isso que a tela nova nasce
torta sem ninguem errar nada. Foram assim o Accrual e o MtM de Swap (nenhum
alinhamento em `th` nem em `td`), o Track de usuarios e o Support Center.

Duas asercoes, e elas pegam defeitos DIFERENTES.

1. A REGRA GENERICA. Uma regra que centraliza UMA coluna (`td.acc-cb-col`, o
   checkbox) nao vale como a regra da tabela -- foi exatamente ela que fez o
   Accrual passar numa primeira varredura mais frouxa. Por isso so conta o
   seletor cujo ULTIMO elemento e `th`/`td` SEM classe, id, atributo ou pseudo.

2. O CLONE do cabecalho com `!important`. Com `scrollX` o DataTables desenha o
   cabecalho numa tabela IRMA e REMOVE o id dela, entao a regra da pagina passa
   a competir com a do plugin sem o id que a fazia ganhar:

       table.dataTable thead th          -> (0,1,3)   text-align: left
       .dt-scroll-headInner thead th     -> (0,1,2)   text-align: center

   O plugin vence por especificidade e o cabecalho sai a ESQUERDA com o corpo
   centralizado -- o desencontro do §3, e o defeito real do Pending
   Confirmation. Seletor de clone com `#id` esta fora do corte: ele ja ganha
   sozinho.

O que este guarda NAO tenta responder: se o clone acaba centralizado por OUTRO
caminho. Ha tres validos no repo hoje -- a regra com `!important` (18 telas), a
classe `.text-center` no markup do `<th>` (Recon de Comitentes) e um seletor
com id que ALCANCA o clone por conter a pagina inteira (`#ops-page
table.dataTable thead th`, nos dois Summaries). Distinguir isso e trabalho de
navegador (o `th` do UA ja e `-internal-center`, entao o que decide e quem
sobrescreve), e uma asercao estatica so reprovaria quem esta certo.
"""
import io
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
PAGES = os.path.join(ROOT, 'apps', 'templates', 'pages')

STYLE = re.compile(r'<style[^>]*>(.*?)</style>', re.S | re.I)
REGRA = re.compile(r'([^{}]+)\{([^{}]*)\}', re.S)
CENTER = re.compile(r'text-align\s*:\s*center', re.I)
CENTER_IMP = re.compile(r'text-align\s*:\s*center\s*!\s*important', re.I)
CLONE = re.compile(r'dt-scroll-head|dataTables_scrollHead', re.I)

# Telas de DEMONSTRACAO do tema comprado: as linhas sao fixas no HTML
# ("Blazor Admin Theme - Final QA", "E-Commerce Redesign", "15 Aug 2025") e as
# colunas numericas levam `text-end` de proposito. Nao sao tabela de dado do
# app -- sao da mesma familia do `horizontal.html`, que foi APAGADO (§3). Se um
# dia elas sairem do repositorio, esta lista sai junto.
DEMO_DO_TEMA = ('dashboard-2.html', 'users-profile.html', 'widgets.html')

falhas = []


def check(rotulo, ok):
    print(('  ok  ' if ok else ' FAIL ') + rotulo)
    if not ok:
        falhas.append(rotulo)


def regras(src):
    return REGRA.findall('\n'.join(STYLE.findall(src)))


def generico(sel):
    """(th, td) — so quando o ULTIMO elemento do seletor e `th`/`td` cru."""
    th = td = False
    for parte in sel.split(','):
        p = parte.strip()
        if not p or p.startswith('@'):
            continue
        ultimo = re.split(r'[\s>+~]+', p)[-1]
        if re.search(r'[.#\[:]', ultimo):
            continue
        if ultimo.lower() == 'th':
            th = True
        elif ultimo.lower() == 'td':
            td = True
    return th, td


def analisa(src):
    """(centraliza_th, centraliza_td, clones_fracos)."""
    th = td = False
    fracos = []
    for sel, decls in regras(src):
        if CENTER.search(decls):
            a, b = generico(sel)
            th, td = th or a, td or b
        if CLONE.search(sel) and re.search(r'\bth\b', sel) and '#' not in sel:
            if CENTER.search(decls) and not CENTER_IMP.search(decls):
                fracos.append(sel.strip().split('\n')[0][:60])
    return th, td, fracos


print('== 1. cabecalho e valores centralizados ==')
alvos = []
for nome in sorted(os.listdir(PAGES)):
    if not nome.endswith('.html') or nome.startswith('email-template'):
        continue
    src = io.open(os.path.join(PAGES, nome), encoding='utf-8').read()
    if '<thead' not in src.lower():
        continue
    alvos.append((nome, src))

check('ha telas com <thead> para conferir (o guarda nao perdeu o alvo)',
      len(alvos) >= 40)

sem_regra = []
for nome, src in alvos:
    if nome in DEMO_DO_TEMA:
        continue
    th, td, _ = analisa(src)
    if not (th and td):
        sem_regra.append('%s (falta %s)' % (nome, ' + '.join(
            [x for x, ok in (('th', th), ('td', td)) if not ok])))
check('as %d telas de dado declaram a regra generica de th E td%s'
      % (len(alvos) - len(DEMO_DO_TEMA),
         '' if not sem_regra else '\n        ' + '\n        '.join(sem_regra)),
      not sem_regra)

# A lista de excecoes tem de continuar sendo de EXCECOES: se uma delas ganhar a
# regra, ela sai daqui, senao a lista vira um lugar onde tela de verdade se
# esconde.
ainda_demo = [n for n in DEMO_DO_TEMA
              if os.path.exists(os.path.join(PAGES, n))]
sobrando = []
for nome in ainda_demo:
    th, td, _ = analisa(io.open(os.path.join(PAGES, nome), encoding='utf-8').read())
    if th and td:
        sobrando.append(nome)
check('as excecoes do tema seguem sem a regra (senao saem da lista): %r'
      % (sobrando or 'nenhuma sobrando',), not sobrando)


print('\n== 2. o clone do cabecalho (scrollX) vence o plugin ==')
fracos_total = []
for nome, src in alvos:
    _, _, fracos = analisa(src)
    for f in fracos:
        fracos_total.append('%s: %s' % (nome, f))
check('nenhuma regra de clone sem `!important`%s'
      % ('' if not fracos_total else '\n        ' + '\n        '.join(fracos_total)),
      not fracos_total)


print('\n== 3. o guarda reprova os casos que aconteceram ==')
# Sem isto, um refactor que afrouxasse os regex deixaria o teste verde por nao
# enxergar mais nada — que e o mesmo verde de "esta tudo certo".
ACCRUAL = """<thead><style>
table.dt-acc thead tr.acc-th-title th { font-size:.7rem; padding:.55rem; }
table.dt-acc th.acc-cb-th, table.dt-acc td.acc-cb-col { text-align: center; }
table.dt-acc tbody td { font-size:.8rem; vertical-align:middle; }
</style>"""
th, td, _ = analisa(ACCRUAL)
check('o Accrual de antes reprova (a regra do checkbox nao conta)',
      not (th and td))

PC = """<thead><style>
#t thead th { text-align: center; }
#t td { text-align: center; }
.dt-scroll-headInner thead th { text-align: center; }
</style>"""
th, td, fracos = analisa(PC)
check('o Pending Confirmation de antes reprova pelo clone sem !important',
      th and td and len(fracos) == 1)

BOM = """<thead><style>
#t thead th { text-align: center; }
#t tbody td { text-align: center; }
.dt-scroll-headInner thead th { text-align: center !important; }
</style>"""
th, td, fracos = analisa(BOM)
check('   e a versao corrigida passa', th and td and not fracos)

# O seletor de clone COM id ja ganha do plugin sozinho — nao pode ser cobrado.
COM_ID = """<thead><style>
#p thead th { text-align:center; } #p tbody td { text-align:center; }
#ops-page table.dataTable thead th { text-align: center; }
</style>"""
th, td, fracos = analisa(COM_ID)
check('clone alcancado por seletor com id nao e cobrado', th and td and not fracos)

print('\n%s' % ('TUDO OK' if not falhas else 'FALHAS (%d)' % len(falhas)))
sys.exit(1 if falhas else 0)
