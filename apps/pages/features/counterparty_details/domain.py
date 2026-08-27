# -*- coding: utf-8 -*-
"""As regras puras do Counterparty Details — formatação de exibição e
normalização de payload. Sem Flask, sem arquivo, sem rede.

O grosso do domínio deste registro (normalizadores `_bank_norm`/`_cgd_norm`/
`_contacts_norm`/`_net_norm`, o parser `_cc_*` da planilha) mora na
`platform/counterparty.py` — é horizontal: summaries, advices e o TED leem o
mesmo registro. Aqui fica só o que é DESTA tela.
"""


def _contact_disp(c):
    if not c:
        return ''
    return (c.get('name') or c.get('email') or c.get('id') or '').strip()


def _acc_disp(acc):
    if not acc:
        return ''
    return (acc.get('bank') or acc.get('account') or acc.get('id') or '').strip()


def _bank_detail(spn, rec, extra=''):
    """Notification detail: 'SPN <spn> · <counterparty> · <extra>'. The leading
    'SPN <spn>' lets the bell deep-link to Reference Data filtered by that SPN."""
    name = str((rec or {}).get('COUNTERPARTY', '') or '').strip()
    head = 'SPN {} · {}'.format(spn, name) if name else 'SPN {}'.format(spn)
    return head + ' · ' + extra if extra else head


def _contact_payload(p):
    rules = p.get('rules')
    if not isinstance(rules, list):
        rules = []
    return {
        'name':   str(p.get('name', '') or '').strip(),
        'phone':  str(p.get('phone', '') or '').strip(),
        'email':  str(p.get('email', '') or '').strip(),
        'rules':  [str(r).strip() for r in rules if str(r).strip()],
        'status': str(p.get('status', 'Active') or 'Active').strip() or 'Active',
    }
