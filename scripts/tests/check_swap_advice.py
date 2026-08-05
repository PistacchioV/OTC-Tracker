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


def pos_rec(contrato, ident, ini, venc, termo, cod1='', cod2='', nome1='', nome2=''):
    """Posicao no formato REAL: 146 campos posicionais (2=Contrato, 11=Data
    inicio, 12=Data vencimento, 25=Data operacao termo). As duas pernas do swap
    ficam em 40/50 (Codigo indice) e 69/74 (Nome Tipo/Classe) — 1a e 2a de cada
    uma NA TELA do Live Position. No arquivo cru ha um 'Nome Tipo/Classe' antes
    (indice 30) que e do bloco do Termo: peg8a-lo pela ordem do arquivo daria a
    classe errada sem erro nenhum. Os nomes de Contrato e Codigo Identificador
    tambem entram, porque a LOB e resolvida POR NOME."""
    vals = [''] * 146
    vals[2], vals[4], vals[11], vals[12], vals[25] = contrato, ident, ini, venc, termo
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
            'PRE', 'VCP', 'x', 'DOLAR DOS EUA'),
    # sem termo -> cai na Data inicio: 01/07/2026..05/08/2026 = 35 dias
    pos_rec('N2', 'EDG-2026-0001', '20260701', '20260805', '', 'VCP', 'PRE', 'EURO', 'y'),
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
SRC = read('apps/pages/routes.py')
check('a regra do universo tem UMA implementacao', SRC.count('def _ops_swap_settling'), 1)
for fn in ('_ops_swap_trade_rows', '_swadv_collect'):
    body = SRC.split('def %s(' % fn, 1)[1].split('\ndef ', 1)[0]
    check('%s usa _ops_swap_settling' % fn, '_ops_swap_settling(' in body, True)

print('\n== 2. a linha completa, coluna a coluna ==')
check('Cliente vem do Athena', cell('A1', 'Cliente'), 'SUZANO SA')
check('LOB e o token do identificador', cell('A1', 'LOB'), 'CEM')
check('Valor Base Original vem dos eventos', cell('A1', 'Valor Base Original'), '1,000,000.00')
# Codigo indice <> VCP -> o proprio codigo e o indexador.
check('Indexador Banco = o Codigo indice', cell('A1', 'Indexador Banco'), 'PRE')
# Codigo indice = VCP -> VCP nao diz a moeda; o indexador esta no Nome
# Tipo/Classe da MESMA perna, em CAIXA ALTA.
check('Indexador Cliente resolve o VCP', cell('A1', 'Indexador Cliente'), 'DOLAR DOS EUA')
check('e o do N2 usa a 2a perna', cell('N2', 'Indexador Cliente'), 'PRE')
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
check('assunto normal',
      [s for s in subs if not s.startswith('(')],
      ['Liquidação de Operação de Derivativo (Swap) - 27/07/2026 - SUZANO SA'])
check('assunto de premio',
      [s for s in subs if s.startswith('(')],
      ['(Pagamento de Prêmio) Liquidação de Operação de Derivativo (Swap) - '
       '27/07/2026 - CLIENTE B3',
       '(Pagamento de Prêmio) Liquidação de Operação de Derivativo (Swap) - '
       '27/07/2026 - SUZANO SA'])
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

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
