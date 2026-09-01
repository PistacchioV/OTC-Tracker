"""Pending Confirmation: a atualizacao em massa e as colunas DERIVADAS.

A tela deixava aplicar em massa uma coisa so — o Pending Status. Agora escolhe-se
a COLUNA e o campo de valor se adapta ao tipo dela, no modelo das paginas de New
Deals.

O que este teste prende:

  1. as colunas que NAO podem entrar na lista. Owner, Economic Group, Aging e
     Status sao derivadas — digitar por cima delas cria um valor que a proxima
     gravacao desfaz, sem avisar. E o Trade Number e a CHAVE da linha no banco:
     aplicar o mesmo numero em varias linhas as fundiria numa so, o que nao tem
     desfazer.

  2. o RECALCULO no servidor. As regras (Reference Data, faixa de aging, prazo
     Maturity - Trade <= 60) sao as MESMAS da importacao do Pending Update. Uma
     copia em JavaScript faria a mesma operacao sair com um Pending Status pelo
     arquivo e outro por uma edicao na tela — e as duas telas mostrariam numeros
     diferentes do mesmo dia.

  3. a cascata: qual coluna dispara o recalculo de que. SPN/Client mexem na
     identidade da contraparte; Trade/Maturity mexem no prazo.

  4. o campo tipado: data com mascara, dropdown fechado onde a lista e fechada,
     autocomplete do Reference Data no SPN e no Client.

Nao encosta em dado real: o endpoint e chamado com linhas sinteticas e a pagina
e renderizada pelo endpoint com sessao de teste.
"""
import io
import os
import re
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from apps.pages import routes as R                            # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def read(rel):
    return io.open(os.path.join(ROOT, rel), encoding='utf-8', errors='ignore').read()


HTML_SRC = read('apps/templates/pages/pending-confirmation.html')

print('== 1. as colunas oferecidas ==')
blk = HTML_SRC.split('var PC_MASS_COLUMNS = [', 1)[1].split('\n    ];', 1)[0]
cols = {int(m.group(1)): m.group(2)
        for m in re.finditer(r"dtCol:\s*(\d+),\s*label:\s*'([^']+)'", blk)}
check('ha colunas', len(cols) > 10, True)
# As quatro derivadas e a chave ficam de fora — e este e o ponto do teste.
for idx, name in ((2, 'Status'), (6, 'Aging'), (12, 'Owner'), (18, 'Economic Group')):
    check('%s (derivada) fora da lista' % name, idx in cols, False)
check('Trade Number (chave) fora da lista', 10 in cols, False)
# E as editaveis dentro.
for idx, name in ((3, 'LOB'), (4, 'SPN'), (5, 'Client'), (7, 'Product Type'),
                  (8, 'Trade Date'), (9, 'Maturity Date'), (11, 'Pending Status'),
                  (13, 'EA'), (14, 'Send Date'), (15, 'Return Date'),
                  (16, 'Break Reason'), (17, 'Comments'), (19, 'Signature Type'),
                  (20, 'FepWeb ID'), (21, 'Pendência')):
    check('%s editavel no indice %d' % (name, idx), cols.get(idx), name)
# Os indices tem de bater com o SF_COLS, que e quem grava a linha.
sf = {int(m.group(2)): m.group(1) for m in
      re.finditer(r"\{ label: '([^']+)',\s*type: '\w+',\s*dtCol: (\d+)\s*\}", HTML_SRC)}
check('indices batem com o SF_COLS (quem grava)',
      sorted((i, n) for i, n in cols.items() if sf.get(i) != n), [])

print('\n== 2. o tipo do campo de valor ==')
kinds = {int(m.group(1)): m.group(2)
         for m in re.finditer(r"dtCol:\s*(\d+),[^}]*?kind:\s*'(\w+)'", blk, re.S)}
for idx in (8, 9, 13, 14, 15):
    check('coluna %d e data (mascara)' % idx, kinds.get(idx), 'date')
