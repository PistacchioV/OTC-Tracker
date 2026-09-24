# -*- coding: utf-8 -*-
"""Escritas do Swap Bullet: importar o Deal Ticket, completar o deal com os
cadastros, montar as linhas dos dois arquivos da B3 e gravá-los."""
import os
import random
import re
from datetime import datetime

from apps.pages import data_store as _store
from apps.pages.platform import swap_new_deals as _sw
from apps.pages.features.swap_bullet import domain, queries
from apps.pages.features.swap_bullet.infra import dt_reader, persistence
from apps.pages.platform import authz as _authz


def _R():
    from apps.pages import routes
    return routes


SWAP_FI_KEY = 'swap-pagamento-final-v3'
PREMIUM_FI_KEY = 'swap-registro-premio'
PAGE_URL = '/new_deals-swap-bullet'

# O nome padrão de cada arquivo por visão; o `file_name` da VARIANTE do
# template (por par de pernas) vence quando cadastrado.
# O nome leva a LOB do deal (`{lob}` = 'EDG_'; vazio quando o deal não tem):
# SWAP_EDG_CLIENTE.txt e PREMIO_SWAP_EDG_CLIENTE.txt. Deals de LOBs diferentes
# no mesmo lote caem em arquivos diferentes — o `send` agrupa pelo nome.
SWAP_FILE_NAMES = {'client': 'SWAP_{lob}CLIENTE.txt', 'bank': 'SWAP_{lob}BANCO.txt',
                   'atacama': 'SWAP_{lob}ATACAMA.txt'}
PREMIUM_FILE_NAMES = {'client': 'PREMIO_SWAP_{lob}CLIENTE.txt', 'bank': 'PREMIO_SWAP_{lob}BANCO.txt',
                      'atacama': 'PREMIO_SWAP_{lob}ATACAMA.txt'}


def _rand10():
    return str(random.randint(1000000000, 9999999999))


# ── Import ───────────────────────────────────────────────────────────────────

def import_upload(filename, data, ref_dt, sid='', dry_run=False):
    """O arquivo do dropzone → deals no arquivo-dia da Trade Date `ref_dt`.
    Devolve o resumo para a tela: quantos, quais, abas/páginas ignoradas e as
    lacunas de cada deal (o que o Send recusaria).

    `dry_run` só PARSEIA e devolve os deals — é o primeiro passo do Import
    das páginas de New Deals: a tela confere as duplicatas (Deal já na
    grade) e pergunta se substitui, e só então grava pelo `persist_deals`."""
    kind, itens = dt_reader.read_upload(filename, data)
    trade_iso = ref_dt.strftime('%Y-%m-%d')
    deals, ignorados = [], []
    for title, payload in itens:
        if kind == 'grid':
            if not domain.is_dt_grid(payload):
                ignorados.append(title)
                continue
            raw = domain.parse_dt_grid(payload)
        else:
            if 'VALORBASE' not in domain.norm(payload) or 'VENCIMENTO' not in domain.norm(payload):
                ignorados.append(title)
                continue
            raw = domain.parse_dt_text(payload)
        deal = domain.deal_from_raw(raw, trade_iso)
        deal['_sheet'] = title
        enrich(deal)
        deals.append(deal)
    imported = 0 if dry_run else persist_deals(deals, sid=sid)
    lacunas = {}
    accounts = queries.own_accounts()
    for d in deals:
        faltas = domain.missing_for_send(d, queries.codes_for(d), accounts)
        if faltas:
            lacunas[d['_id']] = faltas
    return {'success': True, 'imported': imported, 'deals': deals, 'ignored': ignorados,
            'missing': lacunas, 'trade_date': trade_iso, 'kind': kind, 'dry_run': bool(dry_run)}


