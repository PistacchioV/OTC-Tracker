"""Other Products Summary > Trade Level: a linha de SWAP.

Uma linha do Trade Level nasce de CINCO arquivos que nao se conhecem, e o join e
todo por codigo:

  Operations B3 --Titulo--> B3 ID, LOB, Settlement B3
        |-- = CETIP ID -->  Swap Athena --> Internal ID, Counterparty, Direction
        |                        |-- = Trade Id --> OTM Settlements --> Settlement
        |-- = Cod. Contrato -->  Swap Events --> Type (VCP x Calculado)
        |-- = Contrato ------->  Posicao SWAP --> prazo --> IR

Cada seta e um lugar onde a linha sai errada SEM ninguem perceber: o numero
aparece, so nao e o numero certo. Por isso a secao 1 monta as cinco fontes num
tempfile e chama `_ops_swap_trade_rows` DE VERDADE, conferindo campo a campo.

As tres armadilhas que ela prende:

  1. o DEDUP. O mesmo swap chega ao Operations B3 uma vez por Tipo Operacao
     (amortizacao, juros, premio). Sem dedup a tela mostraria o mesmo contrato
     duas ou tres vezes; com dedup a mais, o Settlement B3 perderia parcelas.
     A linha e UMA, mas o Settlement B3 soma TODAS as linhas do Titulo.

  2. o vao do 721. A formula da planilha (`IF(E12>721;15%)`) deixa o prazo 721
     exato sem resposta e devolve FALSE. A tabela por faixas fecha isso, e a
     secao 2 fixa a tabela inteira contra a formula original.

  3. a ORDEM das colunas, que vive em TRES listas posicionais (os <th>, o
     rowMaker do JS e `_OPS_TRADE_COLS`). Mexer numa so desloca a tabela toda
     sem erro nenhum no console.

Nao encosta em dado real: as cinco fontes sao um tempfile e as raizes do modulo
sao devolvidas no finally.
"""
import io
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import date, datetime

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from apps.pages import routes as R                        # noqa: E402

fails = []

# Os tres cadastros de swap sao lidos DO SEED, nao do arquivo. Duas razoes:
#   * o arquivo e dado do usuario — quem editar a tabela de IR pela tela faria
#     este teste falhar sem ter quebrado nada;
#   * e o seed e justamente o que precisa ser fixado: ele tem de reproduzir a
#     formula da planilha na instalacao nova, antes de qualquer edicao.
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


# ─────────────────────────────────────────────────────────────────────────────
print('\n== 1. o join das cinco fontes, ponta a ponta ==')
REF = date(2026, 7, 27)
REF_DT = datetime(2026, 7, 27)
POS_DT = R._prev_anbima_bizday(REF_DT)          # a posicao e sempre D-1 ANBIMA
DREF = POS_DT.strftime('%y%m%d')

tmp = tempfile.mkdtemp(prefix='ops-trade-test-')
ds = os.path.join(tmp, 'ds')
b3 = os.path.join(tmp, 'b3')


def opb3(titulo, tipo_op, valor, tipo_tit='SWAP', cpty='CLIENTE B3'):
    return {'Conta': '73760.00-9', 'Tipo Operação': tipo_op, 'C/V': 'CREDOR',
            'Título': titulo, 'Tipo Título': tipo_tit, 'Tipo de Regime': '',
            'Data Vencimento': '05/08/2026', 'Valor': valor,
            'Modalidade Liquidação': '', 'Status': '', 'Data Liquidação': '27/07/2026',
            'Contraparte (Nome Simpl.)': cpty, 'Conta Contraparte': '', 'Num Ctrl Operação': ''}


write_json(os.path.join(ds, '2026', '07', '27', 'operations-b3_20260727.json'), [
    # A1 chega DUAS vezes (juros + amortizacao) -> uma linha so, Settlement B3 = 150
    opb3('A1', 'PAGAMENTO DE DIF. DE JUROS', '100,00'),
    opb3('A1', 'PAGAMENTO DE DIF. AMORTIZACAO', '50,00'),
    # RESGATE nao e liquidacao de diferencial -> nao entra
    opb3('B2', 'RESGATE', '999,00'),
    # premio sem contraparte no Athena -> linha aparece, mas sem Internal ID
    opb3('C3', 'PAGAMENTO DE PREMIO', '77,00', cpty='SEM ATHENA'),
    # TER com o mesmo tipo de operacao -> nao e swap, nao entra
    opb3('T4', 'PAGAMENTO DE PREMIO', '11,00', tipo_tit='TER'),
])

