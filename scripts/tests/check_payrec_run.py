"""Pay/Rec: um botao de acao so, e quem decide a fonte e a dropzone.

A tela tinha dois botoes — "Import from folder" e "Run" — e o operador escolhia
a fonte no botao. Agora ha so o Run: com arquivos anexados na dropzone, roda com
ELES; sem nenhum, varre a pasta de insumos (o que o Import fazia).

A regra tem DUAS copias, e e por isso que este script existe:

  * o navegador decide o `mode` que manda no POST
    (`reconciliation-payrec.js`);
  * o servidor decide de novo em `_gather_sources` — `mode == 'manual' and
    files` usa os anexos, qualquer outro caso cai na pasta.

Se so o navegador soubesse da regra, um `manual` sem arquivo (ou um cliente
antigo em cache) mandaria o servidor procurar anexos que nao existem. A queda
para a pasta e o que faz as duas copias concordarem, e e o que este teste prova
de verdade — chamando a funcao, nao lendo o texto dela.

Nao encosta em dado real: a pasta de insumos e um tempfile e a leitura de
planilha e stub.
"""
import io
import os
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from apps.pages import recon_payrec as RP                       # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def read(path):
    return io.open(path, encoding='utf-8').read()


print('\n== 1. sem anexo, o servidor cai na pasta (as duas copias concordam) ==')
tmp = tempfile.mkdtemp(prefix='payrec-test-')
for name in ('settlement_20260805.xlsx', 'RLCTAHIS_20260805.txt'):
    io.open(os.path.join(tmp, name), 'w', encoding='utf-8').write('x')

_base, _read, _persist = RP._INPUT_BASE, RP._read_table, RP._persist_uploads
seen = {}
RP._INPUT_BASE = tmp
RP._read_table = lambda src, sheet=None: ([], [])
RP._persist_uploads = lambda files: [('anexo.xlsx', '/tmp/anexo.xlsx')]
try:
    # `_gather_sources` devolve uma tupla por arquivo lido; o que importa aqui e
    # DE ONDE ele leu, entao contamos.
    check('mode auto le a pasta', len(RP._gather_sources(None, 'auto')), 2)
    check('manual SEM arquivo cai na pasta', len(RP._gather_sources([], 'manual')), 2)
    check('manual com files=None tambem', len(RP._gather_sources(None, 'manual')), 2)
    check('manual COM arquivo usa o anexo', len(RP._gather_sources(['f'], 'manual')), 1)
finally:
    RP._INPUT_BASE, RP._read_table, RP._persist_uploads = _base, _read, _persist
    for name in os.listdir(tmp):
        os.remove(os.path.join(tmp, name))
    os.rmdir(tmp)

print('\n== 2. a tela tem um botao de acao so ==')
HTML = read('apps/templates/pages/reconciliation-payrec.html')
check('o botao Import sumiu', 'prImportBtn' in HTML, False)
check('o Run continua', HTML.count('id="prRunBtn"'), 1)
check('o End process continua', HTML.count('id="prEndBtn"'), 1)
check('a dropzone continua', HTML.count('id="prDrop"'), 1)

print('\n== 3. o navegador manda o modo pela dropzone ==')
JS = read('apps/static/js/pages/reconciliation-payrec.js')
check('quem decide e a contagem de arquivos',
      'var manual = dzFiles.length > 0;' in JS, True)
check('com arquivo vai manual', "fd.append('mode', 'manual');" in JS, True)
check('sem arquivo vai auto', "p.set('mode', 'auto');" in JS, True)
check('nenhum call site passa modo fixo',
      "run('manual'" in JS or "run('auto'" in JS, False)
check('so o Run dispara', JS.count('run(runBtn)'), 1)
# Limpar a dropzone so faz sentido quando os anexos foram de fato enviados.
check('a dropzone so limpa no caminho manual',
      'if (manual) clearDzFiles();' in JS, True)

print('\n== 4. o rotulo diz qual dos dois caminhos vai acontecer ==')
check('o hint acompanha a dropzone', JS.count('syncRunHint()'), 3)
for lang in ('en', 'br', 'es'):
    check('%s tem os dois textos' % lang,
          ('runFolder:' in JS and 'runFiles:' in JS), True)

