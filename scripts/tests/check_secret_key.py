# -*- coding: utf-8 -*-
"""Producao sem `SECRET_KEY` no ambiente sobe com uma chave POR MAQUINA.

A guarda que recusa subir sem `SECRET_KEY` existe para impedir a chave
ALEATORIA a cada restart -- com ela, todo cookie de sessao e invalidado na
subida e a pessoa e deslogada sem motivo aparente, um defeito que nao se parece
com configuracao faltando.

O que criava a chave, porem, era um passo do `start-otc-tracker.bat`, que mora
no share e nao esta no repositorio (HANDOFF §322: `%LOCALAPPDATA%\\OTC-Tracker`,
com o `secret_key.txt` e o `.snapshot` do requirements). Isso era invisivel
enquanto a mesa inteira usava UMA instancia; quando cada pessoa passou a rodar a
sua, virou um passo manual por MAQUINA -- e a maquina em que ele nao roda nao
sobe, com uma mensagem mandando definir a chave no `.env`, que e justamente o
unico lugar em que ela nao esta.

O app passou a manter o arquivo por conta propria. Isso NAO afrouxa a guarda:
ela quer estabilidade entre restarts, e um arquivo persistido e tao estavel
quanto o `.env`. O que se prende aqui:

  1. `SECRET_KEY` no ambiente VENCE -- e o jeito de varias maquinas
     compartilharem sessao, e o arquivo nao pode passar na frente;
  2. sem ela, producao SOBE, e a chave e a MESMA na subida seguinte (se nao
     fosse, o arquivo nao teria resolvido nada);
  3. o arquivo nasce 0600 onde o SO tem modo de arquivo: quem le a chave assina
     cookie em nome de qualquer pessoa;
  4. `OTC_SECRET_KEY_FILE` move o arquivo -- e o default NAO e o share nem o
     `%TEMP%`;
  5. caminho ingravavel volta a RECUSAR a subida, e a mensagem nomeia o arquivo
     que ele tentou (a antiga so falava do `.env`);
  6. DEBUG nao passa por nada disso.
"""
import io
import os
import stat
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')

import apps                                                # noqa: E402
from apps import create_app, _secret_key_file, _persisted_secret_key  # noqa: E402
from apps.config import Config, DebugConfig                # noqa: E402

fails = []


def check(rotulo, ok):
    print(('  ok  ' if ok else ' FAIL ') + rotulo)
    if not ok:
        fails.append(rotulo)


