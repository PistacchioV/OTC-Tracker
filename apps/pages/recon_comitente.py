"""
Reconciliação de Comitentes — módulo de processamento Flask.
Porta a lógica de comitente.py (PySide6) para o contexto web.

Modos de execução:
  - run_auto(recon_date)       → Outlook + drive de rede (ambiente JP)
  - run_reconciliation(f1,f2,f3) → arquivos enviados via upload (fallback)
"""

import os
import sqlite3
import tempfile
from datetime import datetime, date as _date, timedelta

import pandas as pd

try:
    from fuzzywuzzy import fuzz as _fuzz
except ImportError:
    try:
        from rapidfuzz import fuzz as _fuzz
    except ImportError:
        _fuzz = None

# ─── Path do banco ────────────────────────────────────────────────────────────
_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_MODULE_DIR, '..', 'static', 'data', 'db', 'matching_comitentes.db')
DB_PATH = os.path.normpath(DB_PATH)

# ─── Helpers de normalização ──────────────────────────────────────────────────

def sanitize_cnpj(cnpj):
    if pd.isna(cnpj) or str(cnpj).strip() in ('', 'nan'):
        return ''
    d = ''.join(filter(str.isdigit, str(cnpj)))
    if not d:
        return ''
    if len(d) == 14:
        return d
    return d.zfill(14)[:14]


def _norm_cnpj_comitente(cnpj):
    if pd.isna(cnpj) or str(cnpj).strip() in ('', 'nan'):
        return ''
    try:
        s = str(cnpj).replace('.', '').replace('-', '').replace('/', '').strip()
        d = ''.join(filter(str.isdigit, s))
        return d.zfill(14)[:14] if d else ''
    except Exception:
        return ''


def _norm_cnpj_party(cnpj):
    if pd.isna(cnpj) or str(cnpj).strip() in ('', 'nan'):
        return ''
    try:
        s = str(cnpj).replace('.0', '').strip()
        d = ''.join(filter(str.isdigit, s))
        return d.zfill(14)[:14] if d else ''
    except Exception:
        return ''


def format_cnpj(cnpj):
    c = sanitize_cnpj(cnpj)
    if len(c) == 14:
        return f'{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}'
    return c


def _fuzzy_score(a, b):
    if _fuzz is None:
        return 0.0
    if pd.isna(a) and pd.isna(b):
        return 100.0
    if pd.isna(a) or pd.isna(b):
        return 0.0
    sa, sb = str(a).strip(), str(b).strip()
    if not sa and not sb:
        return 0.0
    try:
        return round(_fuzz.ratio(sa, sb), 2)
    except Exception:
        return 0.0


def _fmt_address_b3(address):
    if pd.isna(address) or address == '':
        return ''
    address = str(address).replace('.0', '')
    parts = address.split(', ')
    if parts:
        parts[-1] = parts[-1].zfill(8)
    parts = [p if p != 'nan' else '' for p in parts]
    return ', '.join(parts)


def _fmt_address_party(address):
    if pd.isna(address) or address == '':
        return ''
    mapping = {
        ',BH,': ',BA,', ',MH,': ',MA,', ',MG,': ',MT,', ',MI,': ',MG,',
        ',PR,': ',PA,', ',PA,': ',PR,', ',PM,': ',PE,', ',RG,': ',RN,'
    }
    for old, new in mapping.items():
        address = address.replace(old, new)
    parts = address.split(',')
    parts = [p if p != 'nan' else '' for p in parts]
    if parts:
        parts[-1] = parts[-1].replace('-', '').replace('.', '').zfill(8)
    return ', '.join(parts)


def _fmt_phone_b3(phone):
    if str(phone) in ('nannan', ''):
        return ''
    p = str(phone).replace('.0', '')
    area, num = p[:2], p[2:]
    if len(num) < 8:
        num = num.zfill(8)
    if len(num) == 9:
        return f'({area}) {num[:-5]}-{num[-4:]}'
    if len(num) == 8:
        return f'({area}) {num[:-4]}-{num[-4:]}'
    return p


