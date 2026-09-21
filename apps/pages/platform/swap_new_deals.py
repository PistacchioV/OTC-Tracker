# -*- coding: utf-8 -*-
"""O que as duas páginas de swap de New Deals (Bullet e Cashflow) FAZEM igual
e que precisa do mundo: ler o Deal Ticket solto no dropzone, consultar os
cadastros (contas B3, Reference Data, códigos), completar o deal com eles e
disparar o que vem depois do B3 ID.

Horizontal desde 21/09/2026 — nasceu espalhado pelo `queries`/`commands`/
`infra` do Swap Bullet e saiu de lá quando o Swap Cashflow passou a precisar
das mesmas respostas (feature não importa feature). As regras PURAS estão em
`platform/swap_deal_ticket.py`; aqui fica só o que lê cadastro ou grava.

Platform não importa feature nem NOME do routes: o que ainda é do `routes`
(`_mapping_rows`, `_refdata_records`, `_intrag_engine`, `_pc_save_from_deal`…)
é busca ATRASADA dentro da função — é o que deixa os testes trocarem o
atributo no `routes` e verem a troca aqui.
"""
import datetime as _dt
import io
import re
import traceback
from datetime import datetime

from apps.pages.platform import swap_deal_ticket as _dtk


def _R():
    from apps.pages import routes
    return routes


# ── O Deal Ticket solto no dropzone → grades e textos ────────────────────────
# xlsx/xlsm: UMA grade por aba (no Bullet a primeira aba é o DT contra o
# cliente e a segunda o B2B Banco × Atacama; abas sem Valor Base + Vencimento
# são ignoradas por quem chama). A célula vira texto de forma determinística:
# data → ISO; número com formato de porcentagem → 'NN.NN%' (o Excel guarda
# 100,00% como 1.0 — sem o formato o parser leria 1%); inteiro sem `.0`.
# PDF: o texto de cada página (pypdf) — uma operação por página.

def cell_text(v, number_format=''):
    if v is None:
        return ''
    if isinstance(v, bool):
        return 'TRUE' if v else 'FALSE'
    if isinstance(v, _dt.datetime):
        return v.strftime('%Y-%m-%d')
    if isinstance(v, _dt.date):
        return v.strftime('%Y-%m-%d')
    if isinstance(v, (int, float)):
        f = float(v)
        if f != f:
            return ''
        if '%' in str(number_format or ''):
            return ('%.4f' % (f * 100)).rstrip('0').rstrip('.') + '%'
        if f.is_integer() and abs(f) < 1e15:
            return str(int(f))
        return ('%.10f' % f).rstrip('0').rstrip('.')
    return str(v)


def sheets_from_xlsx(data):
    """[(título, grade)] de todas as abas, células como texto."""
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    out = []
    for ws in wb.worksheets:
        grid = []
        for row in ws.iter_rows():
            grid.append([cell_text(c.value, getattr(c, 'number_format', '')) for c in row])
        out.append((ws.title, grid))
    wb.close()
    return out


