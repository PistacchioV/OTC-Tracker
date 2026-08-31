"""Cache de leitura para os JSONs do dia (Operations B3, OTM Settlements,
posições B3...) que várias telas/famílias de produto reabrem para a MESMA
data dentro de um único request — e que um refresh/polling volta a pedir
segundos depois.

Duas camadas, independentes uma da outra:
  1. Por REQUEST (Flask `g`): a mesma chamada dentro do mesmo request nunca
     relê o arquivo — mata a duplicação entre famílias de produto que montam
     a mesma tela a partir dos mesmos dados.
  2. Entre requests, por `SHARED_CACHE_TTL_SECONDS` (`_shared_cache`, com
     lock próprio): um refresh de tela ou um polling segundos depois reusa o
     último resultado em vez de bater no share de rede de novo.

`bump_cache_gen` é a válvula de escape da camada 2: quem SALVA um arquivo que
um destes loaders lê deve chamá-la (com o caminho do arquivo salvo) logo
depois de gravar, para a própria edição do usuário nunca ficar escondida
atrás do TTL — a geração do dia muda, a chave de cache muda junto, e o valor
salvo antes simplesmente para de ser encontrado (não precisa apagar nada).
"""
import os
import re
import threading
import time
import functools

from flask import g, has_app_context

SHARED_CACHE_TTL_SECONDS = 5

_shared_cache_lock = threading.Lock()
_shared_cache = {}                  # key -> (valor, expira_em)
_shared_cache_gen = {}              # 'YYYYMMDD' -> geração


def cache_day_key(ref):
    """`ref` (date/datetime) normalizado para 'YYYYMMDD' — o mesmo formato que
    `bump_cache_gen` extrai do nome do arquivo salvo, para as duas pontas
    caírem na mesma geração."""
    return ref.strftime('%Y%m%d') if hasattr(ref, 'strftime') else str(ref)


def bump_cache_gen(jp):
    """Invalida o cache curto do dia codificado no nome de `jp`
    (..._YYYYMMDD.json). Chamado pelos `*_save` logo após gravar, para a
    própria edição do usuário nunca esperar o TTL."""
    m = re.search(r'(\d{8})', os.path.basename(jp))
    if not m:
        return
    with _shared_cache_lock:
        _shared_cache_gen[m.group(1)] = _shared_cache_gen.get(m.group(1), 0) + 1


def once_per_request(fn):
    """Memoiza `fn()` (sem argumentos) pela duração de UM request.

    Existe para o loader cacheado por MTIME que é consultado uma vez por LINHA.
    O cache por mtime evita reler o arquivo; ele não evita o `stat` que decide
    se o arquivo mudou — e esse stat fica DENTRO do laço de linhas.

    Em disco local o stat é um syscall e some no ruído. No share do JPM é ida e
    volta de rede: as cinco telas de Live Position resolvem o nome da
    contraparte pelo `RefData.json` uma vez por linha, e uma posição de vinte
    mil linhas pagava vinte mil stats do MESMO arquivo. A tela demora minutos e
    não há erro nenhum para ver — nem no log, porque ninguém falhou.

    Só a camada de REQUEST, de propósito: nada de TTL entre requests. O que se
    quer é matar a repetição dentro de UMA montagem de tela, e um TTL mudaria a
    resposta de quem edita o cadastro e recarrega — que é a garantia de que
    "edição na tela vale no request seguinte, sem restart".

    Fora de um request (scheduler, script de migração) não memoiza nada: a
    rotina longa tem de continuar enxergando o arquivo mudar embaixo dela.
    """
    @functools.wraps(fn)
    def wrapper():
        if not has_app_context():
            return fn()
        store = g.setdefault('_once_cache', {})
        chave = '%s.%s' % (fn.__module__, fn.__qualname__)
        if chave not in store:
            store[chave] = fn()
        return store[chave]
    return wrapper


def req_cached(fn):
    """`fn(ref, ...)` — mesma chamada não relê o arquivo: nem dentro de um
    request (todas as famílias de produto pedem o mesmo dia), nem entre
    requests dentro do TTL (refresh, polling). Fora de um request (ex.: rotina
    agendada) só o cache curto entre requests se aplica."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        day = cache_day_key(args[0]) if args else ''
        gen = _shared_cache_gen.get(day, 0)
        key = (fn.__name__, day, gen, args, tuple(sorted(kwargs.items())))
        store = g.setdefault('_req_cache', {}) if has_app_context() else None
        if store is not None and key in store:
            return store[key]
        now = time.monotonic()
        with _shared_cache_lock:
            hit = _shared_cache.get(key)
        if hit is not None and hit[1] > now:
            value = hit[0]
        else:
            value = fn(*args, **kwargs)
            with _shared_cache_lock:
                _shared_cache[key] = (value, now + SHARED_CACHE_TTL_SECONDS)
        if store is not None:
            store[key] = value
        return value
    return wrapper