def _fmt_phone_party(phone):
    if pd.isna(phone) or phone == '':
        return ''
    p = str(phone).replace('.0', '')
    l = len(p)
    try:
        if l <= 9:
            return f'({p[:2]}) {p[2:-4]}-{p[-4:]}'
        elif l == 10:
            return f'({p[:2]}) {p[2:-4]}-{p[-4:]}'
        elif l == 11:
            return f'({p[:2]}) {p[2:-4]}-{p[-4:]}'
        elif l == 12:
            if p[2] == '0':
                mn, ac = p[-7:], p[-9:-7]
                return f'({ac}) {mn[:-3]}-{mn[-4:]}'
            mn, ac = p[-8:], p[-10:-8]
            return f'({ac}) {mn[:-4]}-{mn[-4:]}'
        elif l == 13:
            if p[2] == '0':
                mn, ac = p[-8:], p[-10:-8]
                return f'({ac}) {mn[:-4]}-{mn[-4:]}'
            mn, ac = p[-9:], p[-11:-9]
            return f'({ac}) {mn[:-5]}-{mn[-4:]}'
        elif l in (14, 15) and p[2] == '0':
            mn, ac = p[-9:], p[-11:-9]
            return f'({ac}) {mn[:-5]}-{mn[-4:]}'
    except Exception:
        pass
    return p


def _fmt_email(email):
    if pd.isna(email) or email == '':
        return ''
    if ';' in str(email):
        return '; '.join(e.strip().upper() for e in str(email).split(';') if e.strip())
    return str(email).strip().upper()


def _cmp_email(b3, party):
    if pd.isna(b3) and pd.isna(party):
        return 100.0
    if pd.isna(b3) or pd.isna(party):
        return 0.0
    b, p = str(b3).strip().upper(), str(party).strip().upper()
    if not b or not p:
        return 0.0
    if ',' in p:
        return 100.0 if b in [e.strip() for e in p.split(',')] else 0.0
    return 100.0 if b == p else 0.0


def _fmt_fins_party(fins):
    if pd.isna(fins) or str(fins).strip() in ('', 'nan'):
        return ''
    return 'S' if fins == 'FUNDACAO/ASSOCIACAO/SEM FINS LUCRATIVOS' else 'N'


def _fmt_fins_b3(fins):
    if pd.isna(fins) or str(fins).strip() in ('', 'nan'):
        return ''
    return fins


def _fmt_spn(spn):
    if pd.isna(spn) or spn == '':
        return ''
    return str(spn).replace('.0', '')


def _fmt_cnae_b3(cnae):
    if pd.isna(cnae) or cnae == '':
        return ''
    return str(cnae)


def _fmt_cnae_party(ir):
    try:
        if pd.isna(ir) or str(ir).lower() in ('', 'nan'):
            return ''
        d = ''.join(filter(str.isdigit, str(ir)))
        if len(d) < 2:
            return ''
        prefix = int(d[:2])
    except Exception:
        return ''
    ranges = [
        (1,3,'A'),(5,9,'B'),(10,33,'C'),(35,35,'D'),(36,39,'E'),(41,43,'F'),
        (45,47,'G'),(49,53,'H'),(55,56,'I'),(58,63,'J'),(64,66,'K'),(68,68,'L'),
        (69,75,'M'),(77,82,'N'),(84,84,'O'),(85,85,'P'),(86,88,'Q'),(90,93,'R'),
        (94,96,'S'),(97,97,'T'),(99,99,'U'),
    ]
    for s, e, sec in ranges:
        if s <= prefix <= e:
            return f'{sec}{prefix:02d}'
    return ''


def _fmt_start_party(d):
    if pd.isna(d) or not isinstance(d, str) or not d.strip() or d == 'nan':
        return ''
    for fmt in ('%d-%b-%Y', '%d-%B-%Y', '%d-%b-%y', '%d-%B-%y'):
        try:
            return datetime.strptime(d.strip().title(), fmt).strftime('%d/%m/%Y')
        except Exception:
            continue
    return ''


