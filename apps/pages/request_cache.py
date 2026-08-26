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