class Ambiente(object):
    """Troca variaveis de ambiente e devolve tudo no fim."""

    def __init__(self, **kv):
        self.kv, self.antes = kv, {}

    def __enter__(self):
        for k, v in self.kv.items():
            self.antes[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return self

    def __exit__(self, *a):
        for k, v in self.antes.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


TMP = tempfile.mkdtemp()
ARQ = os.path.join(TMP, 'estado', 'secret_key.txt')


print('== 1. a variavel de ambiente vence o arquivo ==')
# Ela e relida no `create_app`, e nao so no corpo do `Config`: la a leitura
# acontece no IMPORT, entao quem importasse `apps.config` antes do
# `load_dotenv()` do run.py congelava o fallback aleatorio COM a chave certa no
# `.env` ao lado -- app subindo sem erro e deslogando todo mundo a cada
# restart. Este teste importa o config bem antes de mexer no ambiente, entao ele
# vive exatamente essa ordem.
with Ambiente(SECRET_KEY='chave-explicita', DEBUG=None, OTC_SECRET_KEY_FILE=ARQ):
    app = create_app(Config)
    check('com SECRET_KEY no ambiente, ela e a chave da app',
          app.config['SECRET_KEY'] == 'chave-explicita')
    check('   e o arquivo nem chega a ser criado', not os.path.exists(ARQ))


print('\n== 2. sem ela, producao sobe -- e a chave PERSISTE ==')
with Ambiente(SECRET_KEY=None, DEBUG=None, OTC_SECRET_KEY_FILE=ARQ):
    app1 = create_app(Config)
    k1 = app1.config['SECRET_KEY']
    check('producao sobe sem SECRET_KEY no ambiente', bool(k1))
    check('   e o arquivo foi criado', os.path.exists(ARQ))
    # A razao de o arquivo existir: se a chave mudasse aqui, todo cookie de
    # sessao seria invalidado na subida — que e o defeito que a guarda impede.
    app2 = create_app(Config)
    check('a subida SEGUINTE reusa a mesma chave', app2.config['SECRET_KEY'] == k1)
    check('   e ela e a que esta no arquivo',
          io.open(ARQ, encoding='utf-8').read().strip() == k1)
    check('a chave tem tamanho de chave (token_hex(32))', len(k1) == 64)

    if os.name != 'nt':
        modo = stat.S_IMODE(os.stat(ARQ).st_mode)
        check('o arquivo nasce 0600 (quem le a chave forja sessao)', modo == 0o600)
    else:
        print('  --  modo de arquivo: pulado no Windows')


print('\n== 3. onde o arquivo mora por padrao ==')
with Ambiente(OTC_SECRET_KEY_FILE=None, LOCALAPPDATA=os.path.join(TMP, 'AppData')):
    padrao = _secret_key_file()
    check('o default fica sob %LOCALAPPDATA%\\OTC-Tracker',
          padrao == os.path.join(TMP, 'AppData', 'OTC-Tracker', 'secret_key.txt'))
# `%TEMP%` e alvo de Limpeza de Disco e de GPO: chave apagada desloga todo
# mundo, que e o oposto do que o arquivo existe para fazer.
with Ambiente(OTC_SECRET_KEY_FILE=None, LOCALAPPDATA=None):
    check('sem LOCALAPPDATA cai no HOME, nunca no TEMP',
          _secret_key_file().startswith(os.path.expanduser('~')))
check('e o caminho e absoluto, entao nao depende do cwd',
      os.path.isabs(_secret_key_file()))
with Ambiente(OTC_SECRET_KEY_FILE='relativo/chave.txt'):
    check('   inclusive um valor relativo em OTC_SECRET_KEY_FILE',
          os.path.isabs(_secret_key_file()))


print('\n== 4. quando nem o arquivo da, o app RECUSA subir ==')
# O ponto e a mensagem: a antiga mandava definir a chave no `.env`, que e o
# unico lugar em que ela nao estava. Sem nomear o arquivo, quem le o traceback
# nao tem por onde comecar.
ruim = os.path.join(TMP, 'nao-existe.txt')
_real = apps._persisted_secret_key
try:
    apps._persisted_secret_key = lambda: None
    with Ambiente(SECRET_KEY=None, DEBUG=None, OTC_SECRET_KEY_FILE=ruim):
        msg = ''
        try:
            create_app(Config)
        except RuntimeError as exc:
            msg = str(exc)
        check('sem chave e sem arquivo, levanta', bool(msg))
        check('   e a mensagem nomeia o arquivo tentado', ruim in msg)
        check('   e diz as duas saidas (.env e OTC_SECRET_KEY_FILE)',
              '.env' in msg and 'OTC_SECRET_KEY_FILE' in msg)
finally:
    apps._persisted_secret_key = _real

# O caminho ingravavel de verdade tambem devolve None, sem estourar: a decisao
# de recusar a subida e do create_app, nao deste helper.
with Ambiente(OTC_SECRET_KEY_FILE=os.path.join(os.devnull, 'x', 'chave.txt')):
    check('caminho ingravavel devolve None em vez de estourar',
          _persisted_secret_key() is None)


print('\n== 5. DEBUG nao passa por nada disso ==')
with Ambiente(SECRET_KEY=None, DEBUG=None, OTC_SECRET_KEY_FILE=os.path.join(TMP, 'debug.txt')):
    app = create_app(DebugConfig)
    check('DebugConfig sobe sem chave nenhuma', bool(app.config['SECRET_KEY']))
    check('   e sem criar arquivo', not os.path.exists(os.path.join(TMP, 'debug.txt')))
with Ambiente(SECRET_KEY=None, DEBUG='True', OTC_SECRET_KEY_FILE=os.path.join(TMP, 'debug2.txt')):
    # `DEBUG=True` no ambiente com o Config base: o modo documentado do run.py.
    create_app(Config)
    check('DEBUG=True no ambiente idem', not os.path.exists(os.path.join(TMP, 'debug2.txt')))

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
