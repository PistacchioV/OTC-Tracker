# -*- coding: utf-8 -*-
"""New Deals Monitor — o snapshot dos cards e o e-mail de pendências (19h/19h30).

Movido VERBATIM do routes.py: os nomes internos (`_ndm_*`, `_NDM_*`) foram
preservados — inclusive para os testes que os trocam — e o que é de plataforma
é alcançado por busca atrasada (`_R().<nome>`). A separação interna em
domain/queries/commands é trabalho futuro; a fronteira com o routes já vale.
"""
import json
import os
import re
import threading
import time
import traceback
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import render_template


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


_NDM_CARDS = [
    {'key': 'ndf-commodities',    'label': 'NDF Commodities',     'url': '/new_deals-ndf-commodities',    'dirs': ('NDF/Commodities',),                          'les': ('JPM', 'LAW')},
    {'key': 'ndf-fwdstart',       'label': 'NDF FWD Start',       'url': '/new_deals-ndf-fwdstart',       'dirs': ('NDF/FWD Start', 'NDF/FwdStart'),             'les': ('JPM', 'MGT', 'LAW')},
    {'key': 'ndf-otherpublisher', 'label': 'NDF Other Publisher', 'url': '/new_deals-ndf-otherpublisher', 'dirs': ('NDF/OtherPublisher', 'NDF/Other Publisher'), 'les': ('JPM', 'MGT', 'LAW')},
    {'key': 'ndf-vanilla',        'label': 'NDF Vanilla',         'url': '/new_deals-ndf-vanilla',        'dirs': ('NDF/Vanilla',),                              'les': ('JPM', 'MGT', 'LAW')},
    {'key': 'opt-commodities',    'label': 'Commodities Options', 'url': '/new_deals-opt-commodities',    'dirs': ('Option/Commodities',),                       'les': ('JPM', 'LAW')},
    {'key': 'opt-fxo',            'label': 'FX Options',          'url': '/new_deals-opt-fxo',            'dirs': ('Option/FXO',),                               'les': ('JPM', 'LAW')},
    {'key': 'opt-equity',         'label': 'Equity Options',      'url': None, 'soon': True,              'dirs': ('Option/Equity', 'Option/Equities'),          'les': ('JPM', 'ATA')},
    {'key': 'swap-equities',      'label': 'Swap Equities',       'url': None, 'soon': True,              'dirs': ('Swap/Equities',),                            'les': ('JPM', 'ATA')},
    {'key': 'swap-cem',           'label': 'Swap CEM',            'url': None, 'soon': True,              'dirs': ('Swap/CEM',),                                 'les': ('JPM', 'LAW')},
    {'key': 'intrag-ndf',         'label': 'Intrag NDF',          'url': '/intrag-ndf',                   'dirs': ('Intrag/NDF',),                               'les': ('LAW', 'ATA')},
    {'key': 'intrag-option',      'label': 'Intrag Option',       'url': '/intrag-option',                'dirs': ('Intrag/Option',),                            'les': ('LAW', 'ATA')},
]

_NDM_JPM_RE = re.compile(r'J\.?P\.?\s*MORGAN', re.IGNORECASE)

_NDM_ATA_DIRS = {'Option/Equity', 'Option/Equities', 'Swap/Equities'}

_NDM_GENERIC_NDF_DIRS = {'NDF/FWD Start', 'NDF/FwdStart',
                         'NDF/OtherPublisher', 'NDF/Other Publisher',
                         'NDF/Vanilla'}

