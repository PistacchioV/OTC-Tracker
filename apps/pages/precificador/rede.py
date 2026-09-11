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
* **a saída pelo próprio Windows** (`obter`, só no Windows): o proxy do JPM
  pede autenticação (407) que o `requests` não sabe dar — a mesma que a macro
  VBA da mesa dá sem perceber, pelo WinInet. Ver o bloco `_via_winhttp`.
"""
import logging
import sys

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


# ── a saída pelo próprio Windows: o que a macro da mesa usa ─────────────────
# Na instância o proxy `proxy.jpmchase.net:9443` responde 407 (proxy
# authentication required) e a conexão direta expira. O `requests` com o
# `requests-negotiate-sspi` negocia Kerberos com o SERVIDOR de destino (o
# 401 do ADFS), não com o PROXY: o 407 fica sem resposta e a fila inteira
# morre. A macro VBA da mesa (`MSXML2.XMLHTTP`) nunca viu isso porque o
# WinInet manda as credenciais do usuário logado ao proxy sozinho. Aqui as
# duas saídas do Windows entram na fila DEPOIS das do `requests`: o WinHTTP
# (`WinHttpRequest.5.1`, com proxy explícito, auto-logon e timeouts) e, por
# último, o WinInet da macro (`MSXML2.XMLHTTP`, Opções de Internet, sem
# timeout — o último recurso, não o primeiro). A que responder fica
# memorizada no `_route_ok` do Quotes como as outras, então a chamada
# seguinte vai direto nela em vez de pagar de novo o 407 e o timeout.
# Fora do Windows (ou sem pywin32) a lista é vazia e nada muda.

_COM_WINHTTP = 'winhttp (Windows credentials)'
_COM_WININET = 'wininet (Internet Options, like the desk macro)'


def _tem_com():
    if sys.platform != 'win32':
        return False
    try:
        import win32com.client  # noqa: F401
        import pythoncom  # noqa: F401
    except ImportError:
        return False
    return True


def _proxy_winhttp():
    """`host:porta` para o `SetProxy` do WinHTTP: o proxy cadastrado do Quotes,
    senão o do sistema; vazio = a configuração do WinHTTP da máquina."""
    alvo = _q.QUOTES_PROXY or ''
    if not alvo:
        try:
            from urllib.request import getproxies
            sistema = getproxies()
            alvo = sistema.get('https') or sistema.get('http') or ''
        except Exception:                           # noqa: BLE001
            alvo = ''
    alvo = str(alvo).strip()
    if '://' in alvo:
        alvo = alvo.split('://', 1)[1]
    return alvo.rstrip('/')


def _via_winhttp(url, cab, timeout):
    """GET pelo WinHTTP: proxy explícito, credenciais do Windows no 407."""
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    try:
        req = win32com.client.Dispatch('WinHttp.WinHttpRequest.5.1')
        proxy = _proxy_winhttp()
        if proxy:
            req.SetProxy(2, proxy, '<local>')          # HTTPREQUEST_PROXYSETTING_PROXY
        ms_conn = int(_q.QUOTES_CONNECT_TIMEOUT) * 1000
        ms_io = int(timeout) * 1000
        req.SetTimeouts(ms_conn, ms_conn, ms_io, ms_io)
        req.Open('GET', url, False)
        req.SetAutoLogonPolicy(0)                     # AutoLogonPolicy_Always (após o Open)
        for k, v in cab.items():
            req.SetRequestHeader(k, v)
        req.Send()
        return int(req.Status), _corpo_com(req), str(req.StatusText or '')
    finally:
        pythoncom.CoUninitialize()


def _via_wininet(url, cab, timeout):
    """GET pelo WinInet (`MSXML2.XMLHTTP`): exatamente a macro da mesa."""
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    try:
        req = win32com.client.Dispatch('MSXML2.XMLHTTP')
        req.open('GET', url, False)
        for k, v in cab.items():
            req.setRequestHeader(k, v)
        req.send()
        return int(req.status), _corpo_com(req), str(req.statusText or '')
    finally:
        pythoncom.CoUninitialize()


def _corpo_com(req):
    """Os bytes da resposta: `responseBody` é um SAFEARRAY de bytes que o
    pywin32 entrega como `bytes`/`memoryview`; sem ele, o texto em UTF-8."""
    try:
        corpo = req.ResponseBody
        if corpo is not None:
            return bytes(corpo)
    except Exception:                               # noqa: BLE001
        pass
    return str(req.ResponseText or '').encode('utf-8')


def _rotas_com():
    if not _tem_com():
        return []
    return [(_COM_WINHTTP, _via_winhttp), (_COM_WININET, _via_wininet)]


def _uma_com(fn, nome, url, cab, timeout):
    try:
        status, corpo, texto = fn(url, cab, timeout)
    except Exception as exc:                        # noqa: BLE001
        raise _q._RouteError(_q._short_error(exc))
    if status in (407, 502, 504):
        raise _q._RouteError('the proxy answered HTTP {}'.format(status))
    if status >= 400:
        raise ErroRede('HTTP {codigo} from {url}', status=status, codigo=status, url=url)
    return corpo


def _tentativas():
    """As saídas na ordem: as do `requests` (o Quotes), depois as do Windows;
    a memorizada vai na frente, seja qual for."""
    fila = [(nome, ('requests', proxies)) for nome, proxies in _q._routes()]
    fila += [(nome, ('com', fn)) for nome, fn in _rotas_com()]
    nome_ok = _q._route_ok.get('name')
    if nome_ok:
        fila.sort(key=lambda r: 0 if r[0] == nome_ok else 1)
    return fila


def obter(url, cabecalho=None, timeout=TIMEOUT):
    """GET que devolve bytes, tentando as saídas em ordem."""
    cab = _cabecalho(cabecalho)
    tentativas = []
    for nome, (tipo, alvo) in _tentativas():
        try:
            if tipo == 'com':
                conteudo = _uma_com(alvo, nome, url, cab, timeout)
            else:
                s = _sessao(alvo)
                try:
                    conteudo = _uma(s, 'GET', url, cab, None, timeout)
                finally:
                    try:
                        s.close()
                    except Exception:               # noqa: BLE001
                        pass
        except _q._RouteError as exc:
            tentativas.append('{}: {}'.format(nome, exc))
            log.warning('[tools] %s por %s falhou: %s', url, nome, exc)
            continue
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
