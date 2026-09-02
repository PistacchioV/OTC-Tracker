# -*- coding: utf-8 -*-
"""As seis rotas do Support Center.

Camada FINA de tradução: lê a sessão, chama a consulta ou o comando, e devolve
JSON. As regras de quem vê e quem edita estão no `domain.py`; o que é decidido
aqui é só o CÓDIGO DE STATUS — 401 sem sessão, 404 sem chamado, 403 sem
permissão, 400 quando o pedido veio incompleto.

A ordem das checagens é observável e está preservada byte a byte: autenticação,
existência, visibilidade, e só então permissão de campo. Trocá-la muda o código
que o cliente recebe (um chamado inexistente pediu 404 antes de 403, e um 403
ali diria a quem sonda que o chamado EXISTE).
"""
from flask import jsonify, request, send_from_directory, session

from apps.pages import blueprint, otc_tickets
from apps.pages.features.support import commands, domain, queries
from apps.pages.features.support.infra import mappers


def _sessao():
    """(SID, nome, e-mail) da sessão — a única leitura de sessão da feature."""
    return ((session.get('user_sid') or '').strip().upper(),
            (session.get('user_name') or '').strip(),
            (session.get('user_email') or '').strip())


def _papel():
    return str(session.get('user_role') or '').strip().upper()


def _master():
    from apps.pages import routes
    return routes._session_is_master()


def _nao_autenticado():
    return jsonify({'success': False, 'error': 'Not authenticated'}), 401


def _erro(msg, codigo):
    return jsonify({'success': False, 'error': msg}), codigo


def _publico(ticket, sid, roles=None):
    return mappers.to_public(ticket, sid, _master(), _papel(), roles)


def _carregar(ticket_id, sid):
    """O chamado + o mapa de papéis, ou a resposta de erro já pronta.

    Devolve `(ticket, roles, None)` no caminho feliz e `(None, None, resposta)`
    quando não há o que mostrar — é o que evita repetir o par 404/403 em cada
    uma das quatro rotas que carregam um chamado.
    """
    ticket = queries.get_one(ticket_id)
    if not ticket:
        return None, None, _erro('Ticket not found', 404)
    roles = queries.roles_for(ticket)
    if not domain.can_view(ticket, sid, _master(), _papel(), roles):
        return None, None, _erro('Not allowed', 403)
    return ticket, roles, None


@blueprint.route('/api/tickets', methods=['GET'])
def api_tickets_list():
    if not session.get('authenticated'):
        return _nao_autenticado()
    sid, _name, _mail = _sessao()
    tickets, roles = queries.list_visible(sid, _master(), _papel())
    return jsonify({
        'success': True,
        'tickets': [_publico(t, sid, roles) for t in tickets],
        'counts': otc_tickets.counts(tickets),
        'is_master': _master(),
        'agent_name': otc_tickets.AGENT_NAME,
        'statuses': otc_tickets.STATUSES,
        'priorities': otc_tickets.PRIORITIES,
        'me': {'sid': sid, 'name': session.get('user_name') or '',
               'email': session.get('user_email') or ''},
    })


@blueprint.route('/api/tickets', methods=['POST'])
def api_tickets_create():
    if not session.get('authenticated'):
        return _nao_autenticado()
    sid, name, mail_addr = _sessao()
    if not sid:
        return _erro('Session has no SID', 400)
    data = request.get_json(silent=True) or {}
    subject = (data.get('subject') or '').strip()
    if not subject:
        return _erro('Subject is required', 400)
    description = (data.get('description') or '').strip()
    if not description:
        return _erro('Description is required', 400)
    ticket, envio = commands.open_ticket(
        sid, name, mail_addr, _papel(), subject, description,
        (data.get('priority') or '').strip(), data.get('tags'))
    return jsonify({'success': True, 'ticket': _publico(ticket, sid),
                    'email_sent': envio is True,
                    'email_error': None if envio is True else envio})


@blueprint.route('/api/tickets/<ticket_id>', methods=['GET'])
def api_tickets_get(ticket_id):
    if not session.get('authenticated'):
        return _nao_autenticado()
    sid, _name, _mail = _sessao()
    ticket, roles, erro = _carregar(ticket_id, sid)
    if erro:
        return erro
    return jsonify({'success': True, 'ticket': _publico(ticket, sid, roles),
                    # As imagens anexadas vão SÓ no GET de um chamado: na
                    # listagem seria um listdir do share por linha da tela.
                    'images': queries.images_for(ticket_id),
                    'statuses': otc_tickets.STATUSES,
                    'priorities': otc_tickets.PRIORITIES,
                    'agent_name': otc_tickets.AGENT_NAME})


