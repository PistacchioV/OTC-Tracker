# -*- coding: utf-8 -*-
"""As 44 rotas da família New Deals (NDF, FXO, Commodities e os genéricos).

Só a casca — a última e maior. Os MOTORES ficam no routes até a fase
platform/: os caches por dia e a persistência (`_generic_nd_*`, `_nd_*`), o
lookup de contraparte (`_ndf_ref_by_accronym`), o roteamento por publisher, o
espelho Lawton, os geradores TER/Conecta e os hooks de espelhamento (Pending
Confirmation, esteira, Intrag) — tudo alcançado por `_R()`.
"""
import io
import json
import os
import re
import traceback
from datetime import datetime

from flask import jsonify, request, session

from apps.pages import blueprint
from apps.pages import data_store as _store  # noqa: E402
from apps.pages.features.new_deals import catalog
from apps.pages.platform import authz as _authz
from apps.pages.platform import mirrors as _mirrors


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


# ── O mapeamento do B3 ID grava, e DIZ se gravou ────────────────────────────

# O que a tela recebe quando o mapeamento não chegou ao arquivo-dia. Não é
# `Error`: `Error` é o veredito da B3 (o retorno veio e não foi `EXECUCAO OK`),
# e confundir os dois faria a mesa procurar no arquivo de retorno um problema
# que está do lado de cá.
MAPPING_NAO_GRAVADO = 'Failed'


def _grava_mapeamento(finder, deal_text, client_name, updates):
    """Aplica o resultado do mapping na linha do arquivo-dia e DIZ se gravou.

    Devolve `(gravado, linha, motivo)` — a linha é a cópia JÁ atualizada, que
    é o que alimenta Intrag e Pending Confirmation.

    Os quatro endpoints de `mapping-b3` faziam isto no corpo, e os quatro
    respondiam `Success` à tela **sem olhar se a gravação aconteceu**
    (21/09/2026): o `new_status` era decidido pelo arquivo de retorno da B3 e ia
    para o `results` adiante, enquanto a gravação ficava atrás de um
    `if file_path is not None:` e de um `except Exception: pass`. Havia duas
    saídas mudas:

    1. **a linha não é achada** — o casamento é por `(Deal, Client)` EXATO, e
       não achando, o código seguia em frente;
    2. **a gravação estoura** — no share, `_store.read` e `_atomic_write_json`
       levantam `BancoOcupado`/`BancoIlegivel` quando a instância vizinha está
       com a trava (§4). Isso é ESPERADO ali, não excepcional, e o `pass`
       engolia.

    Nos dois casos o navegador recebia `Success`, pintava Status e B3 ID na
    grade e anunciava *"N deal(s) mapped successfully"*; na abertura seguinte a
    linha voltava do banco como estava — `Sent`. A mesa só descobria reabrindo a
    tela, e como o defeito depende da trava do vizinho, ele pegava ALGUMAS
    operações e não todas, que é o que mais atrapalha o diagnóstico.

    Por isso as duas saídas agora LOGAM com o deal e o cliente, e o resultado
    devolvido sai da gravação, nunca da intenção.
    """
    if not deal_text:
        return False, None, 'deal_vazio'
    file_path, idx = finder(deal_text, client_name)
    if file_path is None:
        # O finder já emitiu o diagnóstico detalhado (`[_find_ndf] CLIENT
        # MISMATCH` / `DEAL NAME NOT MATCHED`, com os pares (Deal, Client) do
        # arquivo). Esta linha é o que liga aquele diagnóstico ao mapeamento —
        # sem ela, o aviso do finder fica no log sem dizer o que se perdeu.
        _R().log.warning('[MAPPING-B3] linha NAO ENCONTRADA no arquivo-dia: '
                         'deal=%r client=%r — o B3 ID nao foi gravado',
                         deal_text, client_name)
        return False, None, 'row_not_found'
    with _R()._cache_lock:
        try:
            deals_list = _store.read(file_path)
            # O índice do finder é da leitura MEMOIZADA: com o dia mudado no meio
            # (a instância vizinha inseriu ou apagou uma linha), o B3 ID caía na
            # operação do lado. A linha se acha de novo na leitura fresca.
            deal_k, client_k = _nd_par(deal_text, client_name)
            idx = next((i for i, d in enumerate(deals_list)
                        if _nd_casa(d, deal_k, client_k)), None)
            if idx is None:
                _R().log.warning('[MAPPING-B3] linha SUMIU do arquivo-dia entre a busca e a '
                                 'gravação: deal=%r client=%r em %s', deal_text, client_name, file_path)
                return False, None, 'row_not_found'
            deals_list[idx].update(updates)
            _R()._atomic_write_json(file_path, deals_list)      # funil (§335)
            return True, deals_list[idx].copy(), ''
        except Exception as exc:                                # noqa: BLE001
            _R().log.exception('[MAPPING-B3] falha ao GRAVAR deal=%r client=%r em %s',
                               deal_text, client_name, file_path)
            return False, None, '%s: %s' % (type(exc).__name__, exc)


def _import_resposta(deals, data, base_dir, suffix, file_path):
    """O POST que o IMPORT do dropzone manda (`_import`) quando a grade não tem
    a operação: acha a linha já gravada em vez de duplicá-la (ver
    `_nd_import_upsert`). Chamar sob o `_cache_lock`, com `deals` já lido."""
    resultado, linha = _R()._nd_import_upsert(deals, data, base_dir, suffix, file_path)
    if resultado != 'same':
        _R()._atomic_write_json(file_path, deals)
    return jsonify({"success": True, "deal": data.get('Deal', ''), "result": resultado,
                    "status": linha.get('Status', ''), "b3_id": linha.get('B3_ID', '')})


# ── 4-olhos no SERVIDOR ───────────────────────────────────────────────────────
# O PATCH aplicava `deals[idx].update(updates)` com o que o navegador mandou:
# qualquer Status, e Maker/Checker do CORPO do pedido. A regra de que quem
# editou não aprova vivia só no JS — um POST direto, ou uma aba desatualizada,
# passava por cima. Swap Bullet/Cashflow, Unwinds e Intrag já conferem aqui.
_ND_FINAL_STATUSES = ('Sent', 'Success')
_ND_BACK_STATUSES = ('New', 'Pending', 'Approved')
# O que não é DADO da operação num PATCH: estado e carimbos.
_ND_GUARD_META = ('Status', 'Maker', 'Checker', '_client')


def _nd_edit_de_registrada(deal, upd, product):
    """O Save do modal de Edit numa linha JÁ ENVIADA (Sent/Success).

    O modal manda `Status: 'Pending'` junto com os campos, e a trava abaixo o
    recusava como `status_regression` — o 409 da aba velha. A tela não lia a
    resposta e dizia "Saved": a edição sumia no recarregamento (o "dá erro ou
    não faz nada" das Opt Comm na prod, 26/10/2026). Uma edição não é aba
    velha: é a régua do Amend da API (`_nd_api_amend`), a MESMA função —
    mudança ECONÔMICA devolve a operação à fila como `Amend` (de onde ela
    volta ao 4-olhos e à B3), mudança só cosmética mantém o status."""
    from apps.pages.platform import new_deals as _pf_nd
    dados = {k: v for k, v in upd.items() if k not in _ND_GUARD_META}
    antes = dict(deal or {})
    depois = dict(antes, **dados)
    mudou = [k for k, v in dados.items()
             if str(antes.get(k, '') or '').strip() != str(v or '').strip()]
    economico = any(_pf_nd._nd_amend_is_economic(
        k, str(antes.get(k, '') or '').strip(), str(dados[k] or '').strip(),
        antes, depois, product) for k in mudou)
    if economico:
        upd['Status'] = 'Amend'
        upd['AmendChanged'] = sorted(set(antes.get('AmendChanged') or []) | set(mudou))
    else:
        upd.pop('Status', None)
    return upd


def _nd_guard_updates(deal, updates, sid, product=''):
    """(updates saneados, código de recusa ou '').

    - `Maker`/`Checker` não-vazios são da SESSÃO (vazio segue vazio: limpar é
      permitido);
    - Pending → Approved pelo próprio Maker é `same_user` — a mesma trava do
      botão Confirm (New/Amend → Approved segue livre, §540);
    - Sent/Success não voltam a New/Pending/Approved (`status_regression`): é
      a aba aberta antes do envio gravando o status que ela ainda mostra. O
      `Amend` passa — é o caminho do dado econômico. A exceção é o Save do
      modal de Edit (`Pending` COM campos de dado): ele segue a régua do Amend
      (`_nd_edit_de_registrada`). `product` é a chave do `_GENERIC_ND_PRODUCTS`
      (o Strike do FWD Start é cosmético)."""
    sid = str(sid or '').strip()
    upd = dict(updates or {})
    for k in ('Maker', 'Checker'):
        if str(upd.get(k, '') or '').strip():
            upd[k] = sid
    novo = str(upd.get('Status', '') or '').strip()
    atual = str((deal or {}).get('Status', '') or '').strip()
    if novo and novo != atual:
        if atual in _ND_FINAL_STATUSES and novo in _ND_BACK_STATUSES:
            if novo == 'Pending' and any(k not in _ND_GUARD_META for k in upd):
                return _nd_edit_de_registrada(deal, upd, product), ''
            return None, 'status_regression'
        if novo == 'Approved' and atual == 'Pending':
            maker = str((deal or {}).get('Maker', '') or '').strip().upper()
            if _authz.is_own_change(maker, sid):
                return None, 'same_user'
    return upd, ''


_ND_GUARD_HTTP = {
    'same_user': (403, 'A different user must approve a deal you imported or last edited.'),
    'status_regression': (409, 'This deal was already sent — reload the page.'),
}


def _nd_guard_response(code):
    status, msg = _ND_GUARD_HTTP[code]
    return jsonify({'success': False, 'error': code, 'message': msg}), status


# ── O veredito sai da GRAVAÇÃO (26/10/2026, HANDOFF §685) ────────────────────
# As quatro famílias (Opt Comm, Opt FXO, NDF Comm e o NDF genérico) tinham cada
# uma a sua cópia de bulk-delete, bulk-patch, envio e mapping, e as quatro
# respondiam `success` dizendo só QUANTOS — a tela tirava da grade, pintava e
# anunciava tudo o que tinha pedido. Aqui a resposta diz O QUE: par a par o
# que foi feito, o que não foi achado e o que foi recusado, e a tela só mexe na
# linha que o servidor confirmou.

def _nd_par(deal, client):
    return (str(deal or '').strip(), str(client or '').strip())


def _nd_casa(d, deal, client):
    """A linha `d` é o (Deal, Client) pedido? Trim dos dois lados; `client`
    vazio casa qualquer cliente (o contrato do bulk-patch)."""
    if not isinstance(d, dict):
        return False
    if str(d.get('Deal') or '').strip() != deal:
        return False
    return not client or str(d.get('Client') or '').strip() == client


def _nd_le_dia(fp):
    """O arquivo-dia de quem vai GRAVAR, sob a trava: ocupado, ilegível ou
    corrompido SOBE. Lido como `[]`, a gravação seguinte escrevia o dia sem as
    outras linhas (CLAUDE.md §548)."""
    deals = _store.read(fp)
    return deals if isinstance(deals, list) else [deals]


def _nd_bulk_delete(finder, pairs, label):
    pares = []
    for p in pairs or []:
        t = _nd_par(p.get('deal'), p.get('client'))
        if t not in pares:
            pares.append(t)
    por_arquivo, nao_achados = {}, []
    for deal, client in pares:
        fp, _ = finder(deal, client)
        if fp:
            por_arquivo.setdefault(fp, []).append((deal, client))
        else:
            nao_achados.append((deal, client))
    apagados, feitos = 0, []
    for fp, alvo in por_arquivo.items():
        with _R()._cache_lock:
            deals = _nd_le_dia(fp)
            ficam, achou = [], set()
            for d in deals:
                t = _nd_par(d.get('Deal'), d.get('Client')) if isinstance(d, dict) else None
                if t in alvo:
                    achou.add(t)
                    continue
                ficam.append(d)
            if len(ficam) != len(deals):
                _R()._atomic_write_json(fp, ficam)
            apagados += len(deals) - len(ficam)
        feitos.extend(t for t in alvo if t in achou)
        nao_achados.extend(t for t in alvo if t not in achou)
    if apagados > 0:
        _R()._create_notification(
            session.get('user_sid', ''), session.get('user_name', ''), 'Bulk Delete', label,
            str(apagados) + ' deal' + ('s' if apagados != 1 else '') + ' deleted')
    return jsonify({'success': True, 'deleted': apagados,
                    'done': [{'deal': d, 'client': c} for d, c in feitos],
                    'not_found': [{'deal': d, 'client': c} for d, c in nao_achados]})


def _nd_bulk_patch(finder, patches, label, product='', ajusta=None, depois=None):
    """`ajusta(linha)` reordena a linha gravada (FXO); `depois(linha)` roda FORA
    da trava para cada linha que virou Success (Pending Confirmation)."""
    sid = session.get('user_sid', '')
    por_arquivo, nao_achados = {}, []
    for p in patches or []:
        deal, client = _nd_par(p.get('deal_id'), p.get('client'))
        upd = p.get('updates') or {}
        if not deal or not upd:
            nao_achados.append((deal, client))
            continue
        fp, _ = finder(deal, client)
        if fp:
            por_arquivo.setdefault(fp, []).append((deal, client, upd))
        else:
            nao_achados.append((deal, client))
    feitos, recusados, sucessos = [], [], []
    for fp, ops in por_arquivo.items():
        with _R()._cache_lock:
            deals = _nd_le_dia(fp)
            mudou = False
            for deal, client, upd in ops:
                idxs = [i for i, d in enumerate(deals) if _nd_casa(d, deal, client)]
                if not idxs:
                    nao_achados.append((deal, client))
                    continue
                for idx in idxs:
                    u, recusa = _nd_guard_updates(deals[idx], upd, sid, product)
                    if recusa:
                        recusados.append({'deal_id': deal, 'client': client, 'error': recusa})
                        continue
                    deals[idx].update(u)
                    if ajusta:
                        deals[idx] = ajusta(deals[idx])
                    mudou = True
                    feitos.append({'deal_id': deal, 'client': client,
                                   'status': deals[idx].get('Status', '')})
                    if str(u.get('Status', '')) == 'Success':
                        sucessos.append(deals[idx].copy())
            if mudou:
                _R()._atomic_write_json(fp, deals)
    if depois:
        for d in sucessos:
            depois(d)
    if feitos:
        _R()._create_notification(
            session.get('user_sid', ''), session.get('user_name', ''), 'Bulk Update', label,
            str(len(feitos)) + ' deal' + ('s' if len(feitos) != 1 else '') + ' updated')
    return jsonify({'success': True, 'updated': len(feitos), 'done': feitos,
                    'refused': recusados,
                    'not_found': [{'deal_id': d, 'client': c} for d, c in nao_achados]})


# O ENVIO à B3 confere no SERVIDOR e marca `Sent` no MESMO pedido. A tela
# mandava o arquivo e depois um PATCH solto (`.catch(console.warn)`): com o
# PATCH recusado ou o banco ocupado, o arquivo ia para a B3, a linha ficava
# `Approved` e o próximo Send registrava a operação DE NOVO. E o status que a
# tela conferia era o dela — uma linha que outro usuário editou (Pending no
# banco) ia ao arquivo sem a segunda aprovação.
_ND_ENVIAVEL = ('Approved', 'Error')


def _nd_conferir_envio(finder, deals, sid):
    """Recusas antes de qualquer arquivo: `[{deal, client, error, status}]`."""
    recusas = []
    for d in deals or []:
        if str(d.get('Status', '') or '').strip() == 'Canceled':
            continue                    # o gerador já pula; não é operação a marcar
        deal, client = _nd_par(d.get('Deal'), d.get('Client'))
        fp = finder(deal, client)[0] if deal else None
        linha = None
        if fp:
            linha = next((x for x in _nd_le_dia(fp) if _nd_casa(x, deal, client)), None)
        if linha is None:
            recusas.append({'deal': deal, 'client': client, 'error': 'not_found', 'status': ''})
            continue
        status = str(linha.get('Status', '') or '').strip()
        if status not in _ND_ENVIAVEL:
            recusas.append({'deal': deal, 'client': client, 'error': 'not_sendable',
                            'status': status})
        elif _authz.is_own_change(str(linha.get('Maker', '') or '').strip().upper(), sid):
            recusas.append({'deal': deal, 'client': client, 'error': 'same_user',
                            'status': status})
    return recusas


