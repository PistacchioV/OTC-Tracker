# -*- coding: utf-8 -*-
"""As regras puras do MtM de Swap — o layout das duas tabelas (Swap e COE), o
reconhecimento do arquivo pelo nome, o parse de número BR, as constantes de
geração do arquivo B3 e as consultas sobre a tabela em memória.

Puro: nada aqui importa `routes`, Flask ou disco.
"""
import os
import random


_MTM_ACCOUNT      = '73760009'               # col D house account (73760.00-9), digits only


_MTM_FILTER_COL   = 3                         # col D


_MTM_RECON_DATA_ROW  = 8                      # ConsultaInformacoesAtualizMID: headers row 8, data from row 9 (idx 8)


_MTM_RECON_VALUE_COL = 6                      # col G = registered Valor MTM (signed)


_MTM_SWAP_BOOKS   = ('CEM', 'EDG', 'Hybrids', 'Commodities')


_MTM_FIXED_HEADERS = [
    'Código IF', 'Data Início', 'PARTE / Conta', 'Nome Simplificado Parte',
    'CONTRAPARTE / Conta', 'Nome Simplificado Contraparte',
    'Data Vencimento', 'Valor MTM', 'Comments',
]


_MTM_DISPLAY_SRC  = [0, 2, 3, 4, 5, 6, 10, None, None]


_MTM_COE_HEADERS  = ['Código do COE', 'Nome Simplificado Emissor', 'Conta Emissor', 'Nome Figura', 'Valor MTM', 'Comments']


_MTM_COE_SRC      = [0, 1, 2, 3, None, None]  # A,B,C,D (A '#' stripped) + Valor MTM (blank) + Comments (manual)


_MTM_COE_REFDATE_COL = 6                       # col G reference date


_MTM_VALOR_IDX    = _MTM_FIXED_HEADERS.index('Valor MTM')    # 7


_MTM_COMMENT_IDX  = _MTM_FIXED_HEADERS.index('Comments')     # 8


_MTM_COE_VALOR_IDX   = _MTM_COE_HEADERS.index('Valor MTM')   # 4


_MTM_COE_COMMENT_IDX = _MTM_COE_HEADERS.index('Comments')    # 5


_MTM_ZERO_COMMENT   = 'MtM não pode ser Zero'


_MTM_STATUS_MISSING = 'Missing MtM'                   # rows with no matching MtM value


def _mtm_is_cem_value_name(n):
    nl = (n or '').lower()
    return 'vcp_cetip_mtm' in nl and not nl.endswith('.msg')


def _mtm_parse_num_br(s):
    """Parse a BRL-formatted amount like "-1.802.855,64" (dot thousands, comma
    decimal, optional surrounding quotes) → float, or None. Used for the recon file
    (ConsultaInformacoesAtualizMID), whose values are in BRL format — unlike the
    page's US-format Valor MTM (see _mtm_parse_num)."""
    s = str(s or '').strip().strip("'").strip('"').strip()
    if not s:
        return None
    s = s.replace('.', '').replace(',', '.')      # drop dot thousands, comma → decimal
    try:
        return float(s)
    except ValueError:
        return None


def _mtm_is_edg_value_name(n):
    """EDG/COE MtM values file — named 'EDG.<ext>' (any extension)."""
    return os.path.splitext(n or '')[0].strip().lower() == 'edg'


_MTM_HYB_VALUE_COL = 4                                # col E: MTM in scaling currency


def _mtm_is_hyb_value_name(n):
    return 'stream_level_mtm' in (n or '').lower()



def _mtm_is_swap_name(n):
    return 'sematualmid' in (n or '').lower()


def _mtm_is_coe_name(n):
    nl = (n or '').lower()
    return 'coe' in nl and ('consultamtmcoe' in nl or 'swap-coe' in nl)


def _mtm_finalize(buckets):
    """Append [status, maker, checker, id] to each row; return per-book counts."""
    for lob, rws in buckets.items():
        for i, rw in enumerate(rws):
            rw.extend(['New', '', ''])
            rw.append('{}-{}'.format(lob, i))
    return {k: len(v) for k, v in buckets.items()}