def pages_from_pdf(data):
    """[texto] por página do PDF. Levanta ValueError se o pypdf não estiver
    instalado ou o arquivo não for legível."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:                              # pragma: no cover
        raise ValueError('pypdf is not installed (pip install pypdf)') from exc
    reader = PdfReader(io.BytesIO(data))
    return [(p.extract_text() or '') for p in reader.pages]


# O que o arquivo É, pelo CONTEÚDO — o Outlook renomeia anexo e um .xlsx chega
# como .txt sem aviso (a mesma lição do dropzone da recompra, §488).
_MAGIC_ZIP = b'PK\x03\x04'
_MAGIC_PDF = b'%PDF'
_MAGIC_CFB = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'      # o .msg do Outlook (e o .xls antigo)


def kind_of(data):
    """'xlsx' | 'pdf' | 'msg' | 'eml' | 'html' | '' — pelos primeiros bytes."""
    head = bytes(data[:4096] or b'')
    if head.startswith(_MAGIC_ZIP):
        return 'xlsx'
    if head.lstrip().startswith(_MAGIC_PDF):
        return 'pdf'
    if head.startswith(_MAGIC_CFB):
        return 'msg'
    txt = head.decode('latin-1', 'replace')
    low = txt.lower()
    if re.search(r'^(from|to|subject|mime-version|content-type|received|date|message-id):',
                 txt, re.I | re.M) and ('mime-version' in low or 'content-type' in low):
        return 'eml'
    if '<table' in low or '<html' in low:
        return 'html'
    return ''


class _TableGrid(object):
    """As <table> de um HTML como grades de texto (uma por tabela) — o Deal
    Ticket colado no CORPO de um e-mail. Sem dependência: html.parser."""

    def __init__(self):
        from html.parser import HTMLParser
        grids, pilha = [], []

        class P(HTMLParser):
            def handle_starttag(self, tag, attrs):
                if tag == 'table':
                    pilha.append({'rows': [], 'row': None, 'cell': None})
                elif not pilha:
                    return
                elif tag == 'tr':
                    pilha[-1]['row'] = []
                elif tag in ('td', 'th'):
                    pilha[-1]['cell'] = []
                    span = dict(attrs).get('colspan')
                    pilha[-1]['span'] = int(span) if str(span or '').isdigit() else 1
                elif tag == 'br' and pilha[-1]['cell'] is not None:
                    pilha[-1]['cell'].append(' ')

            def handle_endtag(self, tag):
                if not pilha:
                    return
                t = pilha[-1]
                if tag in ('td', 'th') and t['cell'] is not None and t['row'] is not None:
                    t['row'].append(' '.join(''.join(t['cell']).split()))
                    t['row'].extend([''] * (t.get('span', 1) - 1))
                    t['cell'] = None
                elif tag == 'tr' and t['row'] is not None:
                    t['rows'].append(t['row'])
                    t['row'] = None
                elif tag == 'table':
                    grids.append(pilha.pop()['rows'])

            def handle_data(self, data):
                if pilha and pilha[-1]['cell'] is not None:
                    pilha[-1]['cell'].append(data)

        self.grids = grids
        self.parser = P(convert_charrefs=True)


def grids_from_html(text):
    tg = _TableGrid()
    tg.parser.feed(str(text or ''))
    tg.parser.close()
    return [g for g in tg.grids if g]


def _attachments_of_msg(data):
    """(corpo html, [(nome, bytes)]) de um .msg do Outlook."""
    import extract_msg
    msg = extract_msg.openMsg(io.BytesIO(data))
    corpo = getattr(msg, 'htmlBody', None) or b''
    if isinstance(corpo, bytes):
        corpo = corpo.decode('utf-8', 'replace')
    anexos = []
    for a in getattr(msg, 'attachments', None) or []:
        dados = getattr(a, 'data', None)
        if isinstance(dados, (bytes, bytearray)):
            anexos.append((str(getattr(a, 'longFilename', None) or getattr(a, 'shortFilename', None) or 'anexo'),
                           bytes(dados)))
    return corpo, anexos


def _attachments_of_eml(data):
    """(corpo html, [(nome, bytes)]) de um .eml (MIME)."""
    import email
    import email.policy
    msg = email.message_from_bytes(bytes(data), policy=email.policy.default)
    corpo, anexos = '', []
    for part in msg.walk():
        if part.is_multipart():
            continue
        nome = part.get_filename()
        if nome:
            anexos.append((str(nome), part.get_payload(decode=True) or b''))
        elif part.get_content_type() == 'text/html' and not corpo:
            try:
                corpo = part.get_content()
            except Exception:                               # noqa: BLE001
                corpo = (part.get_payload(decode=True) or b'').decode('utf-8', 'replace')
    return corpo, anexos


def read_upload(filename, data, _depth=0):
    """O arquivo do dropzone → [(kind, título, payload)], com `kind` 'grid'
    (grade de uma aba ou de uma tabela HTML) ou 'text' (página de PDF).

    Lido pelo CONTEÚDO, nunca pela extensão. O e-mail (.msg/.eml) entra pelos
    ANEXOS que são Deal Ticket (xlsx/pdf); sem anexo que sirva, pelas tabelas
    do corpo. Levanta ValueError para o que não é nenhum dos formatos."""
    k = kind_of(data)
    nome = str(filename or '')
    if k == 'xlsx':
        return [('grid', t, g) for t, g in sheets_from_xlsx(data)]
    if k == 'pdf':
        return [('text', '%s › page %d' % (nome, i + 1) if _depth else 'page %d' % (i + 1), t)
                for i, t in enumerate(pages_from_pdf(data))]
    if k == 'html':
        texto = bytes(data).decode('utf-8', 'replace')
        return [('grid', 'table %d' % (i + 1), g) for i, g in enumerate(grids_from_html(texto))]
    if k in ('msg', 'eml') and _depth == 0:
        corpo, anexos = (_attachments_of_msg if k == 'msg' else _attachments_of_eml)(data)
        out = []
        for an, ad in anexos:
            if kind_of(ad) in ('xlsx', 'pdf'):
                out.extend((kk, an + ' › ' + t, p) for kk, t, p in read_upload(an, ad, _depth + 1))
        if not out and corpo:
            out = [('grid', 'e-mail table %d' % (i + 1), g) for i, g in enumerate(grids_from_html(corpo))]
        return out
    raise ValueError('unsupported file — drop the Deal Ticket as .xlsx or .pdf, '
                     'or the e-mail that carries it')


# ── Cadastros ────────────────────────────────────────────────────────────────

def own_accounts():
    """{LE: conta PRÓPRIA só dígitos} do `b3-accounts` — 'JPM': '73760009'."""
    out = {}
    for row in _R()._mapping_rows('b3-accounts'):
        le = str(row.get('LE', '') or '').strip().upper()
        if not le or _R()._b3_account_type(row.get('ACCOUNT TYPE', '')) != 'OWN':
            continue
        acc = re.sub(r'\D', '', str(row.get('ACCOUNT', '') or ''))
        if acc and le not in out:
            out[le] = acc
    return out


def omnibus_account(le='JPM', kind='CLIENT 2'):
    """A conta guarda-chuva de clientes da LE (o omnibus)."""
    for row in _R()._mapping_rows('b3-accounts'):
        if str(row.get('LE', '') or '').strip().upper() != le:
            continue
        if _R()._b3_account_type(row.get('ACCOUNT TYPE', '')) == kind:
            return re.sub(r'\D', '', str(row.get('ACCOUNT', '') or ''))
    return ''


def le_by_spn(spn):
    """SPN de entidade NOSSA pelo cadastro `le-spn` → {LE, NAME, SPN} ou None."""
    return _dtk.le_for_spn(_R()._mapping_rows('le-spn'), spn)


def refdata_by_spn(spn):
    """O registro do Reference Data da SPN (ou {})."""
    key = _R()._spn_key(spn)
    if not key:
        return {}
    for rec in _R()._refdata_records():
        if _R()._spn_key(rec.get('SPN', '')) == key:
            return rec
    return {}


def codes_for(deal):
    """Os códigos B3 dos campos cadastráveis do deal, pelos de-para do
    /mapping. Vazio = lacuna (o preview mostra, o Send recusa)."""
    func_rows = _R()._mapping_rows('swap-funcionalidade')
    code_rows = _R()._mapping_rows('swap-code-labels')
    curve_rows = _R()._mapping_rows('swap-bullet-curve')
    func_txt = str(deal.get('Functionality') or '').strip()
    if _dtk.norm(func_txt) in ('', 'NA', 'N', 'NAO', 'NENHUMA', 'NONE', 'SEM'):
        func_txt = 'SEM FUNCIONALIDADE'
    codes = {
        'functionality': _dtk.code_by_label(func_rows, func_txt),
        'adhesion': _dtk.code_by_label(code_rows, deal.get('Adhesion', ''), field='Adesão'),
        'premium_schedule': _dtk.code_by_label(code_rows, deal.get('PremiumSchedule', ''), field='Sim/Não'),
        'reset': _dtk.code_by_label(code_rows, deal.get('Reset', ''), field='Sim/Não'),
        'signA': _dtk.code_by_label(code_rows, deal.get('CurveASign', '+'), field='Sinal Taxa'),
        'signB': _dtk.code_by_label(code_rows, deal.get('CurveBSign', '+'), field='Sinal Taxa'),
        'curveA': _dtk.curve_code(curve_rows, deal.get('CurveA', ''), deal.get('CurveACategory', '')),
        'curveB': _dtk.curve_code(curve_rows, deal.get('CurveB', ''), deal.get('CurveBCategory', '')),
    }
    return codes


def template_blocks(key):
    """Os blocos do template do File Interpreter (lista) — [] sem template."""
    tpl = _R()._fi_tpl_cached(key)
    return list((tpl or {}).get('blocks') or [])


def participant(le):
    """O Nome Simplificado do participante da LE (header dos arquivos)."""
    nome = _R()._b3_participant_name(le)
    if not nome:
        raise ValueError('B3 Accounts: no Simplified Name registered for legal entity %r '
                         '— register it at /mapping › B3 Accounts' % le)
    return nome


def fields_of(key, per_block, record_vals):
    """[{seq, block, field, value}] na ordem do template — rótulo do
    cadastro, valor do gerador (o que o motor vai posicionar). `per_block`
    = {id do bloco: valores}; bloco sem entrada usa `record_vals`."""
    rows = []
    for b in template_blocks(key):
        src = per_block.get(b.get('id'))
        if src is None:
            src = record_vals or {}
        for f in b.get('fields') or []:
            seq = str(f.get('seq', '')).strip()
            rows.append({'seq': seq, 'block': b.get('title', ''), 'field': f.get('field', ''),
                         'format': f.get('format', ''), 'position': f.get('position', ''),
                         'source': f.get('source', ''),
                         'value': str(src.get(seq, src.get(seq.lstrip('0') or '0', '')))})
    return rows


# ── Completar o deal com os cadastros ────────────────────────────────────────

def enrich(deal):
    """Completa o deal com o que NÃO está no DT: a conta B3 e o CNPJ da
    contraparte (Reference Data pela SPN; sem conta própria, o omnibus de
    clientes do Banco + o Tax ID), e o código D-n da Data de Cotação (dias
    úteis ANBIMA até o vencimento). Só preenche o que está em branco — o que
    a mesa editou fica."""
    # SPN de entidade NOSSA (cadastro le-spn): a contraparte é a Atacama (o
    # B2B), ou outra perna intragrupo — nome e conta vêm do cadastro, não do
    # Reference Data, onde essa SPN nunca esteve.
    le = le_by_spn(deal.get('SPN', '')) if deal.get('SPN') else None
    if le:
        deal['LE'] = 'ATACAMA' if le['LE'] == 'ATACAMA' else deal.get('LE') or 'JPM'
        deal['Pair'] = 'JPM x ATACAMA' if le['LE'] == 'ATACAMA' else 'JPM x CLI'
        deal['Client'] = le['NAME'] or le['LE']
        deal['ClientRefData'] = 'ok'
        deal['ClientTaxId'] = ''
        deal.pop('ClientAccountNote', None)
        conta = own_accounts().get(le['LE'], '')
        if conta:
            deal['ClientAccount'] = conta
    if not le and not _dtk.is_b2b(deal):
        # A contraparte é IDENTIFICADA pela SPN do DT (o nome no DT é um
        # apelido — 'Safra'): quem responde nome, CNPJ e conta B3 é o
        # Reference Data. Sem SPN, tenta o nome do DT como último recurso.
        rec = refdata_by_spn(deal.get('SPN', '')) if deal.get('SPN') else {}
        if not rec and not deal.get('SPN') and deal.get('ClientDT'):
            alvo = _dtk.norm(deal.get('ClientDT'))
            for r in _R()._refdata_records():
                if _dtk.norm(r.get('COUNTERPARTY', '')) == alvo:
                    rec = r
                    break
        deal['ClientRefData'] = 'ok' if rec else ''
        if rec:
            nome = str(rec.get('COUNTERPARTY', '') or '').strip()
            if nome:
                deal['Client'] = nome
            if not deal.get('SPN'):
                deal['SPN'] = re.sub(r'\.0$', '', str(rec.get('SPN', '') or ''))
            if not deal.get('ClientTaxId'):
                deal['ClientTaxId'] = re.sub(r'\D', '', str(rec.get('TAX ID', '') or ''))
            if not deal.get('ClientAccount'):
                acc = re.sub(r'\D', '', str(rec.get('B3 ACCOUNT', '') or ''))
                if acc:
                    deal['ClientAccount'] = acc
                    deal['ClientTaxId'] = ''        # conta própria do cliente: sem CNPJ no registro
        if not deal.get('ClientAccount'):
            omni = omnibus_account('JPM', 'CLIENT 2')
            if omni:
                deal['ClientAccount'] = omni
                deal['ClientAccountNote'] = 'omnibus'
    if not str(deal.get('QuoteDateCode') or '').strip():
        q = _dtk.parse_date(deal.get('QuoteDate'))
        m = _dtk.parse_date(deal.get('MaturityDate'))
        if q and m:
            n = _R()._anbima_biz_diff(datetime(q.year, q.month, q.day), datetime(m.year, m.month, m.day))
            deal['QuoteDateCode'] = str(min(max(n, 0), 5)).zfill(2)
    if not str(deal.get('VcpText') or '').strip():
        deal['VcpText'] = _dtk.vcp_text(deal)
    return deal


# ── Depois do B3 ID (§481) ───────────────────────────────────────────────────

def confirmation_deal(deal):
    """O deal no formato das confirmações (`swap_deal_ticket.confirmation_deal`)
    com o CNPJ da contraparte do Reference Data — o `enrich` o apaga da linha
    quando o cliente tem conta B3 própria (não vai no registro), e o
    documento e o XML precisam dele."""
    out = _dtk.confirmation_deal(deal)
    if not re.sub(r'\D', '', str(out.get('TaxID') or '')):
        rec = refdata_by_spn(deal.get('SPN', '')) if deal.get('SPN') else {}
        out['TaxID'] = re.sub(r'\D', '', str((rec or {}).get('TAX ID', '') or ''))
    return out


def b3_mapped(deal, tag='SWAP'):
    """O deal ganhou B3 ID. No B2B, a linha da **Intrag Swap** (a visão da
    Atacama, na carteira dela); contra cliente, a linha do **Pending
    Confirmation** e a da esteira de **Manual Confirmations** (Produto SWAP /
    SWAP CORPORATE, chave = B3 ID, LOB do deal). Cada braço se protege: a
    falha vai para o log com o traceback e não derruba a gravação da grade.
    `tag` é só o prefixo do log (`SWAP BULLET`, `SWAP CASHFLOW`)."""
    b3 = str(deal.get('B3ID') or '').strip()
    if not b3:
        return
    try:
        if _dtk.is_b2b(deal):
            entry = _dtk.intrag_swap_entry(deal, codes_for(deal))
            start = _dtk.parse_date(deal.get('StartDate')) or _dtk.parse_date(deal.get('TradeDate'))
            start_dt = datetime(start.year, start.month, start.day) if start else None
            _R()._intrag_engine()._save_intrag_swap_entry(entry, start_dt)
        else:
            tipo = _dtk.confirmation_source(deal)
            # A mesma porta das outras páginas: o `_pc_save_from_deal` pula a
            # perna interna sozinho e é ele quem chama o `_mc_save_from_deal`.
            _R()._pc_save_from_deal(confirmation_deal(deal), tipo, pending_status='Pending OTC',
                                    trade_number=b3, source=tipo)
    except Exception:                                       # noqa: BLE001
        _R().log.warning('[%s] post-mapping flow failed for %s:\n%s', tag, b3, traceback.format_exc())