def _fmt_start_b3(d):
    if pd.isna(d) or not isinstance(d, str) or not d.strip() or d == 'nan':
        return ''
    return d


# ─── Lógica de Status ────────────────────────────────────────────────────────

def _is_empty(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return True
    return str(v).strip().lower() in ('', 'nan', 'none')


def _is_zero_score(v):
    if v is None:
        return False
    if isinstance(v, float) and pd.isna(v):
        return False
    s = str(v).strip().upper().replace('%', '')
    if s in ('', 'N/A', 'NA', 'NAN', 'NONE'):
        return False
    try:
        return float(s) == 0.0
    except Exception:
        return False


def _has_required_missing(row):
    dono = str(row.get('Dono do Cadastro', '')).strip().upper()
    always = [
        ('B3 Address', 'Party Central Address'),
        ('B3 Phone', 'Party Central Phone'),
        ('B3 E-mail', 'Party Central E-mail'),
        ('B3 Fins Lucrativos', 'Party Central Fins Lucrativos'),
    ]
    for b, p in always:
        if _is_empty(row.get(b, '')) or _is_empty(row.get(p, '')):
            return True
    if _is_empty(row.get('Natureza Fiscal', '')):
        return True
    if dono == 'S':
        for b, p in [('B3 Name', 'Party Central Name'), ('B3 Start Date', 'Party Central Start Date'), ('B3 CNAE', 'Party Central CNAE')]:
            if _is_empty(row.get(b, '')) or _is_empty(row.get(p, '')):
                return True
    score_cols = [
        'Address Matching Score (%)', 'Name Matching Score (%)', 'Phone Matching Score (%)',
        'E-mail Matching Score (%)', 'Fins Lucrativos Matching Score (%)',
        'Start Date Matching Score (%)', 'CNAE Matching Score (%)'
    ]
    if any(_is_zero_score(row.get(c)) for c in score_cols):
        return True
    return False


def _compare_with_db(df, db_path):
    try:
        conn = sqlite3.connect(db_path)
        db_df = pd.read_sql('SELECT * FROM comitentes', conn)
        conn.close()
    except Exception:
        db_df = pd.DataFrame(columns=df.columns)
    if 'index' in db_df.columns:
        db_df = db_df.drop(columns=['index'])

    df = df.copy()
    df['_key'] = df['B3 CNPJ'].apply(sanitize_cnpj)
    if 'B3 CNPJ' in db_df.columns:
        db_df['_key'] = db_df['B3 CNPJ'].apply(sanitize_cnpj)
    else:
        db_df['_key'] = ''

    cmp_cols = [c for c in df.columns if c not in ('Status', '_key')]

    def _set_status(row):
        if _has_required_missing(row):
            return 'Amend'
        k, le = row['_key'], row.get('LE', '')
        mask = db_df['_key'] == k
        if 'LE' in db_df.columns:
            mask &= db_df['LE'] == le
        matched = db_df[mask]
        if matched.empty:
            return 'New'
        dbr = matched.iloc[0]
        all_eq = all(
            (str(row.get(c, '')).strip().upper() if not _is_empty(row.get(c)) else '')
            == (str(dbr.get(c, '')).strip().upper() if not _is_empty(dbr.get(c)) else '')
            for c in cmp_cols if c in dbr
        )
        try:
            ms = float(row.get('Matching Score Averaged', 0))
        except Exception:
            ms = 0
        if all_eq:
            return 'Amend' if ms <= 80 else 'OK'
        return 'Amend' if ms <= 80 else 'Check'

    df['Status'] = df.apply(_set_status, axis=1)
    return df.drop(columns=['_key'])


# ─── Função principal ─────────────────────────────────────────────────────────

def run_reconciliation(file_b3_cgd, file_dcad, file_party):
    """
    Executa reconciliação completa com os 3 arquivos enviados via upload.
    Salva resultado em SQLite e retorna {'data': [...], 'counts': {...}}.
    """
    # STEP 1: Base B3 & CGD
    df_cgd = pd.read_excel(file_b3_cgd)
    df_cgd = df_cgd[df_cgd['CGD Status'] == 'Yes'].dropna(subset=['SPN'])
    df_cgd['_cnpj'] = df_cgd['CGD CNPJ'].apply(_norm_cnpj_party)
    df_cgd['_root'] = df_cgd['_cnpj'].str[:8]
    raizes = set(df_cgd['_root'].unique())

    # STEP 2: DCADCOMITENTES
    df_com = pd.read_csv(file_dcad, sep=';', skiprows=1, header=None, encoding='latin1')
    keep = [2,3,4,5,7,8,9,10,11,13,14,15,16,17,19,26,44,45,52,54,79]
    df_com = df_com.iloc[:, keep]
    names = {
        2:'LE',3:'B3 Tipo',4:'B3 CNPJ',5:'B3 Name',7:'Bairro',8:'Logradouro',
        9:'Numero',10:'Complemento',11:'CEP',13:'Cidade',14:'Estado',15:'País',
        16:'DDD',17:'Telefone',19:'B3 E-mail',26:'Natureza Fiscal',
        44:'B3 Start Date',45:'B3 CNAE',52:'_StatusB3',54:'Dono do Cadastro',
        79:'B3 Fins Lucrativos'
    }
    df_com.columns = [names[c] for c in keep]
    df_com['B3 CNPJ'] = df_com['B3 CNPJ'].apply(_norm_cnpj_comitente)
    df_com['B3 Name'] = df_com['B3 Name'].apply(lambda x: str(x).upper() if pd.notna(x) else '')
    df_com['B3_Root_CNPJ'] = df_com['B3 CNPJ'].str[:8]
    df_com = df_com[df_com['B3_Root_CNPJ'].isin(raizes) & (df_com['_StatusB3'] != 2)]
    df_com['B3 Address'] = df_com.apply(
        lambda r: f"{r['Logradouro']}, {r['Numero']}, {r['Complemento']}, {r['Bairro']}, {r['Cidade']}, {r['Estado']}, {'BR' if str(r['País']).strip().upper()=='BRASIL' else r['País']}, {r['CEP']}", axis=1
    ).apply(_fmt_address_b3)
    df_com['B3 E-mail'] = df_com['B3 E-mail'].apply(_fmt_email)
    df_com['B3 Phone'] = df_com.apply(lambda r: _fmt_phone_b3(f"{r['DDD']}{r['Telefone']}"), axis=1)
    df_com['B3 Start Date'] = df_com['B3 Start Date'].apply(_fmt_start_b3)
    df_com['B3 Fins Lucrativos'] = df_com['B3 Fins Lucrativos'].apply(_fmt_fins_b3)
    df_com['B3 CNAE'] = df_com['B3 CNAE'].apply(_fmt_cnae_b3)
    df_b3 = df_com[['Dono do Cadastro','LE','B3 Tipo','B3 CNPJ','B3 Name',
                     'B3 Address','B3 Phone','B3 E-mail','B3 Fins Lucrativos',
                     'B3 Start Date','B3 CNAE','Natureza Fiscal','B3_Root_CNPJ']]

    # STEP 3: Party Central
    df_pc = pd.read_excel(file_party, sheet_name='Party Central')
    if 'Client Role Status' in df_pc.columns:
        df_pc = df_pc[df_pc['Client Role Status'] == 'ACT']
    if 'End Date of Client Relationship' in df_pc.columns:
        df_pc = df_pc[
            df_pc['End Date of Client Relationship'].isna() |
            (df_pc['End Date of Client Relationship'].astype(str).isin(['', 'nan']))
        ]
    df_pc = df_pc[['Legal Name / Name','SPN','Legal address','Tax ID','Phone number',
                   'Email','Party Brazil Classification','Trading Start Date','IR Activity Code']]
    df_pc = df_pc.rename(columns={
        'Legal Name / Name':'Party Central Name','SPN':'Party Central SPN',
        'Legal address':'Party Central Address','Tax ID':'Party Central CNPJ',
        'Phone number':'Party Central Phone','Email':'Party Central E-mail',
        'Party Brazil Classification':'Party Central Fins Lucrativos',
        'Trading Start Date':'Party Central Start Date','IR Activity Code':'Party Central CNAE'
    })
    df_pc['Party Central CNPJ'] = df_pc['Party Central CNPJ'].apply(_norm_cnpj_party)
    df_pc['_pc_root'] = df_pc['Party Central CNPJ'].str[:8]
    df_pc = df_pc[df_pc['_pc_root'].isin(raizes)]
    df_pc = df_pc.map(lambda x: x.upper() if isinstance(x, str) else x)
    df_pc['Party Central SPN'] = df_pc['Party Central SPN'].apply(_fmt_spn)
    df_pc['Party Central Phone'] = df_pc['Party Central Phone'].apply(_fmt_phone_party)
    df_pc['Party Central E-mail'] = df_pc['Party Central E-mail'].apply(_fmt_email)
    df_pc['Party Central Fins Lucrativos'] = df_pc['Party Central Fins Lucrativos'].apply(_fmt_fins_party)
    df_pc['Party Central Start Date'] = df_pc['Party Central Start Date'].apply(_fmt_start_party)
    df_pc['Party Central CNAE'] = df_pc['Party Central CNAE'].apply(_fmt_cnae_party)
    df_pc['Party Central Address'] = df_pc['Party Central Address'].apply(_fmt_address_party)
    df_pc = df_pc[~df_pc['Party Central Name'].str.startswith('ESCROW', na=False)]

    # STEP 4: Match por CNPJ completo dentro de cada raiz
    matches = []
    for root in raizes:
        b3r = df_b3[df_b3['B3_Root_CNPJ'] == root]
        pcr = df_pc[df_pc['_pc_root'] == root]
        if b3r.empty or pcr.empty:
            continue
        m = pd.merge(b3r, pcr, left_on='B3 CNPJ', right_on='Party Central CNPJ', how='inner')
        if not m.empty:
            matches.append(m)

    if not matches:
        return {'data': [], 'counts': {'total':0,'new':0,'check':0,'ok':0,'amend':0}}

    df = pd.concat(matches, ignore_index=True)

    # STEP 5: Scores
    df['Address Matching Score (%)'] = df.apply(
        lambda r: _fuzzy_score(r['B3 Address'], r['Party Central Address']), axis=1)
    df['Name Matching Score (%)'] = df.apply(
        lambda r: 'N/A' if r['Dono do Cadastro'] == 'N'
        else _fuzzy_score(r['B3 Name'], r['Party Central Name']), axis=1)
    df['Phone Matching Score (%)'] = df.apply(
        lambda r: _fuzzy_score(r['B3 Phone'], r['Party Central Phone']), axis=1)
    df['Start Date Matching Score (%)'] = df.apply(
        lambda r: 'N/A' if r['Dono do Cadastro'] == 'N'
        else _fuzzy_score(r['B3 Start Date'], r['Party Central Start Date']), axis=1)
    df['Fins Lucrativos Matching Score (%)'] = df.apply(
        lambda r: _fuzzy_score(r['B3 Fins Lucrativos'], r['Party Central Fins Lucrativos']), axis=1)
    df['E-mail Matching Score (%)'] = df.apply(
        lambda r: _cmp_email(r['B3 E-mail'], r['Party Central E-mail']), axis=1)

    def _cnae_score(row):
        if str(row.get('Dono do Cadastro', '')).strip().upper() == 'N':
            return 'N/A'
        b = str(row.get('B3 CNAE', '') or '').strip().upper()
        p = str(row.get('Party Central CNAE', '') or '').strip().upper()
        return 100.0 if b and p and b == p else 0.0
    df['CNAE Matching Score (%)'] = df.apply(_cnae_score, axis=1)

    # Normaliza scores
    df['Address Matching Score (%)'] = df['Address Matching Score (%)'].apply(
        lambda x: 0.0 if not isinstance(x, str) and not pd.isna(x) and float(x) < 70 else x)
    for col in ('Phone Matching Score (%)', 'E-mail Matching Score (%)'):
        df[col] = df[col].apply(
            lambda x: 0.0 if not isinstance(x, str) and not pd.isna(x) and float(x) != 100 else x)
    df['Start Date Matching Score (%)'] = df['Start Date Matching Score (%)'].apply(
        lambda x: x if isinstance(x, str) and x == 'N/A'
        else (100.0 if not pd.isna(x) and float(x) == 100 else 0.0))

    def _avg(row):
        cols = ['Address Matching Score (%)','Name Matching Score (%)','Phone Matching Score (%)',
                'E-mail Matching Score (%)','Fins Lucrativos Matching Score (%)',
                'Start Date Matching Score (%)','CNAE Matching Score (%)']
        nums = []
        for c in cols:
            v = row.get(c)
            if isinstance(v, str) and v == 'N/A':
                continue
            try:
                if not pd.isna(v):
                    nums.append(float(v))
            except Exception:
                pass
        return round(sum(nums) / len(nums), 2) if nums else 0.0

    df['Matching Score Averaged'] = df.apply(_avg, axis=1)
    df['Status'] = 'New'

    desired = [
        'Dono do Cadastro','LE','Party Central SPN','B3_Root_CNPJ','B3 CNPJ','Party Central CNPJ',
        'B3 Name','Party Central Name','Name Matching Score (%)',
        'B3 Address','Party Central Address','Address Matching Score (%)',
        'B3 Phone','Party Central Phone','Phone Matching Score (%)',
        'B3 E-mail','Party Central E-mail','E-mail Matching Score (%)',
        'B3 Fins Lucrativos','Party Central Fins Lucrativos','Fins Lucrativos Matching Score (%)',
        'B3 Start Date','Party Central Start Date','Start Date Matching Score (%)',
        'B3 CNAE','Party Central CNAE','CNAE Matching Score (%)','Natureza Fiscal',
        'Matching Score Averaged','Status'
    ]
    df = df[[c for c in desired if c in df.columns]].drop_duplicates(subset=['B3 CNPJ','LE'])
    df = df.sort_values('Matching Score Averaged')
    df['B3 CNPJ'] = df['B3 CNPJ'].apply(format_cnpj)
    df['Party Central CNPJ'] = df['Party Central CNPJ'].apply(format_cnpj)

    # STEP 6: Status pelo DB
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    df = _compare_with_db(df, DB_PATH)

    # Salva
    conn = sqlite3.connect(DB_PATH)
    df.to_sql('comitentes', conn, if_exists='replace', index=False)
    conn.close()

    return _build_response(df)


def load_from_db():
    if not os.path.exists(DB_PATH):
        return {'data': [], 'counts': {'total':0,'new':0,'check':0,'ok':0,'amend':0}}
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute('SELECT * FROM comitentes').fetchall()]
        conn.close()
        for r in rows:
            for k, v in r.items():
                if v is None:
                    r[k] = ''
        return _build_response_from_list(rows)
    except Exception:
        return {'data': [], 'counts': {'total':0,'new':0,'check':0,'ok':0,'amend':0}}


