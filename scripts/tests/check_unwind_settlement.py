"""check_unwind_settlement.py — a recompra de OPCAO de Commodities e de SWAP da
EDG segue a esteira inteira, como a de NDF de Commodities (mesa, 21/10/2026).

"Tudo que for recompra contra CLIENTE tera o Termo de Resilicao; o que for
contra Atacama e Lawton tem o arquivo da Intrag" — e a liquidacao entra no
Other Products (Trade Level, Summary, TED), no Settlement Advice da pagina do
produto e no AVISO DE RECOMPRA. Antes, so o NDF de Commodities chegava la: a
opcao e o swap paravam na tela de Unwinds, e o cadastro `opb3-events` (lista
branca: swap so diferencial/premio, opcao so exercicio/premio) barrava a
antecipacao tambem pelo lado da B3.

O que se prende:

  1. a ESTEIRA: as duas paginas no `PAGINAS_COM_TERMO`, os sources na
     plataforma, o rotulo do card, as familias do backfill (sem a perna do
     fundo);
  2. o TERMO, mesmo modelo e mesmas colunas, so os valores mudam: o eixo e a
     moeda por produto (`para_o_termo`), o Anexo I (opcao em QUANTIDADE, swap
     em BRL), o XML com o produto RECOMPRADO (`OPTION`/`SWAP`, o swap so em
     reais) e o aviso quando um Termo junta produtos;
  3. a LIQUIDACAO lida por pagina: o aviso de termo e o Pay/Rec seguem SO com o
     NDF de Commodities; as curvas do swap na visao do banco somam o caixa;
  4. o aviso de OPCAO: a linha UNWIND sem IR (so premio paga), a perna do fundo
     fora do documento, o e-mail de recompra (assunto, tabela, prioridade) e o
     Trade Level;
  5. o aviso de SWAP e o Trade Level de swap: a MESMA leitura, o IR do swap, o
     contrato fora da leitura da B3, o e-mail de recompra.

    OTC_SHARED_DRIVE_ROOT=/tmp/otc-share python scripts/tests/check_unwind_settlement.py
"""
import os
import re
import sys
import tempfile
from datetime import date, datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, ROOT)
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')
if os.name != 'nt' and not os.environ.get('OTC_SHARED_DRIVE_ROOT'):
    os.environ['OTC_SHARED_DRIVE_ROOT'] = tempfile.mkdtemp(prefix='otc-share-')

FALHAS = []


def check(nome, cond, extra=''):
    print(('  ok  ' if cond else ' FAIL ') + nome + (('  — ' + str(extra)) if (not cond and extra) else ''))
    if not cond:
        FALHAS.append(nome)


from run import app                                                        # noqa: E402
from apps.pages import routes as R                                         # noqa: E402
from apps.pages import otc_emails as E                                     # noqa: E402
from apps.pages import manual_conf as MC                                   # noqa: E402
from apps.pages.platform import confirmations as CF                        # noqa: E402
from apps.pages.platform import settlement as SET                          # noqa: E402
from apps.pages.platform import manual_confirmation as PMC                 # noqa: E402
from apps.pages.features.unwinds import catalog as CAT                     # noqa: E402
from apps.pages.features.unwinds import commands as F1                     # noqa: E402
from apps.pages.features.unwinds import domain as FD                       # noqa: E402
from apps.pages.features.unwinds.product import commands as P              # noqa: E402
from apps.pages.features.unwinds.product import domain as PD               # noqa: E402

OPT = CAT.page('options/commodities')
SWP = CAT.page('swap/edg')
NDFC = CAT.page('ndf/commodities')
HOJE = date(2026, 10, 21)

L_OPT = {'_id': 'o1', 'DealID': 'ATS-OPT-1', 'Contract': '27X00001234', 'Counterparty': 'CLIENTE ALFA SA',
         'TaxID': '12345678000190', 'Underlying': 'brent', 'OriginalNotional': 5000, 'UnwoundBefore': 0,
         'UnwoundNotional': 1000, 'UnitPremium': 2.5, 'FXRate': 5.10, 'Result': -12750.0,
         'Direction': 'PAY', 'TradeDate': '2026-03-02', 'SettlementDate': '2026-10-21',
         'PartyAccount': '73760.00-9'}
