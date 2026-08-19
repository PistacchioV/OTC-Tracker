"""Manual Confirmations: a esteira de validação de uma confirmação gerada.

O que este teste prende:

  1. **quem valida cada produto** vem do cadastro `manual-conf-validation`, por
     Produto × LOB, com LOB em branco valendo como coringa. Sem cadastro o
     produto cai em OTC + MO — e a tela AVISA, em vez de deixar a confirmação
     parada num Pending que ninguém sabe de quem é.

  2. **MO e FO correm em paralelo**, não em fila. Encadeá-las atrasaria a
     segunda por nada, e uma confirmação parada nas duas mesas tem de aparecer
     nos DOIS cards — mostrá-la só num esconde trabalho da outra.

  3. **o Pending é DERIVADO**, nunca digitado. Uma coluna escrita à mão
     discordaria das datas ao lado dela no primeiro reject.

  4. **o reject limpa o que já foi validado.** O documento vai ser refeito, e um
     'VALIDADO p/ MO' carimbado sobre a versão anterior seria um aval que
     ninguém deu à versão nova.

  5. **o carimbo leva hora E SPN**, e o SPN vem da sessão — aceitar o SPN do
     corpo do POST deixaria qualquer sessão assinar por outra pessoa.

  6. **só os quatro produtos que geram confirmação** entram na esteira. Vanilla
     e Other Publisher alimentam o Pending Confirmation e param por aí; o
     recorte é pelo `source`, porque as três páginas de NDF gravam o mesmo
     Product Type.

Não encosta em dado real: os bancos são recriados num diretório temporário e o
cadastro vai para outro.
"""
import io
import json
import os
import shutil
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from apps.pages import manual_conf as M                          # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


# ── Bancos e cadastro de teste ───────────────────────────────────────────────
TMP_DB = tempfile.mkdtemp(prefix='mc-db-')
TMP_MAP = tempfile.mkdtemp(prefix='mc-map-')
M._DB_DIR = TMP_DB
M._MAPPINGS_DIR = TMP_MAP


def write_map(rows):
    with io.open(os.path.join(TMP_MAP, 'manual-conf-validation.json'), 'w', encoding='utf-8') as fh:
        json.dump(rows, fh, ensure_ascii=False)


MAPA = [
    {'PRODUCT': 'NDF COMM', 'LOB': '', 'OTC': 'REQUESTED', 'MO': 'REQUESTED', 'FO': 'EXEMPT'},
    {'PRODUCT': 'SWAP', 'LOB': '', 'OTC': 'REQUESTED', 'MO': 'REQUESTED', 'FO': 'REQUESTED'},
    {'PRODUCT': 'SWAP', 'LOB': 'EDG', 'OTC': 'EXEMPT', 'MO': 'REQUESTED', 'FO': 'REQUESTED'},
]
write_map(MAPA)


def novo(key, produto='NDF COMM', lob='CEM', **kw):
    d = {'Trade ID': key, 'Produto': produto, 'LOB': lob, 'Cliente': 'ACME S.A.'}
    d.update(kw)
    M.upsert_row(M.blank_row(**d))
    return M.find_row(key)


print('== 1. quem valida cada produto sai do cadastro ==')
r, achou = M.rule_for('NDF COMM', 'CEM')
check('o LOB em branco é coringa do produto', (r, achou),
      ({'OTC': True, 'MO': True, 'FO': False}, True))
r, achou = M.rule_for('SWAP', 'EDG')
check('a linha com LOB ganha da linha coringa', (r, achou),
      ({'OTC': False, 'MO': True, 'FO': True}, True))
r, achou = M.rule_for('SWAP', 'CEM')
check('outra LOB cai no coringa', r['FO'], True)
r, achou = M.rule_for('PRODUTO NOVO', 'CEM')
check('produto sem cadastro cai em OTC + MO', (r, achou), (dict(M.DEFAULT_RULE), False))
check('   e o default é mesmo OTC + MO', M.DEFAULT_RULE,
      {'OTC': True, 'MO': True, 'FO': False})

print('\n== 2. a esteira anda ==')
row = novo('T1')
check('nasce em Pending OTC', row['Pending'], M.PENDING_OTC)
row = M.mark_validated('T1', M.STAGE_OTC, 'A111111')
check('validado o OTC, vai para Pending MO', row['Pending'], M.PENDING_MO)
check('   e o Conferido OTC é carimbado', bool(row['Conferido OTC']), True)
check('   junto com a data de envio para MO/FO', bool(row['Data envio validação MO/FO']), True)
row = M.mark_validated('T1', M.STAGE_MO, 'B222222')
# O fim da esteira tem DOIS degraus (§254): validações feitas SEM o Enviado
# p/ cliente é Pending FepWeb (aguardando envio); Ok exige a data do envio.
check('validado o MO, aguarda o envio (FepWeb)', row['Pending'], M.PENDING_FEPWEB)
check('   e a linha AINDA é pendente', M.target_category(row), 'pending')
check('   Pending FepWeb não se escreve à mão: é derivado',
      M.pending_stage(dict(row, **{'Pending': ''})), M.PENDING_FEPWEB)
r1 = M.find_row('T1')
r1[M.SENT_COLUMN] = '12/08/2026'
M.upsert_row(r1)
row = M.find_row('T1')
check('com o Enviado p/ cliente, fecha', row['Pending'], M.STATUS_OK)
check('   e a linha migra para o banco ok', M.target_category(row), 'ok')
check('   que é onde ela está mesmo',
      [x['Trade ID'] for x in M.load_rows('ok')], ['T1'])
check('   e não está mais no pending', M.load_rows('pending'), [])

# O FO é EXEMPT em NDF COMM: validar o MO basta. Se o EXEMPT fosse ignorado, a
# confirmação ficaria pendente para sempre numa mesa que nem olha esse produto.
check('o FO EXEMPT não segura a linha', M.find_row('T1')['VALIDADO p/ FO'], '')

print('\n== 3. MO e FO em paralelo ==')
novo('T2', produto='SWAP')
M.mark_validated('T2', M.STAGE_OTC, 'A111111')
check('as duas mesas ao mesmo tempo', M.find_row('T2')['Pending'], M.PENDING_MOFO)
M.mark_validated('T2', M.STAGE_FO, 'C333333')
check('validado só o FO, sobra o MO', M.find_row('T2')['Pending'], M.PENDING_MO)
M.mark_validated('T2', M.STAGE_MO, 'B222222')
check('validadas as duas, aguarda o envio', M.find_row('T2')['Pending'], M.PENDING_FEPWEB)
# O hold do jurídico (§254) VENCE a derivação até alguém soltá-lo — é o único
# valor de Pending que se escreve à mão, junto com o Pending OTC que o desfaz.
r2 = M.find_row('T2')
r2['Pending'] = M.PENDING_LEGAL
M.upsert_row(r2)
check('Pending Legal gravado vence a derivação', M.find_row('T2')['Pending'], M.PENDING_LEGAL)
r2 = M.find_row('T2')
r2['Pending'] = ''
M.upsert_row(r2)
check('   e solto, a derivação volta a mandar', M.find_row('T2')['Pending'], M.PENDING_FEPWEB)

# Produto cujo OTC é EXEMPT começa direto nas duas mesas.
novo('T3', produto='SWAP', lob='EDG')
check('OTC EXEMPT pula a primeira etapa', M.find_row('T3')['Pending'], M.PENDING_MOFO)

