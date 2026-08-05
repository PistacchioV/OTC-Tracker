"""Other Products > NDF > Settlement Advice: o aviso do Termo de Mercadoria.

Uma linha nasce de QUATRO fontes que nao se conhecem:

  Operations B3 --Titulo--> B3 ID e o universo (Resgate + TER + Type COMMODITIES)
        |-- = Contrato --> Posicao NDF --> Nº da Confirmacao, datas, quantidade,
        |                                  codigo do subjacente
        |                                       |-- Subjacente.json --> COMMODITY(COD)
        |-- sufixo do Nº da Confirmacao --> OTM Settlements --> Resultado Apurado
        |-- nome da contraparte --> RefData/CPD --> Settlement Net

O que este teste prende (tudo falha SEM erro no console):

  1. o UNIVERSO. Tres peneiras — Tipo Operacao = Resgate, Tipo Titulo = TER e a
     coluna derivada Type = COMMODITIES. Errar qualquer uma traz para o aviso do
     cliente operacao que nao e dele (uma opcao, um termo de cambio).

  2. o join do OTM pelo SUFIXO. O Trade Id do OTM e o Nº da Confirmacao carregam
     o mesmo identificador DEPOIS do hifen e prefixos diferentes antes. Comparar
     a string inteira nao casa nada, e a coluna de valor sai vazia.

  3. o IR. 0,005% so quando o BANCO paga (apurado < 0); LAWTON isenta; e o IR
     ENCOLHE o liquido, nunca aumenta.

  4. a Cotacao Mercadoria da ASIATICA. Sem data unica de fixing, o valor e o
     mes/ano da 1a data de verificacao, escrito "Media Fev/2027" — nao a data.

Nao encosta em dado real: as fontes vao para um tempfile e as raizes do modulo
voltam no finally.
"""
import io
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from apps.pages import routes as R                        # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def read(path):
    return io.open(path, encoding='utf-8').read()


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False)


# O cadastro de Subjacente e o de contraparte sao stubs: o teste nao depende do
# cadastro real nem o suja.
# Stub da FUNCAO, nao do cache: `_subjacente_map` revalida o mtime do arquivo
# real e recarregaria por cima de um cache preenchido na mao.
R._subjacente_map = lambda: {'OAHDY': 'ALUMINIO', 'CAFX': 'CAFE'}
R._ndfsum_refdata_spn = lambda: {R._fcst_norm('AMG BRASIL S.A.'): {'spn': '9', 'taxid': '1'}}
R._refdata_by_taxid = lambda: {'45985371000108': 'AMG BRASIL S.A.'}
R._cpd_load = lambda: [{'SPN': '9', 'COUNTERPARTY': 'AMG BRASIL S.A.',
                        'NET': {'value': 'Pay/Rec', 'status': 'Active'}}]

REF = datetime(2026, 8, 5)


def opb3(titulo, tipo_op='RESGATE', tipo_tit='TER', cpty='CLI', valor='1,00', conta=''):
    return {'Conta': '73760.00-9', 'Tipo Operação': tipo_op, 'Título': titulo,
            'Tipo Título': tipo_tit, 'Valor': valor, 'Data Liquidação': '05/08/2026',
            'Contraparte (Nome Simpl.)': cpty, 'Conta Contraparte': conta}


def ter(contrato, classe, cpty, conf, emissao, subj, fix_moeda, fix_ativo, qtd, asian='',
        cnpj=''):
    """Registro da posicao NDF no formato que `_lpndf_collect` le.

    As datas de media asiatica sao um bloco POSICIONAL: a 1a e a chave de indice
    100 do registro. Por isso o preenchimento ate 100 — sem ele a coluna
    "Media Asiatica (data) 1" nem existe, e o caminho da asiatica nao e exercido.
    """
    rec = {c: '' for c in R._LPNDF_COLUMNS}
    rec.update({'Contrato': contrato, 'Classe do Ativo Subjacente': classe,
                'Nome da Contraparte': cpty, 'Codigo Identificador': conf,
                'Data de Emissao': emissao, 'Codigo do Ativo Subjacente': subj,
                'Data de Fixing da Moeda': fix_moeda,
                'Data de Fixing do Ativo Subjacente': fix_ativo,
                'Valor Base no registro': qtd, 'Nome da Parte': 'BANCO J.P. MORGAN S.A.',
                'CPF/CNPJ da Contraparte': cnpj})
    while len(rec) < 100:
        rec['_pad%03d' % len(rec)] = ''
    rec['_asian1'] = asian
    return rec