@blueprint.route('/api/tickets/<ticket_id>', methods=['POST'])
def api_tickets_update(ticket_id):
    if not session.get('authenticated'):
        return _nao_autenticado()
    sid, name, _mail = _sessao()
    ticket, roles, erro = _carregar(ticket_id, sid)
    if erro:
        return erro
    data = request.get_json(silent=True) or {}
    perms = _publico(ticket, sid, roles)
    recusa = domain.refuse_change(data, _master(), perms)
    if recusa:
        return _erro(recusa, 403)
    changes = domain.accepted_changes(data)
    if not changes:
        return _erro('Nothing to update', 400)

    updated, events, envio = commands.update_ticket(
        ticket_id, sid, name, changes, ticket.get('status'))
    if updated is None:
        return _erro('Ticket not found', 404)
    if not events:
        return jsonify({'success': True, 'ticket': _publico(updated, sid, roles),
                        'changed': 0})
    return jsonify({'success': True, 'ticket': _publico(updated, sid, roles),
                    'changed': len(events),
                    'email_sent': envio is True,
                    'email_error': None if envio in (True, None) else envio})


@blueprint.route('/api/tickets/<ticket_id>/comment', methods=['POST'])
def api_tickets_comment(ticket_id):
    if not session.get('authenticated'):
        return _nao_autenticado()
    sid, name, _mail = _sessao()
    ticket = queries.get_one(ticket_id)
    if not ticket:
        return _erro('Ticket not found', 404)
    roles = queries.roles_for(ticket)
    if not _publico(ticket, sid, roles)['can_comment']:
        return _erro('Not allowed', 403)
    text = ((request.get_json(silent=True) or {}).get('text') or '').strip()
    if not text:
        return _erro('Comment is empty', 400)
    updated = commands.comment(ticket_id, sid, name, text)
    if updated is None:
        return _erro('Ticket not found', 404)
    return jsonify({'success': True, 'ticket': _publico(updated, sid, roles)})


@blueprint.route('/api/tickets/<ticket_id>/images', methods=['POST'])
def api_tickets_images_upload(ticket_id):
    """Anexa imagens ao chamado (multipart, campo `images`).

    Quem pode anexar é quem pode editar o CONTEÚDO do chamado
    (`can_edit_fields`: o requester enquanto aberto, o master sempre) — a
    imagem explica o problema, então é conteúdo, como a descrição.
    """
    if not session.get('authenticated'):
        return _nao_autenticado()
    sid, _name, _mail = _sessao()
    ticket, roles, erro = _carregar(ticket_id, sid)
    if erro:
        return erro
    if not _publico(ticket, sid, roles)['can_edit_fields']:
        return _erro('Not allowed', 403)
    files = [(f.filename, f.read()) for f in request.files.getlist('images') if f]
    if not files:
        return _erro('No image in the request', 400)
    try:
        saved = commands.add_images(ticket['id'], files)
    except ValueError as exc:
        return _erro(str(exc), 400)
    except OSError as exc:
        return _erro('Could not write to the images folder: {}'.format(exc), 500)
    return jsonify({'success': True, 'saved': saved,
                    'images': queries.images_for(ticket['id'])})


@blueprint.route('/api/tickets/<ticket_id>/images/<name>')
def api_tickets_image_file(ticket_id, name):
    """Serve UMA imagem do chamado. A visibilidade é a do chamado (mesma mesa
    vê); o nome só passa se for um que o store gera E com o prefixo deste
    ticket — o resto o safe_join do send_from_directory recusa."""
    if not session.get('authenticated'):
        return _nao_autenticado()
    sid, _name, _mail = _sessao()
    ticket, _roles, erro = _carregar(ticket_id, sid)
    if erro:
        return erro
    fn = str(name or '')
    tid = otc_tickets._img_tid(ticket['id'])
    if not otc_tickets._IMG_NAME_RE.match(fn) or not fn.upper().startswith(tid + '_'):
        return _erro('Image not found', 404)
    return send_from_directory(otc_tickets.images_dir(), fn, max_age=3600)


@blueprint.route('/api/tickets/<ticket_id>/images/<name>', methods=['DELETE'])
def api_tickets_image_delete(ticket_id, name):
    if not session.get('authenticated'):
        return _nao_autenticado()
    sid, _name, _mail = _sessao()
    ticket, roles, erro = _carregar(ticket_id, sid)
    if erro:
        return erro
    if not _publico(ticket, sid, roles)['can_edit_fields']:
        return _erro('Not allowed', 403)
    if not commands.remove_image(ticket['id'], name):
        return _erro('Image not found', 404)
    return jsonify({'success': True, 'images': queries.images_for(ticket['id'])})


@blueprint.route('/api/tickets/<ticket_id>', methods=['DELETE'])
def api_tickets_delete(ticket_id):
    if not session.get('authenticated'):
        return _nao_autenticado()
    sid, name, _mail = _sessao()
    ticket = queries.get_one(ticket_id)
    if not ticket:
        return _erro('Ticket not found', 404)
    if not (_master() or domain.is_requester(ticket, sid)):
        return _erro('Only the requester or the master can delete a ticket', 403)
    commands.delete_ticket(ticket, sid, name)
    return jsonify({'success': True})
