"""O botao Edit da linha SEMPRE abre um modal (regra da mesa, 28/09/2026).

As tres telas de recompra (catalogo, NDF FX e Intrag Unwind) editavam NA
PROPRIA LINHA: o Edit trocava as celulas por `<input>` e punha Save/Cancel na
coluna Actions. A mesa quer o modal em toda tela, e o que se prende aqui e:

1. toda pagina com `btn-row-edit` tem um modal de edicao (`modal-content` no
   template ou o `arOpenEditModal` das paginas de New Deals);
2. nenhuma pagina desenha o par Save/Cancel da edicao inline
   (`btn-row-save` + `btn-row-cancel` como classe da linha).
"""
import io
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
PAGES = os.path.join(ROOT, 'apps', 'templates', 'pages')

fails = []


def check(label, cond, detail=''):
    print(('  ok  ' if cond else ' FAIL ') + label + ('' if cond else '\n        ' + str(detail)))
    if not cond:
        fails.append(label)


sem_modal, inline = [], []
for nome in sorted(os.listdir(PAGES)):
    if not nome.endswith('.html'):
        continue
    txt = io.open(os.path.join(PAGES, nome), encoding='utf-8').read()
    if 'btn-row-edit' not in txt:
        continue
    if 'modal-content' not in txt and 'arOpenEditModal' not in txt:
        sem_modal.append(nome)
    if re.search(r'btn-row-save["\s]', txt) and re.search(r'btn-row-cancel["\s]', txt):
        inline.append(nome)

check('toda pagina com Edit tem modal de edicao', not sem_modal, sem_modal)
check('nenhuma pagina edita na propria linha (Save/Cancel inline)', not inline, inline)
for nome in ('unwinds-product.html', 'unwinds-ndf-fx.html', 'intrag-unwind.html'):
    txt = io.open(os.path.join(PAGES, nome), encoding='utf-8').read()
    check('%s: o Edit abre o modal' % nome,
          'Modal.getOrCreateInstance' in txt and 'liquid-glass' in txt)

print('\n%s' % ('TUDO OK' if not fails else '%d FALHA(S): %s' % (len(fails), fails)))
sys.exit(1 if fails else 0)
