# -*- coding: utf-8 -*-
"""Save CETIP Files: o JSON do dia e o que acontece quando ele NAO sai.

O arquivo que a rotina salva na pasta do dia nao e o que as telas leem. Quem
alimenta o Live Position, o Settlement Forecast, a Swap Characteristics e o
Other Products e o **JSON por dia** que o `_b3_export_json` deriva dele —
`73760_YYMMDD_DPOSICAO-SWAP.CETIP21` vira
`<categoria>/AAAA/MM/DD/73760_YYMMDD_DPOSICAO-SWAP.json`.

Duas coisas erram em SILENCIO e este teste prende as duas:

1. **O NOME.** O leitor monta o nome do JSON por conta propria
   (`'73760_{}_DPOSICAO-SWAP.json'.format(dref)`), entao a derivacao do
   `_b3_export_json` e um CONTRATO entre dois lugares que nao se conhecem. Um
   `.txt` a mais no DEST do cadastro `cetip-files` produz
   `...DPOSICAO-SWAP.CETIP21.json` e nenhum leitor acha — cada tela cai
   sozinha no dia anterior, certa e desatualizada ao mesmo tempo.

2. **A FALHA MUDA.** O `_b3_export_json` e best-effort: devolve `None` e loga.
   Ate 11/09/2026 o retorno era DESCARTADO — a rotina respondia
   "`N` file(s) saved" e o e-mail dizia que os arquivos do KPI estavam prontos
   no dia exato em que o JSON nao existia. Nada na tela, no e-mail ou no
   payload dizia que faltava o dia.

Nao encosta em dado real: fonte sintetica em tempfile, SMTP dublado.
"""
import io, json, os, shutil, sys, tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', os.path.join(ROOT, '.check-share'))
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

from apps.pages import routes as R                                   # noqa: E402
from apps import create_app                                          # noqa: E402
from apps.config import DebugConfig                                  # noqa: E402
from apps.pages.features.cetip import domain as CD                   # noqa: E402
from apps.pages.features.cetip import entrypoint as CE               # noqa: E402
from apps.pages.features.cetip.infra import mail as CM               # noqa: E402

app = create_app(DebugConfig)
app.config['TESTING'] = True

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def cliente():
    c = app.test_client()
    with c.session_transaction() as s:
        s['authenticated'] = True
        s['user_sid'] = 'A111111'
        s['user_name'] = 'Alice Souza'
        s['user_role'] = 'BO'
        s['user_email'] = 'alice.souza@jpmorgan.com'
        s['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()
    return c


REF = datetime(2026, 9, 10)
DREF = REF.strftime('%y%m%d')

print('== 1. o nome do JSON e o MESMO que os leitores montam ==')
# O que os leitores pedem (Live Position, Swap Characteristics, Forecast):
esperado = {
    'SWAP Position (DPOSICAO-SWAP)': ('Swap', '73760_{}_DPOSICAO-SWAP.json'.format(DREF)),
    'NDF Position (DPOSICAO-TER)':   ('NDF', '73760_{}_DPOSICAO-TER.json'.format(DREF)),
    'Option Position (OPC DPOSICAO)': ('Option', '73760_{}_DPOSICAO.json'.format(DREF)),
    'SWAP Flow (DFLUXO_SWAP)':       ('Swap', '73760_{}_DFLUXO.json'.format(DREF)),
}
with app.app_context():
    from apps.pages.features.cetip import queries as CQ
    por_tipo = {r['label']: r for r in CQ._cetip_rules()}
    for tipo, (cat, json_name) in sorted(esperado.items()):
        regra = por_tipo.get(tipo)
        if not regra:
            check('%s tem regra no cadastro' % tipo, False, True)
            continue
        dest_name = regra['dest_name'](DREF)
        derivado = os.path.splitext(dest_name)[0] + '.json'
        check('%-32s %s -> %s' % (tipo, dest_name, json_name), derivado, json_name)
        check('   e na categoria %s' % cat, (regra.get('json') or {}).get('category'), cat)

print('\n== 2. o JSON que nao sai NAO passa por "salvo com sucesso" ==')
tmp_src = tempfile.mkdtemp(prefix='check-cetip-json-src-')
tmp_dst = tempfile.mkdtemp(prefix='check-cetip-json-dst-')
try:
    mes = REF.strftime('%m') + '. ' + R._EN_MONTH_NAMES[REF.month - 1]
    d_src = os.path.join(tmp_src, REF.strftime('%Y'), mes, REF.strftime('%d'))
    os.makedirs(d_src, exist_ok=True)
    # Uma posicao de swap sintetica (headerless, ';'): basta existir para a regra casar.
    with io.open(os.path.join(d_src, 'CETIP21_{}_DPOSICAO-SWAP.TXT'.format(DREF)),
                 'w', encoding='latin-1', newline='') as fh:
        fh.write('1;20260910;C1;73760.00-9;;;;00041.00-7\r\n')

    R.CETIP_SOURCE_ROOT = tmp_src
    R.CETIP_DEST_ROOT = tmp_dst
    R._create_notification = lambda *a, **kw: None
    CM._send_cetip_email = lambda *a, **kw: True

    # O export falha (é best-effort e devolve None — é assim que ele avisa).
    R._b3_export_json = lambda *a, **kw: None

    c = cliente()
    r = c.post('/api/control-panel/cetip-settlement',
               json={'date': '2026-09-10', 'send_email': False})
    d = r.get_json()
    check('a rotina responde 200 (o ARQUIVO foi salvo mesmo)', r.status_code, 200)
    check('mas o payload diz QUAL JSON faltou',
          [j['dest'] for j in d.get('json_failed', [])],
          ['73760_{}_DPOSICAO-SWAP.CETIP21'.format(DREF)])
    check('e a mensagem da tela avisa, em vez de so contar arquivos',
          ('WITHOUT their per-day JSON' in d['message'],
           'previous day' in d['message']), (True, True))

    print('\n== 3. o e-mail do OTC Ops nao afirma que o KPI esta pronto ==')
    corpos = []
    CM._send_cetip_email = lambda to, cc, assunto, ola, msg, *a, **kw: (corpos.append(msg) or True)
    c.post('/api/control-panel/cetip-settlement',
           json={'date': '2026-09-10', 'send_email': True})
    check('o corpo carrega o aviso e o nome do arquivo',
          (bool(corpos) and 'could <b>not</b> be generated' in corpos[-1],
           bool(corpos) and 'DPOSICAO-SWAP' in corpos[-1]), (True, True))

    print('\n== 4. com o export OK, nada de aviso (o caminho feliz continua limpo) ==')
    R._b3_export_json = lambda src, cfg, dest_name, dref, **kw: '/tmp/ok.json'
    del corpos[:]
    r = c.post('/api/control-panel/cetip-settlement',
               json={'date': '2026-09-10', 'send_email': True})
    d = r.get_json()
    check('json_failed vazio', d.get('json_failed'), [])
    check('a mensagem nao inventa aviso', 'WITHOUT their per-day JSON' in d['message'], False)
    check('nem o e-mail', bool(corpos) and 'could <b>not</b> be generated' in corpos[-1], False)
finally:
    shutil.rmtree(tmp_src, ignore_errors=True)
    shutil.rmtree(tmp_dst, ignore_errors=True)

print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