def _nd_recusa_envio(recusas):
    return jsonify({'ok': False, 'error': 'not_sendable', 'refused': recusas,
                    'message': 'Some deals cannot be sent — reload the page.'}), 409


def _nd_marcar_enviados(finder, deals, sid):
    """Depois do arquivo gravado: `Sent` + Checker em cada linha. Devolve
    (marcados, falhas) — a falha aqui é com o arquivo JÁ na pasta, e a tela tem
    de dizer que NÃO se reenvia."""
    por_arquivo, falhas = {}, []
    for d in deals or []:
        if str(d.get('Status', '') or '').strip() == 'Canceled':
            continue
        deal, client = _nd_par(d.get('Deal'), d.get('Client'))
        try:
            fp = finder(deal, client)[0] if deal else None
        except Exception as exc:                                # noqa: BLE001
            falhas.append({'deal': deal, 'client': client, 'reason': '%s: %s' % (type(exc).__name__, exc)})
            continue
        if fp:
            por_arquivo.setdefault(fp, []).append((deal, client))
        else:
            falhas.append({'deal': deal, 'client': client, 'reason': 'row_not_found'})
    marcados = []
    for fp, alvo in por_arquivo.items():
        try:
            with _R()._cache_lock:
                linhas = _nd_le_dia(fp)
                feitos = []
                for deal, client in alvo:
                    idxs = [i for i, x in enumerate(linhas) if _nd_casa(x, deal, client)]
                    for i in idxs:
                        linhas[i]['Status'] = 'Sent'
                        linhas[i]['Checker'] = sid
                    if idxs:
                        feitos.append((deal, client))
                    else:
                        falhas.append({'deal': deal, 'client': client, 'reason': 'row_not_found'})
                if feitos:
                    _R()._atomic_write_json(fp, linhas)
            marcados.extend({'deal': d, 'client': c} for d, c in feitos)
        except Exception as exc:                                # noqa: BLE001
            _R().log.exception('[SEND] arquivo gravado mas o status NAO: %s', fp)
            falhas.extend({'deal': d, 'client': c, 'reason': '%s: %s' % (type(exc).__name__, exc)}
                          for d, c in alvo)
    if falhas:
        _R().log.warning('[SEND] %d linha(s) foram para a B3 sem o status Sent gravado: %s',
                         len(falhas), falhas)
    return marcados, falhas


def _nd_apaga_retornos(linhas_por_arquivo, gravou, tag):
    """Apaga o arquivo de retorno só quando TODA linha do produto nele casou
    com uma operação desta passada E gravou — a regra que o Swap Bullet e a
    recompra já seguem. Apagado por "ter linha do produto", ele levava os B3 ID
    que esta passada não absorveu: retorno de ontem lido com a Reference Date
    de hoje (as candidatas são as do DIA), a gravação que falhou (`saved:
    false` dizia "tente de novo" com o arquivo já apagado) e, no OPC, as linhas
    da outra página de opção. O que fica é relido na próxima passada."""
    for fp, deals in linhas_por_arquivo.items():
        pendentes = [d for d in deals if not (d and gravou.get(d))]
        if pendentes:
            _R().log.warning('[MAPPING-B3 %s] retorno MANTIDO %s: %d linha(s) sem operação '
                             'gravada nesta passada', tag, os.path.basename(fp), len(pendentes))
            continue
        try:
            _store.remove(fp)
        except Exception:                                       # noqa: BLE001
            _R().log.warning('[MAPPING-B3 %s] não consegui apagar %s', tag, fp, exc_info=True)


@blueprint.route('/api/new-deals/opt-commodities/cache', methods=['POST'])
def api_save_deal_cache():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "No data provided"}), 400
    _R()._nd_fix_underlying_marker(data)

    # Use the deal's TradeDate (dd/mm/yyyy) for the directory; fall back to today
    trade_date_raw = data.get('TradeDate', '')
    try:
        ref_date = datetime.strptime(trade_date_raw, '%d/%m/%Y')
    except (ValueError, TypeError):
        ref_date = datetime.now()

    dir_path = os.path.join(
        _R().CACHE_BASE_DIR,
        ref_date.strftime('%Y'),
        ref_date.strftime('%m')
    )
    os.makedirs(dir_path, exist_ok=True)

    fname = ref_date.strftime('%Y%m%d') + '_optcomm.json'
    file_path = os.path.join(dir_path, fname)

    with _R()._cache_lock:
        if _store.exists(file_path):
            deals = _nd_le_dia(file_path)
        else:
            deals = []

        if data.get('_import'):
            return _import_resposta(deals, data, _R().CACHE_BASE_DIR, '_optcomm.json', file_path)
        deal_name   = data.get('Deal', '').strip()
        client_name = data.get('Client', '').strip()
        data.pop('_client', None)
        existing_idx = next((i for i, d in enumerate(deals)
                             if deal_name
                             and d.get('Deal', '').strip() == deal_name
                             and d.get('Client', '').strip() == client_name), None)
        if existing_idx is not None:
            # O Add Row não SUBSTITUI a operação já gravada (26/10/2026): o POST
            # trocava a linha inteira, e um Sent/Success voltava a Pending sem o
            # B3 ID. Quem atualiza uma linha existente é o PATCH (Edit) ou o
            # import (`_import`, acima).
            return jsonify({"success": False, "error": "deal_exists",
                            "message": "This deal is already saved — edit it instead."}), 409
        deals.append(data)
        target_idx = existing_idx if existing_idx is not None else len(deals) - 1
        for _k in ('Maker', 'Checker'):
            if _k in deals[target_idx]:
                deals[target_idx][_k] = deals[target_idx].pop(_k)
        _R()._atomic_write_json(file_path, deals)

    return jsonify({"success": True, "deal": data.get('Deal', '')})

@blueprint.route('/api/new-deals/opt-commodities/cache/search', methods=['POST'])
def api_search_deal_cache():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    body = request.get_json(silent=True) or {}
    filters = body.get('filters', [])

    # `_day_files` + `_day_json`: `os.scandir` (a listagem já traz mtime e
    # tamanho) e memo por arquivo, então a segunda busca não reabre o que não
    # mudou. A busca não tem intervalo de datas, então não há o que podar.
    # `strict`: dia que o banco não entrega (ocupado sem cópia em memória,
    # ilegível) SOBE — 503/500 com o motivo — em vez de sumir da tabela. Lida
    # como vazia, a busca respondia `success: true` sem as operações logo
    # depois de uma gravação mudar o carimbo do dia (30/09/2026).
    matched = []
    _dias = list(_R()._day_files(_R().CACHE_BASE_DIR, '_optcomm.json', strict=True))
    # UMA abertura de banco para todos os dias enumerados, em vez de
    # uma por dia: eles são tabelas do MESMO banco do produto (§4).
    _R()._day_prefetch(_dias)
    for fpath, _fname, mtime, size in _dias:
        for deal in _R()._day_json(fpath, mtime, size, strict=True):
            if _R()._deal_matches(deal, filters):
                matched.append(deal)

    return jsonify({"success": True, "deals": matched})

def _intrag_segue(family, antes, depois):
    """A linha da Intrag acompanha o PATCH que mudou o Trade Date ou o Deal
    (§701): a gravação da Intrag procura a linha só no dia de destino, e a do
    dia antigo ficava — a operação duas vezes na Intrag. Melhor esforço: a
    origem já gravou; a falha é DITA na tela (`mirrors`)."""
    try:
        _R()._intrag_engine()._intrag_follow_deal(family, antes, depois)
    except Exception as exc:                                # noqa: BLE001
        _R().log.warning('[ND PATCH] Intrag %s: a linha de %r não acompanhou:\n%s',
                         family, (depois or {}).get('Deal', ''), traceback.format_exc())
        _mirrors.falhou('intrag', (depois or {}).get('Deal', ''), exc)


@blueprint.route('/api/new-deals/opt-commodities/cache/<deal_id>', methods=['PATCH'])
def api_update_deal_cache(deal_id):
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    client  = request.args.get('client')
    updates = request.get_json(silent=True)
    if not updates:
        return jsonify({"success": False, "message": "No data provided"}), 400

    file_path, _ = _R()._find_deal_in_cache(deal_id, client)
    if file_path is None:
        return jsonify({"success": False, "message": "Deal not found"}), 404

    with _R()._cache_lock:
        deals = _nd_le_dia(file_path)
        idx = next((i for i, d in enumerate(deals)
                    if (d.get('Deal') or '').strip() == (deal_id or '').strip()
                    and (client is None or (d.get('Client', '') or '').strip() == (client or '').strip())), None)
        if idx is None:
            return jsonify({"success": False, "message": "Deal not found"}), 404
        updates.pop('_client', None)
        updates, _recusa = _nd_guard_updates(deals[idx], updates, session.get('user_sid', ''))
        if _recusa:
            return _nd_guard_response(_recusa)
        antes = dict(deals[idx])
        deals[idx].update(updates)
        for _k in ('Maker', 'Checker'):
            if _k in deals[idx]:
                deals[idx][_k] = deals[idx].pop(_k)
        _R()._atomic_write_json(file_path, deals)
        updated_deal = deals[idx].copy()

    # Mirror NDF: push to Intrag Option when Status→Success and the counterparty
    # is Banco J.P. Morgan (intragroup). External clients instead become a fresh
    # outstanding confirmation → Pending Confirmation (the manual-mapping twin of
    # the return-file scan trigger; _pc_save_from_deal skips internal legs itself).
    _intrag_segue('opt', antes, updated_deal)
    if str(updates.get('Status', '')) == 'Success':
        _R()._intrag_engine()._maybe_save_intrag_opt(updated_deal)
        _R()._pc_save_from_deal(updated_deal, 'OPTION COMM')     # → pending confirmation

    _fields = {k: v for k, v in updates.items() if k not in ('Maker', 'Checker', '_client')}
    if _fields:
        if 'Status' in _fields:
            # The 'Sent' transition is already announced by the 'Sent to B3'
            # notification emitted from send-conecta — skip the redundant
            # 'Status Updated' entry so the bell shows a single item per send.
            if str(_fields.get('Status', '')) != 'Sent':
                _R()._create_notification(
                    session.get('user_sid', ''), session.get('user_name', ''),
                    'Status Updated', 'Opt Comm',
                    deal_id + ' → ' + str(_fields.get('Status', '')) + _R()._nd_token(updated_deal.get('TradeDate'))
                )
        else:
            _R()._create_notification(
                session.get('user_sid', ''), session.get('user_name', ''),
                'Deal Updated', 'Opt Comm',
                deal_id + ' (' + ', '.join(_fields.keys()) + ')' + _R()._nd_token(updated_deal.get('TradeDate'))
            )
    return jsonify({"success": True, "status": updated_deal.get('Status', ''),
                    "b3_id": updated_deal.get('B3_ID', '')})

@blueprint.route('/api/new-deals/opt-commodities/cache/<deal_id>', methods=['DELETE'])
def api_delete_deal_cache(deal_id):
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    client = request.args.get('client')
    file_path, _ = _R()._find_deal_in_cache(deal_id, client)
    if file_path is None:
        return jsonify({"success": False, "message": "Deal not found"}), 404

    with _R()._cache_lock:
        deals = _nd_le_dia(file_path)
        idx = next((i for i, d in enumerate(deals)
                    if (d.get('Deal') or '').strip() == (deal_id or '').strip()
                    and (client is None or (d.get('Client', '') or '').strip() == (client or '').strip())), None)
        if idx is None:
            return jsonify({"success": False, "message": "Deal not found"}), 404
        removed = deals.pop(idx)
        _R()._atomic_write_json(file_path, deals)

    _R()._create_notification(
        session.get('user_sid', ''), session.get('user_name', ''),
        'Deal Deleted', 'Opt Comm', deal_id + _R()._nd_token((removed or {}).get('TradeDate'))
    )
    return jsonify({"success": True})

@blueprint.route('/api/new-deals/opt-commodities/cache/bulk-delete', methods=['POST'])
def api_bulk_delete_deal_cache():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    pairs = (request.get_json(silent=True) or {}).get('pairs', [])
    if not pairs:
        return jsonify({"success": False, "message": "No pairs provided"}), 400
    return _nd_bulk_delete(_R()._find_deal_in_cache, pairs, 'Opt Comm')

@blueprint.route('/api/new-deals/opt-commodities/cache/bulk-patch', methods=['POST'])
def api_opt_bulk_patch_deal_cache():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    patches = (request.get_json(silent=True) or {}).get('patches', [])
    if not patches:
        return jsonify({"success": False, "message": "No patches provided"}), 400
    return _nd_bulk_patch(_R()._find_deal_in_cache, patches, 'Opt Comm')

@blueprint.route('/api/new-deals/opt-fxo/cache', methods=['POST'])
def api_save_fxo_cache():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "No data provided"}), 400

    trade_date_raw = data.get('TradeDate', '')
    try:
        ref_date = datetime.strptime(trade_date_raw, '%d/%m/%Y')
    except (ValueError, TypeError):
        ref_date = datetime.now()

    dir_path = os.path.join(_R().OPT_FXO_CACHE_DIR, ref_date.strftime('%Y'), ref_date.strftime('%m'))
    os.makedirs(dir_path, exist_ok=True)
    file_path = os.path.join(dir_path, ref_date.strftime('%Y%m%d') + '_optfxo.json')

    with _R()._cache_lock:
        if _store.exists(file_path):
            deals = _nd_le_dia(file_path)
        else:
            deals = []

        deal_name   = data.get('Deal', '').strip()
        client_name = data.get('Client', '').strip()
        data.pop('_client', None)
        existing_idx = next((i for i, d in enumerate(deals)
                             if deal_name
                             and d.get('Deal', '').strip() == deal_name
                             and d.get('Client', '').strip() == client_name), None)
        # Persist in table-column order (Maker/Checker last) — not alphabetical.
        if existing_idx is not None:
            # O Add Row não SUBSTITUI a operação já gravada (26/10/2026): o POST
            # trocava a linha inteira, e um Sent/Success voltava a Pending sem o
            # B3 ID. Quem atualiza uma linha existente é o PATCH (Edit) ou o
            # import (`_import`, acima).
            return jsonify({"success": False, "error": "deal_exists",
                            "message": "This deal is already saved — edit it instead."}), 409
        deals.append(_R()._fxo_order_deal(data))
        _R()._atomic_write_json(file_path, deals)

    return jsonify({"success": True, "deal": data.get('Deal', '')})

@blueprint.route('/api/new-deals/opt-fxo/cache/search', methods=['POST'])
def api_search_fxo_cache():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    body = request.get_json(silent=True) or {}
    filters = body.get('filters', [])
    # `_day_files` + `_day_json`: `os.scandir` (a listagem já traz mtime e
    # tamanho) e memo por arquivo, então a segunda busca não reabre o que não
    # mudou. A busca não tem intervalo de datas, então não há o que podar.
    matched = []
    _dias = list(_R()._day_files(_R().OPT_FXO_CACHE_DIR, '_optfxo.json', strict=True))
    # UMA abertura de banco para todos os dias enumerados, em vez de
    # uma por dia: eles são tabelas do MESMO banco do produto (§4).
    _R()._day_prefetch(_dias)
    for fpath, _fname, mtime, size in _dias:
        for deal in _R()._day_json(fpath, mtime, size, strict=True):
            if _R()._deal_matches(deal, filters):
                matched.append(deal)
    return jsonify({"success": True, "deals": matched})

