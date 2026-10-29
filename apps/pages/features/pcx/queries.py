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
    """As linhas do banco `pending` que seguem pendentes — a MESMA resposta do
    chip Status = Pending da página (`_pc_pending_rows`, uma função para as
    duas). Backlog e ok não entram (equipe, 29/10/2026)."""
    return _routes()._pc_pending_rows()


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
        from apps.pages import duck_read          # DB-only (fase 3): arquivo-dia payload-LISTA.
        dados = duck_read.day_records(path)
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