print('\n== 4. o Pending é derivado, não digitado ==')
M.upsert_row(M.blank_row(**{'Trade ID': 'T4', 'Produto': 'NDF COMM', 'LOB': 'CEM',
                            'Pending': 'Ok', 'Aging Confirmação': '999'}))
r = M.find_row('T4')
check('o Pending escrito à mão é ignorado', r['Pending'], M.PENDING_OTC)
check('o Aging também', r['Aging Confirmação'], '')
check('   e as duas estão marcadas como derivadas', sorted(M.DERIVED_COLUMNS),
      ['Aging Confirmação', 'Pending'])
# O aging conta da data de ENVIO para o OTC, não da data da operação: uma
# operação de três meses atrás cuja confirmação saiu ontem não está atrasada.
ontem = (datetime.now().date() - timedelta(days=1)).strftime('%d/%m/%Y')
antigo = (datetime.now().date() - timedelta(days=90)).strftime('%d/%m/%Y')
M.upsert_row(M.blank_row(**{'Trade ID': 'T5', 'Produto': 'NDF COMM',
                            'Data Operação': antigo, 'Data envio validação OTC': ontem}))
check('o aging é da pendência, não da operação', M.find_row('T5')['Aging Confirmação'], '1')

print('\n== 5. o reject devolve para o OTC e limpa o que já valeu ==')
novo('T6', produto='SWAP')
M.mark_validated('T6', M.STAGE_OTC, 'A111111')
M.mark_validated('T6', M.STAGE_MO, 'B222222')
r = M.reject('T6', M.STAGE_FO, 'C333333', 'notional errado')
check('volta para Pending OTC', r['Pending'], M.PENDING_OTC)
check('o Conferido OTC é limpo', r['Conferido OTC'], '')
check('o VALIDADO p/ MO também', r['VALIDADO p/ MO'], '')
check('   e o carimbo dele', r['Time Stamp MO'], '')
check('o reject fica registrado na mesa que devolveu',
      r['Time Stamp FO'].startswith('REJEITADO '), True)
check('   com o SPN de quem devolveu', 'C333333' in r['Time Stamp FO'], True)
check('e a linha volta para o banco pending', M.target_category(r), 'pending')

print('\n== 6. o carimbo leva hora e SPN ==')
novo('T7')
r = M.mark_validated('T7', M.STAGE_OTC, 'E930179')
stamp = r['Time Stamp OTC']
check('tem a data', datetime.now().strftime('%d/%m/%Y') in stamp, True)
check('tem o SPN', 'E930179' in stamp, True)
check('tem hora e minuto', len(stamp.split(' · ')[0]) == len('01/01/2026 00:00'), True)
check('sem SPN não inventa um', ' · —' in M.stamp_now(''), True)

print('\n== 6b. o prazo de cada mesa ==')
# Dias ÚTEIS a contar da DATA DA OPERAÇÃO (trade date), não da geração do
# documento: o prazo é do trade, e gerar a confirmação com atraso não compra
# tempo novo. As mesas correm em paralelo, então D+4 e D+6 saem do MESMO dia.
check('OTC D+3, MO D+4, FO D+6',
      [M.SLA_BIZDAYS[s] for s in (M.STAGE_OTC, M.STAGE_MO, M.STAGE_FO)], [3, 4, 6])
SEG = {'Data Operação': '03/08/2026'}                      # segunda-feira
check('o prazo é em dias ÚTEIS, não corridos',
      [M.fmt_date(M.sla_deadline(SEG, s)) for s in (M.STAGE_OTC, M.STAGE_MO, M.STAGE_FO)],
      ['06/08/2026', '07/08/2026', '11/08/2026'])          # D+6 pula o fim de semana
check('a linha sem data de operação não inventa prazo',
      M.sla_deadline({}, M.STAGE_OTC), None)

# A luz: verde com folga, âmbar na véspera e no dia, vermelha depois.
luzes = [M.sla_state(SEG, M.STAGE_OTC, date(2026, 8, d))['level']
         for d in (4, 5, 6, 7)]
check('verde → âmbar → vermelho', luzes, ['ok', 'warn', 'warn', 'late'])
# A etapa validada PARA de contar: mantê-la vermelha cobraria um trabalho feito.
check('a etapa já validada sai como done',
      M.sla_state(dict(SEG, **{'Conferido OTC': '20/08/2026'}),
                  M.STAGE_OTC, date(2026, 8, 31))['level'], 'done')

print('\n== 6c. fora do prazo, a justificativa é obrigatória ==')
novo('T8', **{'Data Operação': '01/01/2020'})              # prazo estourado há anos
falhou = False
try:
    M.mark_validated('T8', M.STAGE_OTC, 'E930179')
except M.SlaCommentRequired:
    falhou = True
check('sem motivo, o carimbo é RECUSADO', falhou, True)
check('   e a linha continua pendente', M.find_row('T8')['Pending'], M.PENDING_OTC)
r = M.mark_validated('T8', M.STAGE_OTC, 'E930179', 'arquivo da B3 saiu com atraso')
check('com motivo, valida', bool(r['Conferido OTC']), True)
# Uma coluna por mesa: o atraso do MO não explica o do FO.
check('   e o motivo fica na coluna da etapa',
      r['OTC Comments'], 'arquivo da B3 saiu com atraso')
check('   sem encostar nas outras', (r['MO Comments'], r['FO Comments']), ('', ''))
# Dentro do prazo ninguém precisa justificar nada.
novo('T9')
check('dentro do prazo, valida sem motivo',
      bool(M.mark_validated('T9', M.STAGE_OTC, 'E930179')['Conferido OTC']), True)

print('\n== 7. o Monitor ==')
p = M.monitor_payload()
por_label = {c['label']: c for c in p['cards']}
check('cinco cards, na ordem da esteira (Legal antes, FepWeb depois — §254)',
      [c['label'] for c in p['cards']],
      [M.PENDING_LEGAL, M.PENDING_OTC, M.PENDING_MO, M.PENDING_FO, M.PENDING_FEPWEB])
# T3 está em Pending MO/FO e tem de aparecer nos DOIS cards.
nos_dois = [c['label'] for c in p['cards']
            if any(i['key'] == 'T3' for i in c['items'])]
check('a linha parada nas duas mesas aparece nos dois cards',
      sorted(nos_dois), sorted([M.PENDING_MO, M.PENDING_FO]))
check('   e não no card do OTC (ela já passou / é isenta)',
      any(i['key'] == 'T3' for i in por_label[M.PENDING_OTC]['items']), False)
check('o item traz o que identifica a confirmação sem abrir',
      sorted(por_label[M.PENDING_OTC]['items'][0].keys()),
      sorted(list(M.MONITOR_FIELDS) +
             ['Tipo', 'sla', 'key', 'keys', 'trades', 'count', 'stage', 'docs']))

# ── A falta de Data Callback nos cards fora das mesas ────────────────────────
# É CONTAGEM e não bandeira: um documento cobre várias operações, e "falta
# callback" num grupo de dez não diz se falta em uma ou nas dez. Só o card de
# Pending FepWeb a mostra (a tela decide) — ali a confirmação está validada
# esperando o envio, e o callback é o que precisa ter acontecido antes dele.
def _fep(tid, cli, cb):
    r = M.blank_row(**{'Trade ID': tid, 'Cliente': cli, 'Produto': 'FXO', 'LOB': 'CEM',
                       'Moeda': 'USD', 'Data Operação': '05/08/2026', 'Data Callback': cb})
    r['Pending'] = M.PENDING_FEPWEB
    return r


