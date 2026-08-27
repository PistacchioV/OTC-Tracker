# -*- coding: utf-8 -*-
"""As leituras: as linhas Pending de hoje e as da foto de um dia anterior."""
import json

from apps.pages.features.pcx import domain
from apps.pages.features.pcx.infra import persistence


def _routes():
    """Busca ATRASADA — ver `features/support/infra/persistence.py`."""
    from apps.pages import routes
    return routes


def rows():
    """As linhas cuja situação ATUAL é Pending — a mesma resposta do chip
    Status = Pending da página: os três DBs são lidos e a categoria vem
    recomputada (`_pc_target_category`), porque uma linha que virou Ok pode
    ainda morar fisicamente no DB de pending até o re-route diário."""
    R = _routes()
    seen, rows = set(), []
    for cat in ('backlog', 'pending', 'ok'):
        for r in R._pc_load_rows(cat):
            if R._pc_target_category(r) != 'pending':
                continue
            tn = str(r.get('Trade Number', '') or '')
            key = tn or ('#%d' % len(rows))
            if key in seen:
                continue
            seen.add(key)
            rows.append(r)
    return rows


def rows_at(ref):
    """As linhas Pending de `ref` — sem data, as de hoje; com data, as do snapshot.

    Duas coisas que não dão erro nenhum se forem esquecidas:

      * o snapshot **não** passa por `_pc_target_category`. Ele já É o balde
        `pending` daquele dia; recomputar a categoria usaria o calendário de HOJE
        (aging, vencimento) e devolveria a situação atual de linhas antigas —
        exatamente o que a data de referência existe para não fazer;
      * snapshot ausente é ERRO, nunca queda para os dados de hoje. Uma planilha
        com o nome de 12/08 e o conteúdo de 13/08 é pior que planilha nenhuma:
        ninguém tem como perceber pelo arquivo.
    """
    if ref is None:
        return rows()
    path = persistence.snapshot_path(ref)
    try:
        with open(path, encoding='utf-8') as fh:
            dados = json.load(fh)
    except (IOError, OSError, json.JSONDecodeError):
        raise domain.NoSnapshot(path, ref)
    return [r for r in dados if isinstance(r, dict)] if isinstance(dados, list) else []



def status():
    return persistence.read_status()


def send_time():
    return domain.time_of(persistence.TIME_RAW)


def share_path():
    """O caminho que o card mostra — onde a planilha vive no share."""
    import os
    return os.path.join(persistence.DIR, domain.FILENAME)