@blueprint.route('/api/new-deals/opt-fxo/cache/<deal_id>', methods=['PATCH'])
def api_update_fxo_cache(deal_id):
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    client  = request.args.get('client')
    updates = request.get_json(silent=True)
    if not updates:
        return jsonify({"success": False, "message": "No data provided"}), 400

    file_path, _ = _R()._find_fxo(deal_id, client)
    if file_path is None:
        return jsonify({"success": False, "message": "Deal not found"}), 404

    with _R()._cache_lock:
        deals = _nd_le_dia(file_path)
        idx = next((i for i, d in enumerate(deals)
                    if (d.get('Deal') or '').strip() == (deal_id or '').strip()
                    and (client is None or (d.get('Client', '') or '').strip() == (client or '').strip())), None)
        if idx is None:
            return jsonify({"success": False, "message": "Deal not found"}), 404
        updates.pop('_client', None)
        updates, _recusa = _nd_guard_updates(deals[idx], updates, session.get('user_sid', ''))
        if _recusa:
            return _nd_guard_response(_recusa)
        antes = dict(deals[idx])
        deals[idx].update(updates)
        # Rewrite in table-column order (Maker/Checker last) — not alphabetical.
        deals[idx] = _R()._fxo_order_deal(deals[idx])
        _R()._atomic_write_json(file_path, deals)
        updated_deal = deals[idx].copy()

    # Mirror opt-comm: push to Intrag Option (FXO overrides) when Status→Success
    # and the counterparty is Banco J.P. Morgan (intragroup). External clients
    # instead flow to Pending Confirmation (manual-mapping twin of the return-file
    # scan trigger; _pc_save_from_deal skips internal legs itself).
    _intrag_segue('opt', antes, updated_deal)
    if str(updates.get('Status', '')) == 'Success':
        _R()._intrag_engine()._maybe_save_intrag_fxo(updated_deal)
        _R()._pc_save_from_deal(updated_deal, 'OPTION')          # → pending confirmation

    _fields = {k: v for k, v in updates.items() if k not in ('Maker', 'Checker', '_client')}
    if _fields:
        if 'Status' in _fields:
            if str(_fields.get('Status', '')) != 'Sent':
                _R()._create_notification(
                    session.get('user_sid', ''), session.get('user_name', ''),
                    'Status Updated', 'Opt FXO',
                    deal_id + ' → ' + str(_fields.get('Status', '')) + _R()._nd_token(updated_deal.get('TradeDate'))
                )
        else:
            _R()._create_notification(
                session.get('user_sid', ''), session.get('user_name', ''),
                'Deal Updated', 'Opt FXO',
                deal_id + ' (' + ', '.join(_fields.keys()) + ')' + _R()._nd_token(updated_deal.get('TradeDate'))
            )
    return jsonify({"success": True, "status": updated_deal.get('Status', ''),
                    "b3_id": updated_deal.get('B3_ID', '')})

@blueprint.route('/api/new-deals/opt-fxo/cache/<deal_id>', methods=['DELETE'])
def api_delete_fxo_cache(deal_id):
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    client = request.args.get('client')
    file_path, _ = _R()._find_fxo(deal_id, client)
    if file_path is None:
        return jsonify({"success": False, "message": "Deal not found"}), 404

    with _R()._cache_lock:
        deals = _nd_le_dia(file_path)
        idx = next((i for i, d in enumerate(deals)
                    if (d.get('Deal') or '').strip() == (deal_id or '').strip()
                    and (client is None or (d.get('Client', '') or '').strip() == (client or '').strip())), None)
        if idx is None:
            return jsonify({"success": False, "message": "Deal not found"}), 404
        removed = deals.pop(idx)
        _R()._atomic_write_json(file_path, deals)

    _R()._create_notification(
        session.get('user_sid', ''), session.get('user_name', ''),
        'Deal Deleted', 'Opt FXO', deal_id + _R()._nd_token((removed or {}).get('TradeDate'))
    )
    return jsonify({"success": True})

@blueprint.route('/api/new-deals/opt-fxo/cache/bulk-delete', methods=['POST'])
def api_bulk_delete_fxo_cache():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    pairs = (request.get_json(silent=True) or {}).get('pairs', [])
    if not pairs:
        return jsonify({"success": False, "message": "No pairs provided"}), 400
    return _nd_bulk_delete(_R()._find_fxo, pairs, 'Opt FXO')

@blueprint.route('/api/new-deals/opt-fxo/cache/bulk-patch', methods=['POST'])
def api_fxo_bulk_patch_deal_cache():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    patches = (request.get_json(silent=True) or {}).get('patches', [])
    if not patches:
        return jsonify({"success": False, "message": "No patches provided"}), 400
    return _nd_bulk_patch(_R()._find_fxo, patches, 'Opt FXO',
                          ajusta=lambda d: _R()._fxo_order_deal(d))

@blueprint.route('/api/new-deals/opt-fxo/import-api', methods=['POST'])
def api_fxo_import_api():
    """Manual trigger of the Athena FXO pull (Import button, empty dropzone).
    `ref_date` = campo Reference Date da página (default hoje)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    try:
        result = _R()._fxo_api_pull(sid=session.get('user_sid', '') or 'API',
                               actor_name=session.get('user_name', '') or 'Athena API',
                               ref_date=(request.get_json(silent=True) or {}).get('ref_date'))
    except Exception as e:                              # noqa: BLE001
        _R().log.warning('[opt-fxo] manual Athena API import failed: %s', e)
        return jsonify({'success': False, 'message': str(e)}), 502
    return jsonify(result)

@blueprint.route('/api/new-deals/ndf/import-api', methods=['POST'])
def api_ndf_import_api():
    """Manual trigger of the Athena NDF pull (Import button, empty dropzone,
    on the FWD Start / Other Publisher / Vanilla pages). `ref_date` = campo
    Reference Date da página (default hoje)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    try:
        result = _R()._ndf_api_pull(sid=session.get('user_sid', '') or 'API',
                               actor_name=session.get('user_name', '') or 'Athena API',
                               ref_date=(request.get_json(silent=True) or {}).get('ref_date'))
    except Exception as e:                              # noqa: BLE001
        _R().log.warning('[ndf] manual Athena API import failed: %s', e)
        return jsonify({'success': False, 'message': str(e)}), 502
    return jsonify(result)

