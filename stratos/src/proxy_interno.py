"""Os sistemas INTERNOS do JPM pelo proxy do Stratos (`get_proxied_url`).

O contêiner roda na AWS e não alcança host interno nenhum: a Athena
(`athena-app*.jpmchase.net`, `athena-reports.jpmchase.net`) e o ADFS por onde
ela autentica. O caminho da documentação do Stratos é o
`stratosblocks.utilities.get_proxied_url(internal_url, headers, files)`, que
devolve a URL do proxy, os cabeçalhos com o `target-server` e o `proxies` do
`requests`. Sem isso cada chamada fica esperando a conexão até o tempo-limite,
e o gateway do Stratos corta o pedido antes ("upstream request timeout", que a
tela lia como JSON).

Todo o app fala com a Athena por UMA sessão, a do `athena_api.build_session`
(lida pelo atributo do módulo em todos os chamadores). `instala` a embrulha:
a sessão ganha um `send` que desvia pelo proxy SÓ o host interno — a mesma
sessão vai também ao BCB e ao Yahoo (`quotes`, `precificador/rede.py`), que
são da internet e seguem pelo proxy de saída (`_proxy_do_stratos`).

O que o embrulho cuida, além de trocar a URL:
  · os REDIRECIONAMENTOS (o SSO da Athena passa pelo ADFS): cada salto é
    seguido aqui e desviado de novo, porque o `Location` aponta o host interno
    (ou é relativo a ele) e não o proxy;
  · os COOKIES: o `requests` os guardaria sob o host do proxy, e o salto
    seguinte, para o host interno, iria sem eles — eles são gravados também
    sob o host interno;
  · o `Content-Type` do pedido (o form_post do ADFS é urlencoded): pedido com
    `files=True`, que não o fixa, e o original prevalece;
  · o `resp.url` volta a ser o endereço interno (log e redirecionamento
    relativo leem dele).

Os hosts internos são os sufixos de `OTC_STRATOS_INTERNOS` (vírgulas), ou os
domínios do JPM (`SUFIXOS`). `OTC_STRATOS_PROXY_INTERNO=0` desliga. A dev nunca
importa isto. O que o proxy NÃO resolve é a AUTENTICAÇÃO: a Athena pede
Kerberos, e no Linux não há o `requests-negotiate-sspi`.
"""
import logging
import os
from urllib.parse import urlsplit

log = logging.getLogger('otc_tracker')

SUFIXOS = ('.jpmchase.net', '.jpmorganchase.com', '.jpmchase.com', '.jpmorgan.com')


def sufixos():
    lidos = tuple(s.strip().lower() for s in os.getenv('OTC_STRATOS_INTERNOS', '').split(',')
                  if s.strip())
    return lidos or SUFIXOS


def _host(url):
    return (urlsplit(url or '').hostname or '').lower()


def interno(url, suf=None):
    """O host da URL é de um sistema interno do JPM?"""
    host = _host(url)
    if not host:
        return False
    for s in suf or sufixos():
        s = s if s.startswith('.') else '.' + s
        if host == s[1:] or host.endswith(s):
            return True
    return False


def proxia(sessao, get_proxied_url, suf=None):
    """Embrulha o `send` da sessão (no objeto, não na classe): o pedido a host
    interno sai pelo proxy do Stratos, o resto como sempre. Devolve a sessão."""
    from requests.cookies import extract_cookies_to_jar

    original = sessao.send

    def send(request, **kw):
        alvo = request.url
        if not interno(alvo, suf):
            return original(request, **kw)
        seguir = kw.pop('allow_redirects', True)
        url, cabecalhos, proxies = get_proxied_url(internal_url=alvo,
                                                   headers=dict(request.headers), files=True)
        pedido = request.copy()
        tipo = request.headers.get('Content-Type')
        pedido.url = url
        pedido.headers.update(cabecalhos or {})
        if tipo:
            pedido.headers['Content-Type'] = tipo
        envio = dict(kw, proxies=proxies or kw.get('proxies'))
        resp = original(pedido, allow_redirects=False, **envio)
        # Os cookies também sob o host INTERNO: é para ele que vai o salto seguinte.
        extract_cookies_to_jar(sessao.cookies, request, resp.raw)
        resp.url = alvo
        if not seguir:
            return resp
        # O que o Session.send faria, com cada salto passando de novo por aqui.
        historico = [resp] + list(sessao.resolve_redirects(resp, request, **kw))
        resp = historico.pop()
        resp.history = historico
        return resp

    sessao.send = send
    sessao._otc_stratos_proxy = True
    return sessao


def instala():
    """Troca o `athena_api.build_session` por um que devolve a sessão com o
    desvio. Sem o `get_proxied_url` (fora do contêiner) ou com
    `OTC_STRATOS_PROXY_INTERNO=0`, nada muda. Devolve se instalou."""
    if os.getenv('OTC_STRATOS_PROXY_INTERNO', '1').strip() == '0':
        log.warning('[stratos] OTC_STRATOS_PROXY_INTERNO=0: os sistemas internos sem o proxy')
        return False
    try:
        from stratosblocks.utilities import get_proxied_url
    except ImportError:
        log.warning('[stratos] sem o stratosblocks.utilities.get_proxied_url: '
                    'os sistemas internos (Athena) ficam inalcançáveis')
        return False
    from apps.pages import athena_api
    if getattr(athena_api.build_session, '_otc_stratos_proxy', False):
        return True
    cru = athena_api.build_session

    def build_session():
        return proxia(cru(), get_proxied_url)

    build_session._otc_stratos_proxy = True
    build_session.__wrapped__ = cru
    athena_api.build_session = build_session
    log.warning('[stratos] sistemas internos pelo proxy do Stratos (%s)', ', '.join(sufixos()))
    return True
