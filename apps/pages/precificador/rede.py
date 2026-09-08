# -*- coding: utf-8 -*-
"""Saída HTTP das ferramentas — pela MESMA porta do Quotes.

O `quotes.py` já resolveu a pergunta difícil desta casa: como um host de
INTERNET (BCB, Yahoo) sai da rede do JPM. A resposta dele é a sessão Kerberos
da Athena (`athena_api.build_session`, `trust_env=False`) com o proxy voltando
explícito e em FILA — proxy cadastrado, proxy do sistema, conexão direta —,
a primeira que responder memorizada no processo (CLAUDE.md §8).

Este módulo não repete nada disso: ele consome a fila (`_routes`), a sessão
(`_session`) e a classificação de erro (`_short_error`) do Quotes. Duas
cadeias no mesmo processo seriam duas respostas para "por onde saio", e a que
divergisse falharia numa máquina só, sem erro que apontasse para cá.

O que o Quotes não tinha e as fontes daqui pedem:

* **bytes, não só JSON** — a EURIBOR chega em CSV;
* **sessão com cookie e POST** — o visualizador do Banco da Finlândia é um
  formulário ASP.NET que só entrega o arquivo depois de duas idas com cookie e
  viewstate (`SessaoNavegada`). A rota é escolhida na PRIMEIRA chamada e fica:
  trocar de saída no meio jogaria fora o cookie e o formulário voltaria ao
  começo sem dizer nada.
"""
import logging

from apps.pages import quotes as _q
from apps.pages.precificador.erros import ErroDeFonte

log = logging.getLogger('otc_tracker')

TIMEOUT = 40

# UA de navegador comum: o relatório do Banco da Finlândia responde 403 ao UA
# padrão do requests. A Athena não passa por aqui, então o UA de negociação
# do ADFS não é necessário.
UA_PADRAO = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
             '(KHTML, like Gecko) Chrome/120.0 Safari/537.36')


class ErroRede(ErroDeFonte):
    """Falha de rede. ``status`` traz o código HTTP quando houve resposta —
    um 429 pede esperar; um timeout pede olhar o proxy."""

    def __init__(self, molde, status=None, **valores):
        super().__init__(molde, **valores)
        self.status = status


def _sessao(proxies):
    try:
        return _q._session(proxies)
    except RuntimeError as exc:                     # requests ausente
        raise ErroRede(str(exc))


def _uma(sessao, metodo, url, cabecalho, dados, timeout):
    """Uma tentativa por uma rota. Erro de REDE → `_RouteError` (tenta a
    próxima); erro da FONTE → `ErroRede` (a rota funcionou, para aqui). O 407
    e os 502/504 vêm do PROXY e contam como rota ruim."""
    try:
        r = sessao.request(metodo, url, headers=cabecalho, data=dados,
                           timeout=(_q.QUOTES_CONNECT_TIMEOUT, timeout))
    except Exception as exc:                        # noqa: BLE001
        raise _q._RouteError(_q._short_error(exc))
    if r.status_code in (407, 502, 504):
        raise _q._RouteError('the proxy answered HTTP {}'.format(r.status_code))
    if r.status_code >= 400:
        raise ErroRede('HTTP {codigo} from {url}', status=r.status_code,
                       codigo=r.status_code, url=url)
    return r.content


def _cabecalho(extra):
    cab = {'User-Agent': UA_PADRAO, 'Accept': '*/*'}
    cab.update(extra or {})
    return cab


def obter(url, cabecalho=None, timeout=TIMEOUT):
    """GET que devolve bytes, tentando as saídas em ordem."""
    cab = _cabecalho(cabecalho)
    tentativas = []
    for nome, proxies in _q._routes():
        s = _sessao(proxies)
        try:
            try:
                conteudo = _uma(s, 'GET', url, cab, None, timeout)
            except _q._RouteError as exc:
                tentativas.append('{}: {}'.format(nome, exc))
                log.warning('[tools] %s por %s falhou: %s', url, nome, exc)
                continue
        finally:
            try:
                s.close()
            except Exception:                       # noqa: BLE001
                pass
        if _q._route_ok.get('name') != nome:
            log.info('[tools] saída em uso: %s', nome)
            _q._route_ok['name'] = nome
        return conteudo
    # a rota memorizada morreu junto com as outras: a próxima chamada
    # recomeça pela ordem natural em vez de insistir na que caiu
    _q._route_ok['name'] = None
    raise ErroRede('could not reach {url} ({detalhe})', url=url,
                   detalhe='; '.join(tentativas) or 'no route available')


def obter_json(url, cabecalho=None, timeout=TIMEOUT):
    import json
    bruto = obter(url, dict(cabecalho or {}, Accept='application/json'), timeout)
    try:
        return json.loads(bruto.decode('utf-8'))
    except ValueError as exc:
        pista = ''
        if b'<html' in bruto[:400].lower():
            # sintoma clássico de SSO: a página de login em vez do JSON
            pista = ' (the answer was HTML, not JSON — a sign-on page?)'
        raise ErroRede('unreadable answer from {url}: {motivo}{pista}',
                       url=url, motivo=str(exc), pista=pista) from exc


class SessaoNavegada:
    """GET e POST com cookies, pela mesma fila de saída."""

    def __init__(self, timeout=TIMEOUT, cabecalho=None):
        self.timeout = timeout
        self.cabecalho = _cabecalho(cabecalho)
        self._sessao = None
        self._nome = None

    def _pedir(self, url, dados, extra):
        cab = dict(self.cabecalho)
        cab.update(extra or {})
        metodo = 'GET' if dados is None else 'POST'
        if dados is not None:
            cab.setdefault('Content-Type', 'application/x-www-form-urlencoded')
        if self._sessao is not None:
            try:
                return _uma(self._sessao, metodo, url, cab, dados, self.timeout)
            except _q._RouteError as exc:
                raise ErroRede('could not reach {url} ({detalhe})', url=url,
                               detalhe='{}: {}'.format(self._nome, exc))
        tentativas = []
        for nome, proxies in _q._routes():
            s = _sessao(proxies)
            try:
                conteudo = _uma(s, metodo, url, cab, dados, self.timeout)
            except _q._RouteError as exc:
                tentativas.append('{}: {}'.format(nome, exc))
                s.close()
                continue
            self._sessao, self._nome = s, nome
            _q._route_ok['name'] = nome
            return conteudo
        raise ErroRede('could not reach {url} ({detalhe})', url=url,
                       detalhe='; '.join(tentativas) or 'no route available')

    def get(self, url, referer=None):
        return self._pedir(url, None, {'Referer': referer} if referer else None)

    def post(self, url, dados, referer=None):
        return self._pedir(url, dados, {'Referer': referer} if referer else None)

    def close(self):
        if self._sessao is not None:
            try:
                self._sessao.close()
            except Exception:                       # noqa: BLE001
                pass
            self._sessao = None