tmp = tempfile.mkdtemp(prefix='ndfadv-')
ds, b3 = os.path.join(tmp, 'ds'), os.path.join(tmp, 'b3')
day = os.path.join(ds, '2026', '08', '05')

write_json(os.path.join(day, 'operations-b3_20260805.json'), [
    # O Valor do Operations B3 e o lado B3 do Trade Level: C1 bate com o interno
    # (Difference zero), C3 NAO bate — e a linha que tem de sair como Check.
    # C1 vem pela conta OMNIBUS: o nome da posicao e do titular do guarda-chuva
    # e o cliente de verdade sai do CNPJ.
    opb3('C1', valor='-2028144,04', conta='73760.10-2'),
    opb3('C2', valor='-500000,00'),               # entra — LAWTON, tambem pagando
    opb3('C3', valor='2000000,00'),               # entra — e DIVERGE do interno
    opb3('X3', tipo_op='PAGAMENTO DE PREMIO'),    # nao e Resgate
    opb3('X4', tipo_tit='OPC'),                   # nao e TER
    opb3('F5'),                                   # TER Resgate, mas Type = cambio
])
# O OTM traz PREFIXO diferente e o trade partido em duas linhas de fluxo.
write_json(os.path.join(day, 'otm-settlement_20260805.json'), [
    {'Trade Id': 'OTM-1NR000', 'Amount': '-2000000.00', 'Currency': 'BRL'},
    {'Trade Id': 'OTM-1NR000', 'Amount': '-28144.04', 'Currency': 'BRL'},
    {'Trade Id': 'OTM-1NR00R', 'Amount': '-500000.00', 'Currency': 'BRL'},
    {'Trade Id': 'OTM-1NR00S', 'Amount': '2036775.45', 'Currency': 'BRL'},
    {'Trade Id': 'OTM-OUTRO', 'Amount': '9999.00', 'Currency': 'BRL'},
])
POS = R._prev_anbima_bizday(REF).strftime('%y%m%d')
write_json(os.path.join(b3, 'NDF', R._b3_date_subpath(POS),
                        '73760_{}_DPOSICAO-TER.json'.format(POS)), [
    ter('C1', 'COMMODITIES', 'TITULAR DO OMNIBUS', 'DBH-1NR000', '20250603',
        'OAHDY', '20260803', '20260804', '702', cnpj='45985371000108'),
    # Asiatica: SEM data unica de fixing do ativo -> mes/ano da 1a verificacao
    ter('C2', 'COMMODITIES', 'LAWTON MULTIMERCADO EXCLUSIVO FUNDO DE INVESTIMENTO '
        'CREDITO PRIVADO', 'DBH-1NR00R', '20250603', 'CAFX', '20260803', '', '702',
        asian='20270215'),
    ter('C3', 'COMMODITIES', 'AMG BRASIL S.A.', 'DBH-1NR00S', '20250603',
        'OAHDY', '20260803', '20260804', '702'),
    ter('F5', 'TAXAS DE CAMBIO', 'OUTRO CLIENTE', 'DBH-FX', '20250603',
        'USD', '20260803', '20260804', '1'),
])

_ds_root, _b3_root = R.OTM_JSON_ROOT, R.B3_JSON_ROOT
try:
    R.OTM_JSON_ROOT, R.B3_JSON_ROOT = ds, b3
    items = R._ndfadv_collect(REF)
    trade = R._ops_ndfc_trade_rows(REF.date())
    email_rows = R._ndfadv_email_rows(REF)
