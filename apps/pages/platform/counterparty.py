# -*- coding: utf-8 -*-
"""O Counterparty Details (`CounterpartyDetails.json`) — o armazém dos contatos,
net type, banking e CGD de cada contraparte, mais o parser da planilha
"CONTATO DE CLIENTES" que o Update Contacts do Control Panel importa.

Movido VERBATIM do `routes.py` (fase platform/ — CLAUDE.md §10). É horizontal
de fato: `_cpd_load`/`_cpd_find` alimentam o NDF Summary (net type), o Other
Products (`_opssum_rows`), o CGD dos documentos de confirmação
(`_conf_cgd_lookup`), a Recon e a tela de Reference Data — e `_norm_spn` é a
normalização de SPN que meia dúzia de features usa pelo alias do `routes`.

O `routes.py` mantém os nomes como ALIAS, então features e testes seguem
alcançando por `routes.<nome>`. O que ainda é do `routes` — o `_B3_DATA_DIR`,
que os testes trocam LÁ (`R._B3_DATA_DIR = tmp`) — é alcançado por import
ATRASADO dentro da função; o `check_cpd_api`, que troca o `_cpd_path` inteiro,
troca NESTE módulo (o `_cpd_load` o chama por dentro).

`_cpd_save_list` grava um `.bak` antes de reescrever a lista — quem importa a
planilha por cima de 550 cadastros quer o arquivo de ontem ao lado.
"""
import io
import json
import logging
import os
import re
import shutil
import uuid

log = logging.getLogger('otc_tracker')

# ──────────────────────────────────────────────────────────────────────────
# Control Panel — Update Contacts
# Native port of scripts/import_client_contacts.py. Imports the "CONTATO DE
# CLIENTES" spreadsheet into CounterpartyDetails.json: one contact per row,
# data starting at row 5, grouped by SPN (leading zeros ignored). For a matched
# SPN the CONTACTS array is replaced; CGD/BANKING are preserved. SPNs missing
# from the JSON are appended as new records. _cpd_save_list writes a .bak first.
# ──────────────────────────────────────────────────────────────────────────
_CONTACTS_DATA_START_ROW = 5    # 1-based; first data row in the sheet
# 0-based column indices: B,C,D,E,F,G,H
_CC_SPN, _CC_NAME, _CC_ACTIVE, _CC_CONTACT, _CC_PHONE, _CC_EMAIL, _CC_RULE = 1, 2, 3, 4, 5, 6, 7

# Map spreadsheet rule labels → the canonical rules used by the Reference Data
# editor. Unknown values are kept verbatim.
_CONTACT_RULE_MAP = {
    'NEGOTIATION': 'Negotiation', 'NEGOCIACAO': 'Negotiation', 'NEGOCIAÇÃO': 'Negotiation',
    'REPURCHASE': 'Repurchase', 'RECOMPRA': 'Repurchase',
    'SETTLEMENT': 'Settlement', 'LIQUIDACAO': 'Settlement', 'LIQUIDAÇÃO': 'Settlement',
    'CONFIRMATION LETTER': 'Confirmation Letter', 'CARTA DE CONFIRMACAO': 'Confirmation Letter',
    'CARTA DE CONFIRMAÇÃO': 'Confirmation Letter',
    'SETTLEMENT ADVICE': 'Settlement Advice', 'AVISO DE LIQUIDACAO': 'Settlement Advice',
    'AVISO DE LIQUIDAÇÃO': 'Settlement Advice',
    'CONTACT CONFIRMATION': 'Contact Confirmation', 'CONFIRMACAO DE CONTATO': 'Contact Confirmation',
    'IOF': 'IOF',
}


def _cc_cell(row, idx):
    if idx >= len(row):
        return ''
    v = row[idx]
    if v is None:
        return ''
    if isinstance(v, float):
        if v != v:                 # NaN
            return ''
        if v.is_integer():         # 123.0 (numeric SPN) → '123'
            return str(int(v))
    return str(v).strip()


