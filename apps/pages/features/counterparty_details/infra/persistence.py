# -*- coding: utf-8 -*-
"""Acesso ao registro CounterpartyDetails.json — carrega, acha (ou cria) e
normaliza o record de um SPN. O dono do arquivo é a `platform/counterparty.py`
(`_cpd_load`/`_cpd_find`/`_cpd_save_list` e os normalizadores), alcançada por
busca atrasada no routes — é a superfície que os testes patcham.
"""


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


def _bank_get_record(spn):
    """Return (data, rec, banking) for an SPN, creating the record if needed."""
    data = _R()._cpd_load()
    rec = _R()._cpd_find(data, spn)
    if rec is None:
        rec = {'SPN': str(spn or '').strip(), 'COUNTERPARTY': '', 'CGD': [],
               'BANKING': _R()._bank_norm({}), 'CONTACTS': []}
        data.append(rec)
    rec['BANKING'] = _R()._bank_norm(rec.get('BANKING'))
    return data, rec, rec['BANKING']


def _cpd_get_record(spn):
    """Return (data, rec) for an SPN with CGD/CONTACTS/BANKING/NET normalized; create if missing."""
    data = _R()._cpd_load()
    rec = _R()._cpd_find(data, spn)
    if rec is None:
        rec = {'SPN': str(spn or '').strip(), 'COUNTERPARTY': '', 'CGD': [],
               'BANKING': _R()._bank_norm({}), 'CONTACTS': [], 'NET': _R()._net_norm({})}
        data.append(rec)
    rec['CGD'] = _R()._cgd_norm(rec.get('CGD'))
    rec['CONTACTS'] = _R()._contacts_norm(rec.get('CONTACTS'))
    rec['BANKING'] = _R()._bank_norm(rec.get('BANKING'))
    rec['NET'] = _R()._net_norm(rec.get('NET'))
    return data, rec