finally:
    R.OTM_JSON_ROOT, R.B3_JSON_ROOT = _ds_root, _b3_root
    shutil.rmtree(tmp, ignore_errors=True)

COL = {c: i for i, c in enumerate(R._NDFADV_COLUMNS)}
by_b3 = {r['cells'][COL['B3 ID']]: r for r in items}


def cell(b3id, col):
    return by_b3[b3id]['cells'][COL[col]]


# ─────────────────────────────────────────────────────────────────────────────
print('\n== 1. o universo: Resgate + TER + Type COMMODITIES ==')
check('so os termos de mercadoria entram', sorted(by_b3), ['C1', 'C2', 'C3'])
check('premio nao e resgate', 'X3' in by_b3, False)
check('opcao nao e TER', 'X4' in by_b3, False)
check('termo de CAMBIO nao entra', 'F5' in by_b3, False)

print('\n== 2. a linha, coluna a coluna ==')
check('Contraparte vem da posicao NDF', cell('C1', 'Contraparte'), 'AMG BRASIL S.A.')
check('B3 ID e o Titulo do Operations B3', cell('C1', 'B3 ID'), 'C1')
check('Nº da Confirmacao e o Codigo Identificador', cell('C1', 'Nº da Confirmação'), 'DBH-1NR000')
check('Data de Inicio', cell('C1', 'Data de Início da Operação'), '03/06/2025')
# COMMODITY(CODIGO), como na planilha do usuario.
check('Ativo Subjacente resolve a commodity', cell('C1', 'Ativo Subjacente'), 'ALUMINIO(OAHDY)')
check('Ptax = data de fixing da MOEDA', cell('C1', 'Ptax'), '03/08/2026')
check('Quantidade', cell('C1', 'Quantidade da Operação'), '702.00')
check('Settlement Net vem do cadastro', cell('C1', 'Settlement Net'), 'Pay/Rec')
# Sem cadastro, o default seguro (o mesmo da recon) em vez de "sem netting".
check('sem cadastro cai em Total Net', cell('C2', 'Settlement Net'), 'Total Net')

print('\n== 3. Cotacao Mercadoria: data unica x media asiatica ==')
check('com fixing do ativo, a data', cell('C1', 'Cotação Mercadoria'), '04/08/2026')
# Sem data unica, o mes/ano da 1a verificacao — e por extenso, nao a data.
check('sem fixing, a media do mes', cell('C2', 'Cotação Mercadoria'), 'Média Fev/2027')

print('\n== 4. o OTM entra pelo SUFIXO, somado ==')
# Trade Id 'OTM-1NR000' x Nº da Confirmacao 'DBH-1NR000': prefixos diferentes, o
# identificador e o que vem depois do hifen. E as duas linhas de fluxo somam.
check('as duas linhas do mesmo trade somam', cell('C1', 'Resultado Apurado (R$)'), '-2,028,144.04')
check('o outro trade nao vaza', cell('C3', 'Resultado Apurado (R$)'), '2,036,775.45')

print('\n== 5. o IR de 0,005% ==')
# Banco pagando (apurado < 0) -> 0,005% sobre o modulo, arredondado a 2 casas.
check('banco pagando paga IR', cell('C1', 'IR 0,005% (R$)'), '101.41')
# E o IR ENCOLHE o que se movimenta: -2.028.144,04 + 101,41.
check('o liquido encolhe', cell('C1', 'Resultado Líquido (R$)'), '-2,028,042.63')
# Apurado positivo = o banco recebe -> nao ha retencao.
check('banco recebendo nao paga IR', cell('C3', 'IR 0,005% (R$)'), '0.00')
check('e o liquido fica cheio', cell('C3', 'Resultado Líquido (R$)'), '2,036,775.45')
# LAWTON e isenta MESMO com o banco pagando — e a primeira condicao da formula.
check('LAWTON isenta mesmo pagando', cell('C2', 'IR 0,005% (R$)'), '0.00')
check('e por isso o liquido dela e o cheio',
      cell('C2', 'Resultado Líquido (R$)'), '-500,000.00')

