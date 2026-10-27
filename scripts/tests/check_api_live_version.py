"""Pull da Athena: a versão MORTA de um trade corrigido não desfaz a correção.

Operação rebookada na Athena (acronym/SPN errado → certo) volta no getTrades
com o mesmo DEAL NAME duas vezes: a versão antiga com `isDead = true` e a
nova. Desde o §173 o `isDead` é importado, e as duas faziam Amend na MESMA
linha — vindo a antiga por último, a tela ficava com a contraparte errada,
mesmo com a API certa (equipe, 27/10/2026). `_api_live_records` fica só com a
versão viva quando ela existe.

  1. o filtro: morta e cancelada saem quando há viva; só morta fica (o §173);
     só cancelada fica (cancela); deals diferentes não se misturam; ordem;
  2. FXO de ponta a ponta: a linha gravada com o acronym errado, a API com
     [nova viva, antiga morta] nas DUAS ordens → a linha termina com o acronym,
     o SPN e o cliente novos;
  3. o defeito, sem o filtro: com a antiga por último, a linha volta ao errado
     (prova de que o teste pega o que o filtro conserta).

    OTC_SHARED_DRIVE_ROOT=/tmp/otc-share python scripts/tests/check_api_live_version.py
"""
import os
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', tempfile.mkdtemp(prefix='share-root-'))
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

from apps import create_app                                      # noqa: E402
from apps.config import DebugConfig                              # noqa: E402

app = create_app(DebugConfig)
from apps.pages import routes as R                               # noqa: E402
from apps.pages.platform import new_deals as ND                  # noqa: E402

fails = []


def check(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg)
    if not cond:
        fails.append(msg)


def rec(deal, acr, spn, dead=False, cancelled=False):
    # As chaves como a Athena as manda: o import normaliza para MAIÚSCULAS com
    # espaço (`Deal Name` → `DEAL NAME`), e os flags vêm em camelCase.
    return {'Deal Name': deal, 'End Counterparty': acr, 'End Counterparty Description': acr + ' DESC',
            'SPN': spn, 'isDead': dead, 'isCancelled': cancelled, 'Trade Date': '27/10/2026',
            'Settlement Date': '27/11/2026', 'Expiration Date': '25/11/2026', 'Type': 'BUY',
            'Option Type': 'CALL', 'Strike': 5.4, 'Quantity': 1000000, 'Premium Quantity': 10000,
            'Quantity Currency': 'USD'}


print('== 1. o filtro ==')
r = ND._api_live_records([rec('D1', 'NOVO', '2', dead=False), rec('D1', 'VELHO', '1', dead=True),
                          rec('D1', 'VELHO', '1', cancelled=True)])
check([x['End Counterparty'] for x in r] == ['NOVO'], 'com versão viva, a morta e a cancelada saem')
r = ND._api_live_records([rec('D2', 'A', '1', dead=True)])
check(len(r) == 1, 'só versão morta continua sendo puxada (o §173)')
r = ND._api_live_records([rec('D3', 'A', '1', cancelled=True)])
check(len(r) == 1, 'só cancelada continua (é ela que cancela a linha)')
r = ND._api_live_records([rec('D4', 'A', '1'), rec('D5', 'B', '2', dead=True), rec('D4', 'C', '3')])
check([x['End Counterparty'] for x in r] == ['A', 'B', 'C'],
      'deals diferentes não se misturam, duas vivas do mesmo deal ficam, a ordem é a da API')
check(ND._api_live_records([{'DEAL_NAME': 'D_6', 'isDead': 'true'}, {'Deal Name': 'D-6'}]) == [{'Deal Name': 'D-6'}],
      'o DEAL NAME compara como o import o grava (`_` vira `-`), isDead em texto')

print('\n== 2. FXO de ponta a ponta ==')
REF = {
    '1': {'SPN': '1', 'COUNTERPARTY': 'CLIENTE ERRADO SA', 'TAX ID': '11.111.111/0001-11',
          'FX CASH ACCRONYM': 'VELHO'},
    '2': {'SPN': '2', 'COUNTERPARTY': 'CLIENTE CERTO SA', 'TAX ID': '22.222.222/0001-22',
          'FX CASH ACCRONYM': 'NOVO'},
}
_ref = R._fxo_refdata_by_spn
R._fxo_refdata_by_spn = lambda: dict(REF)


def simula(registros, filtro=True):
    """O que o _fxo_persist_new_deals faz com um dia que já tem a linha errada."""
    gravada = {'Deal': 'FX1', 'Client': 'CLIENTE ERRADO SA', 'Acronym': 'VELHO', 'SPN': '1',
               'TaxID': '11.111.111/0001-11', 'Status': 'Sent', 'B3_ID': ''}
    existing = [gravada]
    idx, by_deal = ND._nd_amend_index(existing)
    st = {'existing': existing, 'idx': idx, 'by_deal': by_deal}
    if filtro:
        deals, _canc = ND._fxo_deals_from_api_records(registros, 'API')
    else:
        orig = ND._api_live_records
        ND._api_live_records = lambda rs: list(rs or [])
        try:
            deals, _canc = ND._fxo_deals_from_api_records(registros, 'API')
        finally:
            ND._api_live_records = orig
    for d in deals:
        row = ND._nd_amend_find(st, d)
        if row is not None:
            ND._nd_api_amend_full(row, d, 'fxo')
        else:
            existing.append(d)
    return existing


