# -*- coding: utf-8 -*-
"""As cinco rotas do Holidays Calendar — a casca, nao o parser.

O `check_holiday_calendars.py` (49 assercoes) prende o seed contra o fallback do
navegador, o parser da planilha, o slug e a cor, chamando as funcoes DIRETO. O
que ninguem prendia era o contrato HTTP, e ele guarda cinco decisoes que nao dao
erro nenhum:

  1. **o Save resolve o calendario pelo REGISTRO, nao por um mapa fixo.** O
     calendario criado pela tela nao esta em literal nenhum do codigo: com o
     mapa, o Save devolvia "Unknown calendar" para um calendario que a propria
     pagina acabara de mostrar;
  2. **o registro se semeia na PRIMEIRA leitura**, entao a instancia que nunca
     abriu a tela ja responde com os onze de sempre;
  3. **nome duplicado, arquivo duplicado e arquivo JA EXISTENTE em disco sao
     409, cada um com a sua frase** — e o terceiro existe porque sobrescrever
     apagaria uma agenda que alguem pode estar consumindo pelo FX holiday
     schedule;
  4. **planilha sem feriado nenhum e recusada dizendo o que se esperava ler.**
     Calendario vazio e calendario que ninguem ve e que ninguem entende por que
     nao aparece;
  5. **o registro NAO aparece como agenda de FX**: ele mora na mesma pasta e
     nao e uma lista de feriados.

Escrito ANTES de o Holidays Calendar sair do `routes.py`. Nada real e tocado: a
pasta de dados vai para um tmp.
"""
import io, json, os, sys, tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)

TMP = tempfile.mkdtemp()

from apps.pages import routes as R                          # noqa: E402
from apps import create_app                                 # noqa: E402
from apps.config import DebugConfig                         # noqa: E402

app = create_app(DebugConfig)
app.config['TESTING'] = True

# A pasta de dados vai para o tmp DEPOIS do create_app, para o seed nascer la.
R._B3_DATA_DIR = TMP

NOTIFS = []
R._create_notification = lambda actor_sid, actor_name, action, page, detail='', \
    target_role='', target_sid='': NOTIFS.append(
        {'action': action, 'page': page, 'detail': detail})

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


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


def planilha(linhas):
    """Um .xlsx de verdade — o parser e exercitado, nao stubado."""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    for l in linhas:
        ws.append(l)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _cache_limpo():
    cache = getattr(R, '_HOLIDAY_CAL_CACHE', None)
    if cache is None:                                  # depois da extracao
        from apps.pages.features.holidays.infra import persistence as HP
        cache = HP._cache
    cache['mtime'] = None
    cache['rows'] = None


print('\n== 1. sem sessao ==')
check('a pagina redireciona', anon.get('/holidays-calendar').status_code, 302)
for u in ('/api/holidays/calendars', '/api/fx-holiday-schedules'):
    check('GET %s -> 401' % u, anon.get(u).status_code, 401)
check('POST save -> 401', anon.post('/api/holidays/save', json={}).status_code, 401)
check('POST calendars -> 401', anon.post('/api/holidays/calendars', data={}).status_code, 401)

print('\n== 2. o registro se semeia na PRIMEIRA leitura ==')
# A instancia que nunca abriu a tela ja responde com os onze de sempre — e o
# arquivo passa a existir, sem "rode este script depois do pull".
check('o registro ainda nao existe', os.path.isfile(R._holiday_cal_path()
      if hasattr(R, '_holiday_cal_path') else os.path.join(TMP, 'holiday-calendars.json')), False)
st = c.get('/api/holidays/calendars')
check('200', st.status_code, 200)
d = st.get_json()
check('   ok', d['ok'], True)
nomes = [r['name'] for r in d['calendars']]
check('   os onze do seed', len(nomes), 11)
check('   com ANBIMA e SOFR entre eles',
      ['ANBIMA' in nomes, 'SOFR' in nomes], [True, True])
check('   e o arquivo foi criado', os.path.isfile(os.path.join(TMP, 'holiday-calendars.json')), True)

