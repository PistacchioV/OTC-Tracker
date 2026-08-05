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

print('\n== 10. a tela DIZ por que esta vazia ==')
# Os widgets leem a posicao mais recente (com walk-back), as tabelas leem o batch
# da data. Sem esta faixa, um dia sem importacao deixa a pagina se contradizendo
# em silencio: card com numero, tabela vazia, nenhuma palavra sobre o motivo.
tmp = tempfile.mkdtemp(prefix='ops-src-')
_ds_root, _b3_root = R.OTM_JSON_ROOT, R.B3_JSON_ROOT
try:
    R.OTM_JSON_ROOT, R.B3_JSON_ROOT = tmp, os.path.join(tmp, 'b3')
    st = R._ops_batch_status(REF)
    check('sem nada, o Operations B3 aparece como faltando', 'Operations B3' in st['missing'], True)
    check('sem o Operations B3 o aviso e BLOQUEANTE', st['blocking'], True)
    check('sem posicao, ela tambem e apontada', 'Posição SWAP (B3)' in st['missing'], True)
    check('sem batch nenhum, nao ha dia para sugerir', st['last_batch'], None)

    # Batch da data presente + um dia anterior com batch: deixa de ser bloqueante.
    write_json(os.path.join(tmp, '2026', '07', '27', 'operations-b3_20260727.json'), [])
    write_json(os.path.join(tmp, '2026', '07', '20', 'operations-b3_20260720.json'), [])
    st = R._ops_batch_status(REF)
    check('com o Operations B3, o aviso e so informativo', st['blocking'], False)
    check('o indispensavel sai da lista', 'Operations B3' in st['missing'], False)
    check('as auxiliares seguem apontadas',
          sorted(x for x in st['missing'] if 'SWAP' not in x),
          ['OTM Settlements', 'Swap Athena', 'Swap Events'])
    check('sugere o ultimo dia com batch', st['last_batch'], '2026-07-20')
finally:
    R.OTM_JSON_ROOT, R.B3_JSON_ROOT = _ds_root, _b3_root
    shutil.rmtree(tmp, ignore_errors=True)

print('\n== 11. arquivo presente e tabela vazia: o diagnostico responde ==')
# O caso que trouxe o relato: as quatro fontes do dia estao la, e mesmo assim
# nenhuma linha aparece. A pergunta deixa de ser "que arquivo falta" — e sem
# resposta na tela nao ha o que fazer alem de abrir chamado.
def ob(titulo, op, tipo_tit='SWAP'):
    return {'Conta': '73760.00-9', 'Tipo Operação': op, 'Título': titulo,
            'Tipo Título': tipo_tit, 'Valor': '1,00', 'Data Liquidação': '05/08/2026',
            'Contraparte (Nome Simpl.)': 'X'}


REF8 = datetime(2026, 8, 5)


def diag(opb3_rows):
    tmp = tempfile.mkdtemp(prefix='ops-diag-')
    _r, _b = R.OTM_JSON_ROOT, R.B3_JSON_ROOT
    try:
        R.OTM_JSON_ROOT, R.B3_JSON_ROOT = tmp, os.path.join(tmp, 'b3')
        day = os.path.join(tmp, '2026', '08', '05')
        write_json(os.path.join(day, 'operations-b3_20260805.json'), opb3_rows)
        for k in ('br-onshore-settlements', 'eventos-swap-jpm', 'otm-settlement'):
            write_json(os.path.join(day, '%s_20260805.json' % k), [])
        return R._ops_batch_status(REF8), R._ops_swap_trade_rows(REF8.date())
    finally:
        R.OTM_JSON_ROOT, R.B3_JSON_ROOT = _r, _b
        shutil.rmtree(tmp, ignore_errors=True)


st, rows = diag([ob('A1', 'RESGATE'), ob('A1', 'RESGATE ANTECIPADO'),
                 ob('T1', 'PAGAMENTO DE PREMIO', 'TER')])
check('nenhuma linha passa', len(rows), 0)
check('conta as linhas de SWAP', (st['events'] or {}).get('swap_rows'), 2)
check('lista os Tipo Operacao do ARQUIVO',
      (st['events'] or {}).get('found'), ['RESGATE', 'RESGATE ANTECIPADO'])
check('o TER nao entra na contagem de SWAP', (st['events'] or {}).get('rows'), 3)