try:
    with app.app_context():
        for nome, ordem in (('nova primeiro', [rec('FX1', 'NOVO', '2'), rec('FX1', 'VELHO', '1', dead=True)]),
                            ('antiga primeiro', [rec('FX1', 'VELHO', '1', dead=True), rec('FX1', 'NOVO', '2')])):
            linhas = simula(ordem)
            l0 = linhas[0]
            check(len(linhas) == 1 and l0['Acronym'] == 'NOVO' and l0['SPN'] == '2'
                  and l0['Client'] == 'CLIENTE CERTO SA' and l0['TaxID'] == '22.222.222/0001-22',
                  '%s: a linha fica com o acronym, o SPN, o cliente e o Tax ID novos (%s, %s, %s)'
                  % (nome, l0.get('Acronym'), l0.get('SPN'), l0.get('Client')))
            check(l0['Status'] == 'Amend' and 'Acronym' in (l0.get('AmendChanged') or []),
                  '%s: troca de contraparte numa linha Sent é Amend, com a célula destacada' % nome)

        print('\n== 3. o defeito, sem o filtro ==')
        linhas = simula([rec('FX1', 'NOVO', '2'), rec('FX1', 'VELHO', '1', dead=True)], filtro=False)
        check(linhas[0]['Acronym'] == 'VELHO' and linhas[0]['Client'] == 'CLIENTE ERRADO SA',
              'sem o filtro, a versão morta por último devolve a contraparte errada (%s)'
              % linhas[0].get('Acronym'))
finally:
    R._fxo_refdata_by_spn = _ref

print('\n== 3b. duas versões VIVAS do mesmo trade: fica a mais recente ==')
# O caso real (D5WM-PLNXR): a Athena devolveu a versão antiga SEM `isDead`,
# mesmo `Orig Entry Time`, `Entry Time` anterior. As duas vivas, a última da
# lista vencia, e a correção manual do SPN voltava ao errado no pull seguinte.
ORIG = 'Tue Oct 27 14:05:17 2026'


def versao(acr, spn, entry, orig=ORIG):
    r = rec('FX9', acr, spn)
    r['Orig Entry Time'], r['Entry Time'] = orig, entry
    return r


NOVA = versao('NOVO', '2', 'Tue Oct 27 18:23:21 2026')
VELHA = versao('VELHO', '1', ORIG)
for nome_o, ordem in (('nova primeiro', [NOVA, VELHA]), ('velha primeiro', [VELHA, NOVA])):
    r = ND._api_live_records(ordem)
    check([x['End Counterparty'] for x in r] == ['NOVO'], '%s: fica só a versão de 18:23' % nome_o)
pernas = [versao('PERNA-A', '1', ORIG), versao('PERNA-B', '2', ORIG)]
check(len(ND._api_live_records(pernas)) == 2, 'pernas com o MESMO Entry Time ficam as duas')
outro = [versao('A', '1', 'Tue Oct 27 18:23:21 2026', orig='Tue Oct 27 09:00:00 2026'), VELHA]
check(len(ND._api_live_records(outro)) == 2, 'Orig Entry Time diferente: não são versões, ficam as duas')
sem = [dict(NOVA, **{'Entry Time': ''}), VELHA]
check(len(ND._api_live_records(sem)) == 2, 'Entry Time ilegível: não decide, ficam as duas')
with app.app_context():
    R._fxo_refdata_by_spn = lambda: dict(REF)
    try:
        linhas = simula([dict(NOVA, **{'Deal Name': 'FX1'}), dict(VELHA, **{'Deal Name': 'FX1'})])
    finally:
        R._fxo_refdata_by_spn = _ref
check(linhas[0]['Acronym'] == 'NOVO' and linhas[0]['Client'] == 'CLIENTE CERTO SA',
      'de ponta a ponta: a versão antiga viva por último não desfaz mais a correção (%s)'
      % linhas[0].get('Acronym'))

print('\n== 4. a tela relê a grade quando o pull corrigiu uma linha ==')
# O caso real (D5WM-PLNXR, Suzano, 27/10/2026): o servidor gravava o Amend
# certo, e a tela — que só redesenha as linhas NOVAS do `deals` — dizia "No new
# deals" e seguia com a contraparte antiga até alguém pesquisar de novo.
for pg in ('opt-fxo', 'ndf-vanilla', 'ndf-fwdstart', 'ndf-otherpublisher'):
    txt = open(os.path.join(ROOT, 'apps', 'templates', 'pages', 'new_deals-%s.html' % pg), encoding='utf-8').read()
    check('function apiAmended(res)' in txt and 'if (apiMudou && apiRefIsToday()) sfApply();' in txt
          and "t('swal-api-amended'" in txt,
          '%s: Amend/remoção no pull relê a grade e entra no resumo' % pg)

print(('\nFAIL: %d' % len(fails)) if fails else '\nTUDO OK')
sys.exit(1 if fails else 0)
