# -*- coding: utf-8 -*-
"""As regras puras do Accrual de Swap — layout das colunas, parse e formatação
de fator, o de-para de chave (Código IF), a aplicação dos fatores na tabela, a
migração de layout antigo e as consultas sobre a tabela em memória.

Puro de verdade: nada aqui importa `routes`, Flask, arquivo ou rede — o que
precisa do mundo chega por parâmetro. O que depende de helper de plataforma
(`_cc_cell` para ler célula, `_acc_digits`, `_fi_build_line`) mora em
`queries`/`commands`/`infra`, que podem alcançá-los por busca atrasada.
"""
import re

_ACC_HEADER_ROW = 9                                # 1-based: headers on row 9

_ACC_ACCOUNT_COL = 10                              # col K — house-account filter

_ACC_ACCOUNTS   = {'73760009', '04880006'}         # col K house accounts (digits only)

_ACC_FIXED_HEADERS = [
    'Código IF', 'Data Início', 'Data Vencimento',
    'PARTE / Conta', 'PARTE / Nome Simplificado', 'PARTE / Indexador',
    'CONTRAPARTE / Conta', 'CONTRAPARTE / Nome Simplificado', 'CONTRAPARTE / Indexador',
    'Fator Parte', 'Fator Contraparte', 'Comments',
]

_ACC_DISPLAY_SRC = [0, 5, 6, 10, 11, 13, 16, 17, 19, None, None, None]

_ACC_FACTOR_STATUS_MISSING = 'Missing Accrual'

_ACC_FI_KEY = 'swap-atualizacao-pu-fator'            # cadastro do File Interface

_ACC_VIEW_BY_PREFIX = {'73760': 'BANCO', '04880': 'BANCO', '85398': 'ATACAMA', '00041': 'LAWTON'}

_ACC_VIEW_PART_NAME = {'BANCO': 'JPMORGANBM', 'LAWTON': 'INTRAGLAWTONFDO', 'ATACAMA': 'INTRAGATACAMAFDO'}

_ACC_LOB_TAG = {'CEM': 'CEM', 'EDG': 'EDG', 'Hybrids': 'HYB', 'Commodities': 'COMM'}

_ACC_RECON_ACCOUNTS = {'04880006', '73760009'}

_ACC_RECON_MARKER = 'REGISTRO DE PU/FATOR'

_ACC_RECON_HEADER_ROW = 5                  # 1-based → data starts at index 5


def _acc_parse_num(s):
    """Parse a number that may be BR (1.234,56) or US (1,234.56) formatted."""
    t = str('' if s is None else s).strip().replace('%', '').replace(' ', '')
    if not t or not re.search(r'\d', t):
        return None
    neg = t.startswith('-')
    t = t.lstrip('+-')
    has_c, has_d = ',' in t, '.' in t
    if has_c and has_d:                                  # decimal = whichever comes last
        dec = ',' if t.rfind(',') > t.rfind('.') else '.'
        t = t.replace('.' if dec == ',' else ',', '').replace(dec, '.')
    elif has_c:
        t = t.replace(',', '.')
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def _acc_fmt_factor(s):
    """US format, 8 decimals (rounded), ALWAYS absolute (drop any '-'). '' when the
    cell is not a number."""
    v = _acc_parse_num(s)
    return '' if v is None else '{:.8f}'.format(round(abs(v), 8))


def _acc_le_norm(s):
    """Normalise an LE/view to bare digits without leading zeros (0228 → 228)."""
    return re.sub(r'\D', '', str(s or '')).lstrip('0')


def _acc_factor_keys(code):
    """Lookup keys for a CETIP ID / Código IF: upper-cased and digits-only ('#'+d)."""
    code = str(code or '').strip()
    keys = [code.upper()]
    dg = re.sub(r'\D', '', code)
    if dg:
        keys.append('#' + dg)
    return keys


