"""Quotes (Apps > Quotes) — PTAX, Equities e Commodities numa pagina so.

O que este teste protege, e que erra em SILENCIO se cair:

1. **As opcoes de Equities/Commodities sao o Subjacente do Index B3**, separado
   pelo campo `Classe`. Classe fora da lista de um tipo nao pode vazar para o
   outro: commodity aparecendo na lista de acoes pediria um ticker que o Yahoo
   nao tem, e a tela diria "sem simbolo cadastrado" para um ativo que nunca
   deveria estar ali. Inativo tambem fica de fora — ele so continua no arquivo
   para o historico nao perder o codigo.

2. **O simbolo vem do /mapping, nunca do codigo do ativo.** `AAPL34` nao e
   ticker de mercado; sem cadastro a API tem de responder 404 PEDINDO cadastro,
   e nao tentar o codigo como simbolo (o que viraria um 404 obscuro da fonte).

3. **A comparacao do rotulo e cega a caixa e a espaco repetido** — o rotulo vai
   e volta pela URL, e `'C  K5'` nao pode deixar de casar com `'C K5'`.

4. **A PTAX so traz o boletim de Fechamento.** O BCB publica varios boletins por
   dia; trazer todos poria quatro linhas no mesmo dia com valores diferentes.

5. **O `period2` do Yahoo leva um dia a mais** — o endpoint trata o fim como
   EXCLUSIVO, e sem isso o ultimo dia do periodo pedido some da tabela.

6. **`None` da fonte vira celula VAZIA, nunca `0.00`**: vazio le-se "nao teve
   pregao"; zero afirmaria um preco que nao existiu.

7. **As tres listas de opcao chegam como [codigo, simbolo]** — a tela trata as
   tres do mesmo jeito, e na PTAX o codigo E o simbolo.

Nao encosta em rede: as duas fontes sao stubadas. Nao encosta em dado real: o
Subjacente e o cadastro sao redirecionados para um tempfile.
"""
import io
import json
import os
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from apps.pages import quotes as Q                            # noqa: E402
from apps.pages import routes as R                            # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label
          + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def read(rel):
    return io.open(os.path.join(ROOT, rel), encoding='utf-8', errors='ignore').read()


# ── 1. Opcoes: Subjacente x Classe ────────────────────────────────────────────
print('\n1. Opcoes vindas do Subjacente (Index B3), por Classe')

tmp = tempfile.mkdtemp(prefix='qt-')
SUBJ = [
    {'Codigo do Ativo Subjacente': 'PETR4', 'Classe': 'AÇÕES', 'STATUS': 'ACTIVE'},
    {'Codigo do Ativo Subjacente': 'AAPL34', 'Classe': 'AÇÕES INTERNACIONAIS', 'STATUS': 'ACTIVE'},
    {'Codigo do Ativo Subjacente': 'IBOV', 'Classe': 'INDICES', 'STATUS': 'ACTIVE'},
    {'Codigo do Ativo Subjacente': 'SPX', 'Classe': 'INDICES INTERNACIONAIS', 'STATUS': 'ACTIVE'},
    {'Codigo do Ativo Subjacente': 'BRT', 'Classe': 'COMMODITIES', 'STATUS': 'ACTIVE'},
    {'Codigo do Ativo Subjacente': 'WTI', 'Classe': 'COMMODITIES', 'STATUS': 'ACTIVE'},
    # Inativo: fica no arquivo, some da tela.
    {'Codigo do Ativo Subjacente': 'VELHO3', 'Classe': 'AÇÕES', 'STATUS': 'INACTIVE'},
    # Classe que nao pertence a nenhum dos dois tipos.
    {'Codigo do Ativo Subjacente': 'JUROS', 'Classe': 'TAXA DE JUROS', 'STATUS': 'ACTIVE'},
]
with io.open(os.path.join(tmp, 'Subjacente.json'), 'w', encoding='utf-8') as fh:
    json.dump(SUBJ, fh, ensure_ascii=False)