# ----------------------------------------------------------------------------
#  Placeholder e-mail filter.
#  The source spreadsheet is filled by hand, so a contact with no real address
#  often carries a stand-in instead of a blank cell: 'xxx', 'x-x', 'a definir',
#  and — the tricky ones — strings that ARE valid e-mail syntax but address
#  nobody, like 'xx@xx.com'. Sending confirmations to those bounces, so they
#  are dropped on import and swept out of the stored base.
# ----------------------------------------------------------------------------
_CC_EMAIL_RE = re.compile(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')

# Tokens that never name a real mailbox or company, checked against the local
# part and against the domain's first label ('xx' in 'xx.com.br').
_CC_PLACEHOLDER_TOKENS = {
    'ab', 'abc', 'asd', 'asdf', 'qwerty',
    'na', 'nan', 'n/a', 'none', 'null', 'nulo', 'nil', 'vazio', 'branco',
    'test', 'teste', 'testing', 'example', 'exemplo', 'sample', 'dummy', 'fake',
    'email', 'e-mail', 'mail', 'correio', 'sememail', 'sem-email', 'seemail',
    'naotem', 'nao-tem', 'notem', 'nada', 'adefinir', 'a-definir', 'definir',
    'tbd', 'todo', 'pendente', 'placeholder', 'nomail', 'no-mail',
}
# Domains reserved by RFC 2606 / commonly used as stand-ins.
_CC_PLACEHOLDER_DOMAINS = {'example.com', 'example.org', 'example.net',
                           'test.com', 'teste.com', 'email.com', 'mail.com',
                           'dominio.com', 'empresa.com'}


def _cc_is_placeholder_token(tok, min_len=2):
    """A token that cannot be a real mailbox/company name: a known stand-in word,
    or filler made of one repeated character.

    Two deliberate escape hatches, because dropping a live address costs far more
    than keeping a dead one:
      * `min_len` — 2 for the local part, since a one-letter mailbox is unusual
        but real ('j@nubank.com.br'); 1 for the domain, where it never is.
      * repeated letters other than 'x' only count as filler from three
        characters on — 'bb.com.br' is Banco do Brasil, not a placeholder.
        'x' is the universal stand-in and digits never name a company."""
    t = (tok or '').strip().lower()
    if not t:
        return True
    if t in _CC_PLACEHOLDER_TOKENS:
        return True
    if len(t) < min_len or len(set(t)) != 1 or not t.isalnum():
        return False
    return t[0] == 'x' or t[0].isdigit() or len(t) >= 3


def _cc_email_is_usable(email):
    """True when `email` looks like an address that could actually receive mail.
    A BLANK e-mail is not a placeholder — the caller decides what to do with a
    contact that simply has none."""
    e = (email or '').strip().lower()
    if not e or not _CC_EMAIL_RE.match(e):
        return False
    local, _, domain = e.partition('@')
    if domain in _CC_PLACEHOLDER_DOMAINS:
        return False
    if _cc_is_placeholder_token(local):
        return False
    # First domain label: 'xx' in 'xx.com.br', 'amaggi' in 'amaggi.com.br'.
    return not _cc_is_placeholder_token(domain.split(".")[0], min_len=1)


def _cc_drop_placeholder_contacts(contacts):
    """(kept, dropped[]) — a contact whose e-mail is filled in but unusable is
    dropped; one with a blank e-mail is left untouched."""
    kept, dropped = [], []
    for c in contacts or []:
        email = str((c or {}).get('email', '') or '').strip()
        if email and not _cc_email_is_usable(email):
            dropped.append(c)
        else:
            kept.append(c)
    return kept, dropped


def _cc_parse_rules(raw):
    out, seen = [], set()
    for part in str(raw or '').replace('\n', ';').replace('/', ';').replace(',', ';').split(';'):
        p = part.strip()
        if not p:
            continue
        # 'Active'/'Inactive' são status do contato, não regra — a planilha
        # mistura os dois na mesma célula e o valor acabava duplicado na tela.
        if p.upper() in ('ACTIVE', 'INACTIVE'):
            continue
        canon = _CONTACT_RULE_MAP.get(p.upper(), p)
        if canon.upper() not in seen:
            seen.add(canon.upper())
            out.append(canon)
    return out


def _cc_read_rows(filename, raw_bytes):
    """Return a list of rows (each a list of cell values) from an uploaded
    .xlsx/.xlsm, .csv, .tsv or .txt. Raises ValueError on an unsupported type."""
    name = (filename or '').lower()
    if name.endswith(('.csv', '.tsv', '.txt')):
        import csv as _csv
        # Pick the first encoding that decodes WITHOUT replacement chars, so accented
        # headers (Código, Início, …) never turn into mojibake regardless of the
        # export encoding (utf-8 / Windows-1252 / Latin-1). latin-1 never fails and is
        # byte-exact for ISO-8859-1, so it is the guaranteed last resort.
        text = None
        for enc in ('utf-8-sig', 'cp1252', 'latin-1'):
            try:
                cand = raw_bytes.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
            if '�' not in cand:
                text = cand
                break
        if text is None:
            text = raw_bytes.decode('latin-1', errors='replace')
        if name.endswith('.tsv'):
            delimiter = '\t'
        elif name.endswith('.txt'):
            # Auto-detect: financial exports use tab/';' so the comma thousand
            # separators inside numbers ("-1,802,855.64") don't split columns.
            first = next((ln for ln in text.splitlines() if ln.strip()), '')
            delimiter = '\t' if '\t' in first else (';' if ';' in first else ',')
        else:
            delimiter = ','
        return [list(r) for r in _csv.reader(io.StringIO(text), delimiter=delimiter)]
    if name.endswith(('.xlsx', '.xlsm')):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), read_only=True, data_only=True)
        ws = wb.active
        return [list(r) for r in ws.iter_rows(values_only=True)]
    raise ValueError('Unsupported file type. Please upload .xlsx, .xlsm, .csv or .tsv.')

