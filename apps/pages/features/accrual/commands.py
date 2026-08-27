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


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


def _acc_swap_header(view, today):
    """Linha de header (tipo 0) — literais e larguras do cadastro; participante
    e data entram por seq."""
    return _R()._fi_build_line(domain._ACC_FI_KEY, 'header',
                          {'4': domain._ACC_VIEW_PART_NAME.get(view, view), '5': today},
                          page_url='/accrual-swap')


def _acc_swap_records(row, today):
    """Return a list of {view, line} for one accrual row (empty when no VCP leg)."""
    codigo = str(row[0] or '').strip()
    accP, idxP = row[3], str(row[5] or '').strip().upper()
    accC, idxC = row[6], str(row[8] or '').strip().upper()
    fatP, fatC = row[9], row[10]
    digP = re.sub(r'\D', '', str(accP or '')); digC = re.sub(r'\D', '', str(accC or ''))
    numP = int(digP or '0'); numC = int(digC or '0')
    roleP = '01' if numP > numC else '00'
    roleC = '01' if numC > numP else '00'
    legs = []                                       # (curva, fator) per VCP leg
    if idxP == 'VCP': legs.append((roleP, fatP))
    if idxC == 'VCP': legs.append((roleC, fatC))
    if not legs:
        return []
    prefP, prefC = digP[:5], digC[:5]
    updaters = [(roleP, prefP)]                      # PARTE (our house entity) always updates
    if prefC in domain._ACC_VIEW_BY_PREFIX and prefC != prefP:
        updaters.append((roleC, prefC))             # group counterparty also submits its view
    out = []
    for papel, pref in updaters:
        view = domain._ACC_VIEW_BY_PREFIX.get(pref)
        if not view:
            continue
        for curva, fat in legs:
            meu = ''.join(_R().random.choice('0123456789') for _ in range(10))
            line = _R()._fi_build_line(domain._ACC_FI_KEY, 'registro',
                                  {'4': codigo, '5': papel, '7': curva,
                                   '8': today, '9': meu,
                                   '11': domain._acc_swap_fator(fat)},
                                  page_url='/accrual-swap')
            out.append({'view': view, 'line': line})
    return out


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
    if not by_view:
        return []
    lob_tag = domain._ACC_LOB_TAG.get(lob, str(lob).upper())
    os.makedirs(_R().CONECTA_NEW_PATH, exist_ok=True)
    if evidence_dir:
        try:
            os.makedirs(evidence_dir, exist_ok=True)
        except Exception:
            _R().log.warning('[accrual] could not create evidence dir %s:\n%s', evidence_dir, traceback.format_exc())
    generated = []
    for view in ('BANCO', 'LAWTON', 'ATACAMA'):
        lines = by_view.get(view)
        if not lines:
            continue
        content = '\n'.join([_acc_swap_header(view, today)] + lines)
        fpath = _R()._unique_filepath(_R().CONECTA_NEW_PATH, 'ACCRUAL_{}-{}.txt'.format(view, lob_tag))
        with open(fpath, 'w', encoding='utf-8') as fh:
            fh.write(content)
        # Evidence copy (same base name), best-effort — never blocks the Conecta write.
        if evidence_dir and os.path.isdir(evidence_dir):
            try:
                with open(os.path.join(evidence_dir, os.path.basename(fpath)), 'w', encoding='utf-8') as fh:
                    fh.write(content)
            except Exception:
                _R().log.warning('[accrual] evidence copy failed for %s:\n%s', fpath, traceback.format_exc())
        generated.append({'filename': os.path.basename(fpath), 'path': fpath, 'view': view, 'count': len(lines)})
    return generated


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
