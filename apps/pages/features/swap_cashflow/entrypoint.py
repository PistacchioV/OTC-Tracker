# -*- coding: utf-8 -*-
"""As APIs da página New Deals › Swap › Cashflow (`/new_deals-swap-cashflow`).

A página é o molde do CATÁLOGO (`new_deals/entrypoint.new_deals_product` +
`pages/new_deals-product.html`); aqui ficam só as APIs que o JS dela chama,
com o MESMO contrato do Swap Bullet. Prefixo ESTÁTICO por página (§8): as
genéricas `/api/new-deals/<product>/...` casariam o slug como produto.

Erros e avisos saem ESTRUTURADOS (§486): `{code, params, message}`, e a tela
diz pelo `_TRANS` (`e_<code>`/`w_<code>`); o `message` é só o fallback.
Só a casca: leitura em `queries`, escrita em `commands`, regra em `domain`.
"""
import traceback

from flask import jsonify, request, session

from apps.pages import blueprint
from apps.pages.features.swap_cashflow import commands, domain, queries

API = '/api/new-deals/swap-cashflow'
PAGE = 'Swap Cashflow'        # o rótulo `page` das notificações = `label` do catálogo (três mapas, §8)


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
def api_swap_cashflow():
    err = _auth()
    if err:
        return err
    rows = queries.entries(request.args.get('date', '').strip(),
                           request.args.get('date_from', '').strip(),
                           request.args.get('date_to', '').strip())
    return jsonify({'success': True, 'entries': rows, 'backend': True,
                    'fields': list(domain.SWC_FIELDS), 'labels': list(domain.SWC_LABELS)})


@blueprint.route(API + '/import-file', methods=['POST'])
def api_swap_cashflow_import():
    """O Deal Ticket do dropzone (multipart `file`; `trade_date` dd/mm/aaaa
    ou ISO, default hoje) → deals no arquivo-dia da Trade Date. Com
    `dry_run=1` só parseia (a tela confere as duplicatas e grava pelo batch)."""
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
        _R().log.error('[SWAP CASHFLOW] import failed:\n%s', traceback.format_exc())
        motivo = '%s: %s' % (type(exc).__name__, exc)
        return _err('swc_import_failed', 'Import failed: ' + motivo, 500, params={'reason': motivo})
    if not result.get('deals'):
        return _err('swc_no_deal_ticket', 'Nothing to import — the file needs a Deal Ticket (sheet/page '
                    'with Valor Base and Vencimento) or, in the e-mail body, an Onshore Swap section '
                    'of the Trade Recap.', 400, ignored=result.get('ignored', []))
    if not dry_run and result.get('imported'):
        _notify('Deals Imported', '%d deal(s) from %s' % (result['imported'], f.filename))
    result['file'] = f.filename
    return jsonify(result)


@blueprint.route(API + '/cache/batch', methods=['POST'])
def api_swap_cashflow_batch():
    """Grava os deals que a tela decidiu manter depois do dry-run. Body:
    { deals: [...] }; `_replace: true` é duplicata que a mesa mandou
    substituir (sai como Amend se a linha antiga já tinha andado)."""
    err = _auth()
    if err:
        return err
    deals = (request.get_json(silent=True) or {}).get('deals')
    if not isinstance(deals, list) or not deals:
        return _err('swc_no_rows', 'No deals provided', 400)
    try:
        n = commands.persist_deals(deals, sid=session.get('user_sid', ''))
    except Exception as exc:                                # noqa: BLE001
        _R().log.error('[SWAP CASHFLOW] batch failed:\n%s', traceback.format_exc())
        motivo = '%s: %s' % (type(exc).__name__, exc)
        return _err('swc_save_failed', 'Save failed: ' + motivo, 500, params={'reason': motivo})
    if n:
        _notify('Deals Imported', '%d deal(s) imported from Deal Ticket' % n)
    return jsonify({'success': True, 'imported': n, 'deals': deals})


