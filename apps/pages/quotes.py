"""Cotações — PTAX (BCB), Equities e Commodities.

Porte das três abas do app de desktop `cotaçoes.py` (CustomTkinter) para o OTC
Tracker. Só a busca: as três abas devolvem uma tabela de histórico por período,
e o resto do app desktop (DI, SOFR, IPCA, EURIBOR, calculadoras) ficou de fora.

    PTAX        BCB Olinda (odata)        Data · Moeda · CCY/BRL · CCY/USD
    Equities    Yahoo Finance (chart)     Data · Adj Close · Close · High · Low · Open · Volume
    Commodities Yahoo Finance (chart)     idem

Três decisões que não se leem no código:

**A sessão é a da Athena** (`athena_api.build_session`): Kerberos SSO,
`trust_env=False` e o User-Agent que faz o ADFS negociar. É o que foi pedido —
uma forma de autenticar para todas as APIs do app.

**Mas o proxy volta, explícito — e é uma CADEIA, não um endereço.** O
`build_session` desliga o `trust_env` de propósito, porque a Athena é host
INTERNO e herdar o proxy corporativo dava `WinError 10061` (CLAUDE.md §8). BCB e
Yahoo são o oposto: são internet, e em boa parte da rede JPM a conexão só sai
pelo proxy. Só que o `proxy.jpmchase.net:10443` que o app de desktop usava **não
atende em toda máquina** — na instância do time ele responde *connection refused*,
que é o mesmo `WinError 10061` por outro motivo (ali não há nada escutando).

Por isso a saída é tentada em ORDEM — proxy cadastrado, proxy do sistema
(`getproxies()`, que no Windows lê as Opções de Internet), conexão direta — e a
primeira que responder fica memorizada no processo. Uma máquina que sai direto e
outra que só sai por proxy usam o mesmo código, sem `.env` por máquina. Duas
consequências: o `trust_env` continua **desligado** (o proxy do sistema é copiado
para a sessão, não herdado — herdado, voltaria a valer para a Athena), e erro de
**rede** tenta a próxima rota enquanto erro de **HTTP** para na hora, porque aí a
rota funcionou e o problema é a fonte.

**Sem `yfinance`.** O app desktop usava `yf.download`, que não é dependência do
OTC Tracker e arrastaria pandas-datareader e afins. O que ele faz para OHLCV
diário é uma chamada ao endpoint `chart` do Yahoo, que devolve JSON — feita aqui
com a MESMA sessão, que é justamente o que mantém a autenticação uniforme. Uma
dependência a menos e um caminho de rede a menos para divergir.
"""
import logging
import os
import re
from datetime import datetime, timedelta
from urllib.request import getproxies

from apps.pages import athena_api
from apps.pages.otc_boxparse import has_b3_marker, split_b3_pattern

log = logging.getLogger('otc_tracker')

# O proxy corporativo — só para os endpoints de INTERNET (BCB, Yahoo). Nunca
# para a Athena: ela é interna e o proxy a recusa. `QUOTES_PROXY=` (vazio) tira
# esta rota da fila; ele é a PRIMEIRA tentativa, não a única.
QUOTES_PROXY = os.getenv('QUOTES_PROXY', 'http://proxy.jpmchase.net:9443')
# A porta que o app de desktop usava. Ela é tentada DEPOIS, e existe porque as
# duas convivem na rede: a 10443 respondeu *connection refused* na instância do
# time (WinError 10061 — não há nada escutando ali), e a 9443 é a que atende.
# Quem trocar o `QUOTES_PROXY` não perde o segundo endereço por isso.
_FALLBACK_PROXIES = ('http://proxy.jpmchase.net:10443',)
QUOTES_TIMEOUT = int(os.getenv('QUOTES_TIMEOUT', '30') or 30)
# O timeout de CONEXÃO é curto de propósito: ele é pago uma vez por rota morta,
# e com os 30 s da leitura a fila inteira faria a tela esperar um minuto e meio
# para dizer que não conectou.
QUOTES_CONNECT_TIMEOUT = int(os.getenv('QUOTES_CONNECT_TIMEOUT', '6') or 6)

# As moedas que o BCB publica na PTAX. Não é de-para: é o domínio do endpoint —
# pedir uma moeda fora desta lista devolve vazio, não erro.
PTAX_CURRENCIES = ('AUD', 'CAD', 'CHF', 'DKK', 'EUR', 'GBP', 'JPY', 'NOK', 'SEK', 'USD')

