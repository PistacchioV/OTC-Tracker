# -*- coding: utf-8 -*-
"""As regras do card — puras."""

KINDS = ('otherpub', 'fwdstart')
LABEL = {'otherpub': 'NDF Other Publisher', 'fwdstart': 'NDF FWD Start'}
TIME = {'otherpub': (20, 0), 'fwdstart': (16, 30)}
# O Cc nasce com a caixa da mesa, que é quem responde pelo pedido. É DEFAULT e
# não constante: a lista gravada pelo card manda, inclusive vazia.
CC_DEFAULT = 'brazil.otc.ops@jpmorgan.com'


def subject(kind, ref):
    """`Manual Deals Closed on dd/mm/yyyy — NDF Other Publisher`.

    Em inglês como todo texto visível do app (CLAUDE.md §2), e com a ROTINA no
    fim: os dois e-mails saem no mesmo dia, e sem isso o segundo parece um
    reenvio do primeiro na caixa de quem recebe."""
    return 'Manual Deals Closed on {} — {}'.format(ref.strftime('%d/%m/%Y'),
                                                   LABEL.get(kind, kind))


def row(deal, le_names):
    """Uma linha do e-mail: Deal Id · Legal Entity · Counterparty."""
    le = str(deal.get('LE', '') or '').strip().upper()
    return {
        'deal': str(deal.get('Deal', '') or '').strip(),
        # LE sem cadastro mostra a SIGLA em vez de vazio: a coluna em branco
        # esconderia de que entidade é a operação, que é metade da pergunta.
        'le': le_names.get(le, le),
        'cpty': (str(deal.get('Client', '') or '').strip()
                 or str(deal.get('Acronym', '') or '').strip()),
    }
