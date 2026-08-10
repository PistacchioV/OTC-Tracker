"""Other Products: a operacao de EQUITY, no Trade Level e no Settlement Advice.

A B3 registra essas operacoes como SWAP, entao elas JA entram nas duas telas
pelo Operations B3. O que falta nelas e o outro lado: o **Swap Athena e so de
CEM** e nao tem linha nenhuma para equity. Sem ele a linha saia com o nome curto
da B3 (SAFRABM, INTRAGATACAMAFDO), sem Internal ID, sem Settlement e com as tres
colunas de valor em branco -- e, sem Settlement, ficava fora do Settlement
Summary, que e a fonte do aviso.

A rota que substitui o Athena tem tres paradas:

  Operations B3 --Titulo--> Latam Desk Position --Deal_Ref--> OTM Settlements
                            CLEARING_TRD_ID_INT               270WI<Deal_Ref>
                            CLEARING_TRD_ID_CLNT              270WC<Deal_Ref>

O que este script prende:

  1. o de-para pelo TITULO (e nao pelo OTM): partir do OTM criava uma segunda
     linha para o mesmo trade, ao lado da que o Operations B3 ja produzia;
  2. a coluna de clearing que casou decidindo a perna -- INT leva ao 270WI,
     CLNT ao 270WC. Trocadas, a linha exibe o identificador da outra ponta;
  3. Curva Banco = os fluxos POSITIVOS do OTM, Curva Cliente = os NEGATIVOS,
     Resultado Bruto = a soma dos dois;
  4. o nome saindo do Reference Data pelo Cpty SPN, nunca do nome curto da B3;
  5. a perna interna ficando no Trade Level e saindo do Settlement Summary e do
     Settlement Advice;
  6. o swap de CEM (que TEM Athena) continuando exatamente como estava.

Nao encosta em dado real: as fontes sao um tempfile, os cadastros sao stub e as
raizes do modulo voltam no finally.
"""
import io
import json
import os
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


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False)


REF = date(2026, 8, 10)
REF_DT = datetime(2026, 8, 10)

# Cadastros do stub. Os de swap saem do SEED (e a formula da planilha que precisa
# ficar fixa, nao a tabela editada de hoje); o `le-spn` e escrito aqui porque e
# ele que responde "esta contraparte e nossa?".
_SEED_MAPS = ('opb3-events', 'swap-ir-client', 'swap-ir-term')
_LE_SPN = [{'LE': 'ATACAMA', 'NAME': 'ATACAMA FUNDO DE INVESTIMENTO', 'SPN': '9911', 'NOTES': ''},
           {'LE': 'JPM', 'NAME': 'BANCO J.P MORGAN S.A', 'SPN': '', 'NOTES': ''}]
_real_mapping_rows = R._mapping_rows
_real_otm_cpty = R._otm_cpty_name


def _maps(key):
    if key in _SEED_MAPS:
        return [dict(r) for r in R._MAPPING_DEFS[key]['seed']]
    if key == 'le-spn':
        return [dict(r) for r in _LE_SPN]
    return _real_mapping_rows(key)


def opb3(titulo, tipo_op, valor, cpty):
    return {'Conta': '73760.00-9', 'Tipo Operação': tipo_op, 'C/V': 'CREDOR',
            'Título': titulo, 'Tipo Título': 'SWAP', 'Tipo de Regime': '',
            'Data Vencimento': '05/08/2026', 'Valor': valor,
            'Modalidade Liquidação': '', 'Status': '', 'Data Liquidação': '10/08/2026',
            'Contraparte (Nome Simpl.)': cpty, 'Conta Contraparte': '', 'Num Ctrl Operação': ''}


def otm(tid, amt, spn='', name='', under=''):
    return {'Trade Id': tid, 'Amount': amt, 'Currency': 'BRL', 'Cpty SPN': spn,
            'Cpty Name': name, 'Owner Legal Entity': 'BANCO', 'Underlying': under,
            'Asset Class': 'EQUITIES'}


tmp = tempfile.mkdtemp(prefix='ops-equity-test-')
ds = os.path.join(tmp, 'ds')
b3 = os.path.join(tmp, 'b3')
dia = os.path.join(ds, '2026', '08', '10')

