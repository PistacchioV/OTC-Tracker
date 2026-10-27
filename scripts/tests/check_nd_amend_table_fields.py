"""New Deals: o Amend da API só conta o que a TABELA mostra (equipe, 27/10/2026).

O deal da Athena traz mais campos do que as telas exibem, e a API os reescreve a
cada pull. Comparados como qualquer outro, eles jogavam a linha para `Amend` sem
célula nenhuma destacada. A regra: campo fora das colunas da tela é atualizado
calado; só coluna da tabela faz Amend e entra no `AmendChanged`.

  1. paridade: `_ND_TABLE_FIELDS` de cada produto = o `COL_TO_JSON_FIELD` do
     template (sem os campos do fluxo da página: Status, B3_ID, Maker, id);
  2. campo fora da tabela muda: valor novo gravado, sem Amend e sem AmendChanged;
  3. coluna da tabela muda: Amend e AmendChanged (e o campo calado junto não
     entra no destaque);
  4. produto sem lista compara tudo (o comportamento de antes);
  5. a célula com amend usa a classe do tema, não um rosa fixo no JS.

    OTC_SHARED_DRIVE_ROOT=/tmp/otc-share python scripts/tests/check_nd_amend_table_fields.py
"""
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', '/tmp/otc-share')
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

from apps.pages.platform import new_deals as ND                  # noqa: E402

fails = []


def check(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg)
    if not cond:
        fails.append(msg)


TEMPLATES = {'vanilla': 'new_deals-ndf-vanilla.html', 'fwd-start': 'new_deals-ndf-fwdstart.html',
             'other-publishers': 'new_deals-ndf-otherpublisher.html', 'fxo': 'new_deals-opt-fxo.html'}
DO_FLUXO = {'Status', 'B3_ID', 'Maker', 'id'}

print('== 1. paridade com os templates ==')
for prod, nome in TEMPLATES.items():
    txt = open(os.path.join(ROOT, 'apps', 'templates', 'pages', nome), encoding='utf-8').read()
    m = re.search(r'var COL_TO_JSON_FIELD\s*=\s*\{(.*?)\};', txt, re.S)
    tela = set(re.findall(r"\d+\s*:\s*'([^']+)'", m.group(1))) - DO_FLUXO
    lista = set(ND._ND_TABLE_FIELDS[prod])
    check(tela == lista, '%s: as colunas da tela = _ND_TABLE_FIELDS (só na tela %s, só na lista %s)'
          % (prod, sorted(tela - lista), sorted(lista - tela)))

print('\n== 2. campo fora da tabela: atualizado calado ==')
row = {'Deal': 'D1', 'Client': 'ACME', 'Status': 'Approved', 'Notional': '100', 'FixingDates': 'a'}
mudou = ND._nd_api_amend(row, {'Deal': 'D1', 'Client': 'ACME', 'Notional': '100', 'FixingDates': 'b'},
                         'vanilla')
check(mudou == [] and row['Status'] == 'Approved' and 'AmendChanged' not in row,
      'sem Amend e sem AmendChanged (%r, %r)' % (mudou, row.get('Status')))
check(row['FixingDates'] == 'b', 'o valor novo foi gravado')
row = {'Deal': 'F1', 'Status': 'Sent', 'Premium': '5', 'ApiInternal': 'x'}
mudou, calados = ND._nd_api_amend_full(row, {'Deal': 'F1', 'Premium': '5', 'ApiInternal': 'y'}, 'fxo')
check(mudou == [] and calados == ['ApiInternal'] and row['Status'] == 'Sent',
      'FXO: o calado volta separado, para o dia ser regravado sem contar como amend')

print('\n== 3. coluna da tabela: Amend ==')
row = {'Deal': 'D2', 'Client': 'ACME', 'Status': 'Approved', 'Notional': '100', 'FixingDates': 'a'}
mudou = ND._nd_api_amend(row, {'Deal': 'D2', 'Client': 'ACME', 'Notional': '200', 'FixingDates': 'b'},
                         'vanilla')
check(mudou == ['Notional'] and row['Status'] == 'Amend' and row['AmendChanged'] == ['Notional'],
      'Notional faz Amend; FixingDates não entra no destaque (%r)' % row.get('AmendChanged'))
row = {'Deal': 'D3', 'Status': 'Approved', 'Strike': '5.1'}
ND._nd_api_amend(row, {'Deal': 'D3', 'Strike': '5.2'}, 'vanilla')
check(row['Status'] == 'Approved', 'Strike não é coluna do Vanilla')
row = {'Deal': 'D4', 'Status': 'Approved', 'Strike': '5.1'}
ND._nd_api_amend(row, {'Deal': 'D4', 'Strike': '5.2'}, 'fwd-start')
check(row['Status'] == 'Amend' and row['AmendChanged'] == ['Strike'], 'e é coluna do FWD Start')

print('\n== 4. produto sem lista compara tudo ==')
row = {'Deal': 'D5', 'Status': 'Approved', 'Qualquer': '1'}
check(ND._nd_api_amend(row, {'Deal': 'D5', 'Qualquer': '2'}) == ['Qualquer'] and row['Status'] == 'Amend',
      'sem produto, o de antes')

print('\n== 5. a cor é do tema ==')
paginas = list(TEMPLATES.values()) + ['new_deals-ndf-commodities.html', 'new_deals-opt-commodities.html']
fontes = [os.path.join(ROOT, 'apps', 'templates', 'pages', n) for n in paginas]
fontes.append(os.path.join(ROOT, 'apps', 'static', 'js', 'pages', 'otc-fileupload.js'))
fixos = [os.path.basename(f) for f in fontes if '#ffe0e0' in open(f, encoding='utf-8').read().lower()]
check(not fixos, 'nenhuma tela pinta o amend com cor fixa (%r)' % fixos)
scss = open(os.path.join(ROOT, 'apps', 'static', 'scss', 'otc.scss'), encoding='utf-8').read()
check(re.search(r'td\.otc-amend-cell\s*\{[^}]*--otc-danger[^}]*color:\s*var\(--otc-text\)', scss) is not None,
      'otc-amend-cell no tema: o tom do --otc-danger e o texto do tema')

print(('\nFAIL: %d' % len(fails)) if fails else '\nTUDO OK')
sys.exit(1 if fails else 0)