def _ndm_deal_le(pkey, d):
    """Entidade (LE) de uma linha do monitor, para os subitens dos cards.
    Intrag: pelo portfolio code — INTRAGJP552 = LAW, INTRAGJP633 = ATA
    (Intrag NDF grava 'portfolio_code', Intrag Option grava 'portfolio').
    NDFs genéricos (Vanilla/Other Pub/FWD Start): LE = MGT → MGT;
    Client com LAWTON → LAW (operação contra a Lawton); resto → JPM. O teste
    "Client = Banco" não serve aqui: o nome da MGT no RefData também casa com
    J.P. Morgan, então as linhas JPM×MGT cairiam em LAW indevidamente.
    Demais produtos B3: linha cujo Client é o Banco J.P. Morgan é a
    perna-espelho da entidade intragrupo (ATA nos produtos de equities, LAW
    nos demais); o resto é registro do Banco → JPM."""
    if pkey.startswith('Intrag'):
        code = str(d.get('portfolio_code') or d.get('portfolio') or '').strip().upper()
        return {'INTRAGJP552': 'LAW', 'INTRAGJP633': 'ATA'}.get(code, 'ATA')
    cl = str(d.get('Client') or '')
    if pkey in _NDM_GENERIC_NDF_DIRS:
        if str(d.get('LE') or '').strip().upper() == 'MGT':
            return 'MGT'
        return 'LAW' if 'LAWTON' in cl.upper() else 'JPM'
    if _NDM_JPM_RE.search(cl):
        return 'ATA' if pkey in _NDM_ATA_DIRS else 'LAW'
    return 'JPM'

