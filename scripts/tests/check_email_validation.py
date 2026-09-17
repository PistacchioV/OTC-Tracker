# -*- coding: utf-8 -*-
"""check_email_validation.py — o Email Validation do Swap VCP e do NDF Other
Publisher (`platform/email_validation.py`).

O que se prende, e por que cada coisa nao daria erro sozinha:

  1. o CENARIO sai da CONTA, pelo `b3-accounts`: guarda-chuva (CLIENT 1/2) e
     cliente e nao pede validacao; conta PROPRIA de terceiro e IF (so a
     tabela); Lawton/Atacama numa das pontas e IF + fundo (tabela + anexo).
     Conta em branco NAO e IF. Decidido pelo nome, um "BANCO LAWTON SA"
     cliente viraria fundo;
  2. o SWAP VCP: so as linhas de IF vao no e-mail; o anexo e o arquivo da
     visao do FUNDO (VCP_LAWTON.TXT), pelo gerador do Send, e NUNCA o do
     Banco; nada e escrito no Batch Conecta (pedir validacao nao e enviar) e
     o status nao muda; linha de IF sem fator recusa o pedido; pagina so de
     cliente devolve `no_if_rows`;
  3. o OTHER PUBLISHER: mesma logica — IF so tabela, Lawton com o
     TAXA_LAWTON.txt (Participante e C.Parte trocados); sem TX PARIDADE
     recusa; o payload da tela traz `validation` por id;
  4. os avisos saem ESTRUTURADOS ({code, params}) — a tela diz pelo _TRANS — e
     os dois templates de tela conhecem todo codigo que o servidor manda.

Nada sai da maquina: o SMTP e um espiao e o Batch Conecta e um tmp.
"""
import os
import re
import shutil
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


from apps.pages import routes as R                                          # noqa: E402
from apps.pages.platform import email_validation as EV                      # noqa: E402
from apps.pages.features.other_products import queries as VQ               # noqa: E402

REF = datetime(2026, 9, 8)
TMP = tempfile.mkdtemp(prefix='email-val-')

_SEED = [dict(s) for s in R._MAPPING_DEFS['b3-accounts']['seed']]
_real = (R._mapping_rows, R._create_notification, R.CONECTA_NEW_PATH, EV.send_email,
         VQ.vcp_factor_rows, R._ndfop_collect)
R._mapping_rows = lambda key: [dict(s) for s in _SEED] if key == 'b3-accounts' else _real[0](key)
R.CONECTA_NEW_PATH = os.path.join(TMP, 'conecta')
_notifs, _mails, _sent = [], [], threading.Event()
R._create_notification = lambda *a, **k: _notifs.append(a)


def _spy(subject, html, logo_path, attachments, tag=''):
    _mails.append({'subject': subject, 'html': html, 'attachments': attachments, 'tag': tag})
    _sent.set()
    return True


EV.send_email = _spy


def _last_mail():
    _sent.wait(5)
    _sent.clear()
    return _mails[-1] if _mails else {}


def _f(contrato, conta_c, **kw):
    f = {'contrato': contrato, 'internal_id': 'K' + contrato[:3], 'contraparte': 'CPTY ' + contrato[:3],
         'conta_p': '73760.00-9', 'conta_c': conta_c, 'idx_p': 'DI', 'idx_c': 'VCP', 'lob': 'CEM',
         'vbr': 1000000.0, 'vcp_p': False, 'vcp_c': True, 'fator_p': None, 'fator_c': 1.0119,
         'interno': 5000.0, 'vcp_liq': 5000.0, 'diferenca': 0.0, 'status': 'New', 'maker': ''}
    f.update(kw)
    f['validation'] = EV.scenario(f['conta_p'], f['conta_c'])
    return f


