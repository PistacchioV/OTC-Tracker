#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Onboarding · Tracking Docs — o banco da lista de CGDs do SharePoint.

Quatro coisas que erram em SILÊNCIO:

1. **O `Aging` é DERIVADO, nunca lido da planilha.** A coluna existe na
   exportação e envelhece parada no banco: quem exportou ontem exportou o aging
   de ontem, e a tela mostraria esse número por semanas. Aqui ele é refeito a
   cada leitura, em dias ÚTEIS ANBIMA, e PARA quando o CGD conclui — senão a
   tela cobraria um documento que terminou.
2. **A importação casa as colunas por NOME**, cego a caixa, acento e pontuação,
   e PROCURA o cabeçalho em vez de presumir a linha 1: a exportação do SharePoint
   vem com linhas de título, e uma linha acima importa a planilha inteira
   deslocada — o CNPJ na coluna do SPN, sem erro nenhum.
3. **A etapa da esteira** de um documento que não está `Active`: o cadastro
   `cgd-stage` vence, e sem ele a etapa é derivada pelo primeiro carimbo que
   falta. Documento pendente que não cai em fila nenhuma some da tela.
4. **A importação REESCREVE a tabela.** Rodar duas vezes tem de dar o mesmo
   resultado, e a linha apagada no SharePoint tem de sumir daqui.

Não toca em dado real: o banco e os cadastros vão para um diretório temporário.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

TMP = tempfile.mkdtemp(prefix='cgd-docs-')
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', os.path.join(TMP, 'share'))
os.environ['OTC_DATABASE_DIR'] = os.path.join(TMP, 'db')

from apps.pages import cgd_docs as C                              # noqa: E402

C._MAPPINGS_DIR = os.path.join(TMP, 'mappings')
os.makedirs(C._MAPPINGS_DIR, exist_ok=True)

falhas = []


def check(label, got, exp):
    ok = got == exp
    print(('ok   ' if ok else 'FAIL ') + label + '  ->  ' + repr(got))
    if not ok:
        falhas.append('%s: %r != %r' % (label, got, exp))


def cadastro(linhas):
    with open(os.path.join(C._MAPPINGS_DIR, 'cgd-stage.json'), 'w', encoding='utf-8') as fh:
        json.dump(linhas, fh, ensure_ascii=False)
    C._STAGE_MAP['mtime'] = None


def linha(**kw):
    r = {c: '' for c in C.COLUMNS}
    r.update(kw)
    return r


def pedido(**kw):
    """Uma linha com a SOLICITAÇÃO já completa — os campos obrigatórios do
    formulário preenchidos. Sem eles o documento está no Banking (a solicitação
    ainda está sendo aberta), e todo teste de etapa daí para a frente mediria
    outra coisa."""
    # Os valores saem do PRÓPRIO `REQUEST_FIELDS`, e não de uma lista escrita
    # aqui: um campo obrigatório novo no formulário passaria a segurar tudo no
    # Banking e o teste acusaria a etapa errada em toda asserção seguinte, sem
    # dizer que a causa foi o campo novo.
    _VALOR = {'Data Solicitação': '01/08/2026', 'CNPJ': '10.144.076/0001-44'}
    base = {col: _VALOR.get(col, 'X') for col in C.REQUEST_FIELDS}
    base.update(kw)
    return linha(**base)


# ── 1. Datas ────────────────────────────────────────────────────────────────

