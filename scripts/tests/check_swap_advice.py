"""Other Products > Swap > Settlement Advice: a planilha de aviso, na tela.

E o documento que o cliente recebe dizendo quanto ele ganhou, quanto de IR foi
retido e quanto sobra. Tudo aqui e dinheiro que sai errado SEM erro nenhum: o
numero aparece formatado e plausivel, so nao e o numero certo.

O que este teste prende:

  1. o UNIVERSO. Quais swaps liquidam e a MESMA regra do Trade Level
     (`_ops_swap_settling`): Tipo Titulo = SWAP, Tipo Operacao registrado, dedup
     por Titulo. Duas copias dessa regra deixariam uma tela mostrando um swap que
     a outra nao mostra.

  2. a DATA DE OPERACAO. E a `Data operacao termo` e, so quando ela vem vazia, a
     `Data inicio`. Um forward start com a data errada encurta o prazo e SOBE a
     aliquota de IR — retem imposto a mais do cliente.

  3. o IR encolhendo o caixa nos DOIS sinais: `bruto - ir` quando positivo,
     `bruto + ir` quando negativo. Inverter manda dinheiro a mais para o aviso.

  4. branco != 0%. Sem prazo nao da para escolher a faixa; imprimir 0% ali
     afirmaria uma isencao que ninguem conferiu.

  5. a pagina LIGADA: rota, endpoint e o link do sidenav apontando para a URL de
     verdade, nao para a ancora morta que ficou la por meses.

Nao encosta em dado real: as quatro fontes vao para um tempfile e as raizes do
modulo voltam no finally.
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


def _fontes_com_rotas_(base):
    """routes.py + a arvore de features — as rotas moram nos entrypoints desde
    a verticalizacao, e um scan so do routes viraria assercao vazia."""
    import io as _io, os as _os
    partes = [_io.open(_os.path.join(base, 'apps', 'pages', 'routes.py'), encoding='utf-8').read()]
    # ... e a arvore da platform/ — a fase §316 move os motores compartilhados
    # para la, e um scan que parasse nas features perderia o que acabou de sair
    # do routes (foi a familia de liquidacao a primeira).
    for raiz in (_os.path.join(base, 'apps', 'pages', 'features'),
                 _os.path.join(base, 'apps', 'pages', 'platform')):
        for r, dirs, arqs in _os.walk(raiz):
            dirs[:] = [d for d in dirs if d != '__pycache__']
            for a in sorted(arqs):
                if a.endswith('.py'):
                    partes.append(_io.open(_os.path.join(r, a), encoding='utf-8').read())
    return '\n'.join(partes)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from apps.pages import routes as R                        # noqa: E402

fails = []

# Mesma razao do check_ops_trade_swap: os cadastros de swap vem DO SEED, para
# que uma edicao pela tela nao quebre o teste e o padrao de fabrica fique fixado.
_SWAP_MAPS = ('swap-b3-events', 'swap-ir-client', 'swap-ir-term')
_real_mapping_rows = R._mapping_rows
R._mapping_rows = lambda key: ([dict(r) for r in R._MAPPING_DEFS[key]['seed']]
                               if key in _SWAP_MAPS else _real_mapping_rows(key))


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


REF = datetime(2026, 7, 27)
POS_DT = R._prev_anbima_bizday(REF)
DREF = POS_DT.strftime('%y%m%d')


def opb3(titulo, tipo_op, tipo_tit='SWAP', cpty='CLIENTE B3'):
    return {'Conta': '73760.00-9', 'Tipo Operação': tipo_op, 'C/V': 'CREDOR',
            'Título': titulo, 'Tipo Título': tipo_tit, 'Data Vencimento': '05/08/2026',
            'Valor': '1,00', 'Data Liquidação': '27/07/2026',
            'Contraparte (Nome Simpl.)': cpty}


def athena(cetip, cpty, owner_curve, cpty_curve, bruto, direction):
    return {'CETIP ID': cetip, 'Kapital ID': 'K-' + cetip, 'Owner Legal Entity': 'BANCO J.P. MORGAN',
            'CounterParty': cpty, 'SPN': '1', 'Owner curve': owner_curve,
            'Counterparty curve': cpty_curve, 'BRL Net Amount': bruto, 'Direction': direction}


def ev(contrato, base, ativo_banco, ativo_cliente):
    r = {c: '' for c in R._EVENTS_COLUMNS}
    r.update({'Código do Contrato': contrato, 'Valor Base': base,
              'PARTE / Indexador': ativo_banco, 'CONTRAPARTE / Indexador': ativo_cliente})
    return r


def pos_rec(contrato, ident, ini, venc, termo, cod1='', cod2='', nome1='', nome2='', base=''):
    """Posicao no formato REAL: 146 campos posicionais (2=Contrato, 11=Data
    inicio, 12=Data vencimento, 25=Data operacao termo). As duas pernas do swap
    ficam em 40/50 (Codigo indice) e 69/74 (Nome Tipo/Classe) — 1a e 2a de cada
    uma NA TELA do Live Position. No arquivo cru ha um 'Nome Tipo/Classe' antes
    (indice 30) que e do bloco do Termo: peg8a-lo pela ordem do arquivo daria a
    classe errada sem erro nenhum. Os nomes de Contrato e Codigo Identificador
    tambem entram, porque a LOB e resolvida POR NOME."""
    vals = [''] * 146
    vals[2], vals[4], vals[11], vals[12], vals[25] = contrato, ident, ini, venc, termo
    vals[14] = base                       # 'Valor base' (coluna O)
    vals[30] = 'CLASSE DO TERMO'          # a armadilha: NAO pode virar indexador
    vals[40], vals[50], vals[69], vals[74] = cod1, cod2, nome1, nome2
    names = ['f%03d' % i for i in range(146)]
    names[2], names[4] = 'Contrato', 'Código Identificador'
    return dict(zip(names, vals))


tmp = tempfile.mkdtemp(prefix='swadv-test-')
ds, b3 = os.path.join(tmp, 'ds'), os.path.join(tmp, 'b3')
day = os.path.join(ds, '2026', '07', '27')

write_json(os.path.join(day, 'operations-b3_20260727.json'), [
    # A1 chega duas vezes (juros + amortizacao) -> UMA linha no aviso
    opb3('A1', 'PAGAMENTO DE DIF. DE JUROS'),
    opb3('A1', 'PAGAMENTO DE DIF. AMORTIZACAO'),
    opb3('N2', 'PAGAMENTO DE PREMIO'),          # bruto negativo
    opb3('B3', 'RESGATE'),                      # nao e evento de liquidacao
    opb3('T4', 'PAGAMENTO DE PREMIO', tipo_tit='TER'),   # nao e swap
    opb3('S5', 'PAGAMENTO DE PREMIO'),          # sem prazo na posicao
    opb3('S6', 'PAGAMENTO DE PREMIO'),          # sem linha no Athena
])
write_json(os.path.join(day, 'br-onshore-settlements_20260727.json'), [
    athena('A1', 'SUZANO SA', '1000000.00', '1310217.20', '310217.20', 'Counterparty receives'),
    athena('N2', 'SUZANO SA', '1000.00', '0.00', '-1000.00', 'Counterparty receives'),
    athena('S5', 'SUZANO SA', '1.00', '2.00', '1.00', 'Counterparty receives'),
])
write_json(os.path.join(day, 'eventos-swap-jpm_20260727.json'), [
    ev('A1', '1000000.00', 'PRE', 'CDI'),
    ev('N2', '1000.00', 'CDI', 'PRE'),
])
write_json(os.path.join(b3, 'Swap', R._b3_date_subpath(DREF),
                        '73760_{}_DPOSICAO-SWAP.json'.format(DREF)), [
    # forward start: TEM Data operacao termo -> 22/01/2024..05/08/2026 = 926 dias
    pos_rec('A1', 'CEM-2026-3184', '20240301', '20260805', '20240122',
            'PRE', 'C00', 'x', 'DOLAR DOS EUA', '1000000.00'),
    # sem termo -> cai na Data inicio: 01/07/2026..05/08/2026 = 35 dias
    pos_rec('N2', 'EDG-2026-0001', '20260701', '20260805', '', 'C00', 'PRE', 'EURO', 'y', '1000.00'),
    # sem data nenhuma -> sem prazo
    pos_rec('S5', 'CEM-2026-9999', '', '', ''),
    pos_rec('S6', 'CEM-2026-8888', '20260701', '20260805', ''),
])

_ds_root, _b3_root = R.OTM_JSON_ROOT, R.B3_JSON_ROOT
try:
    R.OTM_JSON_ROOT, R.B3_JSON_ROOT = ds, b3
    rows = R._swadv_rows(REF)
    trade = R._ops_swap_trade_rows(REF.date())
    email_rows = R._swadv_email_rows(REF)
finally:
    R.OTM_JSON_ROOT, R.B3_JSON_ROOT = _ds_root, _b3_root
    shutil.rmtree(tmp, ignore_errors=True)

COL = {c: i for i, c in enumerate(R._SWADV_COLUMNS)}
by_contract = {r[COL['Número de Contrato']]: r for r in rows}


def cell(contrato, col):
    return by_contract.get(contrato, [''] * len(R._SWADV_COLUMNS))[COL[col]]


# ─────────────────────────────────────────────────────────────────────────────
print('\n== 1. o universo e o MESMO do Trade Level ==')
check('so os swaps de diferencial/premio entram', sorted(by_contract), ['A1', 'N2', 'S5', 'S6'])
check('o swap repetido vira UMA linha', len(rows), 4)
check('as duas telas veem os mesmos contratos',
      sorted(by_contract), sorted(r['id_b3'] for r in trade))
SRC = _fontes_com_rotas_(ROOT)
check('a regra do universo tem UMA implementacao', SRC.count('def _ops_swap_settling'), 1)
for fn in ('_ops_swap_trade_rows', '_swadv_collect'):
    body = SRC.split('def %s(' % fn, 1)[1].split('\ndef ', 1)[0]
    check('%s usa _ops_swap_settling' % fn, '_ops_swap_settling(' in body, True)

print('\n== 2. a linha completa, coluna a coluna ==')
check('Cliente vem do Athena', cell('A1', 'Cliente'), 'SUZANO SA')
check('LOB e o token do identificador', cell('A1', 'LOB'), 'CEM')
# Valor Base sai da POSICAO (indice 14), nao mais do arquivo de eventos: uma
# fonte a menos e um join a menos para falhar em silencio — e foi o que deixou a
# coluna vazia no primeiro aviso gerado.
check('Valor Base Original vem da posicao', cell('A1', 'Valor Base Original'), '1,000,000.00')
# O Codigo indice da posicao e um CODIGO (C00, PRE): ele passa PRIMEIRO pelo
# cadastro `swap-index` — o mesmo que a tela do Live Position usa. Comparar o
# codigo cru com 'VCP' nunca casava, porque o VCP e o C00.
check('Indexador Banco = o nome da curva', cell('A1', 'Indexador Banco'), 'PRE')
check('C00 vira VCP no cadastro', R._swapindex_name('C00'), 'VCP')
# Traduzido como VCP -> VCP nao diz a moeda; o indexador esta no Nome
# Tipo/Classe da MESMA perna, em CAIXA ALTA.
check('Indexador Cliente resolve o VCP', cell('A1', 'Indexador Cliente'), 'DOLAR DOS EUA')
check('e o do N2 usa a 2a perna', cell('N2', 'Indexador Cliente'), 'PRE')
check('e a 1a perna do N2 tambem resolve', cell('N2', 'Indexador Banco'), 'EURO')
check('Curva Banco vem do Athena', cell('A1', 'Curva Banco'), '1,000,000.00')
check('Curva Cliente vem do Athena', cell('A1', 'Curva Cliente'), '1,310,217.20')
check('Resultado Bruto vem do Athena', cell('A1', 'Resultado Bruto'), '310,217.20')
# Vencimento do aviso = a data da LIQUIDACAO (a parcela paga hoje), nao o
# vencimento do swap — que na posicao e 05/08/2026 para este contrato.
check('Vencimento e a data de liquidacao', cell('A1', 'Vencimento'), '27/07/2026')
# Sem casamento no Athena a linha ainda sai — com o nome simplificado do B3.
check('sem Athena, cai no nome simplificado do B3', cell('S6', 'Cliente'), 'CLIENTE B3')
check('sem Athena, sem Resultado Bruto', cell('S6', 'Resultado Bruto'), '')

print('\n== 3. a Data de Operacao e a do TRADE, nao a do inicio ==')
# A1 e forward start: a data e 22/01/2024 (operacao termo), NAO 01/03/2024.
check('forward start usa a Data operacao termo', cell('A1', 'Data Operação'), '22/01/2024')
# 22/01/2024 -> 27/07/2026 = 917 dias, e o Prazo e a diferenca entre as DUAS
# datas impressas: o cliente confere a conta do aviso e ela tem de fechar.
check('prazo do TRADE ate a liquidacao', cell('A1', 'Prazo'), '917')
# N2 nao tem termo: cai na Data inicio.
check('sem termo, cai na Data inicio', cell('N2', 'Data Operação'), '01/07/2026')
check('prazo curto', cell('N2', 'Prazo'), '26')

print('\n== 4. o IR e o liquido ==')
# 926 dias -> 15% (a faixa acima de 720 da tabela). 310.217,20 x 15% = 46.532,58
check('aliquota pela faixa do prazo', cell('A1', 'Alíquota IR'), '15.00%')
check('Valor IR = bruto x aliquota', cell('A1', 'Valor IR'), '46,532.58')
check('Valor Liquido = bruto - IR', cell('A1', 'Valor Líquido'), '263,684.62')
# 35 dias -> 22,5%. Bruto NEGATIVO: o IR encolhe o pagamento, nao o aumenta.
check('faixa curta = 22,5%', cell('N2', 'Alíquota IR'), '22.50%')
check('IR sobre o modulo do bruto', cell('N2', 'Valor IR'), '225.00')
check('bruto negativo ENCOLHE (soma o IR)', cell('N2', 'Valor Líquido'), '-775.00')

print('\n== 5. branco nao e zero ==')
check('sem prazo, aliquota em branco', cell('S5', 'Alíquota IR'), '')
check('sem aliquota, sem Valor IR', cell('S5', 'Valor IR'), '')
check('sem aliquota, sem Valor Liquido', cell('S5', 'Valor Líquido'), '')

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 6. a pagina esta LIGADA ==')
check('rota da pagina', "@blueprint.route('/other-products-swap-settlement-advice')" in SRC, True)
check('endpoint de dados',
      "@blueprint.route('/api/other-products-swap-settlement-advice/data')" in SRC, True)
NAV = read('apps/templates/partials/sidenav.html')
check('o sidenav aponta para a URL, nao para a ancora morta',
      'href="/other-products-swap-settlement-advice"' in NAV, True)
check('a ancora morta sumiu', '#other-products-swap-settlement-advice' in NAV, False)
HTML = read('apps/templates/pages/other-products-swap-settlement-advice.html')
# O visualizador generico procura por estes tres nomes; trocar um deixa a pagina
# em branco SEM erro no console.
check('a pagina usa o visualizador generico',
      'live-position-swap-characteristics.js' in HTML, True)
check('o data-api aponta para o endpoint',
      'data-api="/api/other-products-swap-settlement-advice/data"' in HTML, True)
for hook in ('id="swapchar-page"', 'id="swapchar-table"'):
    check('o contrato com o JS: %s' % hook, hook in HTML, True)
# Uma largura por coluna: checkbox + Status + as 15 do aviso.
check('uma largura por coluna',
      len(re.findall(r'#swapchar-table th:nth-child\((\d+)\)', HTML)),
      len(R._SWADV_COLUMNS) + 2)

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 7. o aviso impresso ==')
from apps.pages import otc_emails                          # noqa: E402

by_ct = {r['cells'][0]: r for r in email_rows}
HD = R._swadv_email_headers(False)
HD_P = R._swadv_email_headers(True)
check('o aviso comeca em Numero de Contrato', HD[0], 'Número de Contrato')
check('Cliente e LOB ficam de fora', ('Cliente' in HD or 'LOB' in HD), False)
check('no aviso de premio a coluna Vencimento muda de nome',
      HD_P[HD.index('Vencimento')], 'Pagamento de Prêmio')
check('e so ela muda', [h for h in HD_P if h not in HD], ['Pagamento de Prêmio'])

# Valores em BR: R$ #.##0,00, e o negativo com o simbolo DENTRO dos parenteses.
ecell = lambda ct, col: by_ct[ct]['cells'][HD.index(col)]
check('positivo em BR', ecell('A1', 'Valor Base Original'), 'R$ 1.000.000,00')
check('negativo entre parenteses', ecell('N2', 'Resultado Bruto'), '(R$ 1.000,00)')
check('prazo no formato #.##0', ecell('A1', 'Prazo'), '917')
check('aliquota em BR', ecell('A1', 'Alíquota IR'), '15,00%')
# A tela segue em US: as duas formatacoes convivem de proposito, e o aviso
# formata a partir do NUMERO — reformatar o texto de uma para a outra erraria no
# primeiro valor com separador ambiguo.
check('a tela nao mudou de formato', cell('A1', 'Valor Base Original'), '1,000,000.00')

# A1 tem juros + amortizacao -> liquidacao comum. Os outros tres sao
# PAGAMENTO DE PREMIO puro. Um swap que paga premio E diferencial no mesmo dia
# NAO e premio: chamar o conjunto assim no assunto esconderia o diferencial que
# tambem esta na tabela.
check('premio so quando TODOS os eventos do titulo sao premio',
      {r['cells'][0]: r['premium'] for r in email_rows},
      {'A1': False, 'N2': True, 'S5': True, 'S6': True})

drafts = otc_emails.build_swap_settlement_emails(email_rows, HD, HD_P, '27/07/2026')
subs = sorted(d['subject'] for d in drafts)
# SUZANO normal (A1) + SUZANO premio (N2, S5) + CLIENTE B3 premio (S6).
check('um aviso por contraparte x entidade x premio', len(drafts), 3)
# O assunto leva CONTRAPARTE + CNPJ: o nome sozinho nao identifica (o mesmo
# grupo tem varias entidades com nomes quase iguais), e quem arquiva o aviso casa
# pelo cadastro, que e por CNPJ. A SUZANO tem TAX ID no RefData e o CNPJ aparece;
# o CLIENTE B3 nao tem, e o assunto fica como sempre foi — meio CNPJ no fim do
# assunto seria pior do que nenhum.
check('assunto normal, com o CNPJ da contraparte',
      [s for s in subs if not s.startswith('(')],
      ['Liquidação de Operação de Derivativo (Swap) - 27/07/2026 - '
       'SUZANO SA 16.404.287/0001-55'])
check('assunto de premio, e sem CNPJ quem nao tem TAX ID',
      [s for s in subs if s.startswith('(')],
      ['(Pagamento de Prêmio) Liquidação de Operação de Derivativo (Swap) - '
       '27/07/2026 - CLIENTE B3',
       '(Pagamento de Prêmio) Liquidação de Operação de Derivativo (Swap) - '
       '27/07/2026 - SUZANO SA 16.404.287/0001-55'])
# O documento tem de trazer o cabecalho certo em cada versao.
html_p = [d['html'] for d in drafts if d['subject'].startswith('(')][0]
html_n = [d['html'] for d in drafts if not d['subject'].startswith('(')][0]
check('o aviso de premio traz a coluna renomeada', 'Pagamento de Prêmio' in html_p, True)
check('e o normal nao', 'Pagamento de Prêmio' in html_n, False)
check('o normal traz Vencimento', 'Vencimento' in html_n, True)

check('a pagina tem o botao Print Advice', 'id="swPrintAdvice"' in HTML, True)
check('e ele chama o endpoint',
      "'/api/other-products-swap-settlement-advice/emails'" in HTML, True)
check('o endpoint existe',
      "@blueprint.route('/api/other-products-swap-settlement-advice/emails'" in SRC, True)

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 8. as traducoes de codigo saem do CADASTRO ==')
# Regra de ouro do CLAUDE.md: de-para nao mora no codigo. Estas quatro tabelas
# viviam como dicts em routes.py (ou num arquivo lido por fora) e agora sao
# cadastros do /mapping. O que se prende aqui e o COMPORTAMENTO IDENTICO ao de
# antes — o seed tem de reproduzir o que estava hardcoded, senao a migracao
# muda a tela sem ninguem pedir.
for key in ('swap-index', 'swap-funcionalidade', 'swap-amortizacao', 'swap-code-labels'):
    check('%s registrado em _MAPPING_DEFS' % key, ("'%s': {" % key) in SRC, True)
    check('%s na aba do /mapping' % key,
          ("key: '%s'" % key) in read('apps/templates/pages/mapping.html'), True)
check('nenhum dicionario de traducao sobrou no codigo',
      ('_SWAPCHAR_FUNC_MAP' in SRC) or ('_SWAPCHAR_AMORT_MAP' in SRC), False)

# O Swap Index aponta para o MESMO arquivo da aba do B3 Index Results — nao para
# uma copia. Duas copias divergiriam na primeira edicao, e a divergencia apareceria
# como um codigo cru na tela, sem erro nenhum.
check('o cadastro usa o proprio SwapIndex.json',
      R._mapping_path('swap-index').endswith(os.path.join('static', 'data', 'SwapIndex.json')), True)
check('C00 -> VCP', R._swapindex_name('C00'), 'VCP')
check('codigo desconhecido passa direto', R._swapindex_name('ZZZ'), 'ZZZ')

check('Funcionalidade 9', R._swapchar_func_text('9'), 'SWAP COM PRÊMIO')
check('Funcionalidade 0', R._swapchar_func_text('0'), 'SEM FUNCIONALIDADE')
check('Amortizacao 3', R._swapchar_amort_text('3'), 'Na Data de Vencimento')
check('Amortizacao 4', R._swapchar_amort_text('4'), 'Sem Troca de Amortização')
check('Sinal 00 -> +', R._swapchar_sinal_text('00'), '+')
check('Sinal 01 -> -', R._swapchar_sinal_text('01'), '-')
# 01 = Nao e 00 = Sim: e a especificacao, por mais que pareca invertido.
check('Flag 01 -> Nao', R._lp_bool_ptbr('01'), 'Não')
check('Flag 00 -> Sim', R._lp_bool_ptbr('00'), 'Sim')

print('\n== 9. a Difference do Trade Level tem o ✓/✗ ==')
OPS = read('apps/templates/pages/other-products-summary.html')
check('a celula da Difference passa pelo diffCell', 'diffCell(r)' in OPS, True)
# O icone sai do MESMO status que pinta o badge — duas fontes contariam
# historias diferentes na primeira vez que a tolerancia mudasse.
check('o icone sai do status', "r.status === 'OK'" in OPS, True)
for cls in ('ti ti-check text-success', 'ti ti-x text-danger'):
    check('mesma marca do NDF: %s' % cls,
          (cls in OPS) and (cls in read('apps/templates/pages/ndf-summary.html')), True)

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 10. o status New -> Generated -> Sent, nas DUAS telas ==')
# O aviso e um so: se cada tela contasse o seu proprio estado, uma diria
# "Generated" e a outra "New" para o mesmo documento. Por isso as duas leem a
# MESMA chave do MESMO overlay do dia (contraparte x LOB x produto).
R.session = {'user_sid': 'T000000'}          # _opssum_set_status carimba quem gravou
tmp = tempfile.mkdtemp(prefix='swadv-st-')
_ds_root = R.OTM_JSON_ROOT
try:
    R.OTM_JSON_ROOT = tmp
    _p, meta = R._opssum_meta_load(REF)
    check('sem overlay, nasce New', R._opssum_status(meta, 'SUZANO SA', 'CEM', 'SWAP'), 'New')

    R._opssum_set_status(REF, [('SUZANO SA', 'CEM', 'SWAP')], 'Generated')
    _p, meta = R._opssum_meta_load(REF)
    check('gerou o aviso -> Generated', R._opssum_status(meta, 'SUZANO SA', 'CEM', 'SWAP'), 'Generated')
    # A tela do Settlement Summary le do mesmo lugar.
    check('o Settlement Summary enxerga o mesmo estado',
          R._opssum_rows([{'counterparty': 'SUZANO SA', 'lob': 'CEM', 'product': 'SWAP',
                           '_settle_n': 10.0, '_tax_n': None}], REF)[0]['status'],
          'Generated')

    R._opssum_set_status(REF, [('SUZANO SA', 'CEM', 'SWAP')], 'Sent')
    _p, meta = R._opssum_meta_load(REF)
    check('confirmou -> Sent', R._opssum_status(meta, 'SUZANO SA', 'CEM', 'SWAP'), 'Sent')
    # Chave normalizada: grafia diferente no dia seguinte nao perde o estado.
    check('a chave e normalizada', R._opssum_status(meta, 'suzano  sa', 'cem', 'swap'), 'Sent')
    # Outra LOB da mesma contraparte e OUTRA linha de aviso.
    check('outra LOB segue New', R._opssum_status(meta, 'SUZANO SA', 'EDG', 'SWAP'), 'New')
finally:
    R.OTM_JSON_ROOT = _ds_root
    shutil.rmtree(tmp, ignore_errors=True)

check('o endpoint do advice manda os statuses', "'statuses': statuses" in SRC, True)
check('o Print Advice grava Generated', "'Generated')" in SRC, True)
check('e o Confirm grava Sent', "'Sent')" in SRC, True)

# O visualizador e COMPARTILHADO por cinco paginas: o status por linha entrou
# como opcional, e quem nao manda `statuses` tem de continuar com o badge fixo.
JS = read('apps/static/js/pages/live-position-swap-characteristics.js')
check('o viewer aceita statuses', 'buildTable(d.columns, d.rows, d.statuses)' in JS, True)
check('e cai no badge de sempre sem eles', '|| statusBadge' in JS, True)
for st, cls in (('Sent', 'text-bg-primary'), ('Generated', 'text-bg-success'), ('New', 'text-bg-info')):
    check('%s na cor do NDF' % st, ("%s:%s'%s'" % (st, ' ' * (10 - len(st)), cls)) in JS
          or ("%s: '%s'" % (st, cls)) in JS or ("%s:      '%s'" % (st, cls)) in JS, True)
check('a pagina recarrega depois de gerar', 'window.scLoad' in HTML, True)

print('\n== 11. o template de TED continua NDF por default ==')
# O rotulo do produto virou parametro do template. Sem passar nada, ele TEM de
# render o texto de antes — senao o aviso de NDF muda sem ninguem ter pedido.
TED_TPL = read('apps/templates/pages/email-template-ted-release.html')
check('default NDF no template', "product_label|default('NDF')" in TED_TPL, True)
check('o cabecalho usa o parametro', "'Liberação de TED — ' ~ product_label" in TED_TPL, True)
check('o corpo usa o parametro', 'liquidações de {{ product_label }}' in TED_TPL, True)
# O 'NDF' so pode aparecer como DEFAULT (e no comentario que o explica) — nunca
# mais escrito direto no cabecalho ou na frase do corpo.
check('nao sobrou NDF fixo no cabecalho', 'TED — NDF' in TED_TPL, False)
check('nao sobrou NDF fixo no corpo', 'liquidações de NDF' in TED_TPL, False)
check('o endpoint do NDF passa o rotulo', "product_label='NDF'" in SRC, True)

print('\n== 12. a toolbar tem respiro ==')
# Columns e Export sao injetados pelo JS depois do render e vem com margem
# zerada; sem estas regras a fila encosta no cabecalho da tabela.
check('padding na barra', '.card-body > .d-flex.justify-content-between' in HTML, True)
check('altura igual para todos os botoes', '.card-body > .d-flex .dt-button' in HTML, True)
check('respiro antes da tabela', '.card-body > .table-responsive' in HTML, True)

print('\n== 13. a coluna de Actions (Edit / Confirm / Delete) ==')
# O visualizador serve CINCO paginas. A coluna nova e opt-in: sem data-actions
# nada muda para as outras quatro — e o deslocamento das colunas fixas (LEAD)
# tem de acompanhar, senao o filtro por coluna passa a filtrar a vizinha, sem
# erro nenhum na tela.
JS = read('apps/static/js/pages/live-position-swap-characteristics.js')
check('a coluna e opt-in', "page.getAttribute('data-actions')" in JS, True)
check('e esta pagina pediu', 'data-actions="1"' in HTML, True)
check('LEAD conta as colunas fixas', 'var LEAD = ACTIONS ? 3 : 2;' in JS, True)
# Nenhum literal 2 pode ter sobrado nos seis lugares que dependem do offset.
for frag in ("(i + 2)", "slice(2)", "(index + 2)", "c.idx + 2", "idx > 1", "[{}, {}]"):
    check('sem literal %r' % frag, frag in JS, False)
for frag in ("(i + LEAD)", "slice(LEAD)", "(index + LEAD)", "c.idx + LEAD", "idx >= LEAD"):
    check('usa %r' % frag, frag in JS, True)
# As outras quatro paginas nao pediram a coluna — e nao podem ganha-la.
for pg in ('live-position-swap-characteristics', 'live-position-swap-cashflow',
           'live-position-swap-premium', 'other-products-swap-athena',
           'other-products-swap-events', 'other-products-swap-vcp',
           'other-products-ndf-settlement-advice'):
    other = read('apps/templates/pages/%s.html' % pg)
    check('%s segue sem Actions' % pg, 'data-actions' in other, False)
# O que os botoes FAZEM e da pagina: o arquivo compartilhado so entrega o clique.
check('o compartilhado delega', 'window.scRowAction' in JS, True)
check('e a pagina implementa', 'window.scRowAction = function' in HTML, True)
check('o modal existe', 'id="swAdvEditModal"' in HTML, True)
check('com os campos vindos das COLUNAS do servidor',
      'columns.map(function (label, i)' in HTML, True)
# Editar o Numero de Contrato criaria uma linha orfa: e a chave do registro.
check('a chave fica travada no modal', "var locked = (i === KEY_COL);" in HTML, True)

# ── formato dos botoes ────────────────────────────────────────────────────
# `rounded-circle` arredonda em 50% da CAIXA; a caixa do .btn-sm e mais larga
# que alta por causa do padding lateral, entao o resultado e uma ELIPSE. So
# travar 32x32 faz o raio produzir um quadrado de cantos redondos.
check('nenhum botao de acao usa rounded-circle',
      'rounded-circle sc-act' in JS or 'sc-act" ' in JS.replace('sc-row-act sc-act', ''), False)
check('os tres usam a classe de tamanho travado', JS.count('sc-row-act sc-act'), 3)
check('e a pagina trava 32x32',
      'min-width: 32px; max-width: 32px; min-height: 32px; max-height: 32px;' in HTML, True)
check('com canto arredondado, nao circulo', 'border-radius: 10px !important;' in HTML, True)
# O Other Products Summary mostra a MESMA linha de liquidacao: botoes de
# formatos diferentes nas duas telas leem como telas de sistemas diferentes.
OPS = read('apps/templates/pages/other-products-summary.html')
check('mesmo raio do Other Products Summary',
      'border-radius: 10px !important;' in OPS, True)

print('\n== 14. a edicao vale na TELA e no AVISO IMPRESSO ==')
# E o ponto do modulo inteiro: se a celula corrigida so valesse na tela, o
# cliente receberia o valor antigo e ninguem notaria.
SRC = _fontes_com_rotas_(ROOT)
check('a tela le as linhas com overlay',
      'items = _swadv_items(ref)' in SRC or 'items = _R()._swadv_items(ref)' in SRC, True)
check('o aviso impresso tambem',
      'for r in _swadv_items(ref):' in SRC or 'for r in _R()._swadv_items(ref):' in SRC, True)
check('e o overlay sincroniza os numeros CRUS', '_SWADV_NUM_FIELDS' in SRC, True)
# `_mtm_parse_num` le so o formato US; a tabela mostra US e o aviso imprime BR,
# entao o operador digita ora um ora outro.
blk = SRC.split('def _swadv_apply_edits')[1].split('\ndef ')[0]
check('usa o parser tolerante aos dois formatos', '_conf_to_float(str(val))' in blk, True)
# A CHAMADA, nao o nome — o comentario ao lado cita o parser errado de proposito,
# para explicar por que ele nao serve aqui.
check('e nao o que so le US', '_mtm_parse_num(' in blk, False)
check('apagar nao encosta nos arquivos de origem', "e['deleted']" in SRC, True)

print('\n== 15. o Valor Base: UMA leitura para a celula e para o aviso ==')
# O arquivo de POSICAO escreve a virgula como separador DECIMAL ('280000000,00'),
# sem separador de milhar. Lido pelo parser de uso geral, esse mesmo texto vira
# 28.000.000.000 — cem vezes o valor. A tela mostrava certo (tinha o seu proprio
# parse) e o aviso impresso saia com o numero errado: duas leituras do MESMO dado.
check('o caso reportado: 280 milhoes',
      R._swapchar_value_num('280000000,00'), 280000000.0)
check('   e a celula concorda', R._swapchar_fmt_value('280000000,00'), '280,000,000.00')
# A prova de verdade: o texto do arquivo -> celula -> numero cru, sem divergir.
for raw in ('280000000,00', '1234,56', '0,00', '280000000.00'):
    cel = R._swapchar_fmt_value(raw)
    check('%r: celula e cru batem' % raw,
          R._swapchar_value_num(raw), float(cel.replace(',', '')))
check('vazio nao vira zero', R._swapchar_value_num(''), None)
check('texto nao numerico passa inteiro', R._swapchar_fmt_value('n/a'), 'n/a')
check('   e o cru dele e None, nao 0', R._swapchar_value_num('n/a'), None)
# Estrutural: o aviso NAO pode voltar a ler a posicao com o parser de uso geral.
blk = SRC.split('def _swadv_collect')[1].split('\ndef ')[0]
check('o valor_base sai da leitura da posicao',
      "'valor_base': _swapchar_value_num(" in blk, True)
check('e nao do parser de uso geral',
      "'valor_base': _mtm_parse_num(" in blk, False)
check('e o formatador da celula usa a MESMA funcao',
      '_swapchar_value_num(s)' in SRC, True)

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
