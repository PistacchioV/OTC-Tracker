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
3. **As etapas da esteira** de um documento que não está `Active`: o cadastro
   `cgd-stage` vence, e sem ele as etapas são DERIVADAS pelos carimbos — Legal
   e OTC correm em PARALELO (a solicitação nasce nas duas filas), o Taxonomy
   fecha a Legal e passa a pendência ao CEM MO, o `OTC - STAMP` fecha o OTC.
   Documento pendente que não cai em fila nenhuma some da tela.
4. **A importação REESCREVE a tabela.** Rodar duas vezes tem de dar o mesmo
   resultado, e a linha apagada no SharePoint tem de sumir daqui.

Não toca em dado real: o banco e os cadastros vão para um diretório temporário.
"""

import json
import os
import shutil
import subprocess
import sys
import io
import re
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
    formulário preenchidos, como o New Request grava."""
    # Os valores saem do PRÓPRIO `REQUEST_FIELDS`, e não de uma lista escrita
    # aqui: um campo obrigatório novo no formulário mudaria o que a linha de
    # teste representa sem dizer que a causa foi o campo novo.
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

# ── O rotulo de cada coluna, nos tres idiomas ───────────────────────────────
# Os NOMES sao os do banco (e os do SharePoint antes dele) e estao em portugues:
# `Razao Social`, `Emissao`, `Instituicao Financeira`. Renomea-los quebraria a
# base de quem ja a tem em disco, entao quem traduz e o mapa `COLTR` do
# template. Coluna sem entrada aparece na tela com o nome do banco — que foi o
# que fez a tela em ingles mostrar cabecalho em portugues.
print('\n== os rotulos das colunas ==')
_tpl = io.open(os.path.join(ROOT, 'apps', 'templates', 'pages',
                            'onboarding-tracking-docs.html'), encoding='utf-8').read()
_mapa = re.search(r'var COLTR = \{(.*?)\n    \};', _tpl, re.DOTALL)
check('o mapa COLTR existe no template', bool(_mapa), True)
_traduzidas = set(re.findall(r"^\s*'([^']+)':\s*\{", _mapa.group(1), re.M)) if _mapa else set()
check('toda coluna de COLUMNS tem rotulo',
      sorted(c for c in C.COLUMNS if c not in _traduzidas), [])
check('e o mapa nao inventa coluna',
      sorted(c for c in _traduzidas if c not in C.COLUMNS), [])
# Os tres idiomas em cada entrada: faltando um, a tela cai no ingles sem avisar.
_incompletas = []
for _bloco in re.finditer(r"'([^']+)':\s*\{([^}]*)\}", _mapa.group(1) if _mapa else ''):
    _idiomas = set(re.findall(r'\b(en|br|es)\s*:', _bloco.group(2)))
    if _idiomas != {'en', 'br', 'es'}:
        _incompletas.append(_bloco.group(1))
check('todo rotulo tem en/br/es', _incompletas, [])

# O cabecalho e o filtro usam o ROTULO; o resto do codigo, o nome do banco.
check('o cabecalho usa colLabel', 'esc(colLabel(c))' in _tpl, True)

# ── Os dominios fechados ────────────────────────────────────────────────────
print('\n== os dominios de select ==')
check('Doc Type e o Transactional Type do Electronic Inventory',
      list(C.DOC_TYPES),
      ['CGD', 'Appendix', 'CSA', 'CGD Amendment', 'Appendix Amendment'])
check('e a coluna que o usa existe', C.DOC_TYPE_COLUMN in C.COLUMNS, True)
check('Garantidor e Yes/No', list(C.GUARANTOR_OPTIONS), ['Yes', 'No'])

# ── O formulario de abertura ────────────────────────────────────────────────
print('\n== o formulario de New CGD Request ==')
# Todo texto do app nasce em INGLES e e traduzido por `data-lang` (CLAUDE.md 2).
# Os rotulos e as dicas vem do SERVIDOR, entao a chave i18n vem junto com eles —
# o mesmo desenho dos cadastros `dce-*` do /mapping. Sem a chave, o campo sai no
# rotulo ingles; sem a TRADUCAO, ele sai em ingles nas tres telas.
_tr = {}
for _lg in ('en', 'br', 'es'):
    _tr[_lg] = json.load(io.open(os.path.join(ROOT, 'apps', 'static', 'data',
                                              'translations', '%s.json' % _lg),
                                 encoding='utf-8'))