_cb_card = M._extra_card('FEPWEB', M.PENDING_FEPWEB, [
    _fep('CB1', 'ACME', ''), _fep('CB2', 'ACME', ''),
    _fep('CB3', 'BETA', '01/08/2026'), _fep('CB4', 'BETA', '01/08/2026'),
    _fep('CB5', 'GAMA', ''), _fep('CB6', 'GAMA', '01/08/2026')])
_cb = {i['Cliente']: i['no_callback'] for i in _cb_card['items']}
check('o grupo sem callback nenhum conta as duas', _cb['ACME'], 2)
check('   o grupo com callback nas duas não é marcado', _cb['BETA'], 0)
check('   e o misto conta só a que falta', _cb['GAMA'], 1)
check('   com a luz do prazo da ETAPA daquele card',
      sorted(por_label[M.PENDING_OTC]['items'][0]['sla'].keys()),
      ['deadline', 'left', 'level'])
# `Tipo` é o produto no nome do Confirmation Type; `Produto` continua CRU no
# item porque é ele que resolve a pasta do Electronic Inventory em /docs.
check('   com o Tipo ao lado do Produto cru',
      (por_label[M.PENDING_OTC]['items'][0]['Produto'],
       por_label[M.PENDING_OTC]['items'][0]['Tipo']),
      ('NDF COMM', 'NDF COMM'))

# ── O item do card é a CONFIRMAÇÃO, não o trade ──────────────────────────────
# O documento é emitido por contraparte × produto × data e cobre todas as
# operações do grupo. Mostrar um item por trade faria a mesma folha aparecer dez
# vezes na fila — e validar dez vezes o mesmo papel.
for i in (1, 2, 3):
    novo('GRP%d' % i, produto='NDF COMM')
    r = M.find_row('GRP%d' % i)
    r['Data Operação'] = '05/08/2026'
    M.upsert_row(r)
p = M.monitor_payload()
card_otc = next(c for c in p['cards'] if c['label'] == M.PENDING_OTC)
grp = next((i for i in card_otc['items'] if i['Data Operação'] == '05/08/2026'), None)
check('as três operações do mesmo cliente/dia viram UM item', bool(grp), True)
check('   com as três chaves juntas', sorted(grp['keys']), ['GRP1', 'GRP2', 'GRP3'])
check('   e a contagem de operações', grp['count'], 3)
check('o card conta CONFIRMAÇÕES no total',
      card_otc['count'], len(card_otc['items']))
check('   e as operações à parte',
      p['cards'][0]['trades'], sum(i['count'] for i in p['cards'][0]['items']))
# A LOB entra na chave: mesma contraparte e dia em LOBs diferentes são dois
# documentos, e juntá-los faria uma validação carimbar a folha da outra mesa.
# O ATIVO idem: OLEO e PLATTS do mesmo dia são dois papéis — agrupados, um
# Validar daria baixa nos dois.
check('a chave do grupo é LOB × Cliente × Produto × Data × Ativo',
      M.GROUP_FIELDS, ('LOB', 'Cliente', 'Produto', 'Data Operação', 'Moeda'))
check('   e ignora pontuação do nome',
      M.group_key({'LOB': 'CEM', 'Cliente': 'ACME  S.A.', 'Produto': 'NDF COMM',
                   'Data Operação': '05/08/2026'}) ==
      M.group_key({'LOB': 'cem', 'Cliente': 'Acme S/A.', 'Produto': 'ndf comm',
                   'Data Operação': '05/08/2026'}), True)
# A pasta do documento sai da própria linha: é o que faz o Abrir funcionar nas
# confirmações anteriores ao carimbo, que são as que alguém precisa procurar.
cli, rel = M.confirmation_folder({'Cliente': 'ACME S.A.', 'Produto': 'NDF COMM',
                                  'Data Operação': '05/08/2026'})
check('a pasta da confirmação vem da linha', (cli, rel),
      ('ACME S.A.', 'Confirmations/2026/08. August/05/NDF COMM'))
# A pasta É o código do tipo. O share já está cheio de pastas com esse nome (é
# como o upload manual sempre gravou), e ter um segundo nome só para a escrita
# do app recriava pela outra ponta a divergência que a unificação resolveu.
check('   e a pasta é o próprio código do tipo',
      [M.TYPE_FOLDER[t] for t in M.CONFIRMATION_TYPES], list(M.CONFIRMATION_TYPES))
# As pastas de nome antigo continuam CHEIAS no share. Quem procura o documento
# tem de olhar nelas também — senão unificar o nome apagaria da tela toda
# confirmação anterior, com os arquivos intactos lá.
cli2, rels = M.confirmation_folders({'Cliente': 'ACME S.A.', 'Produto': 'NDF COMM',
                                     'Data Operação': '05/08/2026'})
check('   e a busca cobre também a pasta antiga', rels,
      ['Confirmations/2026/08. August/05/NDF COMM',
       'Confirmations/2026/08. August/05/NDF Commodities'])
check('   com a pasta de ESCRITA sempre em primeiro', rels[0], rel)
check('   e todo tipo com o seu histórico declarado',
      sorted(M.TYPE_FOLDER_LEGACY), sorted(M.CONFIRMATION_TYPES))
check('   e o nome da pasta é o mesmo que o save grava',
      sorted(set(M.PRODUCT_FOLDER.values())),
      sorted(set(M.TYPE_FOLDER.values())))
# TYPE_FOLDER é bijetora: duas pastas com o mesmo nome fundiriam dois tipos, e
# `_FOLDER_TYPE` (que é o inverso dela) devolveria só um deles.
check('   e cada tipo tem uma pasta só sua',
      (len(M.TYPE_FOLDER), len(set(M.TYPE_FOLDER.values())), len(M._FOLDER_TYPE)),
      (len(M.CONFIRMATION_TYPES), len(M.CONFIRMATION_TYPES), len(M.CONFIRMATION_TYPES)))
# 'OPTION' (New Deals) e 'FXO' (Electronic Inventory / cadastro) são o MESMO
# produto com dois nomes, e têm de cair na mesma pasta — a linha criada pelo
# Track vem com o segundo, e sem esta entrada ela ficaria sem PDF.
check('   e FXO é a mesma pasta de OPTION',
      (M.PRODUCT_FOLDER.get('FXO'), M.PRODUCT_FOLDER.get('OPTION')),
      ('FXO', 'FXO'))

print('\n== 7b. o tipo de confirmação é UMA lista só ==')
check('os doze tipos', list(M.CONFIRMATION_TYPES),
      ['NDF VANILLA', 'NDF FWD START', 'NDF OTHER PUBLISHER', 'NDF COMM',
       'OPTION COMM', 'FXO', 'SWAP', 'SWAP CORPORATE', 'TERMO DE RESILICAO',
       # Os tres documentos que ALTERAM uma confirmacao ja emitida, em vez de
       # confirmar operacao nova.
       'AMENDMENT', 'ADDENDUM', 'RERATIFICATION'])