@blueprint.route(API + '/cache/search', methods=['POST'])
def api_swap_cashflow_search():
    """O filtro inteligente — o MESMO contrato das páginas de New Deals:
    `filters` = [{field, type, value, mode}] pelo `_deal_matches` sobre todos
    os arquivos-dia (uma abertura por banco)."""
    err = _auth()
    if err:
        return err
    filters = (request.get_json(silent=True) or {}).get('filters', [])
    if not isinstance(filters, list):
        filters = []
    matched = [d for d in queries.entries() if _R()._deal_matches(d, filters)]
    return jsonify({'success': True, 'deals': matched, 'backend': True,
                    'fields': list(domain.SWC_FIELDS), 'labels': list(domain.SWC_LABELS)})


@blueprint.route(API + '/edit', methods=['POST'])
def api_swap_cashflow_edit():
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
        _notify('Deal Updated', d.get('Deal') or d.get('Client') or deal_id)
    return jsonify({'success': True, 'entry': d})


@blueprint.route(API + '/add', methods=['POST'])
def api_swap_cashflow_add():
    err = _auth()
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    fields = payload.get('fields') or {}
    if not str(fields.get('Client') or '').strip() and not str(fields.get('SPN') or '').strip():
        return _err('swc_client_required', 'Client or SPN is required', 400)
    d = commands.add(fields, payload.get('trade_date'), sid=session.get('user_sid', ''))
    _notify('Deal Added', d.get('Deal') or d.get('Client') or d['_id'])
    return jsonify({'success': True, 'entry': d})


@blueprint.route(API + '/confirm', methods=['POST'])
def api_swap_cashflow_confirm():
    """Confirm: New → Approved direto (quem confirma vira Maker); Amend →
    Pending; Pending → Approved exige outro usuário (maker ≠ checker)."""
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
def api_swap_cashflow_delete():
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


@blueprint.route(API + '/economic-affirmation', methods=['POST'])
def api_swap_cashflow_economic_affirmation():
    """Economic Affirmation do dia para as contrapartes INSTITUIÇÃO FINANCEIRA
    (conta CETIP própria): um rascunho .eml por contraparte com o Deal Ticket
    de cada operação — o MESMO e-mail do Swap Bullet, com a tabela Cash Flow
    embaixo quando o deal a tem."""
    err = _auth()
    if err:
        return err
    from apps.pages import otc_emails
    deals = (request.get_json(silent=True) or {}).get('deals', [])
    drafts = otc_emails.build_swap_bullet_affirmation_emails(deals if isinstance(deals, list) else [])
    if not drafts:
        return jsonify({'ok': True, 'count': 0})
    return _R()._email_drafts_response(drafts)


@blueprint.route(API + '/preview', methods=['GET'])
def api_swap_cashflow_preview():
    """Os arquivos de UM deal por visão (cliente; ou Banco + Atacama no B2B),
    campo a campo e a linha inteira — o preview do duplo clique. Deal com
    lacuna devolve 422 com as lacunas estruturadas (o que o Send recusaria)."""
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
    return jsonify({'success': True, 'deal_id': deal_id, 'files': files, 'codes': queries.codes_for(lst[idx])})


@blueprint.route(API + '/send-conecta', methods=['POST'])
def api_swap_cashflow_send():
    """Gera os arquivos dos deals selecionados no `CONECTA_NEW_PATH` (ou
    devolve o conteúdo com `download`) e vira New/Approved → Sent.
    Body: { items: [{deal_id, trade_date}], download: bool }."""
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
        _R().log.error('[SWAP CASHFLOW] send failed:\n%s', traceback.format_exc())
        motivo = '%s: %s' % (type(exc).__name__, exc)
        return _err('swc_send_failed', 'File generation failed: ' + motivo, 500, params={'reason': motivo})
    if not payload.get('download'):
        _notify('Sent to B3', '%d deal%s sent' % (out['count'], '' if out['count'] == 1 else 's'))
    out['success'] = True
    return jsonify(out)


@blueprint.route(API + '/<path:resto>', methods=['GET', 'POST'])
def api_swap_cashflow_unknown(resto):
    """Ação que esta página não tem: JSON com código, nunca a 404 em HTML (a
    tela mostraria `Unexpected token '<'`). As rotas acima são estáticas e
    vencem esta."""
    err = _auth()
    if err:
        return err
    return _err('nd_unknown_action', 'Unknown action: ' + resto, 404, params={'action': resto})