print('\n== 5. a chave i18n do botao removido nao ficou orfa ==')
for lang in ('en', 'br', 'es'):
    j = read('apps/static/data/translations/%s.json' % lang)
    check('%s.json sem pr-import' % lang, '"pr-import"' in j, False)
check('nenhum data-lang aponta para ela', 'data-lang="pr-import"' in HTML, False)

print('\n== 6. o IR regressivo do SWAP no lado interno ==')
# O lado interno chega BRUTO e o historico de mensagens traz o LIQUIDO. Sem
# descontar o IR a linha fica pendente todos os dias por uma diferenca que e
# imposto — foi o caso reportado: -55.462,81 interno contra -47.143,38 do
# cliente, exatamente 15%.
from datetime import date as _date                            # noqa: E402

CF_COLS = ['Trade Id', 'Amount', 'Cpty Name', 'Cashflow Event', 'Asset Class',
           'Owner Legal Entity', 'x1', 'x2', 'x3', 'x4', 'Trade Date']
REF = _date(2026, 8, 5)


def cf(trade, amt, cpty, tdate, asset='INTEREST_RATE'):
    return {'Trade Id': trade, 'Amount': amt, 'Cpty Name': cpty, 'Cashflow Event': '',
            'Asset Class': asset, 'Owner Legal Entity': '0228',
            'x1': '', 'x2': '', 'x3': '', 'x4': '', 'Trade Date': tdate}


def swap_val(rows, ref=REF):
    out = RP._jpm_cashflows(rows, CF_COLS, None, ref_date=ref)
    return round(sum(r['value'] for r in out), 2)


check('o caso reportado: 15% sobre o bruto',
      swap_val([cf('T1', -55462.81, 'SUZANO SA', '01/01/2023')]), -47143.39)
# A tabela e REGRESSIVA: prazo curto paga mais. Uma aliquota fixa passaria no
# teste acima e erraria em todo trade novo.
check('prazo curto paga 22,5%',
      swap_val([cf('T4', -10000.0, 'SUZANO SA', '01/07/2026')]), -7750.00)
# Quem responde "e banco?" e o cadastro `swap-ir-client`, nao um if aqui.
check('banco nao sofre retencao',
      swap_val([cf('T2', -55462.81, 'BANCO SAFRA S.A.', '01/01/2023')]), -55462.81)
check('recebimento fica intacto (a retencao nao e nossa)',
      swap_val([cf('T3', 55462.81, 'SUZANO SA', '01/01/2023')]), 55462.81)
# Sem data nao ha faixa de prazo: descontar por chute e pior que deixar o bruto
# e a linha acusar.
check('sem Trade Date fica BRUTO',
      swap_val([cf('T5', -10000.0, 'SUZANO SA', '')]), -10000.00)
# O IR incide sobre o PAGAMENTO, que e o net do trade — perna a perna tributaria
# valores que se anulam dentro do proprio trade.
check('o IR incide sobre o NET do trade, nao perna a perna',
      swap_val([cf('T6', -30000.0, 'SUZANO SA', '01/01/2023'),
                cf('T6', 10000.0, 'SUZANO SA', '01/01/2023')]), -17000.00)
# A data da conciliacao manda, nao "hoje": reexecutar um dia antigo tem de dar o
# mesmo numero que ja foi conferido.
check('o prazo conta ate a data da CONCILIACAO',
      swap_val([cf('T7', -10000.0, 'SUZANO SA', '01/01/2023')], ref=_date(2023, 3, 1)), -7750.00)
# E a commodity, que ja tinha a sua taxa de 0,005%, nao muda.
check('COMM TER segue com os seus 0,005%',
      swap_val([cf('C1', -1000.0, 'SUZANO SA', '01/01/2023', asset='COMMODITY'),
                cf('C1', -1000.0, 'SUZANO SA', '01/01/2023', asset='COMMODITY')]), -1999.90)

# Uma regra so: a aliquota vem da funcao que o Trade Level e o aviso usam.
SRC = read('apps/pages/recon_payrec.py')
check('a aliquota vem do _ops_swap_ir_rate', 'from apps.pages.routes import _ops_swap_ir_rate' in SRC, True)
check('e nao ha tabela de faixas recopiada aqui',
      ('22.5' in SRC or '0.225' in SRC or '17.5' in SRC), False)

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