# Tipo novo mexe em TRES listas, e a falta de qualquer uma erra em silencio: sem
# TYPE_FOLDER_LEGACY o tipo nao se distingue de um cujo historico alguem esqueceu
# de declarar; sem VALIDATION_SEED ele cai no DEFAULT_RULE sem ninguem decidir.
for _t in ('AMENDMENT', 'ADDENDUM', 'RERATIFICATION'):
    check('   %s nas tres listas' % _t,
          [_t in M.TYPE_FOLDER, _t in M.TYPE_FOLDER_LEGACY,
           any(r['PRODUCT'] == _t for r in M.VALIDATION_SEED)],
          [True, True, True])
# Os códigos são ASCII, e não por estilo: `confirmation_type` compara
# `upper_norm(produto)` com a tupla, e o upper_norm descarta as marcas de
# combinação — um código acentuado não casaria consigo mesmo, em silêncio.
check('   e sem acento, senão o tipo não casa consigo mesmo',
      [t for t in M.CONFIRMATION_TYPES if M.upper_norm(t) != t], [])
check('   e o tipo novo resolve de ida e volta',
      (M.confirmation_type('TERMO DE RESILICAO'),
       M.confirmation_type('Termo de Resilição'),
       M.TYPE_FOLDER['TERMO DE RESILICAO']),
      ('TERMO DE RESILICAO', 'TERMO DE RESILICAO', 'TERMO DE RESILICAO'))
# O nome antigo ficou em cadastros já salvos e em pastas já gravadas. Traduzi-lo
# é o que impede o `select` do mapping de abrir sem a opção da linha — e o
# primeiro Save trocaria o produto dela sem ninguém pedir.
check('   e o nome antigo do Other Publisher ainda traduz',
      M.confirmation_type('OTHER PUBLISHER'), 'NDF OTHER PUBLISHER')
# São CÓDIGOS, não rótulos: a comparação entre as telas é feita sobre eles, e um
# 'Ndf Vanilla' cadastrado pela tela não casaria com o 'NDF VANILLA' do banco.
check('   todos em maiúsculo', [t for t in M.CONFIRMATION_TYPES if t != t.upper()], [])
check('o nome do New Deals vira o do Electronic Inventory',
      [M.confirmation_type('OPTION'), M.confirmation_type('NDF FWD START')],
      ['FXO', 'NDF FWD START'])
# As três páginas de NDF gravam o mesmo Product Type e têm cada uma o seu tipo:
# o documento que sai de cada uma é diferente.
check('   e o NDF de moeda sem quebra é o Vanilla',
      M.confirmation_type('NDF'), 'NDF VANILLA')
check('o swap corporativo é um tipo próprio',
      [M.confirmation_type('SWAP'), M.confirmation_type('SWAP CORPORATIVO')],
      ['SWAP', 'SWAP CORPORATE'])
# A linha legada tem Produto 'NDF' — que POR ACASO está na lista — e é o LOB que
# diz que ela é de mercadoria. Devolver 'NDF' direto a classificaria como termo
# de moeda: outro documento, outra pasta, outra regra de validação.
check('   e a planilha legada é lida pelo par Produto × LOB',
      M.confirmation_type('NDF', 'COMMODITY'), 'NDF COMM')
check('produto que não se sabe traduzir volta como veio',
      M.confirmation_type('Coisa Nova'), 'COISA NOVA')
# O cadastro é feito com 'FXO'; a linha do banco carrega 'OPTION'. Sem o tradutor
# nos DOIS lados, ela caía no DEFAULT_RULE com aviso de "produto sem cadastro".
write_map([{'PRODUCT': 'FXO', 'LOB': '', 'OTC': 'REQUESTED', 'MO': 'EXEMPT', 'FO': 'REQUESTED'}])
check('a regra cadastrada como FXO rege a linha gravada como OPTION',
      M.rule_for('OPTION', 'CEM'),
      ({'OTC': True, 'MO': False, 'FO': True}, True))
write_map(MAPA)      # o cadastro do teste de volta — as seções seguintes leem dele
check('a nomenclatura da planilha legada resolve a MESMA pasta',
      M.confirmation_folder({'Cliente': 'REFINARIA', 'Produto': 'NDF',
                             'LOB': 'COMMODITY', 'Data Operação': '03/08/2026'})[1],
      'Confirmations/2026/08. August/03/NDF COMM')
check('sem produto conhecido nao inventa pasta',
      M.confirmation_folder({'Cliente': 'X', 'Produto': '?', 'Data Operação': '05/08/2026'}),
      (None, None))
# Produto sem cadastro → aviso na tela.
novo('T8', produto='PRODUTO NOVO')
p = M.monitor_payload()
check('produto sem cadastro vira aviso', any('PRODUTO NOVO' in w for w in p['warnings']), True)

print('\n== 8. as colunas ==')
check('31 colunas na tela', len(M.COLUMNS), 31)
# O `Athena ID` SAIU: para os produtos chaveados pelo Deal ele repetia o Trade ID
# e no FWD Start vinha vazio — não acrescentava nada em linha nenhuma. A coluna
# continua no banco (`ensure_db` só acrescenta), então o dado antigo está lá.
check('   o Athena ID não está mais na tela', 'Athena ID' in M.COLUMNS, False)
check('   e o B3 ID vem logo depois da chave',
      M.COLUMNS[M.COLUMNS.index('Trade ID') + 1], 'Cetip ID')
# O nome da coluna é da planilha legada; o que o código escreve nela é o B3_ID.
check('   e o rótulo do Cetip ID diz o que está lá',
      M.COLUMN_LABELS.get('Cetip ID'), 'B3 ID')
# Uma coluna de justificativa POR MESA, ao lado do carimbo dela. Uma só,
# compartilhada, faria a segunda mesa sobrescrever a explicação da primeira.
check('   uma coluna de comentário por etapa',
      [M.STAGE_COMMENT_COLUMN[s] for s in (M.STAGE_OTC, M.STAGE_MO, M.STAGE_FO)],
      ['OTC Comments', 'MO Comments', 'FO Comments'])
check('   e todas na tabela', [c for c in M.STAGE_COMMENT_COLUMN.values()
                               if c not in M.COLUMNS], [])
check('o Trade ID repetido do arquivo virou uma só',
      M.COLUMNS.count('Trade ID'), 1)
check('os três Time Stamp têm nome próprio no banco',
      [c for c in M.COLUMNS if c.startswith('Time Stamp')],
      ['Time Stamp OTC', 'Time Stamp MO', 'Time Stamp FO'])
# O rótulo da tela é INGLÊS e o mapa é COMPLETO: os nomes das colunas são os da
# planilha legada (em português, e são o esquema dos dois DuckDB — renomeá-los
# quebraria o banco de quem já o tem), então quem traduz é este mapa. Coluna sem
# entrada apareceria na tela com o nome do banco, e é isso que a completude pega.
check('   toda coluna tem rótulo',
      [c for c in M.COLUMNS if c not in M.COLUMN_LABELS], [])
check('   e o rótulo é o nome em inglês da coluna',
      [M.COLUMN_LABELS[c] for c in ('Data de vencimento', 'Data Operação', 'Moeda',
                                    'Notional', 'Cliente', 'Cetip ID',
                                    'Aging Confirmação', 'Produto')],
      ['Settlement Date', 'Trade Date', 'Underlying Asset', 'Notional/Qty',
       'Counterparty', 'B3 ID', 'Aging', 'Product'])
