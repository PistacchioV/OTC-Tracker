# -*- coding: utf-8 -*-
"""A camada HTTP da Recon de FXO — as quatro rotas, nao o motor.

O `check_recon_fxo.py` (117 assercoes) protege o MOTOR: a chave, a perna
interna, os cortes por cadastro, o comentario. O que ninguem prendia era a
casca — e ela guarda tres decisoes que nao dao erro nenhum quando caem:

  1. **o `/run` toca os dois cadastros ANTES de rodar.** O motor le o JSON
     direto (importar o `routes` de la seria circular) e nao tem como semear:
     sem esse toque, na instancia em que ninguem abriu a tela de /mapping o
     arquivo nao existe, o cadastro volta vazio e as regras de exclusao
     simplesmente nao valem — a recon roda, responde 200 e mostra como quebra a
     perna interna que o cadastro mandava tirar;
  2. **arquivo do dia que nao chegou NAO e erro.** Ele volta `not_found` com
     200, e a tela oferece o upload manual em vez de mostrar um stack;
  3. **o aviso do sino aponta para a pagina certa.** `page` e o DESTINO do
     clique: 'Reconciliation' e a do Pay/Rec, e era para la que o sino levava.

Escrito ANTES de a Recon FXO sair do `routes.py`, com o codigo ainda no lugar.
O motor e stubado — nada le posicao da B3 nem chama a Athena.
"""
import os, sys, tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)

from apps.pages import routes as R                          # noqa: E402
from apps.pages import recon_fxo as RF                      # noqa: E402
from apps import create_app                                 # noqa: E402
from apps.config import DebugConfig                         # noqa: E402

app = create_app(DebugConfig)
app.config['TESTING'] = True

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


# ── os espioes ──────────────────────────────────────────────────────────────
NOTIFS = []
R._create_notification = lambda actor_sid, actor_name, action, page, detail='', \
    target_role='', target_sid='': NOTIFS.append(
        {'action': action, 'page': page, 'detail': detail})

SEMEADOS = []
_orig_mapping = R._mapping_rows


def _espia_mapping(key, *a, **kw):
    SEMEADOS.append(key)
    return []


R._mapping_rows = _espia_mapping