MAPS = {
    'quotes-equity': [{'LABEL': 'PETR4', 'SYMBOL': 'PETR4.SA', 'NOTES': ''},
                      {'LABEL': ' aapl34 ', 'SYMBOL': 'AAPL34.SA', 'NOTES': ''}],
    'quotes-commodity': [{'LABEL': 'BRT', 'SYMBOL': 'BZ=F', 'NOTES': ''}],
}

_dir_orig, _rows_orig = R._B3_DATA_DIR, R._mapping_rows
R._B3_DATA_DIR = tmp
R._mapping_rows = lambda key: list(MAPS.get(key) or [])
R._quotes_underlying_cache['mtime'] = None
try:
    eq = R._quotes_underlyings('equity')
    com = R._quotes_underlyings('commodity')
finally:
    R._B3_DATA_DIR, R._mapping_rows = _dir_orig, _rows_orig
    R._quotes_underlying_cache['mtime'] = None

check('equity traz as quatro classes de papel/indice, em ordem, sem o INACTIVE',
      [p[0] for p in eq], ['AAPL34', 'IBOV', 'PETR4', 'SPX'])
check('commodity traz so a classe COMMODITIES',
      [p[0] for p in com], ['BRT', 'WTI'])
check('classe de fora (TAXA DE JUROS) nao entra em nenhum dos dois',
      ['JUROS' in [p[0] for p in eq], 'JUROS' in [p[0] for p in com]], [False, False])
check('o simbolo cadastrado vem junto (par [codigo, simbolo])',
      dict(eq)['PETR4'], 'PETR4.SA')
check('sem cadastro, o simbolo vem VAZIO — e o que a tela usa para avisar antes da busca',
      dict(eq)['IBOV'], '')
check('cadastro com caixa/espaco diferente ainda casa', dict(eq)['AAPL34'], 'AAPL34.SA')
check('tipo desconhecido devolve lista vazia, nao erro', R._quotes_underlyings('nope'), [])


# ── 2. symbol_for: cego a caixa e a espaco ────────────────────────────────────
print('\n2. symbol_for — o de-para do /mapping')

rows = [{'LABEL': 'C K5', 'SYMBOL': 'ZC=F'}, {'LABEL': 'BRT', 'SYMBOL': 'BZ=F'}]
check('casa exato', Q.symbol_for(rows, 'BRT'), 'BZ=F')
check('casa cego a caixa e a espaco repetido', Q.symbol_for(rows, ' c  k5 '), 'ZC=F')
check('sem cadastro devolve vazio (a rota traduz em 404 pedindo cadastro)',
      Q.symbol_for(rows, 'IBOV'), '')
check('_label_key normaliza os dois lados', Q._label_key(' aa  bb '), 'AA BB')


# ── 3. Periodo ────────────────────────────────────────────────────────────────
print('\n3. Periodo — os dois formatos e a data invertida')

check('ISO', str(Q._parse_date('2026-08-17', 'x')), '2026-08-17')
check('dd/mm/aaaa', str(Q._parse_date('17/08/2026', 'x')), '2026-08-17')
try:
    Q._parse_date('17-08-2026 xx', 'start date')
    check('data invalida levanta QuotesError', 'nao levantou', 'QuotesError')
except Q.QuotesError as e:
    check('data invalida levanta QuotesError com o motivo por extenso',
          'Invalid start date' in str(e), True)
try:
    Q._period('2026-08-17', '2026-08-01')
    check('fim antes do inicio levanta', 'nao levantou', 'QuotesError')
except Q.QuotesError as e:
    check('fim antes do inicio levanta (e nao devolve tabela vazia)',
          'earlier' in str(e), True)


# ── 4. _num: None e celula vazia, nunca zero ──────────────────────────────────
print('\n4. _num — vazio nao e zero')

check('None vira vazio', Q._num(None, 4), '')
check('texto ilegivel vira vazio', Q._num('n/a', 4), '')
check('zero de verdade continua zero', Q._num(0, 2), '0.00')
check('casas decimais respeitadas', Q._num(5.4321987, 6), '5.432199')
check('milhar no formato da tela', Q._num(1234567.5, 2), '1,234,567.50')


# ── 5. PTAX: so o boletim de Fechamento ───────────────────────────────────────
print('\n5. fetch_ptax — Fechamento, ordem e o formato do parametro')

