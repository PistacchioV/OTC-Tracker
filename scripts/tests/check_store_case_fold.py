# -*- coding: utf-8 -*-
"""O armazém num sistema de arquivos que DIFERENCIA caixa (o EFS do Stratos, §713).

O share da produção guarda `db/cache/B3 Files` e `db/cache/New Deals` (da
importação a partir do disco) e, dentro dos bancos, o `_manifest` com as duas
grafias — `cache/New Deals/…` e `cache/new deals/…`. O código pede tudo em
minúsculas. No Windows (e no Mac) isso não aparece; no Linux o banco "não
existia" e o Dashboard e o New Deals abriam vazios, sem erro nenhum.

O que se prova, num volume que diferencia caixa de verdade (no Mac, uma imagem
APFS case-sensitive montada pelo próprio teste; no Linux, a pasta temporária):

  1. a detecção: o volume diferencia, o disco do Mac não;
  2. o defeito, com a correção DESLIGADA: o caminho pedido em minúsculas não
     acha o banco gravado em `New Deals`;
  3. ligada: leitura, `isfile`, `stat`, `day_files`, `listdir`, `prefetch` e o
     `_canal_no_banco` acham a grafia gravada; a listagem devolve o caminho na
     grafia PEDIDA;
  4. gravar pelo código cai no MESMO arquivo (nenhuma pasta gêmea `new deals`);
  5. o mesmo dia nas duas grafias: vale a gravada por último; o `remove` tira
     as duas;
  6. fora dele (o disco do Mac), nada muda: a correção não liga sozinha.

    OTC_SHARED_DRIVE_ROOT=/tmp/otc-share python scripts/tests/check_store_case_fold.py
"""
import atexit
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'
os.environ.pop('OTC_STORE_CASE_FOLD', None)

from apps.pages import routes as R                          # noqa: E402
from apps.pages import data_store as S                      # noqa: E402

fails = []


def check(label, got, exp=True):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label +
          ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def _diferencia(pasta):
    a = os.path.join(pasta, 'CaixaTeste')
    os.makedirs(a, exist_ok=True)
    try:
        return not os.path.exists(os.path.join(pasta, 'caixateste'))
    finally:
        shutil.rmtree(a, ignore_errors=True)