write_json(os.path.join(ds, '2026', '07', '27', 'br-onshore-settlements_20260727.json'), [
    {'CETIP ID': 'A1', 'Kapital ID': 'K1', 'Owner Legal Entity': 'BANCO J.P. MORGAN',
     'CounterParty': 'SUZANO SA', 'SPN': '1', 'Owner curve': '', 'Counterparty curve': '',
     'BRL Net Amount': '', 'Direction': 'Counterparty receives'},
])

write_json(os.path.join(ds, '2026', '07', '27', 'otm-settlement_20260727.json'), [
    {'Trade Id': 'K1', 'Amount': '100.00', 'Currency': 'BRL'},
    {'Trade Id': 'K1', 'Amount': '50.00', 'Currency': 'BRL'},
    {'Trade Id': 'OUTRO', 'Amount': '9999.00', 'Currency': 'BRL'},
])

ev = {c: '' for c in R._EVENTS_COLUMNS}
ev_a1 = dict(ev, **{'Código do Contrato': 'A1', 'PARTE / Indexador': 'PRE',
                    'CONTRAPARTE / Indexador': 'VCP'})          # basta UMA ponta em VCP
ev_c3 = dict(ev, **{'Código do Contrato': 'C3', 'PARTE / Indexador': 'CDI',
                    'CONTRAPARTE / Indexador': 'PRE'})
write_json(os.path.join(ds, '2026', '07', '27', 'eventos-swap-jpm_20260727.json'), [ev_a1, ev_c3])

# Posicao SWAP no formato REAL: 146 campos posicionais (2=Contrato, 11=Data
# inicio, 12=Data vencimento, 25=Data operacao termo). O arquivo de producao tem
# nomes repetidos, entao so a leitura posicional funciona — e e ela que este
# registro exercita.
def pos_rec(contrato, ini, venc, termo):
    vals = [''] * 146
    vals[2], vals[11], vals[12], vals[25] = contrato, ini, venc, termo
    return {'f%03d' % i: v for i, v in enumerate(vals)}


write_json(os.path.join(b3, 'Swap', R._b3_date_subpath(DREF),
                        '73760_{}_DPOSICAO-SWAP.json'.format(DREF)), [
    # forward start: tem Data operacao termo -> 22/01/2024 .. 05/08/2026 = 926 dias
    pos_rec('A1', '20240301', '20260805', '20240122'),
    # sem termo -> cai na Data inicio: 01/07/2026 .. 05/08/2026 = 35 dias
    pos_rec('C3', '20260701', '20260805', ''),
])

_ds_root, _b3_root = R.OTM_JSON_ROOT, R.B3_JSON_ROOT
try:
    R.OTM_JSON_ROOT, R.B3_JSON_ROOT = ds, b3
    rows = R._ops_swap_trade_rows(REF)
finally:
    R.OTM_JSON_ROOT, R.B3_JSON_ROOT = _ds_root, _b3_root
    shutil.rmtree(tmp, ignore_errors=True)

by_id = {r['id_b3']: r for r in rows}
check('so os swaps de diferencial/premio entram', sorted(by_id), ['A1', 'C3'])
check('o swap repetido vira UMA linha', len(rows), 2)

a = by_id.get('A1', {})
check('A1 · B3 ID', a.get('id_b3'), 'A1')
check('A1 · Internal ID vem do Kapital ID', a.get('internal_id'), 'K1')
check('A1 · Counterparty vem do Athena', a.get('counterparty'), 'SUZANO SA')
check('A1 · Product', a.get('product'), 'SWAP')
check('A1 · Type = VCP (uma ponta basta)', a.get('type'), 'VCP')
check('A1 · Settlement = soma do OTM', a.get('settlement'), '150.00')
check('A1 · Settlement B3 soma AS DUAS linhas', a.get('settlement_b3'), '150.00')
check('A1 · Difference zerada', a.get('difference'), '0.00')
check('A1 · status OK quando bate', a.get('status'), 'OK')
# 926 dias -> 15% (a linha do aviso na planilha do usuario) -> 150 x 15%
check('A1 · Tax Income pelo prazo do TRADE (926d = 15%)', a.get('tax_income'), '22.50')

