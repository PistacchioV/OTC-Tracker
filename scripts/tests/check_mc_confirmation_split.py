"""Confirmations Monitor × Track: um documento, um card — e o card abre o SEU PDF.

Dois relatos da mesa (25/09/2026), a mesma raiz — o card do Monitor agrupava
por CAMPOS que podiam divergir da segregação que montou o documento:

  * commodities: 6 operações num PDF, e o Validate atualizou 5 no Track — um
    deal chegou sem `Commodities` e o documento o juntava pelo Subjacente,
    enquanto a esteira gravava na Moeda o Underlying Asset: 5 + 1 cards, e a
    confirmação ficou em dois estágios;
  * #OTC-0043: USD e EUR do mesmo cliente num card só (linha antiga com Moeda
    `BRL`); gerada a de EUR, o card mostrava — e validava — o PDF de EUR para as
    duas, porque na ordem alfabética ele vem primeiro.

Prova:
  1. o ativo das commodities é UMA função (`_conf_merc_default`) para o
     documento e para a Moeda da esteira;
  2. confirmação gerada agrupa pelo `Confirmation Link` (o documento), não pelos
     campos; sem link, pelos campos de sempre;
  3. com vários PDFs casando, vale o do link — no card e na janela de validação.

Sem share: a listagem da pasta é stub.
"""
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', os.path.join(ROOT, '.check-share'))
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')

from apps.pages import routes as R                                  # noqa: E402
from apps.pages import manual_conf as MCONF                         # noqa: E402
from apps.pages.platform import manual_confirmation as MC           # noqa: E402
from apps.pages.platform import confirmations as PC                 # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


print('== 1. o ativo das commodities: a mesma regra no documento e na esteira ==')
_subj = PC._conf_subjacente_map
PC._conf_subjacente_map = lambda: {'CO1-2': {'mercadoria': 'OLEO'}}
try:
    sem_comm = {'UnderlyingAsset': 'CO1-2', 'Commodities': ''}
    com_comm = {'UnderlyingAsset': 'CO1-2', 'Commodities': 'OLEO'}
    check('deal sem Commodities: o Subjacente responde', PC._conf_merc_default(sem_comm), 'OLEO')
    check('deal com Commodities: ele vence', PC._conf_merc_default(com_comm), 'OLEO')

    def first_de(d):
        return lambda *ns: next((str(d.get(n) or '').strip() for n in ns if str(d.get(n) or '').strip()), '')
    check('a Moeda da esteira e a MESMA do documento (NDF COMM)',
          MC._mc_moeda_do_ativo(sem_comm, 'NDF COMM', first_de(sem_comm)), 'OLEO')
    check('   e na OPTION COMM',
          MC._mc_moeda_do_ativo(sem_comm, 'OPTION COMM', first_de(sem_comm)), 'OLEO')
    grupos, _st, _tot = PC._conf_segregate(
        [dict(sem_comm, Client='ACME', Acronym='ACME', Status='Success'),
         dict(com_comm, Client='ACME', Acronym='ACME', Status='Success')],
        lambda d, s: 'f')
    check('   e o documento junta as duas num grupo so', len(grupos), 1)
finally:
    PC._conf_subjacente_map = _subj

print('\n== 2. confirmacao gerada agrupa pelo DOCUMENTO ==')
LINK_USD = '/api/electronic-inventory/file?client=ACME&rel=Confirmations/2026/09.%20September/25/NDF%20VANILLA/ACME%20-%20USD%20-%20CONFIRMA%C3%87%C3%83O%20-%2020260925.pdf'
LINK_EUR = LINK_USD.replace('USD', 'EUR')
base = {'LOB': 'CEM', 'Cliente': 'ACME', 'Produto': 'NDF VANILLA', 'Data Operação': '25/09/2026'}
check('6 operacoes do mesmo PDF, uma com Moeda divergente: UMA chave',
      MCONF.group_key(dict(base, Moeda='OLEO', **{'Confirmation Link': LINK_USD})),
      MCONF.group_key(dict(base, Moeda='CO1-2', **{'Confirmation Link': LINK_USD})))
check('USD e EUR com Moeda antiga BRL, cada um com o seu PDF: DUAS chaves',
      MCONF.group_key(dict(base, Moeda='BRL', **{'Confirmation Link': LINK_USD})) !=
      MCONF.group_key(dict(base, Moeda='BRL', **{'Confirmation Link': LINK_EUR})), True)
check('sem link (ainda nao gerada): os campos de sempre',
      MCONF.group_key(dict(base, Moeda='USD')), MCONF.group_key(dict(base, Moeda='usd')))
check('o item do Monitor leva o link para a busca do PDF',
      'Confirmation Link' in MCONF.MONITOR_FIELDS, True)

print('\n== 3. varios PDFs casando: vale o do link ==')
PDF_USD = 'ACME - USD - CONFIRMAÇÃO - 20260925.pdf'
PDF_EUR = 'ACME - EUR - CONFIRMAÇÃO - 20260925.pdf'
saved = (MCONF.confirmation_folders, R._ei_client_dir_names, MC._mc_folder_pdfs,
         MC._mc_folder_emails, MC._mc_email_subject)
MCONF.confirmation_folders = lambda row: ('ACME', ['Confirmations/2026/09. September/25/NDF VANILLA'])
R._ei_client_dir_names = lambda c: ['ACME']
MC._mc_folder_pdfs = lambda folder: sorted([PDF_USD, PDF_EUR])      # EUR vem primeiro
MC._mc_folder_emails = lambda folder: []
MC._mc_email_subject = lambda full: ''
try:
    row = dict(base, Moeda='BRL')                   # linha antiga: a Moeda nao filtra nada
    sem = [d['name'] for d in MC._mc_confirmation_docs(row, ['T1'])]
    check('sem link: a pasta inteira (o EUR primeiro — era o defeito)', sem[0], PDF_EUR[:-4])
    com = [d['name'] for d in MC._mc_confirmation_docs(row, ['T1'], LINK_USD)]
    check('com o link do USD: so o PDF do USD', com, [PDF_USD[:-4]])
    check('o nome sai do rel do link', MC._mc_link_pdf_name(LINK_EUR), PDF_EUR[:-4].upper())
    check('link que nao aponta PDF nao filtra', MC._mc_link_pdf_name('/x?rel=a/b.doc'), '')
finally:
    (MCONF.confirmation_folders, R._ei_client_dir_names, MC._mc_folder_pdfs,
     MC._mc_folder_emails, MC._mc_email_subject) = saved

print('\n== 4. a tela passa o link ==')
HTML = open('apps/templates/pages/manual-confirmation-monitor.html', encoding='utf-8').read()
check('o card guarda o link', 'data-docs-link=' in HTML, True)
check('   e o lote o envia', "link: el.attr('data-docs-link')" in HTML, True)
EP = open('apps/pages/features/manual_confirmation/entrypoint.py', encoding='utf-8').read()
check('a janela de validacao usa o link das linhas', "docs = _R()._mc_confirmation_docs(row, _keys, _link)" in EP, True)

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS: %d' % len(fails)))
sys.exit(1 if fails else 0)
