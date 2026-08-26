"""O card New Version Released: a versao lida do link.txt e o aviso a mesa.

A instancia roda com o reloader DESLIGADO: depois de um deploy, o processo que
esta de pe continua servindo o codigo velho ate alguem derruba-lo e subir de
novo, e quem usa a ferramenta nao tem como saber. Este card e o aviso.

Tres coisas que nao dao erro nenhum se cairem, e que este script prende:

  1. a VERSAO nao e digitada — sai do `link.txt` que fica ao lado do .bat. Se o
     parser deixar de reconhecer o formato, o e-mail sairia anunciando "nova
     versao" sem numero, que nao diz nada a quem recebe. Por isso o envio e
     RECUSADO sem versao, em vez de sair em branco;
  2. o destinatario e quem esta ATIVO. Mandar para `Pending` e avisar quem
     ainda nao foi aprovado; deixar de mandar para `Active` e deixar gente no
     codigo velho;
  3. o corpo e o PROCEDIMENTO — fechar o DevShell ANTES de rodar o .bat. Sem o
     passo 1 a pessoa sobe um segundo servidor e continua na versao anterior,
     achando que atualizou.
"""
import io
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', tempfile.mkdtemp(prefix='share-root-'))

TMP = tempfile.mkdtemp(prefix='appver-')
DB = os.path.join(TMP, 'Users_OTCTracker.db')