capturado = {}


def fake_json(payload):
    def _f(url, params, fonte):
        capturado['url'] = url
        capturado['params'] = params
        capturado['fonte'] = fonte
        return payload
    return _f


PTAX_PAYLOAD = {'value': [
    {'tipoBoletim': 'Abertura', 'dataHoraCotacao': '2026-08-14 10:02:00.000',
     'cotacaoCompra': 5.10, 'cotacaoVenda': 5.11, 'paridadeCompra': 1.0, 'paridadeVenda': 1.0},
    {'tipoBoletim': 'Fechamento', 'dataHoraCotacao': '2026-08-14 13:09:00.000',
     'cotacaoCompra': 5.4321, 'cotacaoVenda': 5.4327, 'paridadeCompra': 1.0, 'paridadeVenda': 1.0},
    {'tipoBoletim': 'Fechamento', 'dataHoraCotacao': '2026-08-17 13:09:00.000',
     'cotacaoCompra': 5.5000, 'cotacaoVenda': 5.5006, 'paridadeCompra': 1.0, 'paridadeVenda': 1.0},
]}

_get_orig = Q._get_json
Q._get_json = fake_json(PTAX_PAYLOAD)
try:
    cols, prows = Q.fetch_ptax('usd', '2026-08-14', '2026-08-17')
finally:
    Q._get_json = _get_orig

check('colunas da PTAX', cols, list(Q.PTAX_COLUMNS))
check('so o Fechamento entra (a Abertura do mesmo dia fica de fora)', len(prows), 2)
check('mais recente primeiro', [r[0] for r in prows], ['17/08/2026', '14/08/2026'])
check('data em dd/mm/aaaa e moeda em MAIUSCULA', prows[1][:2], ['14/08/2026', 'USD'])
check('valor com 4 casas', prows[1][2], '5.4321')
check('o Olinda recebe a data em mm-dd-aaaa, entre aspas',
      [capturado['params']['@dataInicial'], capturado['params']['@dataFinalCotacao']],
      ["'08-14-2026'", "'08-17-2026'"])
check('a moeda vai entre aspas simples (odata)', capturado['params']['@moeda'], "'USD'")
check('a fonte se nomeia no erro', capturado['fonte'], 'PTAX (BCB)')

try:
    Q.fetch_ptax('BRL', '2026-08-14', '2026-08-17')
    check('moeda fora do dominio do BCB levanta', 'nao levantou', 'QuotesError')
except Q.QuotesError as e:
    check('moeda fora do dominio do BCB levanta em vez de devolver vazio',
          'PTAX' in str(e), True)


# ── 6. Yahoo: period2 exclusivo, None vazio, ordem ────────────────────────────
print('\n6. fetch_ohlc — o dia a mais no period2 e o None da fonte')

from datetime import datetime, timedelta                       # noqa: E402

YF_PAYLOAD = {'chart': {'error': None, 'result': [{
    'timestamp': [int(datetime(2026, 8, 14, 12).timestamp()),
                  int(datetime(2026, 8, 17, 12).timestamp())],
    'indicators': {
        'quote': [{'close': [10.5, None], 'high': [11.0, None], 'low': [10.0, None],
                   'open': [10.2, None], 'volume': [1500, None]}],
        'adjclose': [{'adjclose': [10.4, None]}],
    },
}]}}

Q._get_json = fake_json(YF_PAYLOAD)
try:
    cols, yrows = Q.fetch_ohlc('PETR4.SA', '2026-08-14', '2026-08-17')
finally:
    Q._get_json = _get_orig

check('colunas do OHLCV', cols, list(Q.OHLC_COLUMNS))
check('mais recente primeiro', [r[0] for r in yrows], ['17/08/2026', '14/08/2026'])
check('None da fonte vira celula VAZIA, nunca 0.00', yrows[0][1:], ['', '', '', '', '', ''])
check('valor com 6 casas e volume com 2', yrows[1][1:], ['10.400000', '10.500000',
                                                         '11.000000', '10.000000',
                                                         '10.200000', '1,500.00'])
