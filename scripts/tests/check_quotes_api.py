# -*- coding: utf-8 -*-
"""As tres rotas de Cotacoes — a casca, nao o motor.

O `check_quotes.py` (132 assercoes) protege o `quotes.py`: o de-para com
padrao `"MY"`, o periodo, a fila de rotas de saida, a sessao Kerberos. O que
ninguem prendia era o que a TELA recebe, e ali moram quatro decisoes que nao
dao erro nenhum:

  1. **fonte que nao responde e 502, nao 500.** O app esta de pe; quem falhou
     foi o BCB ou o Yahoo. Com 500 a tela diz "erro interno" e manda procurar
     o defeito no lugar errado;
  2. **subjacente sem simbolo cadastrado e 404 PEDINDO CADASTRO**, e nunca uma
     tentativa com o codigo cru: 'AAPL34' e 'AA UN' nao sao tickers de mercado,
     e a resposta seria um 404 obscuro da fonte em vez de "falta cadastrar";
  3. **as opcoes saem do Subjacente AO VIVO, so as ACTIVE**, com o simbolo
     JUNTO — a tela mostra `AAPL34 -> AAPL34.SA`, e sem isso quem escolhe nao
     distingue o que esta cadastrado do que vai falhar pedindo cadastro;
  4. **`kind` desconhecido e 404**, nao um 500 vindo de um KeyError.

Escrito ANTES de as Cotacoes sairem do `routes.py`. A rede e stubada — nada sai
da maquina.
"""
import io, json, os, sys, tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)

TMP = tempfile.mkdtemp()

from apps.pages import routes as R                          # noqa: E402
from apps.pages import quotes as Q                          # noqa: E402
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


# ── o Subjacente de mentira, com um INATIVO no meio ─────────────────────────
SUBJ = [
    {'Codigo do Ativo Subjacente': 'AAPL34', 'Classe': 'AÇÕES INTERNACIONAIS', 'STATUS': 'ACTIVE'},
    {'Codigo do Ativo Subjacente': 'PETR4',  'Classe': 'AÇÕES',                'STATUS': 'ACTIVE'},
    {'Codigo do Ativo Subjacente': 'MORTO3', 'Classe': 'AÇÕES',                'STATUS': 'INACTIVE'},
    {'Codigo do Ativo Subjacente': 'BOK6',   'Classe': 'COMMODITIES',          'STATUS': 'ACTIVE'},
]
R._B3_DATA_DIR = TMP
io.open(os.path.join(TMP, 'Subjacente.json'), 'w', encoding='utf-8').write(
    json.dumps(SUBJ, ensure_ascii=False))

# As colunas sao `LABEL`/`SYMBOL` — as mesmas do cadastro de verdade. Inventar
# nomes aqui faria o de-para devolver '' e o teste cobraria o endpoint por um
# erro que era do proprio teste.
CADASTROS = {
    'quotes-equity':    [{'LABEL': 'AAPL34', 'SYMBOL': 'AAPL34.SA'}],
    'quotes-commodity': [{'LABEL': 'BO"MY"', 'SYMBOL': 'ZL"MY".CBT'}],
}
R._mapping_rows = lambda key, *a, **kw: CADASTROS.get(key, [])


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
r = anon.get('/quotes')
check('a pagina redireciona', r.status_code, 302)
check('/api/quotes/ptax -> 401', anon.get('/api/quotes/ptax').status_code, 401)
check('/api/quotes/equity -> 401', anon.get('/api/quotes/equity').status_code, 401)

print('\n== 2. a pagina abre com um mes para tras ==')
# Quem abre a tela quer o historico recente, nao um campo vazio pedindo duas
# datas — e o padrao e o mesmo do app de desktop.
r = c.get('/quotes')
check('200', r.status_code, 200)
corpo = r.get_data(as_text=True)
hoje = datetime.now()
check('   date_to = hoje', hoje.strftime('%Y-%m-%d') in corpo, True)
check('   date_from = hoje-30',
      (hoje - timedelta(days=30)).strftime('%Y-%m-%d') in corpo, True)

print('\n== 3. as opcoes saem do Subjacente AO VIVO ==')
opcoes = R._quotes_underlyings if hasattr(R, '_quotes_underlyings') else None
if opcoes is None:                                    # depois da extracao
    from apps.pages.features.quotes import queries as _q_queries
    opcoes = _q_queries.underlyings