_sem_chave, _sem_trad = [], []
for _f in C.REQUEST_FORM:
    if not _f.get('lang'):
        _sem_chave.append(_f['label'])
    if _f.get('hint') and not _f.get('hint_lang'):
        _sem_chave.append(_f['label'] + ' (hint)')
    for _k in (_f.get('lang'), _f.get('hint_lang')):
        if _k:
            for _lg in ('en', 'br', 'es'):
                if _k not in _tr[_lg]:
                    _sem_trad.append('%s/%s' % (_lg, _k))
check('todo campo tem chave i18n', _sem_chave, [])
check('e toda chave existe nos tres idiomas', _sem_trad, [])
# Rotulo em portugues escapa do i18n: ele apareceria igual nas tres telas.
_acentos = [f['label'] for f in C.REQUEST_FORM
            if any(ch in f['label'] for ch in 'áàâãéêíóôõúçÁÀÂÃÉÊÍÓÔÕÚÇ')]
check('nenhum rotulo em portugues', _acentos, [])

# O `enabled_by` diz que um campo so vale quando OUTRO tem certo valor, e quem
# declara e o formulario — nao o JS. Com a regra no navegador, o dia em que o
# dominio do mestre mudasse ela continuaria olhando para o valor antigo e o
# campo ficaria travado para sempre, sem erro nenhum. Sao DOIS dependentes: as
# informacoes do Garantidor (ligadas pelo Yes) e o Dominio (ligado quando o
# checkbox do Apendice esta DESMARCADO = No).
_dep = {f['column']: f['enabled_by'] for f in C.REQUEST_FORM if f.get('enabled_by')}
check('ha dois campos dependentes', sorted(_dep), ['Dominio', 'Nome Garantidor'])
_e = _dep['Nome Garantidor']
check('   o garantidor depende do Garantidor', _e['column'], 'Garantidor')
check('   ligado no valor Yes', _e['value'], 'Yes')
check('   e o valor dele existe no dominio', _e['value'] in C.GUARANTOR_OPTIONS, True)
check('   ligado, vira obrigatorio', bool(_e.get('required_when_on')), True)
check('   desligado, volta para N/A', _e.get('value_when_off'), 'N/A')
_d = _dep['Dominio']
check('   o Dominio depende do checkbox do Apendice', _d['column'], '_domain_in_appendix')
check('   e liga quando ele esta DESMARCADO', _d['value'], 'No')
check('   desmarcado, o dominio e obrigatorio', bool(_d.get('required_when_on')), True)
check('   marcado, a coluna grava que esta no Apendice',
      _d.get('value_when_off'), 'Included in the Appendix')
# A coluna que MANDA tem de ser um campo do proprio formulario, senao o JS
# procura um mestre que nao esta na tela e a dependencia nunca liga.
for _col, _eb in _dep.items():
    check('   e a coluna que manda em %s esta no formulario' % _col,
          any(f['column'] == _eb['column'] for f in C.REQUEST_FORM), True)
# O checkbox mestre nasce MARCADO (o dominio no Apendice e o caso comum) e a
# coluna dele e PSEUDO — nao persiste, so liga a dependencia.
_chk = [f for f in C.REQUEST_FORM if f['column'] == '_domain_in_appendix'][0]
check('   o checkbox nasce marcado', _chk.get('default'), 'Yes')
check('   e nao entra nos obrigatorios', '_domain_in_appendix' in C.REQUEST_FIELDS, False)

# O separador das entidades e o `;`, e o modal CORTA nele para achar a
# contraparte do anexo (a pasta do Electronic Inventory e de UM cliente).
# Trocar a dica sem trocar o corte manda o grupo inteiro para o nome da pasta.
_partial = io.open(os.path.join(ROOT, 'apps', 'templates', 'partials',
                                'onboarding-new-request.html'), encoding='utf-8').read()
check('a dica pede o ; como separador',
      all(';' in f['hint'] for f in C.REQUEST_FORM
          if f['column'] in ('Razão Social', 'CNPJ')), True)
