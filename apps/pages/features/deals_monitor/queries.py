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
from apps.pages import data_store as _store  # noqa: E402
from apps.pages.data_paths import unwinds_cache_root  # noqa: E402


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

    def _varre(raiz, prefixo=''):
        """Conta por produto × status × LE os arquivos-dia de `raiz` na data.

        `prefixo` entra no pkey para as árvores que NÃO são a de New Deals: as
        recompras vivem em `cache/unwinds/` (fora dela de propósito, §454), e
        sem o prefixo um `NDF/FX` de lá cairia no mesmo balde de um `NDF/FX`
        que alguém criasse aqui — duas coisas diferentes somadas num card só,
        sem nada acusar."""
        if not _store.isdir(raiz):
            return
        _dias = list(_R()._day_files(raiz, '.json', desde=ref_date, ate=ref_date))
        # UMA abertura de banco para todos os dias enumerados, em vez de
        # uma por dia: eles são tabelas do MESMO banco do produto (§4).
        _R()._day_prefetch(_dias)
        for fpath, fname, mtime, size in _dias:
            if fname[:8] != want:
                continue
            root = os.path.dirname(fpath)
            rel = os.path.relpath(root, raiz).replace('\\', '/')
            pkey = prefixo + '/'.join([p for p in rel.split('/') if not p.isdigit()][:2])
            data = _R()._day_json(fpath, mtime, size)
            for d in (data if isinstance(data, list) else [data]):
                if isinstance(d, dict):
                    # Intrag entries carry lowercase 'status' — without the
                    # fallback every intrag deal counted as 'New' forever.
                    st = str(d.get('Status') or d.get('status') or 'New').strip() or 'New'
                    if st == 'Canceled':      # cancelado via API: fora das métricas
                        continue
                    # O balde é da LINHA, não do arquivo: nas pastas de swap a
                    # LOB de cada operação decide o card (`domain._ndm_bucket`),
                    # e o mesmo arquivo-dia alimenta Swap Equities e Swap CEM.
                    balde = domain._ndm_bucket(pkey, d)
                    found.setdefault(balde, _R().Counter())[st] += 1
                    found_les.setdefault(balde, _R().Counter())[domain._ndm_deal_le(pkey, d)] += 1
                    # A operação que VAI para a Intrag conta lá desde o import,
                    # não só quando o espelho nasce no Success (§567).
                    destino = domain.intrag_destino(pkey, d) if not prefixo else None
                    if destino:
                        found.setdefault(destino, _R().Counter())[domain.AWAITING_B3] += 1
                        found_les.setdefault(destino, _R().Counter())[
                            domain.intrag_destino_le(destino)] += 1

    _varre(_R().NEW_DEALS_CACHE_ROOT)
    # As RECOMPRAS: outra árvore, mesmo Monitor. O caminho vem do `data_paths`
    # (a mesma porta que a vertical usa para gravar) e o prefixo do `domain`,
    # que é quem o catálogo de cards declara em `dirs`.
    _varre(unwinds_cache_root(), domain.PREFIXO_UNWIND)

    cards, claimed = [], set()
    for c in domain._NDM_CARDS:
        agg, agg_le = _R().Counter(), _R().Counter()
        for dkey in domain.card_buckets(c):
            if dkey in found:
                agg.update(found[dkey])
                agg_le.update(found_les.get(dkey, {}))
                claimed.add(dkey)
        cards.append({
            'key': c['key'], 'label': c['label'], 'url': c['url'],
            'soon': bool(c.get('soon')), 'total': sum(agg.values()),
            'statuses': dict(agg),
            # Os estados FECHADOS deste produto, quando ele não fecha em
            # `Success`/`Ok` — o aviso de pendências lê daqui.
            'done': list(c.get('done') or ()),
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
            if not _store.isfile(fp):
                continue
            try:
                from apps.pages import duck_read  # DB-only (fase 3): arquivo-dia payload-LISTA.
                data = duck_read.day_records(fp)
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
    # NDF da JPMORGAN CHASE (MGT) contra cliente — Vanilla e FWD Start no
    # documento MGT (§453): ciclo próprio, um grupo por contraparte × moeda ×
    # produto. Os deals de MGT saem do card do FWD Start do BANCO e entram aqui.
    mgt_groups, _mgt_deal_statuses, _mgt_total = _R()._conf_mgt_groups(ref)
    mgt_state = _R()._conf_state_load(ref, 'ndf-mgt')
    mgt_statuses = _R()._conf_stage_counts(
        mgt_groups, mgt_state,
        lambda g: _R()._conf_key(g['acronym'], g['mercadoria'], g['family']), conf_stages)
    conf_cards.append({
        'key': 'conf-ndf-mgt', 'label': 'NDF MGT x Client',
        'url': '/new_deals-ndf-vanilla', 'soon': False,
        'total': len(mgt_groups), 'statuses': mgt_statuses,
        'groups': [{'label': '{} · {} · {}'.format(g['acronym'], g['mercadoria'],
                                                   _R()._CONF_MGT_FAMILY_LABEL.get(g['family'], g['family'])),
                    'family': g['family'], 'count': g['count']} for g in mgt_groups],
    })
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

    # Termo de Resilição (mesa, 28/09/2026): as recompras do dia CONTRA O
    # CLIENTE (NDF FX e as do catálogo com Termo — o fundo não tem Termo, §580),
    # pela MESMA segregação do Confirmations Monitor (contraparte × moeda, ou
    # mercadoria no NDF Comm; `_conf_unwind_groups`). A etapa é a da esteira,
    # onde a recompra entra no import; sem documento gerado ela é `Pending OTC`.
    unw_groups, _unw_deal_statuses, _unw_total = _R()._conf_unwind_groups(ref)
    conf_cards.append({
        'key': 'conf-unwind-termo', 'label': 'Termo de Resilição',
        'url': '/manual-confirmation/monitor', 'soon': False,
        'total': len(unw_groups),
        'statuses': _R()._conf_stage_counts(unw_groups, {}, None, conf_stages),
        'groups': [{'label': '{} · {}'.format(g['acronym'], g['mercadoria']) if g['mercadoria']
                    else g['acronym'], 'family': g['family'], 'count': g['count']}
                   for g in unw_groups],
    })

    return cards, conf_cards


def _fechados(card):
    """Os status em que o card FECHA, sem caixa: `success`/`ok` mais o `done`
    que o card declara. UMA regra para a tela, o aviso das 19h e as tarefas do
    Intraday Monitor — ver o comentário do `_ndm_pending_blocks`."""
    f = {'success', 'ok'}
    f.update(str(x).strip().lower() for x in (card.get('done') or ()))
    return f


def _card_zone(card, zone):
    """A zona do card: Intrag é zona própria na tela, mas vem junto dos cards
    de B3 (o único teste é o prefixo da chave)."""
    return 'Intrag' if str(card.get('key') or '').startswith('intrag-') else zone


def _zone_totals(cards, conf_cards):
    """{zona: {total, closed}} — o progresso de cada zona, pela regra do
    `_fechados`. Zona sem nada importado vem com zero nos dois."""
    out = {z: {'total': 0, 'closed': 0} for z in domain._NDM_TYPE_ORDER}
    for zone, group in (('Registration', cards), ('Confirmation', conf_cards)):
        for card in group:
            z = out.setdefault(_card_zone(card, zone), {'total': 0, 'closed': 0})
            fim = _fechados(card)
            z['total'] += int(card.get('total') or 0)
            z['closed'] += sum(int(v or 0) for k, v in (card.get('statuses') or {}).items()
                               if str(k).strip().lower() in fim)
    return out


def _ndm_pending_blocks(ref, cards=None, conf_cards=None):
    """Blocos (um por tipo) com os cards que ainda não estão 100% Success.
    Retorna (blocks, grand_total); lista vazia = nada pendente na data.
    Quem já tem os cards (o snapshot do Intraday Monitor) os passa, e a zona
    não é contada duas vezes."""
    if cards is None or conf_cards is None:
        cards, conf_cards = _ndm_monitor_snapshot(ref)
    by_type = {}
    for zone, group in (('Registration', cards), ('Confirmation', conf_cards)):
        for card in group:
            z = _card_zone(card, zone)
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
            # O card pode DECLARAR onde ele fecha (`done`): a recompra acaba
            # em `Sent`, porque o B3 ID de volta ainda não existe para ela.
            fechados = _fechados(card)
            success = sum(int(v or 0) for k, v in statuses.items()
                          if str(k).strip().lower() in fechados)
            pending = total - success
            if total <= 0 or pending <= 0:
                continue
            _z, product, detail = domain._ndm_card_taxonomy(card, z)
            # Chips do card, na ordem em que aparecem: diz de QUE ação a
            # pendência é (New, Amend, Generated…), não só quantas são.
            breakdown = ', '.join(
                '{} {}'.format(v, str(k)[:1].upper() + str(k)[1:])
                for k, v in statuses.items()
                if str(k).strip().lower() not in fechados and v)
            by_type.setdefault(_z, []).append(
                {'product': product, 'detail': detail, 'pending': pending,
                 'breakdown': breakdown, 'total': total, 'success': success,
                 'key': card.get('key'), 'url': card.get('url')})
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
        d = _store.read(persistence._NDM_PENDING_STATUS_FILE)
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


# ══════════════════════════════════════════════════════════════════════════
# INTRADAY MONITOR (§567)
# ══════════════════════════════════════════════════════════════════════════

def _recon_fallback(task_id, dia):
    """(rodou?, hora 'HH:MM', pendências) pelo cache da PRÓPRIA recon — o plano
    B para o que rodou antes de existir o registro de execuções (o dia do
    deploy). Só vale execução CARIMBADA no dia pedido: a data de referência de
    uma recon não é o dia em que alguém a rodou (a CGD lê o D-1), e aceitar a
    referência como execução daria como feita hoje a recon rodada ontem.
    A Comitente não tem plano B: ela não guarda nem data nem hora (§567)."""
    ymd = dia.strftime('%Y-%m-%d')
    br = dia.strftime('%d/%m/%Y')
    try:
        if task_id == 'recon-fxo':
            from apps.pages import recon_fxo
            d = _store.read(recon_fxo._cache_path(ymd))
            ran = str((d or {}).get('ran_at') or '')
            if ran.startswith(br):
                c = d.get('counts') or {}
                return True, ran[11:16], sum(int(c.get(k) or 0)
                                             for k in ('nok', 'no_match', 'no_match_ath'))
        elif task_id == 'recon-cgd':
            from apps.pages import recon_cgd
            d = recon_cgd.carregar(recon_cgd.dia_util_anterior(dia).strftime('%Y-%m-%d'))
            ger = str((d or {}).get('generated_at') or '')
            if ger.startswith(br):
                c = d.get('counts') or {}
                return True, ger[11:16], sum(int(c.get(k) or 0)
                                             for k in ('pending_b3', 'pending_action', 'only_b3'))
        elif task_id == 'recon-payrec':
            from apps.pages import recon_payrec
            path = os.path.join(recon_payrec._CACHE_DIR, ymd + '.json')
            if _store.exists(path):
                from datetime import datetime as _dt
                quando = _dt.fromtimestamp(_store.stat(path).st_mtime)
                if quando.date() == dia:
                    d = _store.read(path) or {}
                    return True, quando.strftime('%H:%M'), (
                        len(d.get('pending_payment') or []) + len(d.get('pending_receivement') or []))
        elif task_id == 'save-cetip':
            hora = _cetip_saved_notif(dia)
            if hora:
                return True, hora, None
    except FileNotFoundError:
        pass
    except Exception:                                       # noqa: BLE001
        _R().log.warning('[intraday-monitor] plano B de %s falhou', task_id, exc_info=True)
    return False, '', None


def _cetip_saved_notif(dia):
    """'HH:MM' do primeiro aviso "CETIP Files Saved" do dia com ao menos um
    arquivo salvo, ou None — o plano B do Save CETIP Files. Cada pessoa roda a
    PRÓPRIA instância: quem salva por uma instância sem o `task_runs.record`
    (pull/restart atrasado) ou com o registro perdido (banco ocupado) deixava a
    tarefa aberta no Monitor com os arquivos salvos. O aviso do sino sai de
    toda versão da rotina, na mesma hora, e diz o que foi salvo."""
    from datetime import timedelta
    conn = _R().get_notif_connection(readonly=True)
    try:
        row = conn.execute(
            "SELECT MIN(created_at) FROM notifications "
            "WHERE action = 'CETIP Files Saved' AND created_at >= ? AND created_at < ? "
            "AND detail NOT LIKE '0 file%'",
            [dia, dia + timedelta(days=1)]).fetchone()
    finally:
        conn.close()
    return row[0].strftime('%H:%M') if row and row[0] else None


def _branch_state(dia, runs):
    """O estado da Branch Reversal no dia, pelo resultado do Pay/Rec (o
    finalizado quando há, senão o de trabalho) e pelo registro de execuções.

    `detected` só com a ROTA NOVA e reversão a fazer (`has_settlement` +
    `pay_receive`, a mesma condição do botão Branch Settl.). Pay/Rec que não
    rodou não diz nada — a tarefa não aparece, e o cartão do Pay/Rec já diz
    que ele não rodou. `settled` é a linha da reversão (`branch == 'reversal'`)
    casada com o extrato ou justificada."""
    from apps.pages import recon_payrec
    try:
        d = recon_payrec.load_last(dia.strftime('%Y-%m-%d')) or {}
    except Exception:                                       # noqa: BLE001
        _R().log.warning('[intraday-monitor] Pay/Rec ilegível para a Branch', exc_info=True)
        d = {}
    b = d.get('branch') or {}
    out = {'detected': bool(b.get('has_settlement') and b.get('pay_receive')),
           'pay_receive': b.get('pay_receive') or '', 'amount': b.get('reversal_net'),
           'settled': False, 'draft_at': None, 'draft_by': None}
    for lista, fechou in (('settled', True), ('pending_payment', False),
                          ('pending_receivement', False)):
        for r in d.get(lista) or []:
            if isinstance(r, dict) and r.get('branch') == 'reversal':
                if fechou or str(r.get('status') or '').strip().lower() == 'justified':
                    out['settled'] = True
    drafts = [r for r in runs if r.get('task') == 'branch-reversal' and r.get('event') == 'draft']
    if drafts:
        out['draft_at'] = drafts[-1].get('time')
        out['draft_by'] = drafts[-1].get('name') or drafts[-1].get('sid')
    return out


def _payrec_ended_fallback(task_id, dia):
    """(finalizado?, 'HH:MM') do Pay/Rec pelo histórico que o End process grava
    — o plano B para o dia finalizado antes de existir o registro. Vale só com o
    carimbo no dia pedido, pela mesma razão do `_recon_fallback`."""
    if task_id != 'recon-payrec':
        return False, None
    try:
        from apps.pages import recon_payrec
        from datetime import datetime as _dt
        p = recon_payrec._history_path(dia.strftime('%Y-%m-%d'))
        if p and _store.exists(p):
            quando = _dt.fromtimestamp(_store.stat(p).st_mtime)
            if quando.date() == dia:
                return True, quando.strftime('%H:%M')
    except FileNotFoundError:
        pass
    except Exception:                                       # noqa: BLE001
        _R().log.warning('[intraday-monitor] histórico do Pay/Rec ilegível', exc_info=True)
    return False, None


def _intraday_snapshot(ref):
    """O que a página do Intraday Monitor desenha, num request só: as tarefas
    do dia com estado e progresso, os KPIs, a atividade (quem rodou o quê) e
    os cards das zonas — que são o DETALHE da página, então saem da mesma
    contagem que decidiu o estado das três tarefas de zona."""
    from apps.pages.platform import task_runs
    dia = ref.date() if hasattr(ref, 'date') else ref
    agora = _R()._br_now().replace(tzinfo=None)
    feriado = dia.strftime('%Y-%m-%d') in (_R()._anbima_holidays() or ())
    cfg = domain.task_config(persistence._load_intraday_tasks())

    cards, conf_cards = _ndm_monitor_snapshot(ref)
    zonas = _zone_totals(cards, conf_cards)
    runs = task_runs.runs_of(dia)

    tarefas = []
    for t in domain.TASKS:
        c = cfg[t['id']]
        item = {'id': t['id'], 'kind': t['kind'], 'label': t['label'], 'icon': t['icon'],
                'url': t['url'], 'days': c['days'], 'done_on': t.get('done_on') or 'run'}
        if t['kind'] == 'branch':
            b = _branch_state(dia, runs)
            item.update(b)
            passos = 2 if b['settled'] else (1 if b['draft_at'] else 0)
            item['progress'] = passos * 50
            est = domain.avalia(c, dia, agora, feriado, b['settled'], bool(b['draft_at']))
            # Só EXISTE no dia com liquidação da Branch: fora disso não é devida
            # nem aparece na linha "fora da agenda" (`conditional`).
            est['due'] = est['due'] and b['detected']
            item['conditional'] = True
        elif t['kind'] == 'zone':
            z = zonas.get(t['zone']) or {'total': 0, 'closed': 0}
            total, fechado = z['total'], z['closed']
            feito = fechado >= total                  # zona vazia: nada a fazer
            item.update({'total': total, 'closed': fechado, 'open': total - fechado,
                         'progress': 100 if not total else int(round(100.0 * fechado / total))})
            est = domain.avalia(c, dia, agora, feriado, feito, fechado > 0)
        else:
            meus = [r for r in runs if r.get('task') == t['id']]
            execs = [r for r in meus if r.get('event', 'run') == 'run']
            if execs:
                ultimo = execs[-1]
                item.update({'ran_at': execs[0].get('time'), 'last_at': ultimo.get('time'),
                             'by': ultimo.get('name') or ultimo.get('sid'),
                             'open': (ultimo.get('summary') or {}).get('open'),
                             'runs': len(execs)})
                feito_em = _parse_hora(dia, execs[0].get('time'))
            else:
                rodou, hora, pend = _recon_fallback(t['id'], dia)
                if rodou:
                    item.update({'ran_at': hora, 'last_at': hora, 'open': pend, 'runs': 1})
                feito_em = _parse_hora(dia, hora) if rodou else None
            fins = [r for r in meus if r.get('event') == 'end']
            if fins:
                item['ended'], item['ended_at'] = True, fins[-1].get('time')
            else:
                item['ended'], item['ended_at'] = _payrec_ended_fallback(t['id'], dia)
            rodou = bool(item.get('runs'))
            if t.get('done_on') == 'end':
                # Conclui no End process: rodar é o meio do caminho.
                feito = bool(item['ended'])
                item['progress'] = 100 if feito else (50 if rodou else 0)
                est = domain.avalia(c, dia, agora, feriado, feito, rodou,
                                    _parse_hora(dia, item['ended_at']) if feito else None)
            else:
                feito = rodou
                item['progress'] = 100 if feito else 0
                est = domain.avalia(c, dia, agora, feriado, feito, False, feito_em)
        item.update(est)
        tarefas.append(item)

    devidas = [x for x in tarefas if x['due']]
    kpis = {s: sum(1 for x in devidas if x['state'] == s)
            for s in ('done', 'in_progress', 'todo', 'late')}
    kpis['due'] = len(devidas)
    kpis['pct'] = int(round(100.0 * kpis['done'] / len(devidas))) if devidas else 100
    # O progresso MÉDIO: a zona pela metade conta pela metade. É o segundo
    # número do anel — "concluídas" só anda quando uma tarefa inteira fecha.
    kpis['progress'] = (int(round(sum(x['progress'] for x in devidas) / float(len(devidas))))
                        if devidas else 100)
    rotulo = {t['id']: t['label'] for t in domain.TASKS}
    atividade = [{'task': r.get('task'), 'label': rotulo.get(r.get('task'), r.get('task')),
                  'time': r.get('time'), 'by': r.get('name') or r.get('sid'),
                  'event': r.get('event', 'run'), 'open': (r.get('summary') or {}).get('open')}
                 for r in reversed(runs)]
    return {'date': dia.strftime('%Y-%m-%d'), 'now': agora.strftime('%Y-%m-%dT%H:%M'),
            'holiday': feriado, 'tasks': tarefas, 'kpis': kpis, 'activity': atividade,
            'cards': cards, 'conf_cards': conf_cards}


def _parse_hora(dia, hhmm):
    from datetime import datetime as _dt
    try:
        hh, mm = (int(x) for x in str(hhmm or '').split(':')[:2])
        return _dt(dia.year, dia.month, dia.day, hh, mm)
    except (TypeError, ValueError):
        return None


def _fmt_brl(v):
    try:
        return 'R$ {:,.2f}'.format(abs(float(v)))
    except (TypeError, ValueError):
        return ''


def task_detail(t):
    """A situação de UMA tarefa em frase curta — a coluna Detail do e-mail
    (que é em inglês, como o resto dele)."""
    if t['kind'] == 'zone':
        if not t.get('total'):
            return 'Nothing imported for this date.'
        return '{}/{} closed · {} open'.format(t['closed'], t['total'], t['open'])
    if t['kind'] == 'branch':
        valor = '{} {}'.format('Bank pays' if t.get('pay_receive') == 'Pay' else 'Bank receives',
                               _fmt_brl(t.get('amount')))
        if t.get('settled'):
            return valor + ' — settled in Pay/Rec.'
        if t.get('draft_at'):
            return valor + ' — VP approval draft at {}; reversal not settled in Pay/Rec yet.'.format(
                t['draft_at'])
        return valor + ' — VP approval draft not generated yet.'
    if not t.get('runs'):
        return 'Not run yet.'
    txt = 'Ran at {}'.format(t.get('last_at') or t.get('ran_at'))
    if t.get('open') is not None:
        txt += ' · {} open break(s)'.format(t['open'])
    if t.get('done_on') == 'end' and not t.get('ended'):
        txt += ' — End process not run yet.'
    return txt


def _intraday_pending(ref):
    """O conteúdo do aviso de pendências do Intraday Monitor: (tarefas,
    blocos, total, kpis). `tarefas` são as DEVIDAS e não concluídas, com a
    frase da situação; `blocos` é o detalhe por produto das zonas, do MESMO
    snapshot (a zona não é contada duas vezes). Nada nos dois = nada a cobrar."""
    snap = _intraday_snapshot(ref)
    tarefas = [dict(t, detail=task_detail(t)) for t in snap['tasks']
               if t['due'] and t['state'] != 'done']
    ordem = {'late': 0, 'in_progress': 1, 'todo': 2}
    tarefas.sort(key=lambda t: (ordem.get(t['state'], 3), t['deadline']))
    blocks, total = _ndm_pending_blocks(ref, snap['cards'], snap['conf_cards'])
    return tarefas, blocks, total, snap['kpis']


# ══ PENDENTE DE D-1 (§567) ═══════════════════════════════════════════════════
# O card "From D-1" do Monitor: o que ficou por fazer no dia útil anterior, item
# a item, cada um com o link para a página JÁ na data (`?tradedate=` nas telas
# de operação, `?date=` nas recons — `static/js/deep-link.js`). É o MESMO
# snapshot do dia, aplicado ao D-1, e fica em memória por alguns minutos: o
# Monitor consulta a cada 60 s, e o D-1 muda pouco — refazer as duas contagens
# em todo poll dobraria as idas ao share.
_PREV_CACHE = {}
_PREV_TTL = 180


def _link(url, param, iso):
    if not url or url.startswith('#'):
        return None
    return '{}{}{}={}'.format(url, '&' if '?' in url else '?', param, iso)


def _prev_items(ref):
    """{date, date_fmt, items, tasks}: as pendências do dia útil anterior a `ref`."""
    import time as _t
    d1 = _R()._prev_anbima_bizday(ref.date() if hasattr(ref, 'date') else ref)
    chave = d1.strftime('%Y-%m-%d')
    em = _PREV_CACHE.get(chave)
    if em and em[0] > _t.time():
        return em[1]
    tarefas, blocks, _total, _kpis = _intraday_pending(d1)
    itens = []
    zonas_abertas = set()
    for b in blocks:
        for r in b['rows']:
            zonas_abertas.add(b['type'])
            nome = r['product'] if r['detail'] in ('—', '') else '{} {}'.format(r['product'], r['detail'])
            itens.append({'kind': 'zone', 'zone': b['type'], 'label': nome, 'count': r['pending'],
                          'detail': r['breakdown'], 'url': _link(r.get('url'), 'tradedate', chave)})
    ids = {t['id']: t for t in domain.TASKS}
    for t in tarefas:
        if t['kind'] == 'zone':
            continue                       # já está acima, produto a produto
        cat = ids.get(t['id']) or {}
        if t['kind'] == 'recon' and cat.get('link_ref', 'prev') == 'prev':
            dia_ref = _R()._prev_anbima_bizday(d1).strftime('%Y-%m-%d')
        else:
            dia_ref = chave
        itens.append({'kind': t['kind'], 'task': t['id'], 'label': t['label'], 'count': None,
                      'detail': t['detail'], 'url': _link(t['url'], 'date', dia_ref)})
    out = {'date': chave, 'date_fmt': d1.strftime('%d/%m/%Y'), 'items': itens,
           'tasks': len(tarefas)}
    _PREV_CACHE.clear()                    # só o D-1 corrente importa
    _PREV_CACHE[chave] = (_t.time() + _PREV_TTL, out)
    return out