print('\n== 3. o Save resolve pelo REGISTRO ==')
st = c.post('/api/holidays/save', json={'calendar': 'SOFR', 'date': '2026-12-25'})
check('campo faltando', st.get_json()['error'], 'Missing fields')
st = c.post('/api/holidays/save',
            json={'calendar': 'NAO-EXISTE', 'date': '2026-12-25', 'title': 'x'})
check('calendario fora do registro', st.get_json()['ok'], False)
check('   dizendo qual', 'NAO-EXISTE' in st.get_json()['error'], True)
st = c.post('/api/holidays/save',
            json={'calendar': 'SOFR', 'date': '2026-12-25', 'title': 'Natal'})
check('grava', st.get_json()['ok'], True)
check('   e conta', st.get_json()['total'], 1)
# Cego a caixa e a espaco: o nome chega da tela e do payload, e um 'brazil '
# nao pode deixar de achar o calendario em silencio.
st = c.post('/api/holidays/save',
            json={'calendar': ' sofr ', 'date': '2026-01-01', 'title': 'Ano Novo'})
check('nome com caixa/espaco diferente ainda casa', st.get_json()['ok'], True)
# O mesmo feriado, mandado igual, nao duplica.
check('   e o mesmo feriado, igual, nao duplica',
      c.post('/api/holidays/save',
             json={'calendar': ' sofr ', 'date': '2026-01-01',
                   'title': 'Ano Novo'}).get_json()['total'], 2)
# VERRUGA CONHECIDA, registrada aqui para nao ser "corrigida" por acidente numa
# refatoracao: o nome do calendario e usado de DOIS jeitos — como chave de busca
# (cego a caixa, via `_holiday_file_for`) e como VALOR gravado em `calendar`
# (preservando a caixa que veio). A deduplicacao compara o registro inteiro,
# entao o mesmo feriado mandado como 'sofr' e depois como 'SOFR' entra DUAS
# vezes e a tela desenha o feriado repetido. O conserto e normalizar o nome pelo
# registro antes de montar a entrada — mudanca de COMPORTAMENTO, e por isso fora
# desta extracao.
check('   mas com OUTRA caixa duplica (verruga conhecida)',
      c.post('/api/holidays/save',
             json={'calendar': 'SOFR', 'date': '2026-01-01',
                   'title': 'Ano Novo'}).get_json()['total'], 3)
# O arquivo sai do REGISTRO, nao de um nome adivinhado: e essa indirecao
# que faz o Save achar tambem o calendario criado pela tela.
_sofr_file = [r['file'] for r in d['calendars'] if r['name'] == 'SOFR'][0]
gravado = json.load(io.open(os.path.join(TMP, _sofr_file), encoding='utf-8'))
check('   gravado em ordem de data', [x['date'] for x in gravado],
      ['2026-01-01', '2026-01-01', '2026-12-25'])

print('\n== 4. criar calendario: o que e recusado ==')
st = c.post('/api/holidays/calendars', data={'name': ''})
check('sem nome -> 400', (st.status_code, st.get_json()['error']),
      (400, 'Calendar name is required.'))
st = c.post('/api/holidays/calendars', data={'name': 'SOFR2'})
check('sem arquivo -> 400', st.status_code, 400)
check('   pedindo a planilha', 'spreadsheet' in st.get_json()['error'], True)
st = c.post('/api/holidays/calendars', data={
    'name': '###', 'file': (io.BytesIO(planilha([['Holiday', 'Description']])), 'x.xlsx')})
check('nome sem letra nem digito -> 400', st.status_code, 400)
check('   dizendo o porque', 'at least one letter' in st.get_json()['error'], True)
st = c.post('/api/holidays/calendars', data={
    'name': 'VAZIO',
    'file': (io.BytesIO(planilha([['Holiday', 'Description']])), 'v.xlsx')})
check('planilha so com cabecalho -> 400', st.status_code, 400)
check('   dizendo o que se esperava ler', 'Column A' in st.get_json()['error'], True)