PTAX_COLUMNS = ('Date', 'Currency', 'CCY/BRL Bid', 'CCY/BRL Ask',
                'CCY/USD Bid', 'CCY/USD Ask')
OHLC_COLUMNS = ('Date', 'Adj Close', 'Close', 'High', 'Low', 'Open', 'Volume')

_PTAX_URL = ('https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/'
             'CotacaoMoedaPeriodo(moeda=@moeda,dataInicial=@dataInicial,'
             'dataFinalCotacao=@dataFinalCotacao)')
_YAHOO_URL = 'https://query1.finance.yahoo.com/v8/finance/chart/{}'


class QuotesError(Exception):
    """Falha que a tela mostra ao usuário — sempre com o motivo por extenso."""


class _RouteError(Exception):
    """Falha de REDE numa rota de saída — vale tentar a próxima.

    Separada da `QuotesError` de propósito: um HTTP 404 da fonte não melhora
    trocando de proxy, e insistir gastaria três tentativas para chegar à mesma
    resposta."""


def _session(proxies):
    """A sessão da Athena (Kerberos) com a rota de saída pedida.

    O `trust_env` continua desligado (é do `build_session`): o proxy do sistema,
    quando é a vez dele, é COPIADO para a sessão. Herdado, ele voltaria a valer
    também para a Athena, que é o host interno que o `trust_env=False` protege.
    """
    session = athena_api.build_session()
    session.proxies.clear()
    session.proxies.update(proxies or {})
    return session


def _routes():
    """As saídas a tentar, em ordem, sem repetir endereço.

    Uma máquina que sai direto e outra que só sai por proxy usam o mesmo código:
    a diferença é qual delas responde primeiro. A que responder fica memorizada
    no processo (`_route_ok`) — sem isso, toda busca pagaria de novo o timeout
    das rotas mortas que vêm antes dela.
    """
    rotas, vistos = [], set()

    def add(nome, proxies):
        chave = (proxies.get('http', ''), proxies.get('https', ''))
        if chave in vistos:
            return
        vistos.add(chave)
        rotas.append((nome, proxies))

    if QUOTES_PROXY:
        add('proxy ' + QUOTES_PROXY, {'http': QUOTES_PROXY, 'https': QUOTES_PROXY})
    try:
        sistema = getproxies()          # no Windows, as Opções de Internet
    except Exception:                   # noqa: BLE001
        sistema = {}
    alvo = sistema.get('https') or sistema.get('http')
    if alvo:
        add('system proxy ' + alvo, {'http': sistema.get('http') or alvo,
                                     'https': sistema.get('https') or alvo})
    for url in _FALLBACK_PROXIES:
        add('proxy ' + url, {'http': url, 'https': url})
    add('direct connection', {})

    nome_ok = _route_ok.get('name')
    if nome_ok:
        rotas.sort(key=lambda r: 0 if r[0] == nome_ok else 1)
    return rotas


_route_ok = {'name': None}


def _parse_date(value, label):
    """`YYYY-MM-DD` ou `dd/mm/yyyy` → date. As duas porque a tela manda ISO e
    quem chama de fora costuma mandar o formato que se lê na tela."""
    s = str(value or '').strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    raise QuotesError('Invalid {}: {!r} (use dd/mm/yyyy).'.format(label, value))


def _period(start, end):
    """(início, fim) validados. Fim antes do início é erro de quem digitou, e
    dizer isso é melhor do que devolver uma tabela vazia."""
    d1, d2 = _parse_date(start, 'start date'), _parse_date(end, 'end date')
    if d2 < d1:
        raise QuotesError('The end date is earlier than the start date.')
    return d1, d2


def _num(v, dec):
    """Número formatado como a tela mostra, ou '' quando a fonte não trouxe.

    Vazio ≠ zero: o Yahoo devolve `null` no dia sem pregão daquele papel, e um
    `0.00` ali afirmaria um preço que não existiu."""
    if v is None:
        return ''
    try:
        return '{:,.{d}f}'.format(float(v), d=dec)
    except (TypeError, ValueError):
        return ''