L_SWP = {'_id': 's1', 'DealID': '70045952', 'Contract': '25L03771509', 'Counterparty': 'REDE DOR SAO LUIZ SA',
         'TaxID': '06047087000139', 'InstrumentID': 'RDOR3', 'LOB': 'EDG', 'OriginalNotional': 3338928.0,
         'UnwoundBefore': 0, 'UnwoundNotional': 3338928.0, 'Result': -1180434.45, 'Direction': 'PAY',
         'OurCurve': 'CDI', 'CptyCurve': 'RDOR3', 'TradeDate': '2025-12-23', 'MaturityDate': '2026-12-23',
         'SettlementDate': '2026-10-21', 'PartyAccount': '73760.00-9',
         'EquityLeg': -1300000.0, 'FundingLeg': 119565.55,
         'LegSides': {'visao': 'banco', 'EquityLeg': 'cliente', 'FundingLeg': 'banco'}}

print('== 1. a esteira ==')
check('as duas paginas tem esteira e Termo',
      PD.PAGINAS_COM_TERMO == {'NDF/Commodities': 'UNWIND NDF COMM',
                               'Options/Commodities': 'UNWIND OPTION COMM', 'Swap/EDG': 'UNWIND SWAP'})
check('...e a plataforma conhece os sources',
      {'UNWIND OPTION COMM', 'UNWIND SWAP'} <= set(R._MC_CONFIRMATION_SOURCES))
check('o card diz o produto recomprado',
      (MC.confirmation_label('UNWIND OPTION COMM'), MC.confirmation_label('UNWIND SWAP')) ==
      ('TERMO DE RESILICAO OPTION COMMODITIES', 'TERMO DE RESILICAO SWAP'))
check('opcao de commodities e LOB COMMODITY; o swap leva a LOB do deal',
      (PMC._lob_for_source('UNWIND OPTION COMM'), PMC._lob_for_source('UNWIND SWAP', {'LOB': 'EDG'})) ==
      ('COMMODITY', 'EDG'))
import importlib.util as _iu                                                # noqa: E402
_spec = _iu.spec_from_file_location('bf', os.path.join(ROOT, 'scripts', 'backfill_manual_confirmations.py'))
BF = _iu.module_from_spec(_spec)
_spec.loader.exec_module(BF)
check('o backfill tem as duas familias',
      (BF.FAMILIES['Unwind Options Commodities']['source'], BF.FAMILIES['Unwind Swap EDG']['source']) ==
      ('UNWIND OPTION COMM', 'UNWIND SWAP'))
_bf_src = open(os.path.join(ROOT, 'scripts', 'backfill_manual_confirmations.py'), encoding='utf-8').read()
check('...e o backfill pula a recompra do FUNDO (o import ja pulava)',
      'if _ufase1.e_do_fundo(deal):' in _bf_src)