def _ndm_monitor_snapshot(ref):
    """(cards, conf_cards) do Monitor na reference date — exatamente a estrutura
    que a página consome. Está fora do endpoint de propósito: o e-mail diário de
    pendências lê daqui, e assim não existe uma segunda contagem para divergir
    do que o usuário vê na tela."""
    want = ref.strftime('%Y%m%d')

    # Um único walk: agrupa os arquivos DA DATA por produto (caminho sem os
    # níveis de ano/mês), contando linhas por Status e por LE (_ndm_deal_le).
    found, found_les = {}, {}
    if os.path.isdir(_R().NEW_DEALS_CACHE_ROOT):
        for root, _dirs, files in os.walk(_R().NEW_DEALS_CACHE_ROOT):
            for fname in files:
                if not fname.endswith('.json') or fname[:8] != want:
                    continue
                rel = os.path.relpath(root, _R().NEW_DEALS_CACHE_ROOT).replace('\\', '/')
                pkey = '/'.join([p for p in rel.split('/') if not p.isdigit()][:2])
                try:
                    with open(os.path.join(root, fname), encoding='utf-8') as fh:
                        data = json.load(fh)
                except Exception:
                    continue
                bucket = found.setdefault(pkey, _R().Counter())
                les    = found_les.setdefault(pkey, _R().Counter())
                for d in (data if isinstance(data, list) else [data]):
                    if isinstance(d, dict):
                        # Intrag entries carry lowercase 'status' — without the
                        # fallback every intrag deal counted as 'New' forever.
                        st = str(d.get('Status') or d.get('status') or 'New').strip() or 'New'
                        if st == 'Canceled':      # cancelado via API: fora das métricas
                            continue
                        bucket[st] += 1
                        les[_ndm_deal_le(pkey, d)] += 1

    cards, claimed = [], set()
    for c in _NDM_CARDS:
        agg, agg_le = _R().Counter(), _R().Counter()
        for dkey in c['dirs']:
            if dkey in found:
                agg.update(found[dkey])
                agg_le.update(found_les.get(dkey, {}))
                claimed.add(dkey)
        cards.append({
            'key': c['key'], 'label': c['label'], 'url': c['url'],
            'soon': bool(c.get('soon')), 'total': sum(agg.values()),
            'statuses': dict(agg),
            # Lista ordenada (não dict) para o front preservar a ordem dos LEs
            'les': [{'le': k, 'count': agg_le.get(k, 0)} for k in c.get('les', ())],
        })
    # "e etc": qualquer produto com arquivos na data que não está no catálogo
    # (ex.: Swap Rates / Swap Commodities) ganha um card genérico no fim.
    for pkey in sorted(found):
        if pkey in claimed:
            continue
        agg = found[pkey]
        cards.append({
            'key': 'extra-' + pkey.lower().replace('/', '-').replace(' ', '-'),
            'label': pkey.replace('/', ' '), 'url': None, 'soon': False,
            'total': sum(agg.values()), 'statuses': dict(agg),
        })

    # Zona Confirmations: segregação contraparte × mercadoria (pontas
    # banco/lawton fora). O ciclo aqui é o DA CONFIRMAÇÃO (New → Generated →
    # Success), não o status dos deals: cada grupo segregado conta 1 no chip do
    # seu estágio. NDF Commodities, Commodities Options e FX Options têm o
    # fluxo completo; os demais produtos só contam a segregação.
    conf_groups, _deal_statuses, _conf_deal_total = _R()._conf_ndfcomm_groups(ref)
    conf_state = _R()._conf_state_load(ref)
    # UMA leitura da esteira para os quatro cards de confirmação.
    conf_stages = _R()._conf_esteira_stages()
    conf_statuses = _R()._conf_stage_counts(
        conf_groups, conf_state,
        lambda g: _R()._conf_key(g['acronym'], g['mercadoria'], g['family']), conf_stages)
    conf_cards = [{
        'key': 'conf-ndf-commodities', 'label': 'NDF Commodities',
        'url': '/new_deals-ndf-commodities', 'soon': False,
        'total': len(conf_groups), 'statuses': conf_statuses,
        'groups': [{'label': '{} · {}'.format(g['acronym'], g['mercadoria']),
                    'family': g['family'], 'count': g['count']} for g in conf_groups],
    }]

    def _conf_option_card(key, label, url, cache_dirs, suffix, by_commodity):
        if isinstance(cache_dirs, str):
            cache_dirs = (cache_dirs,)
        groups = {}
        for cache_dir in cache_dirs:
            fp = os.path.join(cache_dir, ref.strftime('%Y'), ref.strftime('%m'),
                              ref.strftime('%Y%m%d') + suffix)
            if not os.path.isfile(fp):
                continue
            try:
                with open(fp, encoding='utf-8') as fh:
                    data = json.load(fh)
            except Exception:
                data = []
            for d in (data if isinstance(data, list) else []):
                if not isinstance(d, dict):
                    continue
                if str(d.get('Status') or '').strip() == 'Canceled':
                    continue
                client = str(d.get('Client') or '').strip()
                if _R()._CONF_INTERNAL_RE.search(client):
                    continue
                acr = str(d.get('Acronym') or '').strip() or client or '(sem contraparte)'
                merc = str(d.get('Commodities') or '').strip().upper() if by_commodity else ''
                g = groups.setdefault((acr, merc), {'acronym': acr, 'mercadoria': merc,
                                                    'count': 0, 'trades': []})
                g['count'] += 1
                for c in ('Deal', 'B3_ID'):
                    v = str(d.get(c) or '').strip()
                    if v:
                        g['trades'].append(v)
        ordered = sorted(groups.values(), key=lambda g: (g['acronym'], g['mercadoria']))
        return {
            'key': key, 'label': label, 'url': url, 'soon': False,
            'total': len(ordered),
            'statuses': _R()._conf_stage_counts(ordered, {}, None, conf_stages),
            'groups': [{'label': ('{} · {}'.format(g['acronym'], g['mercadoria'])
                                  if g['mercadoria'] else g['acronym']),
                        'count': g['count']} for g in ordered],
        }

    # FWD Start tem duas grafias de pasta em produção (FwdStart / FWD Start),
    # como nos cards de B3 — o card soma as duas. Segregação só por contraparte
    # (NDF de moeda não tem mercadoria).
    conf_cards.append(_conf_option_card(
        'conf-ndf-fwdstart', 'NDF FWD Start', '/new_deals-ndf-fwdstart',
        (os.path.join(_R().NEW_DEALS_CACHE_ROOT, 'NDF', 'FwdStart'),
         os.path.join(_R().NEW_DEALS_CACHE_ROOT, 'NDF', 'FWD Start')),
        '_ndffwdstart.json', False))
    # Commodities Options: ciclo próprio da confirmação, igual ao NDF Comm.
    opt_groups, _opt_deal_statuses, _opt_total = _R()._conf_optcomm_groups(ref)
    opt_state = _R()._conf_state_load(ref, 'opt-comm')
    opt_statuses = _R()._conf_stage_counts(
        opt_groups, opt_state,
        lambda g: _R()._conf_key(g['acronym'], g['mercadoria'], g['family']), conf_stages)
    conf_cards.append({
        'key': 'conf-opt-commodities', 'label': 'Commodities Options',
        'url': '/new_deals-opt-commodities', 'soon': False,
        'total': len(opt_groups), 'statuses': opt_statuses,
        'groups': [{'label': '{} · {}'.format(g['acronym'], g['mercadoria']),
                    'family': g['family'], 'count': g['count']} for g in opt_groups],
    })
    # FX Options: ciclo próprio da confirmação também (Vanilla × Asian), igual
    # ao Commodities Options — a segregação aqui é por contraparte × moeda base.
    fxo_groups, _fxo_deal_statuses, _fxo_total = _R()._conf_optfxo_groups(ref)
    fxo_state = _R()._conf_state_load(ref, 'opt-fxo')
    fxo_statuses = _R()._conf_stage_counts(
        fxo_groups, fxo_state,
        lambda g: _R()._conf_key(g['acronym'], g['mercadoria'], g['family']), conf_stages)
    conf_cards.append({
        'key': 'conf-opt-fxo', 'label': 'FX Options',
        'url': '/new_deals-opt-fxo', 'soon': False,
        'total': len(fxo_groups), 'statuses': fxo_statuses,
        'groups': [{'label': '{} · {}'.format(g['acronym'], g['mercadoria']),
                    'family': g['family'], 'count': g['count']} for g in fxo_groups],
    })

    return cards, conf_cards

