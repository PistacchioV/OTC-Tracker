"""Support Center ponta a ponta: CRUD, permissoes, ID sequencial, notificacoes
e o e-mail de encerramento (SMTP stubado, nao sai nada da maquina).

Redireciona o arquivo de tickets para um tmp e o DuckDB dos usuarios para uma
copia, para nao encostar em nada real.
"""
import io, json, os, shutil, sys, tempfile
from datetime import datetime, timedelta

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))   # scripts/tests/ -> raiz do repo
sys.path.insert(0, ROOT)
os.chdir(ROOT)

TMP = tempfile.mkdtemp()

from apps.pages import otc_tickets                       # noqa: E402
otc_tickets._DIR = os.path.join(TMP, 'tickets')
otc_tickets._FILE = os.path.join(otc_tickets._DIR, 'tickets.json')

from apps.pages import routes as R                       # noqa: E402
from apps import create_app                              # noqa: E402
from apps.config import DebugConfig                      # noqa: E402

# --- captura de notificacoes e de e-mail ----------------------------------
NOTIFS = []
R._create_notification = lambda actor_sid, actor_name, action, page, detail='', \
    target_role='', target_sid='': NOTIFS.append(
        {'actor': actor_sid, 'action': action, 'page': page, 'detail': detail,
         'role': target_role, 'sid': target_sid})

MAILS = []
_real_mail = R._tk_send_closed_email
def fake_mail(ticket):
    MAILS.append({'to': ticket.get('requester_email'), 'id': ticket.get('id'),
                  'status': ticket.get('status')})
    return True
R._tk_send_closed_email = fake_mail

app = create_app(DebugConfig)
app.config['TESTING'] = True

MASTER = 'E930179'          # _MASTER_SIDS
USER_A = 'A111111'
USER_B = 'B222222'

fails = []
def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)

def client_for(sid, name, role, email=None):
    c = app.test_client()
    with c.session_transaction() as s:
        s['authenticated'] = True
        s['user_sid'] = sid
        s['user_name'] = name
        s['user_role'] = role
        s['user_email'] = email or (name.lower().replace(' ', '.') + '@jpmorgan.com')
        s['session_expires_at'] = (datetime.now() + timedelta(days=1)).isoformat()
    return c

master = client_for(MASTER, 'Master User', 'MASTER')
alice  = client_for(USER_A, 'Alice Souza', 'BO')
bob    = client_for(USER_B, 'Bob Lima',    'BO')

def jget(c, url):
    r = c.get(url)
    return r.status_code, (r.get_json() or {})
def jpost(c, url, body):
    r = c.post(url, json=body)
    return r.status_code, (r.get_json() or {})
def jdel(c, url):
    r = c.delete(url)
    return r.status_code, (r.get_json() or {})

print('\n== 1. criacao: ID sequencial, status New, requester da sessao ==')
st, d = jpost(alice, '/api/tickets', {'subject': 'Login falha', 'description': 'nao entro',
                                      'priority': 'High', 'tags': ['login', ' 2fa ']})
check('HTTP 200', st, 200)
check('id OTC-0001', d['ticket']['id'], 'OTC-0001')
check('status New', d['ticket']['status'], 'New')
check('requester name da sessao', d['ticket']['requester_name'], 'Alice Souza')
check('requester sid da sessao', d['ticket']['requester_sid'], USER_A)
check('e-mail da sessao', d['ticket']['requester_email'], 'alice.souza@jpmorgan.com')
check('due date em branco', d['ticket']['due_date'], '')
check('tags limpas', d['ticket']['tags'], ['login', '2fa'])
check('agente fixo', d['ticket']['agent_name'], 'OTC Tracker Team')
check('1 evento na timeline', len(d['ticket']['activity']), 1)

st, d = jpost(bob, '/api/tickets', {'subject': 'Relatorio vazio', 'description': 'sem linhas'})
check('id OTC-0002 (sequencial)', d['ticket']['id'], 'OTC-0002')
st, d = jpost(alice, '/api/tickets', {'subject': 'Terceiro', 'description': 'x'})
check('id OTC-0003', d['ticket']['id'], 'OTC-0003')

