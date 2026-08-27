"""Contraparte de um deal da API: como SPN, Client e Tax ID sao achados.

A ordem importa e ja shipou contraparte errada duas vezes (§147/§148). Hoje ela
e:

  1. accronym do End Counterparty no Reference Data (exato e sem o sufixo de
     entidade);
  2. sendo PERNA INTERNA (o accronym esta no mapping Legal Entity x Accronym), a
     identidade da entidade: razao social cadastrada em le-spn -> Reference Data,
     depois os accronyms da LE, depois o SPN da LE;
  3. nao sendo perna interna, o SPN que veio da API.

As armadilhas que este script protege:

  * a Settlement Location NUNCA pode alimentar o passo da LE — ela e a NOSSA
    perna, e usa-la fazia um cliente virar o proprio Banco J.P. Morgan;
  * o SPN da API nao entra no caminho da perna interna (seria o mesmo erro por
    outro caminho);
  * perna interna MANTEM o accronym da API (o nome do book) em vez do accronym da
    entidade no Reference Data;
  * o upgrade do le-spn nao pode brigar com quem editou a tela: linha ausente ele
    cria, nome apagado ele respeita.

Nao encosta em dado real: mapping e Reference Data sao stubs em memoria.
"""
import io
import os
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


# ── Cadastros de mentira ──────────────────────────────────────────────────────
JPM = {'SPN': '23779', 'COUNTERPARTY': 'BANCO J.P MORGAN S.A',
       'FX CASH ACCRONYM': 'JPMORGANBM', 'TAX ID': '33.172.537/0001-98'}
LAWTON = {'SPN': '37862', 'COUNTERPARTY': 'LAWTON MULTIMERCADO EXCLUSIVO',
          'FX CASH ACCRONYM': 'LAWTON', 'TAX ID': '05.592.116/0001-80'}
ACME = {'SPN': '135742', 'COUNTERPARTY': 'ACME DO BRASIL LTDA',
        'FX CASH ACCRONYM': 'ACMEBRA', 'TAX ID': '45.985.371/0001-08'}

BY_SPN = {R._norm_spn(r['SPN']): r for r in (JPM, LAWTON, ACME)}
BY_ACR = {r['FX CASH ACCRONYM']: r for r in (JPM, LAWTON, ACME)}

MAPS = {
    # 'LM-FWDECOMBRR FXC' e nome de BOOK: nao existe no Reference Data.
    'le-accronym': [
        {'LE': 'JPM', 'ACCRONYM': 'LM-FWDECOMBRR FXC', 'SETTLEMENT LOCATION': 'BRAZIL'},
        {'LE': 'MGT', 'ACCRONYM': 'LM-FXECOMBRR JPMCBB FXC', 'SETTLEMENT LOCATION': 'JPMCBB'},
        {'LE': 'LAWTON', 'ACCRONYM': 'CLIENT FX NDF LAWTON', 'SETTLEMENT LOCATION': 'LAWTON'},
    ],
    'le-spn': [
        {'LE': 'JPM', 'NAME': 'BANCO J.P MORGAN S/A', 'SPN': '', 'NOTES': ''},
        {'LE': 'MGT', 'NAME': 'JPMORGAN CHASE BANK, N.A. - SAO PAULO BRANCH',
         'SPN': '99999', 'NOTES': ''},
        {'LE': 'LAWTON', 'NAME': '', 'SPN': '', 'NOTES': ''},
        {'LE': 'ATACAMA', 'NAME': '', 'SPN': '', 'NOTES': ''},
    ],
}

_orig_rows = R._mapping_rows
R._mapping_rows = lambda key: MAPS.get(key, _orig_rows(key))