_NDM_TAXONOMY = {
    'ndf-commodities':    ('NDF', 'Commodities'),
    'ndf-fwdstart':       ('NDF', 'FWD Start'),
    'ndf-otherpublisher': ('NDF', 'Other Publisher'),
    'ndf-vanilla':        ('NDF', 'Vanilla'),
    'opt-commodities':    ('Option', 'Commodities'),
    'opt-fxo':            ('Option', 'FX'),
    'opt-equity':         ('Option', 'Equity'),
    'swap-equities':      ('Swap', 'Equities'),
    'swap-cem':           ('Swap', 'CEM'),
    # Intrag não tem sub-variante: o tipo da linha já diz Intrag, e repetir a
    # palavra na coluna Detail não acrescenta nada.
    'intrag-ndf':         ('NDF', '—'),
    'intrag-option':      ('Option', '—'),
    'intrag-swap':        ('Swap', '—'),
}

_NDM_TYPE_ORDER = ['Registration', 'Confirmation', 'Intrag']

def _ndm_card_taxonomy(card, zone):
    """(tipo, produto, detalhe) de um card. Produto fora do catálogo (os cards
    'Others', que nascem sozinhos quando aparece um diretório novo no cache)
    cai no label do próprio card, para nunca sumir do e-mail por falta de
    cadastro."""
    key = str(card.get('key') or '')
    if key in _NDM_TAXONOMY:
        product, detail = _NDM_TAXONOMY[key]
    elif key.startswith('conf-') and key[5:] in _NDM_TAXONOMY:
        product, detail = _NDM_TAXONOMY[key[5:]]
    else:
        label = str(card.get('label') or key or '—').strip()
        parts = label.split(None, 1)
        product, detail = (parts[0], parts[1]) if len(parts) == 2 else (label, '—')
    return zone, product, detail

