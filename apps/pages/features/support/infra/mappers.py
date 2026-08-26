# -*- coding: utf-8 -*-
"""O chamado como a TELA o recebe: o ticket mais os flags de permissão."""
from apps.pages import otc_tickets
from apps.pages.features.support import domain


def to_public(ticket, sid, is_master, session_role, roles=None):
    """Ticket + os flags que habilitam os controles da tela.

    Os flags são calculados no SERVIDOR de propósito: a UI esconde o que o
    usuário não pode fazer, mas quem recusa de fato é o endpoint.
    """
    out = dict(ticket)
    out['agent_name'] = otc_tickets.AGENT_NAME
    out.update(domain.permissions(ticket, sid, is_master, session_role,
                                  otc_tickets.FINAL_STATUSES, roles))
    return out
