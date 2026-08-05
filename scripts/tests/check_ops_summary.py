"""Other Products Summary > Settlement Summary: o net por contraparte.

Esta tabela e um PORTE do Settlement Summary do NDF, e o valor do porte esta em
nao ter recopiado a regra: Receive/Pay, Settlement Net, Direction, Account e
Observation saem das MESMAS funcoes `_ndfsum_*` que a pagina de NDF usa. Duas
copias de uma regra de dinheiro divergem em silencio — o numero continua
aparecendo, so deixa de ser o mesmo numero das duas telas.

A unica diferenca deliberada: la a linha e a CONTRAPARTE, aqui e
contraparte x LOB x produto, porque a pagina cobre varios produtos.

O que este teste prende (tudo falha SEM erro no console):

  1. o IR encolhendo o caixa. `settlement - tax` quando positivo,
     `settlement + tax` quando negativo. Trocar o sinal manda dinheiro a mais
     ou a menos para o aviso, e o total continua "parecendo certo".

  2. Total Net x Pay/Rec. Total Net colapsa numa ponta so; Pay/Rec mantem as
     duas. Cair no default errado muda o aviso que o cliente recebe.

  3. o CRUZAMENTO da conta. Direction e a visao do BANCO; os defaults do
     Reference Data sao a visao da CONTRAPARTE. Banco PAY -> conta
     DEFAULT_RECEIVE do cliente. Inverter isso imprime a conta errada num
     aviso de pagamento.

  4. o agrupamento. Mesmo cliente com dois produtos = duas linhas; e o net
     NAO atravessa produto nem LOB.

  5. a ORDEM das colunas, em TRES listas posicionais (<th>, rowMaker, e
     `_OPSSUM_COLS`).

  6. LOB = TOKEN (EDG/CEM), nao o Codigo Identificador inteiro. As duas
     tabelas da pagina tem uma coluna LOB; falarem linguas diferentes seria o
     defeito.

Nao encosta em dado real: RefData e CounterpartyDetails sao stubs em memoria, as
cinco fontes do Trade Level vao para um tempfile e as raizes do modulo voltam no
finally.
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


# ── Cadastro de mentira: RefData (nome -> SPN) e CounterpartyDetails (net type +
#    contas). Sao os DOIS arquivos que a tabela le do disco; stubados, o teste
#    nao depende do cadastro real nem o suja.
def acc(id_, bank, agency, account):
    return {'id': id_, 'bank': bank, 'agency': agency, 'account': account,
            'status': 'Active', 'maker': 'T', 'checker': 'T'}


CPD = [
    {'SPN': '111', 'COUNTERPARTY': 'SUZANO SA',
     'NET': {'value': 'Total Net', 'status': 'Active'},
     'BANKING': {'ACCOUNTS': [acc('p1', '341', '0910', '967'), acc('r1', '376', '0001', '123')],
                 'DEFAULT_PAY': {'current': 'p1'}, 'DEFAULT_RECEIVE': {'current': 'r1'}}},
    {'SPN': '222', 'COUNTERPARTY': 'CLIENTE PAYREC',
     'NET': {'value': 'Pay/Rec', 'status': 'Active'},
     'BANKING': {'ACCOUNTS': [acc('p2', '033', '0002', '999')],
                 'DEFAULT_PAY': {'current': 'p2'}}},
]
R._cpd_load = lambda: [dict(r) for r in CPD]
R._ndfsum_refdata_spn = lambda: {
    R._fcst_norm('SUZANO SA'): {'spn': '111', 'taxid': '1'},
    R._fcst_norm('CLIENTE PAYREC'): {'spn': '222', 'taxid': '2'},
}


def trow(cpty, lob, product, settle, tax=None):
    """Linha do Trade Level como `_ops_swap_trade_rows` a devolve (so os campos
    que o Settlement Summary consome)."""
    return {'counterparty': cpty, 'lob': lob, 'product': product,
            '_settle_n': settle, '_tax_n': tax}


REF = datetime(2026, 7, 27)

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 1. o IR encolhe o caixa, nos dois sinais ==')
# Recebendo 1.000 com 150 de IR -> entram 850. Pagando 1.000 com 150 de IR ->
# saem 850. O imposto NUNCA aumenta o que se movimenta.
rows = R._opssum_rows([trow('CLIENTE PAYREC', 'CEM', 'SWAP', 1000.0, 150.0)], REF)
check('recebimento liquido de IR', rows[0]['receive'], '850.00')
rows = R._opssum_rows([trow('CLIENTE PAYREC', 'CEM', 'SWAP', -1000.0, 150.0)], REF)
check('pagamento tambem encolhe', rows[0]['pay'], '-850.00')
rows = R._opssum_rows([trow('CLIENTE PAYREC', 'CEM', 'SWAP', 1000.0, None)], REF)
check('sem IR calculado, valor cheio', rows[0]['receive'], '1,000.00')

print('\n== 2. Total Net colapsa; Pay/Rec mantem as duas pontas ==')
mixed = [trow('CLIENTE PAYREC', 'CEM', 'SWAP', 1000.0),
         trow('CLIENTE PAYREC', 'CEM', 'SWAP', -400.0)]
pr = R._opssum_rows(mixed, REF)[0]
check('Pay/Rec · Receive bruto', pr['receive'], '1,000.00')
check('Pay/Rec · Pay bruto', pr['pay'], '-400.00')
check('Pay/Rec · Settlement Net mostra o tipo', pr['net_type'], 'Pay/Rec')

tn = R._opssum_rows([trow('SUZANO SA', 'CEM', 'SWAP', 1000.0),
                     trow('SUZANO SA', 'CEM', 'SWAP', -400.0)], REF)[0]
check('Total Net · uma ponta so', (tn['receive'], tn['pay']), ('600.00', ''))
check('Total Net · Settlement Net mostra o tipo', tn['net_type'], 'Total Net')
tn_neg = R._opssum_rows([trow('SUZANO SA', 'CEM', 'SWAP', 400.0),
                         trow('SUZANO SA', 'CEM', 'SWAP', -1000.0)], REF)[0]
check('Total Net · negativo vai para Pay', (tn_neg['receive'], tn_neg['pay']), ('', '-600.00'))

# Contraparte fora do Reference Data: cai no Total Net (mesmo default seguro do
# NDF) em vez de assumir que nao ha netting.
sem = R._opssum_rows([trow('NAO CADASTRADO LTDA', 'CEM', 'SWAP', 100.0)], REF)[0]
check('sem cadastro cai em Total Net', sem['net_type'], 'Total Net')
check('sem cadastro nao inventa conta', sem['account'], '')

print('\n== 3. Direction e a conta, que se cruzam ==')
check('total positivo = o banco recebe', tn['direction'], 'RECEIVE')
check('total negativo = o banco paga', tn_neg['direction'], 'PAY')
# Banco RECEIVE -> o cliente PAGA -> conta DEFAULT_PAY do cliente (341).
check('banco recebe -> conta de PAGAMENTO do cliente',
      tn['account'], 'BCO: 341 | AG: 0910 | CC: 967')
# Banco PAY -> o cliente RECEBE -> conta DEFAULT_RECEIVE do cliente (376).
check('banco paga -> conta de RECEBIMENTO do cliente',
      tn_neg['account'], 'BCO: 376 | AG: 0001 | CC: 123')

print('\n== 4. a observacao automatica Internal/External ==')
# 341 e externo, 376 e JPMorgan (interno) -> rotulo misto, cada slot com o seu.
check('mista', tn['obs'], 'Pay External | Receive Internal')
# So DEFAULT_PAY cadastrado -> o slot sem default fica FORA do rotulo.
check('slot sem default nao entra no rotulo', pr['obs'], 'Pay External')
check('sem nenhuma conta, sem rotulo', sem['obs'], '')

print('\n== 5. o net NAO atravessa produto nem LOB ==')
multi = R._opssum_rows([trow('SUZANO SA', 'CEM', 'SWAP', 1000.0),
                        trow('SUZANO SA', 'CEM', 'OPTION', -400.0),
                        trow('SUZANO SA', 'EDG', 'SWAP', 50.0)], REF)
check('tres linhas, uma por (LOB, produto)', len(multi), 3)
check('cada uma com o seu valor',
      sorted((r['lob'], r['product'], r['receive'], r['pay']) for r in multi),
      [('CEM', 'OPTION', '', '-400.00'), ('CEM', 'SWAP', '1,000.00', ''),
       ('EDG', 'SWAP', '50.00', '')])
# Linha sem contraparte ou sem valor nao vira aviso: nao ha o que liquidar.
check('sem contraparte fica de fora', R._opssum_rows([trow('', 'CEM', 'SWAP', 10.0)], REF), [])
check('sem settlement fica de fora', R._opssum_rows([trow('X', 'CEM', 'SWAP', None)], REF), [])

print('\n== 6. a observacao digitada vence a automatica ==')
tmp = tempfile.mkdtemp(prefix='ops-sum-test-')
_ds_root = R.OTM_JSON_ROOT
try:
    R.OTM_JSON_ROOT = tmp
    path = R._opssum_meta_path(REF)
    # A chave e normalizada: gravada com caixa/acento diferentes, ainda casa.
    write_json(path, {R._opssum_key('suzano  sa', 'cem', 'swap'): {'obs': 'liquidar via TED'}})
    got = R._opssum_rows([trow('SUZANO SA', 'CEM', 'SWAP', 1000.0)], REF)[0]
    check('overlay do dia prevalece', got['obs'], 'liquidar via TED')
    check('outra linha segue na automatica',
          R._opssum_rows([trow('SUZANO SA', 'EDG', 'SWAP', 1000.0)], REF)[0]['obs'],
          'Pay External | Receive Internal')
finally:
    R.OTM_JSON_ROOT = _ds_root
    shutil.rmtree(tmp, ignore_errors=True)

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 7. LOB e o TOKEN, nao o Codigo Identificador ==')
REF_D = date(2026, 7, 27)
POS_DT = R._prev_anbima_bizday(REF)
DREF = POS_DT.strftime('%y%m%d')
tmp = tempfile.mkdtemp(prefix='ops-sum-lob-')
ds, b3 = os.path.join(tmp, 'ds'), os.path.join(tmp, 'b3')

write_json(os.path.join(ds, '2026', '07', '27', 'operations-b3_20260727.json'), [
    {'Conta': '73760.00-9', 'Tipo Operação': 'PAGAMENTO DE DIF. DE JUROS', 'C/V': 'CREDOR',
     'Título': 'A1', 'Tipo Título': 'SWAP', 'Data Vencimento': '05/08/2026', 'Valor': '100,00',
     'Data Liquidação': '27/07/2026', 'Contraparte (Nome Simpl.)': 'CLI'},
    {'Conta': '73760.00-9', 'Tipo Operação': 'PAGAMENTO DE PREMIO', 'C/V': 'CREDOR',
     'Título': 'Z9', 'Tipo Título': 'SWAP', 'Data Vencimento': '05/08/2026', 'Valor': '10,00',
     'Data Liquidação': '27/07/2026', 'Contraparte (Nome Simpl.)': 'CLI'},
])


def pos_rec(contrato, ident):
    """Posicao no formato REAL (146 campos posicionais) com os DOIS nomes que
    importam: `_ops_swap_pos_terms` le por indice, `_opb3_tipo_maps` le por nome."""
    vals = [''] * 146
    vals[2], vals[4] = contrato, ident
    names = ['f%03d' % i for i in range(146)]
    names[2], names[4] = 'Contrato', 'Código Identificador'
    return dict(zip(names, vals))


write_json(os.path.join(b3, 'Swap', R._b3_date_subpath(DREF),
                        '73760_{}_DPOSICAO-SWAP.json'.format(DREF)),
           [pos_rec('A1', 'CEM-2026-3184'), pos_rec('Z9', 'ZZZ-2026-0001')])

_ds_root, _b3_root = R.OTM_JSON_ROOT, R.B3_JSON_ROOT
try:
    R.OTM_JSON_ROOT, R.B3_JSON_ROOT = ds, b3
    trade = {r['id_b3']: r for r in R._ops_swap_trade_rows(REF_D)}
finally:
    R.OTM_JSON_ROOT, R.B3_JSON_ROOT = _ds_root, _b3_root
    shutil.rmtree(tmp, ignore_errors=True)

check('CEM-2026-3184 vira CEM', trade.get('A1', {}).get('lob'), 'CEM')
# Identificador sem token conhecido -> celula VAZIA, que pede cadastro em vez de
# rotular a linha com uma LOB inventada.
check('identificador sem token fica vazio', trade.get('Z9', {}).get('lob'), '')
check('os numeros crus viajam para o Settlement Summary',
      '_settle_n' in trade.get('A1', {}), True)

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 8. a ordem das colunas concorda nas TRES listas ==')
HTML = read('apps/templates/pages/other-products-summary.html')
head = HTML.split('id="ops-summary-table"', 1)[1].split('</thead>', 1)[0]
ths = re.findall(r'<th data-lang="ops-col-([a-z0-9-]+)"', head)
from_html = [t.replace('-', '_') for t in ths if t not in ('actions', 'status')]
# A partir do `row.add(` — antes dele o JS ja tocou em `r.obs` para montar o
# <input>, e apanhar essa mencao deslocaria a lista inteira.
js = HTML.split('(j.summary || []).forEach', 1)[1].split('dtSummary.row.add(', 1)[1].split('});', 1)[0]
from_js = re.findall(r'(?:esc|accountHtml)\(r\.(\w+)', js) + ['obs']
SRC = read('apps/pages/routes.py')
m = re.search(r'_OPSSUM_COLS = \((.*?)\)\n', SRC, re.S)
from_py = re.findall(r"'(\w+)'", m.group(1)) if m else []
EXPECTED = ['counterparty', 'lob', 'product', 'receive', 'pay', 'settlement_net',
            'direction', 'account', 'obs']
# O <th> chama a coluna de "Settlement Net"; o payload chama o campo de
# `net_type` (e o TIPO de net, nao um valor). Mesma coluna, nomes diferentes de
# proposito — a comparacao normaliza o par.
check('a ordem pedida esta no cabecalho', from_html, EXPECTED)
check('o rowMaker do JS segue a mesma',
      [c if c != 'net_type' else 'settlement_net' for c in from_js], EXPECTED)
check('_OPSSUM_COLS segue a mesma',
      [c if c != 'net_type' else 'settlement_net' for c in from_py], EXPECTED)
check('a linha de filtros tem uma caixa por coluna filtravel',
      head.count('<input type="text" placeholder='), len(EXPECTED) + 1)
check('o DataTables sabe quantas colunas de dado ha',
      "initTable('ops-summary-table', 9)" in HTML, True)

print('\n== 9. a regra e a MESMA do NDF, nao uma copia ==')
import inspect                                            # noqa: E402
body = inspect.getsource(R._opssum_rows)
for fn in ('_ndfsum_net_type', '_ndfsum_account_fmt', '_ndfsum_obs_auto', '_ndfsum_refdata_spn'):
    check('%s vem do NDF' % fn, fn in body, True)
check('a observacao tem endpoint para persistir',
      "@blueprint.route('/api/other-products-summary/observation'" in SRC, True)
check('o JS salva a observacao', "'/api/other-products-summary/observation'" in HTML, True)

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