# A B3 registra as duas pernas da MESMA operacao como dois Titulos de swap.
write_json(os.path.join(dia, 'operations-b3_20260810.json'), [
    opb3('B3-CLNT-222', 'PAGAMENTO DE DIF. DE JUROS', '-130.000,00', 'SAFRABM'),
    opb3('B3-INT-111', 'PAGAMENTO DE DIF. DE JUROS', '130.000,00', 'INTRAGATACAMAFDO'),
    # Um swap de CEM de verdade, com linha no Athena -- tem de continuar igual.
    opb3('CEM-1', 'PAGAMENTO DE DIF. DE JUROS', '500,00', 'CLIENTE B3'),
])

# Athena: SO o swap de CEM. E a premissa do caso -- equity nao esta ali.
write_json(os.path.join(dia, 'br-onshore-settlements_20260810.json'), [
    {'CETIP ID': 'CEM-1', 'Kapital ID': 'K1', 'Owner Legal Entity': 'BANCO J.P. MORGAN',
     'CounterParty': 'SUZANO SA', 'SPN': '1', 'Owner curve': '900,00',
     'Counterparty curve': '-400,00', 'BRL Net Amount': '500,00',
     'Direction': 'Counterparty receives'},
])

# Latam: UMA linha cobre as duas pernas. O Deal_Ref vem com largura de campo
# diferente do Trade Id de proposito -- um lado zera a esquerda, o outro nao.
write_json(os.path.join(dia, 'latam-desk-position_20260810.json'), [
    {'Deal_Ref': '12345', 'Deal_ID': 'D12345', 'CALLPUT': 'CALL',
     'Underlying_Name': 'PETROBRAS PN', 'UNDERLYING_RIC': 'PETR4.SA',
     'Trade_Date': '20260701',
     'CLEARING_TRD_ID_INT': 'B3-INT-111', 'CLEARING_TRD_ID_CLNT': 'B3-CLNT-222'},
])

write_json(os.path.join(dia, 'otm-settlement_20260810.json'), [
    # Perna do CLIENTE: dois fluxos -> Curva Banco 20k, Curva Cliente -150k,
    # Resultado Bruto -130k (o banco paga, logo a contraparte recebe e ha IR).
    otm('270WC0012345', '20000.00', '1808267', 'SAFRA TEXTO LIVRE', 'PETR4'),
    otm('270WC0012345', '-150000.00', '1808267', 'SAFRA TEXTO LIVRE'),
    # Perna INTERNA do mesmo Deal_Ref.
    otm('270WI0012345', '130000.00', '9911', 'ATACAMA'),
    # O swap de CEM, chaveado pelo Kapital ID.
    otm('K1', '500.00'),
])

_roots = (R.OTM_JSON_ROOT, R.LATAM_JSON_ROOT, R.B3_JSON_ROOT)
try:
    R.OTM_JSON_ROOT = R.LATAM_JSON_ROOT = ds
    R.B3_JSON_ROOT = b3                      # sem posicao: LOB e datas vem de outro lugar
    R._mapping_rows = _maps
    R._otm_cpty_name = (lambda spn: {'9911': 'ATACAMA FUNDO DE INVESTIMENTO',
                                     '1808267': 'SAFRA CORRETORA LTDA'}.get(R._spn_key(spn), ''))
    trade = R._ops_swap_trade_rows(REF)
    resumo = R._opssum_rows(trade, REF_DT)
    aviso = R._swadv_collect(REF_DT)
    internos = tuple(R._ops_is_internal_cpty(n) for n in
                     ('ATACAMA FUNDO DE INVESTIMENTO', 'BANCO J.P MORGAN S.A', 'SUZANO SA',
                      'BANCO SAFRA S.A. — CLIENTE', 'ATACAMA FDO INV MULTIMERCADO'))
finally:
    R.OTM_JSON_ROOT, R.LATAM_JSON_ROOT, R.B3_JSON_ROOT = _roots
    R._mapping_rows, R._otm_cpty_name = _real_mapping_rows, _real_otm_cpty
    shutil.rmtree(tmp, ignore_errors=True)

by_b3 = {r['id_b3']: r for r in trade}