print('== as datas da planilha ==')
check('data de verdade', C.fmt_date(date(2026, 8, 21)), '21/08/2026')
check('texto em dd/mm/aaaa', C.fmt_date('21/08/2026'), '21/08/2026')
check('ISO vira dd/mm/aaaa', C.fmt_date('2026-08-21'), '21/08/2026')
# Serial do Excel: contagem desde 30/12/1899.
check('serial do Excel', C.fmt_date(46255), '21/08/2026')
# Texto que não é data volta como veio: apagá-lo esconderia o erro da planilha.
check('texto que não é data fica visível', C.fmt_date('a combinar'), 'a combinar')
check('vazio continua vazio', C.fmt_date(''), '')
# O SharePoint grava data COM HORA, e o que não está em DATE_COLUMNS sai como
# veio: `B3 Register` e `Captis` apareciam na grade como `2022-08-02 00:00:00`
# ao lado de um `02/08/2022` na coluna vizinha — o mesmo dado em duas grafias na
# mesma linha, e a de fora ainda ordenava e filtrava por outro texto.
check('data com hora perde a hora', C.fmt_date('2022-08-02 00:00:00'), '02/08/2022')
check('   inclusive com hora de verdade', C.fmt_date('2026-06-24 15:30:00'), '24/06/2026')
# A lista tem de ser COMPLETA. Estas são as colunas do SharePoint que guardam
# data; uma que saia daqui volta a aparecer com `00:00:00` na tela.
check('DATE_COLUMNS cobre toda coluna de data',
      sorted(C.DATE_COLUMNS),
      sorted(['B3 Register', 'Captis', 'Conclusion - Stamp', 'Data Solicitação',
              'Emissão', 'MO - STAMP', 'OTC - STAMP', 'Signature Date']))
check('   e toda uma delas existe em COLUMNS',
      [c for c in C.DATE_COLUMNS if c not in C.COLUMNS], [])


# ── 2. O aging ──────────────────────────────────────────────────────────────

print('\n== o aging ==')
# 01/07/2026 (quarta) → 20/07/2026 (segunda): 13 dias úteis.
r = linha(**{'Data Solicitação': '01/07/2026', 'Conclusion - Stamp': '20/07/2026',
             'Aging': '999'})
check('conta em dias ÚTEIS até a conclusão', C.aging_of(r), 13)
check('   e IGNORA o aging que veio da planilha', r['Aging'] != C.aging_of(r), True)

r2 = linha(**{'Data Solicitação': '01/07/2026'})
check('sem conclusão conta até hoje',
      C.aging_of(r2, hoje=date(2026, 7, 20)), 13)
check('o relógio PARA na conclusão',
      C.aging_of(r, hoje=date(2026, 12, 31)), 13)
check('sem data de solicitação não inventa zero', C.aging_of(linha()), '')


# ── 3. A etapa da esteira ───────────────────────────────────────────────────

print('\n== a esteira ==')
cadastro([])
check('documento Active não é pendência de ninguém',
      C.pending_stage(linha(Status='Active')), (None, False))
check('   e o teste é cego a caixa e acento',
      C.pending_stage(linha(Status=' active ')), (None, False))

# Banking é a PRIMEIRA mesa: enquanto a solicitação não tem os campos
# obrigatórios do formulário, ela está sendo aberta e não é pendência das mesas
# seguintes.
check('solicitação incompleta → Banking',
      C.pending_stage(linha(Status='Em elaboração')), ('Banking', True))
for falta in C.REQUEST_FIELDS:
    r = pedido(Status='X')
    r[falta] = ''
    check('   falta "%s" → Banking' % falta, C.pending_stage(r)[0], 'Banking')
check('solicitação completa, sem carimbo nenhum → Legal',
      C.pending_stage(pedido(Status='Em elaboração')), ('Legal', True))
check('emitido e assinado, sem carimbo do OTC → OTC',
      C.pending_stage(pedido(**{'Status': 'X', 'Emissão': '01/08/2026',
                                'Signature Date': '02/08/2026'})),
      ('OTC', True))
check('carimbado pelo OTC, sem o do MO → CEM MO',
      C.pending_stage(pedido(**{'Status': 'X', 'Emissão': '01/08/2026',
                                'Signature Date': '02/08/2026',
                                'OTC - STAMP': '03/08/2026'})),
      ('CEM MO', True))
# Tudo carimbado e ainda não Active: fica com a última mesa. Devolver "nenhuma"
# faria o documento sumir das quatro filas.
check('tudo carimbado e ainda não Active fica na última mesa',
      C.pending_stage(pedido(**{'Status': 'X', 'Emissão': '01/08/2026',
                                'Signature Date': '02/08/2026',
                                'OTC - STAMP': '03/08/2026', 'MO - STAMP': '04/08/2026'})),
      ('CEM MO', True))