def fetch_ptax(currency, start, end):
    """Histórico da PTAX de uma moeda → (colunas, linhas).

    Só o boletim de **Fechamento**: o BCB publica vários boletins por dia
    (abertura e intermediários) e a cotação que a mesa usa é a de fechamento —
    trazer todos poria quatro linhas no mesmo dia, com valores diferentes.
    """
    ccy = str(currency or '').strip().upper()
    if ccy not in PTAX_CURRENCIES:
        raise QuotesError('{!r} is not published in the BCB PTAX bulletin.'.format(currency))
    d1, d2 = _period(start, end)
    params = {
        '@moeda': "'{}'".format(ccy),
        # O Olinda espera mm-dd-aaaa neste endpoint.
        '@dataInicial': "'{}'".format(d1.strftime('%m-%d-%Y')),
        '@dataFinalCotacao': "'{}'".format(d2.strftime('%m-%d-%Y')),
        '$format': 'json',
        '$select': ('paridadeCompra,paridadeVenda,cotacaoCompra,cotacaoVenda,'
                    'dataHoraCotacao,tipoBoletim'),
    }
    data = _get_json(_PTAX_URL, params, 'PTAX (BCB)')
    rows = []
    for item in (data.get('value') or []):
        if str(item.get('tipoBoletim', '')).strip().lower() != 'fechamento':
            continue
        stamp = str(item.get('dataHoraCotacao') or '')
        try:
            dia = datetime.strptime(stamp[:10], '%Y-%m-%d').strftime('%d/%m/%Y')
        except ValueError:
            dia = stamp
        rows.append([dia, ccy,
                     _num(item.get('cotacaoCompra'), 4), _num(item.get('cotacaoVenda'), 4),
                     _num(item.get('paridadeCompra'), 4), _num(item.get('paridadeVenda'), 4)])
    rows.sort(key=_row_date_key, reverse=True)
    return list(PTAX_COLUMNS), rows


def fetch_ohlc(symbol, start, end):
    """Histórico diário de um símbolo do Yahoo → (colunas, linhas).

    O `period2` leva um dia a mais porque o endpoint trata o fim como
    EXCLUSIVO — sem isso o último dia do período pedido some da tabela, que é o
    mesmo `+ timedelta(days=1)` que o app de desktop fazia no `yf.download`.
    """
    sym = str(symbol or '').strip()
    if not sym:
        raise QuotesError('No market symbol given.')
    d1, d2 = _period(start, end)
    params = {
        'period1': int(datetime(d1.year, d1.month, d1.day).timestamp()),
        'period2': int((datetime(d2.year, d2.month, d2.day) + timedelta(days=1)).timestamp()),
        'interval': '1d',
        'events': 'div,split',
    }
    data = _get_json(_YAHOO_URL.format(sym), params, 'Yahoo Finance')
    chart = (data.get('chart') or {})
    if chart.get('error'):
        raise QuotesError('Yahoo Finance refused {}: {}'.format(
            sym, (chart['error'] or {}).get('description') or chart['error']))
    result = (chart.get('result') or [None])[0]
    if not result:
        raise QuotesError('No data for {} in the period.'.format(sym))
    stamps = result.get('timestamp') or []
    quote = ((result.get('indicators') or {}).get('quote') or [{}])[0]
    adj = ((result.get('indicators') or {}).get('adjclose') or [{}])[0].get('adjclose') or []

    def at(seq, i):
        return seq[i] if i < len(seq) else None

    rows = []
    for i, ts in enumerate(stamps):
        rows.append([
            datetime.fromtimestamp(ts).strftime('%d/%m/%Y'),
            _num(at(adj, i), 6),
            _num(at(quote.get('close') or [], i), 6),
            _num(at(quote.get('high') or [], i), 6),
            _num(at(quote.get('low') or [], i), 6),
            _num(at(quote.get('open') or [], i), 6),
            _num(at(quote.get('volume') or [], i), 2),
        ])
    rows.sort(key=_row_date_key, reverse=True)
    return list(OHLC_COLUMNS), rows


def _row_date_key(row):
    """Chave de ordenação da 1ª coluna (dd/mm/aaaa). A tabela abre do mais
    recente para o mais antigo; texto ordenaria 01/12 antes de 02/01."""
    try:
        return datetime.strptime(row[0], '%d/%m/%Y')
    except (ValueError, IndexError):
        return datetime.min


def _short_error(exc):
    """O motivo em UMA linha.

    A mensagem crua do urllib3 tem 400 caracteres — URL, pool, endereço do
    objeto —, e é ela que aparecia na tela: quem lê precisa saber que o proxy
    recusou, não em que posição de memória isso aconteceu.
    """
    txt = str(exc)
    baixo = txt.lower()
    if 'unable to connect to proxy' in baixo:
        return 'the proxy refused the connection'
    if 'timed out' in baixo or 'timeout' in baixo:
        return 'timed out'
    if 'getaddrinfo' in baixo or 'name or service not known' in baixo \
            or 'failed to resolve' in baixo or 'nodename nor servname' in baixo:
        return 'host not resolved'
    if 'certificate' in baixo or 'sslerror' in baixo:
        return 'SSL failure'
    if 'refused' in baixo:
        return 'connection refused'
    return type(exc).__name__