@blueprint.route('/api/new-deals/opt-fxo/cache/batch', methods=['POST'])
def api_fxo_cache_batch():
    """Persist a finalized list of FXO deals (after the page resolves duplicates)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    data = request.get_json(silent=True) or {}
    deals = data.get('deals', [])
    if not deals:
        return jsonify({'success': True, 'imported': 0})
    saved = _R()._fxo_persist_deals(deals)
    if saved:
        _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                             'New Deals', 'Opt FXO',
                             '{} deal{} imported from XLSX'.format(saved, '' if saved == 1 else 's'))
    return jsonify({'success': True, 'imported': saved})

@blueprint.route('/api/new-deals/opt-fxo/import-xlsx', methods=['POST'])
def api_fxo_import_xlsx():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    import openpyxl

    files = request.files.getlist('files')
    if not files and 'file' in request.files:
        files = [request.files['file']]
    if not files:
        return jsonify({'success': False, 'message': 'no_file'}), 400

    sid = session.get('user_sid', '') or ''
    refmap = _R()._fxo_refdata_by_spn()
    refmap_acr = _R()._fxo_refdata_by_accronym(refmap)
    deals, errors = [], []

    for f in files:
        if not f or not (f.filename or '').lower().endswith('.xlsx'):
            continue
        try:
            wb = openpyxl.load_workbook(io.BytesIO(f.read()), read_only=True, data_only=True)
        except Exception as e:                       # noqa: BLE001
            errors.append('{}: {}'.format(f.filename, e))
            continue
        ws = wb.active
        it = ws.iter_rows(values_only=True)
        try:
            header = next(it)
        except StopIteration:
            wb.close()
            continue

        col = {}
        for i, h in enumerate(header):
            n = re.sub(r'[\s_]+', ' ', str(h or '').strip().upper())
            if n and n not in col:
                col[n] = i

        def g(row, name):
            i = col.get(name)
            return row[i] if (i is not None and i < len(row)) else None

        for r in it:
            if r is None:
                continue
            deal = _R()._fxo_deal_from_row(lambda name: g(r, name), sid, refmap, refmap_acr)
            if deal:
                deals.append(deal)
        wb.close()

    # dry_run=1 → parse only (the page first checks Deal+Client duplicates against
    # the table and asks the user before persisting via /cache/batch).
    dry_run = (request.args.get('dry_run') in ('1', 'true', 'yes')
               or (request.form.get('dry_run') in ('1', 'true', 'yes')))
    saved = 0
    if not dry_run:
        saved = _R()._fxo_persist_deals(deals)
        if saved:
            _R()._create_notification(sid, session.get('user_name', ''),
                                 'New Deals', 'Opt FXO',
                                 '{} deal{} imported from XLSX'.format(saved, '' if saved == 1 else 's'))
    return jsonify({'success': True, 'imported': saved, 'deals': deals, 'errors': errors})

def _opc_default_name(prefix, view):
    """O nome padrão do arquivo OPC de uma visão — `FXO_Banco.txt`,
    `FXO_Lawton.txt` — quando a variante do cadastro não dá um."""
    return '{}_{}.txt'.format(prefix, 'Banco' if view == 'JPM' else view.title())


@blueprint.route('/api/new-deals/opt-fxo/send-conecta', methods=['POST'])
def api_fxo_send_conecta():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    """B3 Conecta file for FXO. Same layout as opt-commodities with the FXO tweaks
    (all in the File Interface template 'opcoes-flexiveis-vcp', page overrides):
    Tipo Indicador (seq 3)='4', Tipo de Cotação (seq 18)='1' (an older docstring
    said '2', but production always wrote '1' — the cadastro documents the real byte),
    'Data de fixing do ativo subjacente' (seq 20) = last fixing date when VANILLA
    (blank ASIAN), 'Data de fixing da moeda do ativo subjacente' (seq 21) always
    blank. Asian fixing-date count uses the ANBIMA calendar (FXHolidaySchedule).
    A montagem das linhas é do cadastro (_fi_build_line): ordem, larguras e
    literais Fixed saem do template; aqui ficam só os valores calculados."""
    from decimal import Decimal
    import datetime as _dt
    import json as _json

    data  = request.get_json(silent=True) or {}
    deals = data.get('deals', [])
    download = bool(data.get('download'))   # preview: devolve o conteúdo, não grava
    if not deals:
        return jsonify({'ok': False, 'error': 'No deals provided'}), 400
    if not download:
        # status e 4-olhos conferidos no SERVIDOR antes do arquivo (§685)
        _recusas = _nd_conferir_envio(_R()._find_fxo, deals, session.get('user_sid', ''))
        if _recusas:
            return _nd_recusa_envio(_recusas)

    # O cadastro é a autoridade da linha: sem template (ou sem os blocos), o
    # arquivo NÃO sai meio montado — erro claro pedindo o /file-interpreter.
    _tpl = _R()._fi_tpl_cached('opcoes-flexiveis-vcp')
    if _tpl is None or not {'header', 'registro', 'registro-media-asiatica'} <= {
            b.get('id') for b in _tpl.get('blocks', [])}:
        return jsonify({'ok': False, 'error': 'File Interpreter template missing/invalid '
                                              '— check /file-interpreter (opcoes-flexiveis-vcp)'}), 500

    today = _dt.datetime.today().strftime('%Y%m%d')

    def _sh(v):
        return re.sub(r'<[^>]+>', '', str(v or '')).strip()

    def _date(val):
        val = _sh(val)
        if not val:
            return ''
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y'):
            try:
                return _dt.datetime.strptime(val, fmt).strftime('%Y%m%d')
            except ValueError:
                continue
        return ''

    def _num(val, div100=False):
        val = _sh(str(val or ''))
        if not val:
            return ''
        clean = val.replace(',', '')
        try:
            d = Decimal(clean)
            if div100:
                d = d / Decimal('100')
            return format(d.normalize(), 'f').replace('.', ',')
        except Exception:
            return clean.replace('.', ',')

    def _qty(val):
        v = _sh(str(val or ''))
        if not v:
            return ''
        try:
            return str(int(round(float(v.replace(',', ''))))) + ',00'
        except Exception:
            return v

    def _cli(client):
        c = client.upper()
        if 'LAWTON' in c:
            return '73760009'
        if 'BANCO J.P MORGAN' in c or 'JP MORGAN' in c:
            return '00041007'
        return '73760009'

    def _cpty(client):
        c = client.upper()
        if 'LAWTON' in c:
            return '00041007'
        if 'BANCO J.P MORGAN' in c or 'JP MORGAN' in c:
            return '73760009'
        return '73760102'

    def _taxid(client, taxid):
        c = client.upper()
        if 'LAWTON' in c or 'BANCO J.P MORGAN' in c or 'JP MORGAN' in c:
            return ''
        return re.sub(r'[.\-/]', '', _sh(taxid))

    deal_count = 0
    # Um destino por ARQUIVO: o padrão é FXO_Banco.txt, e a variante do
    # template (pelo par de pernas do deal) pode cadastrar outro nome.
    out_files  = {}

    for deal in deals:
        # No download (preview) o status não importa — baixa até cancelado.
        if not download and str(deal.get('Status', '') or '').strip() == 'Canceled':
            continue                    # cancelado via API: fora dos arquivos
        client     = _sh(deal.get('Client', ''))
        taxid      = _sh(deal.get('TaxID', ''))
        instrument = _sh(deal.get('Instrument', ''))
        direction  = _sh(deal.get('Direction', ''))
        trade_type       = _sh(deal.get('TradeType', ''))
        strike_ccy       = _sh(deal.get('StrikeCurrency', ''))
        fx_holiday_sched = _sh(deal.get('FXHolidaySchedule', '')) or 'anbima'
        vanilla          = trade_type.upper() == 'VANILLA'
        asian            = trade_type.upper() == 'ASIAN'
        brl              = strike_ccy.upper() == 'BRL'

        opt = 'P' if 'PUT' in instrument.upper() else ('C' if 'CALL' in instrument.upper() else '')
        dir_code  = '2' if direction.upper() == 'SELL' else '1'
        fix_start = _date(deal.get('FixingStartDate', ''))
        fix_end   = _date(deal.get('FixingEndDate', ''))

        # ANBIMA calendar (file name is case-insensitive on the FS we run on)
        _deal_holidays = set()
        if not vanilla and fx_holiday_sched:
            # Strip anything but word chars so a crafted FXHolidaySchedule
            # (e.g. '../../secret') can't escape the data dir (path traversal).
            _sched_file = re.sub(r'[^A-Za-z0-9_]', '', fx_holiday_sched.replace('-', '_').lower())
            holiday_path = os.path.join(_R()._B3_DATA_DIR, '{}.json'.format(_sched_file)) if _sched_file else None
            try:
                # DB-first (fase 3): o schedule é um calendário do registro.
                from apps.pages import duck_read
                _raw = duck_read.calendar_rows(holiday_path)
                if _raw is None:
                    _raw = _store.read(holiday_path)
                _deal_holidays = set(item['date'] if isinstance(item, dict) else item for item in _raw)
            except Exception:
                pass

        _biz = 0
        if not vanilla and fix_start and fix_end:
            try:
                _s = _dt.datetime.strptime(fix_start, '%Y%m%d').date()
                _e = _dt.datetime.strptime(fix_end, '%Y%m%d').date()
                _cur = _s
                while _cur <= _e:
                    if _cur.weekday() < 5 and _cur.strftime('%Y-%m-%d') not in _deal_holidays:
                        _biz += 1
                    _cur += _dt.timedelta(days=1)
            except Exception:
                pass

        # Só os campos não-Fixed, por seq do cadastro; os literais ('OPC  00002',
        # Tipo Indicador '4', Tipo de Cotação '1', Tipo de Exercício '2'…)
        # saem do template — byte a byte o que sempre foi enviado.
        trade_date = _date(deal.get('TradeDate', ''))
        _spot_date = _date(deal.get('SpotDate', ''))
        _is_bank_or_lawton = ('LAWTON' in client.upper() or 'BANCO J.P MORGAN' in client.upper()
                              or 'JP MORGAN' in client.upper())
        vals = {
            '4':  _cli(client),
            '5':  dir_code,
            '7':  _cpty(client),
            '8':  _taxid(client, taxid),
            '9':  opt,
            '10': trade_date,
            '11': _date(deal.get('SettlementDate', '')),
            '12': _sh(deal.get('UnderlyingAsset', '')),
            '13': _qty(deal.get('TotalNotional', '')),
            '14': _num(deal.get('Strike', '')),
            '19': 'S' if brl else '',
            '20': fix_end if vanilla else '',         # FXO: fixing do ativo = last fixing (VANILLA)
            '24': str(_R().random.randint(1000000000, 9999999999)),
            '25': _sh(deal.get('Deal', '')),
            '27': _num(deal.get('PremiumPerUnit', '')),
            '29': ('2' if trade_date == _spot_date else '3') if _is_bank_or_lawton else '1',
            '33': _spot_date,
            '48': '' if vanilla else '1',
            '49': '0' if vanilla else (str(_biz) if _biz else ''),
        }

        # Par de pernas → variante do template (Fixed das contas por par);
        # sem variante, o base — byte a byte o de sempre.
        # O arquivo é UM por visão (a perna da esquerda do par): com a conta da
        # visão no nome do arquivo (§646), a linha do Lawton não divide mais o
        # FXO_Banco.txt com as do Banco.
        le_pair = _R()._opc_le_pair(client)
        view = _R()._b3_view_le(le_pair)
        fname = (_R()._fi_variant_file_name('opcoes-flexiveis-vcp', '/new_deals-opt-fxo', le_pair)
                 or _opc_default_name('FXO', view))
        dest = out_files.setdefault((view, fname), [])

        deal_count += 1
        dest.append(_R()._fi_build_line('opcoes-flexiveis-vcp', 'registro', vals,
                                   page_url='/new_deals-opt-fxo', le_pair=le_pair,
                                   deal=deal))

        # Asian — one fixing line (line type 2) per business day in the window
        if asian and fix_start and fix_end:
            try:
                _s2 = _dt.datetime.strptime(fix_start, '%Y%m%d').date()
                _e2 = _dt.datetime.strptime(fix_end, '%Y%m%d').date()
            except Exception:
                _s2 = _e2 = None
            _cur2 = _s2
            while _s2 and _cur2 <= _e2:
                if _cur2.weekday() < 5 and _cur2.strftime('%Y-%m-%d') not in _deal_holidays:
                    dest.append(_R()._fi_build_line(
                        'opcoes-flexiveis-vcp', 'registro-media-asiatica',
                        {'3': _cur2.strftime('%Y%m%d')}, page_url='/new_deals-opt-fxo',
                        le_pair=le_pair, deal=deal))
                _cur2 += _dt.timedelta(days=1)

    # O header do OPC não depende do par (participante Fixed no template + a
    # data): o mesmo header abre todos os arquivos.
    header = _R()._fi_build_line('opcoes-flexiveis-vcp', 'header', {'4': today},
                            page_url='/new_deals-opt-fxo')
    if not out_files:
        out_files[('JPM', 'FXO_Banco.txt')] = []   # lote só de cancelados: header, como sempre

    try:
        if download:
            files = [{'filename': fname, 'content': '\n'.join([header] + lines)}
                     for (view, fname), lines in out_files.items()]
            return jsonify({'ok': True, 'count': deal_count, 'files': files,
                            'filename': files[0]['filename'] if files else ''})
        # Os nomes na New (com a conta da visão) ANTES do primeiro arquivo:
        # visão sem conta cadastrada recusa o lote inteiro.
        nomes = {k: _R()._conecta_file_name(*k) for k in out_files}
        os.makedirs(_R().CONECTA_NEW_PATH, exist_ok=True)
        generated = []
        for k, lines in out_files.items():
            filepath = _R()._unique_filepath(_R().CONECTA_NEW_PATH, nomes[k])
            with open(filepath, 'w', encoding='utf-8') as fh:
                fh.write('\n'.join([header] + lines))
            generated.append(os.path.basename(filepath))
        if deal_count > 0:
            _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                                 'Sent to B3', 'Opt FXO',
                                 str(deal_count) + ' deal' + ('' if deal_count == 1 else 's') + ' sent')
        # o arquivo JÁ está na pasta: o `Sent` vai no mesmo pedido (§685)
        _marcados, _falhas = _nd_marcar_enviados(_R()._find_fxo, deals, session.get('user_sid', ''))
        return jsonify({'ok': True, 'filename': generated[0] if generated else '',
                        'count': deal_count, 'files': generated,
                        'marked': _marcados, 'status_failed': _falhas})
    except Exception as exc:                          # noqa: BLE001
        return jsonify({'ok': False, 'error': str(exc)}), 500

def _e_antecipacao(linha):
    """A linha do retorno ecoa uma ANTECIPACAO (`TER  1` + `0014`) — a recompra
    (§587), que tem Mapping proprio nas telas de Unwinds. A regra e a de
    `unwinds.domain.e_antecipacao`; feature nao importa feature."""
    parts = str(linha or '').split(';', 4)
    if len(parts) < 5:
        return False
    r = parts[4].lstrip()
    return r[5:6] == '1' and r[6:10] == '0014'


@blueprint.route('/api/new-deals/opt-fxo/mapping-b3', methods=['POST'])
def api_fxo_mapping_b3():
    """Same B3-ID mapping as opt-commodities (Conecta return files carry 'OPC'
    option lines), but resolves deals in the _optfxo.json cache."""
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401

    data = request.get_json(silent=True) or {}
    sent_deals = data.get('deals', [])
    if not sent_deals:
        return jsonify({'ok': True, 'results': []})

    mapping = {}
    linhas_por_arquivo = {}   # arquivo → Deal de cada linha OPC tipo 1
    try:
        if not _store.isdir(_R().RETURN_PATH):
            return jsonify({'ok': False, 'error': 'Return folder not found: {}'.format(_R().RETURN_PATH)}), 400
        for fname in _store.listdir(_R().RETURN_PATH):
            fpath = os.path.join(_R().RETURN_PATH, fname)
            if not _store.isfile(fpath):
                continue
            try:
                with open(fpath, encoding='utf-8', errors='replace') as fh:
                    lines = fh.readlines()
                donos = []
                for line in lines[1:]:
                    line = line.strip()
                    if not line or line[56:59] != 'OPC':
                        continue
                    parts = line.split(';')
                    if len(parts) < 5:
                        continue
                    b3_id       = parts[1].strip()
                    status_text = parts[3].strip()
                    pipe_parts  = parts[4].strip().split('|')
                    if len(pipe_parts) < 25 or pipe_parts[1].strip() != '1':
                        continue
                    deal_text = pipe_parts[24].strip()
                    if not deal_text:
                        continue
                    donos.append(deal_text)
                    is_ok = (status_text == 'EXECUCAO OK')
                    if deal_text not in mapping or (is_ok and not mapping[deal_text]['ok']):
                        mapping[deal_text] = {'b3_id': b3_id, 'ok': is_ok}
                if donos:
                    linhas_por_arquivo[fpath] = donos
            except Exception:
                continue
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500

    results = []
    gravou = {}
    for sent in sent_deals:
        deal_text   = sent.get('Deal', '')
        client_name = sent.get('Client', '')
        if not deal_text or deal_text not in mapping:
            continue
        info       = mapping[deal_text]
        new_status = 'Success' if info['ok'] else 'Error'
        updates    = {'Status': new_status}
        if info['ok']:
            updates['B3_ID'] = info['b3_id']

        gravado, linha, motivo = _grava_mapeamento(
            _R()._find_fxo, deal_text, client_name, updates)
        gravou[deal_text] = gravou.get(deal_text, True) and gravado

        intrag_candidate = linha if (gravado and new_status == 'Success') else None
        if intrag_candidate is not None:
            _R()._intrag_engine()._maybe_save_intrag_fxo(intrag_candidate)
            _R()._pc_save_from_deal(intrag_candidate, 'OPTION')      # → pending confirmation

        results.append({
            'id':     deal_text,
            'deal':   deal_text,
            'b3_id':  (info['b3_id'] if info['ok'] else '') if gravado else '',
            'status': new_status if gravado else MAPPING_NAO_GRAVADO,
            'saved':  gravado,
            'reason': motivo,
        })

    # Deal da outra página de opção (o OPC é dos dois) ou de outro dia fica
    # sem dono aqui, e o retorno fica para quem o absorve (_nd_apaga_retornos)
    _nd_apaga_retornos(linhas_por_arquivo, gravou, 'Opt FXO')

    # O sino conta o que FICOU GRAVADO, não o que se tentou: escrito
    # `len(results)`, ele anunciava para a mesa inteira um número que
    # inclui o mapeamento que não chegou ao banco.
    _n_gravados = sum(1 for r in results if r.get('saved'))
    if _n_gravados:
        _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                             'B3 Mapped', 'Opt FXO',
                             str(_n_gravados) + ' deal' + ('' if _n_gravados == 1 else 's') + ' mapped')
    return jsonify({'ok': True, 'results': results})

@blueprint.route('/api/new-deals/ndf-commodities/cache', methods=['POST'])
def api_ndf_save_deal_cache():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "No data provided"}), 400
    _R()._nd_fix_underlying_marker(data)

    trade_date_raw = data.get('TradeDate', '')
    try:
        ref_date = datetime.strptime(trade_date_raw, '%d/%m/%Y')
    except (ValueError, TypeError):
        ref_date = datetime.now()

    dir_path = os.path.join(_R().NDF_COMM_CACHE_DIR, ref_date.strftime('%Y'), ref_date.strftime('%m'))
    os.makedirs(dir_path, exist_ok=True)

    fname = ref_date.strftime('%Y%m%d') + '_ndfcomm.json'
    file_path = os.path.join(dir_path, fname)

    with _R()._cache_lock:
        if _store.exists(file_path):
            deals = _nd_le_dia(file_path)
        else:
            deals = []

        if data.get('_import'):
            return _import_resposta(deals, data, _R().NDF_COMM_CACHE_DIR, '_ndfcomm.json', file_path)
        deal_name   = data.get('Deal', '').strip()
        client_name = data.get('Client', '').strip()
        existing_idx = next((i for i, d in enumerate(deals)
                             if deal_name
                             and d.get('Deal', '').strip() == deal_name
                             and d.get('Client', '').strip() == client_name), None)
        if existing_idx is not None:
            # O Add Row não SUBSTITUI a operação já gravada (26/10/2026): o POST
            # trocava a linha inteira, e um Sent/Success voltava a Pending sem o
            # B3 ID. Quem atualiza uma linha existente é o PATCH (Edit) ou o
            # import (`_import`, acima).
            return jsonify({"success": False, "error": "deal_exists",
                            "message": "This deal is already saved — edit it instead."}), 409
        deals.append(data)

        _R()._atomic_write_json(file_path, deals)

    # When used as the manual-edit fallback (PATCH 404 → upsert), ?notify=1 makes
    # the row-level edit produce the same bell notification a PATCH would.
    if request.args.get('notify') and deal_name:
        _R()._create_notification(
            session.get('user_sid', ''), session.get('user_name', ''),
            'Deal Updated', 'NDF Comm',
            deal_name + (' / ' + client_name if client_name else '') + _R()._nd_token(data.get('TradeDate')))

    return jsonify({"success": True, "deal": data.get('Deal', '')})

@blueprint.route('/api/new-deals/ndf-commodities/cache/search', methods=['POST'])
def api_ndf_search_deal_cache():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    body = request.get_json(silent=True) or {}
    filters = body.get('filters', [])

    # `_day_files` + `_day_json`: `os.scandir` (a listagem já traz mtime e
    # tamanho) e memo por arquivo, então a segunda busca não reabre o que não
    # mudou. A busca não tem intervalo de datas, então não há o que podar.
    matched = []
    _dias = list(_R()._day_files(_R().NDF_COMM_CACHE_DIR, '_ndfcomm.json', strict=True))
    # UMA abertura de banco para todos os dias enumerados, em vez de
    # uma por dia: eles são tabelas do MESMO banco do produto (§4).
    _R()._day_prefetch(_dias)
    for fpath, _fname, mtime, size in _dias:
        for deal in _R()._day_json(fpath, mtime, size, strict=True):
            if _R()._deal_matches(deal, filters):
                matched.append(deal)

    return jsonify({"success": True, "deals": matched})

@blueprint.route('/api/new-deals/ndf-commodities/cache/<deal_id>', methods=['PATCH'])
def api_ndf_update_deal_cache(deal_id):
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    client  = request.args.get('client')
    updates = request.get_json(silent=True)
    _R().log.info("[NDF PATCH] deal_id=%r client=%r updates=%s", deal_id, client, updates)

    if not updates:
        _R().log.warning("[NDF PATCH] No JSON body received")
        return jsonify({"success": False, "message": "No data provided"}), 400

    file_path, idx_found = _R()._find_ndf_deal_in_cache(deal_id, client)
    # O caminho é o ENDEREÇO do arquivo-dia — é por ele que tudo é chaveado —,
    # não a fonte da leitura: o finder varre pelo funil `_day_json`, que é
    # DB-only. Escrever só `file=<...>.json` num app cuja leitura sai do banco
    # se lê como "continua lendo JSON", e foi assim que este log virou alarme
    # falso em 09/09/2026. O `open` mais abaixo é a GRAVAÇÃO (§4, fase 3: o
    # read-modify-write da escrita segue no JSON de propósito).
    _R().log.info("[NDF PATCH] _find_ndf_deal_in_cache → arquivo-dia=%s idx=%s "
                  "(busca pelo BANCO; o JSON é o meio de gravação)",
                  file_path, idx_found)

    if file_path is None:
        # _find_ndf_deal_in_cache already emitted the detailed diagnosis (repr diffs, client mismatch list)
        _R().log.warning("[NDF PATCH] 404 — deal_id=%r (repr=%r) client=%r (repr=%r)",
                    deal_id, repr(deal_id), client, repr(client))
        return jsonify({"success": False, "message": "Deal not found"}), 404

    with _R()._cache_lock:
        deals = _nd_le_dia(file_path)
        idx = next((i for i, d in enumerate(deals)
                    if (d.get('Deal') or '').strip() == (deal_id or '').strip()
                    and (client is None or (d.get('Client', '') or '').strip() == (client or '').strip())), None)
        _R().log.debug("[NDF PATCH] idx in loaded file=%s", idx)
        if idx is None:
            _R().log.warning("[NDF PATCH] 404 — deal found in file scan but not after reload. deal_id=%r client=%r file=%s", deal_id, client, file_path)
            return jsonify({"success": False, "message": "Deal not found"}), 404
        prev_status = deals[idx].get('Status', '?')
        updates, _recusa = _nd_guard_updates(deals[idx], updates, session.get('user_sid', ''))
        if _recusa:
            return _nd_guard_response(_recusa)
        antes = dict(deals[idx])
        deals[idx].update(updates)
        _R().log.info("[NDF PATCH] Updated deal[%d] %r: Status %r→%r updates=%s",
                 idx, deal_id, prev_status, deals[idx].get('Status', '?'), updates)
        _R()._atomic_write_json(file_path, deals)
        updated_deal = deals[idx].copy()

    _intrag_segue('ndf', antes, updated_deal)
    # Save to Intrag when Status→Success and client is BANCO JP MORGAN
    new_status = updated_deal.get('Status', '')
    cl_lower = (updated_deal.get('Client', '') or '').lower()
    if new_status == 'Success' and 'banco' in cl_lower and 'morgan' in cl_lower:
        try:
            _R()._intrag_engine()._save_intrag_ndf_entry(updated_deal)
        except Exception as exc:
            _R().log.error('[NDF PATCH] Failed to save Intrag entry for deal=%r: %s', deal_id, exc)
            _mirrors.falhou('intrag', deal_id, exc)
    # External clients (non-intragroup) instead become a fresh outstanding
    # confirmation → Pending Confirmation. Manual-mapping twin of the return-file
    # scan trigger; _pc_save_from_deal skips internal/intragroup legs itself.
    if new_status == 'Success':
        _R()._pc_save_from_deal(updated_deal, 'NDF COMM')        # → pending confirmation

    _fields = {k: v for k, v in updates.items() if k not in ('Maker', 'Checker', '_client')}
    if _fields:
        if 'Status' in _fields:
            # The 'Sent' transition is already announced by the 'Sent to B3'
            # notification emitted from send-conecta — skip the redundant
            # 'Status Updated' entry so the bell shows a single item per send.
            if str(_fields.get('Status', '')) != 'Sent':
                _R()._create_notification(
                    session.get('user_sid', ''), session.get('user_name', ''),
                    'Status Updated', 'NDF Comm',
                    deal_id + ' → ' + str(_fields.get('Status', '')) + _R()._nd_token(updated_deal.get('TradeDate'))
                )
        else:
            _R()._create_notification(
                session.get('user_sid', ''), session.get('user_name', ''),
                'Deal Updated', 'NDF Comm',
                deal_id + ' (' + ', '.join(_fields.keys()) + ')' + _R()._nd_token(updated_deal.get('TradeDate'))
            )
    return jsonify({"success": True, "status": updated_deal.get('Status', ''),
                    "b3_id": updated_deal.get('B3_ID', '')})

@blueprint.route('/api/new-deals/ndf-commodities/cache/<deal_id>', methods=['DELETE'])
def api_ndf_delete_deal_cache(deal_id):
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    client = request.args.get('client')
    file_path, _ = _R()._find_ndf_deal_in_cache(deal_id, client)
    if file_path is None:
        return jsonify({"success": False, "message": "Deal not found"}), 404

    with _R()._cache_lock:
        deals = _nd_le_dia(file_path)
        idx = next((i for i, d in enumerate(deals)
                    if (d.get('Deal') or '').strip() == (deal_id or '').strip()
                    and (client is None or (d.get('Client', '') or '').strip() == (client or '').strip())), None)
        if idx is None:
            return jsonify({"success": False, "message": "Deal not found"}), 404
        removed = deals.pop(idx)
        _R()._atomic_write_json(file_path, deals)

    _R()._create_notification(
        session.get('user_sid', ''), session.get('user_name', ''),
        'Deal Deleted', 'NDF Comm', deal_id + _R()._nd_token((removed or {}).get('TradeDate'))
    )
    return jsonify({"success": True})

@blueprint.route('/api/new-deals/ndf-commodities/cache/bulk-delete', methods=['POST'])
def api_ndf_bulk_delete_deal_cache():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    pairs = (request.get_json(silent=True) or {}).get('pairs', [])
    if not pairs:
        return jsonify({"success": False, "message": "No pairs provided"}), 400
    return _nd_bulk_delete(_R()._find_ndf_deal_in_cache, pairs, 'NDF Comm')

@blueprint.route('/api/new-deals/ndf-commodities/cache/bulk-patch', methods=['POST'])
def api_ndf_bulk_patch_deal_cache():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    patches = (request.get_json(silent=True) or {}).get('patches', [])
    if not patches:
        return jsonify({"success": False, "message": "No patches provided"}), 400
    return _nd_bulk_patch(_R()._find_ndf_deal_in_cache, patches, 'NDF Comm')

@blueprint.route('/api/new-deals/ndf-commodities/send-conecta', methods=['POST'])
def api_ndf_send_conecta():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    import datetime as _dt

    data  = request.get_json(silent=True) or {}
    deals = data.get('deals', [])
    download = bool(data.get('download'))   # preview: devolve o conteúdo, não grava
    if not deals:
        return jsonify({'ok': False, 'error': 'No deals provided'}), 400
    if not download:
        # status e 4-olhos conferidos no SERVIDOR antes do arquivo (§685)
        _recusas = _nd_conferir_envio(_R()._find_ndf_deal_in_cache, deals, session.get('user_sid', ''))
        if _recusas:
            return _nd_recusa_envio(_recusas)

    today = _dt.datetime.today().strftime('%Y%m%d')

    # Um destino por ARQUIVO: o nome padrão é TCO_{LAWTON,BANCO}.txt e a
    # variante do template (pelo par de pernas do deal) pode cadastrar outro
    # em `file_name`. Headers pelo bloco `header` do cadastro (layout 00003);
    # o Participante sai do `b3-accounts` pela LE da visão — ou do Fixed da
    # variante, quando o cadastro o fixou.
    page_url  = '/new_deals-ndf-commodities'
    out_files = {}
    try:
        for deal in deals:
            is_jpmorgan, ter_lines = _R()._ndf_comm_ter_lines(deal)
            bucket = 'LAWTON' if is_jpmorgan else 'BANCO'
            client = re.sub(r'<[^>]+>', '', str(deal.get('Client', '') or '')).strip()
            pair   = _R()._ter_le_pair(_R()._TER_BUCKET_LE[bucket], client)
            fname  = (_R()._fi_variant_file_name(_R()._TER_FI_KEY, page_url, pair)
                      or 'TCO_{}.txt'.format(bucket))
            d = out_files.setdefault(fname, {'bucket': bucket, 'pair': pair,
                                             'lines': [], 'count': 0})
            d['lines'].extend(ter_lines)
            d['count'] += 1
        headers = {fname: _R()._ter_file_header(_R()._TER_BUCKET_LE[d['bucket']], today,
                                           page_url, le_pair=d['pair'])
                   for fname, d in out_files.items() if d['lines']}
    except ValueError as exc:
        _R().log.error('[NDF COMM] send-conecta sem header: %s', exc)
        return jsonify({'ok': False, 'error': str(exc) or _R()._TER_FI_ERROR}), 500

    output_dir = _R().CONECTA_NEW_PATH
    generated  = []
    try:
        if download:
            generated = [{'filename': fname, 'count': d['count'],
                          'content': '\n'.join([headers[fname]] + d['lines'])}
                         for fname, d in out_files.items() if d['lines']]
            return jsonify({'ok': True, 'count': sum(d['count'] for d in out_files.values()),
                            'files': generated,
                            'filename': generated[0]['filename'] if generated else ''})
        # Na New o nome leva a conta da visão (o balde) na frente (§646),
        # calculado para TODOS antes do primeiro arquivo.
        nomes = {fname: _R()._conecta_file_name(d['bucket'], fname)
                 for fname, d in out_files.items() if d['lines']}
        os.makedirs(output_dir, exist_ok=True)
        for fname, d in out_files.items():
            if not d['lines']:
                continue
            path = _R()._unique_filepath(output_dir, nomes[fname])
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write('\n'.join([headers[fname]] + d['lines']))
            generated.append({'filename': os.path.basename(path), 'count': d['count']})
        total = sum(d['count'] for d in out_files.values())
        primary = generated[0]['filename'] if generated else ''
        if total > 0:
            _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''), 'Sent to B3', 'NDF Comm', str(total) + ' deal' + ('' if total == 1 else 's') + ' sent')
        # o arquivo JÁ está na pasta: o `Sent` vai no mesmo pedido (§685)
        _marcados, _falhas = _nd_marcar_enviados(_R()._find_ndf_deal_in_cache, deals, session.get('user_sid', ''))
        return jsonify({'ok': True, 'filename': primary, 'count': total, 'files': generated,
                        'marked': _marcados, 'status_failed': _falhas})
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500

@blueprint.route('/api/new-deals/ndf-commodities/mapping-b3', methods=['POST'])
def api_ndf_mapping_b3():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401

    data = request.get_json(silent=True) or {}
    sent_deals = data.get('deals', [])
    if not sent_deals:
        return jsonify({'ok': True, 'results': []})

    mapping         = {}
    linhas_por_arquivo = {}   # arquivo → dono (Deal) de cada linha TER
    try:
        if not _store.isdir(_R().RETURN_PATH):
            return jsonify({'ok': False, 'error': f'Return folder not found: {_R().RETURN_PATH}'}), 400

        for fname in _store.listdir(_R().RETURN_PATH):
            fpath = os.path.join(_R().RETURN_PATH, fname)
            if not _store.isfile(fpath):
                continue
            try:
                with open(fpath, 'r', encoding='latin-1') as fh:
                    lines = fh.readlines()
                donos = []
                for line in lines[1:]:  # skip header row
                    line = line.strip()
                    if not line:
                        continue
                    # Sigla at chars 57-59 (1-based): only 'TER' (termo) lines —
                    # e nunca a ANTECIPACAO (0014) da recompra: ela volta no
                    # mesmo arquivo de retorno com o mesmo TER, e contada aqui o
                    # arquivo era APAGADO antes do Mapping da recompra le-lo.
                    if line[56:59] != 'TER' or _e_antecipacao(line):
                        continue
                    donos.append(next((sd.get('Deal', '') for sd in sent_deals
                                       if sd.get('Deal', '') and sd.get('Deal', '') in line), None))
                    if 'EXECUCAO OK' not in line:
                        continue
                    parts = line.split(';')
                    if len(parts) < 2:
                        continue
                    b3_id = parts[1].strip()
                    for sd in sent_deals:
                        deal_text = sd.get('Deal', '')
                        if deal_text and deal_text not in mapping and deal_text in line:
                            mapping[deal_text] = b3_id
                if donos:
                    linhas_por_arquivo[fpath] = donos
            except Exception:
                continue
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500

    results = []
    gravou = {}     # Deal → a linha ficou como o retorno manda (ver _nd_apaga_retornos)
    for sd in sent_deals:
        deal_text   = sd.get('Deal', '')
        client_name = sd.get('Client', '')
        if str(sd.get('Status', '') or '').strip() == 'Canceled':
            gravou[deal_text] = True    # cancelado via API: fora do mapping, nada a gravar
            continue
        if deal_text and deal_text in mapping:
            b3_id      = mapping[deal_text]
            new_status = 'Success'
            updates    = {'Status': new_status, 'B3_ID': b3_id}
        else:
            b3_id = ''
            # Só vira `Error` quem esperava retorno (`_ND_MAPPING_ERRORABLE`, a
            # regra do genérico): a tela manda todo status (§626), e sem isto
            # um Approved/Pending que nem foi registrado virava Error.
            prev = str(sd.get('Status', '') or '').strip()
            if prev and prev not in _R()._ND_MAPPING_ERRORABLE:
                gravou[deal_text] = True
                continue
            new_status = 'Error'
            updates    = {'Status': new_status}

        gravado, linha, motivo = _grava_mapeamento(
            _R()._find_ndf_deal_in_cache, deal_text, client_name, updates)
        gravou[deal_text] = gravou.get(deal_text, True) and gravado

        intrag_candidate = linha if (gravado and new_status == 'Success') else None
        if intrag_candidate is not None:
            cl_low = (intrag_candidate.get('Client', '') or '').lower()
            if 'banco' in cl_low and 'morgan' in cl_low:
                try:
                    _R()._intrag_engine()._save_intrag_ndf_entry(intrag_candidate)
                except Exception as exc:
                    _R().log.error('[MAPPING-B3] Intrag save failed for deal=%r: %s', deal_text, exc)
                    _mirrors.falhou('intrag', deal_text, exc)
            _R()._pc_save_from_deal(intrag_candidate, 'NDF COMM')       # → pending confirmation

        # O que volta é o que FICOU GRAVADO. Não gravou, não há B3 ID a mostrar:
        # devolvê-lo faria a grade pintar na tela um número que o banco não tem.
        results.append({
            'id':     deal_text,
            'deal':   deal_text,
            'b3_id':  b3_id if gravado else '',
            'status': new_status if gravado else MAPPING_NAO_GRAVADO,
            'saved':  gravado,
            'reason': motivo,
        })

    _nd_apaga_retornos(linhas_por_arquivo, gravou, 'NDF Comm')

    # O sino conta o que FICOU GRAVADO, não o que se tentou: escrito
    # `len(results)`, ele anunciava para a mesa inteira um número que
    # inclui o mapeamento que não chegou ao banco.
    _n_gravados = sum(1 for r in results if r.get('saved'))
    if _n_gravados:
        _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''), 'B3 Mapped', 'NDF Comm', str(_n_gravados) + ' deal' + ('' if _n_gravados == 1 else 's') + ' mapped')
    return jsonify({'ok': True, 'results': results})

@blueprint.route('/api/new-deals/opt-commodities/send-conecta', methods=['POST'])
def api_send_conecta():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    from decimal import Decimal
    import datetime as _dt

    data  = request.get_json(silent=True) or {}
    deals = data.get('deals', [])
    download = bool(data.get('download'))   # preview: devolve o conteúdo, não grava
    if not deals:
        return jsonify({'ok': False, 'error': 'No deals provided'}), 400
    if not download:
        # status e 4-olhos conferidos no SERVIDOR antes do arquivo (§685)
        _recusas = _nd_conferir_envio(_R()._find_deal_in_cache, deals, session.get('user_sid', ''))
        if _recusas:
            return _nd_recusa_envio(_recusas)

    # O cadastro do File Interface (opcoes-flexiveis-vcp) comanda a montagem
    # das linhas — ordem, larguras e literais Fixed saem do template; aqui
    # ficam só os valores calculados. Sem template/blocos, erro claro: nunca
    # arquivo para a B3 meio montado em silêncio.
    _tpl = _R()._fi_tpl_cached('opcoes-flexiveis-vcp')
    if _tpl is None or not {'header', 'registro', 'registro-media-asiatica'} <= {
            b.get('id') for b in _tpl.get('blocks', [])}:
        return jsonify({'ok': False, 'error': 'File Interpreter template missing/invalid '
                                              '— check /file-interpreter (opcoes-flexiveis-vcp)'}), 500

    today = _dt.datetime.today().strftime('%Y%m%d')

    def _sh(v):
        return re.sub(r'<[^>]+>', '', str(v or '')).strip()

    def _date(val):
        val = _sh(val)
        if not val:
            return ''
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y'):
            try:
                return _dt.datetime.strptime(val, fmt).strftime('%Y%m%d')
            except ValueError:
                continue
        return ''

    def _num(val, div100=False):
        val = _sh(str(val or ''))
        if not val:
            return ''
        clean = val.replace(',', '')
        try:
            d = Decimal(clean)
            if div100:
                d = d / Decimal('100')
            s = format(d.normalize(), 'f')
            return s.replace('.', ',')
        except Exception:
            return clean.replace('.', ',')

    def _qty(val):
        """Integer quantity formatted as {int},00 for B3 field 13."""
        v = _sh(str(val or ''))
        if not v:
            return ''
        clean = v.replace(',', '')
        try:
            return str(int(round(float(clean)))) + ',00'
        except Exception:
            return v

    def _cli(client):
        c = client.upper()
        if 'LAWTON' in c:
            return '73760009'
        if 'BANCO J.P MORGAN' in c or 'JP MORGAN' in c:
            return '00041007'
        return '73760009'

    def _cpty(client):
        c = client.upper()
        if 'LAWTON' in c:
            return '00041007'
        if 'BANCO J.P MORGAN' in c or 'JP MORGAN' in c:
            return '73760009'
        return '73760102'

    def _taxid(client, taxid):
        c = client.upper()
        if 'LAWTON' in c or 'BANCO J.P MORGAN' in c or 'JP MORGAN' in c:
            return ''
        return re.sub(r'[.\-/]', '', _sh(taxid))

    import json as _json
    deal_count = 0
    # Um destino por ARQUIVO: o padrão é OPC_Banco.txt, e a variante do
    # template (pelo par de pernas do deal) pode cadastrar outro nome.
    out_files  = {}

    for deal in deals:
        # No download (preview) o status não importa — baixa até cancelado.
        if not download and str(deal.get('Status', '') or '').strip() == 'Canceled':
            continue                    # cancelado via API: fora dos arquivos
        client     = _sh(deal.get('Client', ''))
        taxid      = _sh(deal.get('TaxID', ''))
        instrument = _sh(deal.get('Instrument', ''))
        direction  = _sh(deal.get('Direction', ''))
        trade_type        = _sh(deal.get('TradeType', ''))
        strike_ccy        = _sh(deal.get('StrikeCurrency', ''))
        fx_holiday_sched  = _sh(deal.get('FXHolidaySchedule', ''))
        qic               = _sh(deal.get('QuotedInCents', 'NO')).upper() == 'YES'
        vanilla           = trade_type.upper() == 'VANILLA'
        asian             = trade_type.upper() == 'ASIAN'
        brl               = strike_ccy.upper() == 'BRL'

        opt = 'P' if 'PUT'  in instrument.upper() else ('C' if 'CALL' in instrument.upper() else '')
        dir_code   = '2' if direction.upper() == 'SELL' else '1'
        fix_start  = _date(deal.get('FixingStartDate', ''))
        fix_end    = _date(deal.get('FixingEndDate', ''))
        fxconv     = _date(deal.get('FXConvDate', ''))

        _deal_holidays = set()
        if not vanilla and fx_holiday_sched:
            _sched_file2 = fx_holiday_sched.replace('-', '_')
            holiday_path = _R().data_path(f'{_sched_file2}.json')
            try:
                # DB-first (fase 3): o schedule é um calendário do registro.
                from apps.pages import duck_read
                _raw = duck_read.calendar_rows(holiday_path)
                if _raw is None:
                    _raw = _store.read(holiday_path)
                _deal_holidays = set(
                    item['date'] if isinstance(item, dict) else item
                    for item in _raw
                )
            except Exception:
                pass

        _biz = 0
        if not vanilla and fix_start and fix_end:
            try:
                _s = _dt.datetime.strptime(fix_start, '%Y%m%d').date()
                _e = _dt.datetime.strptime(fix_end,   '%Y%m%d').date()
                _cur = _s
                while _cur <= _e:
                    _date_str = _cur.strftime('%Y-%m-%d')
                    if _cur.weekday() < 5 and _date_str not in _deal_holidays:
                        _biz += 1
                    _cur += _dt.timedelta(days=1)
            except Exception:
                pass

        # Só os campos não-Fixed, por seq do cadastro; os literais ('OPC  00002',
        # Tipo Indicador '3', Tipo de Exercício '2'…) saem do template —
        # byte a byte o que sempre foi enviado.
        trade_date = _date(deal.get('TradeDate', ''))
        _spot_date = _date(deal.get('SpotDate', ''))
        _is_bank_or_lawton = 'LAWTON' in client.upper() or 'BANCO J.P MORGAN' in client.upper() or 'JP MORGAN' in client.upper()
        vals = {
            '4':  _cli(client),
            '5':  dir_code,
            '7':  _cpty(client),
            '8':  _taxid(client, taxid),
            '9':  opt,
            '10': trade_date,
            '11': _date(deal.get('SettlementDate', '')),
            '12': _sh(deal.get('UnderlyingAsset', '')),
            '13': _qty(deal.get('TotalNotional', '')),
            '14': _num(deal.get('Strike', ''), div100=qic),
            # Tipo de Cotação: cadastro (Commodities × B3 › Tipo de Cotação —
            # Opção). Sem linha, ou coluna vazia, sai o '5' de sempre. §177
            '18': _R()._b3_quote_cfg(_sh(deal.get('UnderlyingAsset', '')))['opt'],
            '19': 'S' if brl else '',
            '20': fix_start if vanilla else '',
            '21': fxconv if (not brl or vanilla) else '',
            '24': str(_R().random.randint(1000000000, 9999999999)),
            '25': _sh(deal.get('Deal', '')),
            '27': _num(deal.get('PremiumPerUnit', ''), div100=qic),
            '29': ('2' if trade_date == _spot_date else '3') if _is_bank_or_lawton else '1',
            '33': _spot_date,
            '48': '' if vanilla else '1',
            '49': '0' if vanilla else (str(_biz) if _biz else ''),
        }

        # Par de pernas → variante do template (Fixed das contas por par);
        # sem variante, o base — byte a byte o de sempre.
        # Um arquivo por visão, como no FXO (§646).
        le_pair = _R()._opc_le_pair(client)
        view = _R()._b3_view_le(le_pair)
        fname = (_R()._fi_variant_file_name('opcoes-flexiveis-vcp',
                                       '/new_deals-opt-commodities', le_pair)
                 or _opc_default_name('OPC', view))
        dest = out_files.setdefault((view, fname), [])

        deal_count += 1
        dest.append(_R()._fi_build_line('opcoes-flexiveis-vcp', 'registro', vals,
                                   page_url='/new_deals-opt-commodities',
                                   le_pair=le_pair, deal=deal))

        if asian and fix_start and fix_end:
            try:
                _s2 = _dt.datetime.strptime(fix_start, '%Y%m%d').date()
                _e2 = _dt.datetime.strptime(fix_end,   '%Y%m%d').date()
            except Exception:
                _s2 = _e2 = None
            _cur2 = _s2
            while _s2 and _cur2 <= _e2:
                if _cur2.weekday() < 5 and _cur2.strftime('%Y-%m-%d') not in _deal_holidays:
                    _d = _cur2.strftime('%Y%m%d')
                    dest.append(_R()._fi_build_line(
                        'opcoes-flexiveis-vcp', 'registro-media-asiatica',
                        {'3': _d, '4': _d if brl else ''},
                        page_url='/new_deals-opt-commodities', le_pair=le_pair,
                        deal=deal))
                _cur2 += _dt.timedelta(days=1)

    # O header do OPC não depende do par (participante Fixed no template + a
    # data): o mesmo header abre todos os arquivos.
    header = _R()._fi_build_line('opcoes-flexiveis-vcp', 'header', {'4': today},
                            page_url='/new_deals-opt-commodities')
    if not out_files:
        out_files[('JPM', 'OPC_Banco.txt')] = []   # lote só de cancelados: header, como sempre

    output_dir = _R().CONECTA_NEW_PATH
    try:
        if download:
            files = [{'filename': fname, 'content': '\n'.join([header] + lines)}
                     for (view, fname), lines in out_files.items()]
            return jsonify({'ok': True, 'count': deal_count, 'files': files,
                            'filename': files[0]['filename'] if files else ''})
        nomes = {k: _R()._conecta_file_name(*k) for k in out_files}
        os.makedirs(output_dir, exist_ok=True)
        generated = []
        for k, lines in out_files.items():
            filepath = _R()._unique_filepath(output_dir, nomes[k])
            with open(filepath, 'w', encoding='utf-8') as fh:
                fh.write('\n'.join([header] + lines))
            generated.append(os.path.basename(filepath))
        if deal_count > 0:
            _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''), 'Sent to B3', 'Opt Comm', str(deal_count) + ' deal' + ('' if deal_count == 1 else 's') + ' sent')
        # o arquivo JÁ está na pasta: o `Sent` vai no mesmo pedido (§685)
        _marcados, _falhas = _nd_marcar_enviados(_R()._find_deal_in_cache, deals, session.get('user_sid', ''))
        return jsonify({'ok': True, 'filename': generated[0] if generated else '',
                        'count': deal_count, 'files': generated,
                        'marked': _marcados, 'status_failed': _falhas})
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500

@blueprint.route('/api/new-deals/opt-commodities/mapping-b3', methods=['POST'])
def api_mapping_b3():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401

    data = request.get_json(silent=True) or {}
    sent_deals = data.get('deals', [])   # [{id, Deal}]
    if not sent_deals:
        return jsonify({'ok': True, 'results': []})

    # ── scan return folder ────────────────────────────────────────────
    mapping       = {}   # deal_text -> {'b3_id': str, 'ok': bool}
    linhas_por_arquivo = {}   # arquivo → Deal de cada linha OPC tipo 1
    try:
        if not _store.isdir(_R().RETURN_PATH):
            return jsonify({'ok': False, 'error': f'Return folder not found: {_R().RETURN_PATH}'}), 400

        for fname in _store.listdir(_R().RETURN_PATH):
            fpath = os.path.join(_R().RETURN_PATH, fname)
            if not _store.isfile(fpath):
                continue
            try:
                with open(fpath, encoding='utf-8', errors='replace') as fh:
                    lines = fh.readlines()
                donos = []
                for line in lines[1:]:   # skip header
                    line = line.strip()
                    if not line:
                        continue
                    # Sigla at chars 57-59 (1-based): Options map only 'OPC' (opção) lines
                    if line[56:59] != 'OPC':
                        continue
                    parts = line.split(';')
                    if len(parts) < 5:
                        continue
                    b3_id       = parts[1].strip()
                    status_text = parts[3].strip()
                    opc_part    = parts[4].strip()
                    pipe_parts  = opc_part.split('|')
                    if len(pipe_parts) < 25:
                        continue
                    if pipe_parts[1].strip() != '1':   # only type-1 (characteristics) lines
                        continue
                    deal_text = pipe_parts[24].strip()
                    if not deal_text:
                        continue
                    donos.append(deal_text)
                    is_ok = (status_text == 'EXECUCAO OK')
                    if deal_text not in mapping or (is_ok and not mapping[deal_text]['ok']):
                        mapping[deal_text] = {'b3_id': b3_id, 'ok': is_ok}
                if donos:
                    linhas_por_arquivo[fpath] = donos
            except Exception:
                continue
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500

    # ── match sent deals and update cache ────────────────────────────
    results = []
    gravou = {}
    for sent in sent_deals:
        deal_text   = sent.get('Deal', '')
        client_name = sent.get('Client', '')
        if not deal_text or deal_text not in mapping:
            continue

        info       = mapping[deal_text]
        new_status = 'Success' if info['ok'] else 'Error'
        updates    = {'Status': new_status}
        if info['ok']:
            updates['B3_ID'] = info['b3_id']

        gravado, linha, motivo = _grava_mapeamento(
            _R()._find_deal_in_cache, deal_text, client_name, updates)
        gravou[deal_text] = gravou.get(deal_text, True) and gravado

        intrag_candidate = linha if (gravado and new_status == 'Success') else None
        if intrag_candidate is not None:
            _R()._intrag_engine()._maybe_save_intrag_opt(intrag_candidate)
            _R()._pc_save_from_deal(intrag_candidate, 'OPTION COMM')   # → pending confirmation

        results.append({
            'id':     deal_text,
            'deal':   deal_text,
            'b3_id':  (info['b3_id'] if info['ok'] else '') if gravado else '',
            'status': new_status if gravado else MAPPING_NAO_GRAVADO,
            'saved':  gravado,
            'reason': motivo
        })

    # Deal da outra página de opção (o OPC é dos dois) ou de outro dia fica
    # sem dono aqui, e o retorno fica para quem o absorve (_nd_apaga_retornos)
    _nd_apaga_retornos(linhas_por_arquivo, gravou, 'Opt Comm')

    # O sino conta o que FICOU GRAVADO, não o que se tentou: escrito
    # `len(results)`, ele anunciava para a mesa inteira um número que
    # inclui o mapeamento que não chegou ao banco.
    _n_gravados = sum(1 for r in results if r.get('saved'))
    if _n_gravados:
        _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''), 'B3 Mapped', 'Opt Comm', str(_n_gravados) + ' deal' + ('' if _n_gravados == 1 else 's') + ' mapped')
    return jsonify({'ok': True, 'results': results})

@blueprint.route('/api/new-deals/opt-commodities/premium-email', methods=['POST'])
def api_opt_premium_email():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401

    from apps.pages import otc_emails
    deals = (request.get_json(silent=True) or {}).get('deals', [])
    drafts = otc_emails.build_premium_emails(deals, asset_label='Opção de Commodities')
    if not drafts:
        return jsonify({'ok': True, 'count': 0})
    return _R()._email_drafts_response(drafts)

@blueprint.route('/api/new-deals/opt-fxo/premium-email', methods=['POST'])
def api_fxo_premium_email():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401

    from apps.pages import otc_emails
    deals = (request.get_json(silent=True) or {}).get('deals', [])
    drafts = otc_emails.build_premium_emails(deals, asset_label='Opção de Moeda',
                                             ref_key='FX CASH ACCRONYM',
                                             cc_comm_sales=False)   # FX flow — Comm Sales isn't copied
    if not drafts:
        return jsonify({'ok': True, 'count': 0})
    return _R()._email_drafts_response(drafts)

@blueprint.route('/api/new-deals/opt-commodities/economic-affirmation', methods=['POST'])
def api_opt_economic_affirmation_email():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401

    from apps.pages import otc_emails
    deals = (request.get_json(silent=True) or {}).get('deals', [])
    drafts = otc_emails.build_economic_affirmation_emails(deals, asset_label='Opção Mercadoria')
    if not drafts:
        return jsonify({'ok': True, 'count': 0})
    return _R()._email_drafts_response(drafts)

@blueprint.route('/api/new-deals/ndf-commodities/economic-affirmation', methods=['POST'])
def api_ndf_economic_affirmation_email():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401

    from apps.pages import otc_emails
    deals = (request.get_json(silent=True) or {}).get('deals', [])
    drafts = otc_emails.build_economic_affirmation_emails(deals, asset_label='Termo de Mercadoria')
    if not drafts:
        return jsonify({'ok': True, 'count': 0})
    return _R()._email_drafts_response(drafts)

@blueprint.route('/api/new-deals/ndf-commodities/confirmations')
def api_ndfcomm_confirmations():
    """Grupos de confirmação da reference date, com o link de geração quando o
    template da família já existe (por ora, só strike-usd)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    ds = (request.args.get('date') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    groups, _statuses, _total = _R()._conf_ndfcomm_groups(ref)
    state = _R()._conf_state_load(ref)
    out = []
    for g in groups:
        available = g['family'] in _R()._CONF_FAMILY_TEMPLATES
        entry = state.get(_R()._conf_key(g['acronym'], g['mercadoria'], g['family'])) or {}
        status = entry.get('status') or 'New'
        qs = ('date=' + ref.strftime('%Y-%m-%d')
              + '&acronym=' + _R().quote(g['acronym'])
              + '&mercadoria=' + _R().quote(g['mercadoria']))
        url = _R()._CONF_FAMILY_TEMPLATES[g['family']][1] + '?' + qs if available else None
        validate_url = ('/confirmation/ndf-comm/validate?' + qs + '&family=' + _R().quote(g['family'])) \
            if status in ('Generated', 'Success') else None
        out.append({
            'acronym': g['acronym'], 'client': g['client'],
            'mercadoria': g['mercadoria'], 'family': g['family'],
            'count': g['count'], 'eligible': g['eligible'],
            'available': available, 'url': url,
            'status': status, 'validate_url': validate_url,
        })
    return jsonify({'success': True, 'date': ref.strftime('%Y-%m-%d'), 'groups': out})

@blueprint.route('/api/new-deals/opt-commodities/confirmations')
def api_optcomm_confirmations():
    """Grupos de confirmação de Opção de Commodities da reference date."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    ds = (request.args.get('date') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    groups, _statuses, _total = _R()._conf_optcomm_groups(ref)
    state = _R()._conf_state_load(ref, 'opt-comm')
    out = []
    for g in groups:
        available = g['family'] in _R()._CONF_OPT_FAMILY_TEMPLATES
        entry = state.get(_R()._conf_key(g['acronym'], g['mercadoria'], g['family'])) or {}
        status = entry.get('status') or 'New'
        qs = ('date=' + ref.strftime('%Y-%m-%d')
              + '&acronym=' + _R().quote(g['acronym'])
              + '&mercadoria=' + _R().quote(g['mercadoria']))
        url = _R()._CONF_OPT_FAMILY_TEMPLATES[g['family']][1] + '?' + qs if available else None
        validate_url = ('/confirmation/opt-comm/validate?' + qs + '&family=' + _R().quote(g['family'])) \
            if status in ('Generated', 'Success') else None
        out.append({
            'acronym': g['acronym'], 'client': g['client'],
            'mercadoria': g['mercadoria'], 'family': g['family'],
            'count': g['count'], 'eligible': g['eligible'],
            'available': available, 'url': url,
            'status': status, 'validate_url': validate_url,
        })
    return jsonify({'success': True, 'date': ref.strftime('%Y-%m-%d'), 'groups': out})

@blueprint.route('/api/new-deals/opt-fxo/confirmations')
def api_optfxo_confirmations():
    """Grupos de confirmação de Opção de Câmbio da reference date."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    ds = (request.args.get('date') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    groups, _statuses, _total = _R()._conf_optfxo_groups(ref)
    state = _R()._conf_state_load(ref, 'opt-fxo')
    out = []
    for g in groups:
        available = g['family'] in _R()._CONF_FXO_FAMILY_TEMPLATES
        entry = state.get(_R()._conf_key(g['acronym'], g['mercadoria'], g['family'])) or {}
        status = entry.get('status') or 'New'
        qs = ('date=' + ref.strftime('%Y-%m-%d')
              + '&acronym=' + _R().quote(g['acronym'])
              + '&mercadoria=' + _R().quote(g['mercadoria']))
        url = _R()._CONF_FXO_FAMILY_TEMPLATES[g['family']][1] + '?' + qs if available else None
        validate_url = ('/confirmation/opt-fxo/validate?' + qs + '&family=' + _R().quote(g['family'])) \
            if status in ('Generated', 'Success') else None
        out.append({
            'acronym': g['acronym'], 'client': g['client'],
            'mercadoria': g['mercadoria'], 'family': g['family'],
            'count': g['count'], 'eligible': g['eligible'],
            'available': available, 'url': url,
            'status': status, 'validate_url': validate_url,
        })
    return jsonify({'success': True, 'date': ref.strftime('%Y-%m-%d'), 'groups': out})

@blueprint.route('/api/new-deals/ndf-fwdstart/confirmations')
def api_ndffwdstart_confirmations():
    """Grupos de confirmação de NDF FWD Start da reference date."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    ds = (request.args.get('date') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    groups, _statuses, _total = _R()._conf_fwdstart_groups(ref)
    state = _R()._conf_state_load(ref, 'ndf-fwdstart')
    out = []
    for g in groups:
        available = g['family'] in _R()._CONF_FWDSTART_FAMILY_TEMPLATES
        entry = state.get(_R()._conf_key(g['acronym'], g['mercadoria'], g['family'])) or {}
        status = entry.get('status') or 'New'
        qs = ('date=' + ref.strftime('%Y-%m-%d')
              + '&acronym=' + _R().quote(g['acronym'])
              + '&mercadoria=' + _R().quote(g['mercadoria']))
        url = _R()._CONF_FWDSTART_FAMILY_TEMPLATES[g['family']][1] + '?' + qs if available else None
        validate_url = ('/confirmation/ndf-fwdstart/validate?' + qs + '&family=' + _R().quote(g['family'])) \
            if status in ('Generated', 'Success') else None
        out.append({
            'acronym': g['acronym'], 'client': g['client'],
            'mercadoria': g['mercadoria'], 'family': g['family'],
            'count': g['count'], 'eligible': g['eligible'],
            'available': available, 'url': url,
            'status': status, 'validate_url': validate_url,
        })
    return jsonify({'success': True, 'date': ref.strftime('%Y-%m-%d'), 'groups': out})

@blueprint.route('/api/new-deals/ndf-mgt/confirmations')
def api_ndfmgt_confirmations():
    """Grupos de confirmação da JPMORGAN CHASE (MGT) contra cliente — Vanilla
    e FWD Start — da reference date (§453)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    ds = (request.args.get('date') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    groups, _statuses, _total = _R()._conf_mgt_groups(ref)
    state = _R()._conf_state_load(ref, 'ndf-mgt')
    out = []
    for g in groups:
        available = g['family'] in _R()._CONF_MGT_FAMILY_TEMPLATES
        entry = state.get(_R()._conf_key(g['acronym'], g['mercadoria'], g['family'])) or {}
        status = entry.get('status') or 'New'
        qs = ('date=' + ref.strftime('%Y-%m-%d')
              + '&acronym=' + _R().quote(g['acronym'])
              + '&mercadoria=' + _R().quote(g['mercadoria']))
        url = _R()._CONF_MGT_FAMILY_TEMPLATES[g['family']][1] + '?' + qs if available else None
        validate_url = ('/confirmation/ndf-mgt/validate?' + qs + '&family=' + _R().quote(g['family'])) \
            if status in ('Generated', 'Success') else None
        out.append({
            'acronym': g['acronym'], 'client': g['client'],
            'mercadoria': g['mercadoria'], 'family': g['family'],
            'count': g['count'], 'eligible': g['eligible'],
            'available': available, 'url': url,
            'status': status, 'validate_url': validate_url,
        })
    return jsonify({'success': True, 'date': ref.strftime('%Y-%m-%d'), 'groups': out})

@blueprint.route('/api/new-deals/<product>/cache', methods=['POST'])
def api_generic_nd_save_cache(product):
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    cfg = _R()._generic_nd_cfg(product)
    if not cfg:
        return jsonify({"success": False, "message": "Unknown product"}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "No data provided"}), 400

    try:
        ref_date = datetime.strptime(data.get('TradeDate', ''), '%d/%m/%Y')
    except (ValueError, TypeError):
        ref_date = datetime.now()

    dir_path = os.path.join(cfg['dir'], ref_date.strftime('%Y'), ref_date.strftime('%m'))
    os.makedirs(dir_path, exist_ok=True)
    file_path = os.path.join(dir_path, ref_date.strftime('%Y%m%d') + cfg['suffix'])

    with _R()._cache_lock:
        if _store.exists(file_path):
            deals = _nd_le_dia(file_path)
        else:
            deals = []

        if data.get('_import'):
            return _import_resposta(deals, data, cfg['dir'], cfg['suffix'], file_path)
        deal_name   = data.get('Deal', '').strip()
        client_name = data.get('Client', '').strip()
        existing_idx = next((i for i, d in enumerate(deals)
                             if deal_name
                             and d.get('Deal', '').strip() == deal_name
                             and d.get('Client', '').strip() == client_name), None)
        if existing_idx is not None:
            # O Add Row não SUBSTITUI a operação já gravada (26/10/2026): o POST
            # trocava a linha inteira, e um Sent/Success voltava a Pending sem o
            # B3 ID. Quem atualiza uma linha existente é o PATCH (Edit) ou o
            # import (`_import`, acima).
            return jsonify({"success": False, "error": "deal_exists",
                            "message": "This deal is already saved — edit it instead."}), 409
        deals.append(data)
        _R()._atomic_write_json(file_path, deals)

    return jsonify({"success": True, "deal": data.get('Deal', '')})

@blueprint.route('/api/new-deals/<product>/cache/search', methods=['POST'])
def api_generic_nd_search_cache(product):
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    cfg = _R()._generic_nd_cfg(product)
    if not cfg:
        return jsonify({"success": False, "message": "Unknown product"}), 404

    filters = (request.get_json(silent=True) or {}).get('filters', [])
    matched, refmap_cache = [], {}
    # `mutavel=True`: o `_generic_nd_reenrich` ALTERA os dicionários, e sem a
    # cópia a alteração ficaria gravada no memo — o próximo leitor veria o dado
    # de outro request. Ela custa microssegundos contra a dezena de
    # milissegundos de uma leitura no share.
    _dias = list(_R()._day_files(cfg['dir'], cfg['suffix'], strict=True))
    # UMA abertura de banco para todos os dias enumerados, em vez de
    # uma por dia: eles são tabelas do MESMO banco do produto (§4).
    _R()._day_prefetch(_dias)
    for fpath, _fname, mtime, size in _dias:
        deals = _R()._day_json(fpath, mtime, size, mutavel=True, strict=True)
        try:
            # Contraparte cadastrada depois do import → persiste o
            # enriquecimento, senão a linha volta vazia a cada visita.
            #
            # Grava sobre o dia RELIDO sob a trava, nunca sobre `deals`: essa
            # lista veio do memo, e gravá-la inteira desfazia o Confirm/Edit que
            # outro usuário fez entre a leitura e aqui — calado, porque a busca
            # não é uma edição. O enriquecimento só preenche SPN VAZIO, então
            # reaplicá-lo à cópia fresca dá o mesmo resultado.
            if _R()._generic_nd_reenrich(deals, refmap_cache):
                with _R()._cache_lock:
                    fresco = _R()._day_records_for_write(fpath, lambda _d: False)
                    if fresco and _R()._generic_nd_reenrich(fresco, refmap_cache):
                        _R()._atomic_write_json(fpath, fresco)
                    if fresco is not None:
                        deals = fresco
                # O mtime novo já invalidaria a entrada, mas contar com isso é
                # contar com a resolução do relógio do share.
                _R()._daycache_forget(fpath)
        except Exception:                                   # noqa: BLE001
            # A falha de GRAVAR não tira o dia da busca (era `continue`): a
            # mesa via menos operações do que o dia tem, sem aviso nenhum.
            _R().log.warning('[ND SEARCH] enriquecimento de %s não gravado:\n%s',
                             fpath, traceback.format_exc())
        for deal in deals:
            if _R()._deal_matches(deal, filters):
                matched.append(deal)
    return jsonify({"success": True, "deals": matched})

@blueprint.route('/api/new-deals/<product>/cache/<deal_id>', methods=['PATCH'])
def api_generic_nd_update_cache(product, deal_id):
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    cfg = _R()._generic_nd_cfg(product)
    if not cfg:
        return jsonify({"success": False, "message": "Unknown product"}), 404

    client  = request.args.get('client')
    updates = request.get_json(silent=True)
    if not updates:
        return jsonify({"success": False, "message": "No data provided"}), 400

    file_path, _ = _R()._find_generic_nd_deal(cfg, deal_id, client)
    if file_path is None:
        return jsonify({"success": False, "message": "Deal not found"}), 404

    with _R()._cache_lock:
        deals = _nd_le_dia(file_path)
        idx = next((i for i, d in enumerate(deals)
                    if d.get('Deal') == deal_id and (client is None or d.get('Client', '') == client)), None)
        if idx is None:
            return jsonify({"success": False, "message": "Deal not found"}), 404
        updates, _recusa = _nd_guard_updates(deals[idx], updates, session.get('user_sid', ''), product)
        if _recusa:
            return _nd_guard_response(_recusa)
        antes = dict(deals[idx])
        deals[idx].update(updates)
        _R()._atomic_write_json(file_path, deals)
        updated_deal = deals[idx].copy()

    if product in ('vanilla', 'other-publishers'):
        _intrag_segue('ndf', antes, updated_deal)
    # Vanilla / Other Publisher contra o Lawton alimentam a Intrag NDF no
    # layout "Instrucao NDF Moeda" quando o Status vira Success (FWD Start fora
    # — o strike só existe na strike set date, quando rebooka como vanilla).
    if str(updates.get('Status', '')) == 'Success':
        if product in ('vanilla', 'other-publishers') and \
                'LAWTON' in (updated_deal.get('Client', '') or '').upper():
            try:
                _R()._intrag_engine()._save_intrag_ndf_moeda_entry(updated_deal)
            except Exception as exc:
                _R().log.error('[ND %s] Intrag moeda save failed for deal=%r: %s',
                          product, deal_id, exc)
                _mirrors.falhou('intrag', deal_id, exc)
        _R()._generic_nd_pc_trigger(product, updated_deal)       # → pending confirmation

    _fields = {k: v for k, v in updates.items() if k not in ('Maker', 'Checker', '_client')}
    if _fields:
        if 'Status' in _fields:
            # The 'Sent' transition is already announced by the 'Sent to B3'
            # notification emitted from send-conecta — skip the redundant
            # 'Status Updated' entry so the bell shows a single item per send.
            if str(_fields.get('Status', '')) != 'Sent':
                _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                                     'Status Updated', cfg['label'], deal_id + ' → ' + str(_fields.get('Status', '')) + _R()._nd_token(updated_deal.get('TradeDate')))
        else:
            _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                                 'Deal Updated', cfg['label'], deal_id + ' (' + ', '.join(_fields.keys()) + ')' + _R()._nd_token(updated_deal.get('TradeDate')))
    return jsonify({"success": True, "status": updated_deal.get('Status', ''),
                    "b3_id": updated_deal.get('B3_ID', '')})

