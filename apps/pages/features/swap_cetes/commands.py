# -*- coding: utf-8 -*-
"""Escritas do Swap Cetes: importar o e-mail das Cetes (o bloco `cetip usd
irs`), montar os dois arquivos da B3 — o Registro de Contrato com Pagamento
Final (0301, versão 1 do layout) na visão do Banco e na do Lawton —, gravá-los
no Batch Conecta, mapear o retorno da B3 e, no Success, a linha da Intrag
Swap (o fluxo padrão do intragrupo)."""
import os
import random
from datetime import datetime, timedelta

from apps.pages import data_store as _store
from apps.pages.platform import authz as _authz
from apps.pages.platform import swap_deal_ticket as _dtk
from apps.pages.features.swap_cetes import domain, queries
from apps.pages.features.swap_cetes.infra import email_reader, persistence


def _R():
    from apps.pages import routes
    return routes


SWAP_FI_KEY = 'swap-pagamento-final'          # a versão 1 do layout: header 38, registro 1899
PAGE_URL = '/new_deals-swap-cetes'
# O Conecta lê o arquivo como ANSI (cp1252): cada caractere é UM byte (§480).
FILE_ENCODING = 'cp1252'


def _rand10():
    return str(random.randint(1000000000, 9999999999))


# ── Import ───────────────────────────────────────────────────────────────────

def parse_upload(filename, data, trade_iso):
    """O e-mail do dropzone → (deals, ignorados): um deal por bloco `cetip usd
    irs`; os outros blocos da tranche (o NDF offshore, o FX cash…) voltam como
    ignorados, pelo título."""
    assunto, linhas = email_reader.read(filename, data)
    if not domain.tranche_of(assunto):
        assunto = next((ln for ln in linhas if domain.tranche_of(ln)), assunto)
    deals, ignorados = [], []
    for b in domain.blocks(linhas):
        titulo = '#%s %s' % (b['num'], b['title'])
        if not domain.is_cetip_irs(b['title']):
            ignorados.append(titulo)
            continue
        deal = domain.deal_from_block(b, trade_iso, assunto)
        deal['_sheet'] = titulo
        deals.append(deal)
    return deals, ignorados


def import_upload(filename, data, ref_dt, sid='', dry_run=False):
    """O arquivo do dropzone → deals no arquivo-dia da Trade Date `ref_dt`.
    `dry_run` só PARSEIA (o passo 1 do Import das páginas de New Deals: a tela
    confere as duplicatas e grava pelo `persist_deals`)."""
    trade_iso = ref_dt.strftime('%Y-%m-%d')
    deals, ignorados = parse_upload(filename, data, trade_iso)
    imported = 0 if dry_run else persist_deals(deals, sid=sid)
    return {'success': True, 'imported': imported, 'deals': deals, 'ignored': ignorados,
            'missing': missing_by_id(deals), 'trade_date': trade_iso, 'dry_run': bool(dry_run)}


def lacunas(deal, accounts=None):
    return domain.missing_for_send(deal, queries.leg_rows(),
                                   accounts if accounts is not None else queries.own_accounts(),
                                   queries.codes_for(deal))


def missing_by_id(deals):
    accounts = queries.own_accounts()
    out = {}
    for d in deals or []:
        faltas = lacunas(d, accounts)
        if faltas:
            out[d['_id']] = faltas
    return out


def _prepare(d, accounts=None):
    """O que o deal precisa ter antes de gravar: o Meu Número (o MESMO nas duas
    visões) e a conta do Lawton no `ClientAccount` — é por ela que o plano B do
    casamento do retorno da B3 procura a operação."""
    if not str(d.get('MyNumber') or '').strip():
        d['MyNumber'] = _rand10()
    accounts = accounts if accounts is not None else queries.own_accounts()
    d['ClientAccount'] = domain.return_signature_account(accounts)
    d.setdefault('Client', 'Lawton')
    return d


def persist_deals(deals, sid=''):
    """Grava os deals nos arquivos-dia das suas Trade Dates. Deal marcado
    `_replace` (a tela escolheu SUBSTITUIR uma duplicata) sai da esteira como
    `Amend` quando a linha antiga já tinha andado — a não ser que tenha B3 ID
    (§554: o registro já existe). → quantidade gravada."""
    accounts = queries.own_accounts()
    por_dia = {}
    for d in deals or []:
        if not isinstance(d, dict):
            continue
        if not d.get('_id'):
            d['_id'] = domain.make_deal_id(d)
        _prepare(d, accounts)
        d['ImportedBy'] = sid
        replace = bool(d.pop('_replace', False))
        ref = domain.parse_date(d.get('TradeDate')) or datetime.now().date()
        ref_dt = datetime(ref.year, ref.month, ref.day)
        d['TradeDate'] = ref_dt.strftime('%Y-%m-%d')
        por_dia.setdefault(ref_dt, []).append((d, replace))
    n = 0
    for ref_dt, lst in por_dia.items():
        n += persistence.upsert(ref_dt, [d for d, _r in lst])
        amend = [d['_id'] for d, r in lst if r and (d.get('Status') or 'New') != 'New'
                 and not str(d.get('B3ID') or '').strip()]
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