def _ndm_pending_blocks(ref):
    """Blocos (um por tipo) com os cards que ainda não estão 100% Success.
    Retorna (blocks, grand_total); lista vazia = nada pendente na data."""
    cards, conf_cards = _ndm_monitor_snapshot(ref)
    by_type = {}
    for zone, group in (('Registration', cards), ('Confirmation', conf_cards)):
        for card in group:
            # Intrag é zona própria na tela, mas vem junto dos cards de B3.
            z = 'Intrag' if str(card.get('key') or '').startswith('intrag-') else zone
            total = int(card.get('total') or 0)
            statuses = card.get('statuses') or {}
            # ⚠️ Success comparado SEM caixa: o cache do Intrag grava o status em
            # minúsculo ('success'), e contar só a grafia 'Success' deixaria os
            # cards de Intrag eternamente pendentes no aviso — falso alarme
            # diário é o jeito mais rápido de a mesa parar de ler o e-mail.
            # 'Ok' é o estado FECHADO dos cards de confirmação (inclui as
            # etapas depois do OTC, que `_conf_esteira_stages` traduz para
            # Ok): sem contá-lo aqui, confirmação já validada pelo OTC
            # continuaria aparecendo como ação pendente no e-mail.
            success = sum(int(v or 0) for k, v in statuses.items()
                          if str(k).strip().lower() in ('success', 'ok'))
            pending = total - success
            if total <= 0 or pending <= 0:
                continue
            _z, product, detail = _ndm_card_taxonomy(card, z)
            # Chips do card, na ordem em que aparecem: diz de QUE ação a
            # pendência é (New, Amend, Generated…), não só quantas são.
            breakdown = ', '.join(
                '{} {}'.format(v, str(k)[:1].upper() + str(k)[1:])
                for k, v in statuses.items()
                if str(k).strip().lower() not in ('success', 'ok') and v)
            by_type.setdefault(_z, []).append(
                {'product': product, 'detail': detail, 'pending': pending,
                 'breakdown': breakdown, 'total': total, 'success': success})
    blocks = []
    for t in _NDM_TYPE_ORDER + sorted(k for k in by_type if k not in _NDM_TYPE_ORDER):
        rows = by_type.get(t)
        if not rows:
            continue
        rows.sort(key=lambda r: (-r['pending'], r['product'], r['detail']))
        blocks.append({'type': t, 'rows': rows,
                       'total': sum(r['pending'] for r in rows)})
    return blocks, sum(b['total'] for b in blocks)

_NDM_PENDING_DEFAULT_TO = 'brazil.otc.ops@jpmorgan.com'

_NDM_PENDING_RECIPIENTS_FILE = os.path.join(_R()._DAILY_METRIC_DIR,
                                            'deals_monitor_pending_recipients.json')

_NDM_PENDING_TIMES = os.getenv('DEALS_MONITOR_PENDING_TIMES', '19:00,19:30')

def _ndm_pending_status():
    """{last, next} do aviso automático, para a tela do Control Panel.

    `last` é o desfecho gravado no último disparo ('enviado', 'empty', ou a
    mensagem do erro); `next` é o próximo horário calculado da MESMA forma que o
    scheduler calcula. Sem isto a única evidência de que a rotina rodou é uma
    linha de log no servidor, que ninguém lê — e "não está funcionando" fica sem
    resposta."""
    last = {}
    try:
        with open(_NDM_PENDING_STATUS_FILE, encoding='utf-8') as fh:
            d = json.load(fh)
        if isinstance(d, dict):
            last = d
    except Exception:                                       # noqa: BLE001
        last = {}
    now = _R()._br_now()
    times = _ndm_pending_times()
    nxt = None
    for hh, mm in times:
        cand = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if cand > now:
            nxt = cand
            break
    if nxt is None:
        hh, mm = times[0]
        nxt = (now + timedelta(days=1)).replace(hour=hh, minute=mm, second=0, microsecond=0)
    return {
        'times': ['{:02d}:{:02d}'.format(h, m) for h, m in times],
        'next': nxt.strftime('%d/%m/%Y %H:%M'),
        'now_br': now.strftime('%d/%m/%Y %H:%M'),
        'last': last,
    }

