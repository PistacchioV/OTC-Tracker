"""Confere a CHEGADA dos bancos no Stratos (HANDOFF §681 passo C, §708):
`envia_dados.py` (máquina do JPM) → `pacotes_dados.py` + `/stratos/pacotes`
(contêiner) → o ponteiro lido na subida (`otc_stratos._dados_do_pacote`).

O drive é uma pasta local (`DriveLocal`, o mesmo contrato do cliente HTTP), e
os bancos são DuckDB de verdade:

  1. o envio: arquivo grande em PARTES, `envio.json` por último, retomada sem
     reenviar, pacote INCOMPLETO recusado, `.zip` recusado;
  2. a conferência: junta as partes, o DuckDB abre, sha256 trocado/arquivo
     faltando/duckdb mais novo recusam, envio pela metade não confere;
  3. ativar só o conferido; o ativo não se confere de novo; desativar;
  4. a subida: o ponteiro aponta OTC_DATA_DIR/OTC_DATABASE_DIR, a variável do
     ambiente vence, ponteiro para pacote não conferido é ignorado;
  5. a rota: só o master, a lista, o Check em fundo, o Activate.

    OTC_SHARED_DRIVE_ROOT=/tmp/otc-share python stratos/tests/check_pacotes_dados.py
"""
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
STRATOS = os.path.dirname(AQUI)
RAIZ = os.path.dirname(STRATOS)
sys.path.insert(0, RAIZ)
sys.path.insert(0, STRATOS)
sys.path.insert(0, os.path.join(STRATOS, 'src'))
os.chdir(RAIZ)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', tempfile.mkdtemp(prefix='share-root-'))
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

import duckdb                                               # noqa: E402
import envia_dados as E                                     # noqa: E402
import pacotes_dados as PD                                  # noqa: E402
import ponte_share as PS                                    # noqa: E402

FALHAS = []


def ok(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg)
    if not cond:
        FALHAS.append(msg)


def _sha(p):
    with open(p, 'rb') as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def pacote_falso(base, nome, completo=True, versao=None):
    """O que o exporta_dados.py monta: data/db/*.db + um anexo + manifest."""
    pac = os.path.join(base, nome)
    db = os.path.join(pac, 'data', 'db', 'cache', 'payrec.db')
    os.makedirs(os.path.dirname(db))
    con = duckdb.connect(db)
    con.execute('CREATE TABLE t AS SELECT range AS i, repeat(\'x\', 200) AS s FROM range(4000)')
    con.close()
    anexo = os.path.join(pac, 'data', 'tickets', 'a.png')
    os.makedirs(os.path.dirname(anexo))
    with open(anexo, 'wb') as fh:
        fh.write(b'\x89PNG' + os.urandom(3000))
    arquivos = [{'caminho': 'data/' + os.path.relpath(p, os.path.join(pac, 'data')).replace(os.sep, '/'),
                 'tipo': t, 'bytes': os.path.getsize(p), 'sha256': _sha(p)}
                for p, t in ((db, 'duckdb'), (anexo, 'arquivo'))]
    man = {'formato': 1, 'criado_em': '2026-10-27T18:00:00', 'duckdb': versao or duckdb.__version__,
           'completo': completo, 'arquivos': arquivos, 'pulados': [] if completo else
           [{'caminho': 'db/x.db', 'motivo': 'EM USO'}], 'erros': [], 'fora': []}
    with io.open(os.path.join(pac, 'manifest.json'), 'w', encoding='utf-8') as fh:
        json.dump(man, fh)
    return pac


class DriveContando(PS.DriveLocal):
    def __init__(self, raiz):
        PS.DriveLocal.__init__(self, raiz)
        self.salvos = []

    def save(self, caminho, fh):
        self.salvos.append(caminho)
        PS.DriveLocal.save(self, caminho, fh)