st, _ = diag([ob('T1', 'PAGAMENTO DE PREMIO', 'TER')])
check('arquivo sem SWAP nenhum e dito com todas as letras',
      (st['events'] or {}).get('swap_rows'), 0)

st, rows = diag([ob('A1', 'PAGAMENTO DE DIF. DE JUROS')])
check('com Tipo Operacao cadastrado, a linha sai', len(rows), 1)
check('e o diagnostico se cala', st['events'], None)

# Espaco duplo: os arquivos da B3 vem com padding, e sem colapsar o espaco a
# linha cadastrada nao casa — o swap sumiria da tela sem sinal nenhum.
check('espaco duplo casa com a linha cadastrada',
      R._ops_norm_event('PAGAMENTO DE  DIF.  DE JUROS'),
      R._ops_norm_event('PAGAMENTO DE DIF. DE JUROS'))
st, rows = diag([ob('A1', ' PAGAMENTO DE  DIF. DE JUROS ')])
check('e a linha passa de verdade', len(rows), 1)

check('a pagina consome o diagnostico de eventos', 'src.events' in HTML, True)
check('a mensagem lista os valores do arquivo', 'ev.found' in HTML, True)
check('e diz onde cadastrar', 'ops-ev-register' in HTML, True)

check('o endpoint publica o diagnostico', "'sources': sources" in SRC, True)
check('a pagina consome o diagnostico', 'setSources(j.sources' in HTML, True)
for hook in ('id="ops-src-row"', 'id="ops-src-msg"', 'id="ops-src-goto"'):
    check('a faixa existe no HTML: %s' % hook, hook in HTML, True)
# Bloqueante e informativo TEM de se distinguir na tela: mesma cor para os dois
# faria "faltou tudo" parecer "faltou um detalhe".
check('bloqueante e informativo tem cores diferentes',
      'alert-warning' in HTML and 'alert-info' in HTML, True)

print('\n== 12. Actions e Status iguais aos do NDF Summary ==')
NDF = read('apps/templates/pages/ndf-summary.html')
# As duas paginas mostram a MESMA coisa; se uma usa <select> e a outra badge, a
# pessoa le dois vocabularios para o mesmo estado. Aqui a comparacao e literal:
# os mesmos seletores, as mesmas classes de badge.
for cls in ('ops-row-act', 'ops-row-del', 'ops-row-confirm'):
    check('a classe %s existe nas duas' % cls, (cls in HTML) and (cls in NDF), True)
# O botao de acao e um quadrado arredondado de tamanho TRAVADO — sem os
# min/max uma regra do tema deixa Confirm e Delete de tamanhos diferentes.
for prop in ('min-width: 32px', 'max-width: 32px', 'border-radius: 10px !important'):
    check('o botao de acao trava "%s"' % prop, prop in HTML, True)
check('Trade Level usa badge, nao <select>', 'statusBadge(r.status' in HTML, True)
check('Settlement Summary usa a pill New/Generated/Sent', 'statusPill(r.status' in HTML, True)
for state, cls in (('Sent', 'text-bg-primary'), ('Generated', 'text-bg-success'), ('New', 'text-bg-info')):
    check('%s na mesma cor do NDF' % state,
          ("pill('%s', '%s')" % (state, cls)) in HTML
          and ("pill('%s', '%s')" % (state, cls)) in NDF, True)
# O <select> segue existindo — para a linha MANUAL do Add row, onde o estado e
# de quem digitou e nao do calculo.
check('a linha manual mantem o <select>', 'statusCell(' in HTML, True)
# Confirm que nao confirma nada seria so um botao bonito.
check('o Confirm tem endpoint', "@blueprint.route('/api/other-products-summary/mark-sent'" in SRC, True)
check('e o JS o chama', "'/api/other-products-summary/mark-sent'" in HTML, True)

tmp = tempfile.mkdtemp(prefix='ops-sent-')
_ds_root = R.OTM_JSON_ROOT
try:
    R.OTM_JSON_ROOT = tmp
    path = R._opssum_meta_path(REF)
    write_json(path, {R._opssum_key('SUZANO SA', 'CEM', 'SWAP'): {'status': 'Sent'}})
    got = R._opssum_rows([trow('SUZANO SA', 'CEM', 'SWAP', 1000.0)], REF)[0]
    check('o status confirmado sobrevive ao reload', got['status'], 'Sent')
    check('sem overlay, a linha nasce New',
          R._opssum_rows([trow('SUZANO SA', 'EDG', 'SWAP', 1.0)], REF)[0]['status'], 'New')