print('\n== 2. o cliente NAO escolhe requester nem status ==')
st, d = jpost(bob, '/api/tickets', {'subject': 'Forjado', 'description': 'y',
                                    'status': 'Closed', 'requester_sid': MASTER,
                                    'requester_name': 'Outro', 'id': 'OTC-9999'})
check('status ignorado -> New', d['ticket']['status'], 'New')
check('requester ignorado -> sessao', d['ticket']['requester_sid'], USER_B)
check('id ignorado -> sequencia', d['ticket']['id'], 'OTC-0004')

print('\n== 3. campos obrigatorios ==')
st, d = jpost(alice, '/api/tickets', {'subject': '', 'description': 'x'})
check('sem assunto -> 400', st, 400)
st, d = jpost(alice, '/api/tickets', {'subject': 'x', 'description': '  '})
check('sem descricao -> 400', st, 400)

print('\n== 4. visibilidade: master ve tudo, a MESA ve a fila dela ==')
# A unidade da visibilidade e a MESA, nao a pessoa: alice e bob sao os dois do
# BO e enxergam os quatro chamados do BO. Sem isso, o colega que abriu o mesmo
# pedido ontem nao tinha como saber, e o time abria o chamado duas vezes.
st, d = jget(master, '/api/tickets')
check('master ve 4', len(d['tickets']), 4)
check('master flag', d['is_master'], True)
st, d = jget(alice, '/api/tickets')
check('alice (BO) ve os 4 do BO',
      sorted(t['id'] for t in d['tickets']),
      ['OTC-0001', 'OTC-0002', 'OTC-0003', 'OTC-0004'])
check('alice nao e master', d['is_master'], False)
st, d = jget(bob, '/api/tickets')
check('bob (BO) ve os mesmos 4',
      sorted(t['id'] for t in d['tickets']),
      ['OTC-0001', 'OTC-0002', 'OTC-0003', 'OTC-0004'])
# Ver nao e ser dono: a tela precisa separar o chamado proprio do chamado do
# colega, porque so o primeiro se edita.
_por_id = {t['id']: t for t in d['tickets']}
check('   o dele vem como proprio',
      (_por_id['OTC-0002']['is_requester'], _por_id['OTC-0002']['same_role']),
      (True, False))
check('   e o da alice como da mesa',
      (_por_id['OTC-0001']['is_requester'], _por_id['OTC-0001']['same_role']),
      (False, True))
check('   sem poder editar o do colega',
      (_por_id['OTC-0001']['can_edit_fields'], _por_id['OTC-0001']['can_delete'],
       _por_id['OTC-0001']['can_comment']), (False, False, False))

st, d = jget(bob, '/api/tickets/OTC-0001')
check('bob abre o ticket da alice (mesma mesa) -> 200', st, 200)
st, d = jget(master, '/api/tickets/OTC-0001')
check('master abre qualquer um', st, 200)

# Outra MESA nao ve nada disso. E o teste que importa: sem ele, "todo mundo ve
# tudo" passaria em todos os anteriores. (Quem CRIA ticket vai para o fim do
# arquivo: o ID e sequencial e as notificacoes sao acumuladas, entao um ticket a
# mais aqui deslocaria todas as assercoes seguintes.)
carol = client_for('C333333', 'Carol Dias', 'MO')
st, d = jget(carol, '/api/tickets')
check('carol (MO) nao ve a fila do BO', [t['id'] for t in d['tickets']], [])
st, d = jget(carol, '/api/tickets/OTC-0001')
check('   nem abre um deles -> 403', st, 403)

print('\n== 5. status e due date: so o master ==')
st, d = jpost(alice, '/api/tickets/OTC-0001', {'status': 'Resolved'})
check('alice nao muda status -> 403', st, 403)
st, d = jpost(alice, '/api/tickets/OTC-0001', {'due_date': '2026-08-10'})
check('alice nao muda prazo -> 403', st, 403)
st, d = jget(master, '/api/tickets/OTC-0001')
check('status intacto', d['ticket']['status'], 'New')

st, d = jpost(master, '/api/tickets/OTC-0001', {'status': 'In Progress', 'due_date': '2026-08-10'})
check('master muda os dois', st, 200)
check('status novo', d['ticket']['status'], 'In Progress')
check('prazo novo', d['ticket']['due_date'], '2026-08-10')
check('2 eventos gravados', d['changed'], 2)
check('nenhum e-mail (nao e final)', len(MAILS), 0)

