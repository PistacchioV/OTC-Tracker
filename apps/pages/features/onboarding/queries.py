# -*- coding: utf-8 -*-
"""As duas leituras do Onboarding. Nenhuma delas escreve nada."""
from apps.pages import cgd_docs
from apps.pages.features.onboarding.infra import mappers, persistence


def _rows():
    """As linhas, ou lista vazia quando o banco ainda não foi importado.

    O `db_ready` volta junto porque a tela precisa dos dois: sem linha nenhuma
    e sem saber se o banco existe, ela não tem como dizer se o resultado é
    *"nada pendente"* ou *"ninguém importou ainda"*.
    """
    existe, path = persistence.db_ready()
    return (cgd_docs.load_all() if existe else []), existe, path


def overview():
    """As filas do Overview mais os contadores dos cards.

    Os quatro números FECHAM (`total = pending + active + closed`): com três, a
    diferença entre o total e a soma era justamente o que tinha sumido das
    filas.
    """
    gen = cgd_docs.generation()          # ANTES das linhas: ver `docs`
    rows, existe, path = _rows()
    data = cgd_docs.overview(rows)
    data.update({'db': path, 'db_ready': existe, 'counts': cgd_docs.counts(rows),
                 'gen': gen})
    return data


def docs():
    """A grade do Tracking Docs: as linhas com a etapa, mais os domínios."""
    # A geração é lida ANTES das linhas: uma reimportação entre as duas
    # leituras faz a tela carregar a geração VELHA com linhas novas — e a
    # primeira escrita é recusada à toa, o que é seguro. Na ordem inversa, a
    # geração nova validaria `_id`s da lista velha.
    gen = cgd_docs.generation()
    rows, existe, path = _rows()
    data = {'db': path, 'db_ready': existe, 'gen': gen,
            'rows': [mappers.with_stage(r) for r in rows]}
    data.update(mappers.field_domains())
    return data
