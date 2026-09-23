"""Confirmations Monitor: o card só mostra o PDF do SEU ativo.

A pasta do dia de uma contraparte guarda um PDF por confirmação
(`<acrônimo> - <mercadoria> - CONFIRMAÇÃO…`). O filtro do card
(`_mc_confirmation_docs`) procura o Trade ID e depois o Ativo no nome, e quando
nada casava devolvia a PASTA INTEIRA: o card de AÇÚCAR da Mondelez, com a
confirmação de SOJA já gerada no mesmo dia, mostrava o PDF de soja e trocava o
Generate por Validate — a de açúcar não se gerava mais.

Agora o PDF cujo nome diz OUTRA mercadoria sai do card. O que continua:
  * PDF do próprio ativo, ou com o Trade ID, aparece;
  * PDF sem o padrão do app (upload à mão) não diz o ativo e aparece;
  * linha LEGADA com a MOEDA na coluna Ativo (`USD`) segue com a queda para a
    pasta inteira — ali o Ativo não identifica nada;
  * os e-mails de recap seguem a regra de sempre.

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

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


PASTA = {'pdfs': [], 'mails': []}
saved = (MCONF.confirmation_folders, R._ei_client_dir_names, MC._mc_folder_pdfs,
         MC._mc_folder_emails, MC._mc_email_subject, R._moeda_num_code)
MCONF.confirmation_folders = lambda row: ('MONDELEZ', ['Confirmations/2026/09. September/22/NDF COMM'])
R._ei_client_dir_names = lambda c: ['MONDELEZ']
MC._mc_folder_pdfs = lambda folder: list(PASTA['pdfs'])
MC._mc_folder_emails = lambda folder: list(PASTA['mails'])
MC._mc_email_subject = lambda full: ''
R._moeda_num_code = lambda s: {'USD': '220', 'BRL': '790'}.get(str(s or '').upper(), '')


def nomes(row, trades=None):
    return [d['name'] for d in MC._mc_confirmation_docs(row, trades) if not d.get('email')]


SOJA = 'MONDNNBR - SOJA - CONFIRMAÇÃO DE OPERAÇÕES DE DERIVATIVOS nº DBH-SOJA1.pdf'
ACUCAR = 'MONDNNBR - AÇÚCAR - CONFIRMAÇÃO DE OPERAÇÕES DE DERIVATIVOS nº DBH-ACU1.pdf'
MANUAL = 'Mondelez assinado.pdf'
try:
    print('== 1. o caso da mesa: card de ACUCAR com so a confirmacao de SOJA na pasta ==')
    PASTA['pdfs'] = [SOJA]
    PASTA['mails'] = ['INTERNAL FW_ Trade Recap Sugar.msg']
    row = {'Moeda': 'ACUCAR', 'Cliente': 'MONDELEZ'}
    check('o PDF de soja NAO aparece no card de acucar', nomes(row, ['DBH-ACU1']), [])
    check('   (sem PDF, a tela volta a oferecer o Generate)',
          any(not d.get('email') for d in MC._mc_confirmation_docs(row, ['DBH-ACU1'])), False)
    check('   e o e-mail de recap continua', [d['name'] for d in MC._mc_confirmation_docs(row, ['DBH-ACU1'])
                                              if d.get('email')], ['INTERNAL FW_ Trade Recap Sugar'])

    print('\n== 2. cada card com o seu PDF ==')
    PASTA['pdfs'] = [SOJA, ACUCAR]
    check('card de acucar -> o de acucar (acento nao importa)', nomes(row, ['DBH-ACU1']),
          ['MONDNNBR - AÇÚCAR - CONFIRMAÇÃO DE OPERAÇÕES DE DERIVATIVOS nº DBH-ACU1'])
    check('card de soja -> o de soja', nomes({'Moeda': 'SOJA'}, ['DBH-SOJA1']),
          ['MONDNNBR - SOJA - CONFIRMAÇÃO DE OPERAÇÕES DE DERIVATIVOS nº DBH-SOJA1'])
    check('pelo Ativo, sem Trade ID no nome', nomes({'Moeda': 'ACUCAR'}, ['OUTRO']),
          ['MONDNNBR - AÇÚCAR - CONFIRMAÇÃO DE OPERAÇÕES DE DERIVATIVOS nº DBH-ACU1'])

    print('\n== 3. o que continua como era ==')
    PASTA['pdfs'] = [SOJA, MANUAL]
    check('PDF sem o padrao do app (upload a mao) continua aparecendo',
          nomes(row, ['DBH-ACU1']), ['Mondelez assinado'])
    PASTA['pdfs'] = [SOJA]
    check('linha legada com MOEDA no Ativo: a queda para a pasta inteira segue',
          nomes({'Moeda': 'USD'}, ['NADA']),
          ['MONDNNBR - SOJA - CONFIRMAÇÃO DE OPERAÇÕES DE DERIVATIVOS nº DBH-SOJA1'])
    check('linha sem Ativo tambem', nomes({'Moeda': ''}, ['NADA']),
          ['MONDNNBR - SOJA - CONFIRMAÇÃO DE OPERAÇÕES DE DERIVATIVOS nº DBH-SOJA1'])
finally:
    (MCONF.confirmation_folders, R._ei_client_dir_names, MC._mc_folder_pdfs,
     MC._mc_folder_emails, MC._mc_email_subject, R._moeda_num_code) = saved

print('\n%s' % ('FAIL: %d' % len(fails) if fails else 'all ok'))
sys.exit(1 if fails else 0)
