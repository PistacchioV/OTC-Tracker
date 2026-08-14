"""
Support Center — armazenamento dos tickets.

Camada de dados pura: só lê/escreve o arquivo, não sabe nada de sessão, de
notificação nem de e-mail (isso fica em `routes.py`, que é quem tem o request).

Arquivo único, `apps/static/data/tickets/tickets.json`:

    {"seq": 3, "tickets": [ {...}, {...}, {...} ]}

`seq` é o contador do ID sequencial (#OTC-0001, #OTC-0002, …). Ele vive NO
ARQUIVO e nunca é derivado do maior ID existente: derivar reaproveitaria o
número de um ticket apagado, e dois tickets diferentes com o mesmo ID quebram
o histórico e o link do e-mail de encerramento.

Todo ciclo ler → alterar → gravar roda dentro de `_lock` e termina num
`_atomic_write_json`. A gravação atômica sozinha não bastaria: dois requests
que lessem a mesma versão e gravassem em seguida fariam o segundo apagar a
alteração do primeiro (mesma regra do `_cache_lock` do routes.py — ver
CLAUDE.md, seção Concurrency).
"""

import io
import json
import os
import tempfile
import threading
from datetime import datetime

_DIR = os.path.normpath(os.path.join(
    os.path.dirname(__file__), '..', 'static', 'data', 'tickets'))
_FILE = os.path.join(_DIR, 'tickets.json')

# Lock próprio, separado do `_cache_lock` do routes.py: os dois protegem
# arquivos diferentes e nunca são tomados juntos, então não há ordem de
# aquisição a respeitar (nem risco de deadlock).
_lock = threading.RLock()

ID_PREFIX = 'OTC'

# O ciclo de vida. 'New' é o único status de criação (regra do usuário) e os
# dois últimos são terminais — entrar num deles é o que dispara o e-mail de
# encerramento para o requester.
STATUSES = ['New', 'In Progress', 'Pending', 'Resolved', 'Closed']
FINAL_STATUSES = {'Resolved', 'Closed'}
OPEN_STATUSES = {'New', 'In Progress'}

PRIORITIES = ['Low', 'Medium', 'High', 'Urgent']

# O agente é fixo: não há fila de atendentes, quem responde é o time.
AGENT_NAME = 'OTC Tracker Team'


def _now():
    return datetime.now().replace(microsecond=0).isoformat(sep=' ')


