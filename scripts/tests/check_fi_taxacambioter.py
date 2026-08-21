# -*- coding: utf-8 -*-
"""TAXACAMBIOTER (Batch Conecta TAXA · NDF Other Publisher) — byte a byte.

A montagem da linha saiu do código e passou para o cadastro do File Interface
(`apps/static/data/file-interpreter/taxacambioter.json`). Este check prova que a
troca não mudou um byte: as funções `_legacy_*` abaixo são a cópia autocontida
do gerador ANTIGO (a lista fixa de labels + concat posicional que vivia em
`_ndfop_conecta_fields` / `api_ndfop_send`) e geram os goldens; a linha nova
tem de ser idêntica em cada ramo — linha banco, linha Lawton (swap), campos
vazios (B3 ID em branco) e o comprimento total de 86 caracteres.

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

from apps.pages import routes as R  # noqa: E402

FAILED = [False]


def check(label, ok):
    print(('  ok    ' if ok else ' FAIL   ') + label)
    if not ok:
        FAILED[0] = True


# O N Contr Interno é aleatório (MID(RAND();3;10) da planilha) — fixa para o
# golden ser determinístico. R.random é o módulo stdlib importado pelo routes.
RND = '1234567890'
R.random.choices = lambda *a, **k: list(RND)


# ── Cópia autocontida do gerador LEGADO (pré-File Interface) ─────────────────
#  Transcrição literal do _ndfop_conecta_fields/_ndfop_acct8/_ndfop_rate12 e
#  dos headers montados à mão no api_ndfop_send, como estavam antes da
#  refatoração. É ela que documenta e prova a equivalência.

_COLS = ['CLIENT', 'B3 ID', 'ATHENA ID', 'CCY FC', 'TX PARIDADE',
         'CCY LC', 'TX COTADA', 'CONTA PARTE', 'CONTA CONTRAPARTE']
_LEG_LABELS = ['Id do sistema', 'Id tipo linha', 'Código operação',
               'N Contr Interno', 'Participante', 'Pap. Participante',
               'C.Parte', 'Contrato', 'Tx Câmbio', 'Tx Paridade',
               'Tx Cotada', 'Quantidade de Datas de Verificação']


def _legacy_acct8(v):
    d = re.sub(r'\D', '', str(v or ''))
    return d.zfill(8) if d else ''


def _legacy_valnum(v):
    s = str(v or '').strip()
    if not s:
        return None
    try:
        if ',' in s:
            return float(s.replace('.', '').replace(',', '.'))
        return float(s)
    except ValueError:
        return None


def _legacy_rate12(v):
    n = _legacy_valnum(v)
    if n is None or n < 0:
        return ''
    ip, dec = '{:.8f}'.format(n).split('.')
    return (ip.zfill(4) + dec) if len(ip) <= 4 else ''


def _legacy_fields(cells, swap=False):
    idx = {c: i for i, c in enumerate(_COLS)}
    part, cparte = '73760009', _legacy_acct8(cells[idx['CONTA CONTRAPARTE']])
    if swap:
        part, cparte = cparte, part
    vals = ['TER  ', '1', '0015',
            RND,
            part, ' ', cparte,
            str(cells[idx['B3 ID']] or '').strip().ljust(10),
            ' ' * 12,
            _legacy_rate12(cells[idx['TX PARIDADE']]),
            _legacy_rate12(cells[idx['TX COTADA']]),
            '000']
    return list(zip(_LEG_LABELS, vals))


def _legacy_line(cells, swap=False):
    return ''.join(v for _, v in _legacy_fields(cells, swap))


def _legacy_header(name, pad):
    today = datetime.today().strftime('%Y%m%d')
    return 'TER  00015' + name + ' ' * pad + today + '00001'


def make_cells(**kw):
    row = [''] * len(_COLS)
    for k, v in kw.items():
        row[_COLS.index(k.replace('_', ' '))] = v
    return row


def new_line(cells, swap=False):
    return ''.join(v for _, v in R._ndfop_conecta_fields(cells, swap=swap))


# ── Goldens: os ramos do gerador ─────────────────────────────────────────────

BANCO = make_cells(**{'B3 ID': 'TER0012345', 'TX PARIDADE': '5.55',
                      'TX COTADA': '1.00000000', 'CONTA CONTRAPARTE': '73760.10-2'})
LAWTON = make_cells(**{'B3 ID': 'TER0099876', 'TX PARIDADE': '1.234,56789',
                       'TX COTADA': '1', 'CONTA CONTRAPARTE': '41007'})
VAZIOS = make_cells(**{'B3 ID': '', 'TX PARIDADE': '2.5',
                       'TX COTADA': '1', 'CONTA CONTRAPARTE': '12345'})

print('· linha nova == golden legado, byte a byte')
for label, cells, swap in [('linha banco', BANCO, False),
                           ('linha Lawton (banco-side)', LAWTON, False),
                           ('linha Lawton (swap)', LAWTON, True),
                           ('campos vazios (B3 ID em branco)', VAZIOS, False)]:
    gold = _legacy_line(cells, swap)
    got = new_line(cells, swap)
    check(label, got == gold)
    check(label + ' — 86 chars', len(gold) == 86 and len(got) == 86)

print('· preview: labels e valores campo a campo')
flds = R._ndfop_conecta_fields(BANCO)
leg = _legacy_fields(BANCO)
check('labels vêm do template na ordem do bloco',
      [l for l, _ in flds] == _LEG_LABELS)
check('valores campo a campo idênticos ao legado', flds == leg)
sw = dict(R._ndfop_conecta_fields(LAWTON, swap=True))
check('swap troca Participante e C.Parte',
      sw['Participante'] == '00041007' and sw['C.Parte'] == '73760009')

print('· headers de arquivo passam pelo motor')
check('header banco', R._ndfop_conecta_header('JPMORGANBM') == _legacy_header('JPMORGANBM', 10))
check('header lawton',
      R._ndfop_conecta_header('INTRAGLAWTONFDO') == _legacy_header('INTRAGLAWTONFDO', 5))

print('· o cadastro comanda: template editado muda a linha')
_ORIG_DIR = R._FILE_INTERPRETER_DIR
tmp = tempfile.mkdtemp(prefix='fi-taxacambioter-')
try:
    with open(join(_ORIG_DIR, 'taxacambioter.json'), encoding='utf-8') as fh:
        tpl = json.load(fh)
    blk = next(b for b in tpl['blocks'] if b['id'] == 'registro')
    fld = next(f for f in blk['fields'] if f['field'] == 'Quantidade de Datas de Verificação')
    assert fld['source'] == 'Fixed'
    fld['source_detail'] = '999'
    with open(join(tmp, 'taxacambioter.json'), 'w', encoding='utf-8') as fh:
        json.dump(tpl, fh, ensure_ascii=False, indent=2)
    R._FILE_INTERPRETER_DIR = tmp
    R._fi_tpl_cache.clear()
    edited = new_line(BANCO)
    check('Fixed editado (000 → 999) aparece na linha',
          edited.endswith('999') and edited[:-3] == _legacy_line(BANCO)[:-3])
    shutil.rmtree(tmp)
    tmp = tempfile.mkdtemp(prefix='fi-taxacambioter-vazio-')
    R._FILE_INTERPRETER_DIR = tmp
    R._fi_tpl_cache.clear()
    try:
        R._ndfop_conecta_fields(BANCO)
        check('template ausente → ValueError (nada de arquivo meio montado)', False)
    except ValueError:
        check('template ausente → ValueError (nada de arquivo meio montado)', True)
finally:
    R._FILE_INTERPRETER_DIR = _ORIG_DIR
    R._fi_tpl_cache.clear()
    shutil.rmtree(tmp, ignore_errors=True)

print('· sanidade do cadastro')
with open(join(_ORIG_DIR, 'taxacambioter.json'), encoding='utf-8') as fh:
    tpl = json.load(fh)
reg = next(b for b in tpl['blocks'] if b['id'] == 'registro')
widths = [R._fi_width(f.get('format')) for f in reg['fields']]
check('todo format do registro é mensurável', all(w is not None for w in widths))
check('soma das larguras do registro = 86 = record_length',
      sum(widths) == 86 and tpl.get('record_length') == 86)
hdr = next(b for b in tpl['blocks'] if b['id'] == 'header')
hw = [R._fi_width(f.get('format')) for f in hdr['fields']]
check('header soma 43', all(w is not None for w in hw) and sum(hw) == 43)
contrato = next(f for f in reg['fields'] if f['field'] == 'Contrato')
check('Contrato é X(10) (produção), manual citado no source_note',
      contrato['format'] == 'X(10)' and 'X(11)' in contrato.get('source_note', ''))

sys.exit(1 if FAILED[0] else 0)