# Os três carimbos compartilham o rótulo curto de propósito: cada um aparece
# encostado no VALIDADO da sua mesa, que é como a planilha era lida.
check('   e os três carimbos dividem o rótulo curto',
      sorted({M.COLUMN_LABELS[c] for c in M.COLUMNS if c.startswith('Time Stamp')}),
      ['Time Stamp'])
check('o link do documento fica FORA da tabela',
      ('Confirmation Link' in M.DB_COLUMNS, 'Confirmation Link' in M.COLUMNS),
      (True, False))
check('a chave é o Trade ID', M.KEY_COLUMN, 'Trade ID')

print('\n== 9. só os produtos que geram confirmação entram ==')
from apps.pages import routes as R                                # noqa: E402
check('os quatro produtos', sorted(R._MC_CONFIRMATION_SOURCES),
      ['NDF COMM', 'NDF FWD START', 'OPTION', 'OPTION COMM'])
# As três páginas genéricas de NDF gravam o MESMO Product Type: o recorte tem de
# ser pelo `source`, senão Vanilla e Other Publisher entrariam junto.
check('as três páginas de NDF gravam o mesmo Product Type',
      sorted(set(R._GENERIC_ND_PC_TYPE.values())), ['NDF'])
check('e só o FWD Start tem source de confirmação',
      R._GENERIC_ND_MC_SOURCE, {'fwd-start': 'NDF FWD START'})
check('   que é um dos quatro',
      R._GENERIC_ND_MC_SOURCE['fwd-start'] in R._MC_CONFIRMATION_SOURCES, True)
# O upload manual do Electronic Inventory e o `save` do app gravavam em pastas
# DIFERENTES para o mesmo produto ('FXO' × 'FX Options'), e o Monitor procura só
# onde o app grava — a confirmação subida à mão ficava invisível para ele.
check('o Confirmation Type do upload é a MESMA lista',
      list(R._EI_CONFIRMATION_TYPES), list(M.CONFIRMATION_TYPES))
check('   e todo tipo do upload sabe em que pasta gravar',
      [t for t in R._EI_CONFIRMATION_TYPES if t not in M.TYPE_FOLDER], [])
check('o seed cobre todos os tipos',
      sorted({s['PRODUCT'] for s in R._MC_VALIDATION_SEED}),
      sorted(M.CONFIRMATION_TYPES))

print('\n== 8b. o E-mail Subject sai do recap que está na pasta ==')
# O casamento é em dois passos, e a ordem separa o certo do plausível. A versão
# que pegava "o primeiro recap da pasta" carimbava o assunto da DBH-1AAA também
# na DBH-1BBB, e dava a uma operação SEM recap próprio o e-mail de outra
# confirmação — a pasta é cliente × dia × produto e guarda mais de uma.
def _mail(nome, assunto):
    return {'name': nome, 'email': True, 'subject': assunto, 'url': ''}


_PDF = {'name': 'ACME - USD - DBH-1AAA', 'url': ''}
_R1 = _mail('Internal Recap DBH-1AAA', 'Recap - DBH-1AAA')
_R2 = _mail('Internal Recap DBH-1BBB', 'Recap - DBH-1BBB')
_RU = _mail('Internal Recap ACME 05-08-2026', 'Recap - ACME 05/08')

check('cada operação leva o recap que a NOMEIA',
      R._mc_sync_email_subjects([_PDF, _R1, _R2], ['DBH-1AAA', 'DBH-1BBB']),
      {'DBH-1AAA': 'Recap - DBH-1AAA', 'DBH-1BBB': 'Recap - DBH-1BBB'})
# Recap único sem nome de operação é o do booking: vale para o grupo inteiro.
check('   recap único sem nome de operação vale para o grupo',
      R._mc_sync_email_subjects([_PDF, _RU], ['DBH-1AAA', 'DBH-1BBB']),
      {'DBH-1AAA': 'Recap - ACME 05/08', 'DBH-1BBB': 'Recap - ACME 05/08'})
# Vários recaps e nenhum nomeando operação é escolha às cegas: célula vazia pede
# o dado, célula errada aponta para um e-mail que não confirma aquele trade.
check('   vários recaps sem nome de operação não escrevem nada',
      R._mc_sync_email_subjects([_PDF, _RU, _mail('Recap ACME reenvio', 'X')],
                                ['DBH-1AAA']), {})
check('   e a operação sem recap próprio também não',
      R._mc_sync_email_subjects([_PDF, _R1, _R2], ['DBH-9ZZZ']), {})
check('   PDF não é e-mail', R._mc_sync_email_subjects([_PDF], ['DBH-1AAA']), {})

# A gravação só toca o que MUDOU: sem isso, cada abertura do Monitor reescreveria
# a esteira inteira (o upsert apaga e reinsere a linha nos dois bancos).
M.upsert_row(M.blank_row(**{'Trade ID': 'SUBJ1', 'Cliente': 'ACME',
                            'Produto': 'FXO', 'LOB': 'CEM'}))
check('grava o assunto na linha', M.set_email_subjects({'SUBJ1': 'Recap - X'}), 1)
check('   e a célula ficou com ele',
      M.find_row('SUBJ1')['E-mail Subject'], 'Recap - X')
check('   reescrever o MESMO assunto não grava nada',
      M.set_email_subjects({'SUBJ1': 'Recap - X'}), 0)
check('   assunto novo sobrescreve (o e-mail é a fonte da coluna)',
      (M.set_email_subjects({'SUBJ1': 'Recap - Y'}),
       M.find_row('SUBJ1')['E-mail Subject']), (1, 'Recap - Y'))
check('   chave inexistente não cria linha',
      (M.set_email_subjects({'NAO-EXISTE': 'Z'}), M.find_row('NAO-EXISTE')), (0, None))
M.delete_row('SUBJ1')

print('\n== 8c. o Notional Amount CCY e o anexo do BACC ==')
# A coluna guarda moeda e valor num texto só ('USD 1500000'), porque é assim que
# ela é lida na tela — valor sem moeda ao lado não diz nada em quem opera duas
# moedas no mesmo dia. Quem reparte é UMA função; um split espalhado pelos
# consumidores divergiria no primeiro valor com separador de milhar.
check('a coluna nasce à direita do Notional',
      M.COLUMNS.index('Notional Amount CCY') - M.COLUMNS.index('Notional'), 1)
check('   e reparte em (moeda, valor)',
      [M.split_notional_ccy(v) for v in
       ('USD 1500000', 'BRL  250000,50 ', '', '1500000', 'OLEO 10')],
      [('USD', '1500000'), ('BRL', '250000,50'), ('', ''),
       ('', '1500000'), ('', 'OLEO 10')])

# A MOEDA sai do campo daquele produto, não de uma cadeia de fallback: cada um
# guarda o valor num lugar, e o primeiro campo preenchido nem sempre é o que a
# mesa chama de moeda do notional.
_D = {'StrikeCurrency': 'USD', 'QuantityCurrency': 'BRL'}
check('mercadoria e FXO usam o Strike Currency',
      [R._mc_notional_ccy(_D, s, '1500000')
       for s in ('NDF COMM', 'OPTION COMM', 'OPTION')],
      ['USD 1500000'] * 3)