check('period2 e o dia SEGUINTE ao fim pedido (o endpoint trata o fim como exclusivo)',
      capturado['params']['period2'],
      int((datetime(2026, 8, 17) + timedelta(days=1)).timestamp()))
check('period1 e o inicio pedido', capturado['params']['period1'],
      int(datetime(2026, 8, 14).timestamp()))
check('intervalo diario', capturado['params']['interval'], '1d')
check('o simbolo vai no CAMINHO, nao em parametro', capturado['url'].endswith('/PETR4.SA'), True)

Q._get_json = fake_json({'chart': {'error': {'description': 'No data found'}, 'result': None}})
try:
    Q.fetch_ohlc('NAOEXISTE', '2026-08-14', '2026-08-17')
    check('erro do Yahoo vira QuotesError', 'nao levantou', 'QuotesError')
except Q.QuotesError as e:
    check('erro do Yahoo vira QuotesError com a descricao da fonte',
          'No data found' in str(e), True)
finally:
    Q._get_json = _get_orig


# ── 7. A sessao e a da Athena, com o proxy dos endpoints externos ─────────────
print('\n7. Sessao — Kerberos da Athena + proxy explicito')

src = read('apps/pages/quotes.py')
check('a sessao sai do athena_api (uma forma de autenticar para todas as APIs)',
      'athena_api.build_session()' in src, True)
check('o proxy e escrito na sessao, nao herdado do ambiente',
      'session.proxies.update' in src, True)
# A dependencia e o que conta, nao a palavra: o cabecalho do modulo explica
# justamente por que o `yf.download` do app de desktop nao foi portado.
check('nao importa yfinance (uma dependencia a menos e um caminho de rede a menos)',
      [l for l in src.splitlines()
       if l.startswith(('import ', 'from ')) and 'yfinance' in l], [])


# ── 8. Rotas, pagina e menu ───────────────────────────────────────────────────
print('\n8. Rotas, pagina e menu')

rsrc = read('apps/pages/routes.py')
check('a rota da pagina existe', "@blueprint.route('/quotes')" in rsrc, True)
check('a API da PTAX existe', "@blueprint.route('/api/quotes/ptax')" in rsrc, True)
check('a API por tipo existe', "@blueprint.route('/api/quotes/<kind>')" in rsrc, True)
check('sem simbolo cadastrado a API responde 404 PEDINDO cadastro, e nao tenta o codigo',
      "'mapping': cadastro" in rsrc and 'has no market symbol registered' in rsrc, True)
check('a PTAX chega como [codigo, simbolo], como as outras duas',
      'currencies=[[c, c] for c in _q.PTAX_CURRENCIES]' in rsrc, True)

nav = read('apps/templates/partials/sidenav.html')
check('o item Quotes esta no sidenav (e o que o Page_Access enxerga)',
      'href="/quotes"' in nav, True)
check('o item traduz por data-lang', 'data-lang="quotes"' in nav, True)

html = read('apps/templates/pages/quotes.html')
check('combobox de tipo', 'id="qt-kind"' in html, True)
check('combobox de instrumento NASCE desabilitado', 'id="qt-instrument"' in html
      and 'disabled' in html.split('id="qt-instrument"')[1][:200], True)
check('o Search nasce desabilitado junto', 'id="qtSearch" disabled' in html, True)
check('nao usa .card para o widget proprio (CLAUDE.md §7)',
      'class="card' in html, False)
check('a linha de filtro por coluna existe no thead', 'id="qtFilterRow"' in html, True)
check('toolbar com mb-3, nao mb-2', 'gap-2 mb-3' in html, True)
check('export completo: Copy, CSV, Excel, Print, PDF',
      [t in html for t in ('data-export="copy"', 'data-export="csv"', 'data-export="excel"',
                           'data-export="print"', 'data-export="pdf"')],
      [True] * 5)
check('carrega o table-std.js (selecao de celula para copiar)',
      'js/table-std.js' in html, True)

js = read('apps/static/js/pages/quotes.js')
check('a linha de filtro e montada ANTES do .DataTable(), com orderCellsTop',
      js.index('filt.appendChild(tf)') < js.index(".DataTable({") and 'orderCellsTop: true' in js,
      True)