def _build_response(df):
    rows = []
    for _, r in df.iterrows():
        row = {}
        for k, v in r.items():
            if pd.isna(v):
                row[k] = ''
            elif isinstance(v, float) and v == int(v):
                row[k] = str(v)
            else:
                row[k] = str(v) if not isinstance(v, (int, float, bool)) else v
        rows.append(row)
    return _build_response_from_list(rows)


def _build_response_from_list(rows):
    counts = {
        'total': len(rows),
        'new':   sum(1 for r in rows if r.get('Status') == 'New'),
        'check': sum(1 for r in rows if r.get('Status') == 'Check'),
        'ok':    sum(1 for r in rows if r.get('Status') == 'OK'),
        'amend': sum(1 for r in rows if r.get('Status') == 'Amend'),
    }
    return {'data': rows, 'counts': counts}


# ─── Caminho de rede B3 (ambiente JP) ────────────────────────────────────────
_DCAD_BASE = r"I:\Confirmation\Derivativos\Alteryx\Posição B3\ARQUIVOS CETIP"

# Caixas Outlook e subjects dos emails
_MAILBOX         = 'brazil.otc.ops@jpmorgan.com'
_SUBJECT_B3_CGD  = 'Base B3 & CGD Consolidada'
_SUBJECT_PARTY   = '[PROD] - REPORT - Party Central Client Report General - SUCCESS - Client Report Generated (general)'

