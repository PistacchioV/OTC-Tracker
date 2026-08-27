# -*- coding: utf-8 -*-
"""As leituras do card: o cadastro de bankers, os grupos e os rascunhos."""
import re

from apps.pages.features.sigcoll import domain


def _routes():
    """Busca ATRASADA — ver `features/support/infra/persistence.py`."""
    from apps.pages import routes
    return routes


def bankers_index():
    """{ nome normalizado → e-mail }, do cadastro **Mapping › Bankers E-mails**.

    Era uma lista mantida à mão no `signature_collection_bankers.json`, com 58
    nomes: banker novo só entrava por commit, e enquanto isso o e-mail de coleta
    saía sem ele no Cc. Virou cadastro, e o arquivo mora hoje em
    `static/data/mappings/bankers-email.json` como os outros — o que mudou é quem
    edita, não quantas listas existem.
    """
    R = _routes()
    idx = {}
    for r in R._mapping_rows('bankers-email'):
        nm, em = R._pc_norm(r.get('BANKER', '')), str(r.get('EMAIL', '') or '').strip()
        if nm and em:
            idx[nm] = em
    if not idx:
        # Lista vazia é sempre um problema: o Cc do e-mail de coleta sai sem os
        # bankers e ninguém percebe, porque o e-mail vai embora do mesmo jeito.
        # O `_mapping_rows` semeia os 58 na primeira leitura, então cair aqui
        # significa que alguém esvaziou o cadastro pela tela.
        _routes().log.warning('[sigcoll] Mapping > Bankers E-mails está vazio — o Cc do e-mail '
                    'de coleta de assinatura vai sair só com as caixas fixas.')
    return idx


def cc_emails(banker_group, bankers):
    R = _routes()
    """Cc = the counterparty's bankers (banker-group string → per-name e-mail) plus
    the fixed Ops mailboxes. Deduplicated, order preserved."""
    out, seen = [], set()
    for name in re.split(r'[;,/&]| e ', str(banker_group or '')):
        em = bankers.get(R._pc_norm(name))
        if em and em.lower() not in seen:
            seen.add(em.lower())
            out.append(em)
    for em in domain.CC_FIXED:
        if em.lower() not in seen:
            seen.add(em.lower())
            out.append(em)
    return out


def to_emails(cp):
    """Counterparty confirmation e-mails from CounterpartyDetails; falls back to all
    of the counterparty's contact e-mails when no rule mentions confirmation."""
    from apps.pages import otc_emails
    ems = otc_emails._contacts_emails(cp or {}, domain.TO_KEYWORDS)
    if not ems:
        seen = set()
        for c in ((cp or {}).get('CONTACTS') or []):
            em = str(c.get('email') or c.get('EMAIL') or '').strip()
            if em and em.lower() not in seen:
                seen.add(em.lower())
                ems.append(em)
    return ems


def groups():
    """Group pending-signature rows by (disclaimer, counterparty). Returns a list of
    dicts {cp_name, spn, rec, disclaimer, rows} sorted by counterparty."""
    R = _routes()
    rows = [r for r in R._pc_load_rows('pending')
            if R._pc_norm(r.get('Pending Status', '')) in domain.PENDING]
    by_spn, by_name = R._fxo_refdata_by_spn(), R._pc_refdata_by_name()
    groups = {}
    for r in rows:
        rec = R._pc_refdata_lookup(r, by_spn, by_name)
        cp_name = (str(rec.get('COUNTERPARTY', '') or '').strip()
                   or str(r.get('Client', '') or '').strip() or 'Counterparty')
        spn = R._norm_spn(r.get('SPN', ''))
        disc = domain.disclaimer(R._pc_norm(r.get('Pending Status', '')))
        # Banker group: RefData BANKER when present, else the row's Owner column
        # (which the Pending Confirmation page populates with the banker names).
        banker = (str((rec or {}).get('BANKER', '') or '').strip()
                  or str(r.get('Owner', '') or '').strip())
        key = (disc, spn or cp_name.upper())
        g = groups.setdefault(key, {'cp_name': cp_name, 'spn': spn, 'banker': banker,
                                    'disclaimer': disc, 'rows': []})
        if not g['banker'] and banker:
            g['banker'] = banker
        g['rows'].append(r)
    return sorted(groups.values(), key=lambda g: (g['cp_name'].upper(), g['disclaimer']))


def build_drafts():
    from apps.pages import otc_emails
    bankers = bankers_index()
    cpd = otc_emails._build_cpdetails_index()
    drafts = []
    for g in groups():
        cp = cpd.get(g['spn']) or {}
        drafts.append({
            'subject': 'Important - Confirmação de Operação de Derivativo {} - {}'.format(
                g['disclaimer'], g['cp_name']),
            'html': domain.email_html(g['rows']),
            'to': '; '.join(to_emails(cp)),
            'cc': '; '.join(cc_emails(g['banker'], bankers)),
        })
    return drafts

