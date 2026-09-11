# -*- coding: utf-8 -*-
"""As escritas do Accrual — a geração dos arquivos de Batch Conecta (uma visão
por entidade) e o batimento contra o arquivo de operações do dia.

`_acc_run_recon` MUTA a tabela em memória (o status de cada linha e o bloco
`recon`); quem persiste é o endpoint, chamando `persistence._accrual_save`.
"""
import os
import re
import traceback

from apps.pages.features.accrual import domain
from apps.pages.platform import pu_fator as _pf
from apps.pages import data_store as _store  # noqa: E402


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


# O header e os registros do arquivo de PU/Fator moram na platform
# (`pu_fator`, §452) — o Swap VCP manda o mesmo arquivo. Aliases.
_acc_swap_header = _pf.acc_swap_header
_acc_swap_records = _pf.acc_swap_records
def _acc_write_batch_files(data, lob, today, evidence_dir=None):
    """Generate + write ACCRUAL_<view>-<lob>.txt for one LOB book, split by view.
    Written to the Batch Conecta folder AND (best-effort) to the evidence folder
    (Regulatory\\Accrual\\YYYY\\mm. Month\\DD). Returns [{filename, path, view, count}]."""
    by_view = {}
    for r in ((data.get('tables') or {}).get(lob) or []):
        if not r or len(r) < 15:
            continue
        if str(r[-4] or '') == domain._ACC_FACTOR_STATUS_MISSING:    # skip rows without a factor
            continue
        for rec in _acc_swap_records(r, today):
            by_view.setdefault(rec['view'], []).append(rec['line'])
    lob_tag = domain._ACC_LOB_TAG.get(lob, str(lob).upper())
    return _pf.write_view_files(by_view, lob_tag, today, evidence_dir)


def _acc_run_recon(data, rows):
    """Gather registered factors per Código IF from the operacoes rows, then flag each
    VCP leg OK/Check by simple factor membership. Mutates data (recon + status)."""
    by_cif = {}                                           # cif_key -> [rounded floats]
    for i in range(domain._ACC_RECON_HEADER_ROW, len(rows)):     # data from row 6 (index 5)
        row = rows[i]
        if _R()._acc_digits(_R()._cc_cell(row, 1)) not in domain._ACC_RECON_ACCOUNTS:  # col B house account
            continue
        if _R()._cc_cell(row, 4).strip().upper() != domain._ACC_RECON_MARKER:          # col E marker
            continue
        cif = _R()._cc_cell(row, 7).strip()                                     # col H título
        fac = domain._acc_parse_num(_R()._cc_cell(row, 15))                     # col P factor (comma→dot)
        if not cif or fac is None:
            continue
        for k in domain._acc_factor_keys(cif):
            by_cif.setdefault(k, []).append(round(fac, 8))

    def _regs(cif):
        for k in domain._acc_factor_keys(cif):
            if k in by_cif:
                return by_cif[k]
        return []

    recon_out, ok_rows, check_rows = {}, 0, 0
    for table in (data.get('tables') or {}).values():
        for r in table:
            if not r or len(r) < 15:
                continue
            idxP = str(r[5] or '').strip().upper()
            idxC = str(r[8] or '').strip().upper()
            legs = []                                       # (tag, accrual_factor); p=Parte, c=Contra
            if idxP == 'VCP': legs.append(('p', r[9]))
            if idxC == 'VCP': legs.append(('c', r[10]))
            if not legs:
                continue
            regs = _regs(str(r[0] or '').strip())
            regset = set(regs)
            regdisp = ', '.join('{:.8f}'.format(x) for x in regs)
            entry, all_ok = {}, True
            for tag, acc_fac in legs:
                accv = domain._acc_parse_num(acc_fac)
                ok = (accv is not None and round(accv, 8) in regset)
                if not ok:
                    all_ok = False
                entry[tag] = {'ok': ok, 'reg': regdisp}
            recon_out[str(r[-1])] = entry
            r[-4] = 'Success' if all_ok else 'Check'        # status
            if all_ok: ok_rows += 1
            else:      check_rows += 1
    data['recon'] = recon_out
    return {'success_rows': ok_rows, 'check_rows': check_rows, 'map_entries': len(by_cif)}