def _atomic_write(path, data):
    """Grava JSON sem deixar o arquivo pela metade. Igual ao
    `_atomic_write_json` do routes.py, incluindo o fallback de Windows: lá o
    os.replace() levanta PermissionError se um leitor concorrente estiver com o
    arquivo aberto sem FILE_SHARE_DELETE."""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            pass
        with io.open(path, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        try:
            os.unlink(tmp)
        except OSError:
            pass
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read():
    """Estado bruto do arquivo. Um arquivo ausente, vazio ou corrompido vira um
    estado vazio em vez de estourar — a página de tickets não pode derrubar o
    app por causa de um JSON quebrado."""
    try:
        with io.open(_FILE, encoding='utf-8') as fh:
            data = json.load(fh)
    except (IOError, OSError, ValueError):
        return {'seq': 0, 'tickets': []}
    if not isinstance(data, dict):
        return {'seq': 0, 'tickets': []}
    tickets = data.get('tickets')
    if not isinstance(tickets, list):
        tickets = []
    try:
        seq = int(data.get('seq') or 0)
    except (TypeError, ValueError):
        seq = 0
    return {'seq': seq, 'tickets': [t for t in tickets if isinstance(t, dict)]}


def _write(state):
    os.makedirs(_DIR, exist_ok=True)
    _atomic_write(_FILE, state)


def _fmt_id(n):
    return '{}-{:04d}'.format(ID_PREFIX, n)


def _event(kind, title, detail, by_sid, by_name):
    return {'at': _now(), 'kind': kind, 'title': title, 'detail': detail or '',
            'by_sid': by_sid or '', 'by_name': by_name or ''}


def list_all():
    with _lock:
        return _read()['tickets']


def get(ticket_id):
    tid = (ticket_id or '').strip().upper()
    with _lock:
        for t in _read()['tickets']:
            if (t.get('id') or '').upper() == tid:
                return t
    return None


def create(requester_sid, requester_name, requester_email, subject, priority,
           tags, description, requester_role=''):
    """Cria o ticket e devolve o registro completo já gravado.

    Status e ID não vêm do cliente: status é sempre 'New' e o ID é o próximo da
    sequência. O requester também não — quem cria é sempre o dono, o chamador
    passa os dados da própria sessão.

    O `requester_role` é o papel de quem abriu, e fica gravado NO TICKET em vez
    de ser perguntado ao cadastro de usuários na hora de exibir: ele é o papel
    de quem abriu o chamado, não o papel que a pessoa tem hoje. Sair do Back
    Office para o Middle não leva os chamados antigos do BO para a fila do MO.
    """
    prio = priority if priority in PRIORITIES else 'Medium'
    with _lock:
        state = _read()
        seq = state['seq'] + 1
        ticket = {
            'id': _fmt_id(seq),
            'seq': seq,
            'requester_sid': (requester_sid or '').strip().upper(),
            'requester_name': (requester_name or '').strip(),
            'requester_email': (requester_email or '').strip(),
            'requester_role': (requester_role or '').strip().upper(),
            'subject': (subject or '').strip(),
            'priority': prio,
            'status': 'New',
            'tags': [x for x in (tags or []) if x],
            'description': (description or '').strip(),
            # Vazio de propósito: só o master preenche o prazo (regra do usuário).
            'due_date': '',
            'created_at': _now(),
            'updated_at': _now(),
            'closed_at': '',
            'activity': [_event('created', 'Ticket Created',
                                'Ticket submitted through the Support Center.',
                                requester_sid, requester_name)],
        }
        state['seq'] = seq
        state['tickets'].append(ticket)
        _write(state)
        return ticket


def update(ticket_id, changes, by_sid, by_name):
    """Aplica `changes` e devolve `(ticket, eventos)`.

    `eventos` é a lista de mudanças efetivamente gravadas — o chamador usa para
    decidir o que notificar e se o ticket acabou de ser encerrado. Um campo que
    chega com o mesmo valor que já estava lá não gera evento nem toca em
    `updated_at`: sem isso, abrir e salvar a tela sem mexer em nada encheria a
    timeline de ruído.

    A validação de QUEM pode mudar O QUÊ é do chamador (routes.py, que tem a
    sessão). Aqui só se garante que os valores são válidos.
    """
    tid = (ticket_id or '').strip().upper()
    labels = {'status': 'Status', 'priority': 'Priority', 'due_date': 'Due Date',
              'subject': 'Subject', 'description': 'Description', 'tags': 'Tags'}
    with _lock:
        state = _read()
        target = None
        for t in state['tickets']:
            if (t.get('id') or '').upper() == tid:
                target = t
                break
        if target is None:
            return None, []

        events = []
        for field in ('status', 'priority', 'due_date', 'subject', 'description', 'tags'):
            if field not in changes:
                continue
            new = changes[field]
            if field == 'status' and new not in STATUSES:
                continue
            if field == 'priority' and new not in PRIORITIES:
                continue
            if field == 'tags':
                new = [x for x in (new or []) if x]
            elif isinstance(new, str):
                new = new.strip()
            old = target.get(field)
            if field == 'tags':
                if list(old or []) == list(new):
                    continue
            elif (old or '') == (new or ''):
                continue

            target[field] = new
            if field == 'status':
                title = 'Status changed to "{}"'.format(new)
                detail = 'Previous status: {}.'.format(old or '—')
            elif field == 'due_date':
                title = 'Due Date set'
                detail = new or 'Due date cleared.'
            else:
                title = '{} updated'.format(labels[field])
                detail = ', '.join(new) if field == 'tags' else ''
            ev = _event(field, title, detail, by_sid, by_name)
            target.setdefault('activity', []).insert(0, ev)
            events.append({'field': field, 'old': old, 'new': new, 'event': ev})

        if events:
            target['updated_at'] = _now()
            # closed_at marca a ENTRADA no status terminal. Reabrir limpa o
            # carimbo, então um ticket que volte a ser encerrado dispara o
            # e-mail de novo — que é o que o requester espera.
            if target.get('status') in FINAL_STATUSES:
                if not target.get('closed_at'):
                    target['closed_at'] = _now()
            else:
                target['closed_at'] = ''
            _write(state)
        return target, events


def add_comment(ticket_id, text, by_sid, by_name):
    """Anota um comentário na timeline. Não muda status nem prazo."""
    tid = (ticket_id or '').strip().upper()
    body = (text or '').strip()
    if not body:
        return None
    with _lock:
        state = _read()
        for t in state['tickets']:
            if (t.get('id') or '').upper() != tid:
                continue
            ev = _event('comment', 'Comment Added', body, by_sid, by_name)
            t.setdefault('activity', []).insert(0, ev)
            t['updated_at'] = _now()
            _write(state)
            return t
    return None


def delete(ticket_id):
    """Remove o ticket. O `seq` do arquivo NÃO recua — ver o cabeçalho."""
    tid = (ticket_id or '').strip().upper()
    with _lock:
        state = _read()
        keep = [t for t in state['tickets'] if (t.get('id') or '').upper() != tid]
        if len(keep) == len(state['tickets']):
            return False
        state['tickets'] = keep
        _write(state)
        return True


def counts(tickets):
    """Números dos cards do topo da lista."""
    out = {'open': 0, 'pending': 0, 'resolved': 0, 'closed': 0, 'total': len(tickets)}
    for t in tickets:
        st = t.get('status') or ''
        if st in OPEN_STATUSES:
            out['open'] += 1
        elif st == 'Pending':
            out['pending'] += 1
        elif st == 'Resolved':
            out['resolved'] += 1
        elif st == 'Closed':
            out['closed'] += 1
    return out