def cliente(auth=True):
    c = app.test_client()
    if auth:
        with c.session_transaction() as s:
            s['authenticated'] = True
            s['user_sid'] = 'A111111'
            s['user_name'] = 'Alice Souza'
            s['user_role'] = 'BO'
            s['user_email'] = 'alice.souza@jpmorgan.com'
            s['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()
    return c


c, anon = cliente(), cliente(auth=False)

print('\n== 1. sem sessao ==')
# A PAGINA redireciona para o login; as APIs respondem JSON. Sao contratos
# diferentes de proposito: um <a> que devolve 401 deixa a tela em branco.
r = anon.get('/reconciliation-fxo')
check('a pagina redireciona', r.status_code, 302)
check('   para o sign-in', '/login' in r.headers.get('Location', '')
      or 'sign' in r.headers.get('Location', '').lower(), True)
check('data -> 401', anon.get('/reconciliation-fxo/data').status_code, 401)
check('run -> 401', anon.post('/reconciliation-fxo/run').status_code, 401)
check('comment -> 401', anon.post('/reconciliation-fxo/comment', json={}).status_code, 401)

print('\n== 2. a pagina abre em D-1 ANBIMA ==')
# A posicao da B3 e o EOD da Athena sao do fechamento anterior. Abrir em "hoje"
# mandaria todo mundo procurar um arquivo que ainda nao existe — e numa
# segunda-feira, ou no dia seguinte a um feriado, "ontem" no calendario civil
# nao e dia util nenhum.
r = c.get('/reconciliation-fxo')
check('a pagina abre', r.status_code, 200)
esperado = R._prev_anbima_bizday(datetime.now()).strftime('%Y-%m-%d')
check('   com a data do ultimo dia util', esperado in r.get_data(as_text=True), True)

print('\n== 3. /data devolve o que o motor leu ==')
_orig_load = RF.load_last
RF.load_last = lambda ref: {'recon_date': ref or 'sem-data', 'rows': [{'x': 1}]}
st = c.get('/reconciliation-fxo/data?recon_date=2026-08-25')
check('200', st.status_code, 200)
check('   a data pedida chega ao motor', st.get_json()['recon_date'], '2026-08-25')
RF.load_last = lambda ref: (_ for _ in ()).throw(RuntimeError('disco fora'))
st = c.get('/reconciliation-fxo/data')
check('o motor que estoura -> 500', st.status_code, 500)
check('   com o motivo', st.get_json()['error'], 'disco fora')
RF.load_last = _orig_load

print('\n== 4. o /run SEMEIA os dois cadastros antes de rodar ==')
# Esta e a assercao que justifica o teste. Sem o toque, a recon roda, responde
# 200 e mostra como quebra a perna interna que o cadastro mandava tirar.
_orig_run = RF.run_fxo
chamadas = []
RF.run_fxo = lambda ref, files=None, mode='auto': (
    chamadas.append({'ref': ref, 'mode': mode, 'files': files})
    or {'success': True, 'meta': '3 quebras'})
del SEMEADOS[:]; del NOTIFS[:]
st = c.post('/reconciliation-fxo/run', data={'mode': 'auto', 'recon_date': '2026-08-25'})
check('200', st.status_code, 200)
check('os dois cadastros foram tocados', sorted(SEMEADOS),
      ['fxo-book-disregard', 'fxo-internal-cpty'])
check('   e a data chegou ao motor', chamadas[-1]['ref'], '2026-08-25')
check('   modo auto nao manda arquivo', chamadas[-1]['files'], None)

print('\n== 5. o aviso do sino aponta para a Recon FXO ==')
check('um aviso', len(NOTIFS), 1)
check('   acao', NOTIFS[0]['action'], 'Recon Generated')
check('   pagina (o DESTINO do clique)', NOTIFS[0]['page'], 'Recon FXO')
check('   com a data no detalhe', '2026-08-25' in NOTIFS[0]['detail'], True)
# O rotulo tem de existir nos tres mapas de destino, senao o clique nao vai a
# lugar nenhum (o item nasce <div> em vez de <a>, sem erro no console).
check('   e o rotulo tem destino', bool(R._NOTIF_PAGE_URL.get('Recon FXO')), True)

print('\n== 6. recon sem sucesso NAO avisa ==')
RF.run_fxo = lambda ref, files=None, mode='auto': {'success': False, 'error': 'x'}
del NOTIFS[:]
st = c.post('/reconciliation-fxo/run', data={'mode': 'auto'})
check('200 (o resultado e o corpo)', st.status_code, 200)
check('   nenhum aviso', NOTIFS, [])

print('\n== 7. arquivo que nao chegou NAO e erro ==')
def _sem_arquivo(ref, files=None, mode='auto'):
    raise FileNotFoundError('CETIP21_260825_DPOSICAO.OPC')
RF.run_fxo = _sem_arquivo
st = c.post('/reconciliation-fxo/run', data={'mode': 'auto'})
check('responde 200, nao 500', st.status_code, 200)
d = st.get_json()
check('   com not_found', d['not_found'], True)
check('   e o nome do arquivo, para a tela dizer qual', 'DPOSICAO' in d['detail'], True)
check('   nenhum aviso de recon gerada', NOTIFS, [])

print('\n== 8. o resto estoura como 500 ==')
RF.run_fxo = lambda ref, files=None, mode='auto': (_ for _ in ()).throw(ValueError('coluna sumiu'))
st = c.post('/reconciliation-fxo/run', data={'mode': 'auto'})
check('500', st.status_code, 500)
check('   success False', st.get_json()['success'], False)
check('   com o motivo', st.get_json()['error'], 'coluna sumiu')
RF.run_fxo = _orig_run

print('\n== 9. o comentario e do TRADE, e volta com o status recalculado ==')
# O endpoint nao recebe data nenhuma de proposito: a justificativa pertence a
# operacao e volta em toda recon dela. E o status novo sai do MESMO codigo que a
# tabela usa — reproduzir aqui a regra "com comentario vira Justified" criaria
# uma segunda resposta para a mesma pergunta.
st = c.post('/reconciliation-fxo/comment', json={'comment': 'x'})
check('sem chave -> 400', st.status_code, 400)
check('   dizendo o porque', 'chave' in st.get_json()['error'], True)

# O `save_comment` NAO e stubado: o arquivo de comentarios vai para um tmp e o
# ciclo roda inteiro. E o que prova a decisao que importa aqui — o comentario
# gravado por este endpoint e o MESMO que o `aplicar_comentarios` le de volta.
# Com o save stubado, o arquivo fica vazio e o status volta cru: o teste
# passaria sem exercitar nada.
RF._COMMENTS_PATH = os.path.join(tempfile.mkdtemp(), 'recon-fxo-comments.json')
st = c.post('/reconciliation-fxo/comment',
            json={'key': 'CETIP-123', 'comment': 'quebra conhecida',
                  'status': 'Partial - Cntpy', 'status_raw': 'Partial - Cntpy'})
check('200', st.status_code, 200)
d = st.get_json()
check('   gravou pela chave da operacao',
      RF.load_comments().get('CETIP-123'), 'quebra conhecida')
check('   devolve o comentario', d['comment'], 'quebra conhecida')
check('   e o status ja recalculado', d['status'], 'Justified')
check('   com o CRU preservado', d['status_raw'], 'Partial - Cntpy')

st = c.post('/reconciliation-fxo/comment',
            json={'key': 'CETIP-123', 'comment': '',
                  'status': 'Partial - Cntpy', 'status_raw': 'Partial - Cntpy'})
check('apagar o comentario devolve o status cru', st.get_json()['status'], 'Partial - Cntpy')
R._mapping_rows = _orig_mapping

print(('FAIL: %d' % len(fails)) if fails else 'TUDO OK')
sys.exit(1 if fails else 0)