print('\n== 5. criar calendario: o caminho feliz ==')
del NOTIFS[:]
_cache_limpo()
st = c.post('/api/holidays/calendars', data={
    'name': 'nova mesa',
    'file': (io.BytesIO(planilha([
        ['Holiday', 'Description', 'Holiday Type'],
        [datetime(2026, 5, 1), 'Labour Day', 'Full'],
        ['2026-09-07', 'Independence', 'Full'],
        ['2026-09-07', 'Repetido', 'Full'],        # mesma data: entra uma vez
        [None, 'sem data', ''],                    # descartada
        ['2026-11-15', '', ''],                    # sem descricao: descartada
    ])), 'nova.xlsx')})
check('201/200', st.status_code, 200)
d = st.get_json()
check('   ok', d['ok'], True)
check('   o nome vai em MAIUSCULA', d['calendar']['name'], 'NOVA MESA')
check('   o slug vira o arquivo', d['calendar']['file'], 'nova_mesa.json')
check('   e a classe de CSS', d['calendar']['class'], 'hc-cal-nova_mesa')
check('   com cor da paleta', d['calendar']['color'] in R._HOLIDAY_CAL_PALETTE
      if hasattr(R, '_HOLIDAY_CAL_PALETTE') else True, True)
check('   dois feriados (a data repetida entra uma vez)', d['total'], 2)
feriados = json.load(io.open(os.path.join(TMP, 'nova_mesa.json'), encoding='utf-8'))
check('   o datetime do Excel virou ISO', feriados[0]['date'], '2026-05-01')
check('   e o texto tambem', feriados[1]['date'], '2026-09-07')
check('   com o calendario carimbado', feriados[0]['calendar'], 'NOVA MESA')
check('o aviso do sino saiu', len(NOTIFS), 1)
check('   com a pagina certa', NOTIFS[0]['page'], 'Holidays Calendar')

print('\n== 6. e ele passa a ser um calendario como os outros ==')
_cache_limpo()
d = c.get('/api/holidays/calendars').get_json()
check('aparece no registro', 'NOVA MESA' in [r['name'] for r in d['calendars']], True)
st = c.post('/api/holidays/save',
            json={'calendar': 'NOVA MESA', 'date': '2026-12-31', 'title': 'Reveillon'})
check('   e aceita feriado avulso', st.get_json()['ok'], True)

print('\n== 7. os tres 409 ==')
_cache_limpo()
boa = [['Holiday', 'Description'], ['2026-05-01', 'Labour Day']]
st = c.post('/api/holidays/calendars', data={
    'name': 'NOVA MESA', 'file': (io.BytesIO(planilha(boa)), 'x.xlsx')})
check('nome repetido -> 409', st.status_code, 409)
check('   dizendo qual', 'already exists' in st.get_json()['error'], True)
# Arquivo em disco SEM linha no registro: sobrescrever apagaria uma agenda que
# alguem pode estar consumindo pelo FX holiday schedule.
io.open(os.path.join(TMP, 'solta.json'), 'w', encoding='utf-8').write('[]')
_cache_limpo()
st = c.post('/api/holidays/calendars', data={
    'name': 'SOLTA', 'file': (io.BytesIO(planilha(boa)), 'x.xlsx')})
check('arquivo ja em disco -> 409', st.status_code, 409)
check('   dizendo o nome do arquivo', 'solta.json' in st.get_json()['error'], True)

print('\n== 8. o registro nao e uma agenda de FX ==')
# Ele mora na mesma pasta; sem a excecao, apareceria como opcao de schedule.
d = c.get('/api/fx-holiday-schedules').get_json()
check('ok', d['ok'], True)
check('as agendas criadas aparecem', 'nova_mesa' in d['schedules'], True)
check('   e o REGISTRO nao', 'holiday-calendars' in d['schedules'], False)

print(('FAIL: %d' % len(fails)) if fails else 'TUDO OK')
sys.exit(1 if fails else 0)
