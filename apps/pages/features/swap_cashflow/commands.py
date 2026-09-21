# -*- coding: utf-8 -*-
"""Escritas do Swap Cashflow: importar o Deal Ticket (com a tabela Cash
Flow), completar o deal com os cadastros, montar os arquivos da B3 — o
contrato de Fluxo Não Constante (0301 v00003), o cronograma (0034) e, com
agenda de prêmio, o 0897 — e gravá-los no Batch Conecta."""
import os
import random
import re
from datetime import datetime

from apps.pages.platform import swap_deal_ticket as _dtk
from apps.pages.platform import swap_new_deals as _sw
from apps.pages.features.swap_cashflow import domain, queries
from apps.pages.features.swap_cashflow.infra import persistence


def _R():
    from apps.pages import routes
    return routes


CONTRACT_FI_KEY = 'swap-fluxo-nao-constante-v3'
FLOW_FI_KEY = 'swap-fluxo-contrato-nao-constante'
PREMIUM_FI_KEY = 'swap-registro-premio'
PAGE_URL = '/new_deals-swap-cashflow'

# O nome padrão de cada arquivo por visão (`{lob}` = 'CEM_'); o `file_name`
# da VARIANTE do template (por par de pernas) vence quando cadastrado. O `CF`
# separa estes dos arquivos do Swap Bullet, que caem na MESMA pasta do Batch
# Conecta com o mesmo prefixo SWAP_ (SUPOSIÇÃO de nome — o Conecta lê o layout
# pelo header, não pelo nome do arquivo).
CONTRACT_FILE_NAMES = {'client': 'SWAP_CF_{lob}CLIENTE.txt', 'bank': 'SWAP_CF_{lob}BANCO.txt',
                       'atacama': 'SWAP_CF_{lob}ATACAMA.txt'}
FLOW_FILE_NAMES = {'client': 'FLUXO_SWAP_CF_{lob}CLIENTE.txt', 'bank': 'FLUXO_SWAP_CF_{lob}BANCO.txt',
                   'atacama': 'FLUXO_SWAP_CF_{lob}ATACAMA.txt'}
PREMIUM_FILE_NAMES = {'client': 'PREMIO_SWAP_CF_{lob}CLIENTE.txt', 'bank': 'PREMIO_SWAP_CF_{lob}BANCO.txt',
                      'atacama': 'PREMIO_SWAP_CF_{lob}ATACAMA.txt'}

# O Conecta lê o arquivo como ANSI (cp1252): cada caractere é UM byte (§480).
FILE_ENCODING = 'cp1252'

_MY_NUMBERS = ('MyNumber', 'MyNumberMirror', 'PremiumMyNumber', 'PremiumMyNumberMirror',
               'FlowMyNumber', 'FlowMyNumberMirror')


def _rand10():
    return str(random.randint(1000000000, 9999999999))


# ── Import ───────────────────────────────────────────────────────────────────

def parse_upload(filename, data, trade_iso):
    """O arquivo do dropzone → (deals, ignorados). Lido pelo CONTEÚDO
    (`platform/swap_new_deals.read_upload`): xlsx, pdf, ou o e-mail (.msg/
    .eml) que carrega um dos dois. Cada aba/página que é Deal Ticket vira um
    deal com o cronograma da tabela Cash Flow dela."""
    deals, ignorados = [], []
    for kind, title, payload in _sw.read_upload(filename, data):
        if kind == 'grid':
            grade, flows = domain.split_cashflow_grid(payload)
            if not _dtk.is_dt_grid(grade):
                ignorados.append(title)
                continue
            raw = _dtk.parse_dt_grid(grade)
            extras = domain.cem_extras_grid(grade)
        else:
            if 'VALORBASE' not in _dtk.norm(payload) or 'VENCIMENTO' not in _dtk.norm(payload):
                ignorados.append(title)
                continue
            texto, flows = domain.split_cashflow_text(payload)
            raw = _dtk.parse_dt_text(texto)
            extras = domain.cem_extras_text(texto)
        deal = domain.deal_from_raw(raw, flows, trade_iso, extras)
        deal['_sheet'] = title
        enrich(deal)
        deals.append(deal)
    return deals, ignorados


