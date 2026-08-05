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

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