def persist_deals(deals, sid=''):
    """Grava os deals (já montados) nos arquivos-dia das suas Trade Dates,
    dando os quatro Meu Número a quem ainda não tem. Deal marcado
    `_replace` (a tela escolheu SUBSTITUIR uma duplicata) sai da esteira
    como `Amend` quando a linha antiga já tinha andado — reimportar um DT
    corrigido não pode manter um Approved/Sent que valia para o dado
    antigo; New continua New. → quantidade gravada."""
    por_dia = {}
    for d in deals or []:
        if not isinstance(d, dict):
            continue
        if not d.get('_id'):
            d['_id'] = domain.make_deal_id(d)
        d.setdefault('MyNumber', _rand10())
        d.setdefault('MyNumberMirror', _rand10())
        d.setdefault('PremiumMyNumber', _rand10())
        d.setdefault('PremiumMyNumberMirror', _rand10())
        d['ImportedBy'] = sid
        replace = bool(d.pop('_replace', False))
        ref = domain.parse_date(d.get('TradeDate')) or datetime.now().date()
        ref_dt = datetime(ref.year, ref.month, ref.day)
        d['TradeDate'] = ref_dt.strftime('%Y-%m-%d')
        por_dia.setdefault(ref_dt, []).append((d, replace))
    n = 0
    for ref_dt, lst in por_dia.items():
        novas = [d for d, _r in lst]
        n += persistence.upsert(ref_dt, novas)
        # Linha com B3 ID fica `Success` (§554): o registro já existe na B3, e
        # rebaixá-la a `Amend` a levaria a `Approved` com o B3 ID na tela.
        amend = [d['_id'] for d, r in lst if r and (d.get('Status') or 'New') != 'New'
                 and not str(d.get('B3ID') or '').strip()]
        if amend:
            with _R()._cache_lock:
                fp = persistence.day_path(ref_dt)
                entries = _store.read(fp) if _store.exists(fp) else []
                mudou = False
                for e in entries:
                    if persistence.key_of(e) in amend and (e.get('Status') or 'New') != 'New':
                        e['Status'] = 'Amend'; e['Checker'] = ''; mudou = True
                if mudou:
                    _R()._atomic_write_json(fp, entries)
                    _R()._daycache_forget(fp)
    return n


# O `enrich` (conta B3, CNPJ e D-n pelos cadastros) mora na horizontal
# `platform/swap_new_deals.py` desde 21/09/2026 — o Swap Cashflow completa o
# deal do mesmo jeito.
enrich = _sw.enrich


# ── Os arquivos ──────────────────────────────────────────────────────────────

def _today_ymd():
    return datetime.now().strftime('%Y%m%d')


_participant = _sw.participant


def _file_name(key, view, default, deal=None):
    """O `file_name` cadastrado na variante do par vence; senão o padrão da
    visão com a LOB do deal no lugar de `{lob}`."""
    try:
        nome = _R()._fi_variant_file_name(key, PAGE_URL, domain.le_pair(view))
    except Exception:                                   # noqa: BLE001
        nome = ''
    if nome:
        return nome
    lob = re.sub(r'[^A-Z0-9]', '', str((deal or {}).get('LOB') or '').upper())
    return default.format(lob=lob + '_' if lob else '')


# O Conecta lê o arquivo como ANSI (cp1252): cada caractere é UM byte — é o
# que o Excel da mesa grava e o que mantém o registro em 1927 bytes.
FILE_ENCODING = 'cp1252'


def _build_blocks(key, values, view, deal, skip=('header',)):
    """Concatena os blocos do template (menos o header) numa linha só — o
    registro 0301 é UMA linha apresentada em 18 grupos; o 0897 tem o
    registro e o fluxo como linhas separadas, então quem chama escolhe."""
    parts = []
    for b in queries.template_blocks(key):
        if b.get('id') in skip:
            continue
        parts.append(_R()._fi_build_line(key, b['id'], values, page_url=PAGE_URL,
                                         le_pair=domain.le_pair(view), deal=deal))
    if not parts:
        raise ValueError('file-interpreter template missing: ' + key)
    return ''.join(parts)


