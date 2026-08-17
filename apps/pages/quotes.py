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

**Mas o proxy volta, explícito.** O `build_session` desliga o `trust_env` de
propósito, porque a Athena é host INTERNO e herdar o proxy corporativo dava
`WinError 10061` (CLAUDE.md §8). BCB e Yahoo são o oposto: são internet, e sem
o proxy corporativo a conexão simplesmente não sai da rede JPM. Por isso o proxy
é escrito na sessão aqui — o mesmo `proxy.jpmchase.net:10443` que o app de
desktop usava —, e não herdado do ambiente: herdado, ele voltaria a valer também
para a Athena.

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

from apps.pages import athena_api

log = logging.getLogger('otc_tracker')

# O proxy corporativo — só para os endpoints de INTERNET (BCB, Yahoo). Nunca
# para a Athena: ela é interna e o proxy a recusa.
QUOTES_PROXY = os.getenv('QUOTES_PROXY', 'http://proxy.jpmchase.net:10443')
QUOTES_TIMEOUT = int(os.getenv('QUOTES_TIMEOUT', '30') or 30)

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


def _session():
    """A sessão da Athena (Kerberos) com o proxy dos endpoints externos."""
    session = athena_api.build_session()
    if QUOTES_PROXY:
        session.proxies.update({'http': QUOTES_PROXY, 'https': QUOTES_PROXY})
    return session


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


def _get_json(url, params, fonte):
    """GET com a sessão Kerberos + proxy, devolvendo JSON.

    Toda falha vira `QuotesError` com o nome da FONTE: fora da rede JPM as três
    abas falham, e "Yahoo Finance: timeout" responde a pergunta que um stack
    trace na tela não responde."""
    try:
        session = _session()
    except RuntimeError as exc:                       # requests ausente
        raise QuotesError(str(exc))
    try:
        resp = session.get(url, params=params, timeout=QUOTES_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except QuotesError:
        raise
    except Exception as exc:                          # noqa: BLE001
        log.warning('[quotes] %s falhou (%s): %s', fonte, url, exc)
        raise QuotesError('{}: {}'.format(fonte, exc))
    finally:
        try:
            session.close()
        except Exception:                             # noqa: BLE001
            pass


def symbol_for(rows, label):
    """Símbolo cadastrado para o rótulo escolhido na tela, ou ''.

    A comparação é cega a caixa e a espaço repetido: o rótulo vai e volta pela
    URL, e `'C  K5'` não pode deixar de casar com `'C K5'`."""
    alvo = _label_key(label)
    for r in (rows or []):
        if _label_key(r.get('LABEL')) == alvo:
            return str(r.get('SYMBOL') or '').strip()
    return ''


def _label_key(v):
    return re.sub(r'\s+', ' ', str(v or '')).strip().upper()