check('autoWidth: true (senao o cabecalho e o corpo medem larguras diferentes)',
      'autoWidth: true' in js, True)
check('columns.adjust() depois do draw, com o segundo passe atrasado',
      'dt.columns.adjust()' in js and 'setTimeout' in js, True)
check('chama o otcCellCopy', 'otcCellCopy' in js, True)
check('CSV com ; e BOM (o que o Excel pt-BR precisa)',
      "fieldSeparator: ';'" in js and 'bom: true' in js, True)
check('texto montado em JS sai do mapa _TRANS local, lendo o idioma do localStorage',
      '_TRANS' in js and '__OTC_TRACKER_LANG__' in js, True)
check('o segundo combobox so habilita depois do tipo',
      'inp.disabled = !kind' in js, True)
check('o codigo digitado e validado contra a lista do tipo antes de ir a rede',
      'function chosen()' in js, True)
check('nao sobrou codigo das abas antigas',
      ['qtTabs' in js, 'selectTab' in js, 'state.tab' in js], [False, False, False])


# ── 9. Cadastros e traducoes ──────────────────────────────────────────────────
print('\n9. Cadastros /mapping e traducoes')

check('os dois cadastros estao no _MAPPING_DEFS',
      ["'quotes-equity':" in rsrc, "'quotes-commodity':" in rsrc], [True, True])
mp = read('apps/templates/pages/mapping.html')
check('e os dois aparecem na tela de Mapping',
      ["'quotes-equity'" in mp, "'quotes-commodity'" in mp], [True, True])

for key in ('quotes-equity', 'quotes-commodity'):
    fp = os.path.join(ROOT, 'apps', 'static', 'data', 'mappings', key + '.json')
    check('o JSON de %s esta versionado' % key, os.path.exists(fp), True)
    if os.path.exists(fp):
        data = json.load(io.open(fp, encoding='utf-8'))
        check('%s: todas as linhas tem LABEL e SYMBOL' % key,
              all(str(r.get('LABEL') or '').strip() and str(r.get('SYMBOL') or '').strip()
                  for r in data), True)
        chaves = [Q._label_key(r.get('LABEL')) for r in data]
        check('%s: sem LABEL repetido (dois simbolos para o mesmo ativo)' % key,
              len(chaves), len(set(chaves)))

# O `.SA` e regra de papel BRASILEIRO — em commodity ele casaria por acaso
# (`AULF27` tem a mesma forma) e pediria ao Yahoo um ticker que nao existe.
com_json = json.load(io.open(os.path.join(
    ROOT, 'apps', 'static', 'data', 'mappings', 'quotes-commodity.json'), encoding='utf-8'))
check('nenhuma commodity foi semeada com o sufixo .SA',
      [r['SYMBOL'] for r in com_json if str(r['SYMBOL']).upper().endswith('.SA')], [])

CHAVES = ('quotes', 'qt-kind', 'qt-kind-ptax', 'qt-kind-equity', 'qt-kind-commodity',
          'qt-instrument', 'qt-from', 'qt-to', 'qt-search', 'qt-columns', 'qt-export',
          'qt-clear-filters', 'qt-empty')
for lang in ('en', 'br', 'es'):
    tr = json.load(io.open(os.path.join(
        ROOT, 'apps', 'static', 'data', 'translations', lang + '.json'), encoding='utf-8'))
    faltando = [k for k in CHAVES if k not in tr]
    check('%s.json tem todas as chaves da tela' % lang, faltando, [])

# Toda chave data-lang da pagina precisa existir nas tres traducoes: sem a
# entrada, o texto fica no ingles do template e a pagina sai bilingue.
import re                                                      # noqa: E402
usadas = sorted(set(re.findall(r'data-lang="([^"]+)"', html)))
en = json.load(io.open(os.path.join(ROOT, 'apps', 'static', 'data', 'translations', 'en.json'),
                       encoding='utf-8'))
check('nenhuma data-lang da pagina esta fora do en.json',
      [k for k in usadas if k not in en], [])


print('\n' + ('FAIL: %d' % len(fails) if fails else 'todos ok'))
sys.exit(1 if fails else 0)