def import_upload(filename, data, ref_dt, sid='', dry_run=False):
    """O arquivo do dropzone → deals no arquivo-dia da Trade Date `ref_dt`.
    `dry_run` só PARSEIA (o passo 1 do Import das páginas de New Deals: a
    tela confere as duplicatas e grava pelo `persist_deals`). Devolve os
    deals, as abas ignoradas e as lacunas de cada deal (estruturadas)."""
    trade_iso = ref_dt.strftime('%Y-%m-%d')
    deals, ignorados = parse_upload(filename, data, trade_iso)
    imported = 0 if dry_run else persist_deals(deals, sid=sid)
    return {'success': True, 'imported': imported, 'deals': deals, 'ignored': ignorados,
            'missing': missing_by_id(deals), 'trade_date': trade_iso, 'dry_run': bool(dry_run)}


def missing_by_id(deals):
    accounts = queries.own_accounts()
    out = {}
    for d in deals or []:
        faltas = lacunas(d, accounts)
        if faltas:
            out[d['_id']] = faltas
    return out


def lacunas(deal, accounts=None):
    codes = queries.codes_for(deal)
    return domain.missing_for_send(deal, codes, accounts if accounts is not None else queries.own_accounts(),
                                   codes.get('amortization'))


def _stamp_numbers(d):
    for k in _MY_NUMBERS:
        if not str(d.get(k) or '').strip():
            d[k] = _rand10()


def persist_deals(deals, sid=''):
    """Grava os deals (já montados) nos arquivos-dia das suas Trade Dates,
    dando os seis Meu Número a quem ainda não tem. Deal marcado `_replace` (a
    tela escolheu SUBSTITUIR uma duplicata) sai da esteira como `Amend`
    quando a linha antiga já tinha andado; New continua New. → gravados."""
    por_dia = {}
    for d in deals or []:
        if not isinstance(d, dict):
            continue
        d[domain.SCHEDULE_FIELD] = domain.normalize_schedule(d.get(domain.SCHEDULE_FIELD))
        d['Flows'] = str(len(d[domain.SCHEDULE_FIELD]))
        if not d.get('_id'):
            d['_id'] = domain.make_deal_id(d)
        _stamp_numbers(d)
        d['ImportedBy'] = sid
        d.setdefault('Status', 'New')
        replace = bool(d.pop('_replace', False))
        ref = _dtk.parse_date(d.get('TradeDate')) or datetime.now().date()
        ref_dt = datetime(ref.year, ref.month, ref.day)
        d['TradeDate'] = ref_dt.strftime('%Y-%m-%d')
        por_dia.setdefault(ref_dt, []).append((d, replace))
    n = 0
    for ref_dt, lst in por_dia.items():
        n += persistence.upsert(ref_dt, [d for d, _r in lst])
        amend = [d['_id'] for d, r in lst if r]
        if amend:
            with _R()._cache_lock:
                fp = persistence.day_path(ref_dt)
                entries = persistence.read_day(fp)
                mudou = False
                for e in entries:
                    if persistence.key_of(e) in amend and (e.get('Status') or 'New') != 'New':
                        e['Status'] = 'Amend'
                        e['Checker'] = ''
                        mudou = True
                if mudou:
                    persistence.write_day(fp, entries)
    return n


def enrich(deal):
    """O `enrich` do Bullet (conta B3, CNPJ e D-n pelos cadastros, na
    horizontal), mais o tipo de amortização na grafia do cadastro e a
    contagem de fluxos."""
    _sw.enrich(deal)
    deal['AmortizationType'] = domain.amortization_label(queries.amortization_rows(),
                                                         deal.get('AmortizationType', ''))
    deal[domain.SCHEDULE_FIELD] = domain.normalize_schedule(deal.get(domain.SCHEDULE_FIELD))
    deal['Flows'] = str(len(deal[domain.SCHEDULE_FIELD]))
    return deal


# ── Os arquivos ──────────────────────────────────────────────────────────────

def _today_ymd():
    return datetime.now().strftime('%Y%m%d')


def _file_name(key, view, default, deal=None):
    """O `file_name` cadastrado na variante do par vence; senão o padrão da
    visão com a LOB do deal no lugar de `{lob}`."""
    try:
        nome = _R()._fi_variant_file_name(key, PAGE_URL, _dtk.le_pair(view))
    except Exception:                                   # noqa: BLE001
        nome = ''
    if nome:
        return nome
    lob = re.sub(r'[^A-Z0-9]', '', str((deal or {}).get('LOB') or '').upper())
    return default.format(lob=lob + '_' if lob else '')