_MONTH_PT = {
    '01':'Janeiro','02':'Fevereiro','03':'Março','04':'Abril',
    '05':'Maio','06':'Junho','07':'Julho','08':'Agosto',
    '09':'Setembro','10':'Outubro','11':'Novembro','12':'Dezembro'
}


def _outlook_download(inbox, subject_filter, tmpdir):
    """
    Baixa o anexo mais recente do email que corresponde ao subject_filter.
    Retorna o caminho do arquivo salvo ou levanta FileNotFoundError.
    """
    mapi_prop = "http://schemas.microsoft.com/mapi/proptag/0x0E1D001F"
    restriction = f'@SQL="{mapi_prop}" = \'{subject_filter}\''
    messages = inbox.Items.Restrict(restriction)
    for msg in list(messages):
        if msg.Class == 43 and msg.Attachments.Count > 0:
            att = msg.Attachments.Item(1)
            dest = os.path.join(tmpdir, att.FileName)
            att.SaveAsFile(dest)
            return dest
    raise FileNotFoundError(f"Email '{subject_filter}' não encontrado na Inbox.")


def run_auto(recon_date_str: str):
    """
    Modo automático (ambiente JP):
    - Conecta ao Outlook e baixa os 2 anexos de email
    - Lê DCADCOMITENTES direto do drive de rede I:\
    - Processa e salva no DB

    recon_date_str: 'YYYY-MM-DD'
    """
    try:
        import win32com.client as _win32
    except ImportError:
        raise EnvironmentError(
            'win32com não disponível. O modo automático requer Windows com Outlook instalado.'
        )

    recon_date = datetime.strptime(recon_date_str, '%Y-%m-%d').date()
    str_date   = recon_date.strftime('%y%m%d')          # ex: 250603
    year       = recon_date.strftime('%Y')
    month_num  = recon_date.strftime('%m')
    day        = recon_date.strftime('%d')

    with tempfile.TemporaryDirectory() as tmpdir:
        # ── Outlook ──────────────────────────────────────────────────────────
        outlook  = _win32.Dispatch('Outlook.Application').GetNamespace('MAPI')
        mailbox  = outlook.Folders[_MAILBOX]
        inbox    = mailbox.Folders['Inbox']

        path_b3_cgd = _outlook_download(inbox, _SUBJECT_B3_CGD, tmpdir)
        path_party  = _outlook_download(inbox, _SUBJECT_PARTY,  tmpdir)

        # ── DCADCOMITENTES via drive de rede ─────────────────────────────────
        dcad_name = f'SIC_{str_date}_DCADCOMITENTES.txt'
        path_dcad = os.path.join(_DCAD_BASE, year, month_num, day, dcad_name)

        if not os.path.exists(path_dcad):
            raise FileNotFoundError(
                f'Arquivo não encontrado: {path_dcad}\n'
                f'Verifique se o drive I:\\ está mapeado e se o arquivo do dia {recon_date.strftime("%d/%m/%Y")} já foi gerado.'
            )

        # ── Abre como file objects e chama a lógica comum ────────────────────
        with open(path_b3_cgd, 'rb') as f1, \
             open(path_dcad, 'rb') as f2, \
             open(path_party, 'rb') as f3:
            return run_reconciliation(f1, f2, f3)
