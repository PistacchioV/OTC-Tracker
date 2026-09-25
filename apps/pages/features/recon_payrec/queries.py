# -*- coding: utf-8 -*-
"""As leituras da tela."""
import re

from apps.pages.features.recon_payrec.infra import persistence


def _routes():
    from apps.pages import routes
    return routes


def last(recon_date):
    from apps.pages.recon_payrec import load_last
    return load_last(recon_date)


def recipients():
    return persistence.load_recipients()


def _entity(le):
    """(razão social, SPN) da entidade pelo cadastro `le-spn`; sem linha
    preenchida, a razão social do seed e o SPN do Reference Data pelo nome."""
    R = _routes()
    rows = list(R._mapping_rows('le-spn') or []) + list(R._LE_SPN_SEED)
    name = spn = ''
    for r in rows:
        if str(r.get('LE', '') or '').strip().upper() != le:
            continue
        name = name or str(r.get('NAME', '') or '').strip()
        spn = spn or str(r.get('SPN', '') or '').strip()
    if name and not spn:
        spn = (R._ndfsum_refdata_spn().get(R._fcst_norm(name)) or {}).get('spn', '')
    return name, spn


def _account_text(acc):
    bank = re.sub(r'\D', '', str(acc.get('bank', '') or ''))
    return 'BCO: {} | AG: {} | CC: {}'.format(bank.zfill(3) if bank else '',
                                              str(acc.get('agency', '') or '').strip(),
                                              str(acc.get('account', '') or '').strip())


def branch_accounts(pay_receive):
    """Conta ORIGEM (quem paga) e DESTINO (quem recebe) da reversão, do
    Reference Data › Counterparty Details: a conta default APROVADA de pagamento
    de quem paga e a de recebimento de quem recebe. `pay_receive` é a visão do
    Banco: `Receive` = a MGT paga o Banco.

    Devolve (origem, destino, avisos). Conta não cadastrada vem com `account`
    vazio e um aviso ESTRUTURADO — o e-mail diz que falta, nunca inventa."""
    R = _routes()
    cpd = R._cpd_load()
    payer, receiver = ('MGT', 'JPM') if pay_receive == 'Receive' else ('JPM', 'MGT')
    avisos = []

    def _lado(le, slot):
        name, spn = _entity(le)
        rec = R._cpd_find(cpd, spn) if spn else None
        acc = R._ndfsum_default_account(R._bank_norm(rec.get('BANKING')), slot) if rec else None
        if not acc:
            avisos.append({'code': 'branch_no_account',
                           'params': {'entity': name or le, 'slot': slot},
                           'text': 'No approved {} account for {} in Counterparty Details.'.format(
                               slot, name or le)})
        return {'le': le, 'name': name or le, 'spn': spn,
                'account': _account_text(acc) if acc else ''}

    return _lado(payer, 'DEFAULT_PAY'), _lado(receiver, 'DEFAULT_RECEIVE'), avisos