# O domínio do Tipo de Assinatura é fechado e tem TRÊS opções: `Manual` é o
# mesmo valor que a tela em português mostra como "Física".
check('o tipo de assinatura tem três opções',
      list(C.SIGNATURE_TYPES), ['FepWeb', 'DocuSign', 'Manual'])

# O formulário de New Request grava NAS COLUNAS DO BANCO. Uma coluna com nome
# errado aqui não dá erro: o `update_row` ignora a chave desconhecida e o campo
# preenchido some no caminho — a solicitação nasceria sem o CNPJ que a pessoa
# digitou. E os obrigatórios saem do próprio formulário, para as duas listas não
# divergirem.
check('todo campo do formulário aponta para uma coluna real',
      [f['column'] for f in C.REQUEST_FORM
       if f['column'] and f['column'] not in C.COLUMNS], [])
check('os obrigatórios saem do formulário',
      list(C.REQUEST_FIELDS),
      [f['column'] for f in C.REQUEST_FORM if f['required'] and f['column']])
# O Apêndice é obrigatório no formulário e não tem coluna — é arquivo, vai para o
# Electronic Inventory. Se ele entrasse no `REQUEST_FIELDS`, a coluna `''` nunca
# estaria preenchida e TODO documento ficaria preso no Banking para sempre.
check('campo sem coluna não entra na regra do Banking',
      '' in C.REQUEST_FIELDS, False)
check('   e são os que seguram o documento no Banking',
      list(C.STAGE_STAMP[0][1]), list(C.REQUEST_FIELDS))
check('o Tipo de Assinatura é campo do formulário e coluna do banco',
      C.SIGNATURE_COLUMN in C.COLUMNS
      and C.SIGNATURE_COLUMN in [f['column'] for f in C.REQUEST_FORM], True)

cadastro([{'STATUS': 'Pending Signature', 'STAGE': 'Legal'},
          {'STATUS': 'AGUARDANDO MO', 'STAGE': 'CEM MO'}])
check('o cadastro VENCE a derivação',
      C.pending_stage(linha(**{'Status': 'Aguardando MO', 'Emissão': '',
                               'Signature Date': ''})),
      ('CEM MO', False))
check('   e a linha cadastrada não vem marcada como derivada',
      C.pending_stage(linha(Status='Pending Signature'))[1], False)
check('   inclusive com a solicitação incompleta (o cadastro é explícito)',
      C.pending_stage(linha(Status='Aguardando MO'))[0], 'CEM MO')
check('status fora do cadastro continua derivando',
      C.pending_stage(pedido(Status='Outro qualquer'))[0], 'Legal')


# ── 4. O banco ──────────────────────────────────────────────────────────────

print('\n== o banco ==')
# As três com a SOLICITAÇÃO completa (o `pedido()` preenche todos os
# obrigatórios): sem isso as três ficariam no Banking, e o que se quer medir
# aqui são as mesas seguintes.
rows = [
    pedido(**{'Status': 'Active', 'Doc Type': 'CGD', 'Razão Social': 'MONDELEZ',
              'CNPJ': '10.144.076/0001-44', 'Data Solicitação': '01/07/2026',
              'Signature Type': 'FepWeb',
              'Emissão': '10/07/2026', 'Signature Date': '15/07/2026',
              'OTC - STAMP': '16/07/2026', 'MO - STAMP': '17/07/2026',
              'Conclusion - Stamp': '20/07/2026', 'Aging': '999'}),
    pedido(**{'Status': 'Pending Signature', 'Doc Type': 'CGD', 'Razão Social': 'ATACAMA',
              'CNPJ': '12.345.678/0001-99', 'Data Solicitação': '01/08/2026',
              'Signature Type': 'DocuSign'}),
    pedido(**{'Status': 'Pending OTC', 'Doc Type': 'CSA', 'Razão Social': 'LAWTON',
              'CNPJ': '98.765.432/0001-11', 'Data Solicitação': '05/08/2026',
              'Signature Type': 'Manual',
              'Emissão': '06/08/2026', 'Signature Date': '07/08/2026'}),
]
n = C.replace_all(rows)
check('gravou as três linhas', n, 3)
lidas = C.load_all()
check('e leu as três de volta', len(lidas), 3)
check('o aging vem RECALCULADO, não o da planilha',
      lidas[0]['Aging'], 13)