check('e o modal corta no ; para achar a contraparte',
      "split(/[;\\n]/)" in _partial, True)
check('o disclaimer do Party Central esta no modal',
      'ob-req-disclaimer' in _partial and 'Party Central' in _partial, True)
check('o Apendice e um dropzone', 'ob-req-drop' in _partial, True)


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

# Banking NÃO é mais mesa: a ação dele é o próprio New Request. A solicitação
# criada nasce pendente em Legal E OTC ao mesmo tempo — as duas trabalham em
# paralelo, e dizer uma só esconderia a outra do próprio trabalho.
check('as mesas são três', list(C.STAGES), ['Legal', 'OTC', 'CEM MO'])
check('solicitação criada → Legal e OTC juntas',
      C.pending_stages(pedido(Status='Em elaboração')), (['Legal', 'OTC'], True))
# O Taxonomy fecha a Legal e PASSA a pendência ao CEM MO; o OTC continua.
check('taxonomy anexado, sem OTC → OTC e CEM MO',
      C.pending_stages(pedido(**{'Status': 'X',
                                 'Taxonomy': '20/08/2026 10:00 · E930179'})),
      (['OTC', 'CEM MO'], True))
# O carimbo do OTC fecha o OTC; sem taxonomy a Legal continua.
check('OTC carimbado, sem taxonomy → só Legal',
      C.pending_stages(pedido(**{'Status': 'X', 'OTC - STAMP': '03/08/2026'})),
      (['Legal'], True))
check('taxonomy + OTC, sem MO → CEM MO',
      C.pending_stages(pedido(**{'Status': 'X',
                                 'Taxonomy': '20/08/2026 10:00 · E930179',
                                 'OTC - STAMP': '03/08/2026'})),
      (['CEM MO'], True))
# As datas de Emissão/Assinatura NÃO derivam mais a Legal: quem as grava é o
# modal do OTC, e o que fecha a Legal é o Taxonomy.
check('emissão e assinatura sozinhas não fecham nada',
      C.pending_stages(pedido(**{'Status': 'X', 'Emissão': '01/08/2026',
                                 'Signature Date': '02/08/2026'})),
      (['Legal', 'OTC'], True))
# Tudo carimbado e ainda não Active: fica com a última mesa. Devolver "nenhuma"
# faria o documento sumir das filas.
check('tudo carimbado e ainda não Active fica na última mesa',
      C.pending_stages(pedido(**{'Status': 'X',
                                 'Taxonomy': '20/08/2026 10:00 · E930179',
                                 'OTC - STAMP': '03/08/2026',
                                 'MO - STAMP': '04/08/2026'})),
      (['CEM MO'], True))
# O singular continua respondendo — é a primeira das pendentes.
check('pending_stage é a primeira da lista',
      C.pending_stage(pedido(Status='X')), ('Legal', True))
# O domínio do Tipo de Assinatura é fechado e tem TRÊS opções: `Manual` é o
# mesmo valor que a tela em português mostra como "Física".
check('o tipo de assinatura tem três opções',
      list(C.SIGNATURE_TYPES), ['FepWeb', 'DocuSign', 'Manual'])

# O formulário de New Request grava NAS COLUNAS DO BANCO. Uma coluna com nome
# errado aqui não dá erro: o `update_row` ignora a chave desconhecida e o campo
# preenchido some no caminho — a solicitação nasceria sem o CNPJ que a pessoa
# digitou. E os obrigatórios saem do próprio formulário, para as duas listas não
# divergirem.
# Coluna pseudo (começa com `_`) é do formulário, não do banco: o servidor a
# descarta e ela só existe para o `enabled_by` do checkbox.
check('todo campo do formulário aponta para uma coluna real',
      [f['column'] for f in C.REQUEST_FORM
       if f['column'] and not f['column'].startswith('_')
       and f['column'] not in C.COLUMNS], [])
check('os obrigatórios saem do formulário',
      list(C.REQUEST_FIELDS),
      [f['column'] for f in C.REQUEST_FORM if f['required'] and f['column']
       and not f['column'].startswith('_')])