print('\n== 6. campos do proprio ticket: o requester edita enquanto aberto ==')
st, d = jpost(alice, '/api/tickets/OTC-0001', {'priority': 'Urgent', 'description': 'detalhado'})
check('alice edita o dela', st, 200)
check('prioridade nova', d['ticket']['priority'], 'Urgent')
st, d = jpost(bob, '/api/tickets/OTC-0001', {'priority': 'Low'})
check('bob nao edita o da alice -> 403', st, 403)

print('\n== 7. no-op nao gera evento nem suja a timeline ==')
before = len(otc_tickets.get('OTC-0001')['activity'])
st, d = jpost(alice, '/api/tickets/OTC-0001', {'priority': 'Urgent'})
check('mesmo valor -> changed 0', d['changed'], 0)
check('timeline intacta', len(otc_tickets.get('OTC-0001')['activity']), before)

print('\n== 8. encerramento: e-mail so na TRANSICAO ==')
MAILS[:] = []
st, d = jpost(master, '/api/tickets/OTC-0001', {'status': 'Resolved'})
check('encerrou', d['ticket']['status'], 'Resolved')
check('1 e-mail enviado', len(MAILS), 1)
check('para o requester', MAILS[0]['to'], 'alice.souza@jpmorgan.com')
check('email_sent no retorno', d['email_sent'], True)
check('closed_at carimbado', bool(d['ticket']['closed_at']), True)

st, d = jpost(master, '/api/tickets/OTC-0001', {'priority': 'High'})
check('salvar de novo NAO reenvia', len(MAILS), 1)

st, d = jpost(master, '/api/tickets/OTC-0001', {'status': 'Closed'})
check('Resolved -> Closed nao reenvia', len(MAILS), 1)

st, d = jpost(master, '/api/tickets/OTC-0001', {'status': 'In Progress'})
check('reabrir limpa closed_at', d['ticket']['closed_at'], '')
st, d = jpost(master, '/api/tickets/OTC-0001', {'status': 'Closed'})
check('encerrar de novo REENVIA', len(MAILS), 2)

print('\n== 9. ticket encerrado: requester nao edita mais ==')
st, d = jpost(alice, '/api/tickets/OTC-0001', {'priority': 'Low'})
check('alice bloqueada em ticket fechado -> 403', st, 403)
st, d = jpost(master, '/api/tickets/OTC-0001', {'priority': 'Low'})
check('master ainda edita', st, 200)

print('\n== 10. comentarios ==')
st, d = jpost(alice, '/api/tickets/OTC-0001/comment', {'text': 'alguma novidade?'})
check('requester comenta mesmo fechado', st, 200)
check('comentario no topo', d['ticket']['activity'][0]['detail'], 'alguma novidade?')
st, d = jpost(bob, '/api/tickets/OTC-0001/comment', {'text': 'intruso'})
check('estranho nao comenta -> 403', st, 403)
st, d = jpost(alice, '/api/tickets/OTC-0001/comment', {'text': '   '})
check('comentario vazio -> 400', st, 400)

print('\n== 11. notificacoes: novo -> master; update -> requester ==')
NOTIFS[:] = []
jpost(bob, '/api/tickets', {'subject': 'Novo do bob', 'description': 'z'})
check('1 notificacao', len(NOTIFS), 1)
check('alvo = papel MASTER', NOTIFS[0]['role'], 'MASTER')
check('sem alvo por SID', NOTIFS[0]['sid'], '')
check('pagina Support', NOTIFS[0]['page'], 'Support')

NOTIFS[:] = []
jpost(master, '/api/tickets/OTC-0005', {'status': 'Pending'})
check('1 notificacao', len(NOTIFS), 1)
check('alvo = SID do requester', NOTIFS[0]['sid'], USER_B)
check('sem alvo por papel', NOTIFS[0]['role'], '')

NOTIFS[:] = []
jpost(bob, '/api/tickets/OTC-0005/comment', {'text': 'obrigado'})
check('requester comentando nao notifica a si mesmo', len(NOTIFS), 0)