tmp = tempfile.mkdtemp(prefix='pacotes-')
try:
    local = os.path.join(tmp, 'exporta')
    drive_raiz = os.path.join(tmp, 'drive')
    raiz = os.path.join(drive_raiz, 'otc-tracker')           # o OTC_STRATOS_ROOT do contêiner
    os.makedirs(local)

    print('== 1. o envio ==')
    pac = pacote_falso(local, 'otc-dados-20261027-180000')
    tam_db = os.path.getsize(os.path.join(pac, 'data', 'db', 'cache', 'payrec.db'))
    parte_mb = (tam_db / 3.0 + 1) / 1048576.0                # o banco vai em 3 partes
    d = DriveContando(drive_raiz)
    destino = E.envia(pac, d, 'otc-tracker', parte_mb)
    ok(destino == 'otc-tracker/pacotes/otc-dados-20261027-180000', 'o destino no drive: %s' % destino)
    partes = [s for s in d.salvos if '.parte-' in s]
    ok(len(partes) == 3, 'o banco grande foi em 3 partes (%d)' % len(partes))
    ok(d.salvos[-1].endswith('/envio.json') and d.salvos[-2].endswith('/manifest.json'),
       'manifest e envio.json por último')
    ok(PD.lista(raiz)[0]['estado'] == 'recebido', 'o contêiner vê o pacote recebido')
    d2 = DriveContando(drive_raiz)
    E.envia(pac, d2, 'otc-tracker', parte_mb)
    ok([s.rsplit('/', 1)[1] for s in d2.salvos] == ['manifest.json', 'envio.json'],
       'rodar de novo não reenvia o que já subiu')
    inc = pacote_falso(local, 'otc-dados-20261027-190000', completo=False)
    try:
        E.envia(inc, DriveContando(drive_raiz), 'otc-tracker')
        ok(False, 'pacote INCOMPLETO recusado')
    except RuntimeError as e:
        ok('INCOMPLETO' in str(e), 'pacote INCOMPLETO recusado')
    try:
        E.main([pac + '.zip', '--drive-local', drive_raiz])
        ok(False, 'o .zip é recusado')
    except SystemExit as e:
        ok(e.code == 2, 'o .zip é recusado (passe a pasta)')

    print('\n== 2. a conferência ==')
    nome = 'otc-dados-20261027-180000'
    conf = PD.confere(raiz, nome, duckdb_aqui=duckdb.__version__)
    ok(conf['ok'] and not conf['erros'], 'confere: ok (%r)' % conf['erros'])
    alvo = os.path.join(raiz, 'pacotes', nome, 'data', 'db', 'cache', 'payrec.db')
    ok(os.path.isfile(alvo) and not [n for n in os.listdir(os.path.dirname(alvo)) if '.parte-' in n],
       'as partes viraram o arquivo e sumiram')
    c = duckdb.connect(alvo, read_only=True)
    ok(c.execute('SELECT count(*) FROM t').fetchone()[0] == 4000, 'o banco juntado abre')
    c.close()
    ok(PD.confere(raiz, nome, duckdb_aqui=duckdb.__version__)['ok'], 'conferir de novo (partes já juntadas): ok')
    # sha trocado e arquivo faltando
    ruim = 'otc-dados-20261027-200000'
    E.envia(pacote_falso(local, ruim), PS.DriveLocal(drive_raiz), 'otc-tracker', 0)
    png = os.path.join(raiz, 'pacotes', ruim, 'data', 'tickets', 'a.png')
    with open(png, 'r+b') as fh:
        fh.seek(10)
        fh.write(b'\x00\x01')
    os.remove(os.path.join(raiz, 'pacotes', ruim, 'data', 'db', 'cache', 'payrec.db'))
    conf = PD.confere(raiz, ruim)
    ok(not conf['ok'] and any('sha256' in e for e in conf['erros']) and any('não chegou' in e for e in conf['erros']),
       'sha trocado e arquivo faltando recusam (%r)' % conf['erros'])
    ok(PD.estado(raiz, ruim)['estado'] == 'recusado', 'estado: recusado')
    novo = 'otc-dados-20261027-210000'
    E.envia(pacote_falso(local, novo, versao='9.0.0'), PS.DriveLocal(drive_raiz), 'otc-tracker', 0)
    conf = PD.confere(raiz, novo, duckdb_aqui=duckdb.__version__)
    ok(not conf['ok'] and any('mais novo' in e for e in conf['erros']), 'duckdb mais novo que o do contêiner recusa')
    meio = os.path.join(raiz, 'pacotes', 'otc-dados-20261027-220000')
    os.makedirs(meio)
    shutil.copy(os.path.join(pac, 'manifest.json'), meio)
    try:
        PD.confere(raiz, 'otc-dados-20261027-220000')
        ok(False, 'envio pela metade não confere')
    except PD.PacoteInvalido as e:
        ok(e.code == 'upload_unfinished', 'envio pela metade não confere (sem envio.json)')
    ok(PD.estado(raiz, 'otc-dados-20261027-220000')['estado'] == 'enviando', 'estado: enviando')
    try:
        PD.estado(raiz, '../fora')
        ok(False, 'nome com caminho recusado')
    except PD.PacoteInvalido:
        ok(True, 'nome com caminho recusado')

    print('\n== 3. ativar ==')
    try:
        PD.ativa(raiz, ruim)
        ok(False, 'recusado não ativa')
    except PD.PacoteInvalido as e:
        ok(e.code == 'not_checked', 'recusado não ativa')
    PD.ativa(raiz, nome)
    ok(PD.ativo(raiz) == nome and PD.estado(raiz, nome)['ativo'], 'o ponteiro aponta o pacote')
    try:
        PD.confere(raiz, nome)
        ok(False, 'o ativo não se confere de novo')
    except PD.PacoteInvalido as e:
        ok(e.code == 'package_active', 'o ativo não se confere de novo')

    print('\n== 4. a subida ==')
    import otc_stratos as O
    for k in ('OTC_DATA_DIR', 'OTC_DATABASE_DIR'):
        os.environ.pop(k, None)
    data = O._dados_do_pacote(raiz)
    esperado = os.path.join(raiz, 'pacotes', nome, 'data')
    ok(data == esperado and os.environ.get('OTC_DATA_DIR') == esperado
       and os.environ.get('OTC_DATABASE_DIR') == os.path.join(esperado, 'db'),
       'o ponteiro vira OTC_DATA_DIR e OTC_DATABASE_DIR')
    os.environ['OTC_DATA_DIR'] = '/outro'
    os.environ.pop('OTC_DATABASE_DIR', None)
    ok(O._dados_do_pacote(raiz) is None and os.environ['OTC_DATA_DIR'] == '/outro', 'a variável do ambiente vence')
    os.environ.pop('OTC_DATA_DIR', None)
    with open(os.path.join(raiz, PD.PONTEIRO), 'w') as fh:
        fh.write(ruim)
    ok(O._dados_do_pacote(raiz) is None and 'OTC_DATA_DIR' not in os.environ,
       'ponteiro para pacote recusado é ignorado (fica em <raiz>/data)')
    PD.desativa(raiz)
    ok(PD.ativo(raiz) == '' and O._dados_do_pacote(raiz) is None, 'desativar: sem ponteiro')

    print('\n== 5. a rota ==')
    from flask import Flask
    app = Flask('t')
    app.config['DATA_DIR'] = os.path.join(raiz, 'data')

    class U(object):
        authorized = True

        def __init__(self, sid):
            self.sid = sid

    class Auth(object):
        sid = 'E930179'

        def user(self):
            return U(self.sid)
    auth = Auth()
    os.environ['OTC_STRATOS_ROOT'] = raiz
    O._rota_pacotes(app, auth)
    cl = app.test_client()
    auth.sid = 'A111111'
    ok(cl.get('/stratos/pacotes').status_code == 403, 'só o master')
    auth.sid = 'E930179'
    j = cl.get('/stratos/pacotes?format=json').get_json()
    ok(j['success'] and {p['nome'] for p in j['pacotes']} >= {nome, ruim}, 'a lista em JSON')
    r = cl.get('/stratos/pacotes')
    ok(r.status_code == 200 and b'Activate' in r.data and nome.encode() in r.data, 'a página com os botões')
    novo2 = 'otc-dados-20261027-230000'
    E.envia(pacote_falso(local, novo2), PS.DriveLocal(drive_raiz), 'otc-tracker', 0)
    r = cl.post('/stratos/pacotes?format=json', data={'acao': 'conferir', 'nome': novo2})
    ok(r.status_code == 200, 'Check começa em fundo')
    for _ in range(100):
        if PD.estado(raiz, novo2)['estado'] == 'conferido':
            break
        time.sleep(0.05)
    ok(PD.estado(raiz, novo2)['estado'] == 'conferido', 'e termina conferido')
    r = cl.post('/stratos/pacotes?format=json', data={'acao': 'ativar', 'nome': ruim})
    ok(r.status_code == 409 and r.get_json()['code'] == 'not_checked', 'Activate de recusado: 409')
    r = cl.post('/stratos/pacotes?format=json', data={'acao': 'ativar', 'nome': novo2})
    ok(r.status_code == 200 and PD.ativo(raiz) == novo2, 'Activate grava o ponteiro')
    r = cl.get('/stratos/pacotes')
    ok(b'restart to switch' in r.data, 'a página diz que falta o restart')
    r = cl.post('/stratos/pacotes?format=json', data={'acao': 'desativar', 'nome': ''})
    ok(r.status_code == 200 and PD.ativo(raiz) == '', 'Deactivate apaga o ponteiro')
finally:
    os.environ.pop('OTC_STRATOS_ROOT', None)
    shutil.rmtree(tmp, ignore_errors=True)

print('\n%d falha(s)' % len(FALHAS))
sys.exit(1 if FALHAS else 0)
