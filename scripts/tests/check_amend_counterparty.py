"""Amend da API: a contraparte acompanha o Deal ID.

Duas coisas travavam a contraparte na PRIMEIRA importacao:

  * SPN, Client e Tax ID estavam em `_ND_AMEND_SKIP` — o amend nunca os
    comparava. Operacao rebookada para outro cliente ficava para sempre com o
    nome antigo na tela;
  * a chave do arquivo do dia e (Deal, Client). Mudando o Client, ela nao casa e
    o deal entrava como LINHA NOVA: a operacao aparecia duas vezes, a antiga com
    a contraparte velha, e nenhuma marcada como Amend.

O contrapeso e o status: um deal ja **Success** nao pode voltar para a fila so
porque a NOSSA resolucao melhorou (§174, quando a perna interna passou a achar
SPN/Client/Tax ID que vinham vazios). A regra e o ACCRONYM — accronym igual,
mudou a resolucao, nao o negocio.

O que este script protege:

  1. os tres campos sao comparados, aplicados e registrados em AmendChanged;
  2. Success sobrevive ao enriquecimento e CAI quando troca de entidade;
  3. `_nd_amend_find`: casa por (Deal, Client), cai para o Deal quando ele e
     unico, e NAO adivinha quando o mesmo Deal tem duas pernas;
  4. os indices de AMEND_FIELD_COLS batem com COL_TO_JSON_FIELD em todas as
     paginas — indice trocado pinta a coluna errada, que e o tipo de erro que
     ja corrompeu dado nesta tela duas vezes.

Nao encosta em dado real: mappings sao stub e nada e escrito em disco.
"""
import io
import os
import re
import sys

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


MAPS = {'le-accronym': [
    {'LE': 'JPM', 'ACCRONYM': 'LM-FWDECOMBRR FXC', 'SETTLEMENT LOCATION': 'BRAZIL'},
    {'LE': 'LAWTON', 'ACCRONYM': 'CLIENT FX NDF LAWTON', 'SETTLEMENT LOCATION': 'LAWTON'},
]}
_orig = R._mapping_rows
R._mapping_rows = lambda key: MAPS.get(key, [])


def deal(**kw):
    base = {'Deal': 'D-1', 'Status': 'New', 'LE': 'JPM', 'Acronym': 'ACMEBRA',
            'SPN': '135742', 'Client': 'ACME DO BRASIL LTDA', 'TaxID': '45.985.371/0001-08',
            'Notional': '1.000,00'}
    base.update(kw)
    return base