def _line(key, block, values, view, deal):
    return _R()._fi_build_line(key, block, values, page_url=PAGE_URL, le_pair=_dtk.le_pair(view), deal=deal)


def _record(key, values, view, deal, skip=('header',)):
    """Os blocos do template (menos o header) numa linha só — o registro do
    contrato é UMA linha que o manual apresenta em grupos."""
    parts = [_line(key, b['id'], values, view, deal)
             for b in queries.template_blocks(key) if b.get('id') not in skip]
    if not parts:
        raise ValueError('file-interpreter template missing: ' + key)
    return ''.join(parts)


class Lacunas(ValueError):
    """O deal tem lacuna: `itens` são as lacunas estruturadas (§486)."""

    def __init__(self, itens):
        self.itens = list(itens or [])
        ValueError.__init__(self, 'missing: ' + '; '.join(domain.lacuna_texts(self.itens)))


def deal_files(deal, view, today_ymd=None):
    """Os arquivos de UMA visão do deal: [{kind, key, file_name, header,
    records, fields, view, le_pair}] — o contrato (0301) e o cronograma
    (0034) sempre; o prêmio (0897) quando há agenda. Levanta `Lacunas`."""
    today_ymd = today_ymd or _today_ymd()
    accounts = queries.own_accounts()
    codes = queries.codes_for(deal)
    faltas = domain.missing_for_send(deal, codes, accounts, codes.get('amortization'))
    if faltas:
        raise Lacunas(faltas)
    parte_le = 'ATACAMA' if view == 'atacama' else 'JPM'
    participant = _sw.participant(parte_le)
    espelho = view == 'atacama'
    my_swap = deal.get('MyNumberMirror' if espelho else 'MyNumber') or _rand10()
    my_flow = deal.get('FlowMyNumberMirror' if espelho else 'FlowMyNumber') or _rand10()
    my_prem = deal.get('PremiumMyNumberMirror' if espelho else 'PremiumMyNumber') or _rand10()
    pair = _dtk.le_pair(view)
    out = []
    # 1. o contrato (4.2.7)
    vals = domain.contract_record_values(deal, view, accounts, codes, my_swap)
    hdr = domain.contract_header_values(participant, today_ymd)
    header = _line(CONTRACT_FI_KEY, 'header', hdr, view, deal)
    record = _record(CONTRACT_FI_KEY, vals, view, deal)
    if len(record) != domain.CONTRACT_RECORD_LENGTH:
        raise ValueError('0301 (fluxo não constante) record has %d characters, the layout wants %d '
                         '(check the file-interpreter template %s)'
                         % (len(record), domain.CONTRACT_RECORD_LENGTH, CONTRACT_FI_KEY))
    out.append({'kind': 'swap', 'label': 'Contract (0301)', 'key': CONTRACT_FI_KEY, 'view': view,
                'le_pair': pair, 'file_name': _file_name(CONTRACT_FI_KEY, view, CONTRACT_FILE_NAMES[view], deal),
                'header': header, 'records': [record],
                'fields': _sw.fields_of(CONTRACT_FI_KEY, {'header': hdr}, vals)})
    # 2. o cronograma (4.2.8)
    h, reg, linhas = domain.flow_values(deal, view, accounts, my_swap, my_flow, codes.get('amortization'),
                                        participant, today_ymd)
    fh = _line(FLOW_FI_KEY, 'header', h, view, deal)
    fr = _line(FLOW_FI_KEY, 'registro', reg, view, deal)
    fl = [_line(FLOW_FI_KEY, 'fluxo', x, view, deal) for x in linhas]
    if len(fr) != domain.FLOW_REGISTRO_LENGTH or any(len(x) != domain.FLOW_LINE_LENGTH for x in fl):
        raise ValueError('0034 record lengths differ from the layout (check the file-interpreter template %s)'
                         % FLOW_FI_KEY)
    campos = _sw.fields_of(FLOW_FI_KEY, {'header': h, 'registro': reg, 'fluxo': linhas[0] if linhas else {}},
                           None)
    out.append({'kind': 'flow', 'label': 'Cash Flow (0034)', 'key': FLOW_FI_KEY, 'view': view, 'le_pair': pair,
                'file_name': _file_name(FLOW_FI_KEY, view, FLOW_FILE_NAMES[view], deal),
                'header': fh, 'records': [fr] + fl, 'fields': campos})
    # 3. o prêmio (4.2.11), como no Bullet
    if _dtk.premium_applies(deal):
        ph, preg, pflow = _dtk.premium_values(deal, view, accounts, my_swap, my_prem, participant, today_ymd)
        out.append({'kind': 'premium', 'label': 'Premium (0897)', 'key': PREMIUM_FI_KEY, 'view': view,
                    'le_pair': pair,
                    'file_name': _file_name(PREMIUM_FI_KEY, view, PREMIUM_FILE_NAMES[view], deal),
                    'header': _line(PREMIUM_FI_KEY, 'header', ph, view, deal),
                    'records': [_line(PREMIUM_FI_KEY, 'registro', preg, view, deal),
                                _line(PREMIUM_FI_KEY, 'fluxo', pflow, view, deal)],
                    'fields': _sw.fields_of(PREMIUM_FI_KEY, {'header': ph, 'registro': preg, 'fluxo': pflow}, None)})
    return out