for idx in (3, 7, 11, 19):
    check('coluna %d e dropdown' % idx, kinds.get(idx), 'select')
for idx in (4, 5):
    check('coluna %d e autocomplete do Reference Data' % idx, kinds.get(idx), 'refdata')
for idx in (16, 17, 20, 21):
    check('coluna %d e texto livre' % idx, kinds.get(idx), 'text')
# A mascara e a MESMA do modal (flatpickr d/m/Y) — outra e o campo aceitar
# dd/mm/yyyy e gravar mm/dd/yyyy sem ninguem notar.
fld = HTML_SRC.split('function pcMassBuildValueField', 1)[1].split('\n    $(document)', 1)[0]
check('data usa o flatpickr d/m/Y', "dateFormat: 'd/m/Y'" in fld, True)
check('o autocomplete le o refData', 'refData.filter' in fld, True)
check('Signature Type sai do proprio cadastro',
      "optionsVar: 'PC_SIGNATURE_TYPES'" in blk and 'PC_SIGNATURE_TYPES.push' in HTML_SRC, True)

print('\n== 3. a cascata: que coluna recalcula o que ==')
casc = HTML_SRC.split('var PC_CASCADE = {', 1)[1].split('};', 1)[0]
got = {int(m.group(1)): [x.strip().strip("'") for x in m.group(2).split(',')]
       for m in re.finditer(r"(\d+):\s*\[([^\]]+)\]", casc)}
check('SPN recalcula a identidade da contraparte', got.get(4),
      ['SPN', 'Client', 'Owner', 'Economic Group', 'Signature Type'])
check('Client faz o mesmo', got.get(5), got.get(4))
check('Trade Date recalcula prazo e idade', got.get(8),
      ['Aging', 'Status', 'Pending Status'])
check('Maturity Date faz o mesmo', got.get(9), got.get(8))
check('as outras colunas nao disparam nada', sorted(got), [4, 5, 8, 9])
# Onde cada derivada entra na linha.
cells = HTML_SRC.split('var PC_DERIVED_CELLS = {', 1)[1].split('};', 1)[0]
cmap = {m.group(1): int(m.group(2)) for m in re.finditer(r"'([^']+)':\s*(\d+)", cells)}
check('Status na 2', cmap.get('Status'), 2)
check('Aging na 6', cmap.get('Aging'), 6)
check('Pending Status na 11', cmap.get('Pending Status'), 11)
check('Owner na 12', cmap.get('Owner'), 12)
check('Economic Group na 18', cmap.get('Economic Group'), 18)
check('Signature Type na 19', cmap.get('Signature Type'), 19)
# E o recalculo e do SERVIDOR, nao uma segunda copia da regra aqui.
check('a tela chama o /derive', "'/api/pending-confirmation/derive'" in HTML_SRC, True)
check('e nao tem a regra dos 60 dias em JS', '60' in casc, False)

print('\n== 4. o recalculo no servidor ==')
from apps import create_app                                   # noqa: E402
from apps.config import DebugConfig                           # noqa: E402