try:
    print('\n== 1. os tres campos passaram a ser comparados ==')
    st = deal(SPN='', Client='', TaxID='')
    changed = R._nd_api_amend(st, deal())
    check('SPN/Client/TaxID entram no changed', sorted(changed), ['Client', 'SPN', 'TaxID'])
    check('o valor novo e aplicado', (st.get('SPN'), st.get('Client')),
          ('135742', 'ACME DO BRASIL LTDA'))
    check('AmendChanged registra os tres', st.get('AmendChanged'), ['Client', 'SPN', 'TaxID'])
    check('Status vai para Amend (nao era Success)', st.get('Status'), 'Amend')

    st = deal()
    check('sem mudanca, nada acontece', R._nd_api_amend(st, deal()), [])

    st = deal(Status='Canceled', Client='')
    check('Canceled nao e reaberto', R._nd_api_amend(st, deal()), [])

    print('\n== 2. Success: enriquecimento destaca, mas nao devolve para a fila ==')
    st = deal(Status='Success', SPN='', Client='', TaxID='')
    ch = R._nd_api_amend(st, deal())
    check('os campos mudam', sorted(ch), ['Client', 'SPN', 'TaxID'])
    check('o Success e mantido', st.get('Status'), 'Success')
    check('a celula e destacada mesmo assim', st.get('AmendChanged'), ['Client', 'SPN', 'TaxID'])

    # Mesmo accronym, contraparte recadastrada com outro nome: continua sendo a
    # nossa resolucao, nao o negocio.
    st = deal(Status='Success', Client='ACME BRASIL S/A')
    R._nd_api_amend(st, deal())
    check('nome novo no mesmo accronym mantem Success', st.get('Status'), 'Success')

    print('\n== 2b. Sent tem a MESMA protecao do Success ==')
    # `Sent` e o arquivo de registro ja enviado a B3, e vem ANTES do `Success`:
    # a janela em que a operacao esperava o retorno era exatamente a que estava
    # desprotegida. Trocar de book, ou passar a resolver a contraparte, devolvia
    # para `Amend` sem Checker uma operacao que ja tinha saido da mesa.
    check('a lista dos status protegidos', sorted(R._ND_AMEND_KEEP_STATUS),
          ['Sent', 'Success'])

    st = deal(Status='Sent', Checker='E930179', SPN='', Client='', TaxID='')
    ch = R._nd_api_amend(st, deal())
    check('Sent: os campos mudam', sorted(ch), ['Client', 'SPN', 'TaxID'])
    check('Sent: o status e mantido', st.get('Status'), 'Sent')
    check('Sent: a celula e destacada mesmo assim', st.get('AmendChanged'),
          ['Client', 'SPN', 'TaxID'])
    check('Sent: o Checker nao e perdido', st.get('Checker'), 'E930179')

    st = deal(Status='Sent', OtherBook='ACME-BR')
    R._nd_api_amend(st, deal(OtherBook='ACME-BR-2'))
    check('Sent: troca de book e cosmetica', st.get('Status'), 'Sent')

    st = deal(Status='Sent', LE='JPM', Acronym='ACMEBRA')
    R._nd_api_amend(st, deal(LE='LAWTON', Acronym='OUTRACP', Client='OUTRA CONTRAPARTE SA',
                             SPN='999', TaxID='00.000.000/0001-00'))
    check('Sent: troca de entidade DERRUBA para Amend', st.get('Status'), 'Amend')

    st = deal(Status='Sent', Notional='1.000,00')
    R._nd_api_amend(st, deal(Notional='2.000,00'))
    check('Sent: notional novo DERRUBA para Amend', st.get('Status'), 'Amend')

    # Os demais status continuam caindo: so quem saiu da mesa e poupado.
    for s in ('New', 'Amend', 'Pending', 'Error'):
        st = deal(Status=s, OtherBook='ACME-BR')
        R._nd_api_amend(st, deal(OtherBook='ACME-BR-2'))
        check('%s continua indo para Amend' % s, st.get('Status'), 'Amend')

    print('\n== 3. Success CAI quando a contraparte muda de verdade ==')
    st = deal(Status='Success', LE='JPM', Acronym='ACMEBRA')
    R._nd_api_amend(st, deal(LE='LAWTON', Acronym='OUTRACP', Client='OUTRA CONTRAPARTE SA',
                             SPN='999', TaxID='00.000.000/0001-00'))
    check('troca de entidade derruba para Amend', st.get('Status'), 'Amend')
    check('a contraparte nova e gravada', st.get('Client'), 'OUTRA CONTRAPARTE SA')

    print('\n== 4. quem casa com quem no arquivo do dia ==')
    A = deal(Deal='D-1', Client='ACME DO BRASIL LTDA')
    B = deal(Deal='D-2', Client='OUTRO CLIENTE SA')
    idx, by_deal = R._nd_amend_index([A, B])
    st = {'idx': idx, 'by_deal': by_deal}
    check('Deal + Client casa', R._nd_amend_find(st, deal(Deal='D-1')) is A, True)
    check('Client mudou -> casa pelo Deal',
          R._nd_amend_find(st, deal(Deal='D-1', Client='ACME BRASIL S/A')) is A, True)
    check('Client vazio -> casa pelo Deal',
          R._nd_amend_find(st, deal(Deal='D-2', Client='')) is B, True)
    check('Deal que nao existe -> None',
          R._nd_amend_find(st, deal(Deal='D-9', Client='X')), None)

    # Duas pernas do mesmo Deal: nao da para saber qual e, entao nao adivinha.
    P1 = deal(Deal='D-3', Client='PERNA UM')
    P2 = deal(Deal='D-3', Client='PERNA DOIS')
    idx2, by2 = R._nd_amend_index([P1, P2])
    st2 = {'idx': idx2, 'by_deal': by2}
    check('duas pernas: Client exato ainda casa',
          R._nd_amend_find(st2, deal(Deal='D-3', Client='PERNA DOIS')) is P2, True)
    check('duas pernas: Client novo NAO adivinha',
          R._nd_amend_find(st2, deal(Deal='D-3', Client='PERNA TRES')), None)

    # O registro do deal novo tem de alimentar os DOIS indices, senao o mesmo
    # pull insere a operacao duas vezes.
    st3 = {'idx': {}, 'by_deal': {}}
    novo = deal(Deal='D-4', Client='NOVO CLIENTE SA')
    R._nd_amend_register(st3, novo)
    check('deal inserido casa pela chave',
          R._nd_amend_find(st3, deal(Deal='D-4', Client='NOVO CLIENTE SA')) is novo, True)
    check('deal inserido casa pelo Deal',
          R._nd_amend_find(st3, deal(Deal='D-4', Client='OUTRO NOME')) is novo, True)