def _mtm_find_row(data, lob, rid):
    for r in (data.get('tables') or {}).get(lob, []) or []:
        if r and str(r[-1]) == str(rid):
            return r
    return None


_MTM_GEN_LAWTON_ACCT  = '00041007'                   # Lawton  = 00041.00-7


_MTM_GEN_ATACAMA_ACCT = {'85398005'}                 # Atacama = 85398.00-5


_MTM_GEN_PARTY = {                                   # Nome Simplificado Parte (20 chars)
    'BANCO':   'JPMORGANBM'       + ' ' * 10,
    'LAWTON':  'INTRAGLAWTONFDO'  + ' ' * 5,
    'ATACAMA': 'INTRAGATACAMAFDO' + ' ' * 4,
}


_MTM_GEN_PARTY_ACCT = {                              # Código Conta Parte per view
    'BANCO': '73760009', 'LAWTON': '00041007', 'ATACAMA': '85398005',
}


_MTM_GEN_BOOK_SUFFIX = {'EDG': 'EDG', 'CEM': 'CEM', 'Hybrids': 'HYB'}


_MTM_GEN_BOOK_CPTY = {'EDG': 'ATACAMA', 'CEM': 'LAWTON', 'Hybrids': 'LAWTON'}


_MTM_FI_KEY = 'mid-informacoes-derivativos'


_MTM_GEN_COE_COLS  = ['Tipo IF', 'Tipo de Linha', 'Código operação', 'Código do Instrumento Financeiro',
                      'Conta do Emissor', 'Data Referência', 'Valor MTM', 'Débito/Crédito']


def _mtm_gen_min_value(v):
    """Zero MtM → the smallest registrable amount (1 in the last available decimal
    place, i.e. 0.01), since B3 rejects a zero MtM. Applied ONLY when generating the
    preview / file — the table keeps the spreadsheet's exact 0.00. Non-zero values
    pass through unchanged."""
    v = v or 0.0
    return 0.01 if round(v, 2) == 0 else v


def _mtm_valor_fixed(v, int_digits):
    """Absolute value as (int_digits + 2) zero-padded digits (implicit 2 decimals)."""
    return str(int(round(abs(v or 0.0) * 100))).zfill(int_digits + 2)


def _mtm_rand_meunum():
    return ''.join(random.choice('0123456789') for _ in range(10))


def _mtm_coe_header(today):
    return 'COE' + '  ' + '0' + '0475' + _MTM_GEN_PARTY['BANCO'] + today


def _mtm_file_lines(fdata):
    if 'lines' in fdata:                             # MID: linha pronta pelo cadastro
        return [fdata['header']] + fdata['lines']
    return [fdata['header']] + [''.join(r[c] for c in fdata['cols']) for r in fdata['rows']]


_MTM_VAL_BOOKS = ('CEM', 'EDG', 'Hybrids')           # swap books (+ COE handled apart)


def _mtm_missing_rows(data, books):
    """Rows still flagged 'Missing MtM' (no MtM value) across the given books."""
    out, tables = [], (data.get('tables') or {})
    for lob in books:
        for r in tables.get(lob, []) or []:
            if r and str(r[-4] or '').strip().lower().startswith('missing'):
                out.append({'lob': lob, 'codigo': str(r[0] or ''), 'id': str(r[-1])})
    return out


def _mtm_check_status_rows(data):
    """(checks, uncommented) — rows whose status is 'Check' (recon divergence).
    MtM row = data cells + [status(-4), maker(-3), checker(-2), id(-1)]; Comments = -5."""
    checks, pending = [], []
    for lob, table in (data.get('tables') or {}).items():
        for r in table or []:
            if not r or len(r) < 5:
                continue
            if str(r[-4] or '').strip().lower() == 'check':
                comment = str(r[-5] or '').strip()
                item = {'id': str(r[-1]), 'lob': lob, 'codigo': str(r[0] or ''), 'comment': comment}
                checks.append(item)
                if not comment:
                    pending.append(item)
    return checks, pending


def _mtm_recon_key(s):
    """Contract-ID match key: drop the '#' (replace with nothing) and normalize to
    match the page's Código IF."""
    return str(s or '').replace('#', '').strip().strip("'").strip('"').upper()