print('\n== 12. exclusao: so requester ou master ==')
st, d = jdel(alice, '/api/tickets/OTC-0002')
check('alice nao apaga o do bob -> 403', st, 403)
st, d = jdel(bob, '/api/tickets/OTC-0002')
check('bob apaga o dele', st, 200)
st, d = jdel(master, '/api/tickets/OTC-0004')
check('master apaga o de outro', st, 200)
st, d = jget(master, '/api/tickets/OTC-0002')
check('sumiu -> 404', st, 404)

print('\n== 13. o seq NAO reaproveita numero de ticket apagado ==')
st, d = jpost(alice, '/api/tickets', {'subject': 'Depois da limpeza', 'description': 'q'})
check('proximo id = OTC-0006', d['ticket']['id'], 'OTC-0006')

print('\n== 14. contadores dos cards ==')
st, d = jget(master, '/api/tickets')
tickets = otc_tickets.list_all()
manual = {'open': 0, 'pending': 0, 'resolved': 0, 'closed': 0}
for t in tickets:
    if t['status'] in ('New', 'In Progress'): manual['open'] += 1
    elif t['status'] == 'Pending': manual['pending'] += 1
    elif t['status'] == 'Resolved': manual['resolved'] += 1
    elif t['status'] == 'Closed': manual['closed'] += 1
for k in manual:
    check('contador %s' % k, d['counts'][k], manual[k])

print('\n== 15. sem autenticacao ==')
anon = app.test_client()
check('GET lista -> 401', anon.get('/api/tickets').status_code, 401)
check('POST cria -> 401', anon.post('/api/tickets', json={'subject': 'a', 'description': 'b'}).status_code, 401)
check('DELETE -> 401', anon.delete('/api/tickets/OTC-0001').status_code, 401)

print('\n== 16. paginas renderizam ==')
for url, needle in (('/tickets-list', 'tk-new-btn'),
                    ('/ticket-details', 'tkd-empty-card'),
                    ('/ticket-details?id=OTC-0001', 'tkd-timeline')):
    r = master.get(url)
    body = r.get_data(as_text=True)
    check('GET %s' % url, (r.status_code, needle in body), (200, True))
r = master.get('/ticket-create')
check('/ticket-create removida -> 404', r.status_code, 404)

print('\n== 17. o template do e-mail renderiza de verdade ==')
R._tk_send_closed_email = _real_mail
sent = {}
class FakeSMTP(object):
    def __init__(self, *a, **k): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def sendmail(self, frm, to, msg):
        sent['from'], sent['to'], sent['msg'] = frm, to, msg
R.smtplib.SMTP = FakeSMTP
st, d = jpost(master, '/api/tickets/OTC-0005', {'status': 'Resolved'})
check('encerrou', d['ticket']['status'], 'Resolved')
check('email_sent', d['email_sent'], True)
check('to = requester', sent['to'][0], 'bob.lima@jpmorgan.com')
check('cc = otc ops', sent['to'][1], 'brazil.otc.ops@jpmorgan.com')
# O corpo vai codificado (base64/quoted-printable) — precisa decodificar, senao
# o `in` procura no texto errado e passa/falha por acidente.
import email as _email                                   # noqa: E402
parsed = _email.message_from_string(sent['msg'])
html_part = ''
for part in parsed.walk():
    if part.get_content_type() == 'text/html':
        html_part = part.get_payload(decode=True).decode('utf-8', 'replace')
check('assunto do e-mail tem o id', 'OTC-0005' in (parsed['Subject'] or ''), True)
check('corpo tem o assunto do ticket', 'Novo do bob' in html_part, True)
check('corpo tem o agente', 'OTC Tracker Team' in html_part, True)
check('corpo tem o status final', 'Resolved' in html_part, True)
check('corpo tem o nome do requester', 'Bob Lima' in html_part, True)
# O cabecalho e COR SOLIDA + gradiente CSS, nunca imagem nem VML (CLAUDE.md §2):
# o <v:rect> do Outlook pintava o banner ora mais estreito que a celula (faixa
# solida a direita), ora na largura da janela inteira. Esta assercao cobrava a
# imagem — a regra anterior — e por isso vivia vermelha desde que o partial
# mudou; agora ela prende a regra que vale.
check('o header tem a cor solida de fallback', 'bgcolor="#4f8ae2"' in html_part, True)
check('   e o gradiente em CSS', 'linear-gradient(' in html_part, True)
check('   sem imagem de gradiente nem VML',
      ('cid:otc_gradient' in html_part) or ('email-header-gradient.png' in html_part)
      or ('<v:rect' in html_part), False)