print('\n== 6. a pagina esta LIGADA ==')
SRC = read('apps/pages/routes.py')
check('rota da pagina',
      "@blueprint.route('/other-products-ndf-settlement-advice')" in SRC, True)
check('endpoint de dados',
      "@blueprint.route('/api/other-products-ndf-settlement-advice/data')" in SRC, True)
NAV = read('apps/templates/partials/sidenav.html')
check('o sidenav aponta para a pagina',
      'href="/other-products-ndf-settlement-advice"' in NAV, True)
HTML = read('apps/templates/pages/other-products-ndf-settlement-advice.html')
check('usa o visualizador generico', 'live-position-swap-characteristics.js' in HTML, True)
check('o data-api aponta para o endpoint',
      'data-api="/api/other-products-ndf-settlement-advice/data"' in HTML, True)
for hook in ('id="swapchar-page"', 'id="swapchar-table"'):
    check('o contrato com o JS: %s' % hook, hook in HTML, True)
check('uma largura por coluna',
      len(re.findall(r'#swapchar-table th:nth-child\((\d+)\)', HTML)),
      len(R._NDFADV_COLUMNS) + 2)
check('o Print Advice esta na pagina', 'swPrintAdvice' in HTML, True)

OTM = read('apps/templates/pages/otm-settlements.html')
check('a toolbar do OTM ganhou respiro',
      '#otm-page .card-body > .d-flex.justify-content-between' in OTM, True)

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 7. as linhas no Trade Level ==')
# Saem das MESMAS linhas do aviso: a tabela e o documento do cliente nao podem
# mostrar valores diferentes para o mesmo contrato.
by_t = {r['id_b3']: r for r in trade}
check('uma linha por contrato', sorted(by_t), ['C1', 'C2', 'C3'])
t = by_t['C1']
check('produto', t['product'], 'TERMO')
check('LOB', t['lob'], 'COMMODITIES')
check('type e a commodity do subjacente', t['type'], 'ALUMINIO(OAHDY)')
# Internal ID = identificador do Athena; B3 ID = Titulo do Operations B3. Trocar
# os dois deixa a linha "preenchida" e impossivel de casar com qualquer sistema.
check('internal id e o do Athena', t['internal_id'], 'DBH-1NR000')
check('b3 id e o do Operations B3', t['id_b3'], 'C1')
check('settlement e o INTERNO (OTM)', t['settlement'], '-2,028,144.04')
check('settlement B3 e o do Operations B3', t['settlement_b3'], '-2,028,144.04')
check('tax income e o IR de 0,005%', t['tax_income'], '101.41')
check('difference zerada', t['difference'], '0.00')
check('status OK quando bate', t['status'], 'OK')
# E quando NAO bate, a linha acusa: 2.036.775,45 interno x 2.000.000,00 no B3.
check('divergencia vira Check', by_t['C3']['status'], 'Check')
check('e a diferenca aparece', by_t['C3']['difference'], '36,775.45')

# O card de NDF Commodities acende: o Trade Level chama de TERMO e o card se
# chama NDF Commodities — a mesma familia tem de ser reconhecida.
rec = R._ops_recon(trade)['ndf']
check('o card de NDF deixa de ser n/a', rec['na'], False)
check('e conta as tres linhas', rec['b3_count'], 3)

print('\n== 8. a isencao de IR e UM cadastro para as duas telas ==')
SRC0 = read('apps/pages/routes.py')
check('cadastro registrado', "'ndfc-ir-exempt': {" in SRC0, True)
check('aba no /mapping', "key: 'ndfc-ir-exempt'" in read('apps/templates/pages/mapping.html'), True)
check('LAWTON isenta', R._ndfc_ir_exempt('LAWTON MULTIMERCADO EXCLUSIVO'), True)
check('ATACAMA isenta', R._ndfc_ir_exempt('ATACAMA FIC FIM'), True)
check('banco isento', R._ndfc_ir_exempt('BANCO DO BRASIL S.A.'), True)
check('cliente comum NAO e isento', R._ndfc_ir_exempt('AMG BRASIL S.A.'), False)
# As duas telas chamam a MESMA funcao — duas listas divergiriam sem erro nenhum,
# uma tela retendo e a outra nao.
check('o aviso usa _ndfc_ir', '_ndfc_ir(apurado, cliente)' in SRC0, True)
adv_ir = by_b3['C1']['ir']
check('o mesmo IR nas duas telas', R._ops_fmt_amt(adv_ir), t['tax_income'])

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 9. o aviso impresso ==')
from apps.pages import otc_emails                          # noqa: E402

