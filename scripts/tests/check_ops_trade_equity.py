"""Other Products Summary > Trade Level: a linha de EQUITIES.

A operacao de equity chega ao OTM Settlements com o Trade Id do sistema
(`270WI...` / `270WC...`) e SEM o identificador da B3. Ele esta no Latam Desk
Position, e o que liga os dois e o NUMERO depois do prefixo -- o `Deal_Ref`:

  OTM Settlements --Trade Id sem prefixo--> Latam Desk Position (Deal_Ref)
                                                 |-- CLEARING_TRD_ID_INT  --> perna contra a ENTIDADE
                                                 |-- CLEARING_TRD_ID_CLNT --> perna contra o CLIENTE

O mesmo Deal_Ref cobre as DUAS pernas (Safra x Atacama), e por isso escolher a
coluna errada nao da erro nenhum: escreve na tela um identificador da B3 que
existe, so que e o da outra ponta.

O que este script prende:

  1. o de-para: prefixo ignorado, zero a esquerda ignorado dos dois lados, e o
     Trade Id sem prefixo conhecido NAO virando chave por acidente;
  2. a escolha da coluna pela CONTRAPARTE (o fato), nao pelo prefixo (a
     convencao de nomenclatura);
  3. a soma por Trade Id -- o OTM traz uma linha por fluxo de caixa, e o que
     liquida e a soma delas;
  4. a perna interna (entidade do `le-spn` ou nome comecando em BANCO) ficando
     no Trade Level e FORA do Settlement Summary, que e a fonte do aviso.

Nao encosta em dado real: as duas fontes sao um tempfile, o cadastro `le-spn` e
um stub e as raizes do modulo voltam no finally.
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
STAMP = '20260810'

# Cadastro de entidades: e por ele que se sabe que ATACAMA e perna interna. Vem
# do stub e nao do arquivo -- quem editar o le-spn pela tela nao pode derrubar
# este teste, e o que precisa ficar fixo e a REGRA, nao o cadastro de hoje.
_LE_SPN = [{'LE': 'ATACAMA', 'NAME': 'ATACAMA FUNDO DE INVESTIMENTO', 'SPN': '9911', 'NOTES': ''},
           {'LE': 'JPM', 'NAME': 'BANCO J.P MORGAN S.A', 'SPN': '', 'NOTES': ''}]
_real_mapping_rows = R._mapping_rows
_real_otm_cpty = R._otm_cpty_name


def otm(tid, amt, spn='', name='', asset='EQUITIES'):
    return {'Trade Id': tid, 'Currency': 'BRL', 'Amount': amt, 'Value Date': '2026-08-10',
            'Direction': '', 'Cpty SPN': spn, 'Cpty Name': name, 'Owner SPN': '',
            'Trade Date': '2026-08-01', 'Asset Class': asset, 'Owner Legal Entity': 'BANCO',
            'Owner Name': '', 'Exception Type': '', 'Cashflow Stage': '', 'Trade Ref': '',
            'Underlying': '', 'Product Class': '', 'Break Reason': ''}


def latam(ref, interno, cliente):
    return {'Deal_Ref': ref, 'Deal_ID': 'D' + ref, 'CALLPUT': 'CALL',
            'CLEARING_TRD_ID_INT': interno, 'CLEARING_TRD_ID_CLNT': cliente}


tmp = tempfile.mkdtemp(prefix='ops-equity-test-')
dia = os.path.join(tmp, '2026', '08', '10')

write_json(os.path.join(dia, 'otm-settlement_%s.json' % STAMP), [
    # O MESMO trade em dois fluxos -> uma linha so, com a soma (150k - 20k).
    otm('270WC0012345', 150000.00, '1808267', 'SAFRA TEXTO LIVRE DO ARQUIVO'),
    otm('270WC0012345', -20000.00, '1808267', 'SAFRA TEXTO LIVRE DO ARQUIVO'),
    # A perna interna do MESMO Deal_Ref: mesmo numero, prefixo 270WI.
    otm('270WI0012345', -130000.00, '9911', 'ATACAMA FUNDO DE INVESTIMENTO'),
    # Interna pelo NOME (comeca em BANCO), sem cadastro nenhum.
    otm('270WC0067890', -45000.00, '', 'BANCO XYZ S.A.'),
    # Sem par no Latam -> a linha aparece, com o B3 ID vazio.
    otm('270WC0099999', 77000.00, '', 'CLIENTE SEM DEAL REF'),
    # Nao e equity -> nao entra por esta familia.
    otm('K-SWAP-1', 10.00, '', 'CLIENTE DE SWAP', 'INTEREST_RATE'),
    # Trade Id sem um dos prefixos conhecidos: nao pode virar chave e casar com
    # o Deal_Ref 12345 de outra operacao.
    otm('XPTO12345', 900.00, '', 'CLIENTE DE OUTRO SISTEMA'),
])
# O Deal_Ref vem com largura de campo diferente do Trade Id de proposito: um
# lado zera a esquerda, o outro nao.
write_json(os.path.join(dia, 'latam-desk-position_%s.json' % STAMP), [
    latam('12345', 'B3-INT-111', 'B3-CLNT-222'),
    latam('0067890', 'B3-INT-333', ''),          # sem perna de cliente
])

_roots = (R.OTM_JSON_ROOT, R.LATAM_JSON_ROOT)
try:
    R.OTM_JSON_ROOT = R.LATAM_JSON_ROOT = tmp
    R._mapping_rows = (lambda key: [dict(r) for r in _LE_SPN] if key == 'le-spn'
                       else _real_mapping_rows(key))
    # SPN sem Reference Data devolve '' -- quem chama mantem o nome do arquivo.
    R._otm_cpty_name = (lambda spn: 'ATACAMA FUNDO DE INVESTIMENTO'
                        if R._spn_key(spn) == '9911' else '')
    rows = R._ops_equity_trade_rows(REF)
    todas = R._ops_trade_rows(REF)
    resumo = R._opssum_rows(rows, REF_DT)
    # Dentro do stub: quem responde 'e perna interna?' e o cadastro `le-spn`, e
    # la fora este processo le o arquivo de verdade.
    internos = tuple(R._ops_is_internal_cpty(n) for n in
                     ('ATACAMA FUNDO DE INVESTIMENTO', 'BANCO XYZ S.A.',
                      'SAFRA TEXTO LIVRE DO ARQUIVO'))
finally:
    R.OTM_JSON_ROOT, R.LATAM_JSON_ROOT = _roots
    R._mapping_rows, R._otm_cpty_name = _real_mapping_rows, _real_otm_cpty
    shutil.rmtree(tmp, ignore_errors=True)

print('\n== 1. o de-para Trade Id x Deal_Ref ==')
by_id = {r['internal_id']: r for r in rows}
check('so as linhas de EQUITIES entram', sorted(by_id),
      ['270WC0012345', '270WC0067890', '270WC0099999', '270WI0012345', 'XPTO12345'])
check('o swap nao entra por esta familia', 'K-SWAP-1' in by_id, False)
check('os dois fluxos do mesmo trade viram UMA linha', len(rows), 5)

check('perna de CLIENTE -> CLEARING_TRD_ID_CLNT',
      by_id['270WC0012345'].get('id_b3'), 'B3-CLNT-222')
check('perna INTERNA (mesmo Deal_Ref) -> CLEARING_TRD_ID_INT',
      by_id['270WI0012345'].get('id_b3'), 'B3-INT-111')
check('   o zero a esquerda nao atrapalha os dois lados',
      by_id['270WC0067890'].get('id_b3'), 'B3-INT-333')
check('sem par no Latam o B3 ID fica VAZIO, e a linha fica',
      by_id['270WC0099999'].get('id_b3'), '')
check('Trade Id sem prefixo conhecido nao casa com Deal_Ref nenhum',
      by_id['XPTO12345'].get('id_b3'), '')

print('\n== 2. o valor e a identidade ==')
check('o Settlement e a SOMA dos fluxos do trade',
      by_id['270WC0012345'].get('settlement'), '130,000.00')
check('   e o sinal viaja no valor', by_id['270WI0012345'].get('settlement'), '-130,000.00')
check('sem lado B3 nao ha divergencia a apurar',
      (by_id['270WC0012345'].get('settlement_b3'), by_id['270WC0012345'].get('difference')),
      ('', ''))
check('LOB e Product da familia', (by_id['XPTO12345'].get('lob'), by_id['XPTO12345'].get('product')),
      ('EQUITIES', 'EQUITY'))
check('o Type vem do CALLPUT do Latam', by_id['270WC0012345'].get('type'), 'CALL')
check('o nome sai do Reference Data pelo SPN, nao do texto do arquivo',
      by_id['270WI0012345'].get('counterparty'), 'ATACAMA FUNDO DE INVESTIMENTO')
check('   sem cadastro, o texto do arquivo fica (a linha nao sai anonima)',
      by_id['270WC0012345'].get('counterparty'), 'SAFRA TEXTO LIVRE DO ARQUIVO')

print('\n== 3. quem gera aviso ==')
check('a entidade do le-spn e perna interna', internos[0], True)
check('   e o nome que comeca em BANCO tambem', internos[1], True)
check('   um cliente de verdade nao', internos[2], False)
check('a perna interna FICA no Trade Level',
      sorted(r['counterparty'] for r in rows if r.get('_no_advice')),
      ['ATACAMA FUNDO DE INVESTIMENTO', 'BANCO XYZ S.A.'])
check('   e sai do Settlement Summary, que e a fonte do aviso',
      sorted(r['counterparty'] for r in resumo),
      ['CLIENTE DE OUTRO SISTEMA', 'CLIENTE SEM DEAL REF', 'SAFRA TEXTO LIVRE DO ARQUIVO'])
check('o net e por positivos x negativos',
      [(r['counterparty'], r['receive'], r['pay'], r['direction'])
       for r in resumo if r['counterparty'] == 'SAFRA TEXTO LIVRE DO ARQUIVO'],
      [('SAFRA TEXTO LIVRE DO ARQUIVO', '130,000.00', '', 'RECEIVE')])

print('\n== 4. a familia entra na lista unica ==')
# `_ops_trade_rows` e o UNICO lugar que sabe quais familias existem -- a tela, os
# cards e o e-mail de TED chamam todos ele.
check('as linhas de equity aparecem em _ops_trade_rows',
      len([r for r in todas if r.get('product') == 'EQUITY']), 5)
SRC = io.open('apps/pages/routes.py', encoding='utf-8').read()
blk = SRC.split('def _ops_trade_rows', 1)[1].split('\ndef ', 1)[0]
check('   e a familia esta registrada la, nao chamada por fora',
      '_ops_equity_trade_rows' in blk, True)
# EQUITY fica fora do card de Option de proposito: sem lado B3, a familia
# entraria com contagem interna e B3 zerado -- um ambar permanente que nao e
# divergencia. `_ops_recon` ignora o produto que nao conhece.
recon = R._ops_recon(rows)
check('o card de Option continua n/a (nao ha lado B3 de equity)',
      (recon['option']['na'], recon['option']['int_count']), (True, 0))

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
