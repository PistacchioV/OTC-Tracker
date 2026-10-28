"""Confere as fotos dos usuários no Stratos (§715): `stratos/envia_fotos.py`
leva, `stratos/src/fotos_stratos.py` serve.

  1. o envio: só imagem até 5 MB, o nome em MINÚSCULAS, em
     `otc-tracker/images/users/` (o drive é uma pasta local);
  2. o contêiner, num app Flask mínimo com o `user_photos` de verdade: a
     pessoa com foto no drive tem `url`, sem foto fica sem; o pedido em
     minúsculas acha a foto gravada em MAIÚSCULAS no drive; a do estático
     segue saindo do estático; arquivo que não há é 404;
  3. instalar duas vezes não soma o embrulho; sem raiz, não instala.

    python stratos/tests/check_fotos_stratos.py
"""
import os
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
STRATOS = os.path.dirname(AQUI)
RAIZ = os.path.dirname(STRATOS)
sys.path.insert(0, os.path.join(STRATOS, 'src'))
sys.path.insert(0, STRATOS)
sys.path.insert(0, RAIZ)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', tempfile.mkdtemp(prefix='share-root-'))

from flask import Flask                                           # noqa: E402

import envia_fotos as EF                                          # noqa: E402
import fotos_stratos as FS                                        # noqa: E402
import ponte_share as PS                                          # noqa: E402

FALHAS = []


def ok(cond, msg):
    print(('ok    ' if cond else 'FAIL  ') + msg)
    if not cond:
        FALHAS.append(msg)


def escreve(caminho, dado):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, 'wb') as fh:
        fh.write(dado)


print('== 1. o envio ==')
origem = tempfile.mkdtemp(prefix='fotos-')
escreve(os.path.join(origem, 'D566328.jpg'), b'JPG-D566328')
escreve(os.path.join(origem, 'E964956.png'), b'PNG-E964956')
escreve(os.path.join(origem, 'leia-me.txt'), b'x')
escreve(os.path.join(origem, 'Z000001.jpg'), b'0' * (EF.MAX_BYTES + 1))
drive = tempfile.mkdtemp(prefix='drive-')
n, fora = EF.envia(origem, PS.DriveLocal(drive))
dest = os.path.join(drive, 'otc-tracker', 'images', 'users')
ok(n == 2 and fora == 2, 'duas fotos sobem, o texto e a grande ficam (%d, %d)' % (n, fora))
ok(sorted(os.listdir(dest)) == ['d566328.jpg', 'e964956.png'], 'em minúsculas (%r)' % os.listdir(dest))

print('\n== 2. o contêiner ==')
from apps.pages.platform import user_photos as UP                 # noqa: E402
nomes_originais = UP._names
raiz = tempfile.mkdtemp(prefix='raiz-')
# no drive a foto com o nome da instância (MAIÚSCULAS); no estático, a do repo
escreve(os.path.join(FS.pasta(raiz), 'D566328.jpg'), b'JPG-DO-DRIVE')
estatico = tempfile.mkdtemp(prefix='static-')
escreve(os.path.join(estatico, 'images', 'users', 'e930179.jpg'), b'JPG-DO-REPO')
app = Flask('teste_fotos', static_folder=estatico, static_url_path='/static')
try:
    ok(FS.instala(app, raiz) is True, 'instala com raiz')
    embrulho = UP._names
    FS.instala(app, raiz)
    ok(UP._names is embrulho, 'instalar de novo não embrulha duas vezes')
    with app.app_context():
        ok(UP.url('d566328').endswith('/images/users/d566328.jpg'), 'quem tem foto no drive tem url')
        ok(UP.url('e930179') != '', 'a foto do estático continua valendo')
        ok(UP.url('x999999') == '', 'sem foto, sem url (as iniciais)')
    c = app.test_client()
    r = c.get('/static/images/users/d566328.jpg')
    ok(r.status_code == 200 and r.data == b'JPG-DO-DRIVE',
       'o pedido em minúsculas acha a foto em MAIÚSCULAS no drive (%s)' % r.status_code)
    r.close()
    r = c.get('/static/images/users/e930179.jpg')
    ok(r.status_code == 200 and r.data == b'JPG-DO-REPO', 'a do estático sai do estático')
    r.close()
    ok(c.get('/static/images/users/nao-existe.jpg').status_code == 404, 'o que não há é 404')
    ok(FS.instala(Flask('outro'), '') is False, 'sem raiz no drive, não instala')
finally:
    UP._names = nomes_originais

print('\n%d falha(s)' % len(FALHAS))
sys.exit(1 if FALHAS else 0)