@blueprint.route('/api/new-deals/<product>/cache/<deal_id>', methods=['DELETE'])
def api_generic_nd_delete_cache(product, deal_id):
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    cfg = _R()._generic_nd_cfg(product)
    if not cfg:
        return jsonify({"success": False, "message": "Unknown product"}), 404

    client = request.args.get('client')
    file_path, _ = _R()._find_generic_nd_deal(cfg, deal_id, client)
    if file_path is None:
        return jsonify({"success": False, "message": "Deal not found"}), 404

    with _R()._cache_lock:
        deals = _nd_le_dia(file_path)
        idx = next((i for i, d in enumerate(deals)
                    if d.get('Deal') == deal_id and (client is None or d.get('Client', '') == client)), None)
        if idx is None:
            return jsonify({"success": False, "message": "Deal not found"}), 404
        removed = deals.pop(idx)
        _R()._atomic_write_json(file_path, deals)

    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Deal Deleted', cfg['label'], deal_id + _R()._nd_token((removed or {}).get('TradeDate')))
    return jsonify({"success": True})

@blueprint.route('/api/new-deals/<product>/cache/bulk-delete', methods=['POST'])
def api_generic_nd_bulk_delete_cache(product):
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    cfg = _R()._generic_nd_cfg(product)
    if not cfg:
        return jsonify({"success": False, "message": "Unknown product"}), 404
    pairs = (request.get_json(silent=True) or {}).get('pairs', [])
    if not pairs:
        return jsonify({"success": False, "message": "No pairs provided"}), 400
    return _nd_bulk_delete(lambda d, c: _R()._find_generic_nd_deal(cfg, d, c), pairs, cfg['label'])

