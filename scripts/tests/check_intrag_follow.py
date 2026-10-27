# -*- coding: utf-8 -*-
"""A linha da Intrag ACOMPANHA a origem que muda de dia ou de chave (§701).

Toda gravação da Intrag procura a linha só no arquivo-dia de destino. Editar o
Trade Date de um NDF/Opção já mapeado, o de um swap B2B (que muda de
arquivo-dia, §656) ou a Data da Recompra / o Deal ID de uma recompra do
catálogo gravava uma linha NOVA no dia novo e deixava a antiga — a operação
duas vezes na Intrag e no arquivo enviado.

O que se prova:
  1. `_intrag_relocate`: a linha muda de dia levando a esteira (status, maker,
     checker, Intrag ID) e sai do dia antigo; troca de chave no mesmo dia; o
     destino que já tem a chave fica com a dele (sem duplicata); sem a linha
     na origem, nada é gravado;
  2. `_intrag_follow_deal` (New Deals): sem mudança de Trade Date nem de Deal
     não lê nada; com mudança, move;
  3. `swap_new_deals.intrag_follow` (Bullet/Cashflow/Cetes): pela regra do dia
     do swap (Trade Date, a Data Início de plano B) e a chave `_id`;
  4. a gravação seguinte (o re-save do mapeamento) acha a linha no dia novo e
     preserva a esteira;
  5. as origens chamam: os quatro PATCH do New Deals, os três Edit de swap e o
     Edit da recompra do catálogo.
"""
import os
import sys
import tempfile
from datetime import datetime

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', os.path.join(ROOT, '.check-share'))
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

TMP = tempfile.mkdtemp(prefix='intrag-follow-')

from apps import create_app                                      # noqa: E402
from apps.config import DebugConfig                              # noqa: E402

app = create_app(DebugConfig)
from apps.pages import data_store as S                           # noqa: E402
from apps.pages.features.intrag.infra import persistence as P    # noqa: E402
from apps.pages.features.intrag import commands as C             # noqa: E402
from apps.pages.platform import swap_new_deals as SW             # noqa: E402

P.INTRAG_NDF_CACHE_DIR = os.path.join(TMP, 'ndf')
P.INTRAG_OPT_CACHE_DIR = os.path.join(TMP, 'opt')
P.INTRAG_SWAP_CACHE_DIR = os.path.join(TMP, 'swap')
P.INTRAG_UNWIND_CACHE_DIR = os.path.join(TMP, 'unwind')

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def dia(pasta, sufixo, d):
    fp = P._intrag_day_file(pasta, sufixo, d)
    return S.read(fp) if S.exists(fp) else []


A, B = datetime(2026, 10, 20), datetime(2026, 10, 22)
NDF = (P.INTRAG_NDF_CACHE_DIR, '_intrag_ndf.json')

print('== 1. _intrag_relocate ==')
P._intrag_ndf_persist({'_deal': 'D-1', 'campo': 'v1'}, A)
P._intrag_ndf_persist({'_deal': 'D-9', 'campo': 'fica'}, A)
fp = P._intrag_day_file(*NDF, A)
lst = S.read(fp)
lst[0].update(status='Approved', maker='M1', checker='C1', intrag_id='IG-77')
S.write(fp, lst)
check('moveu', P._intrag_relocate(*NDF, A, 'D-1', B, 'D-1'), True)
check('   saiu do dia antigo (e a outra ficou)', [e['_deal'] for e in dia(*NDF, A)], ['D-9'])
novo = dia(*NDF, B)
check('   chegou no dia novo com a esteira',
      [(e['_deal'], e['status'], e['maker'], e['checker'], e['intrag_id']) for e in novo],
      [('D-1', 'Approved', 'M1', 'C1', 'IG-77')])
check('troca de chave no mesmo dia', P._intrag_relocate(*NDF, B, 'D-1', B, 'D-1B'), True)
check('   uma linha só, com a chave nova', [e['_deal'] for e in dia(*NDF, B)], ['D-1B'])
P._intrag_ndf_persist({'_deal': 'D-9', 'campo': 'ja-no-destino'}, B)
check('destino que já tem a chave', P._intrag_relocate(*NDF, A, 'D-9', B, 'D-9'), True)
check('   fica com a dele, sem duplicata',
      [(e['_deal'], e.get('campo')) for e in dia(*NDF, B)],
      [('D-1B', 'v1'), ('D-9', 'ja-no-destino')])
