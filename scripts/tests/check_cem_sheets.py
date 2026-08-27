"""CEM (Accrual): as abas sao lidas por POSICAO, nao por nome.

1a aba = summary (fatores), 2a = Kapital CETIP (Kapital -> LE). O arquivo real
chega com a 2a aba nomeada de um jeito que o codigo antigo (que procurava
'kapital' no nome) nao reconhecia, e a importacao morria.

Monta workbooks de verdade com openpyxl; nao le nada do disco da area.
"""
import io
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import openpyxl                                          # noqa: E402
from apps.pages import routes as R
# O Accrual mora em features/accrual, separado em camadas (§321): o parser da
# planilha e o de-para de chave são de `infra/mappers` e `domain`.
from apps.pages.features.accrual.infra import mappers as AE  # noqa: E402
from apps.pages.features.accrual import domain as AD         # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


# --- montagem dos arquivos -------------------------------------------------
# summary: col B = Kapital, col C = CETIP, col I = fator parte, col J = fator contra
def summary_rows():
    hdr = ['titulo'] + [''] * 9
    def row(kapital, cetip, i, j):
        r = [''] * 10
        r[1], r[2], r[8], r[9] = kapital, cetip, i, j
        return r
    return [
        hdr,
        row('K001', 'CET-100', '1,23456789', '9,87654321'),   # LE 228 -> normal
        row('K002', 'CET-200', '2,00000000', '5,00000000'),   # LE 199 -> invertido
        row('K003', 'CET-300', '3,00000000', '7,00000000'),   # LE 123 -> ignorado
        row('K004', 'sem digito', '1,0', '1,0'),              # linha de titulo -> ignorada
    ]


# kapital: col B = Kapital, col E = LE
def kapital_rows():
    def row(kapital, le):
        r = [''] * 6
        r[1], r[4] = kapital, le
        return r
    return [['cabecalho'] + [''] * 5,
            row('K001', '0228'), row('K002', '0199'), row('K003', '0123')]


def wb_bytes(sheet_defs):
    """sheet_defs = [(nome, linhas), ...] na ORDEM em que devem aparecer."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheet_defs:
        ws = wb.create_sheet(title=name)
        for r in rows:
            ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


EXPECTED = {
    # 228 = visao do banco -> parte=col I, contra=col J
    'CET-100': ('1.23456789', '9.87654321'),
    # 199 -> invertido: parte=col J, contra=col I
    'CET-200': ('5.00000000', '2.00000000'),
}

print('\n== 1. nomes que o codigo antigo NAO reconhecia ==')
raw = wb_bytes([('Resumo Gerencial', summary_rows()),
                ('Base CETIP x Kapital', kapital_rows())])
fmap = AE._acc_parse_cem_factors('cem.xlsx', raw)
for cetip, exp in EXPECTED.items():
    check('%s' % cetip, AD._acc_fmap_get(fmap, cetip), exp)
check('LE 123 nao entra', AD._acc_fmap_get(fmap, 'CET-300'), None)
check('linha sem digito ignorada', AD._acc_fmap_get(fmap, 'sem digito'), None)

print('\n== 2. nomes antigos continuam funcionando (a posicao e a mesma) ==')
raw = wb_bytes([('Summary', summary_rows()), ('Kapital CETIP', kapital_rows())])
fmap = AE._acc_parse_cem_factors('cem.xlsx', raw)
for cetip, exp in EXPECTED.items():
    check('%s' % cetip, AD._acc_fmap_get(fmap, cetip), exp)

print('\n== 3. nomes sem qualquer relacao ==')
raw = wb_bytes([('Plan1', summary_rows()), ('Plan2', kapital_rows())])
fmap = AE._acc_parse_cem_factors('cem.xlsx', raw)
check('Plan1/Plan2 tambem', AD._acc_fmap_get(fmap, 'CET-100'), EXPECTED['CET-100'])

print('\n== 4. abas alem da 2a nao atrapalham ==')
raw = wb_bytes([('summary', summary_rows()), ('kapital', kapital_rows()),
                ('Notas', [['lixo']]), ('Parametros', [['mais lixo']])])
fmap = AE._acc_parse_cem_factors('cem.xlsx', raw)
check('4 abas, usa as 2 primeiras', AD._acc_fmap_get(fmap, 'CET-200'), EXPECTED['CET-200'])

print('\n== 5. arquivo com uma aba so -> erro explicito ==')
raw = wb_bytes([('summary', summary_rows())])
try:
    AE._acc_parse_cem_factors('cem.xlsx', raw)
    check('deveria ter levantado', True, False)
except ValueError as e:
    msg = str(e)
    check('fala de 2 abas', 'at least 2 sheets' in msg, True)
    check('diz quantas achou', 'found 1' in msg, True)
    check('lista o nome achado', "'summary'" in msg, True)

print('\n== 6. csv (uma "aba" so) -> mesmo erro, sem estourar ==')
try:
    AE._acc_parse_cem_factors('cem.csv', b'a;b;c\n1;2;3\n')
    check('deveria ter levantado', True, False)
except ValueError as e:
    check('erro claro no csv', 'at least 2 sheets' in str(e), True)

print('\n== 7. abas invertidas produzem resultado VAZIO, nao errado ==')
# Documenta a sensibilidade da escolha posicional: com a ordem trocada o
# parser nao acha CETIP valido na aba de Kapital, entao devolve vazio em vez
# de inventar fator — que e a falha desejada (aparece como Missing Accrual).
raw = wb_bytes([('kapital', kapital_rows()), ('summary', summary_rows())])
fmap = AE._acc_parse_cem_factors('cem.xlsx', raw)
check('ordem trocada -> nada casa', AD._acc_fmap_get(fmap, 'CET-100'), None)

print('\n== 8. lookup por digitos (CETIP com formatacao diferente) ==')
raw = wb_bytes([('a', summary_rows()), ('b', kapital_rows())])
fmap = AE._acc_parse_cem_factors('cem.xlsx', raw)
check('acha por digitos', AD._acc_fmap_get(fmap, 'cet100'), EXPECTED['CET-100'])

print('\n== 9. fator negativo vira absoluto (regra do _acc_fmt_factor) ==')
rows = summary_rows()
rows[1][8] = '-1,23456789'
raw = wb_bytes([('a', rows), ('b', kapital_rows())])
fmap = AE._acc_parse_cem_factors('cem.xlsx', raw)
check('sinal descartado', AD._acc_fmap_get(fmap, 'CET-100')[0], '1.23456789')

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