# ── Os arquivos ──────────────────────────────────────────────────────────────

def _today_ymd():
    return datetime.now().strftime('%Y%m%d')


def _file_name(view):
    """O `file_name` cadastrado na variante do par (File Interpreter) vence;
    senão `SWAP_CETES_BANCO.txt` / `SWAP_CETES_LAWTON.txt`."""
    try:
        nome = _R()._fi_variant_file_name(SWAP_FI_KEY, PAGE_URL, domain.le_pair(view))
    except Exception:                                   # noqa: BLE001
        nome = ''
    return nome or domain.FILE_NAMES[view]


def _line(block, values, view, deal):
    return _R()._fi_build_line(SWAP_FI_KEY, block, values, page_url=PAGE_URL,
                               le_pair=domain.le_pair(view), deal=deal)


class Lacunas(ValueError):
    """O deal tem lacuna: `itens` são as lacunas estruturadas (§486)."""

    def __init__(self, itens):
        self.itens = list(itens or [])
        ValueError.__init__(self, 'missing: ' + '; '.join(domain.lacuna_texts(self.itens)))


def deal_files(deal, view, today_ymd=None):
    """O arquivo de UMA visão do deal: {kind, label, key, view, le_pair,
    file_name, header, records, fields}. Levanta `Lacunas`."""
    today_ymd = today_ymd or _today_ymd()
    accounts = queries.own_accounts()
    codes = queries.codes_for(deal)
    rows = queries.leg_rows()
    faltas = domain.missing_for_send(deal, rows, accounts, codes)
    if faltas:
        raise Lacunas(faltas)
    leg_rows, _e = domain.legs(deal, rows)
    parte_le = domain.VIEW_LE[view][0]
    hdr = domain.header_values(queries.participant(parte_le), today_ymd)
    vals = domain.record_values(deal, view, accounts, codes, leg_rows)
    header = _line('header', hdr, view, deal)
    parts = [_line(b['id'], vals, view, deal)
             for b in queries.template_blocks(SWAP_FI_KEY) if b.get('id') != 'header']
    if not parts:
        raise ValueError('file-interpreter template missing: ' + SWAP_FI_KEY)
    record = ''.join(parts)
    if len(record) != domain.RECORD_LENGTH or len(header) != domain.HEADER_LENGTH:
        raise ValueError('0301 has %d/%d characters, the layout wants %d/%d (check the file-interpreter '
                         'template %s)' % (len(header), len(record), domain.HEADER_LENGTH,
                                           domain.RECORD_LENGTH, SWAP_FI_KEY))
    return {'kind': 'swap', 'label': 'SWAP 0301 · ' + ('Banco' if view == 'bank' else 'Lawton'),
            'key': SWAP_FI_KEY, 'view': view, 'le_pair': domain.le_pair(view),
            'file_name': _file_name(view), 'header': header, 'records': [record],
            'fields': queries.fields_of(SWAP_FI_KEY, {'header': hdr}, vals)}


def preview(deal):
    """Os dois arquivos do deal (Banco e Lawton), sem gravar nada."""
    return [deal_files(deal, view) for view in domain.VIEWS]


class EnvioRecusado(ValueError):
    """O Send recusou o LOTE: `itens` = [{deal_id, code, params, text}]."""

    def __init__(self, itens):
        self.itens = list(itens)
        ValueError.__init__(self, 'Nothing sent — ' + '; '.join(
            '%s: %s' % (x['deal_id'], x['text']) for x in self.itens))