check('   e o FWD Start o Quantity Currency',
      R._mc_notional_ccy(_D, 'NDF FWD START', '1500000'), 'BRL 1500000')
# Sem moeda a célula sai só com o número: em branco ela perderia o notional
# junto, e o valor sem moeda ainda é o valor.
check('   sem moeda no deal fica só o número',
      R._mc_notional_ccy({}, 'OPTION', '1500000'), '1500000')
check('   e sem notional não sobra nada',
      R._mc_notional_ccy(_D, 'OPTION', ''), '')


def _bacc_linha(tid, aging, pend, ccy, notional, cb=''):
    r = M.blank_row(**{'Trade ID': tid, 'Cliente': 'ACME', 'Produto': 'FXO',
                       'LOB': 'CEM', 'Notional': notional, 'Data Callback': cb,
                       'Notional Amount CCY': ((ccy + ' ' + notional) if ccy else notional)})
    r['Aging Confirmação'] = aging
    r['Pending'] = pend
    return r


_FAKE = [_bacc_linha('T-A', '3', 'Pending OTC', 'USD', '1500000'),
         _bacc_linha('T-B', '12', 'Pending MO', 'BRL', '250000.50'),
         _bacc_linha('T-C', '', 'Pending FO', '', '999'),
         _bacc_linha('T-D', '99', 'Ok', 'USD', '1'),
         _bacc_linha('T-E', '40', 'Pending OTC', 'EUR', '77', cb='01/08/2026')]
_orig_load = M.load_all
M.load_all = lambda: _FAKE
try:
    _saida = R._bacc_rows()
finally:
    M.load_all = _orig_load
# Dois cortes que respondem perguntas diferentes: o callback fecha a operação do
# ponto de vista da métrica; o `Ok` é o fim da esteira. E a ordem é a da fila —
# quem espera há mais tempo primeiro. Por texto, '3' viria depois de '12'.
check('o anexo tira o Ok e o que já tem callback, e ordena pelo aging',
      [r['Trade ID'] for r in _saida], ['T-B', 'T-A', 'T-C'])

check('as doze colunas da planilha, na ordem pedida',
      [h for h, _s, _k in R._BACC_COLUMNS],
      ['Trade ID', 'Product', 'Trade Date', 'Legal Entity', 'Conterparty Name',
       'Aging', 'Born Age', 'Notional/Qty', 'National Currency',
       'Notional Amount', 'Comments', 'LOB'])
# O notional ocupa TRÊS colunas, e as duas últimas saem repartidas da coluna
# nova. A moeda não sai da coluna `Moeda`: aquela é o ATIVO, e em mercadoria
# guarda a commodity (OLEO), que não é moeda nenhuma.
check('   a moeda e o valor saem da coluna nova',
      (R._bacc_ccy(_FAKE[0]), R._bacc_amount(_FAKE[0])), ('USD', '1500000'))
check('   e a linha sem moeda sai com a célula da moeda vazia',
      (R._bacc_ccy(_FAKE[2]), R._bacc_amount(_FAKE[2])), ('', '999'))
# Número que não parseia sairia como TEXTO no Excel — sem somar e sem ordenar.
# A versão anterior escrevia como inteiro só o que "parecia dígito", e um
# notional com centavos não passava no teste.
check('o valor vira número de verdade nas duas escritas',
      [R._bacc_num(v) for v in ('1500000', '250000.50', '1.500.000,00', '', 'n/a')],
      [1500000, 250000.5, 1500000, None, None])
_ws = R._bacc_build_xlsx(_saida).active
_hdr = [c.value for c in _ws[1]]
_linha = {_hdr[i]: c.value for i, c in enumerate(_ws[2])}
check('   e chega ao xlsx como número',
      [_linha['Notional/Qty'], _linha['National Currency'],
       _linha['Notional Amount'], _linha['Aging']],
      [250000.5, 'BRL', 250000.5, 12])
check('   Born Age continua sempre vazia',
      [r[6].value for r in _ws.iter_rows(min_row=2)], [None, None, None])
# A máscara vai no CÓDIGO invariante do formato de arquivo (',' = milhar,
# '.' = decimal). Quem desenha é o Excel de quem abre, com o separador do idioma
# dele — num Excel pt-BR este código sai '1.500.000,00', que é a máscara pedida.
# Escrever '#.##0,00' aqui produziria um código malformado, e o valor sairia
# errado sem erro nenhum.
check('as duas colunas de valor levam a máscara de milhar',
      [_ws.cell(row=2, column=_hdr.index(c) + 1).number_format
       for c in ('Notional/Qty', 'Notional Amount')], ['#,##0.00'] * 2)
# O Aging é CONTAGEM, não valor: '12,00' dias não quer dizer nada.
check('   e o Aging não leva',
      _ws.cell(row=2, column=_hdr.index('Aging') + 1).number_format, 'General')
# Máscara sobre texto não faz nada, mas prometeria um número.
_ws2 = R._bacc_build_xlsx([_bacc_linha('T-X', '1', 'Pending OTC', 'EUR', 'n/a')]).active
check('   valor que não parseia fica texto, e sem máscara',
      (_ws2.cell(row=2, column=8).value, _ws2.cell(row=2, column=8).number_format),
      ('n/a', 'General'))

print('\n== 9b. o upgrade do cadastro de validação ==')
ANTIGO = [
    {'PRODUCT': 'NDF COMM', 'LOB': '', 'OTC': 'REQUESTED', 'MO': 'REQUESTED', 'FO': 'EXEMPT'},
    {'PRODUCT': 'OPTION', 'LOB': '', 'OTC': 'EXEMPT', 'MO': 'REQUESTED', 'FO': 'EXEMPT'},
    {'PRODUCT': 'NDF FWD START', 'LOB': '', 'OTC': 'REQUESTED', 'MO': 'REQUESTED', 'FO': 'EXEMPT'},
    {'PRODUCT': 'OPTION EDG', 'LOB': '', 'OTC': 'REQUESTED', 'MO': 'REQUESTED', 'FO': 'REQUESTED'},
]
mig = R._mc_validation_upgrade([dict(r) for r in ANTIGO])
por_par = {(r['PRODUCT'], r['LOB']): r for r in mig}
check('o nome do New Deals vira o tipo', ('FXO', '') in por_par, True)
# 'OPTION EDG' nunca foi um produto: era a opção de câmbio NA LOB EDG. Sem esta
# conversão a regra "no EDG o FO também valida" não regeria linha nenhuma.
check('OPTION EDG vira FXO × LOB EDG', ('FXO', 'EDG') in por_par, True)
check('   e mantém o FO pedido', por_par[('FXO', 'EDG')]['FO'], 'REQUESTED')
# A edição feita na tela tem de sobreviver ao upgrade, senão o cadastro brigaria
# com o usuário a cada leitura.
check('a regra editada à mão é preservada', por_par[('FXO', '')]['OTC'], 'EXEMPT')
# Tipo sem linha nenhuma entra com a do seed: sem isso ele cairia no DEFAULT_RULE
# (OTC + MO), que para o SWAP CORPORATE é a regra ERRADA — nele o FO valida.
check('tipo sem linha ganha a do seed',
      sorted({r['PRODUCT'] for r in mig}), sorted(M.CONFIRMATION_TYPES))