def deal_files(deal, view, today_ymd=None):
    """Os arquivos de UMA visão do deal: [{kind, key, file_name, header,
    records, fields}] — o 0301 sempre; o 0897 quando há agenda de prêmio.
    `fields` é a lista [{seq, block, field, value}] para o preview. Levanta
    ValueError com as lacunas."""
    today_ymd = today_ymd or _today_ymd()
    accounts = queries.own_accounts()
    codes = queries.codes_for(deal)
    faltas = domain.missing_for_send(deal, codes, accounts)
    if faltas:
        raise ValueError('missing: ' + '; '.join(faltas))
    parte_le = 'ATACAMA' if view == 'atacama' else 'JPM'
    participant = _participant(parte_le)
    my_swap = deal.get('MyNumberMirror' if view == 'atacama' else 'MyNumber') or _rand10()
    my_prem = deal.get('PremiumMyNumberMirror' if view == 'atacama' else 'PremiumMyNumber') or _rand10()
    out = []
    vals = domain.swap_record_values(deal, view, accounts, codes, my_swap)
    hdr = domain.swap_header_values(participant, today_ymd)
    header = _R()._fi_build_line(SWAP_FI_KEY, 'header', hdr, page_url=PAGE_URL,
                                 le_pair=domain.le_pair(view), deal=deal)
    record = _build_blocks(SWAP_FI_KEY, vals, view, deal)
    if len(record) != domain.SWAP_RECORD_LENGTH:
        raise ValueError('0301 record has %d characters, the layout wants %d (check the '
                         'file-interpreter template %s)' % (len(record), domain.SWAP_RECORD_LENGTH, SWAP_FI_KEY))
    out.append({'kind': 'swap', 'key': SWAP_FI_KEY, 'view': view, 'le_pair': domain.le_pair(view),
                'file_name': _file_name(SWAP_FI_KEY, view, SWAP_FILE_NAMES[view], deal),
                'header': header, 'records': [record],
                'fields': _fields_of(SWAP_FI_KEY, {'header': hdr}, vals)})
    if domain.premium_applies(deal):
        h, reg, flow = domain.premium_values(deal, view, accounts, my_swap, my_prem, participant, today_ymd)
        header_p = _R()._fi_build_line(PREMIUM_FI_KEY, 'header', h, page_url=PAGE_URL,
                                       le_pair=domain.le_pair(view), deal=deal)
        reg_line = _R()._fi_build_line(PREMIUM_FI_KEY, 'registro', reg, page_url=PAGE_URL,
                                       le_pair=domain.le_pair(view), deal=deal)
        flow_line = _R()._fi_build_line(PREMIUM_FI_KEY, 'fluxo', flow, page_url=PAGE_URL,
                                        le_pair=domain.le_pair(view), deal=deal)
        out.append({'kind': 'premium', 'key': PREMIUM_FI_KEY, 'view': view, 'le_pair': domain.le_pair(view),
                    'file_name': _file_name(PREMIUM_FI_KEY, view, PREMIUM_FILE_NAMES[view], deal),
                    'header': header_p, 'records': [reg_line, flow_line],
                    'fields': _fields_of(PREMIUM_FI_KEY, {'header': h, 'registro': reg, 'fluxo': flow}, None)})
    return out


_fields_of = _sw.fields_of


def preview(deal):
    """Todos os arquivos de todas as visões do deal (sem gravar nada)."""
    files = []
    for view in domain.views_of(deal):
        files.extend(deal_files(deal, view))
    return files


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
            problemas.append(deal_id + ': not found')
            continue
        deal = lst[idx]
        if (deal.get('Status') or 'New') not in domain.STATUS_SENDABLE:
            problemas.append(deal_id + ': status ' + str(deal.get('Status') or 'New'))
            continue
        try:
            for view in domain.views_of(deal):
                for f in deal_files(deal, view, today):
                    g = grupos.setdefault(f['file_name'], {'header': f['header'], 'records': [], 'count': 0})
                    g['records'].extend(f['records'])
                    g['count'] += 1 if f['kind'] == 'swap' else 0
        except ValueError as exc:
            problemas.append(deal_id + ': ' + str(exc))
            continue
        alvos.append((deal_id, deal.get('TradeDate') or td))
    if problemas:
        raise ValueError('Nothing sent — ' + '; '.join(problemas))
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
            # cp1252 (o ANSI do Windows), NUNCA utf-8: o travessão (–) da
            # denominação VCP é UM byte em cp1252 e TRÊS em utf-8 — o Conecta
            # lê byte a byte, a linha passava de 1927 e a B3 recusava o
            # registro ('Campo 126 conteúdo inválido') mostrando 'â€“'.
            with open(path, 'w', encoding=FILE_ENCODING, errors='replace') as fh:
                fh.write('\n'.join([g['header']] + g['records']))
            gerados.append({'filename': os.path.basename(path), 'count': g['count']})
            _R().log.info('[SWAP BULLET] Wrote %s (%d record(s))', path, len(g['records']))
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
            _R()._atomic_write_json(fp, lst)
            _R()._daycache_forget(fp)
    return {'files': gerados, 'count': len(alvos)}


# ── Edição / esteira ─────────────────────────────────────────────────────────