def _load_ndm_pending_recipients():
    """TO/CC do aviso, do card Deals Monitor do Control Panel. Sem nada salvo
    vale o default da mesa — assim a rotina já funciona no pull, antes de
    alguém abrir o Control Panel."""
    try:
        with open(_NDM_PENDING_RECIPIENTS_FILE, encoding='utf-8') as fh:
            d = json.load(fh)
        if isinstance(d, dict) and (d.get('to') or d.get('cc')):
            return {'to': d.get('to', '') or '', 'cc': d.get('cc', '') or ''}
    except Exception:
        pass
    return {'to': _NDM_PENDING_DEFAULT_TO, 'cc': ''}

def _save_ndm_pending_recipients(to, cc):
    os.makedirs(_R()._DAILY_METRIC_DIR, exist_ok=True)
    with open(_NDM_PENDING_RECIPIENTS_FILE, 'w', encoding='utf-8') as fh:
        json.dump({'to': to or '', 'cc': cc or ''}, fh, ensure_ascii=False, indent=2)

def _send_ndm_pending_email(ref, to_list, cc_list):
    """Envia o aviso de pendências do Monitor. Retorna True, 'empty' (nada
    pendente — não manda e-mail) ou a mensagem de erro."""
    from email.mime.image import MIMEImage
    try:
        # O contexto envolve a MONTAGEM INTEIRA, não só o `render_template`: o
        # `_get_logo_path` lê `current_app.root_path` e o gradiente do cabeçalho
        # também passa por aqui. Envolver só o render trocava um "Working outside
        # of application context" por outro, três linhas abaixo. Dentro do
        # request do botão Run isto é no-op (ver `_app_context`).
        with _R()._app_context():
            blocks, grand_total = _ndm_pending_blocks(ref)
            if not blocks:
                _R().log.info('[deals-monitor] %s: nada pendente, e-mail não enviado',
                         ref.strftime('%Y-%m-%d'))
                return 'empty'
            ref_fmt = ref.strftime('%d/%m/%Y')
            html = render_template('pages/email-template-deals-monitor.html',
                                   ref_date_fmt=ref_fmt, blocks=blocks,
                                   grand_total=grand_total, current_year=datetime.now().year)
            msg = MIMEMultipart('related')
            msg['Subject'] = 'Pending Action - Deals Monitor'
            msg['From'] = _R().SHARED_MAILBOX
            if to_list:
                msg['To'] = ', '.join(to_list)
            if cc_list:
                msg['Cc'] = ', '.join(cc_list)
            alt = MIMEMultipart('alternative')
            alt.attach(MIMEText('Please view this report in HTML.', 'plain', 'utf-8'))
            alt.attach(MIMEText(html, 'html', 'utf-8'))
            msg.attach(alt)
            logo_path = _R()._get_logo_path()
            if logo_path:
                with open(logo_path, 'rb') as f:
                    limg = MIMEImage(f.read())
                limg.add_header('Content-ID', '<otc_logo>')
                limg.add_header('Content-Disposition', 'inline', filename='logo.png')
                msg.attach(limg)
            _R()._attach_email_gradient(msg)
        with _R().smtplib.SMTP(_R().SMTP_HOST, _R().SMTP_PORT, timeout=20) as server:
            server.sendmail(_R().SHARED_MAILBOX, to_list + cc_list, msg.as_string())
        _R().log.info('[deals-monitor] aviso de pendências enviado — ref=%s · %d item(ns) '
                 'em %d tipo(s) · to=%s cc=%s', ref.strftime('%Y-%m-%d'), grand_total,
                 len(blocks), to_list, cc_list)
        return True
    except Exception as e:                                  # noqa: BLE001
        _R().log.error('[deals-monitor] aviso de pendências FALHOU:\n%s', traceback.format_exc())
        return '{}: {}'.format(type(e).__name__, e)