eq = opcoes('equity')
check('so as ACTIVE', [x[0] for x in eq], ['AAPL34', 'PETR4'])
check('   em ordem alfabetica', [x[0] for x in eq], sorted(x[0] for x in eq))
check('   com o simbolo JUNTO', dict(eq)['AAPL34'], 'AAPL34.SA')
check('   e vazio para o que nao tem cadastro', dict(eq)['PETR4'], '')
co = opcoes('commodity')
check('commodities resolve o padrao "MY"', dict(co).get('BOK6'), 'ZLK26.CBT')
check('classe desconhecida devolve vazio', opcoes('nao-existe'), [])

print('\n== 4. PTAX: o formato e o 502 da fonte ==')
_orig_ptax = Q.fetch_ptax
Q.fetch_ptax = lambda cur, ini, fim: (['Data', 'Fechamento'],
                                      [[cur, ini or 'sem', fim or 'sem']])
st = c.get('/api/quotes/ptax?currency=EUR&from=2026-08-01&to=2026-08-25')
check('200', st.status_code, 200)
d = st.get_json()
check('   colunas', d['columns'], ['Data', 'Fechamento'])
check('   os tres parametros chegam ao motor', d['rows'][0],
      ['EUR', '2026-08-01', '2026-08-25'])
st = c.get('/api/quotes/ptax')
check('sem moeda vale USD', st.get_json()['rows'][0][0], 'USD')


def _fonte_fora(*a, **kw):
    raise Q.QuotesError('o BCB nao respondeu')


Q.fetch_ptax = _fonte_fora
st = c.get('/api/quotes/ptax')
check('a fonte que nao responde -> 502', st.status_code, 502)
check('   com o motivo por extenso', st.get_json()['error'], 'o BCB nao respondeu')
Q.fetch_ptax = _orig_ptax

print('\n== 5. equity/commodity: um endpoint so ==')
# A diferenca entre as duas e so o CADASTRO de onde o simbolo sai; a fonte, as
# colunas e o formato sao identicos. Duas funcoes seriam duas copias.
_orig_ohlc = Q.fetch_ohlc
Q.fetch_ohlc = lambda sym, ini, fim: (['Date', 'Close'], [[sym, ini or 'sem']])
st = c.get('/api/quotes/equity?instrument=AAPL34&from=2026-08-01')
check('200', st.status_code, 200)
d = st.get_json()
check('   o simbolo resolvido volta na resposta', d['symbol'], 'AAPL34.SA')
check('   e e ele que vai para a fonte', d['rows'][0][0], 'AAPL34.SA')
st = c.get('/api/quotes/commodity?instrument=BOK6')
check('commodity usa o cadastro dela', st.get_json()['symbol'], 'ZLK26.CBT')

print('\n== 6. sem cadastro, PEDE cadastro ==')
st = c.get('/api/quotes/equity?instrument=PETR4')
check('404, nao uma tentativa com o codigo cru', st.status_code, 404)
d = st.get_json()
check('   diz QUAL cadastro', d['mapping'], 'quotes-equity')
check('   e a mensagem nomeia o instrumento', 'PETR4' in d['error'], True)
check('   e nao chamou a fonte', 'Mapping > quotes-equity' in d['error'], True)
st = c.get('/api/quotes/equity')
check('instrumento vazio tambem pede cadastro', st.status_code, 404)
check('   dizendo (empty)', '(empty)' in st.get_json()['error'], True)

print('\n== 7. kind desconhecido e 404, nao 500 ==')
st = c.get('/api/quotes/cripto?instrument=BTC')
check('404', st.status_code, 404)
check('   com a mensagem', st.get_json()['error'], 'Unknown quotes kind.')

print('\n== 8. a fonte fora do ar tambem e 502 aqui ==')
Q.fetch_ohlc = _fonte_fora
st = c.get('/api/quotes/equity?instrument=AAPL34')
check('502', st.status_code, 502)
Q.fetch_ohlc = _orig_ohlc

print(('FAIL: %d' % len(fails)) if fails else 'TUDO OK')
sys.exit(1 if fails else 0)