print('\n== 2. o Termo: mesmo modelo, os valores do produto ==')
with app.test_request_context():
    t_opt, t_swp = PD.para_o_termo(OPT, L_OPT), PD.para_o_termo(SWP, L_SWP)
    check('opcao: o eixo e a MERCADORIA (Underlying), a moeda do contrato o dolar',
          (t_opt['Currency'], t_opt['Commodity'], t_opt['MoedaDoContrato'], t_opt['AthenaID']) ==
          ('BRENT', 'BRENT', 'USD', 'ATS-OPT-1'))
    check('swap: eixo e moeda em BRL', (t_swp['Currency'], t_swp['MoedaDoContrato']) == ('BRL', 'BRL'))
    a_opt, _ = FD.termo_linha(t_opt)
    a_swp, _ = FD.termo_linha(t_swp)
    check('Anexo I da opcao: a QUANTIDADE sem prefixo de moeda, o saldo e o Valor de Resilicao em R$',
          (a_opt['valorBaseLiq'], a_opt['novoValorBase'].strip(), a_opt['valorResilicao'],
           a_opt['registroCetip'], a_opt['numConf']) ==
          (FD.num_br(1000.0), FD.num_br(4000.0), 'R$ ' + FD.num_br(12750.0), '27X00001234', 'ATS-OPT-1'),
          a_opt)
    check('...parcial, e quem paga e o banco (Parte A)',
          (a_opt['resilicao'], a_opt['pagador']) == (FD.RESILICAO_PARCIAL, FD.PAGADOR_PARTE_A))
    check('Anexo I do swap: o Valor Base em BRL, recompra TOTAL',
          (a_swp['valorBaseLiq'], a_swp['resilicao'], a_swp['novoValorBase']) ==
          ('BRL ' + FD.num_br(3338928.0), FD.RESILICAO_TOTAL, FD.NOVO_BASE_ZERO), a_swp)

    d_opt = P.confirmation_deal(OPT, L_OPT, HOJE)
    d_swp = P.confirmation_deal(SWP, L_SWP, HOJE)
    check('o deal da opcao declara OPTION, USD e o FX da recompra',
          (d_opt['XmlTipo'], d_opt['XmlCcy'], d_opt['UnwoundBRL'], d_opt['Currency']) ==
          ('OPTION', 'USD', 12750.0, 'BRENT'))
    check('o deal do swap declara SWAP, BRL e a LOB EDG',
          (d_swp['XmlTipo'], d_swp['XmlCcy'], d_swp['LOB'], d_swp['Currency']) == ('SWAP', 'BRL', 'EDG', 'BRL'))
    check('perna do XML: opcao em USD pelo FX, swap so em reais',
          (CF._conf_unwind_legs(d_opt, {}), CF._conf_unwind_legs(d_swp, {})) ==
          ((12750.0 / 5.10, 12750.0), (0.0, 1180434.45)))
    _n, x_opt, _w = CF._conf_unwind_xml([(d_opt, {})], 'BRENT', datetime(2026, 10, 21))
    _n, x_swp, _w = CF._conf_unwind_xml([(d_swp, {})], 'BRL', datetime(2026, 10, 21))
    check('XML da opcao: tipoOperacao OPTION, evento de resilicao',
          '<tipoOperacao>OPTION</tipoOperacao>' in x_opt and '<tipoEvento>RE</tipoEvento>' in x_opt)
    check('XML do swap: tipoOperacao SWAP, sem moeda estrangeira',
          '<tipoOperacao>SWAP</tipoOperacao>' in x_swp
          and re.search(r'<moedaEstrangeira>\s*</moedaEstrangeira>|<moedaEstrangeira/>', x_swp) is not None,
          x_swp[:400])
    d_ndf = dict(d_opt, XmlTipo='NDF')
    _n, _x, w_mix = CF._conf_unwind_xml([(d_opt, {}), (d_ndf, {})], 'BRENT', datetime(2026, 10, 21))
    check('Termo que junta produtos diferentes AVISA', any('produtos diferentes' in w for w in w_mix), w_mix)

print('\n== 3. a liquidacao lida por pagina ==')
_entries = P.queries.entries
P.queries.entries = lambda page, dia: {'NDF/Commodities': [dict(L_OPT, _id='n1', DealID='N1', Contract='C1',
                                                                Commodity='BRT', Direction='RECEIVE', Result=10.0)],
                                       'Options/Commodities': [L_OPT],
                                       'Swap/EDG': [L_SWP]}.get(page.get('dir'), []) \
    if dia == '2026-10-21' else []
try:
    with app.test_request_context():
        c = F1.commodity_settlement_rows(HOJE)
        o = F1.option_commodity_settlement_rows(HOJE)
        s = F1.swap_edg_settlement_rows(HOJE)
finally:
    P.queries.entries = _entries
check('o aviso de termo (e o Pay/Rec, como COMM TER) segue SO com o NDF de Commodities',
      [r['_chave'] for r in c] == ['N1'])
check('a opcao le so a opcao, com o sinal do banco', [(r['_chave'], r['_settlement']) for r in o] ==
      [('ATS-OPT-1', -12750.0)])
check('o swap le so o swap', [r['_chave'] for r in s] == ['70045952'])
banco, cliente = PD.curvas_do_banco(L_SWP)
check('curvas do swap na visao do banco: a perna do banco e a do cliente (com o sinal trocado)',
      (banco, cliente) == (119565.55, -1300000.0), (banco, cliente))