print('\n== 1. uma linha por operacao, nao duas ==')
check('os tres Titulos viram tres linhas', sorted(by_b3), ['B3-CLNT-222', 'B3-INT-111', 'CEM-1'])
check('   e nenhuma familia paralela duplica o trade', len(trade), 3)

print('\n== 2. o que o Athena daria, vindo do Latam + OTM ==')
cli = by_b3['B3-CLNT-222']
check('perna do CLIENTE: Internal ID = o Trade Id 270WC', cli['internal_id'], '270WC0012345')
check('   e o nome sai do Reference Data pelo Cpty SPN',
      cli['counterparty'], 'SAFRA CORRETORA LTDA')
check('   nao do nome curto da B3', cli['counterparty'] != 'SAFRABM', True)
check('   Settlement = soma dos fluxos do OTM', cli['settlement'], '-130,000.00')
check('   Settlement B3 continua vindo do Operations B3', cli['settlement_b3'], '-130,000.00')
check('   Difference fecha', cli['difference'], '0.00')
check('   Type = o ativo subjacente', cli['type'], 'PETROBRAS PN')
check('   LOB rotula a linha como equity', cli['lob'], 'EQUITIES')
check('   e o produto continua SWAP (e como a B3 registra)', cli['product'], 'SWAP')

itn = by_b3['B3-INT-111']
check('perna INTERNA: a coluna INT leva ao Trade Id 270WI',
      itn['internal_id'], '270WI0012345')
check('   e o nome e o da entidade', itn['counterparty'], 'ATACAMA FUNDO DE INVESTIMENTO')
check('   com o valor da propria perna', itn['settlement'], '130,000.00')

print('\n== 3. o IR sai da mesma tabela do swap ==')
# Trade_Date 01/07/2026 .. liquidacao 10/08/2026 = 40 dias -> faixa ate 180 = 22,5%.
check('a aliquota usa o prazo do Trade_Date do Latam', cli['tax_income'], '29,250.00')
check('   sem Trade_Date nao haveria prazo nem aliquota', bool(cli['tax_income']), True)

print('\n== 4. o swap de CEM nao mudou ==')
cem = by_b3['CEM-1']
check('Internal ID continua o Kapital ID', cem['internal_id'], 'K1')
check('   o nome continua o do Athena', cem['counterparty'], 'SUZANO SA')
check('   e o Type continua VCP/Calculado', cem['type'], 'Calculado')

print('\n== 5. quem gera aviso ==')
check('a entidade do le-spn e perna interna', internos[0], True)
check('   o banco DO GRUPO tambem', internos[1], True)
check('   mas um banco CLIENTE nao (a regra ingenua cortaria o Safra)',
      internos[3], False)
# O `Reference Data Name` da ATACAMA nasce VAZIO no seed: sem o token da LE, a
# perna interna so seria reconhecida depois de alguem preencher a razao social.
check('   o token da LE reconhece a conta por extenso', internos[4], True)
check('   um cliente de verdade nao', internos[2], False)
check('a perna interna FICA no Trade Level', itn.get('id_b3'), 'B3-INT-111')
check('   e sai do Settlement Summary (a fonte do aviso)',
      sorted(r['counterparty'] for r in resumo),
      ['SAFRA CORRETORA LTDA', 'SUZANO SA'])
check('   e sai tambem do Settlement Advice',
      sorted(r['counterparty'] for r in aviso), ['SAFRA CORRETORA LTDA', 'SUZANO SA'])

print('\n== 6. as tres colunas de valor do aviso ==')
adv = {r['counterparty']: r for r in aviso}
eq = adv['SAFRA CORRETORA LTDA']
check('Curva Banco = os fluxos POSITIVOS do OTM', eq['curva_banco'], 20000.0)
check('Curva Cliente = os NEGATIVOS', eq['curva_cliente'], -150000.0)
check('Resultado Bruto = a soma dos dois', eq['bruto'], -130000.0)
check('   e as celulas impressas seguem os mesmos numeros',
      (eq['cells'][8], eq['cells'][10], eq['cells'][11]),
      ('20,000.00', '-150,000.00', '-130,000.00'))
cemadv = adv['SUZANO SA']
check('o swap de CEM continua lendo as curvas do Athena',
      (cemadv['cells'][8], cemadv['cells'][10]), ('900.00', '-400.00'))

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