def _fetch(url, params, proxies):
    """Uma tentativa por uma rota. Erro de rede → `_RouteError` (tenta a
    próxima); erro da FONTE → `QuotesError` (a rota funcionou, para aqui).

    O 407 e os 502/504 são exceção: eles vêm DO PROXY, não da fonte, e por isso
    contam como rota ruim — parar neles esconderia a saída que funciona.
    """
    try:
        session = _session(proxies)
    except RuntimeError as exc:                       # requests ausente
        raise QuotesError(str(exc))
    try:
        try:
            resp = session.get(url, params=params,
                               timeout=(QUOTES_CONNECT_TIMEOUT, QUOTES_TIMEOUT))
        except Exception as exc:                      # noqa: BLE001
            raise _RouteError(_short_error(exc))
        if resp.status_code in (407, 502, 504):
            raise _RouteError('the proxy answered HTTP {}'.format(resp.status_code))
        if resp.status_code >= 400:
            raise QuotesError('HTTP {} from the source.'.format(resp.status_code))
        try:
            return resp.json()
        except ValueError:
            raise QuotesError('the source did not answer JSON (HTTP {}).'.format(
                resp.status_code))
    finally:
        try:
            session.close()
        except Exception:                             # noqa: BLE001
            pass


def _get_json(url, params, fonte):
    """GET com a sessão Kerberos, tentando as rotas em ordem, devolvendo JSON.

    Toda falha vira `QuotesError` com o nome da FONTE e o que cada rota
    respondeu: fora da rede JPM as três abas falham, e "Yahoo Finance: the proxy
    refused the connection; direct connection: timed out" responde a pergunta
    que um stack trace na tela não responde."""
    tentativas = []
    for nome, proxies in _routes():
        try:
            data = _fetch(url, params, proxies)
        except _RouteError as exc:
            tentativas.append('{}: {}'.format(nome, exc))
            log.warning('[quotes] %s por %s falhou: %s', fonte, nome, exc)
            continue
        if _route_ok.get('name') != nome:
            log.info('[quotes] saída em uso: %s', nome)
            _route_ok['name'] = nome
        return data
    # A rota memorizada morreu junto com as outras: esquece, para a próxima
    # busca recomeçar pela ordem natural em vez de insistir na que caiu.
    _route_ok['name'] = None
    raise QuotesError('{}: could not reach the source ({}).'.format(
        fonte, '; '.join(tentativas) or 'no route available'))


# ══════════════════════════════════════════════════════════════════════════
#  O de-para de símbolo aceita PADRÃO, não só código fechado
# ══════════════════════════════════════════════════════════════════════════
#  Um contrato futuro é a MESMA mercadoria em cada vencimento, e cadastrar linha
#  por linha eram 70 linhas para 10 mercadorias — mais uma linha nova a cada
#  vencimento que a B3 abre, para sempre. A notação é a mesma do cadastro
#  Commodities × B3 (`"MY"` = letra do mês + ano, `_` = espaço literal), então
#  quem edita os dois cadastros lê a coluna do mesmo jeito:
#
#      BO"MY"  →  ZL"MY".CBT       BOK6  → ZLK26.CBT
#      C_"MY"  →  ZC"MY".CBT      'C K6' → ZCK26.CBT
#
#  Duas assimetrias que o padrão resolve sozinho, e que são a razão de o de-para
#  literal existir para sempre se ficasse como estava:
#
#   · o ANO tem larguras diferentes nos dois lados. A B3 escreve um dígito
#     (`BOK6`) ou dois (`AULZ29`); o símbolo de mercado escreve sempre dois
#     (`ZLK26`). O dígito único é resolvido na DÉCADA corrente, virando para a
#     próxima quando o ano cairia mais de um ano no passado — contrato futuro
#     aponta para a frente, e `5` em 2026 é 2025 (o vencimento que acabou de
#     passar), nunca 2015;
#   · o `"MY"` do símbolo fica no MEIO (`ZL"MY".CBT`), porque o sufixo de bolsa
#     vem depois do vencimento. Por isso o marcador é lido dos DOIS lados, e não
#     só como prefixo.
#
#  Linha SEM `"MY"` continua sendo de-para literal, e ela **vence** o padrão: é
#  o que permite cadastrar a exceção de um vencimento só sem desmontar a regra
#  da mercadoria inteira. Equities não têm vencimento e são todas literais — o
#  mesmo motor serve os dois cadastros sem nenhum ramo por tipo.
_MONTH_LETTERS = 'FGHJKMNQUVXZ'
_CONTRACT_RE = re.compile(r'^([' + _MONTH_LETTERS + r'])([0-9]{1,2})$')