finally:
    R.OTM_JSON_ROOT = _ds_root
    shutil.rmtree(tmp, ignore_errors=True)

print('\n== 13. cards de reconciliacao B3 x Interno ==')


def tr(product, b3, internal):
    return {'product': product, '_b3_n': b3, '_settle_n': internal}


rec = R._ops_recon([tr('SWAP', 100.0, 100.0), tr('SWAP', 50.0, 50.0)])
check('bate quando contagem e valor concordam', rec['swap']['matched'], True)
check('contagem do lado B3', rec['swap']['b3_count'], 2)
check('valor do lado interno', rec['swap']['int_value'], '150.00')
# So o valor nao basta: duas operacoes que se anulam dariam zero dos dois lados e
# passariam por conciliadas mesmo faltando uma linha de um dos lados.
rec = R._ops_recon([tr('SWAP', 100.0, 100.0), tr('SWAP', 50.0, None)])
check('valor igual mas contagem diferente NAO bate', rec['swap']['matched'], False)
rec = R._ops_recon([tr('SWAP', 100.0, 90.0)])
check('contagem igual mas valor diferente NAO bate', rec['swap']['matched'], False)
check('a diferenca sai assinada', rec['swap']['diff_value'], '(10.00)')

# Familia sem linha no Trade Level = `na`: nao ha divergencia, ha conta que ainda
# nao e feita. Pintar de ambar leria como erro de dado.
rec = R._ops_recon([tr('SWAP', 1.0, 1.0)])
check('swap tem lado interno', rec['swap']['na'], False)
for fam in ('option', 'ndf', 'coe'):
    check('%s ainda e n/a' % fam, rec[fam]['na'], True)
check('o Total nunca e n/a', rec['total']['na'], False)
rec = R._ops_recon([tr('SWAP', 10.0, 10.0), tr('OPTION', 5.0, 5.0)])
check('o Total soma as familias', (rec['total']['b3_count'], rec['total']['b3_value']),
      (2, '15.00'))
check('produto desconhecido nao entra', R._ops_recon([tr('XPTO', 9.0, 9.0)])['total']['b3_count'], 0)

check('o endpoint publica o recon', "'recon': recon" in SRC, True)
check('a pagina consome o recon', 'setRecon(j.recon)' in HTML, True)
for cat in ('swap', 'option', 'ndf', 'coe', 'total'):
    check('card data-cat="%s"' % cat, ('data-cat="%s"' % cat) in HTML, True)
for hook in ('data-recon-b3c', 'data-recon-b3v', 'data-recon-intc', 'data-recon-intv', 'data-recon-badge'):
    check('gancho %s' % hook, hook in HTML, True)
check('Flow virou Cashflow', 'ops-sub-cashflow' in HTML and 'ops-sub-flow' not in HTML, True)
# A luz de fundo e a MESMA do NDF Summary, com o anel como variavel: box-shadow
# nao se soma entre regras, e sem a variavel a luz apagaria o anel (§181).
for rule in ('--ops-ring', '.ops-recon.is-ok', '.ops-recon.is-check', 'ops-recon--total'):
    check('a luz/o total: %s' % rule, rule in HTML, True)
check('o estado n/a existe no JS', "'ops-r-na'" in HTML, True)

print('\n== 14. todo icone de aba do /mapping existe no Tabler ==')
# Uma aba com um nome de icone que nao existe no pacote nao da erro nenhum: fica
# so o espaco em branco, e ninguem nota ate alguem reparar. Foi o caso do
# FXO Conversion Rate (ti-currency-exchange nao existe no vendors.min.css).
MAPHTML = read('apps/templates/pages/mapping.html')
VENDORS = io.open('apps/static/css/vendors.min.css', encoding='utf-8', errors='ignore').read()
icons = re.findall(r"icon:\s*'(ti-[a-z0-9-]+)'", MAPHTML)
check('ha abas com icone declarado', len(icons) > 10, True)
check('nenhum icone inexistente', [i for i in icons if ('.%s:' % i) not in VENDORS], [])

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