check('as datas voltam em dd/mm/aaaa', lidas[0]['Data Solicitação'], '01/07/2026')

# Idempotência: a importação reescreve, não empilha.
C.replace_all(rows)
check('reimportar não duplica', len(C.load_all()), 3)
C.replace_all(rows[:1])
check('   e a linha que sumiu da planilha some do banco', len(C.load_all()), 1)
C.replace_all(rows)

# Edição pela tela.
alvo = C.load_all()[1]
C.update_row(alvo[C.ID_COLUMN], {'Status': 'Pending OTC', 'SPN': '123456'})
depois = [r for r in C.load_all() if r[C.ID_COLUMN] == alvo[C.ID_COLUMN]][0]
check('a edição grava só as colunas conhecidas',
      (depois['Status'], depois['SPN']), ('Pending OTC', '123456'))
C.update_row(alvo[C.ID_COLUMN], {'Coluna Inventada': 'x'})
check('   e coluna que não existe é descartada sem erro',
      len(C.load_all()), 3)

novo_id = C.add_row({'Razão Social': 'NOVO', 'Status': 'Em elaboração'})
check('a linha nova entra no fim', len(C.load_all()), 4)
C.delete_row(novo_id)
check('   e sai inteira', len(C.load_all()), 3)


# ── 5. O Overview ───────────────────────────────────────────────────────────

print('\n== as três filas ==')
cadastro([])
# Estado conhecido: o bloco anterior editou o Status de uma das linhas.
C.replace_all(rows)
ov = C.overview(C.load_all())
check('só o que NÃO está Active entra nas filas', ov['active'], 1)
filas = {c['stage']: c for c in ov['cards']}
check('as quatro mesas na ordem da esteira',
      [c['stage'] for c in ov['cards']], list(C.STAGES))
check('ATACAMA (sem emissão) cai na Legal',
      [i['client'] for i in filas['Legal']['items']], ['ATACAMA'])
check('LAWTON (assinado, sem carimbo do OTC) cai no OTC',
      [i['client'] for i in filas['OTC']['items']], ['LAWTON'])
check('e o item leva o status COMO ESTÁ ESCRITO',
      filas['Legal']['items'][0]['status'], 'Pending Signature')

# A fila vem do mais velho para o mais novo, como no Confirmations Monitor.
C.replace_all(rows + [
    pedido(**{'Status': 'Em elaboração', 'Razão Social': 'MAIS VELHO',
              'CNPJ': '11.111.111/0001-11', 'Signature Type': 'FepWeb',
              'Data Solicitação': '01/01/2026'}),
])
fila_legal = [c for c in C.overview()['cards'] if c['stage'] == 'Legal'][0]
check('a fila abre pelo que espera há mais tempo',
      fila_legal['items'][0]['client'], 'MAIS VELHO')


# ── 6. O script de importação ───────────────────────────────────────────────

print('\n== a importação da planilha ==')
from openpyxl import Workbook                                     # noqa: E402
xlsx = os.path.join(TMP, 'Sharepoint-CGD.xlsx')
wb = Workbook(); ws = wb.active; ws.title = 'Lista'
ws.append(['Lista de CGDs — exportação do SharePoint'])           # título
ws.append([])                                                      # linha vazia
head = list(C.COLUMNS)
# Grafias sujas de propósito: a planilha real vem assim.
head[head.index('Data Solicitação')] = 'DATA SOLICITACAO'
head[head.index('CSA?')] = 'CSA'
head[head.index('OTC - STAMP')] = 'OTC  -  STAMP'
ws.append(head)


def linha_xlsx(**kw):
    r = linha(**kw)
    return [r[c] for c in C.COLUMNS]


ws.append(linha_xlsx(**{'Status': 'Active', 'Razão Social': 'MONDELEZ',
                        'CNPJ': '10.144.076/0001-44', 'Data Solicitação': 46204,
                        'Conclusion - Stamp': '20/07/2026', 'Aging': '999'}))