def send(items, sid='', download=False):
    """Gera os arquivos dos deals selecionados (New/Approved) e vira Sent.
    Um deal com lacuna recusa o LOTE inteiro (nada sai pela metade); os nomes
    da New (com a conta da visão na frente, §646) saem antes do primeiro
    arquivo. `download` devolve o conteúdo em vez de gravar."""
    problemas, alvos, grupos = [], [], {}
    today = _today_ymd()
    for it in items or []:
        deal_id = str((it or {}).get('deal_id') or '').strip()
        td = str((it or {}).get('trade_date') or '').strip()
        if not deal_id:
            continue
        _fp, lst, idx = queries.find(deal_id, td)
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
            arquivos = [deal_files(deal, view, today) for view in domain.VIEWS]
        except Lacunas as exc:
            for x in exc.itens:
                problemas.append(dict(x, deal_id=deal_id))
            continue
        for f in arquivos:
            g = grupos.setdefault(f['file_name'], {'header': f['header'], 'records': [], 'count': 0,
                                                   'le_pair': f['le_pair']})
            g['records'].extend(f['records'])
            g['count'] += 1
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
    nomes = {nome: _R()._conecta_file_name(g['le_pair'], nome) for nome, g in grupos.items()}
    out_dir = _R().CONECTA_NEW_PATH
    os.makedirs(out_dir, exist_ok=True)
    with _R()._cache_lock:
        for nome, g in grupos.items():
            path = _R()._unique_filepath(out_dir, nomes[nome])
            with open(path, 'w', encoding=FILE_ENCODING, errors='replace') as fh:
                fh.write('\n'.join([g['header']] + g['records']))
            gerados.append({'filename': os.path.basename(path), 'count': g['count']})
            _R().log.info('[SWAP CETES] Wrote %s (%d record(s))', path, len(g['records']))
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

# a LOB fica de fora: a Cetes é sempre CEM (`domain.LOB`, §655)
EDITABLE = tuple(k for k in domain.FIELDS if k not in ('Maker', 'Checker', 'Notional')) + (
    'TradeDate', 'Deal', 'B3ID')


def _apply_fields(d, fields):
    for k, v in (fields or {}).items():
        if k not in EDITABLE:
            continue
        v = '' if v is None else str(v).strip()
        if k in domain.DATE_FIELDS or k == 'TradeDate':
            v = domain.iso(domain.parse_date(v)) if v else ''
        d[k] = v
    if 'FixedPayer' in (fields or {}):
        d['FixedPayer'] = str(d.get('FixedPayer') or '').strip().upper()