finally:
    R._mapping_rows = _orig

print('\n== 5. os campos NAO tocados pelo amend ==')
check('a lista de skip', sorted(R._ND_AMEND_SKIP),
      ['AmendChanged', 'B3_ID', 'Checker', 'Maker', 'Status'])

print('\n== 6. tela: AMEND_FIELD_COLS bate com COL_TO_JSON_FIELD ==')
PAGES = ['new_deals-ndf-vanilla', 'new_deals-ndf-otherpublisher',
         'new_deals-ndf-fwdstart', 'new_deals-opt-fxo']
for name in PAGES:
    src = io.open('apps/templates/pages/%s.html' % name, encoding='utf-8').read()
    m = re.search(r'var COL_TO_JSON_FIELD = \{(.*?)\};', src, re.S)
    col = {f: int(n) for n, f in re.findall(r"(\d+)\s*:\s*'([A-Za-z0-9_]+)'", m.group(1))}
    m2 = re.search(r'var AMEND_FIELD_COLS = \{(.*?)\};', src, re.S)
    amend = {f: int(n) for f, n in re.findall(r'([A-Za-z0-9_]+)\s*:\s*(\d+)', m2.group(1))}
    errados = {f: (i, col.get(f)) for f, i in amend.items() if col.get(f) != i}
    check('%s: todo indice bate' % name, errados, {})
    check('%s: a contraparte esta la' % name,
          [f for f in ('SPN', 'Client', 'TaxID') if f in amend], ['SPN', 'Client', 'TaxID'])

print('\n== 7. ponta a ponta no arquivo do dia ==')
# O caminho real: _generic_nd_persist_new_deals lendo e gravando um day file.
# O diretorio do produto e desviado para um tempfile — nada encosta no cache.
import json                                                   # noqa: E402
import tempfile                                               # noqa: E402

tmp = tempfile.mkdtemp(prefix='otc-amend-')
CFG = {'dir': tmp, 'suffix': '_ndf.json', 'label': 'Vanilla'}
_orig_cfg = R._generic_nd_cfg
R._generic_nd_cfg = lambda product: CFG
try:
    D = deal(Deal='D-77', TradeDate='04/08/2026', Client='', SPN='', TaxID='',
             Acronym='LM-FWDECOMBRR FXC', Status='Success')
    fresh, amended = R._generic_nd_persist_new_deals('vanilla', [dict(D)])
    check('primeira importacao insere', (len(fresh), amended), (1, []))

    # Mesma operacao, agora com a contraparte resolvida (§174).
    cheia = dict(D, Client='BANCO J.P MORGAN S.A', SPN='23779',
                 TaxID='33.172.537/0001-98')
    fresh2, amended2 = R._generic_nd_persist_new_deals('vanilla', [cheia])
    check('segunda passada NAO duplica', len(fresh2), 0)
    check('segunda passada amenda', amended2, ['D-77'])

    path = os.path.join(tmp, '2026', '08', '20260804_ndf.json')
    rows = json.load(io.open(path, encoding='utf-8'))
    check('o arquivo tem UMA linha', len(rows), 1)
    check('a contraparte foi gravada',
          (rows[0].get('SPN'), rows[0].get('Client')), ('23779', 'BANCO J.P MORGAN S.A'))
    check('as tres colunas ficam destacadas',
          rows[0].get('AmendChanged'), ['Client', 'SPN', 'TaxID'])
    check('o Success sobreviveu ao enriquecimento', rows[0].get('Status'), 'Success')
finally:
    R._generic_nd_cfg = _orig_cfg
    for root, dirs, files in os.walk(tmp, topdown=False):
        for f in files:
            os.remove(os.path.join(root, f))
        for d in dirs:
            os.rmdir(os.path.join(root, d))
    os.rmdir(tmp)

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