_ndm_pending_scheduler_started = False

_ndm_pending_scheduler_lock = threading.Lock()

_NDM_PENDING_SENT_FILE = os.path.join(_R()._DAILY_METRIC_DIR, 'deals_monitor_pending_sent.json')

_NDM_PENDING_STATUS_FILE = os.path.join(_R()._DAILY_METRIC_DIR, 'deals_monitor_pending_status.json')

def _ndm_pending_claim_slot(slot):
    """Reserva um disparo ('YYYY-MM-DD 19:00') EM DISCO. True = ninguém tinha
    reservado e o e-mail pode sair; False = já foi. Cross-process: duas
    instâncias do app não podem reservar o mesmo slot (ver `_claim_daily_slot`)."""
    return _R()._claim_daily_slot(_NDM_PENDING_SENT_FILE, _R()._DAILY_METRIC_DIR, slot, 16, 'deals-monitor')

def _ndm_pending_times():
    """Horários do dia em (hh, mm), ordenados. Entrada inválida cai no padrão —
    um typo na variável de ambiente não pode matar o aviso."""
    out = []
    for part in str(_NDM_PENDING_TIMES or '').split(','):
        part = part.strip()
        if not part:
            continue
        try:
            hh, mm = (int(x) for x in part.split(':')[:2])
        except (ValueError, TypeError):
            continue
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            out.append((hh, mm))
    return sorted(set(out)) or [(19, 0), (19, 30)]

def _ndm_pending_release_slot(slot):
    """Devolve um slot reivindicado, para que ele possa ser tentado de novo.

    Existe porque a reserva é feita ANTES do envio (é o que impede dois
    processos de mandarem o mesmo aviso). Se o envio falha — SMTP fora do ar,
    rede caindo, o que for — e o slot fica reservado, o aviso daquele horário
    está perdido para sempre: nem o próximo restart o recupera, porque o
    catch-up também consulta esta lista. Uma falha transitória virava um dia sem
    aviso, sem nada na tela para explicar."""
    _R()._release_daily_slot(_NDM_PENDING_SENT_FILE, slot, 'deals-monitor')

def _ndm_pending_status_write(slot, result, when):
    """Grava o desfecho do último disparo, para a tela poder responder "o aviso
    das 19h saiu?". O log do servidor tinha a resposta e ninguém o lê."""
    try:
        os.makedirs(_R()._DAILY_METRIC_DIR, exist_ok=True)
        _R()._atomic_write_json(_NDM_PENDING_STATUS_FILE, {
            'slot': slot, 'result': result,
            'at': when.strftime('%d/%m/%Y %H:%M:%S'),
        })
    except Exception:                                       # noqa: BLE001
        _R().log.warning('[deals-monitor] não consegui gravar o status do disparo:\n%s',
                    traceback.format_exc())

def _ndm_pending_disparar(slot, fired):
    """Manda o aviso de um slot, se ninguém já mandou. True quando o slot era
    deste processo (reivindicado agora).

    Sem destinatário e com falha de envio o slot é DEVOLVIDO: nos dois casos o
    aviso não saiu, e queimar o horário faria o problema desaparecer da fila em
    vez de ser tentado de novo. 'empty' (nada pendente) é desfecho legítimo e
    mantém a reserva — não há o que reenviar."""
    if not _ndm_pending_claim_slot(slot):
        return False
    rec = _load_ndm_pending_recipients()
    to_list, cc_list = _R()._parse_emails(rec['to']), _R()._parse_emails(rec['cc'])
    if not (to_list or cc_list):
        _R().log.warning('[deals-monitor] sem destinatário configurado — aviso pulado')
        _ndm_pending_status_write(slot, 'sem destinatário configurado', fired)
        _ndm_pending_release_slot(slot)
        return True
    res = _send_ndm_pending_email(fired, to_list, cc_list)
    # O resultado vai para o log SEMPRE: quando o aviso não chega, a primeira
    # pergunta é se ele não foi enviado ou se não havia pendência ('empty'), e
    # sem esta linha não dava para saber.
    _R().log.info('[deals-monitor] aviso de %s (BRT): %s', slot,
             'enviado' if res is True else res)
    _ndm_pending_status_write(slot, 'enviado' if res is True else str(res), fired)
    if res is not True and res != 'empty':
        _ndm_pending_release_slot(slot)
    return True

