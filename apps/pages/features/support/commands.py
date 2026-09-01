# -*- coding: utf-8 -*-
"""As escritas do Support Center: gravar o chamado e disparar o que vem depois.

Cada comando faz o mesmo desenho — grava, avisa o sino, manda o e-mail — e a
ORDEM importa: o e-mail e a notificação vêm DEPOIS da gravação, e a falha deles
não desfaz nada. Um chamado que não foi criado porque o SMTP está fora do ar
seria pior do que um chamado criado sem aviso, e o `email_error` volta para a
tela dizendo qual dos dois aconteceu.

Quem decide se a sessão PODE fazer a operação é o `domain.py`, chamado pelo
entrypoint antes de chegar aqui.
"""
from apps.pages import otc_tickets
from apps.pages.features.support import domain
from apps.pages.features.support.infra import mail

PAGE = 'Support'


# Ver a nota em `infra/persistence.py`: `_create_notification` é preocupação de
# plataforma e ainda mora no `routes.py`; a busca é LATE para o teste continuar
# conseguindo trocá-la por um espião.
def _notify(*a, **kw):
    from apps.pages import routes
    return routes._create_notification(*a, **kw)


def _notify_master(actor_sid, actor_name, ticket):
    """Chamado novo → sino do master apenas.

    `MASTER` não é papel de banco: é o valor que `_set_session` grava em
    `user_role` para os SIDs de `_MASTER_SIDS`, então nenhum outro usuário casa
    com esse `target_role`.
    """
    _notify(actor_sid, actor_name, 'New Ticket', PAGE,
            '#{} — {}'.format(ticket.get('id') or '', ticket.get('subject') or ''),
            target_role='MASTER')


def _notify_requester(actor_sid, actor_name, ticket, detail):
    """Atualização → sino do requester apenas. Se quem mexeu foi o próprio
    requester, não há o que avisar."""
    rsid = (ticket.get('requester_sid') or '').upper()
    if not rsid or rsid == (actor_sid or '').upper():
        return
    _notify(actor_sid, actor_name, 'Ticket Updated', PAGE, detail, target_sid=rsid)


def open_ticket(sid, name, email, session_role, subject, description, priority, tags):
    """Abre o chamado, avisa o master e manda o e-mail de abertura.

    Devolve `(ticket, resultado_do_email)` — `True` ou a mensagem de erro.
    """
    from apps.pages import routes
    ticket = otc_tickets.create(
        requester_sid=sid, requester_name=name, requester_email=email,
        subject=subject, priority=priority, tags=domain.clean_tags(tags),
        description=description, requester_role=session_role)
    routes.log.info('[tickets] %s created by %s (%s)', ticket['id'], name, sid)
    _notify_master(sid, name, ticket)
    return ticket, mail.send_opened(ticket)


def update_ticket(ticket_id, sid, name, changes, status_antes):
    """Grava as mudanças. Devolve `(atualizado, eventos, resultado_do_email)`.

    `atualizado` vem `None` quando o chamado sumiu entre a leitura e a gravação.
    Sem evento nenhum (um save que não mudou nada) não há aviso nem e-mail — a
    timeline não pode encher de linhas que não dizem nada.
    """
    from apps.pages import routes
    updated, events = otc_tickets.update(ticket_id, changes, sid, name)
    if updated is None:
        return None, [], None
    if not events:
        return updated, [], None
    routes.log.info('[tickets] %s updated by %s (%s): %s', updated['id'], name, sid,
                    ', '.join(e['field'] for e in events))
    _notify_requester(sid, name, updated, '#{} — {}'.format(
        updated['id'], '; '.join(e['event']['title'] for e in events)))
    resultado = None
    if domain.closing_transition(status_antes, updated.get('status'),
                                 otc_tickets.FINAL_STATUSES):
        resultado = mail.send_closed(updated)
    return updated, events, resultado


def comment(ticket_id, sid, name, text):
    """Comenta e avisa o requester. `None` quando o chamado não existe mais."""
    updated = otc_tickets.add_comment(ticket_id, text, sid, name)
    if updated is None:
        return None
    _notify_requester(sid, name, updated, '#{} — new comment'.format(updated['id']))
    return updated


def delete_ticket(ticket, sid, name):
    """Apaga e avisa o requester.

    O aviso existe para o caso do MASTER apagando o chamado de outra pessoa: sem
    ele, o item some da lista do requester sem explicação nenhuma.
    """
    from apps.pages import routes
    otc_tickets.delete(ticket.get('id'))
    routes.log.info('[tickets] %s deleted by %s (%s)', ticket.get('id'), name, sid)
    _notify_requester(sid, name, ticket,
                      '#{} — ticket deleted'.format(ticket.get('id') or ''))


def add_images(ticket_id, files):
    """Anexa imagens ([(nome_original, bytes)]) ao chamado — devolve os nomes
    gravados. Validação (extensão, tamanho, lote tudo-ou-nada) é do store."""
    return otc_tickets.save_images(ticket_id, files)


def remove_image(ticket_id, name):
    """Remove UMA imagem do chamado (nome conferido pelo store)."""
    return otc_tickets.delete_image(ticket_id, name)