def _acc_fmap_put(fmap, cetip, parte_factor, contra_factor):
    for k in _acc_factor_keys(cetip):
        fmap.setdefault(k, (parte_factor, contra_factor))


def _acc_fmap_get(fmap, code):
    for k in _acc_factor_keys(code):
        if k in fmap:
            return fmap[k]
    return None


def _acc_apply_factors(data, lob, fmap):
    """Fill Fator Parte/Contraparte for the rows of one LOB table. A side keyed by a
    non-VCP indexer gets '-'; a VCP side with no factor flags the row 'Missing
    Accrual'. Row layout: [ ...11 data..., status, maker, checker, id ]."""
    rows = (data.get('tables') or {}).get(lob, [])
    matched = missing = 0
    for row in rows:
        if not row or len(row) < 15:
            continue
        parte_idx  = str(row[5] or '').strip().upper()
        contra_idx = str(row[8] or '').strip().upper()
        entry = _acc_fmap_get(fmap, row[0])
        if entry:
            matched += 1
        pf, cf = entry if entry else ('', '')
        row_missing = False
        if parte_idx == 'VCP':
            if pf:
                row[9] = pf
            else:
                row[9] = ''
                row_missing = True
        else:
            row[9] = '-'
        if contra_idx == 'VCP':
            if cf:
                row[10] = cf
            else:
                row[10] = ''
                row_missing = True
        else:
            row[10] = '-'
        if row_missing:
            row[-4] = _ACC_FACTOR_STATUS_MISSING
            missing += 1
    return matched, missing


def _accrual_migrate(data):
    """Bring rows saved under an older column layout up to the current fixed set,
    padding the data block (before the 4 meta cells status/maker/checker/id) so a
    newly-added column like 'Comments' lands in the right place for old files too."""
    nfix = len(_ACC_FIXED_HEADERS)
    for rows in (data.get('tables') or {}).values():
        for r in rows:
            ndata = len(r) - 4                       # cells before status/maker/checker/id
            while 0 <= ndata < nfix:
                r.insert(ndata, '')                  # append to the data block, push meta right
                ndata += 1
    data['headers'] = list(_ACC_FIXED_HEADERS)
    return data


def _accrual_find(data, lob, rid):
    for r in (data.get('tables') or {}).get(lob, []):
        if r and str(r[-1]) == str(rid):
            return r
    return None


def _acc_missing_accrual_rows(data, lobs):
    """Rows flagged 'Missing Accrual' (no updated factor) across the given LOB books.
    Their presence blocks file generation. Returns [{id, lob, codigo}]."""
    out = []
    for lob in lobs:
        for r in ((data.get('tables') or {}).get(lob) or []):
            if r and len(r) >= 15 and str(r[-4] or '') == _ACC_FACTOR_STATUS_MISSING:
                out.append({'id': str(r[-1]), 'lob': lob, 'codigo': str(r[0] or '')})
    return out


def _acc_check_status_rows(data):
    """Return (all_check_rows, uncommented) — rows whose status is 'Check'."""
    checks, pending = [], []
    for lob, table in (data.get('tables') or {}).items():
        for r in table:
            if not r or len(r) < 15:
                continue
            if str(r[-4] or '').strip().lower() == 'check':
                comment = str(r[-5] or '').strip()
                item = {'id': str(r[-1]), 'lob': lob, 'codigo': str(r[0] or ''), 'comment': comment}
                checks.append(item)
                if not comment:
                    pending.append(item)
    return checks, pending


def _acc_swap_fator(f):
    """Factor → 2 integer + 8 decimal digits, no separator, absolute. 1.0 → '0100000000'."""
    try:
        n = abs(float(str(f or '').replace(',', '.')))
    except (ValueError, TypeError):
        n = 0.0
    ip, fp = '{:.8f}'.format(n).split('.')
    return ip[-2:].rjust(2, '0') + fp


def _accrual_is_vcp_name(n):
    nl = n.lower()
    return ('vcp' in nl) or ('instrumentofin' in nl) or ('intrumentofin' in nl)