def edit(deal_id, trade_date, changes, sid=''):
    """Aplica `changes` → Pending, maker = sid; B3 ID NOVO é o mapeamento
    (Success, e a Intrag nasce). Linha já com B3 ID fica Success (§554).
    → (deal, mapeou?) ou (None, False)."""
    changes = changes or {}
    with _R()._cache_lock:
        fp, lst, idx = queries.find(deal_id, trade_date)
        if idx is None:
            return None, False
        d = lst[idx]
        b3_antes = str(d.get('B3ID') or '').strip()
        _apply_fields(d, changes)
        domain.refresh(d)
        b3_novo = str(d.get('B3ID') or '').strip()
        mapped = bool(b3_novo) and b3_novo != b3_antes
        if mapped:
            d['Status'] = 'Success'
            d['MappedBy'] = sid
            d['MappedAt'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        elif b3_novo:
            d['Status'] = 'Success'
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
    d = domain.deal_from_block({'num': '', 'title': '', 'fields': {}}, ref.strftime('%Y-%m-%d'))
    _apply_fields(d, dict((k, v) for k, v in (fields or {}).items() if k != 'TradeDate'))
    d['FixedPayer'] = ''
    domain.refresh(d)
    d['_id'] = domain.make_deal_id(dict(d, Block=d.get('Block') or _rand10()))
    _prepare(d)
    d.update({'Status': 'Success' if str(d.get('B3ID') or '').strip() else 'New',
              'Maker': '', 'Checker': '', 'ImportedBy': sid})
    persistence.upsert(ref, [d])
    if d['Status'] == 'Success':
        b3_mapped(d)
    return d


def set_status(deal_id, trade_date, status, sid=''):
    """Confirm: New e Amend → Approved direto (quem confirma vira Maker);
    Pending → Approved exige outro usuário. → (deal, código do erro)."""
    with _R()._cache_lock:
        fp, lst, idx = queries.find(deal_id, trade_date)
        if idx is None:
            return None, 'swc_not_found'
        d = lst[idx]
        cur = d.get('Status') or 'New'
        if status == 'Approved':
            if cur not in ('New', 'Amend', 'Pending'):
                return None, 'swc_not_approvable'
            if cur == 'Pending' and _authz.is_own_change(d.get('Maker'), sid):
                return None, 'swc_maker_checker'
            d['Checker'] = sid if cur == 'Pending' else ''
            if cur in ('New', 'Amend'):
                d['Maker'] = sid
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


# ── Mapping B3 ID: o arquivo de retorno ──────────────────────────────────────

MAPPING_ERRORABLE = ('Sent', 'Error')


def _return_files():
    """[(caminho, [linhas parseadas])] do `RETURN_PATH`: só os arquivos com ao
    menos um eco de SWAP 0301. Pasta ausente levanta (a tela diz qual)."""
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
                linhas = [_dtk.parse_return_line(ln) for ln in fh]
        except OSError as exc:
            _R().log.warning('[SWAP CETES] return file unreadable %s: %s', fpath, exc)
            continue
        linhas = [ln for ln in linhas if ln]
        if linhas:
            out.append((fpath, linhas))
    return out


def map_b3(trade_date, sid=''):
    """Varre o retorno da B3 e grava o B3 ID nos deals do arquivo-dia de
    `trade_date`, pelo Meu Número (o mesmo nas duas visões): `EXECUCAO OK` →
    B3 ID + `Success`; eco com outro status → `Error` com o texto da B3;
    enviado e ausente do retorno → `Error`. Quem ganhou `Success` leva a linha
    à Intrag Swap. O arquivo de retorno só é apagado quando TODAS as linhas de
    swap dele casaram aqui (o Bullet e o Cashflow também registram 0301).
    → [{id, b3_id, status, saved, reason, entry}] só com quem MUDOU."""
    ref = domain.parse_date(trade_date)
    if not ref:
        raise ValueError('invalid trade date: {!r}'.format(trade_date))
    arquivos = _return_files()
    todas = [ln for _fp, lns in arquivos for ln in lns]
    results, disparar, usadas = [], [], set()
    with _R()._cache_lock:
        fp = persistence.day_path(datetime(ref.year, ref.month, ref.day))
        lst = persistence.read_day(fp)
        for d in lst:
            if not isinstance(d, dict) or str(d.get('Status') or '').strip() == 'Canceled':
                continue
            antes = (str(d.get('B3ID') or '').strip(), d.get('Status') or 'New')
            hit = _dtk.match_return(d, todas, lst)
            if hit is not None:
                num = str(d.get('MyNumber') or '').strip()
                usadas.update(id(ln) for ln in todas if ln is hit or (num and ln['my_number'] == num))
            if hit is not None and hit['ok'] and hit['b3_id']:
                d['B3ID'] = hit['b3_id']
                d['Status'] = 'Success'
                d.pop('MappingError', None)
            elif hit is not None and not hit['ok'] and antes[1] != 'Success':
                d['Status'] = 'Error'
                d['MappingError'] = hit['status']
            elif antes[0] and antes[1] != 'Success':
                d['Status'] = 'Success'
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
                persistence.write_day(fp, lst)
            except Exception as exc:              # noqa: BLE001 — a tela diz o motivo
                saved, motivo = False, '{}: {}'.format(type(exc).__name__, exc)
                _R().log.error('[MAPPING-B3] swap cetes day file NOT saved %s: %s', fp, motivo)
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
                    _R().log.warning('[SWAP CETES] return file not removed %s: %s', fpath, exc)
    return results


# ── Depois do B3 ID: a Intrag Swap ───────────────────────────────────────────

def _quote_date(deal):
    """A Data de Cotação da linha da Intrag: a data de início recuada o D-n do
    `fx fixing` (t-2 → dois dias úteis ANBIMA antes do Effective)."""
    start = domain.parse_date(deal.get('StartDate'))
    code = str(deal.get('QuoteDateCode') or '')
    if not start or not code.isdigit():
        return ''
    hols, cur, left = _R()._anbima_holidays(), datetime(start.year, start.month, start.day), int(code)
    while left > 0:
        cur -= timedelta(days=1)
        if cur.weekday() < 5 and cur.strftime('%Y-%m-%d') not in hols:
            left -= 1
    return cur.strftime('%Y-%m-%d')


def b3_mapped(deal):
    """O deal ganhou B3 ID → a linha da Intrag Swap na visão do Lawton (a
    carteira dele, INTRAGJP552), no dia da Data de Início. A falha vai para o
    log com o traceback e não derruba a gravação da página."""
    if not str(deal.get('B3ID') or '').strip():
        return
    try:
        leg_rows, erros = domain.legs(deal, queries.leg_rows())
        if erros:
            raise ValueError('; '.join(domain.lacuna_texts(erros)))
        entry = domain.intrag_entry(deal, leg_rows, _quote_date(deal))
        start = domain.parse_date(deal.get('StartDate')) or domain.parse_date(deal.get('TradeDate'))
        start_dt = datetime(start.year, start.month, start.day) if start else None
        _R()._intrag_engine()._save_intrag_swap_entry(entry, start_dt)
    except Exception:                                       # noqa: BLE001
        import traceback
        _R().log.warning('[SWAP CETES] post-mapping flow failed for %s:\n%s', deal.get('B3ID'),
                         traceback.format_exc())
