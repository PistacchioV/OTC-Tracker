"""As fotos dos usuários no Stratos (§715): do Shared Drive, não do código.

No desktop a foto de cada pessoa é `apps/static/images/users/<sid>.jpg`, um
arquivo solto na pasta do código da instância — fora do git de propósito (são
fotos dos colegas, e o repositório fica no GitHub). Para o Stratos elas vão para
o Shared Drive da solução, em `<raiz>/images/users/` (o `stratos/envia_fotos.py`
as leva, da máquina do JPM), e este módulo faz o app enxergá-las:

  · o `platform/user_photos._names` (a lista que decide se a pessoa TEM foto ou
    fica com as iniciais) passa a somar os nomes do drive aos do estático;
  · `/static/images/users/<arquivo>` é respondido do drive quando o arquivo
    está lá, IGNORANDO A CAIXA: a tela pede `<sid minúsculo>.jpg` e as fotos da
    instância são `D566328.jpg` — no Windows isso casa, no Linux do contêiner
    não (o mesmo defeito do §713). O que não está no drive segue para o
    estático de sempre.

A pasta é LISTADA no máximo uma vez por minuto (foto nova aparece no minuto
seguinte, sem restart), como o `user_photos` faz com a dele.
"""
import logging
import os
import re
import threading
import time

log = logging.getLogger('otc_tracker')

TTL = 60.0
_ARQ = re.compile(r'/static/images/users/([A-Za-z0-9._-]+)')
_lock = threading.Lock()


def pasta(raiz):
    return os.path.join(raiz, 'images', 'users')


def indexador(dir_fotos, ttl=TTL):
    """Função que devolve `{nome minúsculo: nome real}` da pasta, relistada a
    cada `ttl` segundos. Pasta ausente: `{}`."""
    memo = {'at': None, 'idx': {}}

    def indice():
        agora = time.monotonic()
        with _lock:
            if memo['at'] is not None and agora - memo['at'] < ttl:
                return memo['idx']
        idx = {}
        try:
            with os.scandir(dir_fotos) as it:
                for e in sorted(it, key=lambda e: e.name):
                    if e.is_file():
                        idx.setdefault(e.name.lower(), e.name)
        except OSError:
            idx = {}
        with _lock:
            memo.update(at=agora, idx=idx)
        return idx
    return indice


def instala(app, raiz):
    """Liga as fotos do drive no app. Sem raiz no drive, nada muda."""
    if not raiz:
        return False
    from flask import request, send_file
    from apps.pages.platform import user_photos as UP
    dir_fotos = pasta(raiz)
    try:
        os.makedirs(dir_fotos, exist_ok=True)
    except OSError:
        log.warning('[stratos] não deu para criar %s: as fotos ficam só as do código', dir_fotos)
    indice = indexador(dir_fotos)
    if not getattr(UP._names, '_otc_stratos_fotos', False):
        original = UP._names

        def _names():
            return frozenset(original()) | frozenset(indice())

        _names._otc_stratos_fotos = True
        UP._names = _names

    def foto_do_drive():
        m = _ARQ.fullmatch(request.path or '')
        if not m:
            return None
        real = indice().get(m.group(1).lower())
        if not real:
            return None                      # o estático de sempre (ou 404)
        return send_file(os.path.join(dir_fotos, real), max_age=300)

    app.before_request(foto_do_drive)
    log.warning('[stratos] fotos dos usuários de %s (%d agora)', dir_fotos, len(indice()))
    return True