def _squeeze(v):
    """Caixa alta e SEM espaço nenhum — a forma em que os dois lados casam.

    O milho é `'C K6'` na B3 e `C_"MY"` no cadastro, cujo prefixo é `'C '`.
    Comparar contando o espaço obrigaria a acertar quantos vieram da fonte; sem
    ele, `'C  K6'` e `'CK6'` são o mesmo contrato."""
    return re.sub(r'\s+', '', str(v or '')).upper()


def _year2(digitos, hoje=None):
    """Ano do contrato em DOIS dígitos, que é como o símbolo de mercado escreve.

    Dois dígitos passam direto. O dígito único da B3 é ambíguo por dez anos, e
    a desambiguação é a do mercado futuro: a década corrente, virando para a
    seguinte quando o ano cairia mais de um ano atrás. A folga de um ano é de
    propósito — o vencimento recém-liquidado ainda é consultado."""
    if len(digitos) >= 2:
        return digitos[-2:]
    ano_hoje = (hoje or datetime.now()).year
    ano = ano_hoje - ano_hoje % 10 + int(digitos)
    if ano < ano_hoje - 1:
        ano += 10
    return '%02d' % (ano % 100)


def symbol_lookup(rows):
    """Devolve `f(código) → símbolo` para o cadastro `rows`.

    É uma FUNÇÃO e não um dicionário porque o cadastro tem duas naturezas: a
    linha literal vira índice, a linha com `"MY"` continua sendo regra e só se
    resolve contra um código concreto. Entregá-la pronta é o que deixa a tela
    resolver os ~900 subjacentes do dia lendo o cadastro uma vez só —
    `symbol_for` é o atalho para quem tem uma consulta apenas."""
    exatos, padroes = {}, []
    for r in (rows or []):
        rotulo, simbolo = str(r.get('LABEL') or ''), str(r.get('SYMBOL') or '').strip()
        if not simbolo:
            continue
        if has_b3_marker(rotulo):
            # Símbolo sem marcador é literal de propósito: a mercadoria inteira
            # respondendo por um contínuo (`ZC=F`) é cadastro válido, e aplicar
            # mês/ano nele produziria um ticker que não existe.
            alvo = split_b3_pattern(simbolo) if has_b3_marker(simbolo) else None
            cab, cau = split_b3_pattern(rotulo)
            padroes.append((_squeeze(cab), _squeeze(cau), simbolo, alvo))
        else:
            exatos[_label_key(rotulo)] = simbolo
    # Prefixo mais longo primeiro: `CO"MY"` tem de ganhar de `C_"MY"` em `COZ6`,
    # senão quem responde pelo código seria a ordem do arquivo.
    padroes.sort(key=lambda p: len(p[0]), reverse=True)

    def _busca(label):
        achado = exatos.get(_label_key(label))
        if achado:
            return achado
        cod = _squeeze(label)
        for cab, cau, simbolo, alvo in padroes:
            if not (cod.startswith(cab) and cod.endswith(cau)):
                continue
            meio = cod[len(cab):len(cod) - len(cau)] if cau else cod[len(cab):]
            # O miolo TEM de ser mês+ano de contrato. Sem essa exigência o
            # prefixo `C` do milho casaria com `CCZ6` (cacau) e com `CLZ6`
            # (WTI), devolvendo o símbolo da mercadoria errada em silêncio.
            m = _CONTRACT_RE.match(meio)
            if m:
                if alvo is None:
                    return simbolo
                return alvo[0] + m.group(1) + _year2(m.group(2)) + alvo[1]
        return ''
    return _busca


def symbol_for(rows, label):
    """Símbolo cadastrado para o rótulo escolhido na tela, ou ''.

    A comparação é cega a caixa e a espaço repetido: o rótulo vai e volta pela
    URL, e `'C  K5'` não pode deixar de casar com `'C K5'`."""
    return symbol_lookup(rows)(label)


def _label_key(v):
    return re.sub(r'\s+', ' ', str(v or '')).strip().upper()
