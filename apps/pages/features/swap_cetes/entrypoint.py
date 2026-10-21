# -*- coding: utf-8 -*-
"""As APIs da página New Deals › Swap › Cetes (`/new_deals-swap-cetes`).

A página é o molde do CATÁLOGO (`new_deals/entrypoint.new_deals_product` +
`pages/new_deals-product.html`, em CARDS); aqui ficam só as APIs que o JS dela
chama, com o MESMO contrato do Swap Cashflow, mais o Mapping B3 ID. Prefixo
ESTÁTICO por página (§8). Erros e lacunas saem ESTRUTURADOS (§486): `{code,
params, message}`; os códigos comuns são os `swc_*` do catálogo, os desta
página `swt_*`. Só a casca: leitura em `queries`, escrita em `commands`.
"""
import traceback

from flask import jsonify, request, session

from apps.pages import blueprint
from apps.pages.features.swap_cetes import commands, domain, queries

API = '/api/new-deals/swap-cetes'
PAGE = 'Swap Cetes'        # o rótulo `page` das notificações = `label` do catálogo (três mapas, §8)


def _R():
    from apps.pages import routes
    return routes


def _err(code, message, status, **extra):
    corpo = {'success': False, 'code': code, 'message': message, 'params': extra.pop('params', {})}
    corpo.update(extra)
    return jsonify(corpo), status


def _auth():
    if not session.get('authenticated'):
        return _err('not_authenticated', 'Not authenticated', 401)
    return None


def _notify(action, detail):
    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                              action, PAGE, detail)


@blueprint.route(API, methods=['GET'])
def api_swap_cetes():
    err = _auth()
    if err:
        return err
    rows = queries.entries(request.args.get('date', '').strip(),
                           request.args.get('date_from', '').strip(),
                           request.args.get('date_to', '').strip())
    return jsonify({'success': True, 'entries': rows, 'backend': True, 'fields': list(domain.FIELDS)})


@blueprint.route(API + '/import-file', methods=['POST'])
def api_swap_cetes_import():
    """O e-mail das Cetes do dropzone (multipart `file`) → um deal por bloco
    `cetip usd irs`. Com `dry_run=1` só parseia (a tela confere as duplicatas
    e grava pelo batch)."""
    err = _auth()
    if err:
        return err
    f = request.files.get('file')
    if f is None or not f.filename:
        return _err('swc_no_file', 'No file received', 400)
    ref_dt = _R()._api_ref_date(request.form.get('trade_date'))
    dry_run = (request.args.get('dry_run') in ('1', 'true', 'yes')
               or request.form.get('dry_run') in ('1', 'true', 'yes'))
    try:
        result = commands.import_upload(f.filename, f.read(), ref_dt, sid=session.get('user_sid', ''),
                                        dry_run=dry_run)
    except ValueError as exc:
        return _err('swc_unreadable', 'Could not read the file: ' + str(exc), 400,
                    params={'reason': str(exc)})
    except Exception as exc:                                # noqa: BLE001
        _R().log.error('[SWAP CETES] import failed:\n%s', traceback.format_exc())
        motivo = '%s: %s' % (type(exc).__name__, exc)
        return _err('swc_import_failed', 'Import failed: ' + motivo, 500, params={'reason': motivo})
    if not result.get('deals'):
        return _err('swt_no_cetip_irs', 'Nothing to import — the e-mail has no "cetip usd irs" block '
                    '(#N cetip usd irs, then label: value lines).', 400, ignored=result.get('ignored', []))
    if not dry_run and result.get('imported'):
        _notify('Deals Imported', '%d deal(s) from %s' % (result['imported'], f.filename))
    result['file'] = f.filename
    return jsonify(result)