def volume_que_diferencia():
    """Uma pasta num sistema de arquivos que diferencia caixa, ou None."""
    tmp = tempfile.mkdtemp(prefix='otc-caixa-')
    if _diferencia(tmp):
        return tmp
    if sys.platform != 'darwin' or not shutil.which('hdiutil'):
        return None
    img, mnt = os.path.join(tmp, 'cs'), os.path.join(tmp, 'vol')
    try:
        subprocess.run(['hdiutil', 'create', '-size', '64m', '-fs', 'Case-sensitive APFS',
                        '-volname', 'otccaixa', '-type', 'SPARSE', img],
                       check=True, capture_output=True)
        subprocess.run(['hdiutil', 'attach', '-nobrowse', '-mountpoint', mnt, img + '.sparseimage'],
                       check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    atexit.register(lambda: subprocess.run(['hdiutil', 'detach', '-force', mnt], capture_output=True))
    return mnt


def usar_raiz(raiz):
    R._B3_DATA_DIR = raiz
    S.memo_forget()
    S._caixa_memo.clear()
    S._dcache.clear()
    S._mfold.clear()


VOL = volume_que_diferencia()
if VOL is None:
    print('skip: sem um sistema de arquivos que diferencie caixa (nem hdiutil)')
    sys.exit(0)
DATA = os.path.join(VOL, 'data')
os.makedirs(os.path.join(DATA, 'db'))
usar_raiz(DATA)


def p(*parts):
    return os.path.join(DATA, *parts)


GRAVADO_27 = p('cache', 'New Deals', 'NDF', 'Vanilla', '2026', '10', '27', '20261027_ndfvanilla.json')
PEDIDO_27 = p('cache', 'new deals', 'NDF', 'Vanilla', '2026', '10', '27', '20261027_ndfvanilla.json')
BASE_PEDIDA = p('cache', 'new deals', 'NDF', 'Vanilla')

print('== 1. a detecção ==')
S.CASE_FOLD = None
check('o volume diferencia caixa', S._fs_diferencia_caixa(), True)

# A importação de antes: o caminho com a grafia do DISCO (`New Deals`).
S.write(GRAVADO_27, [{'Deal': 'D1', 'Client': 'ACME'}])
check('o banco nasceu na pasta `New Deals`',
      os.path.isfile(os.path.join(DATA, 'db', 'cache', 'New Deals', 'NDF', 'Vanilla.db')))

print('\n== 2. o defeito, com a correção desligada ==')
S.CASE_FOLD = False
S.memo_forget()
check('isfile pelo caminho do código não acha', S.isfile(PEDIDO_27), False)
check('day_files pela base do código não lista nada', list(S.day_files(BASE_PEDIDA, '_ndfvanilla.json')), [])

print('\n== 3. ligada: tudo acha a grafia gravada ==')
S.CASE_FOLD = None
S.memo_forget()
check('read', S.read(PEDIDO_27), [{'Deal': 'D1', 'Client': 'ACME'}])
check('isfile', S.isfile(PEDIDO_27), True)
check('stat', S.stat(PEDIDO_27).st_size > 0, True)
dias = list(S.day_files(BASE_PEDIDA, '_ndfvanilla.json'))
check('day_files: o dia, com o caminho na grafia PEDIDA', [d[0] for d in dias], [PEDIDO_27])
check('listdir da pasta do mês pela grafia do código',
      S.listdir(p('cache', 'new deals', 'NDF', 'Vanilla', '2026', '10')), ['27'])
S.memo_forget()
check('prefetch', S.prefetch([PEDIDO_27]).get(PEDIDO_27), [{'Deal': 'D1', 'Client': 'ACME'}])
check('tem_raw', S.tem_raw(PEDIDO_27), True)

print('\n== 4. gravar pelo código cai no MESMO arquivo ==')
PEDIDO_28 = p('cache', 'new deals', 'NDF', 'Vanilla', '2026', '10', '28', '20261028_ndfvanilla.json')
S.write(PEDIDO_28, [{'Deal': 'D2'}])
check('nenhuma pasta gêmea `new deals` em db/cache',
      sorted(os.listdir(os.path.join(DATA, 'db', 'cache'))), ['New Deals'])
check('o dia novo é lido', S.read(PEDIDO_28), [{'Deal': 'D2'}])
check('a listagem tem os dois dias', len(list(S.day_files(BASE_PEDIDA, '_ndfvanilla.json'))), 2)

print('\n== 5. o mesmo dia nas duas grafias ==')
S.write(PEDIDO_27, [{'Deal': 'D1', 'Client': 'ACME CORRIGIDA'}])
S.memo_forget()
check('vale a gravada por último', S.read(PEDIDO_27), [{'Deal': 'D1', 'Client': 'ACME CORRIGIDA'}])
check('e a grafia antiga lê o mesmo dia (a tabela é uma só)',
      S.read(GRAVADO_27), [{'Deal': 'D1', 'Client': 'ACME CORRIGIDA'}])
check('a listagem não repete o dia', len(list(S.day_files(BASE_PEDIDA, '_ndfvanilla.json'))), 2)
S.remove(PEDIDO_27)
S.memo_forget()
check('o remove tira as duas grafias', (S.isfile(PEDIDO_27), S.isfile(GRAVADO_27)), (False, False))

print('\n== 6. fora dele nada muda ==')
MAC = tempfile.mkdtemp(prefix='otc-caixa-ci-')
os.makedirs(os.path.join(MAC, 'db'))
usar_raiz(MAC)
if _diferencia(MAC):
    print('  (o tmp deste sistema já diferencia caixa: a seção não se aplica)')
else:
    check('o disco que não diferencia não liga a correção', S._fs_diferencia_caixa(), False)

print(('\nFALHAS (%d): %s' % (len(fails), fails)) if fails else '\nTUDO OK')
sys.exit(1 if fails else 0)
