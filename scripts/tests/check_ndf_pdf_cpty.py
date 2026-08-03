"""Settlement PDF (NDF Advice): quem leva a Ficha de Liquidacao em PDF anexa.

A lista era a tupla _NDF_PDF_COUNTERPARTIES em otc_emails.py (herdada da macro
CommodiXchange) e virou o cadastro `ndf-pdf-cpty` da tela /mapping. O que este
script protege:

  1. O SEED do mapping e a tupla de fallback continuam identicos. Se alguem
     editar um dos dois e esquecer o outro, uma instancia sem o arquivo passa a
     anexar PDF para um conjunto diferente do que a tela mostra.
  2. Cadastro VAZIO significa "ninguem leva PDF" e e respeitado — nao pode cair
     de volta na lista historica, senao nao ha como desligar o anexo pela tela.
  3. Arquivo AUSENTE (instancia que nunca abriu a tela) cai na lista historica,
     que e o comportamento de antes do cadastro existir.
  4. O match e por nome normalizado: acento, caixa, espaco duplo e travessao nao
     podem separar o que e a mesma contraparte.

Usa um diretorio em tmp; nao encosta no cadastro real.
"""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from apps.pages import otc_emails as E                     # noqa: E402
from apps.pages import routes as R                         # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


TMP = tempfile.mkdtemp()
E._DATA_DIR = TMP                       # o loader resolve o mapping a partir daqui
MAPDIR = os.path.join(TMP, 'mappings')
os.makedirs(MAPDIR)
PATH = os.path.join(MAPDIR, 'ndf-pdf-cpty.json')


def write(rows):
    with open(PATH, 'w', encoding='utf-8') as fh:
        json.dump(rows, fh)


print('\n== 1. seed do mapping == tupla de fallback ==')
seed = [r['COUNTERPARTY'] for r in R._MAPPING_DEFS['ndf-pdf-cpty']['seed']]
check('mesma quantidade', len(seed), len(E._NDF_PDF_COUNTERPARTIES))
check('mesmos nomes, mesma ordem', seed, list(E._NDF_PDF_COUNTERPARTIES))

print('\n== 2. o cadastro manda ==')
write([{'COUNTERPARTY': 'CLIENTE NOVO SA', 'NOTES': 'pediu em 2026'}])
got = E._ndf_pdf_set()
check('contraparte cadastrada entra', E._ndf_pdf_norm('CLIENTE NOVO SA') in got, True)
check('quem saiu do cadastro nao leva mais',
      E._ndf_pdf_norm('HITACHI ENERGY BRASIL LTDA') in got, False)
check('so o que esta cadastrado', len(got), 1)

write([{'COUNTERPARTY': 'A LTDA'}, {'COUNTERPARTY': '  '},
       {'COUNTERPARTY': None}, {'NOTES': 'linha sem a coluna'}, 'linha que nao e dict'])
check('linha em branco/torta e ignorada sem quebrar',
      E._ndf_pdf_set(), {E._ndf_pdf_norm('A LTDA')})

print('\n== 3. cadastro vazio = ninguem leva PDF ==')
write([])
check('lista vazia e respeitada', E._ndf_pdf_set(), set())

print('\n== 4. arquivo ausente/ilegivel cai na lista historica ==')
historica = {E._ndf_pdf_norm(n) for n in E._NDF_PDF_COUNTERPARTIES}
os.remove(PATH)
check('sem arquivo -> lista historica', E._ndf_pdf_set(), historica)
with open(PATH, 'w', encoding='utf-8') as fh:
    fh.write('{isto nao e json')
check('json quebrado -> lista historica', E._ndf_pdf_set(), historica)

print('\n== 5. match por nome normalizado ==')
write([{'COUNTERPARTY': 'ABB ELETRIFICACAO LTDA - FILIAL 0003'}])
got = E._ndf_pdf_set()
for variante in ('ABB ELETRIFICACAO LTDA - FILIAL 0003',
                 'abb eletrificacao ltda - filial 0003',
                 'ABB  ELETRIFICACAO   LTDA - FILIAL 0003',
                 '  ABB ELETRIFICACAO LTDA - FILIAL 0003  ',
                 'ABB ELETRIFICAÇÃO LTDA - FILIAL 0003',
                 'ABB ELETRIFICACAO LTDA – FILIAL 0003'):
    check('casa %r' % variante, E._ndf_pdf_norm(variante) in got, True)
check('outra filial NAO casa',
      E._ndf_pdf_norm('ABB ELETRIFICACAO LTDA - FILIAL 0004') in got, False)
check('nome parcial NAO casa',
      E._ndf_pdf_norm('ABB ELETRIFICACAO LTDA') in got, False)

print('\n== 6. o seed reproduz o comportamento antigo ==')
write(R._MAPPING_DEFS['ndf-pdf-cpty']['seed'])
check('seed na tela == lista historica', E._ndf_pdf_set(), historica)
for nome in E._NDF_PDF_COUNTERPARTIES:
    check('leva PDF: %s' % nome, E._ndf_pdf_norm(nome) in E._ndf_pdf_set(), True)
check('quem nao esta na lista nao leva',
      E._ndf_pdf_norm('EMPRESA QUALQUER LTDA') in E._ndf_pdf_set(), False)

shutil.rmtree(TMP, ignore_errors=True)
print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