@blueprint.route(API + '/cache/batch', methods=['POST'])
def api_swap_cetes_batch():
    err = _auth()
    if err:
        return err
    deals = (request.get_json(silent=True) or {}).get('deals')
    if not isinstance(deals, list) or not deals:
        return _err('swc_no_rows', 'No deals provided', 400)
    try:
        n = commands.persist_deals(deals, sid=session.get('user_sid', ''))
    except Exception as exc:                                # noqa: BLE001
        _R().log.error('[SWAP CETES] batch failed:\n%s', traceback.format_exc())
        motivo = '%s: %s' % (type(exc).__name__, exc)
        return _err('swc_save_failed', 'Save failed: ' + motivo, 500, params={'reason': motivo})
    if n:
        _notify('Deals Imported', '%d deal(s) imported from the Cetes e-mail' % n)
    return jsonify({'success': True, 'imported': n, 'deals': deals})


@blueprint.route(API + '/cache/search', methods=['POST'])
def api_swap_cetes_search():
    """O filtro inteligente — o MESMO contrato das páginas de New Deals."""
    err = _auth()
    if err:
        return err
    filters = (request.get_json(silent=True) or {}).get('filters', [])
    if not isinstance(filters, list):
        filters = []
    matched = [d for d in queries.entries() if _R()._deal_matches(d, filters)]
    return jsonify({'success': True, 'deals': matched, 'backend': True, 'fields': list(domain.FIELDS)})


@blueprint.route(API + '/edit', methods=['POST'])
def api_swap_cetes_edit():
    err = _auth()
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    deal_id = str(payload.get('deal_id') or '').strip()
    if not deal_id:
        return _err('swc_missing_deal_id', 'Missing deal_id', 400)
    d, mapped = commands.edit(deal_id, str(payload.get('trade_date') or ''), payload.get('changes') or {},
                              sid=session.get('user_sid', ''))
    if d is None:
        return _err('swc_not_found', 'Entry not found', 404)
    if mapped:
        _notify('B3 Mapped', '1 deal mapped — B3 ID ' + str(d.get('B3ID') or ''))
    else:
        _notify('Deal Updated', 'Tranche %s %s' % (d.get('Tranche') or '', d.get('Block') or deal_id))
    return jsonify({'success': True, 'entry': d})


@blueprint.route(API + '/add', methods=['POST'])
def api_swap_cetes_add():
    err = _auth()
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    d = commands.add(payload.get('fields') or {}, payload.get('trade_date'), sid=session.get('user_sid', ''))
    _notify('Deal Added', 'Tranche %s %s' % (d.get('Tranche') or '', d['_id']))
    return jsonify({'success': True, 'entry': d})


@blueprint.route(API + '/confirm', methods=['POST'])
def api_swap_cetes_confirm():
    """Confirm: New → Approved direto (quem confirma vira Maker); Amend →
    Approved; Pending → Approved exige outro usuário (maker ≠ checker)."""
    err = _auth()
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    deal_id = str(payload.get('deal_id') or '').strip()
    if not deal_id:
        return _err('swc_missing_deal_id', 'Missing deal_id', 400)
    d, code = commands.set_status(deal_id, str(payload.get('trade_date') or ''), 'Approved',
                                  sid=session.get('user_sid', ''))
    if d is None:
        status, msg = {'swc_not_found': (404, 'Entry not found'),
                       'swc_maker_checker': (403, 'Maker cannot approve their own change — a different '
                                                  'user must check it.'),
                       }.get(code, (400, 'Only New or Pending entries can be approved.'))
        return _err(code, msg, status)
    _notify('Status Updated', deal_id + ' → ' + d['Status'])
    return jsonify({'success': True, 'entry': d})


@blueprint.route(API + '/delete', methods=['POST'])
def api_swap_cetes_delete():
    err = _auth()
    if err:
        return err
    items = (request.get_json(silent=True) or {}).get('items')
    if not isinstance(items, list) or not items:
        return _err('swc_no_rows', 'No rows provided', 400)
    apagados, nao = commands.delete(items)
    if apagados:
        _notify('Deals Deleted', '%d deal(s)' % apagados)
    return jsonify({'success': True, 'deleted': apagados, 'not_found': nao})