check('   e a origem ficou vazia', dia(*NDF, A), [])
check('sem a linha na origem: False', P._intrag_relocate(*NDF, A, 'NAO-HA', B, 'NAO-HA'), False)
check('mesmo dia e mesma chave: False', P._intrag_relocate(*NDF, B, 'D-9', B, 'D-9'), False)

print('\n== 2. _intrag_follow_deal (New Deals) ==')
_orig = P._intrag_relocate
chamadas = []
P._intrag_relocate = lambda *a: chamadas.append(a) or False
try:
    C._intrag_follow_deal('ndf', {'Deal': 'X', 'TradeDate': '2026-10-20'},
                          {'Deal': 'X', 'TradeDate': '2026-10-20'})
    check('sem mudança: nada é lido', chamadas, [])
finally:
    P._intrag_relocate = _orig
P._intrag_ndf_persist({'_deal': 'N-1', 'campo': 'a'}, A)
check('Trade Date mudou: move',
      C._intrag_follow_deal('ndf', {'Deal': 'N-1', 'TradeDate': '2026-10-20'},
                            {'Deal': 'N-1', 'TradeDate': '2026-10-22'}), True)
check('   e está no dia 22', 'N-1' in [e['_deal'] for e in dia(*NDF, B)], True)
OPT = (P.INTRAG_OPT_CACHE_DIR, '_intrag_opt.json')
os.makedirs(os.path.dirname(P._intrag_day_file(*OPT, A)), exist_ok=True)
S.write(P._intrag_day_file(*OPT, A), [{'_deal': 'O-1', 'my_number': '123', 'status': 'Sent'}])
check('Opção: o Deal mudou → a chave nova',
      C._intrag_follow_deal('opt', {'Deal': 'O-1', 'TradeDate': '2026-10-20'},
                            {'Deal': 'O-2', 'TradeDate': '2026-10-20'}), True)
check('   com o my_number e o status', [(e['_deal'], e['my_number'], e['status'])
                                       for e in dia(*OPT, A)], [('O-2', '123', 'Sent')])

print('\n== 3. swap_new_deals.intrag_follow ==')
SWP = (P.INTRAG_SWAP_CACHE_DIR, '_intrag_swap.json')
P._intrag_swap_persist({'_deal': 'swb-1', 'trade_date': '20/10/2026'}, A)
antes = {'_id': 'swb-1', 'TradeDate': '2026-10-20', 'StartDate': '2026-10-25'}
depois = dict(antes, TradeDate='2026-10-22')
check('o Trade Date do swap mudou: move', SW.intrag_follow(antes, depois), True)
check('   sai do 20 e chega no 22', ([e['_deal'] for e in dia(*SWP, A)],
                                    [e['_deal'] for e in dia(*SWP, B)]), ([], ['swb-1']))
check('só a Data Início mudou (com Trade Date): não move',
      SW.intrag_follow(depois, dict(depois, StartDate='2026-11-01')), False)
check('sem Trade Date, o dia é a Data Início (a regra do b3_mapped)',
      SW.intrag_day({'StartDate': '2026-10-25'}), datetime(2026, 10, 25))

print('\n== 4. o re-save acha a linha no dia novo ==')
fp = P._intrag_day_file(*SWP, B)
lst = S.read(fp)
lst[0].update(status='Approved', intrag_id='IG-5')
S.write(fp, lst)
P._intrag_swap_persist({'_deal': 'swb-1', 'trade_date': '22/10/2026'}, B)
check('uma linha, conteúdo novo e a esteira preservada',
      [(e['_deal'], e['trade_date'], e['status'], e.get('intrag_id')) for e in dia(*SWP, B)],
      [('swb-1', '22/10/2026', 'Approved', 'IG-5')])

print('\n== 5. as origens chamam ==')


def src(rel):
    return open(os.path.join(ROOT, *rel.split('/')), encoding='utf-8').read()


nd = src('apps/pages/features/new_deals/entrypoint.py')
check('os quatro PATCH do New Deals', nd.count("_intrag_segue('"), 4)
for rel in ('apps/pages/features/swap_bullet/commands.py',
            'apps/pages/features/swap_cashflow/commands.py',
            'apps/pages/features/swap_cetes/commands.py'):
    check('o Edit de %s' % rel.split('/')[3], '_sw.intrag_follow(antes, d' in src(rel), True)
check('o Edit da recompra do catálogo',
      '_intrag_segue(page, antes, editada)' in src('apps/pages/features/unwinds/product/commands.py'),
      True)

print(('\nFAIL: %d' % len(fails)) if fails else '\nTUDO OK')
sys.exit(1 if fails else 0)