EDITABLE = tuple(k for k in domain.SWB_FIELDS if k not in ('Maker', 'Checker')) + (
    'TradeDate', 'Client', 'SPN', 'LE', 'LOB', 'Deal', 'B3ID')


def edit(deal_id, trade_date, changes, sid=''):
    """Aplica `changes` (só chaves editáveis) → Pending, maker = sid. Datas
    entram em ISO (a tela manda dd/mm/aaaa ou ISO). O `VcpText` é
    recomposto quando algum insumo dele mudou e ele não foi editado à mão.
    → o deal."""
    with _R()._cache_lock:
        fp, lst, idx = queries.find(deal_id, trade_date)
        if idx is None:
            return None
        d = lst[idx]
        before_text = domain.vcp_text(d)
        spn_antes = str(d.get('SPN') or '').strip()
        b3_antes = str(d.get('B3ID') or '').strip()
        touched_text = 'VcpText' in changes and str(changes.get('VcpText') or '').strip() != str(d.get('VcpText') or '').strip()
        for k, v in (changes or {}).items():
            if k not in EDITABLE:
                continue
            v = '' if v is None else str(v).strip()
            if k in domain.SWB_DATE_FIELDS or k == 'TradeDate':
                v = domain.iso(domain.parse_date(v)) if v else ''
            d[k] = v
        if 'LE' in changes or 'Client' in changes:
            if 'ATACAMA' in domain.norm(d.get('Client')):
                d['LE'] = 'ATACAMA'
            d['LE'] = 'ATACAMA' if domain.norm(d.get('LE')) == 'ATACAMA' else 'JPM'
            d['Pair'] = 'JPM x ATACAMA' if d['LE'] == 'ATACAMA' else 'JPM x CLI'
        if 'QuoteDate' in changes or 'MaturityDate' in changes:
            d['QuoteDateCode'] = ''
        if 'SPN' in changes and str(changes.get('SPN') or '').strip() != spn_antes:
            # SPN nova = contraparte nova: o que veio do Reference Data pela
            # SPN antiga (nome, conta B3, CNPJ) é descartado e o `enrich`
            # abaixo puxa de novo pela nova.
            d['ClientRefData'] = ''
            d['ClientAccount'] = ''
            d['ClientTaxId'] = ''
            d.pop('ClientAccountNote', None)
            if d.get('ClientDT'):
                d['Client'] = d['ClientDT']
            if 'LE' not in changes and 'ATACAMA' not in domain.norm(d.get('ClientDT')):
                d['LE'] = 'JPM'
                d['Pair'] = 'JPM x CLI'
        if not touched_text and (str(d.get('VcpText') or '').strip() == before_text.strip()
                                 or not str(d.get('VcpText') or '').strip()):
            d['VcpText'] = ''
        if 'ClientAccount' in changes or 'SPN' in changes:
            pass
        enrich(d)
        b3_novo = str(d.get('B3ID') or '').strip()
        mapped = bool(b3_novo) and b3_novo != b3_antes
        if mapped:
            # B3 ID novo é o MAPEAMENTO da operação: o registro existe na B3, e
            # isso é o `Success` das outras páginas de New Deals — não uma
            # edição a aprovar. Maker/Checker ficam como estavam; quem mapeou
            # fica anotado.
            d['Status'] = 'Success'
            d['MappedBy'] = sid
            d['MappedAt'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        elif b3_novo:
            # A linha JÁ mapeada continua `Success` (§554): o contrato existe
            # na B3, e editar outro campo não reabre a esteira. Era por aqui que
            # o Swap Bullet ficava com B3 ID e `Approved` — o Save voltava a
            # linha para `Pending` e o Confirm seguinte a levava a `Approved`.
            d['Status'] = 'Success'
        else:
            d['Status'] = 'Pending'
            d['Maker'] = sid
            d['Checker'] = ''
        _R()._atomic_write_json(fp, lst)
        _R()._daycache_forget(fp)
    if mapped:
        b3_mapped(d)
    return d


def add(fields, trade_date, sid=''):
    """Deal digitado à mão (Add Row) → New no arquivo-dia da Trade Date."""
    ref = _R()._api_ref_date(trade_date)
    raw = {}
    d = domain.deal_from_raw(raw, ref.strftime('%Y-%m-%d'))
    for k, v in (fields or {}).items():
        if k in EDITABLE and k != 'TradeDate':
            v = '' if v is None else str(v).strip()
            if k in domain.SWB_DATE_FIELDS:
                v = domain.iso(domain.parse_date(v)) if v else ''
            d[k] = v
    if 'ATACAMA' in domain.norm(d.get('Client')) or domain.norm(d.get('LE')) == 'ATACAMA':
        d['LE'] = 'ATACAMA'
    else:
        d['LE'] = 'JPM'
    d['Pair'] = 'JPM x ATACAMA' if d['LE'] == 'ATACAMA' else 'JPM x CLI'
    d['_id'] = domain.make_deal_id(d)
    d['Deal'] = str(fields.get('Deal') or '').strip()
    d['B3ID'] = str(fields.get('B3ID') or '').strip()
    d['VcpText'] = str(fields.get('VcpText') or '').strip() or domain.vcp_text(d)
    d['QuoteDateCode'] = ''
    enrich(d)
    d.update({'MyNumber': _rand10(), 'MyNumberMirror': _rand10(),
              'PremiumMyNumber': _rand10(), 'PremiumMyNumberMirror': _rand10(),
              'Status': 'Success' if d['B3ID'] else 'New', 'Maker': '', 'Checker': '', 'ImportedBy': sid})
    persistence.upsert(ref, [d])
    if d['B3ID']:
        b3_mapped(d)
    return d


def set_status(deal_id, trade_date, status, sid='', require_other_than_maker=False):
    """Muda a esteira (Confirm: New e Amend → Approved direto; Pending →
    Approved com maker ≠ checker). → (deal, erro)."""
    with _R()._cache_lock:
        fp, lst, idx = queries.find(deal_id, trade_date)
        if idx is None:
            return None, 'Entry not found'
        d = lst[idx]
        cur = d.get('Status') or 'New'
        # New e Amend → Approved direto (mesa, 23/09/2026): o Confirm não
        # edita nada, e quem põe a linha em Pending é o Save do Edit
        # (`update_entry`). O Amend parava em Pending e a mesa conferia duas
        # vezes a mesma linha sem ter mexido nela.
        if status == 'Approved':
            if cur not in ('New', 'Amend', 'Pending'):
                return None, 'Only New, Amend or Pending entries can be approved.'
            if cur == 'Pending' and _authz.is_own_change(d.get('Maker'), sid):
                return None, 'Maker cannot approve their own change — a different user must check it.'
            d['Checker'] = sid if cur == 'Pending' else ''
            if cur in ('New', 'Amend'):
                d['Maker'] = sid
        if status == 'Pending':
            d['Maker'] = sid
            d['Checker'] = ''
        d['Status'] = status
        _R()._atomic_write_json(fp, lst)
        _R()._daycache_forget(fp)
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
            _R()._atomic_write_json(fp, lst)
            _R()._daycache_forget(fp)
    return apagados, nao


# ── Mapping B3 ID: o arquivo de retorno (§554) ───────────────────────────────

# Quem o Mapping pode levar a `Error` quando o retorno não a traz: só quem foi
# ENVIADO e esperava resposta. New/Approved não foram à B3.
MAPPING_ERRORABLE = ('Sent', 'Error')


def _return_files():
    """[(caminho, [linhas parseadas])] do `RETURN_PATH`: só os arquivos com
    ao menos um eco de SWAP 0301. Pasta ausente levanta (a tela diz qual)."""
    root = _R().RETURN_PATH
    if not _store.isdir(root):
        raise FileNotFoundError('Return folder not found: {}'.format(root))
    out = []
    for fname in sorted(_store.listdir(root)):
        fpath = os.path.join(root, fname)
        if not _store.isfile(fpath):
            continue
        try:
            with open(fpath, 'r', encoding='cp1252', errors='replace') as fh:
                linhas = [domain.parse_return_line(ln) for ln in fh]
        except OSError as exc:
            _R().log.warning('[SWAP BULLET] return file unreadable %s: %s', fpath, exc)
            continue
        linhas = [ln for ln in linhas if ln]
        if linhas:
            out.append((fpath, linhas))
    return out


def map_b3(trade_date, sid=''):
    """Varre o retorno da B3 e grava o B3 ID nos deals do arquivo-dia de
    `trade_date`: `EXECUCAO OK` → B3 ID + `Success`; eco com outro status →
    `Error` com o texto da B3 (`MappingError`); enviado e ausente do retorno →
    `Error`. A linha que já tem B3 ID e não está `Success` é CURADA para
    `Success` (§554). Depois da gravação, quem ganhou `Success` dispara o
    `b3_mapped` (Intrag / Pending Confirmation — idempotentes).

    O arquivo de retorno só é apagado quando TODAS as linhas de swap dele
    casaram com um deal daqui: o Swap Cashflow também registra 0301, e apagar
    o arquivo inteiro sumiria com o retorno dele.
    → [{id, b3_id, status, saved, reason}] só com quem MUDOU."""
    ref = domain.parse_date(trade_date)
    if not ref:
        raise ValueError('invalid trade date: {!r}'.format(trade_date))
    arquivos = _return_files()
    todas = [ln for _fp, lns in arquivos for ln in lns]
    results, disparar, usadas = [], [], set()
    with _R()._cache_lock:
        fp = persistence.day_path(datetime(ref.year, ref.month, ref.day))
        lst = _store.read(fp) if _store.exists(fp) else []
        lst = [persistence.migrate(e) for e in lst if isinstance(e, dict)]
        for d in lst:
            if str(d.get('Status') or '').strip() == 'Canceled':
                continue
            antes = (str(d.get('B3ID') or '').strip(), d.get('Status') or 'New')
            hit = domain.match_return(d, todas, lst)
            if hit is not None:
                # No B2B o MESMO contrato volta duas vezes (lançado pelo Banco e
                # pelo Atacama): as duas linhas são deste deal.
                nums = domain.return_my_numbers(d)
                usadas.update(id(ln) for ln in todas if ln is hit or ln['my_number'] in nums)
            if hit is not None and hit['ok'] and hit['b3_id']:
                d['B3ID'] = hit['b3_id']
                d['Status'] = 'Success'
                d.pop('MappingError', None)
            elif hit is not None and not hit['ok'] and antes[1] != 'Success':
                d['Status'] = 'Error'
                d['MappingError'] = hit['status']
            elif antes[0] and antes[1] != 'Success':
                d['Status'] = 'Success'          # já mapeada, esteira atrasada
            elif hit is None and antes[1] in MAPPING_ERRORABLE and not antes[0]:
                d['Status'] = 'Error'
                d['MappingError'] = 'not found in the B3 return files'
            depois = (str(d.get('B3ID') or '').strip(), d.get('Status') or 'New')
            if depois == antes:
                continue
            if depois[1] == 'Success':
                d['MappedBy'] = sid
                d['MappedAt'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                disparar.append(d)
            results.append({'id': persistence.key_of(d), 'b3_id': depois[0], 'status': depois[1],
                            'reason': d.get('MappingError', ''), 'entry': d})
        saved, motivo = True, ''
        if results:
            try:
                _R()._atomic_write_json(fp, lst)
                _R()._daycache_forget(fp)
            except Exception as exc:              # noqa: BLE001 — a tela diz o motivo
                saved, motivo = False, '{}: {}'.format(type(exc).__name__, exc)
                _R().log.error('[MAPPING-B3] swap bullet day file NOT saved %s: %s', fp, motivo)
    for r in results:
        r['saved'] = saved
        if not saved:
            r['reason'] = motivo
            r['b3_id'] = ''
    if saved:
        for d in disparar:
            b3_mapped(d)
        for fpath, lns in arquivos:
            if all(id(ln) in usadas for ln in lns):
                try:
                    _store.remove(fpath)
                except OSError as exc:
                    _R().log.warning('[SWAP BULLET] return file not removed %s: %s', fpath, exc)
    return results


# ── Depois do B3 ID (§481) ───────────────────────────────────────────────────

def b3_mapped(deal):
    """O deal ganhou B3 ID → Intrag Swap (B2B) ou Pending Confirmation +
    esteira (contra cliente). A regra é a mesma do Swap Cashflow e mora na
    horizontal (`platform/swap_new_deals.b3_mapped`)."""
    _sw.b3_mapped(deal, tag='SWAP BULLET')


confirmation_deal = _sw.confirmation_deal


def confirmation_deals(ref_dt):
    """Os deals CONTRA CLIENTE do dia `ref_dt`, no formato das confirmações —
    é o que a segregação das confirmações de Swap lê (`platform/confirmations`).
    O B2B fica de fora: a confirmação do intragrupo é a linha da Intrag."""
    out = []
    for d in queries.entries(ref_dt.strftime('%Y-%m-%d')):
        if domain.is_b2b(d):
            continue
        out.append(confirmation_deal(d))
    return out