def _ndm_pending_catch_up(times):
    """Slots de HOJE que já passaram e ninguém reivindicou.

    A instância do time é reiniciada várias vezes por dia (o reloader fica
    desligado, então todo pull pede restart). Subindo depois das 19h30, o loop
    dormia até o dia seguinte e o aviso do dia simplesmente não saía — sem erro
    nenhum no log. O arquivo de claim é que garante que isto não vire e-mail
    repetido quando há mais de um restart."""
    now = _R()._br_now()
    for hh, mm in times:
        cand = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if cand > now:
            continue
        slot = '{} {:02d}:{:02d}'.format(now.strftime('%Y-%m-%d'), hh, mm)
        try:
            if _ndm_pending_disparar(slot, now):
                _R().log.info('[deals-monitor] aviso de %s recuperado no start '
                         '(processo subiu depois do horário)', slot)
        except Exception:                              # noqa: BLE001
            _R().log.error('[deals-monitor] catch-up de %s falhou:\n%s',
                      slot, traceback.format_exc())

def _ndm_pending_scheduler_loop():
    times = _ndm_pending_times()
    while True:
        try:
            # O catch-up roda a CADA volta, não só no start. Ele só dispara
            # slots de hoje que já passaram e que ninguém reivindicou — então
            # num dia normal não faz nada, e é ele que RETENTA o horário cujo
            # envio falhou e foi devolvido. Sem isto, uma queda de SMTP às 19h00
            # custava o aviso do dia inteiro.
            _ndm_pending_catch_up(times)
            now = _R()._br_now()
            # Próximo horário de hoje que ainda não passou; se todos passaram,
            # o primeiro de amanhã.
            nxt = None
            for hh, mm in times:
                cand = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
                if cand > now:
                    nxt = cand
                    break
            if nxt is None:
                hh, mm = times[0]
                nxt = (now + timedelta(days=1)).replace(hour=hh, minute=mm,
                                                        second=0, microsecond=0)
            time.sleep(max(1.0, (nxt - now).total_seconds()))
            fired = _R()._br_now()
            slot = '{} {:02d}:{:02d}'.format(fired.strftime('%Y-%m-%d'),
                                             nxt.hour, nxt.minute)
            if not _ndm_pending_disparar(slot, fired):
                time.sleep(60)
        except Exception:
            _R().log.error('[deals-monitor] scheduler error:\n%s', traceback.format_exc())
            time.sleep(60)

def _ndm_pending_start_scheduler():
    global _ndm_pending_scheduler_started
    with _ndm_pending_scheduler_lock:
        if _ndm_pending_scheduler_started:
            return
        _ndm_pending_scheduler_started = True
    threading.Thread(target=_ndm_pending_scheduler_loop,
                     name='deals-monitor-pending-scheduler', daemon=True).start()
    _R().log.info('[deals-monitor] scheduler de pendências iniciado (%s BRT · '
             'agora são %s no servidor / %s em Brasília)',
             ', '.join('{:02d}:{:02d}'.format(h, m) for h, m in _ndm_pending_times()),
             datetime.now().strftime('%H:%M'), _R()._br_now().strftime('%H:%M'))
