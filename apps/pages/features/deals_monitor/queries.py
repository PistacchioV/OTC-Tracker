# -*- coding: utf-8 -*-
"""As leituras do New Deals Monitor — o snapshot dos cards (a MESMA estrutura
que a página consome e que o e-mail de pendências lê, para nunca existir uma
segunda contagem), os blocos de pendência e o status do aviso automático.
"""
import json
import os
from datetime import timedelta

from apps.pages.features.deals_monitor import domain
from apps.pages.features.deals_monitor.infra import persistence


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


def _ndm_monitor_snapshot(ref):
    """(cards, conf_cards) do Monitor na reference date — exatamente a estrutura
    que a página consome. Está fora do endpoint de propósito: o e-mail diário de
    pendências lê daqui, e assim não existe uma segunda contagem para divergir
    do que o usuário vê na tela."""
    want = ref.strftime('%Y%m%d')

    # A varredura vai pelo `_day_files` COM PODA por data (desde=ate=ref): o
    # walk cru descia a árvore INTEIRA (todos os produtos × todos os meses) a
    # cada request — dezenas de listagens no share para achar os arquivos de
    # UMA data — e ainda abria cada um com `open()` cru, sem o memo que o
    # resto das telas ganhou. Com a poda só o ano/mês da data é listado, e o
    # `_day_json` serve do memo o arquivo que não mudou (o e-mail das 19h lê
    # os mesmos arquivos logo depois da tela). Agrupamento por produto
    # (caminho sem os níveis de dígitos), contando por Status e LE.
    ref_date = ref.date() if hasattr(ref, 'date') else ref
    found, found_les = {}, {}
    if os.path.isdir(_R().NEW_DEALS_CACHE_ROOT):
        for fpath, fname, mtime, size in _R()._day_files(
                _R().NEW_DEALS_CACHE_ROOT, '.json',
                desde=ref_date, ate=ref_date):
            if fname[:8] != want:
                continue
            root = os.path.dirname(fpath)
            rel = os.path.relpath(root, _R().NEW_DEALS_CACHE_ROOT).replace('\\', '/')
            pkey = '/'.join([p for p in rel.split('/') if not p.isdigit()][:2])
            data = _R()._day_json(fpath, mtime, size)
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
                    les[domain._ndm_deal_le(pkey, d)] += 1

    cards, claimed = [], set()
    for c in domain._NDM_CARDS:
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

    # A pasta é `NDF/FwdStart`, UMA grafia — a que o app grava. Segregação só
    # por contraparte (NDF de moeda não tem mercadoria).
    conf_cards.append(_conf_option_card(
        'conf-ndf-fwdstart', 'NDF FWD Start', '/new_deals-ndf-fwdstart',
        (os.path.join(_R().NEW_DEALS_CACHE_ROOT, 'NDF', 'FwdStart'),),
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
            _z, product, detail = domain._ndm_card_taxonomy(card, z)
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
    for t in domain._NDM_TYPE_ORDER + sorted(k for k in by_type
                                             if k not in domain._NDM_TYPE_ORDER):
        rows = by_type.get(t)
        if not rows:
            continue
        rows.sort(key=lambda r: (-r['pending'], r['product'], r['detail']))
        blocks.append({'type': t, 'rows': rows,
                       'total': sum(r['pending'] for r in rows)})
    return blocks, sum(b['total'] for b in blocks)


def _ndm_pending_status():
    """{last, next} do aviso automático, para a tela do Control Panel.

    `last` é o desfecho gravado no último disparo ('enviado', 'empty', ou a
    mensagem do erro); `next` é o próximo horário calculado da MESMA forma que o
    scheduler calcula. Sem isto a única evidência de que a rotina rodou é uma
    linha de log no servidor, que ninguém lê — e "não está funcionando" fica sem
    resposta."""
    last = {}
    try:
        with open(persistence._NDM_PENDING_STATUS_FILE, encoding='utf-8') as fh:
            d = json.load(fh)
        if isinstance(d, dict):
            last = d
    except Exception:                                       # noqa: BLE001
        last = {}
    now = _R()._br_now()
    times = domain._ndm_pending_times()
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