_cli = dict(L_SWP, EquityLeg=1300000.0, FundingLeg=-119565.55,
            LegSides={'visao': 'cliente', 'EquityLeg': 'cliente', 'FundingLeg': 'banco'})
check('...a mesma resposta com o recap na visao do CLIENTE', PD.curvas_do_banco(_cli) == (119565.55, -1300000.0))
check('...e somadas dao o caixa do banco', round(banco + cliente, 2) == -1180434.45)

# ── o ambiente das duas liquidacoes: sem arquivo nenhum, so a recompra ──────
_FUNDO_OPT = dict(L_OPT, _id='o2', DealID='ATS-OPT-2', Counterparty='LAWTON MULTIMERCADO EXCLUSIVO',
                  Result=12750.0, Direction='RECEIVE')
_FUNDO_SWP = dict(L_SWP, _id='s2', DealID='70045953', Contract='25L03771510',
                  Counterparty='ATACAMA MULTIMERCADO', Result=1180434.45, Direction='RECEIVE')


class _Motor(object):
    @staticmethod
    def option_commodity_settlement_rows(ref):
        return [dict(L_OPT, _settlement=-12750.0, _chave='ATS-OPT-1'),
                dict(_FUNDO_OPT, _settlement=12750.0, _chave='ATS-OPT-2')]

    @staticmethod
    def swap_edg_settlement_rows(ref):
        b, c = PD.curvas_do_banco(L_SWP)
        return [dict(L_SWP, _settlement=-1180434.45, _chave='70045952', _curva_banco=b, _curva_cliente=c),
                dict(_FUNDO_SWP, _settlement=1180434.45, _chave='70045953', _curva_banco=-b, _curva_cliente=-c)]

    @staticmethod
    def e_do_fundo(l):
        n = str(l.get('Counterparty') or '').upper()
        return 'LAWTON' in n or 'ATACAMA' in n

    @staticmethod
    def commodity_settlement_rows(ref):
        return []


_TROCA = {
    (R, '_unwind_engine'): lambda: _Motor,
    (R, '_opb3_settle_rows'): lambda ref: [],
    (R, '_opb3_load'): lambda ref: (None, []),
    (R, '_lpopt_collect'): lambda ref: {'columns': [], 'rows': []},
    (R, '_ndfadv_otm_by_suffix'): lambda ref: ({}, {}),
    (R, '_ops_equity_link'): lambda ref: {},
    (R, '_optadv_cognos_prm'): lambda ref: ({}, {}),
    (R, '_ndfsum_refdata_spn'): lambda: {},
    (R, '_cpd_load'): lambda: [],
    (R, '_b3_account_le'): lambda conta: 'BANCO',
    (R, '_ndf_le_row'): lambda le: {'NAME': 'BANCO J.P. MORGAN S/A'},
    (R, '_optadv_edits_load'): lambda ref: (None, {}),
    (R, '_swadv_edits_load'): lambda ref: (None, {}),
    (SET, '_ops_swap_ir_rate'): lambda cliente, prazo, recebe: (0.15 if recebe else 0.0) if prazo else None,
    (SET, '_ops_is_internal_cpty'): lambda nome, spn='': 'ATACAMA' in str(nome).upper(),
    (E, '_build_cpdetails_index'): lambda: {},
}
_ORIG = {k: getattr(*k) for k in _TROCA}
for (mod, nome), fn in _TROCA.items():
    setattr(mod, nome, fn)