@blueprint.route('/api/new-deals/<product>/cache/bulk-patch', methods=['POST'])
def api_generic_nd_bulk_patch_cache(product):
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    cfg = _R()._generic_nd_cfg(product)
    if not cfg:
        return jsonify({"success": False, "message": "Unknown product"}), 404
    patches = (request.get_json(silent=True) or {}).get('patches', [])
    if not patches:
        return jsonify({"success": False, "message": "No patches provided"}), 400
    return _nd_bulk_patch(lambda d, c: _R()._find_generic_nd_deal(cfg, d, c), patches, cfg['label'], product=product,
                          depois=lambda d: _R()._generic_nd_pc_trigger(product, d))

@blueprint.route('/api/new-deals/<product>/send-conecta', methods=['POST'])
def api_generic_nd_send_conecta(product):
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    data = request.get_json(silent=True) or {}
    # `download: true` (o botão do preview) devolve o CONTEÚDO do arquivo em
    # vez de gravar no Batch Conecta — mesmo gerador, byte a byte, sem
    # notificação e IGNORANDO o status do deal.
    #
    # O VANILLA gera arquivo como os outros dois. Ele já nascia no download (o
    # registro dele era de outra ferramenta e o app só montava o arquivo), e a
    # mesa passou a registrar por aqui: o que muda é o DESTINO, não o gerador —
    # a mesma linha, o mesmo template do File Interpreter e as mesmas linhas de
    # verificação, agora gravadas no Batch Conecta.
    download = bool(data.get('download'))
    valid = ('fwd-start', 'other-publishers', 'vanilla')
    if product not in valid:
        return jsonify({'ok': False, 'error': 'send-conecta not available for this product'}), 404
    is_fwd = product == 'fwd-start'
    prefix = {'fwd-start': 'FWDSTART', 'other-publishers': 'OTHERPUBLISHER',
              'vanilla': 'VANILLA'}[product]
    page_url = {'fwd-start': '/new_deals-ndf-fwdstart',
                'other-publishers': '/new_deals-ndf-otherpublisher',
                'vanilla': '/new_deals-ndf-vanilla'}[product]

    deals = data.get('deals', [])
    if not deals:
        return jsonify({'ok': False, 'error': 'No deals provided'}), 400
    if not download:
        # status e 4-olhos conferidos no SERVIDOR antes do arquivo (§685)
        _recusas = _nd_conferir_envio((lambda d, c: _R()._find_generic_nd_deal(_R()._generic_nd_cfg(product), d, c)), deals, session.get('user_sid', ''))
        if _recusas:
            return _nd_recusa_envio(_recusas)

    today = datetime.today().strftime('%Y%m%d')

    # Um destino por ARQUIVO de saída: o nome padrão é {prefix}_{bucket}.txt,
    # e a variante do template (pelo par de pernas do deal) pode cadastrar
    # outro em `file_name`. Deals do mesmo bucket com variantes de nomes
    # diferentes saem em arquivos separados — é o que o cadastro pediu.
    out_files = {}
    counts = _R().Counter()

    def _fi_dest(bucket, client):
        pair = _R()._ter_le_pair(_R()._TER_BUCKET_LE[bucket], client)
        fname = (_R()._fi_variant_file_name(_R()._TER_FI_KEY, page_url, pair)
                 or '{}_{}.txt'.format(prefix, bucket))
        if fname not in out_files:
            out_files[fname] = {'bucket': bucket, 'pair': pair, 'lines': []}
        return out_files[fname], fname

    try:
        made_by_deal = []
        for deal in deals:
            if download and isinstance(deal, dict):
                deal = {k: v for k, v in deal.items() if k != 'Status'}
            made = _R()._generic_ndf_ter_line(deal, is_fwd, page_url=page_url)
            if made is None:
                continue
            made_by_deal.append((deal, made[0]))
            bucket, line = made
            dest, fname = _fi_dest(
                bucket, re.sub(r'<[^>]+>', '', str(deal.get('Client', '') or '')).strip())
            dest['lines'].append(line)
            counts[fname] += 1
            # As linhas de verificação (tipo 2) do Vanilla saem nos DOIS
            # caminhos. Emitir só no download faria o arquivo baixado para
            # conferência diferir do que vai para a B3 — divergência que não
            # aparece em lugar nenhum até a B3 recusar o registro.
            if product == 'vanilla':
                dest['lines'].extend(
                    _R()._vanilla_verification_lines(deal, page_url, dest['pair']))
        # Quebra visão banco × visão Lawton: a linha do banco contra o Lawton
        # gera também a visão Lawton (espelho sintetizado), A MENOS que o lote
        # já traga a perna explícita do mesmo trade — aí ela é a visão Lawton
        # e sintetizar duplicaria o registro na B3. O casamento é pelos termos
        # econômicos (`_nd_lawton_sig`) e consome uma perna explícita por
        # linha do banco, para dois trades iguais no mesmo dia não dividirem
        # um espelho só.
        explicit = [_R()._nd_lawton_sig(d) for d, b in made_by_deal if b == 'LAWTON']
        for deal, bucket in made_by_deal:
            if bucket != 'BANCO' or 'LAWTON' not in str(deal.get('Client', '') or '').upper():
                continue
            sig = _R()._nd_lawton_sig(deal)
            if sig in explicit:
                explicit.remove(sig)
                continue
            mirror = _R()._nd_lawton_mirror(deal)
            made = _R()._generic_ndf_ter_line(mirror, is_fwd, page_url=page_url)
            if made is None:
                continue
            b2, l2 = made
            dest, fname = _fi_dest(b2, str(mirror.get('Client', '') or ''))
            dest['lines'].append(l2)
            counts[fname] += 1
        # Quebra visão MGT x Cliente (as TRÊS páginas genéricas — Vanilla,
        # FWD Start e Other Publisher): a mesa booka contra a MGT
        # (04880.00-6 x 73760.20-5, template do File Interpreter já
        # cadastrado) e o cliente senta no omnibus do BANCO — o arquivo do
        # banco leva a perna espelhada (73760.20-5 x 04880.00-6, Papel
        # invertido). Não há deal com essa visão para cadastrar template, então
        # o espelho é sintetizado como o do Lawton; no Vanilla as linhas de
        # verificação (tipo 2) acompanham — é a única das três que as emite —,
        # senão o registro asiático do lado do banco iria para a B3 sem as
        # datas.
        for deal, bucket in made_by_deal:
            if bucket != 'MGT':
                continue
            client_up = re.sub(r'<[^>]+>', '',
                               str(deal.get('Client', '') or '')).strip().upper()
            # Só a perna contra CLIENTE tem espelho: contra JPM/Lawton a
            # outra visão já sai do próprio lote (ou do espelho Lawton).
            if (re.search(r'J\.?P\.?\s*MORGAN', client_up)
                    or 'LAWTON' in client_up or 'MGT' in client_up):
                continue
            mirror = _R()._nd_mgt_mirror(deal)
            # O CPF/CNPJ da PARTE sai do deal ORIGINAL (o espelho zera o
            # TaxID porque a contraparte dele é a MGT, intragrupo): na visão
            # CLI x MGT a parte é o cliente no omnibus do Banco, e a conta
            # omnibus sozinha não diz para a B3 de quem é a ponta.
            made = _R()._generic_ndf_ter_line(
                mirror, is_fwd, page_url=page_url,
                participant_override=_R()._TER_MGT_MIRROR_PARTICIPANT,
                party_taxid=deal.get('TaxID'))
            if made is None:
                continue
            b2, l2 = made
            dest, fname = _fi_dest(b2, str(mirror.get('Client', '') or ''))
            dest['lines'].append(l2)
            counts[fname] += 1
            if product == 'vanilla':
                dest['lines'].extend(
                    _R()._vanilla_verification_lines(mirror, page_url, dest['pair']))
        # O header é por ARQUIVO: a LE é a do bucket e a variante é a do par
        # do primeiro deal que caiu nele (mesma perna nossa → mesmo header).
        headers = {fname: _R()._ter_file_header(_R()._TER_BUCKET_LE[d['bucket']], today,
                                           page_url, le_pair=d['pair'])
                   for fname, d in out_files.items() if d['lines']}
    except ValueError as exc:
        _R().log.error('[ND %s] send-conecta sem header: %s', product, exc)
        return jsonify({'ok': False, 'error': str(exc) or _R()._TER_FI_ERROR}), 500

    generated = []
    try:
        if download:
            for fname, d in out_files.items():
                if not d['lines']:
                    continue
                generated.append({'filename': fname, 'count': counts[fname],
                                  'content': '\n'.join([headers[fname]] + d['lines'])})
            return jsonify({'ok': True, 'count': len(made_by_deal), 'files': generated,
                            'filename': generated[0]['filename'] if generated else ''})
        # Na New o nome leva a conta da visão (o balde) na frente (§646),
        # calculado para TODOS antes do primeiro arquivo.
        nomes = {fname: _R()._conecta_file_name(d['bucket'], fname)
                 for fname, d in out_files.items() if d['lines']}
        os.makedirs(_R().CONECTA_NEW_PATH, exist_ok=True)
        for fname, d in out_files.items():
            if not d['lines']:
                continue
            path = _R()._unique_filepath(_R().CONECTA_NEW_PATH, nomes[fname])
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write('\n'.join([headers[fname]] + d['lines']))
            generated.append({'filename': os.path.basename(path), 'count': counts[fname]})
        # `count` da resposta e da notificação = DEALS enviados; o espelho
        # sintetizado do Lawton é uma linha a mais no arquivo (conta no
        # per-file `files`), não um deal a mais.
        total = len(made_by_deal)
        if total > 0:
            cfg = _R()._generic_nd_cfg(product)
            _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                                 'Sent to B3', cfg['label'] if cfg else product,
                                 str(total) + ' deal' + ('' if total == 1 else 's') + ' sent')
        primary = generated[0]['filename'] if generated else ''
        # o arquivo JÁ está na pasta: o `Sent` vai no mesmo pedido (§685)
        _marcados, _falhas = _nd_marcar_enviados((lambda d, c: _R()._find_generic_nd_deal(_R()._generic_nd_cfg(product), d, c)), deals, session.get('user_sid', ''))
        return jsonify({'ok': True, 'filename': primary, 'count': total, 'files': generated,
                        'marked': _marcados, 'status_failed': _falhas})
    except Exception as exc:                            # noqa: BLE001
        return jsonify({'ok': False, 'error': str(exc)}), 500