# ──────────────────────────────────────────────────────────────────────────
# Banking accounts — maker/checker (Pending → Active) + Default PAY/RECEIVE
# Model in CounterpartyDetails.json:
#   BANKING: { ACCOUNTS:[{id,bank,agency,account,status,maker,checker}],
#              DEFAULT_PAY:{current,pending,maker,checker},
#              DEFAULT_RECEIVE:{...} }
# ⚠️ SPN matching ignores leading zeros on both sides.
# ──────────────────────────────────────────────────────────────────────────
def _cpd_path():
    from apps.pages import routes
    return os.path.join(routes._B3_DATA_DIR, 'CounterpartyDetails.json')


def _cpd_load():
    # DB-first (fase 3): os registros ORIGINAIS pela coluna `_raw` do
    # reference_data.db, quando o manifest prova o frescor — a fidelidade é
    # total (chave-ausente incluída, que é o que o `_contacts_norm` lê), então
    # a migração one-shot abaixo roda igual nas duas fontes. Sem banco fresco,
    # o JSON de sempre. E SÓ quando `_cpd_path()` é o arquivo CANÔNICO que o
    # espelho cobre: um `_cpd_path` trocado (o check_cpd_api aponta para um
    # arquivo próprio) tem de continuar mandando — o banco reflete OUTRO
    # arquivo, e responder por ele seria ler a fonte errada com carimbo de
    # fresca.
    data = None
    try:
        from apps.pages import duck_read
        data = duck_read.cpd_records(expected_path=_cpd_path())
    except Exception:                                       # noqa: BLE001
        data = None
    if data is None:
        try:
            with open(_cpd_path(), encoding='utf-8') as fh:
                data = json.load(fh)
            data = data if isinstance(data, list) else []
        except (json.JSONDecodeError, IOError, FileNotFoundError):
            return []
    # Migração one-shot do formato legado (BANKING.PAY/RECEIVE, contatos sem
    # id/appr, CGD string, NET ausente): normaliza TODOS os registros e
    # persiste na primeira leitura em que algo mudou. Sem isso os ids de
    # contas/contatos legados eram sorteados de novo a cada request (uuid) e o
    # id que o modal manda num edit nunca batia com o do backend →
    # 'not_found' mesmo com o registro existindo no JSON. A normalização é
    # idempotente, então depois da primeira gravação nada mais muda.
    changed = False
    for rec in data:
        if not isinstance(rec, dict):
            continue
        norm = {'CGD':      _cgd_norm(rec.get('CGD')),
                'CONTACTS': _contacts_norm(rec.get('CONTACTS')),
                'BANKING':  _bank_norm(rec.get('BANKING')),
                'NET':      _net_norm(rec.get('NET'))}
        for k, v in norm.items():
            if rec.get(k) != v:
                rec[k] = v
                changed = True
    if changed:
        try:
            _cpd_save_list(data)
            log.info('[counterparty-details] legacy records migrated to the '
                     'canonical shape (stable ids)')
        except (IOError, OSError):
            log.warning('[counterparty-details] legacy migration could not be saved')
    return data


def _norm_spn(value):
    s = str(value or '').strip()
    if s.endswith('.0'):
        s = s[:-2]
    s = s.lstrip('0')
    return s or ('0' if value not in (None, '') else '')


def _cpd_find(data, spn):
    target = _norm_spn(spn)
    for rec in data:
        if _norm_spn(rec.get('SPN', '')) == target:
            return rec
    return None


def _cpd_save_list(data):
    path = _cpd_path()
    try:
        shutil.copy2(path, path + '.bak')
    except (IOError, OSError):
        pass
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    # Espelho vivo (fase 2): a tabela counterparty_details do
    # reference_data.db acompanha na hora. Melhor esforço.
    try:
        from apps.pages import duck_mirror
        duck_mirror.notify_write(path)
    except Exception:                                       # noqa: BLE001
        pass