try:
    print('\n== 1. de qual Legal Entity o accronym e ==')
    check('book da JPM',        R._ndf_le_from_accronym('LM-FWDECOMBRR FXC'), 'JPM')
    check('caixa/espaco/hifen', R._ndf_le_from_accronym('lm fwdecombrr fxc'), 'JPM')
    check('book da MGT',        R._ndf_le_from_accronym('LM-FXECOMBRR JPMCBB FXC'), 'MGT')
    check('cliente comum',      R._ndf_le_from_accronym('ACMEBRA'), None)

    print('\n== 2. perna interna: razao social -> Reference Data ==')
    # A grafia do cadastro ('S/A') e a do Reference Data ('S.A') sao a mesma coisa
    # depois de normalizadas — e e o unico caminho que resolve um nome de book.
    check('JPM pela razao social',
          R._ndf_le_refdata('JPM', BY_ACR, BY_SPN), JPM)
    # LAWTON nao tem NAME cadastrado: cai no accronym da propria LE.
    check('LAWTON pelo accronym da LE',
          R._ndf_le_refdata('LAWTON', BY_ACR, BY_SPN), LAWTON)
    # MGT nao esta no Reference Data: sobra o SPN cadastrado, sozinho.
    check('MGT so com o SPN cadastrado',
          R._ndf_le_refdata('MGT', BY_ACR, BY_SPN), {'SPN': '99999'})
    # ATACAMA nao tem nada: nada mesmo.
    check('ATACAMA sem cadastro -> {}',
          R._ndf_le_refdata('ATACAMA', BY_ACR, BY_SPN), {})

    print('\n== 3. a ordem completa da busca ==')
    check('accronym exato ganha de tudo',
          R._ndf_ref_by_accronym(BY_ACR, 'ACMEBRA', None, BY_SPN, ''), ACME)
    check('accronym sem o sufixo de entidade',
          R._ndf_ref_by_accronym(BY_ACR, 'ACMEBRA-LAW', None, BY_SPN, ''), ACME)
    check('book interno -> identidade da LE',
          R._ndf_ref_by_accronym(BY_ACR, 'LM-FWDECOMBRR FXC', 'JPM', BY_SPN, ''), JPM)
    check('cliente sem accronym -> SPN da API',
          R._ndf_ref_by_accronym(BY_ACR, 'NAOCADASTRADO', None, BY_SPN, '135742'), ACME)
    check('nada casando -> {}',
          R._ndf_ref_by_accronym(BY_ACR, 'NAOCADASTRADO', None, BY_SPN, '000'), {})

    print('\n== 4. as armadilhas historicas ==')
    # O SPN da API NAO pode resgatar uma perna interna: se a API mandar o SPN da
    # LE (como mandava), a contraparte tem de continuar vindo da identidade dela.
    check('perna interna ignora o SPN da API',
          R._ndf_ref_by_accronym(BY_ACR, 'LM-FXECOMBRR JPMCBB FXC', 'MGT', BY_SPN, '135742'),
          {'SPN': '99999'})
    # E a Settlement Location nunca vira LE aqui: quem passa `le` e o accronym da
    # contraparte. Um cliente nao cadastrado, com location BRAZIL, nao pode virar
    # o Banco J.P. Morgan (§147/§148).
    check('cliente nao cadastrado nao vira JPM',
          R._ndf_ref_by_accronym(BY_ACR, 'SOMICHEL', None, BY_SPN, ''), {})

    print('\n== 5. upgrade do le-spn ==')
    check('arquivo vazio ganha as quatro LEs',
          [r['LE'] for r in R._le_spn_upgrade([])],
          ['JPM', 'MGT', 'LAWTON', 'ATACAMA'])
    check('linha antiga (sem a coluna) ganha o nome',
          R._le_spn_upgrade([{'LE': 'JPM', 'SPN': '1'}])[0].get('NAME'),
          'BANCO J.P MORGAN S.A')
    check('nome apagado pela tela e respeitado',
          R._le_spn_upgrade([{'LE': 'JPM', 'NAME': '', 'SPN': ''}])[0].get('NAME'), '')
    check('nome editado nao e sobrescrito',
          R._le_spn_upgrade([{'LE': 'JPM', 'NAME': 'OUTRO NOME'}])[0].get('NAME'), 'OUTRO NOME')
    up = R._le_spn_upgrade(R._le_spn_upgrade([]))
    check('idempotente (nao duplica linha)', len(up), 4)
    check('o seed nasce sem SPN', [r['SPN'] for r in R._LE_SPN_SEED], ['', '', '', ''])
finally:
    R._mapping_rows = _orig_rows

print('\n== 6. o accronym da API sobrevive na perna interna ==')
src = (io.open('apps/pages/routes.py', encoding='utf-8').read()
       + io.open('apps/pages/platform/new_deals.py', encoding='utf-8').read())
check('builder do NDF',
      "'Acronym':           end_cp if le_cp else ((ref.get('FX CASH ACCRONYM', '') or '') or end_cp)," in src,
      True)
check('builder do FXO', src.count(
      "'Acronym':           end_cp if le_cp else ((ref.get('FX CASH ACCRONYM', '') or '') or end_cp),"), 2)
check('re-enriquecimento',
      "ref_acr = '' if le_map else str(rec.get('FX CASH ACCRONYM', '') or '').strip()" in src, True)

print('\n== 7. a tela: badge e filtro por coluna ==')
js = io.open('apps/static/js/missing-counterparty.js', encoding='utf-8').read()
check('perna interna so escapa do badge com SPN',
      'if (sp && ac && this.leAcrSet && this.leAcrSet[flat(ac)]) return false;' in js, True)
check('o filtro decide pela mesma regra do badge',
      'return self.isMissing(strip(data[c.spn]), strip(data[c.acr]));' in js, True)
PAGES = ['new_deals-ndf-vanilla', 'new_deals-ndf-otherpublisher', 'new_deals-ndf-fwdstart',
         'new_deals-ndf-commodities', 'new_deals-opt-fxo', 'new_deals-opt-commodities']
for name in PAGES:
    page = io.open('apps/templates/pages/%s.html' % name, encoding='utf-8').read()
    check('%s chama o filtro' % name,
          'window._cpInst.columnSearch(columnIndex, this.value)' in page, True)
    check('%s limpa o filtro no Clear' % name,
          'window._cpInst.clearMissingFilter()' in page, True)

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