try:
    with app.test_request_context():
        ref = datetime(2026, 10, 21)
        print('\n== 4. o aviso de OPCAO ==')
        rows = R._optadv_collect(ref)
        u = [r for r in rows if r.get('unwind')]
        check('as duas recompras entram como UNWIND, sem IR (so o premio paga)',
              [(r['b3_id'], r['settle_type'], r['ir'], r['liquido']) for r in u] ==
              [('27X00001234', 'UNWIND', 0.0, -12750.0), ('27X00001234', 'UNWIND', 0.0, 12750.0)], u)
        check('...a perna do fundo fica na tabela e sai do documento',
              [r['no_advice'] for r in u] == [False, True])
        check('...nas colunas da tela: Ptax = FX, quantidade recomprada, sem cotacao',
              u[0]['cells'][5:8] == ['5.1', R._OPTADV_FX_NA, '1,000.00'], u[0]['cells'])
        em = R._optadv_email_rows(ref)
        check('o e-mail so leva a do cliente, com a tabela da recompra',
              len(em) == 1 and em[0]['headers'] == R._OPTADV_UNWIND_EMAIL_HEADERS
              and em[0]['cells'][6] == '1,000.00' and em[0]['cells'][7] == '2.5000', em)
        dr = E.build_ndfc_settlement_emails(em, R._optadv_email_headers(), '21/10/2026', product_label='Opção')
        check('aviso de recompra: assunto, prioridade alta',
              len(dr) == 1 and dr[0]['subject'].startswith(
                  '(Recompra) Liquidação de Operação de Derivativo (Opção de Commodities) + Callback - 21/10/2026')
              and dr[0].get('importance') == 'high', [d['subject'] for d in dr])
        tl = SET._ops_opt_trade_rows(HOJE)
        check('Trade Level: OPTION/UNWIND, a do fundo fora do documento',
              [(r['product'], r['settle_type'], r['_settle_n'], r['_no_advice']) for r in tl] ==
              [('OPTION', 'UNWIND', -12750.0, False), ('OPTION', 'UNWIND', 12750.0, True)], tl)

        print('\n== 5. o aviso de SWAP e o Trade Level de swap ==')
        tr = SET._ops_swap_trade_rows(HOJE)
        check('Trade Level: SWAP/UNWIND da EDG, com o caixa do e-mail',
              [(r['product'], r['lob'], r['settle_type'], r['id_b3'], r['_settle_n']) for r in tr] ==
              [('SWAP', 'EDG', 'UNWIND', '25L03771509', -1180434.45),
               ('SWAP', 'EDG', 'UNWIND', '25L03771510', 1180434.45)], tr)
        check('...o IR do swap: o banco pagando, a contraparte recebe e retem; recebendo, nao',
              (round(tr[0]['_tax_n'], 2), tr[1]['_tax_n']) == (round(1180434.45 * 0.15, 2), 0.0), tr)
        check('...a perna do fundo (Atacama) fora do documento', [r['_no_advice'] for r in tr] == [False, True])
        sa = R._swadv_collect(ref)
        check('Settlement Advice: a MESMA leitura, nas colunas do aviso de swap',
              [(r['cells'][2], r['cells'][7], r['cells'][9], r['bruto'], r['unwind']) for r in sa] ==
              [('25L03771509', 'CDI', 'RDOR3', -1180434.45, True),
               ('25L03771510', 'CDI', 'RDOR3', 1180434.45, True)], [r['cells'] for r in sa])
        check('...Curva Banco e Curva Cliente somam o Resultado Bruto',
              round(sa[0]['curva_banco'] + sa[0]['curva_cliente'], 2) == sa[0]['bruto'])
        se = R._swadv_email_rows(ref)
        check('o e-mail so leva a do cliente, com o Valor Base Recomprado',
              len(se) == 1 and se[0]['headers'] == R._SWADV_UNWIND_EMAIL_HEADERS
              and len(se[0]['cells']) == len(R._SWADV_UNWIND_EMAIL_HEADERS), se)
        ds = E.build_swap_settlement_emails(se, R._swadv_email_headers(False), R._swadv_email_headers(True),
                                            '21/10/2026')
        check('aviso de recompra de swap: assunto, prioridade alta',
              len(ds) == 1 and ds[0]['subject'].startswith(
                  '(Recompra) Liquidação de Operação de Derivativo (Swap) + Callback - 21/10/2026')
              and ds[0].get('importance') == 'high', [d['subject'] for d in ds])
        blk_rows, blk = SET._opsadv_block_incomplete('swap', se, R._swadv_email_headers(False))
        check('o bloqueador acha as colunas de valor no cabecalho da recompra', not blk and len(blk_rows) == 1, blk)
finally:
    for (mod, nome), fn in _ORIG.items():
        setattr(mod, nome, fn)

print()
if FALHAS:
    print('FALHAS (%d):' % len(FALHAS))
    for f in FALHAS:
        print('  -', f)
    sys.exit(1)
print('TUDO OK')