HD = R._ndfadv_email_headers()
check('o aviso comeca no B3 ID', HD[0], 'B3 ID')
# Contraparte e o destinatario; Settlement Net e o criterio de quebra. Nenhum
# dos dois e conteudo do documento que o cliente recebe.
check('Contraparte fica de fora', 'Contraparte' in HD, False)
check('Settlement Net fica de fora', 'Settlement Net' in HD, False)
check('as demais colunas seguem', HD[1:4],
      ['Nº da Confirmação', 'Data de Início da Operação', 'Ativo Subjacente'])

ecell = lambda b3id, col: [r for r in email_rows if r['b3_id'] == b3id][0]['cells'][HD.index(col)]
# Valores em BR, negativo com o simbolo DENTRO dos parenteses.
check('negativo em BR', ecell('C1', 'Resultado Apurado (R$)'), '(R$ 2.028.144,04)')
check('IR em BR', ecell('C1', 'IR 0,005% (R$)'), 'R$ 101,41')
check('positivo em BR', ecell('C3', 'Resultado Apurado (R$)'), 'R$ 2.036.775,45')
# A tela segue em US: o aviso formata a partir do NUMERO, nao do texto da tela.
check('a tela nao mudou', cell('C1', 'Resultado Apurado (R$)'), '-2,028,144.04')

print('\n== 10. a quebra dos avisos ==')
otc_emails._build_cpdetails_index = lambda: {}
otc_emails._contacts_emails = lambda cp, kw: []


def drafts_for(net_type, split, rows_in):
    for r in rows_in:
        r['net_type'] = net_type
    return otc_emails.build_ndfc_settlement_emails(
        rows_in, HD, '05/08/2026', split_commodity=lambda n: split)


def mk(cpty, commodity, liquido):
    return {'counterparty': cpty, 'legal': 'BANCO J.P. MORGAN S.A.', 'spn': '9', 'taxid': '',
            'commodity': commodity, 'apurado': liquido, 'ir': 0.0, 'liquido': liquido,
            'cells': ['X'] * len(HD)}


# Total Net: um aviso, mesmo com duas commodities e sinais opostos.
d = drafts_for('Total Net', False, [mk('AMG', 'ALUMINIO(A)', 100.0), mk('AMG', 'CAFE(C)', -50.0)])
check('Total Net = um aviso so', len(d), 1)
# Pay/Rec: um por SENTIDO.
d = drafts_for('Pay/Rec', False, [mk('AMG', 'ALUMINIO(A)', 100.0), mk('AMG', 'CAFE(C)', -50.0)])
check('Pay/Rec = um por sentido', len(d), 2)
# No Net: um por trade.
d = drafts_for('No Net', False, [mk('AMG', 'ALUMINIO(A)', 100.0), mk('AMG', 'CAFE(C)', -50.0)])
check('No Net = um por trade', len(d), 2)

# A quebra por commodity so vale para quem esta no cadastro. Fora dele, aluminio
# e cafe saem na MESMA tabela.
d = drafts_for('Total Net', True, [mk('MONDELEZ BRASIL LTDA', 'ALUMINIO(A)', 100.0),
                                   mk('MONDELEZ BRASIL LTDA', 'CAFE(C)', 50.0)])
check('Mondelez Total Net = um por commodity', len(d), 2)
# E a quebra por commodity e a ULTIMA: um Pay/Rec do Mondelez sai por sentido E
# por commodity — quatro avisos, nao dois.
d = drafts_for('Pay/Rec', True, [mk('MONDELEZ BRASIL LTDA', 'ALUMINIO(A)', 100.0),
                                 mk('MONDELEZ BRASIL LTDA', 'ALUMINIO(A)', -10.0),
                                 mk('MONDELEZ BRASIL LTDA', 'CAFE(C)', 50.0),
                                 mk('MONDELEZ BRASIL LTDA', 'CAFE(C)', -5.0)])