ws.append(linha_xlsx(**{'Status': 'Pending OTC', 'Razão Social': 'LAWTON',
                        'CNPJ': '98.765.432/0001-11', 'Data Solicitação': '05/08/2026'}))
ws.append([None] * len(C.COLUMNS))                                 # branco no fim
wb.save(xlsx)

env = dict(os.environ)
res = subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'import_cgd_sharepoint.py'),
                      '--xlsx', xlsx],
                     capture_output=True, text=True, env=env, cwd=ROOT)
saida = (res.stdout or '') + (res.stderr or '')
check('o script roda', res.returncode, 0)
check('   e acha o cabeçalho na linha 3 (não na 1)', 'linha 3' in saida, True)
check('   casando as 30 colunas apesar da grafia',
      '%d de %d colunas casadas' % (len(C.COLUMNS), len(C.COLUMNS)) in saida, True)
importadas = C.load_all()
check('a linha em branco do fim não entra', len(importadas), 2)
check('o serial do Excel virou data', importadas[0]['Data Solicitação'], '01/07/2026')
check('o aging da planilha não sobreviveu', importadas[0]['Aging'], 13)

# Cabeçalho que não casa: o script FALHA dizendo o que esperava, em vez de
# importar uma planilha deslocada.
wb2 = Workbook(); ws2 = wb2.active
ws2.append(['coluna a', 'coluna b'])
ws2.append(['1', '2'])
outro = os.path.join(TMP, 'outro.xlsx')
wb2.save(outro)
res2 = subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'import_cgd_sharepoint.py'),
                       '--xlsx', outro],
                      capture_output=True, text=True, env=env, cwd=ROOT)
check('planilha que não é a lista é RECUSADA', res2.returncode != 0, True)
check('   dizendo quais colunas esperava',
      'não achei o cabeçalho' in ((res2.stdout or '') + (res2.stderr or '')), True)

# ── 5. O documento ENCERRADO sai das filas ──────────────────────────────────
# `Inactive` contém `ACTIVE`: com um teste por pedaço o encerrado vira ativo, e
# com um teste exato ele vira PENDENTE e cai na fila do Legal — que é a primeira
# etapa sem carimbo em quem nunca começou. As duas leituras estão erradas, e a
# segunda é pior: o documento morto envelhece para sempre no topo da fila,
# empurrando para baixo o que alguém de fato tem de fazer.
for st, ativo, fechado in (('Active', True, True), ('Inactive', False, True),
                           ('INATIVO', False, True), ('Cancelado', False, True),
                           ('Cancelled', False, True), ('Doc Transacional', False, False)):
    r = {'Status': st}
    check('%-16s is_active' % st, C.is_active(r), ativo)
    check('%-16s is_closed' % st, C.is_closed(r), fechado)
    check('%-16s sem etapa' % st, C.pending_stage(r)[0] is None, fechado)

# E os quatro números do Overview FECHAM. Sem o `closed` explícito o painel
# mostrava três que não somavam o total, e a diferença era justamente o que
# tinha sumido das filas.
ov = C.overview([
    {'Status': 'Active'}, {'Status': 'Active'},
    {'Status': 'Inactive'}, {'Status': 'Cancelado'},
    {'Status': 'Em Analise Legal'}, {'Status': 'Doc Transacional'},
])
check('overview: total', ov['total'], 6)
check('overview: ativos', ov['active'], 2)
check('overview: encerrados', ov['closed'], 2)
check('overview: pendentes', ov['pending'], 2)
check('overview: os quatro fecham',
      ov['pending'] + ov['active'] + ov['closed'] == ov['total'], True)
check('nenhum encerrado nas filas',
      [i['status'] for card in ov['cards'] for i in card['items']
       if C.is_closed({'Status': i['status']})], [])

shutil.rmtree(TMP, ignore_errors=True)

print()
if falhas:
    for f in falhas:
        print('FAIL ' + f)
    sys.exit(1)
print('TUDO OK')
