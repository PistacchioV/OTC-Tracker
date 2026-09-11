# -*- coding: utf-8 -*-
"""check_ted_release.py — o e-mail de liberação de TED do NDF (HANDOFF §451).

Dois defeitos vistos no e-mail de 11/09/2026:

  1. "SSI não localizada" para a JOHNSON & JOHNSON com o arquivo salvo no
     Electronic Inventory: a busca olhava UMA pasta (a vencedora do scan) e o
     share tem pastas GÊMEAS da mesma contraparte ('S.A' × 'SA'), com a SSI na
     outra. Agora olha em todas (`_ei_client_dir_names`) e pega a mais nova;
  2. 'BANCO J.P MORGAN S.A' (sem o segundo ponto) e 'TW NDF BJPM' entravam
     na lista como contraparte: o `_is_jpmorgan` comparava grafias fixas. Só
     contraparte CORPORATE recebe TED — a perna interna (Banco, Lawton, MGT,
     fundos como Atacama, books) sai pela MESMA pergunta do aviso de
     liquidação (`_ops_is_internal_cpty`: le-spn + ECONOMIC GROUP = INTERNAL),
     e o `_is_jpmorgan` ficou cego a pontuação e conhece a sigla BJPM.

Nada sai da máquina: SMTP e as fontes são stubs, o EI é um tmp.
"""
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

falhas = []


def check(rotulo, obtido, esperado):
    ok = obtido == esperado
    print(('  ok  ' if ok else ' FAIL ') + rotulo +
          ('' if ok else '\n        got=%r\n        exp=%r' % (obtido, esperado)))
    if not ok:
        falhas.append(rotulo)


from apps.pages import routes as R                                    # noqa: E402
from apps.pages import otc_emails                                     # noqa: E402
from apps.pages.platform import electronic_inventory as EI            # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
print('== 1. a grafia da entidade nossa ==')
for nome, esperado in (('BANCO J.P MORGAN S.A', True), ('Bco J.P. Morgan S.A.', True),
                       ('JPMORGAN CHASE BANK', True), ('JP MORGAN', True), ('TW NDF BJPM', True),
                       ('BANCO BRADESCO S.A', False), ('JOHNSON & JOHNSON DO BRASIL', False)):
    check('_is_jpmorgan(%r) = %s' % (nome, esperado), otc_emails._is_jpmorgan(nome), esperado)

# ─────────────────────────────────────────────────────────────────────────────
print('== 2. a SSI nas pastas gêmeas do Electronic Inventory ==')
tmp = tempfile.mkdtemp(prefix='ted-ei-')
JJ = 'JOHNSON & JOHNSON DO BRASIL INDUSTRIA E COMERCIO DE PRODUTOS PARA SAUDE LTDA'
raiz_real = R.ELECTRONIC_INVENTORY_ROOT
cache_real = dict(EI._EI_ROOT_CACHE)
try:
    R.ELECTRONIC_INVENTORY_ROOT = tmp
    EI._EI_ROOT_CACHE.update({'complete': False, 'scanning': False, 'dirs': {}, 'multi': {}})
    # a gêmea: mesmo nome com 'LTDA.' e espaço duplo — a que o scan não elege
    g1 = os.path.join(tmp, JJ)
    g2 = os.path.join(tmp, JJ.replace('LTDA', 'LTDA.').replace('SAUDE', 'SAUDE '))
    os.makedirs(os.path.join(g1, 'SSI'))
    os.makedirs(os.path.join(g2, 'SSI'))
    os.makedirs(os.path.join(tmp, 'CARGILL ALIMENTOS LTDA', 'SSI'))
    check('sem arquivo em nenhuma: None', R._ted_ssi_attachment(JJ), None)
    velho = os.path.join(g2, 'SSI', 'SSI - JJ - 01012026.pdf')
    open(velho, 'wb').write(b'x')
    os.utime(velho, (time.time() - 3600, time.time() - 3600))
    check('a SSI na GÊMEA é achada', R._ted_ssi_attachment(JJ), velho)
    novo = os.path.join(g1, 'SSI', 'SSI - JJ - 11092026.pdf')
    open(novo, 'wb').write(b'y')
    check('com as duas, vence a mais nova (de qualquer pasta)', R._ted_ssi_attachment(JJ), novo)
    check('contraparte sem pasta: None', R._ted_ssi_attachment('ZZZ SEM PASTA'), None)
    check('a pasta existe, a SSI não: None', R._ted_ssi_attachment('CARGILL ALIMENTOS LTDA'), None)
