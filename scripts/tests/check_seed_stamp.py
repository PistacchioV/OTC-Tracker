# -*- coding: utf-8 -*-
"""O CARIMBO da semeadura da subida (`apps._seed_data_dir`, 21/09/2026).

A semeadura leva para os bancos o que vem versionado no repositorio, e e
IDEMPOTENTE: na segunda subida ela nao tem nada a fazer. So que "nao ter nada
a fazer" custava 177 aberturas de DuckDB, cada uma uma ida ao share -- 15
minutos de subida com o app sem atender, medidos na instancia do time em
21/09/2026, com o log em silencio porque cada abertura ficava abaixo do teto
de 5s do farol.

O carimbo e a impressao digital do que esta empacotado (caminho + mtime +
tamanho de cada arquivo). Igual ao gravado, a semeadura inteira e pulada.

O que este guarda prende, e por que cada um importa:

  1. a segunda subida nao abre banco NENHUM -- e a medida, nao o texto;
  2. arquivo empacotado que MUDA derruba o carimbo (senao a correcao de um
     cadastro no repositorio nunca chegaria ao banco);
  3. arquivo NOVO tambem derruba (o caso do template novo);
  4. o carimbo mora no `DATABASE_DIR`: apagar os bancos apaga o carimbo, e a
     semeadura volta. Guardado no disco local de cada maquina, quem apagasse
     o `db/` do share ficaria com o carimbo e o cadastro nao voltaria nunca;
  5. semeadura INCOMPLETA (banco ocupado pela instancia vizinha) NAO carimba
     -- carimbar ali congelaria a falta para sempre;
  6. `OTC_SEED_ALWAYS=1` forca.
"""
import io
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', '/tmp/otc-share')
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'
os.environ.pop('OTC_SEED_ALWAYS', None)

import duckdb                                                          # noqa: E402
import apps                                                            # noqa: E402
from apps.pages import data_paths                                      # noqa: E402

fails = []


def check(label, got, exp=True):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


# ── um DATA_DIR empacotado de mentira, e um destino separado ────────────────
tmp = tempfile.mkdtemp(prefix='otc-seed-')
pack = os.path.join(tmp, 'pack')
destino = os.path.join(tmp, 'dados')
os.makedirs(os.path.join(pack, 'mappings'))
os.makedirs(os.path.join(pack, 'translations'))


def escreve(rel, payload):
    caminho = os.path.join(pack, *rel.split('/'))
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with io.open(caminho, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh)
    return caminho


escreve('mappings/um.json', [{'A': '1'}])
escreve('mappings/dois.json', [{'B': '2'}])
escreve('RefData.json', [{'C': '3'}])
# `translations/` e codigo versionado, nao dado: a semeadura o COPIA e nao o
# importa. Entra aqui para o teste cobrir os dois ramos do laco.
with io.open(os.path.join(pack, 'translations', 'en.json'), 'w', encoding='utf-8') as fh:
    json.dump({'k': 'v'}, fh)

data_paths.PACKAGED_DIR = pack
apps.data_paths = data_paths


class FakeApp(object):
    """O minimo que `_seed_data_dir` le do app: `config` e `logger`."""

    class _Log(object):
        def __init__(self):
            self.linhas = []

        def _anota(self, msg, *a, **k):
            try:
                self.linhas.append(str(msg) % a if a else str(msg))
            except Exception:                                   # noqa: BLE001
                self.linhas.append(str(msg))

        info = warning = error = _anota

    def __init__(self, destino, db_dir):
        self.config = {'DATA_DIR': destino, 'DATABASE_DIR': db_dir}
        self.logger = self._Log()


db_dir = os.path.join(destino, 'db')
import apps.pages.data_store as _store                                 # noqa: E402
from apps.config import Config                                         # noqa: E402
Config.DATA_DIR = destino
Config.DATABASE_DIR = db_dir
_store.data_root = lambda: destino

aberturas = []
_connect = duckdb.connect
duckdb.connect = lambda *a, **k: (aberturas.append(a[0] if a else k.get('database')),
                                  _connect(*a, **k))[1]


def semeia():
    """Roda a semeadura e devolve (aberturas de banco, linhas de log)."""
    del aberturas[:]
    app = FakeApp(destino, db_dir)
    apps._seed_data_dir(app)
    return len(aberturas), app.logger.linhas


print('== 1. a PRIMEIRA subida semeia e abre bancos ==')
n1, log1 = semeia()
check('a primeira passada abre banco', n1 > 0, True)
check('e importou o que vem empacotado',
      any('importado' in l for l in log1), True)
