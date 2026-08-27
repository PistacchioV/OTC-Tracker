# -*- coding: utf-8 -*-
"""ACCRUAL (CETIP SWAP Atualização de PU/Fator · 0015) — byte a byte.

A montagem da linha saiu do código e passou para o cadastro do File Interface
(`apps/static/data/file-interpreter/swap-atualizacao-pu-fator.json`). Este check
prova que a troca não mudou um byte: as funções `_legacy_*` abaixo são a cópia
autocontida do gerador ANTIGO (`_acc_swap_header` / `_acc_swap_records` como
eram antes da refatoração) e geram os goldens; a linha nova tem de ser idêntica
em cada ramo — as três views (BANCO / LAWTON / ATACAMA), as duas pernas
(curva 00 e 01), o PU em branco (22 espaços) e o comprimento total de 77.

Divergência de produção mantida de propósito (documentada no notes do
cadastro): Papel/Curva '01' vai para a conta MAIOR, enquanto o manual manda a
menor — o golden é a produção, não o manual.

Não toca em dado real: testa as funções de montagem de linha, não os endpoints
que gravam no share; o template alterado vai para tempfile.
"""
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime
from os.path import abspath, dirname, join, normpath

ROOT = normpath(join(dirname(abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from apps.pages import routes as R
# O Accrual mora em features/accrual (nomes preservados no engine).
from apps.pages.features.accrual import engine as AE  # noqa: E402  # noqa: E402

FAILED = [False]


def check(label, ok):
    print(('  ok    ' if ok else ' FAIL   ') + label)
    if not ok:
        FAILED[0] = True


# O Meu Número é aleatório — fixa para o golden ser determinístico.
# R.random é o módulo stdlib importado pelo routes.
RND = '7777777777'
R.random.choice = lambda seq: '7'

TODAY = datetime.now().strftime('%Y%m%d')


# ── Cópia autocontida do gerador LEGADO (pré-File Interface) ─────────────────
#  Transcrição literal de _acc_swap_fator/_acc_swap_header/_acc_swap_records
#  como estavam antes da refatoração. É ela que documenta e prova a
#  equivalência.

_VIEW_BY_PREFIX = {'73760': 'BANCO', '04880': 'BANCO', '85398': 'ATACAMA', '00041': 'LAWTON'}
_PART_NAME = {'BANCO': 'JPMORGANBM', 'LAWTON': 'INTRAGLAWTONFDO', 'ATACAMA': 'INTRAGATACAMAFDO'}


def _legacy_fator(f):
    try:
        n = abs(float(str(f or '').replace(',', '.')))
    except (ValueError, TypeError):
        n = 0.0
    ip, fp = '{:.8f}'.format(n).split('.')
    return ip[-2:].rjust(2, '0') + fp


def _legacy_header(view, today):
    return 'SWAP 00015' + _PART_NAME.get(view, view).ljust(20) + today


def _legacy_records(row, today):
    codigo = str(row[0] or '').strip()
    accP, idxP = row[3], str(row[5] or '').strip().upper()
    accC, idxC = row[6], str(row[8] or '').strip().upper()
    fatP, fatC = row[9], row[10]
    digP = re.sub(r'\D', '', str(accP or ''))
    digC = re.sub(r'\D', '', str(accC or ''))
    numP = int(digP or '0')
    numC = int(digC or '0')
    roleP = '01' if numP > numC else '00'
    roleC = '01' if numC > numP else '00'
    legs = []
    if idxP == 'VCP':
        legs.append((roleP, fatP))
    if idxC == 'VCP':
        legs.append((roleC, fatC))
    if not legs:
        return []
    prefP, prefC = digP[:5], digC[:5]
    updaters = [(roleP, prefP)]
    if prefC in _VIEW_BY_PREFIX and prefC != prefP:
        updaters.append((roleC, prefC))
    out = []
    for papel, pref in updaters:
        view = _VIEW_BY_PREFIX.get(pref)
        if not view:
            continue
        for curva, fat in legs:
            line = ('SWAP ' + '1' + '0015' + codigo + papel + '00' + curva +
                    today + RND + (' ' * 22) + _legacy_fator(fat))
            out.append({'view': view, 'line': line})
    return out


# Uma linha da tabela do Accrual só é lida nos índices 0..10:
# [Código IF, _, _, PARTE/Conta, _, PARTE/Indexador, CONTRAPARTE/Conta, _,
#  CONTRAPARTE/Indexador, Fator Parte, Fator Contraparte]
def make_row(codigo, accP, idxP, accC, idxC, fatP, fatC):
    return [codigo, '', '', accP, '', idxP, accC, '', idxC, fatP, fatC]


# ── Goldens: os ramos do gerador ─────────────────────────────────────────────
#  Contraparte externa → só a view BANCO; Lawton com as DUAS pernas VCP →
#  4 linhas (2 views × curvas 01 e 00); Atacama com a perna da contraparte →
#  papel 00 na visão do banco e 01 na do fundo.

BANCO_ONLY = make_row('20259876543', '73760.00-9', 'VCP', '12345.67-8', 'DI1',
                      '1.00123456', '')
LAWTON_BOTH = make_row('SWP20250001', '73760.00-9', 'VCP', '00041.00-7', 'VCP',
                       '1.00045', '0,99987654')
ATACAMA_CONTRA = make_row('20257777001', '04880.00-6', 'PRE', '85398.00-5', 'VCP',
                          '', '2.5')
SEM_VCP = make_row('20250000009', '73760.00-9', 'PRE', '12345.67-8', 'DI1',
                   '1.1', '1.2')

print('· linha nova == golden legado, byte a byte')
for label, row in [('contraparte externa → 1 linha BANCO', BANCO_ONLY),
                   ('Lawton, duas pernas VCP → 4 linhas (curvas 01 e 00)', LAWTON_BOTH),
                   ('Atacama, perna da contraparte → BANCO + ATACAMA', ATACAMA_CONTRA)]:
    gold = _legacy_records(row, TODAY)
    got = AE._acc_swap_records(row, TODAY)
    check(label, [(g['view'], g['line']) for g in got] ==
          [(g['view'], g['line']) for g in gold])
    check(label + ' — 77 chars', all(len(g['line']) == 77 for g in got) and
          all(len(g['line']) == 77 for g in gold))

check('sem perna VCP → nenhuma linha', AE._acc_swap_records(SEM_VCP, TODAY) == [])

golds = _legacy_records(LAWTON_BOTH, TODAY)
check('4 linhas: BANCO×2 + LAWTON×2', [g['view'] for g in golds] ==
      ['BANCO', 'BANCO', 'LAWTON', 'LAWTON'])
check('curvas 01 (parte) e 00 (contraparte) nas duas views',
      [g['line'][25:27] for g in golds] == ['01', '00', '01', '00'])
line = AE._acc_swap_records(LAWTON_BOTH, TODAY)[0]['line']
check('PU em branco = 22 espaços (posições 46-67)', line[45:67] == ' ' * 22)
check('fator |0,99987654| → 0099987654',
      _legacy_fator('0,99987654') == '0099987654' and
      AE._acc_swap_records(LAWTON_BOTH, TODAY)[1]['line'][67:77] == '0099987654')
check('fator vazio → 0000000000', _legacy_fator('') == '0000000000')

print('· headers de arquivo passam pelo motor')
for view in ('BANCO', 'LAWTON', 'ATACAMA'):
    check('header ' + view, AE._acc_swap_header(view, TODAY) == _legacy_header(view, TODAY))

print('· o cadastro comanda: template editado muda a linha')
_ORIG_DIR = R._FILE_INTERPRETER_DIR
tmp = tempfile.mkdtemp(prefix='fi-accrual-')
try:
    with open(join(_ORIG_DIR, 'swap-atualizacao-pu-fator.json'), encoding='utf-8') as fh:
        tpl = json.load(fh)
    blk = next(b for b in tpl['blocks'] if b['id'] == 'registro')
    fld = next(f for f in blk['fields'] if f['field'] == 'Tipo de Atualização')
    assert fld['source'] == 'Fixed'
    fld['source_detail'] = '27'
    with open(join(tmp, 'swap-atualizacao-pu-fator.json'), 'w', encoding='utf-8') as fh:
        json.dump(tpl, fh, ensure_ascii=False, indent=2)
    R._FILE_INTERPRETER_DIR = tmp
    R._fi_tpl_cache.clear()
    edited = AE._acc_swap_records(BANCO_ONLY, TODAY)[0]['line']
    gold = _legacy_records(BANCO_ONLY, TODAY)[0]['line']
    check('Fixed editado (Tipo 00 → 27) aparece na linha',
          edited[23:25] == '27' and edited[:23] == gold[:23] and edited[25:] == gold[25:])
    shutil.rmtree(tmp)
    tmp = tempfile.mkdtemp(prefix='fi-accrual-vazio-')
    R._FILE_INTERPRETER_DIR = tmp
    R._fi_tpl_cache.clear()
    try:
        AE._acc_swap_records(BANCO_ONLY, TODAY)
        check('template ausente → ValueError (nada de arquivo meio montado)', False)
    except ValueError:
        check('template ausente → ValueError (nada de arquivo meio montado)', True)
finally:
    R._FILE_INTERPRETER_DIR = _ORIG_DIR
    R._fi_tpl_cache.clear()
    shutil.rmtree(tmp, ignore_errors=True)

print('· sanidade do cadastro')
with open(join(_ORIG_DIR, 'swap-atualizacao-pu-fator.json'), encoding='utf-8') as fh:
    tpl = json.load(fh)
reg = next(b for b in tpl['blocks'] if b['id'] == 'registro')
widths = [R._fi_width(f.get('format')) for f in reg['fields']]
check('todo format do registro é mensurável', all(w is not None for w in widths))
check('soma das larguras do registro = 77 = record_length',
      sum(w or 0 for w in widths) == 77 and tpl.get('record_length') == 77)
hdr = next(b for b in tpl['blocks'] if b['id'] == 'header')
hw = [R._fi_width(f.get('format')) for f in hdr['fields']]
check('header soma 38', all(w is not None for w in hw) and sum(hw) == 38)
pu = next(f for f in reg['fields'] if f['field'] == 'PU para Atualização')
check('PU é Fixed vazio 9(14)V9(08) (22 espaços), manual citado no source_note',
      pu['source'] == 'Fixed' and pu['source_detail'] == '' and
      pu['format'] == '9(14)V9(08)' and 'v9' in pu.get('source_note', ''))

sys.exit(1 if FAILED[0] else 0)