# O Apêndice é obrigatório no formulário e não tem coluna — é arquivo, vai para
# o Electronic Inventory. Se ele entrasse no `REQUEST_FIELDS`, a coluna `''`
# nunca estaria preenchida e a validação cobraria o impossível.
check('campo sem coluna não entra nos obrigatórios',
      '' in C.REQUEST_FIELDS, False)
check('o Tipo de Assinatura é campo do formulário e coluna do banco',
      C.SIGNATURE_COLUMN in C.COLUMNS
      and C.SIGNATURE_COLUMN in [f['column'] for f in C.REQUEST_FORM], True)
# Os quatro identificadores, a LE, o Doc Type e a Instituição Financeira
# entraram no formulário — cada um gravando na coluna que a lista já tinha.
_form_cols = [f['column'] for f in C.REQUEST_FORM]
for _c in ('ECI', 'SPN', 'CASID', 'UCN', 'Instituição Financeira',
           C.LEGAL_ENTITY_COLUMN, C.DOC_TYPE_COLUMN):
    check('o formulário pede %s' % _c, _c in _form_cols, True)
# A LE tem DUAS opções, o Banco por default — e é POR ELA que o modal do OTC
# decide a coluna do B3 ID.
_le = [f for f in C.REQUEST_FORM if f['column'] == C.LEGAL_ENTITY_COLUMN][0]
check('a LE tem as duas entidades', list(_le['options']), list(C.LEGAL_ENTITIES))
check('   com o Banco por default', _le['default'], 'BANCO J.P MORGAN S.A')
check('   Banco → B3 ID - JPM', C.b3_id_column('BANCO J.P MORGAN S.A'), 'B3 ID - JPM')
check('   Chase → B3 ID - MGT',
      C.b3_id_column('JPMORGAN CHASE BANK, N.A. - SAO PAULO BRANCH'), 'B3 ID - MGT')
check('   vazio cai no JPM (o default do formulário)',
      C.b3_id_column(''), 'B3 ID - JPM')
# O Doc Type do formulário é o MESMO domínio do Electronic Inventory.
_dt = [f for f in C.REQUEST_FORM if f['column'] == C.DOC_TYPE_COLUMN][0]
check('o Doc Type oferece os tipos do EI', list(_dt['options']), list(C.DOC_TYPES))

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
# Um STAGE cadastrado que não existe mais (o antigo Banking) cai na derivação:
# devolvê-lo jogaria o item numa fila que a tela não desenha, e ele sumiria.
cadastro([{'STATUS': 'Em abertura', 'STAGE': 'Banking'}])
check('STAGE que não existe mais cai na derivação',
      C.pending_stages(pedido(Status='Em abertura')), (['Legal', 'OTC'], True))
cadastro([])


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
check('as três mesas na ordem da esteira',
      [c['stage'] for c in ov['cards']], list(C.STAGES))
# Sem taxonomy e sem carimbo do OTC, o documento está nas DUAS filas — Legal e
# OTC correm em paralelo, e o mesmo item aparece nas duas.
check('os dois pendentes estão na Legal (sem taxonomy)',
      sorted(i['client'] for i in filas['Legal']['items']), ['ATACAMA', 'LAWTON'])
check('e também no OTC (as mesas correm em paralelo)',
      sorted(i['client'] for i in filas['OTC']['items']), ['ATACAMA', 'LAWTON'])
check('pending conta DOCUMENTOS distintos, não itens de card', ov['pending'], 2)
check('e o item leva o status COMO ESTÁ ESCRITO',
      sorted(i['status'] for i in filas['Legal']['items']),
      ['Pending OTC', 'Pending Signature'])
check('o item leva a LE (é ela que escolhe o B3 ID do modal do OTC)',
      'legal_entity' in filas['OTC']['items'][0], True)

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
# Inactive e Cancelado saem SEPARADOS — o card de cada um existe para a
# diferença aparecer (um valeu e acabou, o outro nunca chegou a valer).
check('overview: inativos', ov['inactive'], 1)
check('overview: cancelados', ov['cancelled'], 1)
check('overview: pendentes', ov['pending'], 2)
check('overview: os números fecham',
      ov['pending'] + ov['active'] + ov['inactive'] + ov['cancelled'] == ov['total'], True)
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