import duckdb                                              # noqa: E402
_c = duckdb.connect(DB)
_c.execute("CREATE SEQUENCE IF NOT EXISTS seq_notif_id START 1")
_c.execute("""CREATE TABLE notifications (
        id INTEGER DEFAULT nextval('seq_notif_id') PRIMARY KEY,
        actor_sid VARCHAR NOT NULL DEFAULT '', actor_name VARCHAR NOT NULL DEFAULT '',
        action VARCHAR NOT NULL DEFAULT '', page VARCHAR NOT NULL DEFAULT '',
        detail VARCHAR DEFAULT '', target_role VARCHAR DEFAULT '',
        target_sid VARCHAR DEFAULT '', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
_c.execute("""CREATE TABLE users (
        SID VARCHAR PRIMARY KEY, Name VARCHAR, Email VARCHAR,
        Role_Description VARCHAR, Position VARCHAR, Role VARCHAR,
        Status VARCHAR, IP_Address VARCHAR, Page_Access VARCHAR DEFAULT '')""")
for sid, nome, mail, status in [
        ('A111111', 'Ana Lima',    'ana@jpmorgan.com',    'Active'),
        ('B222222', 'Bruno Reis',  'bruno@jpmorgan.com',  'Active'),
        ('C333333', 'Caio Souza',  'caio@jpmorgan.com',   'Pending'),
        ('D444444', 'Dora Alves',  'dora@jpmorgan.com',   'Inactive'),
        ('E555555', 'Edu Nunes',   'ANA@JPMORGAN.COM',    'active'),   # duplicado, caixa diferente
        ('F666666', 'Fim Sem Mail', '',                   'Active')]:  # ativo, sem e-mail
    _c.execute("INSERT INTO users (SID, Name, Email, Status) VALUES (?, ?, ?, ?)",
               [sid, nome, mail, status])
_c.close()

from apps.pages import routes as R                         # noqa: E402
# O card saiu do routes.py para features/appver — os nomes agora moram la, e os
# arquivos pendem da pasta de plataforma (routes._DAILY_METRIC_DIR) por busca
# atrasada: UM redirecionamento aponta todos para o tmp.
from apps.pages.features.appver import commands as AC, domain as AD   # noqa: E402
from apps.pages.features.appver.infra import persistence as AP        # noqa: E402
R.DB_PATH = DB
R._DAILY_METRIC_DIR = TMP

from apps import create_app                                # noqa: E402
from apps.config import DebugConfig                        # noqa: E402

app = create_app(DebugConfig)
app.config['TESTING'] = True

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def link(conteudo, binario=False):
    """Escreve um link.txt e aponta o modulo para ele."""
    p = os.path.join(TMP, 'link.txt')
    with open(p, 'wb' if binario else 'w', **({} if binario else {'encoding': 'utf-8'})) as fh:
        fh.write(conteudo)
    AP.LINK_FILE = p
    return p


# ─────────────────────────────────────────────────────────────────────────────
print('== 1. a versao sai do link.txt ==')
CASOS = [
    # o caso real: o arquivo guarda o caminho da pasta do codigo em uso
    (r'\\Nawest.ad.jpmorganchase.com\lac\BRA\intra\Confirmation\Derivativos'
     r'\OTC Tracker\Application\otc-source\v8', 'v8'),
    ('v8.2', 'v8.2'),
    ('Versao atual: v9 (liberada em 25/08/2026)', 'v9'),
    # duas linhas: vale a ULTIMA, que e a que o arquivo terminou apontando
    ('C:\\apps\\otc-source\\v3\nC:\\apps\\otc-source\\v4', 'v4'),
    # sem `vN`, vale o ultimo pedaco do caminho
    (r'\\srv\share\builds\release-2026-08-25', 'release-2026-08-25'),
]
for conteudo, esperado in CASOS:
    link(conteudo)
    check('%-46r -> %s' % (conteudo[-46:], esperado), AP.read_link()[0], esperado)

print('\n== 2. e quando ela NAO sai, o erro e dito ==')
for conteudo, rotulo in [('', 'arquivo vazio'),
                         ('   \n \n', 'so espaco em branco'),
                         ('um paragrafo inteiro que nao e versao nenhuma e passa dos quarenta',
                          'texto longo demais para ser versao')]:
    link(conteudo)
    v, _bruto, err = AP.read_link()
    check(rotulo + ': sem versao', v, '')
    check(rotulo + ': com motivo', bool(err), True)
AP.LINK_FILE = os.path.join(TMP, 'nao-existe.txt')
_v, _b, _e = AP.read_link()
check('arquivo ausente: sem versao', _v, '')
check('arquivo ausente: com motivo', 'FileNotFoundError' in _e, True)

print('\n== 3. cp1252 nao derruba a leitura ==')
# O arquivo e escrito no Windows; um acento em cp1252 estouraria o utf-8, e
# perder o acento e melhor do que nao ler a versao.
link('Vers\xe3o v7\n'.encode('cp1252'), binario=True)
check('acento em cp1252', AP.read_link()[0], 'v7')

print('\n== 4. o destinatario e quem esta ATIVO ==')
ativos = AP.active_users()
check('so os Active', sorted(e for _, e in ativos),
      ['ana@jpmorgan.com', 'bruno@jpmorgan.com'])
check('Pending e Inactive ficam de fora',
      [e for _, e in ativos if 'caio' in e or 'dora' in e], [])
check('e-mail repetido em outra caixa conta uma vez', len(ativos), 2)
check('ativo sem e-mail nao entra',
      [n for n, _ in ativos if n == 'Fim Sem Mail'], [])

# ── SMTP e notificacao stubados: nada sai da maquina ────────────────────────
enviados = []


class _SMTPFake(object):
    def __init__(self, host, port, timeout=None):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def sendmail(self, de, para, corpo):
        enviados.append({'de': de, 'para': list(para), 'corpo': corpo})


R.smtplib.SMTP = _SMTPFake
R._create_notification = lambda *a, **k: None

print('\n== 5. sem versao, o e-mail NAO sai ==')
AP.LINK_FILE = os.path.join(TMP, 'nao-existe.txt')
out = AC.run()
check('desfecho no_version', out.get('reason'), 'no_version')
check('e nada foi enviado', len(enviados), 0)

print('\n== 6. sem usuario ativo, tambem nao ==')
link(r'\\srv\otc-source\v8')
_real_ativos = AP.active_users
AP.active_users = lambda: []
out = AC.run()
check('desfecho no_recipient', out.get('reason'), 'no_recipient')
check('e nada foi enviado', len(enviados), 0)
AP.active_users = _real_ativos

print('\n== 7. o caminho feliz ==')
out = AC.run('bruno@jpmorgan.com; chefe@jpmorgan.com')
check('enviou', out.get('sent'), True)
check('a versao anunciada', out.get('version'), 'v8')
check('para os dois ativos', out.get('to'), 2)
# o Cc que ja esta no TO e descartado: a pessoa receberia duas vezes
check('Cc sem quem ja esta no TO', out.get('cc'), 1)
check('uma mensagem so', len(enviados), 1)
env = enviados[0]
check('o envelope leva TO + CC', sorted(env['para']),
      ['ana@jpmorgan.com', 'bruno@jpmorgan.com', 'chefe@jpmorgan.com'])
corpo = env['corpo']
check('o assunto traz a versao', 'New version v8 released' in corpo, True)
check('o assunto pede o restart', 'please restart' in corpo, True)

print('\n== 8. o corpo e o PROCEDIMENTO, nao um aviso ==')
# Quem recebe nao vai abrir uma tela para descobrir o que fazer.
import email as _email                                     # noqa: E402
# O HTML vai BASE64 dentro do MIME (`MIMEText(..., 'html', 'utf-8')`), entao
# procurar a string no `as_string()` cru nao acha nada: e preciso desmontar a
# mensagem e decodificar a parte text/html.
_msg = _email.message_from_string(corpo)
_texto = ''
for _parte in _msg.walk():
    if _parte.get_content_type() == 'text/html':
        _texto = _parte.get_payload(decode=True).decode('utf-8', 'replace')
        break
check('a mensagem tem uma parte HTML', bool(_texto), True)
_html = _texto            # o mesmo conteudo; nome proprio para as checagens de href
for trecho, rotulo in [
        ('v8', 'a versao'),
        (AD.STARTER, 'o nome do .bat a executar'),
        ('DevShell', 'a janela que tem de ser fechada'),
        ('Ctrl + C', 'como parar o processo'),
        ('Close the application that is running', 'o passo 1: derrubar o que esta no ar')]:
    check('o corpo cita ' + rotulo, trecho in _texto, True)
check('o passo 1 vem ANTES do .bat no corpo',
      _texto.index('Close the application') < _texto.index(AD.STARTER), True)

# O .bat NAO se abre com duplo clique: ele tem de rodar DENTRO do DevShell. O
# texto dizia "(double-click)", que e o caminho que nao funciona — e e o que a
# pessoa tenta primeiro, porque e o obvio.
check('o corpo diz para arrastar o .bat para o DevShell',
      'drag' in _texto and 'into it' in _texto, True)
check('   e desaconselha o duplo clique explicitamente',
      'Do not double-click' in _texto, True)
check('   sem sobrar o "(double-click)" antigo',
      '(double-click)' in _texto, False)

# Os DOIS enderecos, e nenhum deles derivado do hostname: cada pessoa roda a
# propria instancia, e o hostname de quem ENVIA nao abre nada para quem recebe
# (o e-mail saia com `http://chcd293c37n1:8050`, a maquina de uma pessoa so).
check('o passo 3 traz o atalho interno', AP.SHORTCUT in _texto, True)
check('   e o localhost', AP.local_url() in _texto, True)
check('   e nao o hostname da maquina que enviou',
      R._otc_app_url() in _texto, False)
# O atalho se ESCREVE `go/otctracker`, mas como `href` isso e caminho RELATIVO:
# clicado no Outlook, o link morre. O texto fica; o destino ganha o esquema.
check('o atalho tem esquema no href',
      'href="{}"'.format(AD.href(AP.SHORTCUT)) in _texto
      or AD.href(AP.SHORTCUT) in _texto, True)
check('   e o _appver_href nao mexe em quem ja tem esquema',
      AD.href('http://localhost:8051'), 'http://localhost:8051')

print('\n== 9. o status gravado responde "o aviso saiu?" ==')
AP.write_status('sent:v8:2', datetime(2026, 8, 26, 10, 30))
st = AP.read_status()
check('guarda o resultado', st.get('result'), 'sent:v8:2')
check('e o horario', st.get('at'), '26/08/2026 10:30:00')

print('\n== 10. o endpoint ==')


def cliente(sid='A111111', role='BO'):
    cl = app.test_client()
    with cl.session_transaction() as s:
        s['authenticated'] = True
        s['user_sid'] = sid
        s['user_name'] = sid
        s['user_role'] = role
        s['user_email'] = sid + '@x'
        s['session_expires_at'] = (datetime.now() + timedelta(days=1)).isoformat()
    return cl


rules = {str(x.rule) for x in app.url_map.iter_rules()}
check('rota de recipients registrada',
      '/api/control-panel/app-version/recipients' in rules, True)
check('rota de run registrada', '/api/control-panel/app-version/run' in rules, True)
# Sem isto o endpoint fica aberto a quem nao tem o card no /page-access.
for rota in ('/api/control-panel/app-version/recipients',
             '/api/control-panel/app-version/run'):
    check('protegido pelo card: ' + rota.split('/')[-1],
          R._CP_ENDPOINT_CARD.get(rota), 'appversion')
check('o card esta no registro',
      any(c['id'] == 'appversion' for c in R._CONTROL_PANEL_CARDS), True)

cl = cliente()
check('sem sessao devolve 401',
      app.test_client().get('/api/control-panel/app-version/recipients').status_code, 401)
d = cl.get('/api/control-panel/app-version/recipients').get_json()
check('o GET traz a versao', d.get('version'), 'v8')
check('e quantos receberiam', d.get('active_users'), 2)
check('e o caminho lido', d.get('path'), AP.LINK_FILE)
check('e um trecho do arquivo, para conferir',
      d.get('link_preview', '').endswith('v8'), True)

cl.post('/api/control-panel/app-version/recipients', json={'cc': 'x@jpmorgan.com'})
check('o Cc persiste',
      cl.get('/api/control-panel/app-version/recipients').get_json().get('cc'),
      'x@jpmorgan.com')

print('\n== 11. o run pelo endpoint ==')
enviados[:] = []
r = cl.post('/api/control-panel/app-version/run', json={'cc': ''})
b = r.get_json()
check('responde 200', r.status_code, 200)
check('com sucesso', b.get('success'), True)
check('e mandou uma mensagem', len(enviados), 1)

AP.LINK_FILE = os.path.join(TMP, 'nao-existe.txt')
enviados[:] = []
r = cl.post('/api/control-panel/app-version/run', json={'cc': ''})
# 400 e nao 500: o pedido esta bem formado, falta o arquivo dizer a versao.
check('sem versao devolve 400', r.status_code, 400)
check('e diz o caminho que tentou',
      'nao-existe.txt' in (r.get_json() or {}).get('error', ''), True)
check('e nao mandou nada', len(enviados), 0)

shutil.rmtree(TMP, ignore_errors=True)
print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