c = by_id.get('C3', {})
check('C3 · sem Athena, Internal ID vazio', c.get('internal_id'), '')
check('C3 · sem OTM, Settlement vazio', c.get('settlement'), '')
check('C3 · Settlement B3 mesmo assim', c.get('settlement_b3'), '77.00')
check('C3 · Difference vazia (nao inventa zero)', c.get('difference'), '')
check('C3 · status Check', c.get('status'), 'Check')
check('C3 · Type = Calculado quando nao ha VCP', c.get('type'), 'Calculado')
check('C3 · Counterparty cai no nome simplificado', c.get('counterparty'), 'SEM ATHENA')

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 2. o SEED da tabela de IR, contra a formula da planilha ==')
IR = R._ops_swap_ir_rate
check('banco (LEFT 5 = BANCO) isento', IR('BANCO DO BRASIL SA', 30, True), 0.0)
check('JPMORGAN CHASE BANK isento', IR('JPMORGAN CHASE BANK, N.A', 30, True), 0.0)
check('LAWTON isento', IR('LAWTON MULTIMERCADO EXCLUSIVO FUNDO DE INVESTIMENTO '
                          'CREDITO PRIVADO', 30, True), 0.0)
check('OVERSEAS CAPITAL = 10%', IR('J.P. MORGAN OVERSEAS CAPITAL LLC', 30, True), 0.10)
for prazo, exp in ((1, .225), (180, .225), (181, .20), (360, .20), (361, .175),
                   (720, .175), (721, .15), (5000, .15)):
    check('prazo %-5d -> %.3f' % (prazo, exp), IR('SUZANO SA', prazo, True), exp)
check('quem recebe NAO e a contraparte -> 0%', IR('SUZANO SA', 100, False), 0.0)
check('sem prazo -> None (nao afirma isencao)', IR('SUZANO SA', None, True), None)
check('direcao desconhecida -> None', IR('SUZANO SA', 100, None), None)
check('sem cliente -> None', IR('', 100, True), None)

print('\n== 3. quem recebe e a contraparte? ==')
CR = R._ops_cpty_receives
check('texto do Athena manda', CR('Counterparty receives', 999.0), True)
check('outra ponta recebendo', CR('Owner receives', -999.0), False)
check('sem texto: negativo = o banco paga', CR('', -10.0), True)
check('sem texto: positivo = o banco recebe', CR('', 10.0), False)
check('sem texto e sem valor: nao da para afirmar', CR('', None), None)

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 4. a ordem das colunas concorda nas TRES listas ==')
HTML = read('apps/templates/pages/other-products-summary.html')
trade = HTML.split('id="ops-trade-table"', 1)[1].split('</thead>', 1)[0]
ths = re.findall(r'<th data-lang="ops-col-([a-z0-9-]+)"', trade)
from_html = [t.replace('-', '_') for t in ths if t not in ('actions', 'status')]
js = HTML.split('(j.trade || []).forEach', 1)[1].split('});', 1)[0]
# A ultima celula NAO e um esc(): a Difference passa pelo diffCell, que junta o
# numero com o icone ✓/✗ (§188). Ela conta como coluna do mesmo jeito.
from_js = re.findall(r'esc\(r\.(\w+)\)|(diffCell)\(r\)', js)
from_js = ['difference' if b else a for a, b in from_js]
SRC = read('apps/pages/routes.py')
m = re.search(r'_OPS_TRADE_COLS = \((.*?)\)\n', SRC, re.S)
from_py = re.findall(r"'(\w+)'", m.group(1)) if m else []
EXPECTED = ['lob', 'counterparty', 'internal_id', 'id_b3', 'product', 'type',
            'settlement', 'settlement_b3', 'tax_income', 'difference']
check('a ordem pedida esta no cabecalho', from_html, EXPECTED)
check('o rowMaker do JS segue a mesma', from_js, EXPECTED)
check('_OPS_TRADE_COLS segue a mesma', from_py, EXPECTED)
# A linha de filtros cobre Status + as 10 de dado; checkbox e Actions nao filtram.
check('a linha de filtros tem uma caixa por coluna filtravel',
      trade.count('<input type="text" placeholder='), len(EXPECTED) + 1)
check('o DataTables sabe quantas colunas de dado ha',
      "initTable('ops-trade-table', 10, 50)" in HTML, True)

print('\n== 5. os tres cadastros existem e o seed reproduz a formula ==')
for key in ('swap-b3-events', 'swap-ir-client', 'swap-ir-term'):
    check('%s registrado em _MAPPING_DEFS' % key, ("'%s': {" % key) in SRC, True)
    check('%s na aba do /mapping' % key, ("key: '%s'" % key) in read('apps/templates/pages/mapping.html'), True)
check('os tres eventos de liquidacao', sorted(R._ops_swap_event_set()),
      ['pagamento de dif. amortizacao', 'pagamento de dif. de juros', 'pagamento de premio'])
check('RESGATE NAO e evento de liquidacao', 'resgate' in R._ops_swap_event_set(), False)

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