check('logo embutido', 'cid:otc_logo' in html_part, True)

print('\n== 18. arquivo em disco: formato e seq ==')
raw = json.load(io.open(otc_tickets._FILE, encoding='utf-8'))
check('tem seq', raw['seq'], 6)
check('tem lista', isinstance(raw['tickets'], list), True)
check('sem ticket sem id', all(t.get('id') for t in raw['tickets']), True)


print('\n== 19. a mesa isola as duas pontas ==')
# Fica no FIM porque cria tickets: o ID e sequencial e as notificacoes sao
# acumuladas, entao no meio do arquivo isto deslocaria as assercoes seguintes.
_antes = len(jget(alice, '/api/tickets')[1]['tickets'])
st, d = jpost(carol, '/api/tickets', {'subject': 'MO abre um', 'description': 'd'})
_id_mo = d['ticket']['id']
check('o chamado nasce com o papel de quem abriu', d['ticket']['requester_role'], 'MO')
st, d = jget(carol, '/api/tickets')
check('   que ela passa a ver', _id_mo in [t['id'] for t in d['tickets']], True)
st, d = jget(alice, '/api/tickets')
check('   e o BO nao ve', _id_mo in [t['id'] for t in d['tickets']], False)
check('   nem ganhou linha na fila dele', len(d['tickets']), _antes)

# Papel VAZIO nao casa com nada: dois usuarios sem papel no cadastro nao sao uma
# mesa, e trata-los como uma abriria a fila de um para o outro.
sem1 = client_for('D444444', 'Dan Sem Papel', '')
sem2 = client_for('E555555', 'Eva Sem Papel', '')
st, d = jpost(sem1, '/api/tickets', {'subject': 'sem papel', 'description': 'd'})
_id_sem = d['ticket']['id']
st, d = jget(sem2, '/api/tickets')
check('papel vazio nao vira mesa', [t['id'] for t in d['tickets']], [])
st, d = jget(sem1, '/api/tickets')
check('   mas o dono continua vendo o seu', [t['id'] for t in d['tickets']], [_id_sem])

# Ticket ANTERIOR ao requester_role: o papel e resolvido no cadastro de
# usuarios. Sem isso, toda a fila antiga sumiria da mesa que a abriu — e um
# chamado que some e pior do que um que aparece para gente demais.
_st = otc_tickets._read()
for _t in _st['tickets']:
    if _t['id'] == _id_mo:
        _t.pop('requester_role', None)
otc_tickets._write(_st)
R._TK_ROLE_CACHE.clear()
_ROLES = {'C333333': 'MO'}
_orig_roles = R._tk_roles_by_sid
R._tk_roles_by_sid = lambda sids: {str(x or '').strip().upper():
                                   _ROLES.get(str(x or '').strip().upper(), '')
                                   for x in sids if str(x or '').strip()}
try:
    st, d = jget(carol, '/api/tickets')
    check('ticket antigo (sem papel gravado) volta pela mesa do requester',
          _id_mo in [t['id'] for t in d['tickets']], True)
    st, d = jget(alice, '/api/tickets')
    check('   e continua fora da fila das outras',
          _id_mo in [t['id'] for t in d['tickets']], False)
finally:
    R._tk_roles_by_sid = _orig_roles

print('\n== 20. arquivo corrompido nao derruba a pagina ==')
io.open(otc_tickets._FILE, 'w', encoding='utf-8').write(u'{{{ nao e json')
check('list_all devolve vazio', otc_tickets.list_all(), [])
check('a pagina ainda responde 200', master.get('/tickets-list').status_code, 200)
st, d = jget(master, '/api/tickets')
check('API ainda responde', (st, d['tickets']), (200, []))

shutil.rmtree(TMP, ignore_errors=True)
print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