app = create_app(DebugConfig)
cl = app.test_client()
with cl.session_transaction() as s:
    s['authenticated'] = True
    s['user_sid'] = 'T000000'
    s['user_name'] = 'T'
    s['user_role'] = 'ADMIN'
    s['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()


def derive(**row):
    r = cl.post('/api/pending-confirmation/derive', json={'rows': [row]})
    j = r.get_json() or {}
    return (j.get('rows') or [{}])[0]


today = datetime.now().date()


def dmy(days_ago):
    return (today - timedelta(days=days_ago)).strftime('%d/%m/%Y')


def dmy_fwd(days):
    return (today + timedelta(days=days)).strftime('%d/%m/%Y')


# Prazo <= 60 -> Exception FepWeb + Status Ok (a linha migra para o db ok). E a
# regra de NDF Vanilla / Other Publisher, a mesma que o New Deals aplica — o
# rotulo e UM so nos dois caminhos.
d = derive(**{'Trade Date': dmy(5), 'Maturity Date': dmy_fwd(30)})
check('prazo curto vira Exception FepWeb', d.get('Pending Status'),
      'Exception FepWeb')
check('   e Status Ok', d.get('Status'), 'Ok')
check('   com o aging do Trade Date', d.get('Aging'), '5')
# Prazo > 60 -> depende da assinatura da contraparte; sem cadastro, Original.
d = derive(**{'Trade Date': dmy(45), 'Maturity Date': dmy_fwd(200)})
check('prazo longo sem cadastro vira Pending Original', d.get('Pending Status'),
      'Pending Original')
check('   e Status na faixa do aging', d.get('Status'), '>= 30 e < 60 dias de pendência')
# Faixas de aging — a mesma tabela do arAgingStatus do modal.
for days, band in ((3, '< 10 dias de pendência'), (15, '>= 10 e < 20 dias de pendência'),
                   (25, '>= 20 e < 30 dias de pendência'), (45, '>= 30 e < 60 dias de pendência'),
                   (75, '>= 60 e < 90 dias de pendência'), (120, '>= 90 dias de pendência')):
    d = derive(**{'Trade Date': dmy(days), 'Maturity Date': dmy_fwd(300)})
    check('aging %d dias' % days, (d.get('Aging'), d.get('Status')), (str(days), band))
# Sem data nenhuma nao inventa aging.
d = derive(**{})
check('sem Trade Date o aging fica vazio', d.get('Aging'), '')
check('   e o Status tambem', d.get('Status'), '')
# Lote inteiro numa chamada so.
r = cl.post('/api/pending-confirmation/derive', json={'rows': [
    {'Trade Date': dmy(5), 'Maturity Date': dmy_fwd(30)},
    {'Trade Date': dmy(45), 'Maturity Date': dmy_fwd(200)},
]})
j = r.get_json() or {}
check('o lote volta na mesma ordem',
      [x['Pending Status'] for x in j.get('rows', [])],
      ['Exception FepWeb', 'Pending Original'])

# A ETAPA DA ESTEIRA NAO E RECALCULADA. Tudo que nao e NDF Vanilla / Other
# Publisher passa pela esteira de validacao, e quem manda no estagio e o
# Confirmations Monitor: recalcular por prazo aqui trocava um 'Pending MO' por
# 'Pending Original' e a confirmacao sumia da fila da mesa sem ninguem validar.
for etapa in ('Pending OTC', 'Pending MO', 'Pending FO', 'Pending MO/FO',
              'Pending Legal', 'Pending FepWeb'):
    d = derive(**{'Trade Date': dmy(5), 'Maturity Date': dmy_fwd(30),
                  'Pending Status': etapa})
    check('a etapa %s sobrevive ao prazo curto' % etapa, d.get('Pending Status'), etapa)
# O status de assinatura NAO e etapa: esse continua sendo recalculado.
d = derive(**{'Trade Date': dmy(5), 'Maturity Date': dmy_fwd(30),
              'Pending Status': 'Pending Original'})
check('   mas Pending Original ainda e recalculado', d.get('Pending Status'),
      'Exception FepWeb')
# E a tela manda o Pending Status atual no payload — sem isso o servidor nao tem
# como saber que a linha esta na esteira.
pay = HTML_SRC.split('var payload = rows.map', 1)[1].split('});', 1)[0]
check('a tela manda o Pending Status atual', "'Pending Status'" in pay, True)
check('lista vazia responde vazio',
      (cl.post('/api/pending-confirmation/derive', json={'rows': []}).get_json() or {}).get('rows'), [])
check('payload torto nao derruba',
      cl.post('/api/pending-confirmation/derive', json={'rows': 'x'}).status_code, 400)

print('\n== 5. a mesma regra que a importacao do Pending Update usa ==')
SRC = (read('apps/pages/routes.py')
       + read('apps/pages/features/pending_confirmation/entrypoint.py')
       + read('apps/pages/platform/pending_confirmation.py'))
blkp = SRC.split('def _pc_derive_row', 1)[1].split('\ndef ', 1)[0]
check('reusa o _pc_signature_status', '_pc_signature_status(' in blkp, True)
check('   passando o Pending Status atual', "src.get('Pending Status'" in blkp, True)
check('reusa o _pc_refdata_lookup', '_pc_refdata_lookup(' in blkp, True)
check('e nao reescreve a faixa de aging', '< 10' in blkp, False)

print('\n== 6. a tela nao ficou com a barra antiga ==')
check('o combo so-de-status saiu', 'statusMassUpdate' in HTML_SRC, False)
check('o dropdown de coluna existe', "id = 'pcMassColumnSelect'" in HTML_SRC, True)
check('e a tela abre', cl.get('/pending-confirmation').status_code, 200)

print('\n== 7. o upsert em LOTE (2026-09-01): 3 aberturas, nao 4 por linha ==')
# Cada abertura de banco no share e lock exclusivo + connect + commit; o mass
# update mandava um request por linha e cada upsert abria os TRES bancos mais o
# alvo. O lote persiste N linhas em ate tres aberturas — este guarda CONTA.
import tempfile as _tf
from apps.pages.platform import pending_confirmation as _PC
_dbdir = _tf.mkdtemp()
_old_dbdir = R._PC_DB_DIR
R._PC_DB_DIR = _dbdir
_opens = []
_orig_exec = _PC._pc_write_exec
_PC._pc_write_exec = lambda cat, ops: (_opens.append(cat), _orig_exec(cat, ops))[1]
try:
    hoje = datetime.now().strftime('%d/%m/%Y')
    linhas = [{'Trade Number': 'TN%d' % i, 'Client': 'C%d' % i,
               'Trade Date': hoje, 'Pending Status': 'Pending Original'}
              for i in range(5)]
    resp = cl.post('/api/pending-confirmation/upsert', json={'rows': linhas})
    check('o lote responde 200', resp.status_code, 200)
    check('e devolve uma categoria por linha',
          len((resp.get_json() or {}).get('categories') or []), 5)
    check('5 linhas custam no maximo 3 aberturas (foram %d)' % len(_opens),
          len(_opens) <= 3, True)
    # TN repetido: vale a ULTIMA linha (a semantica do upsert sequencial)
    _opens[:] = []
    dupla = [{'Trade Number': 'TNX', 'Client': 'PRIMEIRA', 'Trade Date': hoje,
              'Pending Status': 'Pending Original'},
             {'Trade Number': 'TNX', 'Client': 'SEGUNDA', 'Trade Date': hoje,
              'Pending Status': 'Pending Original'}]
    cl.post('/api/pending-confirmation/upsert', json={'rows': dupla})
    achadas = [r for r in R._pc_load_rows('pending') if r.get('Trade Number') == 'TNX']
    check('TN repetido no lote: sobra UMA linha', len(achadas), 1)
    check('   e ela e a ULTIMA', achadas[0].get('Client'), 'SEGUNDA')
    # o formato de UMA linha continua aceito (compat)
    um = cl.post('/api/pending-confirmation/upsert',
                 json={'row': {'Trade Number': 'TNY', 'Client': 'SO UMA',
                               'Trade Date': hoje,
                               'Pending Status': 'Pending Original'}})
    check('o formato antigo {row} segue valendo', um.status_code, 200)
    check('a tela manda o lote (pcPersistRows)', 'pcPersistRows' in HTML_SRC
          or 'pcPersistRows' in read('apps/templates/pages/pending-confirmation.html'), True)
finally:
    _PC._pc_write_exec = _orig_exec
    R._PC_DB_DIR = _old_dbdir

print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
