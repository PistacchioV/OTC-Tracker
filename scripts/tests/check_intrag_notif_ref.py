"""
check_intrag_notif_ref.py -- a notificacao das telas de Intrag diz o B3 ID (§558).

O `deal_id` que as rotas recebem e a CHAVE interna da linha; nas paginas que
nascem do New Deals (NDF, Option, Swap) ele e o Athena ID, e o sino dizia
"Intrag NDF — DBH-1P7CZ9 → Approved" numa tela cuja referencia e o B3 ID.

  1. `_notif_ref` devolve o B3 ID da linha e, sem ele, a chave;
  2. nenhuma notificacao de linha das telas de Intrag passa o `deal_id` cru.
"""
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from apps.pages.features.intrag import entrypoint as E    # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label +
          ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


print('== 1. _notif_ref ==')
check('B3 ID da linha', E._notif_ref([{'b3_id': ' 26E04610365 ', '_deal': 'DBH-1P7CZ9'}], 0, 'DBH-1P7CZ9'), '26E04610365')
check('sem B3 ID cai na chave', E._notif_ref([{'b3_id': ''}], 0, 'DBH-1P7CZ9'), 'DBH-1P7CZ9')
check('linha sem o campo', E._notif_ref([{}], 0, 'X1'), 'X1')
check('sem linha', E._notif_ref(None, None, 'X1'), 'X1')

print('\n== 2. nenhuma notificacao de linha com o deal_id cru ==')
src = open(os.path.join(ROOT, 'apps/pages/features/intrag/entrypoint.py'), encoding='utf-8').read()
crus = re.findall(r"'(?:Deal|Status) Updated', 'Intrag [A-Za-z ]+', deal_id", src)
check('deal_id cru no sino', crus, [])
check('as 14 passam pelo _notif_ref', len(re.findall(r"', _notif_ref\(entries, idx, deal_id\)", src)), 14)

print('\n%s' % ('FAIL: %d' % len(fails) if fails else 'OK'))
sys.exit(1 if fails else 0)
