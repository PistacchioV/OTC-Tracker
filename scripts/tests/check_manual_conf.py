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
from datetime import datetime, timedelta, timezone

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


write_map([
    {'PRODUCT': 'NDF COMM', 'LOB': '', 'OTC': 'REQUESTED', 'MO': 'REQUESTED', 'FO': 'EXEMPT'},
    {'PRODUCT': 'SWAP', 'LOB': '', 'OTC': 'REQUESTED', 'MO': 'REQUESTED', 'FO': 'REQUESTED'},
    {'PRODUCT': 'SWAP', 'LOB': 'EDG', 'OTC': 'EXEMPT', 'MO': 'REQUESTED', 'FO': 'REQUESTED'},
])


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
check('validado o MO, a esteira fecha', row['Pending'], M.STATUS_OK)
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
check('validadas as duas, fecha', M.find_row('T2')['Pending'], M.STATUS_OK)

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

print('\n== 7. o Monitor ==')
p = M.monitor_payload()
por_label = {c['label']: c for c in p['cards']}
check('três cards, na ordem da esteira', [c['label'] for c in p['cards']],
      [M.PENDING_OTC, M.PENDING_MO, M.PENDING_FO])
# T3 está em Pending MO/FO e tem de aparecer nos DOIS cards.
nos_dois = [c['label'] for c in p['cards']
            if any(i['key'] == 'T3' for i in c['items'])]
check('a linha parada nas duas mesas aparece nos dois cards',
      sorted(nos_dois), sorted([M.PENDING_MO, M.PENDING_FO]))
check('   e não no card do OTC (ela já passou / é isenta)',
      any(i['key'] == 'T3' for i in por_label[M.PENDING_OTC]['items']), False)
check('o item traz o que identifica a confirmação sem abrir',
      sorted(por_label[M.PENDING_OTC]['items'][0].keys()),
      sorted(list(M.MONITOR_FIELDS) + ['key', 'keys', 'trades', 'count', 'stage', 'docs']))

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
grp = next((i for i in p['cards'][0]['items'] if i['Data Operação'] == '05/08/2026'), None)
check('as três operações do mesmo cliente/dia viram UM item', bool(grp), True)
check('   com as três chaves juntas', sorted(grp['keys']), ['GRP1', 'GRP2', 'GRP3'])
check('   e a contagem de operações', grp['count'], 3)
check('o card conta CONFIRMAÇÕES no total',
      p['cards'][0]['count'], len(p['cards'][0]['items']))
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
      ('ACME S.A.', 'Confirmations/2026/08. August/05/NDF Commodities'))
check('   e o nome da pasta é o mesmo que o save grava',
      sorted(M.PRODUCT_FOLDER.values()),
      ['Commodities Options', 'FX Options', 'NDF Commodities', 'NDF FWD Start'])
check('a nomenclatura da planilha legada resolve a MESMA pasta',
      M.confirmation_folder({'Cliente': 'REFINARIA', 'Produto': 'NDF',
                             'LOB': 'COMMODITY', 'Data Operação': '03/08/2026'})[1],
      'Confirmations/2026/08. August/03/NDF Commodities')
check('sem produto conhecido nao inventa pasta',
      M.confirmation_folder({'Cliente': 'X', 'Produto': '?', 'Data Operação': '05/08/2026'}),
      (None, None))
# Produto sem cadastro → aviso na tela.
novo('T8', produto='PRODUTO NOVO')
p = M.monitor_payload()
check('produto sem cadastro vira aviso', any('PRODUTO NOVO' in w for w in p['warnings']), True)

print('\n== 8. as colunas ==')
check('27 colunas na tela', len(M.COLUMNS), 27)
check('o Trade ID repetido do arquivo virou uma só',
      M.COLUMNS.count('Trade ID'), 1)
check('os três Time Stamp têm nome próprio no banco',
      [c for c in M.COLUMNS if c.startswith('Time Stamp')],
      ['Time Stamp OTC', 'Time Stamp MO', 'Time Stamp FO'])
check('   e o rótulo curto na tela (e Moeda exibida como Ativo)',
      sorted(set(M.COLUMN_LABELS.values())), ['Ativo', 'Time Stamp'])
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
HTML = cl.get('/manual-confirmation/track').data.decode('utf-8')
check('a tela recebe as colunas do servidor', 'var COLUMNS = [' in HTML, True)
check('   e não tem uma lista própria', "'Conferido OTC'" in HTML, False)
check('o Trade ID fica fora da edição em massa',
      "c !== KEY" in HTML and 'isDerived(c)' in HTML, True)
# O SPN do carimbo vem da SESSÃO: mandar outro no corpo não pode valer.
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