@blueprint.route('/api/new-deals/<product>/mapping-b3', methods=['POST'])
def api_generic_nd_mapping_b3(product):
    """B3 return-file scan for the generic NDF pages — same logic as the
    ndf-commodities mapping. The TER files write the RIGHT-14 chars of the Deal
    as Código Identificador, so the return-line match uses that suffix."""
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    cfg = _R()._generic_nd_cfg(product)
    if not cfg:
        return jsonify({'ok': False, 'error': 'Unknown product'}), 404

    data = request.get_json(silent=True) or {}
    # `ref_date` = campo Reference Date da página. Com ele a lista sai do ARQUIVO
    # DO DIA e não da tabela: a tabela mostra o resultado da última busca, então
    # mapear o que estava renderizado deixava de fora operações do mesmo dia que
    # ninguém tinha filtrado. `deals` continua aceito para chamadas com lista
    # explícita.
    sent_deals = (_R()._generic_nd_mapping_candidates(cfg, product, data.get('ref_date'))
                  if data.get('ref_date') else data.get('deals', []))
    if not sent_deals:
        return jsonify({'ok': True, 'results': []})

    mapping         = {}
    linhas_por_arquivo = {}   # arquivo → dono (Deal) de cada linha TER
    try:
        if not _store.isdir(_R().RETURN_PATH):
            return jsonify({'ok': False, 'error': f'Return folder not found: {_R().RETURN_PATH}'}), 400

        for fname in _store.listdir(_R().RETURN_PATH):
            fpath = os.path.join(_R().RETURN_PATH, fname)
            if not _store.isfile(fpath):
                continue
            try:
                with open(fpath, 'r', encoding='latin-1') as fh:
                    lines = fh.readlines()
                donos = []
                for line in lines[1:]:  # skip header row
                    line = line.strip()
                    if not line:
                        continue
                    # Sigla at chars 57-59 (1-based): only 'TER' (termo) lines —
                    # e nunca a ANTECIPACAO (0014) da recompra: ela volta no
                    # mesmo arquivo de retorno com o mesmo TER, e contada aqui o
                    # arquivo era APAGADO antes do Mapping da recompra le-lo.
                    if line[56:59] != 'TER' or _e_antecipacao(line):
                        continue
                    donos.append(next((sd.get('Deal', '') for sd in sent_deals
                                       if sd.get('Deal', '') and sd.get('Deal', '')[-14:] in line), None))
                    if 'EXECUCAO OK' not in line:
                        continue
                    parts = line.split(';')
                    if len(parts) < 2:
                        continue
                    b3_id = parts[1].strip()
                    for sd in sent_deals:
                        deal_text = sd.get('Deal', '')
                        if deal_text and deal_text not in mapping and deal_text[-14:] in line:
                            mapping[deal_text] = b3_id
                if donos:
                    linhas_por_arquivo[fpath] = donos
            except Exception:
                continue
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500

    results = []
    gravou = {}     # Deal → a linha ficou como o retorno manda (ver _nd_apaga_retornos)
    for sd in sent_deals:
        deal_text   = sd.get('Deal', '')
        client_name = sd.get('Client', '')
        if str(sd.get('Status', '') or '').strip() == 'Canceled':
            gravou[deal_text] = True    # cancelado via API: fora do mapping, nada a gravar
            continue
        if deal_text and deal_text in mapping:
            b3_id      = mapping[deal_text]
            new_status = 'Success'
            updates    = {'Status': new_status, 'B3_ID': b3_id}
        else:
            b3_id = ''
            # Não achou no retorno: só vira 'Error' quem estava esperando
            # retorno. Agora que a varredura pega o dia inteiro em qualquer
            # status, marcar todo mundo derrubaria para Error operações que nem
            # sequer foram registradas ainda (Approved/Pending) — e, pior, um
            # Success sem B3 ID.
            prev = str(sd.get('Status', '') or '').strip()
            if prev and prev not in _R()._ND_MAPPING_ERRORABLE:
                new_status = prev
                updates    = {}
            else:
                new_status = 'Error'
                updates    = {'Status': new_status}

        # `updates` vazio é a operação que NÃO estava esperando retorno: ela
        # fica como está, e isso não é falha de gravação — não havia o que
        # gravar. Ela também não entra no `results` (ver logo abaixo).
        if not updates:
            gravado, linha, motivo = True, None, ''
        else:
            gravado, linha, motivo = _grava_mapeamento(
                lambda d, c: _R()._find_generic_nd_deal(cfg, d, c),
                deal_text, client_name, updates)
        gravou[deal_text] = gravou.get(deal_text, True) and gravado

        success_deal = linha if (gravado and new_status == 'Success') else None
        if success_deal is not None:
            # Vanilla / Other Publisher contra o Lawton → Intrag NDF (layout
            # "Instrucao NDF Moeda"), mesmo gatilho do update manual.
            if product in ('vanilla', 'other-publishers') and \
                    'LAWTON' in (success_deal.get('Client', '') or '').upper():
                try:
                    _R()._intrag_engine()._save_intrag_ndf_moeda_entry(success_deal)
                except Exception as exc:
                    _R().log.error('[MAPPING-%s] Intrag moeda save failed for deal=%r: %s',
                              product, deal_text, exc)
                    _mirrors.falhou('intrag', deal_text, exc)
            _R()._generic_nd_pc_trigger(product, success_deal)   # → pending confirmation

        # Só entra no resultado quem MUDOU. Varrendo o dia inteiro, a lista
        # passa a incluir deals que ficaram como estavam — contá-los inflaria o
        # "N deal(s) mapped" da notificação e os contadores da tela.
        if updates:
            results.append({
                'id':     deal_text,
                'deal':   deal_text,
                'b3_id':  b3_id if gravado else '',
                'status': new_status if gravado else MAPPING_NAO_GRAVADO,
                'saved':  gravado,
                'reason': motivo,
            })

    _nd_apaga_retornos(linhas_por_arquivo, gravou, cfg['label'])

    # O sino conta o que FICOU GRAVADO, não o que se tentou: escrito
    # `len(results)`, ele anunciava para a mesa inteira um número que
    # inclui o mapeamento que não chegou ao banco.
    _n_gravados = sum(1 for r in results if r.get('saved'))
    if _n_gravados:
        _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                             'B3 Mapped', cfg['label'],
                             str(_n_gravados) + ' deal' + ('' if _n_gravados == 1 else 's') + ' mapped')
    return jsonify({'ok': True, 'results': results})


