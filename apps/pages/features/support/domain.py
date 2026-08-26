# -*- coding: utf-8 -*-
"""As regras do Support Center: quem enxerga o chamado de quem, e quem o edita.

Funções PURAS — sem sessão, sem banco, sem Flask. Tudo que elas precisam saber
sobre o mundo chega por parâmetro (`is_master`, `session_role`, `roles`,
`final_statuses`). Isso não é cerimônia: antes, `_tk_can_view` fazia uma
CONSULTA AO BANCO no meio de uma checagem de permissão, e o custo dessa consulta
aparecia uma vez por linha da tela sem nada no código dizendo isso. Com o I/O
para fora, a resolução em LOTE deixou de ser uma otimização escondida e virou o
único jeito de chamar (ver `queries.py`).

── Quem enxerga o chamado de quem ──────────────────────────────────────────
O Support Center era estritamente pessoal: cada um via os PRÓPRIOS chamados e o
master via todos. A unidade passou a ser a MESA — quem é do Back Office vê os
chamados abertos pelo Back Office, quem é do Middle vê os do Middle. A fila de
uma mesa é assunto da mesa: sem isso, o colega que abriu o mesmo chamado ontem
não tinha como saber, e o time abria o mesmo pedido duas vezes.

**Ver não é poder**: editar, comentar e apagar continuam sendo do REQUESTER (e
do master), então o chamado do colega abre em leitura.

O papel vem GRAVADO no ticket (`requester_role`), e é o de quem abriu, não o que
a pessoa tem hoje: quem sai do BO para o MO não leva os chamados antigos para a
fila nova.

**Papel vazio não casa com nada.** Dois usuários sem papel no cadastro não são
uma mesa, e tratá-los como uma abriria a fila de um para o outro — nesse caso
vale a regra antiga, só o próprio.
"""


def is_requester(ticket, sid):
    """O chamado é de quem está perguntando?"""
    return (ticket.get('requester_sid') or '').upper() == (sid or '').upper()


def same_desk(ticket, session_role, roles=None):
    """O ticket foi aberto por alguém da MESMA mesa que a sessão?

    `roles` é o mapa SID → papel resolvido em LOTE por quem chama, para os
    tickets antigos que não têm o papel gravado. Sem ele, esses tickets
    respondem "não" — e uma listagem inteira de chamados anteriores ficaria
    invisível para a mesa que os abriu.
    """
    if not session_role:
        return False
    papel = str(ticket.get('requester_role') or '').strip().upper()
    if not papel and roles is not None:
        papel = roles.get((ticket.get('requester_sid') or '').strip().upper(), '')
    return bool(papel) and papel == session_role


def can_view(ticket, sid, is_master, session_role, roles=None):
    """O próprio, o da mesa, e tudo para o master."""
    if is_master or is_requester(ticket, sid):
        return True
    if not session_role:
        return False
    return same_desk(ticket, session_role, roles)


def permissions(ticket, sid, is_master, session_role, final_statuses, roles=None):
    """Os flags que a tela usa para habilitar controles.

    Calculados no servidor de propósito: a UI esconde o que o usuário não pode
    fazer, mas quem recusa de fato é o endpoint.
    """
    mine = is_requester(ticket, sid)
    return {
        'can_edit_status': is_master,
        'can_edit_due': is_master,
        'can_edit_fields': is_master or (mine and ticket.get('status') not in final_statuses),
        'can_delete': is_master or mine,
        'can_comment': is_master or mine,
        'is_requester': mine,
        # A tela precisa distinguir o chamado PRÓPRIO do chamado do colega de
        # mesa: os dois aparecem na lista, e só o primeiro se edita.
        'same_role': (not mine) and same_desk(ticket, session_role, roles),
    }


# ── O que cada campo exige de quem edita ────────────────────────────────────
# Status e prazo são do TIME que trata o chamado, não de quem o abriu (regra do
# usuário); assunto, descrição, prioridade e tags são do requester enquanto o
# chamado estiver aberto, e do master sempre.
MASTER_ONLY_FIELDS = ('status', 'due_date')
REQUESTER_FIELDS = ('subject', 'description', 'priority', 'tags')

_MASTER_ONLY_LABEL = {'status': 'status', 'due_date': 'due date'}


def refuse_change(data, is_master, perms):
    """A mudança pedida esbarra em quê? Devolve a MENSAGEM da recusa, ou None.

    Quem traduz isso em 403 é o entrypoint — a regra é de negócio, o código de
    status é protocolo. A ordem é a de sempre (campos de master primeiro), e ela
    é observável: um payload que mexe em `status` **e** em `subject` sem ser o
    master recusa citando o status.
    """
    for field in MASTER_ONLY_FIELDS:
        if field in data and not is_master:
            return 'Only the master can change the {}'.format(_MASTER_ONLY_LABEL[field])
    for field in REQUESTER_FIELDS:
        if field in data and not perms['can_edit_fields']:
            return 'Not allowed to edit this ticket'
    return None


def accepted_changes(data):
    """Só os campos que o cliente pode mandar, na ordem em que sempre entraram.

    Requester, SID e status de criação NÃO saem daqui: quem abre é sempre quem
    está logado, e todo ticket nasce `New`. Aceitar esses campos do corpo
    deixaria qualquer um abrir chamado em nome de outra pessoa.
    """
    return {f: data[f] for f in MASTER_ONLY_FIELDS + REQUESTER_FIELDS if f in data}


def clean_tags(tags):
    """As tags como a tela manda (lista ou texto separado por vírgula)."""
    if isinstance(tags, str):
        tags = [x.strip() for x in tags.split(',')]
    return [x.strip() for x in (tags or []) if str(x).strip()]


def newest_first(tickets):
    """Mais recente primeiro.

    Ordena pelo `seq`, que é monotônico, e não pela data — que é string e empata
    quando dois chamados nascem no mesmo segundo.
    """
    return sorted(tickets, key=lambda t: t.get('seq') or 0, reverse=True)


def closing_transition(status_antes, status_depois, final_statuses):
    """O chamado ACABA de ser encerrado? É o que decide o e-mail ao requester.

    O par antes/depois não é zelo: sem ele, salvar de novo um chamado já
    encerrado — mudando a prioridade, por exemplo — reenviaria o aviso de
    encerramento, e o requester receberia a mesma notícia várias vezes.
    """
    return (status_depois or '') in final_statuses and (status_antes or '') not in final_statuses