check('   com a regra certa no SWAP CORPORATE',
      por_par.get(('SWAP CORPORATE', ''), {}).get('FO'), 'REQUESTED')
check('e o upgrade é idempotente',
      R._mc_validation_upgrade([dict(r) for r in mig]), mig)
check('o FWD Start é chaveado pelo B3 ID, os outros pelo Deal',
      (R._mc_conf_trade_keys([({'Deal': 'D1', 'B3_ID': 'B1'}, None)], 'ndf-fwdstart'),
       R._mc_conf_trade_keys([({'Deal': 'D1', 'B3_ID': 'B1'}, None)], 'ndf-comm')),
      (['B1'], ['D1']))

print('\n== 10. as telas ==')
from apps import create_app                                       # noqa: E402
from apps.config import DebugConfig                               # noqa: E402
app = create_app(DebugConfig)
cl = app.test_client()
with cl.session_transaction() as s:
    s['authenticated'] = True
    s['user_sid'] = 'T000000'
    s['user_name'] = 'T'
    s['user_role'] = 'ADMIN'
    s['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()
check('o item antigo do menu leva ao Monitor',
      cl.get('/manual-confirmation').status_code, 302)
check('o Monitor abre', cl.get('/manual-confirmation/monitor').status_code, 200)
check('o Track abre', cl.get('/manual-confirmation/track').status_code, 200)

# ── Gerar é gravar ──────────────────────────────────────────────────────────
# O checklist do New Deals fecha o ciclo do DOCUMENTO (New → Generated →
# Success); ele NÃO carimba a etapa do OTC na esteira. Carimbando, a confirmação
# nascia já na mesa seguinte e a fila do OTC no Monitor ficava vazia por
# construção — a mesa não tinha onde conferir o que ela mesma acabara de emitir.
check('a geração no New Deals não valida o OTC da esteira',
      hasattr(R, '_mc_stamp_otc_validated'), False)
check('   mas continua carimbando que o documento saiu',
      hasattr(R, '_mc_stamp_generated'), True)

# Os dois botões vivem na TELA DE VALIDAÇÃO, não no card: validar e rejeitar são
# as duas respostas à mesma pergunta, e as duas exigem ter aberto o documento.
MON = cl.get('/manual-confirmation/monitor').data.decode('utf-8')
check('o card do Monitor não rejeita', 'data-mc-reject' in MON, False)
check('   e o Validate abre a tela de validação',
      '/manual-confirmation/validate?stage=' in MON, True)
HTML = cl.get('/manual-confirmation/track').data.decode('utf-8')
# O que vem do servidor sai num bloco `application/json`, e não interpolado no
# meio do JS: `var X = {{ … }}` roda, mas o editor lê o <script> como JavaScript
# puro e acusa erro de sintaxe numa página que funciona.
import json as _json                                                # noqa: E402
_boot = _json.loads(HTML.split('id="mc-boot">')[1].split('</script>')[0])
check('a tela recebe as colunas do servidor', _boot['columns'], list(M.COLUMNS))
check('   pelo bloco de dados, sem Jinja no meio do JS',
      ('var COLUMNS = BOOT.columns' in HTML, '{{' in HTML), (True, False))
# A tela não pode ter uma LISTA de colunas própria — ela desalinharia do
# servidor em silêncio na primeira coluna nova. O que ela tem é um mapa de
# TRADUÇÃO (COLTR), chaveado pelos mesmos nomes que o payload traz e com
# fallback para o rótulo inglês do servidor: um mapa que traduz não é uma
# segunda lista, e coluna sem entrada nele aparece em inglês, não some.
check('   e não monta a própria lista de colunas',
      ('var COLUMNS = [' in HTML, 'COLUMNS = BOOT.columns' in HTML), (False, True))
check('   o mapa de tradução cai no rótulo do servidor',
      'return (m && m[c]) || LABELS[c] || c;' in HTML, True)
check('   e traduz para os três idiomas', ('COLTR = {' in HTML,
      HTML.count("'Data de vencimento':")), (True, 2))
check('o Trade ID fica fora da edição em massa',
      "c !== KEY" in HTML and 'isDerived(c)' in HTML, True)
# ── Cada etapa é assinada pela SUA mesa ─────────────────────────────────────
# Pending OTC é do Back Office, Pending MO do MO, Pending FO do FO. É o que
# separa as funções: quem monta o documento não pode assiná-lo pela mesa
# seguinte. A tela esconde o botão, mas a trava que vale é a do endpoint — sem
# ela um POST direto assinaria pela mesa de qualquer um.
def _como(papel):
    with cl.session_transaction() as ss:
        ss['user_role'] = papel


# A matriz cobre os TRES positivos e os cruzamentos: so provar o 403 deixaria
# passar uma regra que nega tudo, e so provar o 200 deixaria passar uma que
# libera tudo.
for _papel, _etapa, _esperado in (('BO', 'OTC', 200), ('MO', 'MO', 200), ('FO', 'FO', 200),
                                  ('BO', 'MO', 403), ('BO', 'FO', 403),
                                  ('MO', 'OTC', 403), ('MO', 'FO', 403),
                                  ('FO', 'OTC', 403), ('FO', 'MO', 403),
                                  ('ADMIN', 'OTC', 403), ('ADMIN', 'MO', 403),
                                  ('ADMIN', 'FO', 403), ('HUB', 'FO', 403)):
    _como(_papel)
    check('%-5s não assina o Pending %s' % (_papel, _etapa) if _esperado == 403
          else '%-5s assina o Pending %s' % (_papel, _etapa),
          cl.post('/api/manual-confirmation/validate',
                  json={'key': 'T7', 'stage': _etapa}).status_code, _esperado)
# Rejeitar é a outra resposta à MESMA pergunta, então segue a mesma mesa.
_como('FO')
check('quem não assina a etapa também não a devolve',
      cl.post('/api/manual-confirmation/reject',
              json={'key': 'T7', 'stage': 'MO', 'comment': 'x'}).status_code, 403)

# O SPN do carimbo vem da SESSÃO: mandar outro no corpo não pode valer.
_como('MO')
r = cl.post('/api/manual-confirmation/validate',
            json={'key': 'T7', 'stage': 'MO', 'sid': 'INVASOR'})
check('o SPN do POST é ignorado',
      'INVASOR' not in (r.get_json().get('row') or {}).get('Time Stamp MO', ''), True)
check('   e vale o da sessão',
      'T000000' in (r.get_json().get('row') or {}).get('Time Stamp MO', ''), True)
check('reject sem comentário é recusado',
      cl.post('/api/manual-confirmation/reject',
              json={'key': 'T7', 'stage': 'MO', 'comment': ' '}).status_code, 400)
check('só MO e FO rejeitam',
      cl.post('/api/manual-confirmation/reject',
              json={'key': 'T7', 'stage': 'OTC', 'comment': 'x'}).status_code, 400)
# ── Preencher a coluna de validação pela GRADE é validar ───────────────────
# A tela de validação passa pelo `mark_validated` — carimba quem assinou, cobra a
# justificativa fora do prazo e exige a mesa certa. O Track escrevia a MESMA
# coluna como texto livre: a validação entrava sem dono, sem motivo do atraso e
# assinada por qualquer papel, e a segregação valia só no caminho de cima.
_velho = M.fmt_date(date.today() - timedelta(days=60))
novo('G1', produto='SWAP', **{'Data Operação': _velho})          # OTC pendente e atrasado

_como('MO')
check('a grade não deixa o MO assinar pelo OTC',
      cl.post('/api/manual-confirmation/upsert',
              json={'rows': [{'Trade ID': 'G1', 'Conferido OTC': _velho}]}).status_code, 403)

_como('BO')
_r = cl.post('/api/manual-confirmation/upsert',
             json={'rows': [{'Trade ID': 'G1', 'Conferido OTC': _velho}]})
check('   e fora do prazo cobra a justificativa', _r.status_code, 409)
check('      dizendo em qual coluna escrever',
      _r.get_json().get('column'), 'OTC Comments')
check('      sem gravar nada', M.find_row('G1').get('Conferido OTC'), '')

_r = cl.post('/api/manual-confirmation/upsert',
             json={'rows': [{'Trade ID': 'G1', 'Conferido OTC': _velho,
                             'OTC Comments': 'documento chegou atrasado'}]})
check('   com o motivo, grava', _r.status_code, 200)
check('      e CARIMBA quem assinou',
      'T000000' in (M.find_row('G1').get('Time Stamp OTC') or ''), True)
check('      mantendo a data digitada', M.find_row('G1').get('Conferido OTC'), _velho)

# Desfazer a validação não pode deixar o carimbo para trás: ele afirmaria que
# alguém assinou uma etapa que voltou a ficar pendente.
cl.post('/api/manual-confirmation/upsert',
        json={'rows': [{'Trade ID': 'G1', 'Conferido OTC': ''}]})
check('   e apagar a data apaga o carimbo', M.find_row('G1').get('Time Stamp OTC'), '')

# Dentro do prazo não se pede nada — a cobrança é do ATRASO, não da validação.
novo('G2', produto='SWAP', **{'Data Operação': M.fmt_date(date.today())})
_r = cl.post('/api/manual-confirmation/upsert',
             json={'rows': [{'Trade ID': 'G2', 'Conferido OTC': M.fmt_date(date.today())}]})
check('no prazo, a grade grava sem justificativa', _r.status_code, 200)
check('   e carimba do mesmo jeito',
      'T000000' in (M.find_row('G2').get('Time Stamp OTC') or ''), True)

# Ajustar OUTRA coluna de uma linha já validada não é validar de novo: não pode
# recarimbar (apagaria o dono da conferência anterior) nem cobrar justificativa.
M.upsert_row(dict(M.find_row('G2'), **{'Time Stamp OTC': '01/01/2020 09:00 · OUTRO'}))
_como('HUB')
_r = cl.post('/api/manual-confirmation/upsert',
             json={'rows': [{'Trade ID': 'G2', 'Cliente': 'NOVO NOME'}]})
check('editar outra coluna de linha já validada não é validar', _r.status_code, 200)
check('   e o carimbo de quem assinou fica intacto',
      M.find_row('G2').get('Time Stamp OTC'), '01/01/2020 09:00 · OUTRO')

# Lote que falha no meio não pode deixar as linhas anteriores gravadas.
_como('BO')
novo('G3', produto='SWAP', **{'Data Operação': _velho})
cl.post('/api/manual-confirmation/upsert',
        json={'rows': [{'Trade ID': 'G2', 'Cliente': 'ANTES DO ERRO'},
                       {'Trade ID': 'G3', 'Conferido OTC': _velho}]})
check('lote que falha no meio não grava nada',
      M.find_row('G2').get('Cliente'), 'NOVO NOME')

_como('ADMIN')
check('linha sem Trade ID é recusada',
      cl.post('/api/manual-confirmation/upsert',
              json={'rows': [{'Cliente': 'sem chave'}]}).status_code, 400)
# A linha de filtro tem de entrar nas DUAS theads: com scrollX o DataTables
# CLONA o cabeçalho, e a linha só na tabela real fica escondida no corpo — foi
# exatamente assim que ela sumiu da tela sem erro nenhum.
# A linha de filtro tem de ser montada ANTES do `.DataTable()`: com scrollX o
# DataTables MOVE o thead para a tabela do cabeçalho rolável e deixa uma cópia
# oculta no corpo — acrescentá-la depois do init a punha na cópia, onde ela
# existia no DOM e não aparecia.
i_filtros = HTML.find("$('<tr class=\"mc-col-filters\">')")
i_init = HTML.find(".DataTable({")
check('a linha de filtro é montada antes do init', 0 < i_filtros < i_init, True)
check('   e a ordenação fica na 1a linha do thead', 'orderCellsTop: true' in HTML, True)
check('a coluna de Actions existe', 'mc-acts' in HTML and 'data-mc-edit=' in HTML, True)
check('   com excluir e abrir', ('data-mc-del=' in HTML, 'Confirmation Link' in HTML), (True, True))
check('ha botao de export', ('mcExportCsv' in HTML, 'mcExportCopy' in HTML), (True, True))
# O export leva o que esta NA TELA (filtro e ordenacao aplicados): exportar a
# base inteira depois de filtrar entrega outra coisa do que se esta vendo.
check('   e exporta o que esta filtrado',
      "search: 'applied', order: 'applied'" in HTML, True)

check('o sidenav tem os dois subitens, o Monitor primeiro',
      [u for u in __import__('re').findall(r'href="(/manual-confirmation[^"]*)"',
                                           io.open(os.path.join(ROOT, 'apps/templates/partials/sidenav.html'),
                                                   encoding='utf-8').read())],
      ['/manual-confirmation/monitor', '/manual-confirmation/track'])

# O botao Abrir leva ao PAPEL que foi gravado no Electronic Inventory, nao a uma
# tela que o reconstroi: quem valida precisa ver o que vai ao cliente.
link = R._mc_ei_link('ACME S.A.', '/base/ACME S.A.',
                     '/base/ACME S.A./Confirmations/2026/08. August/06/NDF Commodities/x.pdf')
check('o link aponta para o arquivo no Electronic Inventory',
      link.startswith('/api/electronic-inventory/file?client='), True)
check('   com o caminho RELATIVO a pasta do cliente',
      'rel=Confirmations/2026/08.%20August/06' in link, True)
check('   e sem o caminho absoluto do share', '/base/' in link, False)
check('caminho fora da pasta do cliente nao vira link',
      R._mc_ei_link('ACME', '/base/ACME', '/outro/x.pdf'), '')
check('sem arquivo nao inventa link', R._mc_ei_link('ACME', '/base/ACME', ''), '')

print('\n== 11. o e-mail do reject ==')
from apps.pages import otc_emails as E                            # noqa: E402
d = E.build_mc_reject_email({'Trade ID': 'T9', 'Cliente': 'ACME S.A.', 'Produto': 'SWAP'},
                            'MO', 'B222222', 'O notional do Anexo I está 1.000 a menos.')
check('vai para a caixa do OTC Ops', d['to'], 'brazil.otc.ops@jpmorgan.com')
check('o assunto diz quem rejeitou', 'MO' in d['subject'], True)
check('   e qual confirmação', 'T9' in d['subject'], True)
check('o comentário está no corpo', 'Anexo I' in d['html'], True)
check('   e quem apontou', 'B222222' in d['html'], True)

shutil.rmtree(TMP_DB, ignore_errors=True)
shutil.rmtree(TMP_MAP, ignore_errors=True)
print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
