# -*- coding: utf-8 -*-
"""As leituras do Support Center. Nenhuma delas escreve nada."""
from apps.pages import otc_tickets
from apps.pages.features.support import domain
from apps.pages.features.support.infra import persistence


def list_visible(sid, is_master, session_role):
    """Os chamados que esta sessão enxerga, do mais recente para o mais antigo.

    Devolve `(tickets, roles)`: o mapa de papéis vai JUNTO porque quem monta o
    payload precisa dele para o flag `same_role`, e resolvê-lo de novo lá seria
    uma segunda consulta ao banco de usuários pela mesma resposta.
    """
    tickets = otc_tickets.list_all()
    roles = persistence.roles_for_tickets(tickets)
    if not is_master:
        tickets = [t for t in tickets
                   if domain.is_requester(t, sid)
                   or domain.same_desk(t, session_role, roles)]
    return domain.newest_first(tickets), roles


def get_one(ticket_id):
    """Um chamado pelo id, ou `None`. Quem decide se a sessão pode vê-lo é o
    `domain.can_view` — aqui é só a leitura."""
    return otc_tickets.get(ticket_id)


def roles_for(ticket):
    """O papel do requester de UM chamado, quando ele não está gravado.

    Devolve `None` para o ticket que já tem o papel — é o que diz ao domínio
    "não precisa procurar", e evita uma consulta por chamado já resolvido.
    """
    if ticket.get('requester_role'):
        return None
    return persistence.roles_by_sid([ticket.get('requester_sid')])


def images_for(ticket_id):
    """As imagens anexadas ao chamado — nome e tamanho, na ordem de inclusão.
    Só leitura de diretório; quem serve o arquivo é a rota, com o nome
    conferido pelo store."""
    return otc_tickets.list_images(ticket_id)