check('Mondelez Pay/Rec = sentido X commodity', len(d), 4)
# Tres assuntos iguais no mesmo dia seriam tres anexos que ninguem separa.
check('o assunto distingue a commodity',
      len({x['subject'] for x in d}), 2)   # 2 commodities x 2 sentidos, mesmo assunto por commodity
check('o assunto diz Termo de Mercadoria',
      d[0]['subject'].startswith('Liquidação de Operação de Derivativo (Termo de Mercadoria)'), True)

print('\n== 11. cadastros da quebra e do PDF ==')
SRC1 = read('apps/pages/routes.py')
check('cadastro da quebra registrado', "'ndfc-advice-split': {" in SRC1, True)
check('aba no /mapping',
      "key: 'ndfc-advice-split'" in read('apps/templates/pages/mapping.html'), True)
check('Mondelez esta no seed', R._ndfc_split_by_commodity('MONDELEZ BRASIL NORTE NORDESTE LTDA'), True)
check('cliente comum nao quebra', R._ndfc_split_by_commodity('AMG BRASIL S.A.'), False)
# A Ficha em PDF usa o MESMO gerador e o MESMO cadastro do aviso de NDF de moeda.
EM = read('apps/pages/otc_emails.py')
body = EM.split('def _ndfc_settlement_email(', 1)[1].split('\n# ─', 1)[0]
check('o PDF e o mesmo do NDF de moeda', '_ndf_settlement_pdf(' in body, True)
check('e o mesmo cadastro de quem recebe', '_ndf_pdf_set()' in body, True)
check('a pagina tem o botao Print Advice', 'id="swPrintAdvice"' in HTML, True)
check('o endpoint existe',
      "@blueprint.route('/api/other-products-ndf-settlement-advice/emails'" in SRC1, True)

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 12. conta OMNIBUS: o cliente sai do CNPJ ==')
# Na conta guarda-chuva o nome que vem da B3 e o do TITULAR do omnibus, nao o do
# cliente. Mandar o aviso de liquidacao por esse nome e mandar para o cliente
# errado — e a linha "parece certa", com nome e valores preenchidos.
check('C1 veio pela conta omnibus -> nome do CNPJ',
      cell('C1', 'Contraparte'), 'AMG BRASIL S.A.')
# Fora do omnibus, o nome da posicao continua valendo.
check('C2 nao e omnibus -> nome da posicao',
      cell('C2', 'Contraparte').startswith('LAWTON'), True)
# E o Trade Level herda o mesmo nome: as duas telas nao podem discordar de quem
# e a contraparte da mesma operacao.
check('o Trade Level herda o cliente resolvido',
      by_t['C1']['counterparty'], 'AMG BRASIL S.A.')

SRC2 = read('apps/pages/routes.py')
check('cadastro de omnibus registrado', "'b3-omnibus-account': {" in SRC2, True)
check('aba no /mapping',
      "key: 'b3-omnibus-account'" in read('apps/templates/pages/mapping.html'), True)
# A conta aparece ora 73760.10-2, ora com outra pontuacao: a comparacao e por
# digitos, senao o omnibus deixa de ser reconhecido em silencio.
check('73760.10-2 e omnibus', R._b3_is_omnibus('73760.10-2'), True)
check('e a comparacao ignora a pontuacao', R._b3_is_omnibus('7376010 2'), True)
check('outra conta nao e omnibus', R._b3_is_omnibus('73760.00-9'), False)
check('conta vazia nao e omnibus', R._b3_is_omnibus(''), False)
check('a toolbar do Live Position NDF ganhou respiro',
      '#live-position-ndf-page .card-body > .d-flex.justify-content-between'
      in read('apps/templates/pages/live-position-ndf.html'), True)

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