def preview(deal):
    """Todos os arquivos de todas as visões do deal (sem gravar nada)."""
    files = []
    for view in _dtk.views_of(deal):
        files.extend(deal_files(deal, view))
    return files


class EnvioRecusado(ValueError):
    """O Send recusou o LOTE: `itens` = [{deal_id, code, params, text}]."""

    def __init__(self, itens):
        self.itens = list(itens)
        ValueError.__init__(self, 'Nothing sent — ' + '; '.join(
            '%s: %s' % (x['deal_id'], x['text']) for x in self.itens))


def send(items, sid='', download=False):
    """Gera os arquivos dos deals selecionados (New/Approved) e vira Sent.
    `items` = [{deal_id, trade_date}]. Um deal com lacuna recusa o LOTE
    inteiro (nada sai pela metade). `download` devolve o conteúdo em vez de
    gravar. → {'files': [...], 'count': n}"""
    problemas, alvos, grupos = [], [], {}
    today = _today_ymd()
    for it in items or []:
        deal_id = str((it or {}).get('deal_id') or '').strip()
        td = str((it or {}).get('trade_date') or '').strip()
        if not deal_id:
            continue
        fp, lst, idx = queries.find(deal_id, td)
        if idx is None:
            problemas.append({'deal_id': deal_id, 'code': 'swc_not_found', 'params': {}, 'text': 'not found'})
            continue
        deal = lst[idx]
        status = deal.get('Status') or 'New'
        if status not in domain.STATUS_SENDABLE:
            problemas.append({'deal_id': deal_id, 'code': 'swc_status', 'params': {'status': status},
                              'text': 'status ' + status})
            continue
        try:
            arquivos = []
            for view in _dtk.views_of(deal):
                arquivos.extend(deal_files(deal, view, today))
        except Lacunas as exc:
            for x in exc.itens:
                problemas.append(dict(x, deal_id=deal_id))
            continue
        for f in arquivos:
            # O cabeçalho de cada arquivo é o mesmo para todos os deals do
            # grupo (mesmo layout, mesmo participante, mesma data): o grupo é
            # o NOME, e os registros de cada deal entram em sequência.
            g = grupos.setdefault(f['file_name'], {'header': f['header'], 'records': [], 'count': 0})
            g['records'].extend(f['records'])
            g['count'] += 1 if f['kind'] == 'swap' else 0
        alvos.append((deal_id, deal.get('TradeDate') or td))
    if problemas:
        raise EnvioRecusado(problemas)
    if not grupos:
        raise ValueError('No valid rows provided')
    gerados = []
    if download:
        for nome, g in grupos.items():
            gerados.append({'filename': nome, 'count': g['count'],
                            'content': '\n'.join([g['header']] + g['records'])})
        return {'files': gerados, 'count': len(alvos)}
    out_dir = _R().CONECTA_NEW_PATH
    os.makedirs(out_dir, exist_ok=True)
    with _R()._cache_lock:
        for nome, g in grupos.items():
            path = _R()._unique_filepath(out_dir, nome)
            # cp1252, NUNCA utf-8: o travessão (–) da denominação VCP é UM byte
            # em cp1252 e TRÊS em utf-8 — o Conecta lê byte a byte (§480).
            with open(path, 'w', encoding=FILE_ENCODING, errors='replace') as fh:
                fh.write('\n'.join([g['header']] + g['records']))
            gerados.append({'filename': os.path.basename(path), 'count': g['count']})
            _R().log.info('[SWAP CASHFLOW] Wrote %s (%d record(s))', path, len(g['records']))
        por_arquivo = {}
        for deal_id, td in alvos:
            fp, lst, idx = queries.find(deal_id, td)
            if idx is None:
                continue
            if fp in por_arquivo:
                lst = por_arquivo[fp]
                idx = next((i for i, e in enumerate(lst) if persistence.key_of(e) == deal_id), None)
                if idx is None:
                    continue
            lst[idx]['Status'] = 'Sent'
            lst[idx]['SentAt'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            lst[idx]['SentBy'] = sid
            lst[idx]['SentFiles'] = [x['filename'] for x in gerados]
            por_arquivo[fp] = lst
        for fp, lst in por_arquivo.items():
            persistence.write_day(fp, lst)
    return {'files': gerados, 'count': len(alvos)}


# ── Edição / esteira ─────────────────────────────────────────────────────────

EDITABLE = tuple(k for k in domain.SWC_FIELDS if k not in ('Maker', 'Checker', 'Flows')) + (
    'TradeDate', 'Client', 'SPN', 'LE', 'LOB', 'Deal', 'B3ID')


def _apply_fields(d, fields):
    """Grava no deal as chaves editáveis de `fields` (datas em ISO) e o
    cronograma (`CashFlows`, lista) quando ele vem."""
    for k, v in (fields or {}).items():
        if k == domain.SCHEDULE_FIELD:
            d[k] = domain.normalize_schedule(v if isinstance(v, list) else [])
            continue
        if k not in EDITABLE:
            continue
        v = '' if v is None else str(v).strip()
        if k in domain.SWC_DATE_FIELDS or k == 'TradeDate':
            v = _dtk.iso(_dtk.parse_date(v)) if v else ''
        d[k] = v


def _pair_from_le(d):
    if 'ATACAMA' in _dtk.norm(d.get('Client')) or _dtk.norm(d.get('LE')) == 'ATACAMA':
        d['LE'] = 'ATACAMA'
    else:
        d['LE'] = 'JPM'
    d['Pair'] = 'JPM x ATACAMA' if d['LE'] == 'ATACAMA' else 'JPM x CLI'


def edit(deal_id, trade_date, changes, sid=''):
    """Aplica `changes` (só chaves editáveis, mais o cronograma) → Pending,
    maker = sid; B3 ID NOVO é o mapeamento (Success, e o que vem depois dele
    dispara). O `VcpText` é recomposto quando algum insumo mudou e ele não foi
    editado à mão; SPN nova re-puxa a contraparte. → (deal, mapeou?) ou
    (None, False)."""
    changes = changes or {}
    with _R()._cache_lock:
        fp, lst, idx = queries.find(deal_id, trade_date)
        if idx is None:
            return None, False
        d = lst[idx]
        before_text = _dtk.vcp_text(d)
        spn_antes = str(d.get('SPN') or '').strip()
        b3_antes = str(d.get('B3ID') or '').strip()
        touched_text = 'VcpText' in changes and \
            str(changes.get('VcpText') or '').strip() != str(d.get('VcpText') or '').strip()
        _apply_fields(d, changes)
        if 'LE' in changes or 'Client' in changes:
            _pair_from_le(d)
        if 'QuoteDate' in changes or 'MaturityDate' in changes:
            d['QuoteDateCode'] = ''
        if 'SPN' in changes and str(changes.get('SPN') or '').strip() != spn_antes:
            d['ClientRefData'] = ''
            d['ClientAccount'] = ''
            d['ClientTaxId'] = ''
            d.pop('ClientAccountNote', None)
            if d.get('ClientDT'):
                d['Client'] = d['ClientDT']
            if 'LE' not in changes and 'ATACAMA' not in _dtk.norm(d.get('ClientDT')):
                d['LE'] = 'JPM'
                d['Pair'] = 'JPM x CLI'
        if not touched_text and (str(d.get('VcpText') or '').strip() == before_text.strip()
                                 or not str(d.get('VcpText') or '').strip()):
            d['VcpText'] = ''
        enrich(d)
        b3_novo = str(d.get('B3ID') or '').strip()
        mapped = bool(b3_novo) and b3_novo != b3_antes
        if mapped:
            # B3 ID novo é o MAPEAMENTO (§481): o registro existe na B3 — é o
            # `Success` das outras páginas de New Deals, não uma edição a aprovar.
            d['Status'] = 'Success'
            d['MappedBy'] = sid
            d['MappedAt'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        else:
            d['Status'] = 'Pending'
            d['Maker'] = sid
            d['Checker'] = ''
        persistence.write_day(fp, lst)
    if mapped:
        b3_mapped(d)
    return d, mapped


def add(fields, trade_date, sid=''):
    """Deal digitado à mão (Add Row) → New no arquivo-dia da Trade Date."""
    ref = _R()._api_ref_date(trade_date)
    d = domain.deal_from_raw({}, [], ref.strftime('%Y-%m-%d'))
    _apply_fields(d, dict((k, v) for k, v in (fields or {}).items() if k != 'TradeDate'))
    _pair_from_le(d)
    d['Type'] = str((fields or {}).get('Type') or '').strip() or 'Fluxo de Caixa'
    d['_id'] = domain.make_deal_id(d)
    d['Deal'] = str((fields or {}).get('Deal') or '').strip()
    d['B3ID'] = str((fields or {}).get('B3ID') or '').strip()
    d['VcpText'] = str((fields or {}).get('VcpText') or '').strip() or _dtk.vcp_text(d)
    d['QuoteDateCode'] = ''
    enrich(d)
    _stamp_numbers(d)
    d.update({'Status': 'Success' if d['B3ID'] else 'New', 'Maker': '', 'Checker': '', 'ImportedBy': sid})
    persistence.upsert(ref, [d])
    if d['B3ID']:
        b3_mapped(d)
    return d


def set_status(deal_id, trade_date, status, sid=''):
    """Confirm: New → Approved direto (quem confirma vira Maker); Amend →
    Pending (alguém tem de olhar o dado que o DT reimportado mudou); Pending →
    Approved exige outro usuário. → (deal, código do erro)."""
    with _R()._cache_lock:
        fp, lst, idx = queries.find(deal_id, trade_date)
        if idx is None:
            return None, 'swc_not_found'
        d = lst[idx]
        cur = d.get('Status') or 'New'
        if status == 'Approved' and cur == 'Amend':
            status = 'Pending'
        if status == 'Approved':
            if cur not in ('New', 'Pending'):
                return None, 'swc_not_approvable'
            if cur == 'Pending' and d.get('Maker') and d['Maker'] == sid:
                return None, 'swc_maker_checker'
            d['Checker'] = sid if cur == 'Pending' else ''
            if cur == 'New':
                d['Maker'] = sid
        if status == 'Pending':
            d['Maker'] = sid
            d['Checker'] = ''
        d['Status'] = status
        persistence.write_day(fp, lst)
        return d, None


def delete(items):
    """Apaga deals ({deal_id, trade_date}) reagrupando por arquivo. →
    (apagados, não achados)."""
    apagados, nao = 0, []
    por_arquivo = {}
    with _R()._cache_lock:
        for it in items or []:
            deal_id = str((it or {}).get('deal_id') or '').strip()
            if not deal_id:
                continue
            fp, lst, idx = queries.find(deal_id, str((it or {}).get('trade_date') or ''))
            if fp is None:
                nao.append(deal_id)
                continue
            if fp in por_arquivo:
                lst = por_arquivo[fp]
                idx = next((i for i, e in enumerate(lst) if persistence.key_of(e) == deal_id), None)
                if idx is None:
                    nao.append(deal_id)
                    continue
            lst.pop(idx)
            por_arquivo[fp] = lst
            apagados += 1
        for fp, lst in por_arquivo.items():
            persistence.write_day(fp, lst)
    return apagados, nao


# ── Depois do B3 ID (§481) ───────────────────────────────────────────────────

def b3_mapped(deal):
    """O deal ganhou B3 ID → Intrag Swap (B2B) ou Pending Confirmation +
    esteira (contra cliente), pela MESMA regra do Swap Bullet
    (`platform/swap_new_deals.b3_mapped`)."""
    _sw.b3_mapped(deal, tag='SWAP CASHFLOW')


confirmation_deal = _sw.confirmation_deal


def confirmation_deals(ref_dt):
    """Os deals CONTRA CLIENTE do dia `ref_dt`, no formato das confirmações —
    a segregação das confirmações de Swap (`platform/confirmations`) lê os do
    Bullet e os daqui. O B2B fica de fora: é linha da Intrag."""
    out = []
    for d in queries.entries(ref_dt.strftime('%Y-%m-%d')):
        if _dtk.is_b2b(d):
            continue
        out.append(confirmation_deal(d))
    return out