# ── As páginas de New Deals que saem do CATÁLOGO (uma tela só) ───────────────
# Rota ESTÁTICA por página: o catch-all `/<template>` renderizaria o template
# sem a variável `page`. Página nova no catálogo = um decorador a mais aqui
# (o `check_new_deals_catalog.py` cobra os dois lados).
@blueprint.route('/new_deals-swap-cashflow')
@blueprint.route('/new_deals-swap-cetes')
@blueprint.route('/new_deals-opt-edg')
def new_deals_product():
    from flask import redirect, render_template, url_for
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    pagina = catalog.page(request.path)
    if pagina is None:
        return render_template('pages/error-404.html'), 404
    pagina = dict(pagina, selects=dict(pagina['selects']))
    # Select que é CADASTRO sai da tela /mapping (o LABEL de cada linha), e o
    # que foi editado lá vale no request seguinte — nunca uma lista no código.
    for campo, chave in (pagina.get('selects_from_mapping') or {}).items():
        try:
            linhas = _R()._mapping_rows(chave) or []
        except Exception:                                   # noqa: BLE001
            _R().log.warning('[new-deals] cadastro %s ilegivel para o select %s', chave, campo,
                             exc_info=True)
            linhas = []
        pagina['selects'][campo] = [str(l.get('LABEL') or '').strip() for l in linhas
                                    if str(l.get('LABEL') or '').strip()]
    return render_template('pages/new_deals-product.html', segment=pagina['slug'], page=pagina)


# Prefixo ESTÁTICO por página, e não `/api/new-deals/<path:sub>`: as rotas
# genéricas `/api/new-deals/<product>/cache/search` e `.../send-conecta` (NDF
# Vanilla/FWD Start/Other Publisher) casariam o slug do catálogo como
# `product` e responderiam "Unknown product" — o segmento estático vence o
# variável, o `<path>` não. O Swap Cashflow já saiu daqui: o backend dele é a
# vertical `features/swap_cashflow` (21/09/2026), com as rotas estáticas dela.
@blueprint.route('/api/new-deals/opt-edg', methods=['GET', 'POST'])
@blueprint.route('/api/new-deals/opt-edg/<path:resto>', methods=['GET', 'POST'])
def api_new_deals_product(resto=''):
    """O servidor das páginas do catálogo ainda NÃO existe. A carga da grade
    (`cache/search`) devolve vazio com o contrato; toda outra ação responde
    501 com CÓDIGO (§486) — sem isto a tela leria a página 404 em HTML e
    mostraria `Unexpected token '<'`. Quando o backend de um produto nascer,
    as rotas dele substituem as duas linhas do produto aqui."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    pagina = catalog.page_by_api(request.path[len('/api/new-deals/'):])
    if pagina is None:
        return jsonify({'success': False, 'message': 'Not found'}), 404
    if resto in ('', 'cache/search'):
        return jsonify({'success': True, 'deals': [], 'entries': [], 'backend': False,
                        'fields': catalog.fields(pagina), 'labels': catalog.labels(pagina)})
    return jsonify({'success': False, 'code': 'nd_backend_pending',
                    'message': 'This action is not available yet for this product'}), 501