@blueprint.route(API + '/preview', methods=['GET'])
def api_swap_cetes_preview():
    """Os dois arquivos de UM deal (Banco e Lawton), campo a campo e a linha
    inteira — o preview do duplo clique. Lacuna → 422 com as lacunas."""
    err = _auth()
    if err:
        return err
    deal_id = str(request.args.get('deal_id') or '').strip()
    _fp, lst, idx = queries.find(deal_id, str(request.args.get('trade_date') or ''))
    if idx is None:
        return _err('swc_not_found', 'Entry not found', 404)
    try:
        files = commands.preview(lst[idx])
    except commands.Lacunas as exc:
        return _err('swc_lacunas', str(exc), 422, deal_id=deal_id, lacunas=exc.itens)
    except ValueError as exc:
        return _err('swc_file_failed', str(exc), 422, deal_id=deal_id, params={'reason': str(exc)})
    return jsonify({'success': True, 'deal_id': deal_id, 'files': files})


@blueprint.route(API + '/send-conecta', methods=['POST'])
def api_swap_cetes_send():
    """Gera os dois arquivos dos deals selecionados no `CONECTA_NEW_PATH` (ou
    devolve o conteúdo com `download`) e vira New/Approved → Sent."""
    err = _auth()
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    items = payload.get('items')
    if not isinstance(items, list) or not items:
        return _err('swc_no_rows', 'No rows provided', 400)
    try:
        out = commands.send(items, sid=session.get('user_sid', ''), download=bool(payload.get('download')))
    except commands.EnvioRecusado as exc:
        return _err('swc_send_refused', str(exc), 400, lacunas=exc.itens)
    except ValueError as exc:
        return _err('swc_no_rows', str(exc), 400)
    except Exception as exc:                                # noqa: BLE001
        _R().log.error('[SWAP CETES] send failed:\n%s', traceback.format_exc())
        motivo = '%s: %s' % (type(exc).__name__, exc)
        return _err('swc_send_failed', 'File generation failed: ' + motivo, 500, params={'reason': motivo})
    if not payload.get('download'):
        _notify('Sent to B3', '%d deal%s sent' % (out['count'], '' if out['count'] == 1 else 's'))
    out['success'] = True
    return jsonify(out)


@blueprint.route(API + '/mapping-b3', methods=['POST'])
def api_swap_cetes_mapping_b3():
    """O retorno da B3 → B3 ID e Success (e a Intrag Swap) nos deals da Trade
    Date. Body: { ref_date }. O veredito sai da GRAVAÇÃO (§521): `saved`."""
    err = _auth()
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    ref = _R()._api_ref_date(payload.get('ref_date'))
    try:
        results = commands.map_b3(ref.strftime('%Y-%m-%d'), sid=session.get('user_sid', ''))
    except FileNotFoundError as exc:
        return jsonify({'ok': False, 'code': 'return_folder_missing', 'error': str(exc),
                        'params': {'path': _R().RETURN_PATH}}), 404
    except Exception as exc:                                # noqa: BLE001
        _R().log.error('[SWAP CETES] mapping failed:\n%s', traceback.format_exc())
        return jsonify({'ok': False, 'error': '%s: %s' % (type(exc).__name__, exc)}), 500
    gravados = [r for r in results if r.get('saved') and r.get('status') == 'Success']
    if gravados:
        _notify('B3 Mapped', '%d deal%s mapped' % (len(gravados), '' if len(gravados) == 1 else 's'))
    return jsonify({'ok': True, 'results': results})


@blueprint.route(API + '/<path:resto>', methods=['GET', 'POST'])
def api_swap_cetes_unknown(resto):
    """Ação que esta página não tem: JSON com código, nunca a 404 em HTML."""
    err = _auth()
    if err:
        return err
    return _err('nd_unknown_action', 'Unknown action: ' + resto, 404, params={'action': resto})