try:
    # ── 1. o cenario ────────────────────────────────────────────────────────
    print('== 1. o cenario sai da conta ==')
    check('guarda-chuva CLIENT 1 e cliente', EV.scenario('73760.00-9', '73760.10-2')['scenario'], '')
    check('guarda-chuva CLIENT 2, so digitos', EV.scenario('73760009', '73760205')['scenario'], '')
    check('conta propria de terceiro e IF', EV.scenario('73760.00-9', '12345.00-1'),
          {'scenario': 'if', 'funds': []})
    check('Lawton na contraparte e IF + fundo', EV.scenario('73760.00-9', '00041.00-7'),
          {'scenario': 'if_fund', 'funds': ['LAWTON']})
    check('Atacama na PARTE tambem', EV.scenario('85398.00-5', '12345.00-1'),
          {'scenario': 'if_fund', 'funds': ['ATACAMA']})
    check('as duas pontas de fundo', EV.scenario('00041.00-7', '85398.00-5')['funds'], ['ATACAMA', 'LAWTON'])
    check('conta em branco NAO e IF', EV.scenario('73760.00-9', '')['scenario'], '')
    _SEED_BAK = list(_SEED)
    del _SEED[:]
    check('sem cadastro o prefixo do pu_fator segura o fundo', EV.fund_of('00041.00-7'), 'LAWTON')
    _SEED.extend(_SEED_BAK)
    # O Live Position de NDF entrega a conta do Lawton SEM os zeros (`41007`):
    # comparada como veio, nao casa com o cadastro nem com o prefixo, e a linha
    # do fundo saia como IF comum — sem o anexo, e sem erro nenhum.
    check('conta sem os zeros a esquerda (41007) e o Lawton', EV.scenario('73760.00-9', '41007'),
          {'scenario': 'if_fund', 'funds': ['LAWTON']})
    del _SEED[:]
    check('   e tambem pelo prefixo, sem cadastro', EV.fund_of('41007'), 'LAWTON')
    _SEED.extend(_SEED_BAK)
    check('rotulo do e-mail', [EV.scenario_label(EV.scenario('73760.00-9', c))
                               for c in ('12345.00-1', '00041.00-7', '73760.10-2')],
          ['IF', 'IF + LAWTON', ''])

    # ── 1b. o envelope: de otc.tracker para brazil.otc.ops, e so ────────────
    # O espiao de baixo troca o `send_email` inteiro; aqui roda o de VERDADE
    # contra um SMTP falso, que e onde remetente e destinatario sao decididos.
    print('== 1b. o envelope ==')
    import smtplib
    from email import message_from_string
    _env = {}

    class _FakeSMTP(object):
        def __init__(self, host, port, timeout=None):
            _env['host'] = (host, port)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def sendmail(self, frm, to, raw):
            _env.update(frm=frm, to=list(to), msg=message_from_string(raw))

    _smtp_real = smtplib.SMTP
    smtplib.SMTP = _FakeSMTP
    try:
        ok = _real[3]('Swap VCP - 08/09/2026 - Validation', '<p>x</p>', None,
                      [('VCP_LAWTON.TXT', b'linha')], tag='t')
    finally:
        smtplib.SMTP = _smtp_real
    check('envio ok pelo relay da casa', (ok, _env['host']), (True, ('mailhost.jpmchase.net', 25)))
    check('DE otc.tracker PARA brazil.otc.ops — envelope e cabecalho',
          (_env['frm'], _env['to'], _env['msg']['From'], _env['msg']['To']),
          ('otc.tracker@jpmorgan.com', ['brazil.otc.ops@jpmorgan.com'],
           'otc.tracker@jpmorgan.com', 'brazil.otc.ops@jpmorgan.com'))
    check('   sem Cc nem Bcc', (_env['msg']['Cc'], _env['msg']['Bcc']), (None, None))
    check('   e o anexo vai junto', [p.get_filename() for p in _env['msg'].walk() if p.get_filename()],
          ['VCP_LAWTON.TXT'])

    from apps import create_app
    from apps.config import DebugConfig
    app = create_app(DebugConfig); app.config['TESTING'] = True
    cl = app.test_client()
    with cl.session_transaction() as s:
        s['authenticated'] = True; s['user_sid'] = 'E3'; s['user_name'] = 'Tester'
        s['user_email'] = 'tester@jpmorgan.com'
        s['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()

    # ── 2. Swap VCP ─────────────────────────────────────────────────────────
    print('== 2. Swap VCP ==')
    FACT = [_f('21C00035804', '73760.10-2'),                 # cliente
            _f('24H02170822', '12345.00-1'),                 # IF
            _f('26B00099001', '00041.00-7')]                 # IF + Lawton
    VQ.vcp_factor_rows = lambda ref, rows=None, ci=None: [dict(f) for f in FACT]
    URL = '/api/other-products-swap-vcp/email-validation'
    r = cl.post(URL, json={'date': '2026-09-08'})
    b = r.get_json()
    check('pagina inteira: so as duas de IF vao', (r.status_code, b['contracts'], b['skipped']),
          (200, ['24H02170822', '26B00099001'], 1))
    check('   a de fundo e a unica com anexo', (b['with_fund'], b['attached']), (['26B00099001'], ['VCP_LAWTON.TXT']))
    m = _last_mail()
    check('   assunto', (m['subject'], m['tag']), ('Swap VCP - 08/09/2026 - Validation', 'swap-vcp'))
    check('   a tabela traz as duas de IF e NAO a de cliente',
          ['24H02170822' in m['html'], '26B00099001' in m['html'], '21C00035804' in m['html']], [True, True, False])
    check('   com o cenario por linha e o fator na 8a casa',
          ['>IF<' in re.sub(r'\s+', '', m['html']), 'IF + LAWTON' in m['html'], '1.01190000' in m['html']],
          [True, True, True])
    check('   e o aviso do fundo com o anexo citado', ['Internal fund on one side (LAWTON)' in m['html'],
                                                       'VCP_LAWTON.TXT' in m['html']], [True, True])
    nome, dados = m['attachments'][0]
    linhas = dados.decode('utf-8').split('\n')
    check('   anexo: header do LAWTON + 1 registro, nunca a visao do Banco',
          (nome, len(linhas), 'INTRAGLAWTONFDO' in linhas[0], 'JPMORGANBM' in dados.decode('utf-8')),
          ('VCP_LAWTON.TXT', 2, True, False))
    check('   o registro leva o contrato e o fator 2+8', ['26B00099001' in linhas[1], '0101190000' in linhas[1]],
          [True, True])
    check('   NADA foi para o Batch Conecta', os.path.isdir(R.CONECTA_NEW_PATH) and os.listdir(R.CONECTA_NEW_PATH), False)
    check('   aviso no sino com o rotulo da pagina', (_notifs[-1][2], _notifs[-1][3]), ('VCP Validation Requested', 'Swap VCP'))

    r = cl.post(URL, json={'date': '2026-09-08', 'contracts': ['24H02170822']})
    b = r.get_json()
    m = _last_mail()
    check('so IF: sem anexo e sem aviso de fundo', (b['attached'], m['attachments'], 'Internal fund' in m['html']),
          ([], [], False))
    r = cl.post(URL, json={'date': '2026-09-08', 'contracts': ['21C00035804']})
    check('so cliente: no_if_rows, estruturado', (r.status_code, r.get_json()['code'], r.get_json()['params']),
          (400, 'no_if_rows', {'n': 1}))
    FACT[1]['fator_c'] = None
    n_mails = len(_mails)
    r = cl.post(URL, json={'date': '2026-09-08'})
    check('IF sem fator recusa o pedido inteiro', (r.status_code, r.get_json()['code'], r.get_json()['problems'],
                                                   len(_mails) - n_mails),
          (400, 'blocked', ['24H02170822: Contraparte factor missing'], 0))
    FACT[1]['fator_c'] = 1.0119
    del FACT[:]
    r = cl.post(URL, json={'date': '2026-09-08'})
    check('pagina vazia: no_rows', (r.status_code, r.get_json()['code']), (400, 'no_rows'))

    # ── 3. NDF Other Publisher ──────────────────────────────────────────────
    print('== 3. NDF Other Publisher ==')

    def _row(cli, b3, conta_c, tx='5.12345678'):
        return [cli, b3, 'ATH-' + b3, 'CNH', tx, 'BRL', '1.00000000', '73760.00-9', conta_c, 'New', '', '', b3]

    ROWS = [_row('CLIENTE SA', 'B3CLI', '73760.20-5'), _row('BANCO XPTO', 'B3IF', '12345.00-1'),
            _row('LAWTON', 'B3LAW', '41007')]
    R._ndfop_collect = lambda ref: {'widgets': {'total': len(ROWS)}, 'columns': list(R._NDFOP_COLUMNS),
                                    'rows': [list(x) for x in ROWS], 'updated': ''}
    d = cl.get('/api/ndf-other-publisher/data?date=2026-09-08').get_json()
    check('GET data traz validation por id',
          {k: v['scenario'] for k, v in d['validation'].items()}, {'B3CLI': '', 'B3IF': 'if', 'B3LAW': 'if_fund'})
    URL = '/api/ndf-other-publisher/email-validation'
    r = cl.post(URL, json={'date': '2026-09-08'})
    b = r.get_json()
    check('pagina inteira: IF e Lawton vao, cliente fica', (r.status_code, b['ids'], b['skipped'], b['attached'], b['warnings']),
          (200, ['B3IF', 'B3LAW'], 1, ['TAXA_LAWTON.txt'], []))
    m = _last_mail()
    check('   assunto e a tabela com as colunas da pagina',
          (m['subject'], all(c in m['html'] for c in R._NDFOP_COLUMNS), 'B3CLI' in m['html']),
          ('NDF Other Publisher - 08/09/2026 - Validation', True, False))
    nome, dados = m['attachments'][0]
    linhas = dados.decode('utf-8').split('\n')
    check('   anexo: so a linha do Lawton, na visao DELE (Participante = 00041007)',
          (nome, len(linhas), 'INTRAGLAWTONFDO' in linhas[0], 'B3LAW' in linhas[1], 'B3IF' in dados.decode('utf-8'),
           linhas[1].index('00041007') < linhas[1].index('73760009')),
          ('TAXA_LAWTON.txt', 2, True, True, False, True))
    check('   NADA foi para o Batch Conecta', os.path.isdir(R.CONECTA_NEW_PATH) and os.listdir(R.CONECTA_NEW_PATH), False)
    ROWS[1][4] = '-'
    r = cl.post(URL, json={'date': '2026-09-08', 'ids': ['B3IF']})
    check('sem TX PARIDADE recusa, estruturado', (r.status_code, r.get_json()['code'], r.get_json()['params']),
          (400, 'rate_missing', {'ids': 'B3IF'}))
    r = cl.post(URL, json={'date': '2026-09-08', 'ids': ['B3CLI']})
    check('so cliente: no_if_rows', (r.status_code, r.get_json()['code']), (400, 'no_if_rows'))
    ROWS[2][8] = '85398.00-5'
    r = cl.post(URL, json={'date': '2026-09-08', 'ids': ['B3LAW']})
    b = r.get_json()
    check('fundo sem gerador nesta pagina (Atacama): vai sem anexo, AVISANDO',
          (r.status_code, b['attached'], [w['code'] for w in b['warnings']], b['warnings'][0]['params']),
          (200, [], ['fund_without_file'], {'ids': 'B3LAW'}))
    check('   e o e-mail nao promete anexo que nao tem',
          'No fund view file could be generated' in _last_mail()['html'], True)

    # ── 4. a tela conhece todo codigo que o servidor manda ──────────────────
    print('== 4. os codigos na tela ==')

    def _codes(path):
        src = open(os.path.join(ROOT, path), encoding='utf-8').read()
        return set(re.findall(r"'code': '(\w+)'", src))

    vcp_html = open(os.path.join(ROOT, 'apps/templates/pages/other-products-swap-vcp.html'), encoding='utf-8').read()
    nop_js = open(os.path.join(ROOT, 'apps/static/js/pages/ndf-other-publisher.js'), encoding='utf-8').read()
    cod_vcp = _codes('apps/pages/features/other_products/commands.py') | {'fi_template'}
    cod_nop = _codes('apps/pages/features/ndf_other_publisher/commands.py') | {'fi_template'}
    check('Swap VCP: todo e_<code> nos tres idiomas',
          sorted(c for c in cod_vcp if vcp_html.count('e_' + c + ':') < 3), [])
    check('Other Publisher: todo e_/w_<code> nos tres idiomas',
          sorted(c for c in cod_nop if nop_js.count('e_' + c + ':') + nop_js.count('w_' + c + ':') < 3), [])
    check('os dois botoes existem e tem data-lang',
          ['id="vcpEmailValidation"' in vcp_html and 'data-lang="sc-vcp-email-validation"' in vcp_html,
           'data-lang="nop-email-validation"' in open(os.path.join(
               ROOT, 'apps/templates/pages/ndf-other-publisher.html'), encoding='utf-8').read()], [True, True])
    import json
    check('e a chave existe nos tres idiomas',
          [all(k in json.load(open(os.path.join(ROOT, 'apps/static/data/translations', lg + '.json'), encoding='utf-8'))
               for k in ('sc-vcp-email-validation', 'nop-email-validation')) for lg in ('en', 'br', 'es')],
          [True, True, True])
finally:
    (R._mapping_rows, R._create_notification, R.CONECTA_NEW_PATH, EV.send_email,
     VQ.vcp_factor_rows, R._ndfop_collect) = _real
    shutil.rmtree(TMP, ignore_errors=True)

print()
if fails:
    print('FALHOU: %d' % len(fails))
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('TUDO OK')