finally:
    R.ELECTRONIC_INVENTORY_ROOT = raiz_real
    EI._EI_ROOT_CACHE.clear()
    EI._EI_ROOT_CACHE.update(cache_real)
    shutil.rmtree(tmp, ignore_errors=True)

# ─────────────────────────────────────────────────────────────────────────────
print('== 3. o endpoint: só contraparte corporate entra ==')
from apps import create_app                                            # noqa: E402
from apps.config import DebugConfig                                    # noqa: E402

enviados = {}


class _FakeSMTP:
    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def sendmail(self, frm, to, body):
        enviados['to'] = list(to)
        enviados['body'] = body

    def send_message(self, msg, *a, **k):
        enviados['to'] = [x.strip() for x in str(msg['To']).split(',')]
        enviados['body'] = msg.as_string()

    def quit(self):
        pass


def trade(cpty, spn, legal='Bco J.P. Morgan S.A.', settlement=-1000.0):
    return {'counterparty': cpty, 'spn': spn, 'legal': legal, 'settlement': settlement,
            'tax': 0.0, 'net_type': 'Total Net'}


TRADES = [trade('CARGILL ALIMENTOS LTDA', '10'),
          trade('BANCO J.P MORGAN S.A', '20', legal='JPMORGAN CHASE BANK'),
          trade('TW NDF BJPM', '30', legal='JPMORGAN CHASE BANK'),
          trade('ATACAMA FUNDO DE INVESTIMENTO MULTIMERCADO', '40', legal='JPMORGAN CHASE BANK'),
          trade('LAWTON CAPITAL', '50'),
          trade('BANCO BRADESCO S.A', '60')]
INTERNOS = {'40'}                         # o fundo é INTERNAL no Reference Data / le-spn

real = (R.smtplib.SMTP, R._ndfsum_collect, R._cpd_load, R._cpd_find, R._bank_norm,
        R._ndfsum_account_fmt, R._ted_ssi_attachment, R._ops_is_internal_cpty)
try:
    R.smtplib.SMTP = _FakeSMTP
    R._ndfsum_collect = lambda ref: {'email_trades': TRADES}
    R._cpd_load = lambda: []
    R._cpd_find = lambda cpd, spn: {'BANKING': {}}
    R._bank_norm = lambda b: b
    R._ndfsum_account_fmt = lambda banking, side: 'BCO: 341 | AG: 1 | CC: 2'
    R._ted_ssi_attachment = lambda n: None
    R._ops_is_internal_cpty = lambda name, spn='': spn in INTERNOS
    app = create_app(DebugConfig)
    cl = app.test_client()
    with cl.session_transaction() as s:
        s['authenticated'] = True
        s['user_sid'] = 'T000000'
        s['user_name'] = 'T'
        s['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()
    res = cl.post('/api/ndf-summary/ted-email', json={'date': '2026-09-11'}).get_json()
    check('o endpoint respondeu', res.get('ok'), True)
    check('só as duas corporate entram (Cargill e Bradesco)', res.get('count'), 2)
    check('e só elas ficam sem SSI', sorted(res.get('missing_ssi') or []),
          ['BANCO BRADESCO S.A', 'CARGILL ALIMENTOS LTDA'])
    body = enviados.get('body', '')
    for nome in ('TW NDF BJPM', 'ATACAMA', 'LAWTON', 'J.P MORGAN S.A'):
        check('%s fora do e-mail' % nome, nome in body.replace('=\n', ''), False)
finally:
    (R.smtplib.SMTP, R._ndfsum_collect, R._cpd_load, R._cpd_find, R._bank_norm,
     R._ndfsum_account_fmt, R._ted_ssi_attachment, R._ops_is_internal_cpty) = real

print()
print('FALHAS: %d' % len(falhas) if falhas else 'tudo ok')
sys.exit(1 if falhas else 0)