def _contacts_norm(contacts):
    """Coerce stored CONTACTS into maker/checker items. `status` keeps the business
    Active/Inactive value; approval state lives in `appr` (Pending/Active) + maker/checker.
    Legacy contacts (no appr/maker keys) are imported as already approved."""
    out = []
    for c in (contacts or []):
        c = c or {}
        legacy = ('appr' not in c) and ('maker' not in c)
        rules = c.get('rules')
        if not isinstance(rules, list):
            rules = c.get('RULES') if isinstance(c.get('RULES'), list) else []
        out.append({
            'id':      c.get('id') or uuid.uuid4().hex[:8],
            'name':    c.get('name')  or c.get('NAME')  or '',
            'phone':   c.get('phone') or c.get('PHONE') or '',
            'email':   c.get('email') or c.get('EMAIL') or '',
            'rules':   rules,
            'status':  c.get('status') or c.get('STATUS') or 'Active',
            'appr':    c.get('appr') or ('Active' if legacy else 'Pending'),
            'maker':   c.get('maker', '') or ('IMPORT' if legacy else ''),
            'checker': c.get('checker', '') or ('IMPORT' if legacy else ''),
        })
    return out

def _net_norm(net):
    """Coerce a stored Settlement Net Type into {value,status,maker,checker}.
    Missing/legacy records default to Total Net, already Active (imported)."""
    if not isinstance(net, dict):
        net = {}
    val = str(net.get('value', '') or '').strip()
    return {
        'value':   val if val in _CP_NET_TYPES else 'Total Net',
        'status':  net.get('status', 'Active') or 'Active',
        'maker':   net.get('maker', '') or '',
        'checker': net.get('checker', '') or '',
    }

def _default_slot(existing=None):
    existing = existing or {}
    return {
        'current': existing.get('current') or None,
        'pending': existing.get('pending') or None,
        'maker':   existing.get('maker', '') or '',
        'checker': existing.get('checker', '') or '',
    }


def _bank_norm(bank):
    """Coerce any stored BANKING shape into the ACCOUNTS + defaults model."""
    if not isinstance(bank, dict):
        bank = {}
    accounts = bank.get('ACCOUNTS')
    if not isinstance(accounts, list):
        accounts = []
        legacy = []
        for key in ('PAY', 'RECEIVE'):
            for b in (bank.get(key) or []):
                legacy.append({'bank': b.get('bank', ''), 'agency': b.get('agency', ''),
                               'account': b.get('account', '')})
        seen = set()
        for a in legacy:
            k = (a['bank'], a['agency'], a['account'])
            if any(a.values()) and k not in seen:
                seen.add(k)
                accounts.append({'id': uuid.uuid4().hex[:8], 'bank': a['bank'],
                                 'agency': a['agency'], 'account': a['account'],
                                 'status': 'Active', 'maker': 'IMPORT', 'checker': 'IMPORT'})
    out = []
    for a in accounts:
        a = a or {}
        out.append({
            'id':      a.get('id') or uuid.uuid4().hex[:8],
            'bank':    a.get('bank', ''), 'agency': a.get('agency', ''),
            'account': a.get('account', ''),
            'status':  a.get('status', 'Active') or 'Active',
            'maker':   a.get('maker', '') or '', 'checker': a.get('checker', '') or '',
        })
    return {'ACCOUNTS': out,
            'DEFAULT_PAY': _default_slot(bank.get('DEFAULT_PAY')),
            'DEFAULT_RECEIVE': _default_slot(bank.get('DEFAULT_RECEIVE'))}


def _cgd_norm(cgd):
    """Coerce stored CGD into a list of maker/checker items.
    Legacy shapes (string / list-of-strings) become Active items imported."""
    items = []
    raw = cgd if isinstance(cgd, list) else ([cgd] if cgd not in (None, '') else [])
    for x in raw:
        if isinstance(x, dict):
            val = str(x.get('value', '') or '').strip()
            if not val:
                continue
            items.append({
                'id':      x.get('id') or uuid.uuid4().hex[:8],
                'value':   val,
                'status':  x.get('status', 'Active') or 'Active',
                'maker':   x.get('maker', '') or '',
                'checker': x.get('checker', '') or '',
            })
        else:
            val = str(x).strip()
            if val:
                items.append({'id': uuid.uuid4().hex[:8], 'value': val,
                              'status': 'Active', 'maker': 'IMPORT', 'checker': 'IMPORT'})
    return items


# Settlement Net Type — single value per counterparty with maker/checker.
# Item: {value ∈ _CP_NET_TYPES, status ∈ Active|Pending, maker, checker}
_CP_NET_TYPES = ['Total Net', 'Pay/Rec', 'No Net']
