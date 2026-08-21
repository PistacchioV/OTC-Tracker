# -*- coding: utf-8 -*-
"""MID (MtM · Registro de Informações de Derivativos · 0848) — byte a byte.

A montagem da linha saiu do código e passou para o cadastro do File Interface
(`apps/static/data/file-interpreter/mid-informacoes-derivativos.json`). Este
check prova que a troca não mudou um byte: as funções `_legacy_*` abaixo são a
cópia autocontida do gerador ANTIGO (`_mtm_swap_fields` / `_mtm_swap_header` /
`_mtm_generate_book` / `_mtm_file_lines` como eram antes da refatoração) e
geram os goldens; a linha nova tem de ser idêntica em cada ramo — dois books
(CEM→Lawton, EDG→Atacama) com o espelho de sinal invertido, contraparte
externa sem espelho, MtM zero → 0.01, campo de valor vazio, os Notionals em
branco (6+6 espaços) e o comprimento total de 93.

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


# O Meu Número é aleatório — fixa para o golden ser determinístico.
# R.random é o módulo stdlib importado pelo routes.
RND = '7777777777'
R.random.choice = lambda seq: '7'

YMD = '20260806'


# ── Cópia autocontida do gerador LEGADO (pré-File Interface) ─────────────────
#  Transcrição literal de _mtm_gen_min_value/_mtm_valor_fixed/_mtm_cpty_of/
#  _mtm_swap_fields/_mtm_swap_header/_mtm_generate_book/_mtm_file_lines como
#  estavam antes da refatoração (concat posicional sobre _MTM_GEN_SWAP_COLS).
#  É ela que documenta e prova a equivalência.

_LAWTON_ACCT = '00041007'
_ATACAMA_ACCT = {'85398005'}
_PARTY = {'BANCO': 'JPMORGANBM' + ' ' * 10,
          'LAWTON': 'INTRAGLAWTONFDO' + ' ' * 5,
          'ATACAMA': 'INTRAGATACAMAFDO' + ' ' * 4}
_PARTY_ACCT = {'BANCO': '73760009', 'LAWTON': '00041007', 'ATACAMA': '85398005'}
_BOOK_SUFFIX = {'EDG': 'EDG', 'CEM': 'CEM', 'Hybrids': 'HYB'}
_BOOK_CPTY = {'EDG': 'ATACAMA', 'CEM': 'LAWTON', 'Hybrids': 'LAWTON'}
_SWAP_COLS = ['ID do Sistema', 'ID Tipo de Linha', 'Código da Operação', 'Meu Número',
              'Código do Contrato', 'Nome Simplificado Parte', 'Código Conta Parte',
              'Sinal Valor MTM', 'Valor MTM', 'Notional Mínimo', 'Notional Máximo',
              'Data de Referência MTM']


def _legacy_parse_num(s):
    s = str(s or '').strip().strip("'").strip('"').replace(',', '').strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _legacy_min_value(v):
    v = v or 0.0
    return 0.01 if round(v, 2) == 0 else v


def _legacy_valor_fixed(v, int_digits):
    return str(int(round(abs(v or 0.0) * 100))).zfill(int_digits + 2)


def _legacy_cpty_of(row):
    acct = re.sub(r'\D', '', str(row[4] if len(row) > 4 else '' or ''))
    if acct == _LAWTON_ACCT:
        return 'LAWTON'
    if acct in _ATACAMA_ACCT:
        return 'ATACAMA'
    return None


def _legacy_swap_fields(cid, party_key, sinal, v, ymd):
    return {
        'ID do Sistema': 'MID  ', 'ID Tipo de Linha': '1', 'Código da Operação': '0848',
        'Meu Número': RND, 'Código do Contrato': str(cid or ''),
        'Nome Simplificado Parte': _PARTY[party_key],
        'Código Conta Parte': _PARTY_ACCT[party_key],
        'Sinal Valor MTM': sinal, 'Valor MTM': _legacy_valor_fixed(_legacy_min_value(v), 10),
        'Notional Mínimo': ' ' * 6, 'Notional Máximo': ' ' * 6, 'Data de Referência MTM': ymd,
    }


def _legacy_swap_header(party_key, today):
    return 'MID' + '  ' + '0' + '0848' + _PARTY[party_key] + today


def _legacy_generate_book(book_key, rows, ymd):
    suffix = _BOOK_SUFFIX.get(book_key)
    if not suffix:
        return {}
    book_cpty = _BOOK_CPTY.get(book_key)
    today = datetime.now().strftime('%Y%m%d')
    banco = 'MtM_BANCO-' + suffix
    files = {banco: {'view': 'BANCO', 'cols': _SWAP_COLS,
                     'header': _legacy_swap_header('BANCO', today), 'rows': []}}
    for row in rows:
        v = _legacy_parse_num(row[7]) or 0.0
        cid = row[0]
        sinal = '00' if v >= 0 else '01'
        files[banco]['rows'].append(_legacy_swap_fields(cid, 'BANCO', sinal, v, ymd))
        if book_cpty and _legacy_cpty_of(row) == book_cpty:
            fn = 'MtM_' + book_cpty + '-' + suffix
            files.setdefault(fn, {'view': book_cpty, 'cols': _SWAP_COLS,
                                  'header': _legacy_swap_header(book_cpty, today), 'rows': []})
            files[fn]['rows'].append(
                _legacy_swap_fields(cid, book_cpty, '01' if v >= 0 else '00', v, ymd))
    return files


def _legacy_file_lines(fdata):
    return [fdata['header']] + [''.join(r[c] for c in fdata['cols']) for r in fdata['rows']]


# Uma linha da tabela do MtM só é lida nos índices 0 (Código IF),
# 4 (CONTRAPARTE / Conta) e 7 (Valor MTM, formato '{:,.2f}' da página).
def make_row(cid, conta, valor):
    return [cid, '', '', '', conta, '', '', valor]


# ── Goldens: os ramos do gerador ─────────────────────────────────────────────

CEM_ROWS = [
    make_row('20250012345', '12345.67-8', '1,802,855.65'),   # externa → sem espelho
    make_row('20250054321', '00041.00-7', '-2,500.00'),      # Lawton, negativo → espelho 00
    make_row('20250098765', '99999.99-9', ''),               # valor vazio → 0.01
]
EDG_ROWS = [
    make_row('20257777001', '85398.00-5', '0.00'),           # Atacama, MtM zero → 0.01
]

print('· arquivos novos == golden legado, byte a byte')
for label, book, rows in [('book CEM (BANCO + espelho LAWTON)', 'CEM', CEM_ROWS),
                          ('book EDG (BANCO + espelho ATACAMA)', 'EDG', EDG_ROWS),
                          ('book Hybrids (espelho LAWTON, sufixo HYB)', 'Hybrids',
                           [make_row('20251111111', '00041.00-7', '10.00')])]:
    gold = _legacy_generate_book(book, rows, YMD)
    got = R._mtm_generate_book(book, rows, YMD)
    check(label + ' — mesmos arquivos', sorted(got) == sorted(gold))
    same = all(R._mtm_file_lines(got[fn]) == _legacy_file_lines(gold[fn]) for fn in gold)
    check(label + ' — linhas idênticas', same)
    lens = [len(ln) for fn in got for ln in R._mtm_file_lines(got[fn])[1:]]
    check(label + ' — 93 chars', lens and all(n == 93 for n in lens))

gold = _legacy_generate_book('CEM', CEM_ROWS, YMD)
check('externa não espelha; Lawton sim',
      sorted(gold) == ['MtM_BANCO-CEM', 'MtM_LAWTON-CEM'] and
      len(gold['MtM_LAWTON-CEM']['rows']) == 1)
lines = _legacy_file_lines(gold['MtM_BANCO-CEM'])
check('sinal 00/01 e espelho invertido',
      lines[2][59:61] == '01' and
      _legacy_file_lines(gold['MtM_LAWTON-CEM'])[1][59:61] == '00')
check('valor vazio → 0.01 → 000000000001', lines[3][61:73] == '000000000001')
check('MtM zero → 0.01', _legacy_file_lines(
    _legacy_generate_book('EDG', EDG_ROWS, YMD)['MtM_BANCO-EDG'])[1][61:73] == '000000000001')
check('Notionals em branco = 12 espaços (posições 74-85)',
      lines[1][73:85] == ' ' * 12)
got = R._mtm_generate_book('CEM', CEM_ROWS, YMD)
check('book desconhecido → nada', R._mtm_generate_book('COE', CEM_ROWS, YMD) == {})

print('· preview: rótulos vêm do template, células fecham com a linha')
prev = R._mtm_gen_preview(got)
with open(join(R._FILE_INTERPRETER_DIR, 'mid-informacoes-derivativos.json'), encoding='utf-8') as fh:
    tpl = json.load(fh)
reg = next(b for b in tpl['blocks'] if b['id'] == 'registro-emissao')
tpl_labels = [f['field'] for f in reg['fields']]
banco_prev = next(p for p in prev if p['filename'] == 'MtM_BANCO-CEM.txt')
check('labels do preview == field do template', banco_prev['cols'] == tpl_labels)
check('células remontam a linha byte a byte',
      [''.join(cells) for cells in banco_prev['rows']] ==
      R._mtm_file_lines(got['MtM_BANCO-CEM'])[1:])
check('header do preview == header do arquivo',
      banco_prev['header'] == _legacy_swap_header('BANCO', datetime.now().strftime('%Y%m%d')))

print('· headers de arquivo passam pelo motor')
today = datetime.now().strftime('%Y%m%d')
for pk in ('BANCO', 'LAWTON', 'ATACAMA'):
    check('header ' + pk, R._mtm_swap_header(pk, today) == _legacy_swap_header(pk, today))

print('· o cadastro comanda: template editado muda a linha')
_ORIG_DIR = R._FILE_INTERPRETER_DIR
tmp = tempfile.mkdtemp(prefix='fi-mid-')
try:
    blk = next(b for b in tpl['blocks'] if b['id'] == 'registro-emissao')
    fld = next(f for f in blk['fields'] if f['field'] == 'Código da Operação')
    assert fld['source'] == 'Fixed'
    fld['source_detail'] = '0849'
    with open(join(tmp, 'mid-informacoes-derivativos.json'), 'w', encoding='utf-8') as fh:
        json.dump(tpl, fh, ensure_ascii=False, indent=2)
    R._FILE_INTERPRETER_DIR = tmp
    R._fi_tpl_cache.clear()
    edited = R._mtm_file_lines(R._mtm_generate_book('CEM', CEM_ROWS[:1], YMD)['MtM_BANCO-CEM'])[1]
    gold1 = _legacy_file_lines(_legacy_generate_book('CEM', CEM_ROWS[:1], YMD)['MtM_BANCO-CEM'])[1]
    check('Fixed editado (0848 → 0849) aparece na linha',
          edited[6:10] == '0849' and edited[:6] == gold1[:6] and edited[10:] == gold1[10:])
    shutil.rmtree(tmp)
    tmp = tempfile.mkdtemp(prefix='fi-mid-vazio-')
    R._FILE_INTERPRETER_DIR = tmp
    R._fi_tpl_cache.clear()
    try:
        R._mtm_generate_book('CEM', CEM_ROWS[:1], YMD)
        check('template ausente → ValueError (nada de arquivo meio montado)', False)
    except ValueError:
        check('template ausente → ValueError (nada de arquivo meio montado)', True)
finally:
    R._FILE_INTERPRETER_DIR = _ORIG_DIR
    R._fi_tpl_cache.clear()
    shutil.rmtree(tmp, ignore_errors=True)

print('· sanidade do cadastro')
with open(join(_ORIG_DIR, 'mid-informacoes-derivativos.json'), encoding='utf-8') as fh:
    tpl = json.load(fh)
reg = next(b for b in tpl['blocks'] if b['id'] == 'registro-emissao')
widths = [R._fi_width(f.get('format')) for f in reg['fields']]
check('todo format do registro é mensurável', all(w is not None for w in widths))
check('soma das larguras do registro = 93 = record_length',
      sum(w or 0 for w in widths) == 93 and tpl.get('record_length') == 93)
hdr = next(b for b in tpl['blocks'] if b['id'] == 'header')
hw = [R._fi_width(f.get('format')) for f in hdr['fields']]
check('header soma 38', all(w is not None for w in hw) and sum(hw) == 38)
for name in ('Notional Mínimo', 'Notional Máximo'):
    fld = next(f for f in reg['fields'] if f['field'] == name)
    check(name + ' é Fixed vazio 9(04)V9(02) (6 espaços), manual citado no source_note',
          fld['source'] == 'Fixed' and fld['source_detail'] == '' and
          fld['format'] == '9(04)V9(02)' and 'v9' in fld.get('source_note', ''))

sys.exit(1 if FAILED[0] else 0)