stamp = os.path.join(db_dir, '_seed_stamp.txt')
check('o carimbo nasceu no DATABASE_DIR', os.path.isfile(stamp), True)
check('o cadastro chegou ao banco', _store.read(os.path.join(destino, 'mappings', 'um.json')),
      [{'A': '1'}])
check('e o que nao e JSON foi COPIADO',
      os.path.isfile(os.path.join(destino, 'translations', 'en.json')), True)

print('\n== 2. a SEGUNDA subida nao abre banco nenhum (a medida) ==')
n2, log2 = semeia()
check('zero aberturas de DuckDB', n2, 0)
check('e o log DIZ que pulou e como forcar',
      any('não mudou' in l and 'OTC_SEED_ALWAYS' in l for l in log2), True)

print('\n== 3. arquivo empacotado que MUDA derruba o carimbo ==')
# mtime distinto do anterior: em disco com resolucao de 1s, gravar duas vezes
# no mesmo segundo daria a MESMA digital e o teste passaria por engano.
caminho = escreve('mappings/um.json', [{'A': '9'}])
os.utime(caminho, (0, 0))
n3, _ = semeia()
check('volta a abrir banco', n3 > 0, True)
# E o valor do BANCO continua o de antes -- o carimbo nao afrouxa a regra do
# §434: a semeadura NUNCA sobrescreve, porque o que esta no banco e o que a
# mesa editou pela tela. Corrigir um cadastro no repositorio continua exigindo
# o script proprio (§488, `import_file_interpreter_template.py`). Isto esta
# aqui para que uma leitura futura do carimbo nao confunda "voltou a rodar"
# com "passou a sobrescrever".
check('mas o banco MANTEM o valor da mesa (a semeadura nunca sobrescreve)',
      _store.read(os.path.join(destino, 'mappings', 'um.json')), [{'A': '1'}])
check('carimbou de novo', os.path.isfile(stamp), True)
check('e a subida seguinte pula outra vez', semeia()[0], 0)

print('\n== 4. arquivo NOVO tambem derruba ==')
novo = escreve('mappings/tres.json', [{'D': '4'}])
os.utime(novo, (0, 0))
check('volta a abrir banco', semeia()[0] > 0, True)
check('e a seguinte pula', semeia()[0], 0)

print('\n== 5. o carimbo mora com os BANCOS ==')
check('o carimbo esta dentro do DATABASE_DIR',
      os.path.dirname(stamp), os.path.normpath(db_dir))
shutil.rmtree(db_dir)
check('apagar os bancos apaga o carimbo junto', os.path.isfile(stamp), False)
check('e a semeadura volta a rodar', semeia()[0] > 0, True)

print('\n== 6. semeadura INCOMPLETA nao carimba ==')
# Banco ocupado pela instancia vizinha: sem este ramo o carimbo congelaria a
# falta -- as subidas seguintes pulariam e o cadastro nunca entraria.
os.remove(stamp)
_isfile = _store.isfile
_um = os.path.join(destino, 'mappings', 'um.json')


def ocupado(path):
    if os.path.normpath(path) == os.path.normpath(_um):
        raise _store.BancoOcupado('mappings.db')
    return _isfile(path)


_store.isfile = ocupado
_n, log6 = semeia()
_store.isfile = _isfile
check('o ocupado foi reportado', any('ocupado por outra' in l for l in log6), True)
check('o log DIZ que a passada ficou incompleta',
      any('INCOMPLETA' in l for l in log6), True)
check('e NAO carimbou', os.path.isfile(stamp), False)
check('entao a subida seguinte tenta de novo', semeia()[0] > 0, True)

print('\n== 7. OTC_SEED_ALWAYS=1 forca ==')
# Aqui a pergunta e se a semeadura PULOU ou RODOU, e quem responde isso e o
# log -- nao a contagem de aberturas. Dentro de UM processo o cache de
# manifesto do armazem ja esta quente depois da primeira passada, entao uma
# passada que roda inteira pode nao abrir banco nenhum; e no RESTART, com o
# cache vazio, que as 177 aberturas acontecem.
check('carimbado apos a passada completa', os.path.isfile(stamp), True)
check('sem a variavel, PULA', any('não mudou' in l for l in semeia()[1]), True)
os.environ['OTC_SEED_ALWAYS'] = '1'
check('com a variavel, RODA mesmo carimbado',
      any('não mudou' in l for l in semeia()[1]), False)
os.environ.pop('OTC_SEED_ALWAYS')

duckdb.connect = _connect
shutil.rmtree(tmp, ignore_errors=True)
print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
