# -*- coding: utf-8 -*-
"""Rotas da página New Deals › Swap › Bullet (`/new_deals-swap-bullet`).

A página renderiza pelo catch-all do `routes.py`; aqui ficam só as APIs.
Só a casca: leitura em `queries`, escrita em `commands`, regra em `domain`.
"""
import traceback
from datetime import datetime

from flask import jsonify, request, session

from apps.pages import blueprint
from apps.pages.features.swap_bullet import commands, domain, queries


def _R():
    from apps.pages import routes
    return routes


PAGE = 'Swap Bullet'          # o rótulo `page` das notificações (três mapas, §8)


def _auth():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    return None


@blueprint.route('/api/new-deals/swap-bullet')
def api_swap_bullet():
    err = _auth()
    if err:
        return err
    rows = queries.entries(request.args.get('date', '').strip(),
                           request.args.get('date_from', '').strip(),
                           request.args.get('date_to', '').strip())
    return jsonify({'success': True, 'entries': rows,
                    'fields': list(domain.SWB_FIELDS), 'labels': list(domain.SWB_LABELS)})


@blueprint.route('/api/new-deals/swap-bullet/import-file', methods=['POST'])
def api_swap_bullet_import():
    """O Deal Ticket do dropzone (multipart `file`, .xlsx ou .pdf; `trade_date`
    dd/mm/aaaa ou ISO, default hoje) → deals no arquivo-dia da Trade Date."""
    err = _auth()
    if err:
        return err
    f = request.files.get('file')
    if f is None or not f.filename:
        return jsonify({'success': False, 'message': 'No file received'}), 400
    ref_dt = _R()._api_ref_date(request.form.get('trade_date'))
    dry_run = (request.args.get('dry_run') in ('1', 'true', 'yes')
               or request.form.get('dry_run') in ('1', 'true', 'yes'))
    try:
        result = commands.import_upload(f.filename, f.read(), ref_dt, sid=session.get('user_sid', ''),
                                        dry_run=dry_run)
    except ValueError as exc:
        return jsonify({'success': False, 'message': 'Could not read the file: ' + str(exc)}), 400
    except Exception as exc:                                # noqa: BLE001
        _R().log.error('[SWAP BULLET] import failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'message': 'Import failed: %s: %s' % (type(exc).__name__, exc)}), 500
    if not result.get('deals'):
        return jsonify({'success': False,
                        'message': 'No Deal Ticket found — the file needs a sheet/page with '
                                   'Valor Base and Vencimento.',
                        'ignored': result.get('ignored', [])}), 400
    if not dry_run:
        _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                                  'Deals Imported', PAGE,
                                  '%d deal(s) from %s' % (result['imported'], f.filename))
    result['file'] = f.filename
    return jsonify(result)


@blueprint.route('/api/new-deals/swap-bullet/cache/batch', methods=['POST'])
def api_swap_bullet_batch():
    """Grava os deals que a tela decidiu manter depois do dry-run (o passo 2
    do Import das páginas de New Deals). Body: { deals: [...] }; deal com
    `_replace: true` é duplicata que a mesa mandou substituir."""
    err = _auth()
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    deals = payload.get('deals')
    if not isinstance(deals, list) or not deals:
        return jsonify({'success': False, 'message': 'No deals provided'}), 400
    try:
        n = commands.persist_deals(deals, sid=session.get('user_sid', ''))
    except Exception as exc:                                # noqa: BLE001
        _R().log.error('[SWAP BULLET] batch failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'message': 'Save failed: %s: %s' % (type(exc).__name__, exc)}), 500
    if n:
        _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                                  'Deals Imported', PAGE, '%d deal(s) imported from Deal Ticket' % n)
    return jsonify({'success': True, 'imported': n, 'deals': deals})


@blueprint.route('/api/new-deals/swap-bullet/cache/search', methods=['POST'])
def api_swap_bullet_search():
    """A busca do filtro inteligente — o MESMO contrato das outras páginas de
    New Deals: `filters` = [{field, type, value, mode}] avaliados pelo
    `_deal_matches` sobre todos os arquivos-dia (uma abertura por banco)."""
    err = _auth()
    if err:
        return err
    filters = (request.get_json(silent=True) or {}).get('filters', [])
    if not isinstance(filters, list):
        filters = []
    matched = [d for d in queries.entries() if _R()._deal_matches(d, filters)]
    return jsonify({'success': True, 'deals': matched})


@blueprint.route('/api/new-deals/swap-bullet/edit', methods=['POST'])
def api_swap_bullet_edit():
    err = _auth()
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    deal_id = str(payload.get('deal_id') or '').strip()
    if not deal_id:
        return jsonify({'success': False, 'message': 'Missing deal_id'}), 400
    d = commands.edit(deal_id, str(payload.get('trade_date') or ''),
                      payload.get('changes') or {}, sid=session.get('user_sid', ''))
    if d is None:
        return jsonify({'success': False, 'message': 'Entry not found'}), 404
    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                              'Deal Updated', PAGE, deal_id)
    return jsonify({'success': True, 'entry': d})


@blueprint.route('/api/new-deals/swap-bullet/add', methods=['POST'])
def api_swap_bullet_add():
    err = _auth()
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    fields = payload.get('fields') or {}
    if not str(fields.get('Client') or '').strip():
        return jsonify({'success': False, 'message': 'Client is required'}), 400
    d = commands.add(fields, payload.get('trade_date'), sid=session.get('user_sid', ''))
    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                              'Deal Added', PAGE, d['Deal'])
    return jsonify({'success': True, 'entry': d})


@blueprint.route('/api/new-deals/swap-bullet/confirm', methods=['POST'])
def api_swap_bullet_confirm():
    """Confirm: New → Approved direto (quem confirma vira Maker); Pending →
    Approved exige outro usuário (maker ≠ checker)."""
    err = _auth()
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    deal_id = str(payload.get('deal_id') or '').strip()
    if not deal_id:
        return jsonify({'success': False, 'message': 'Missing deal_id'}), 400
    d, msg = commands.set_status(deal_id, str(payload.get('trade_date') or ''), 'Approved',
                                 sid=session.get('user_sid', ''))
    if d is None:
        code = 404 if msg == 'Entry not found' else (403 if 'Maker' in msg else 400)
        return jsonify({'success': False, 'message': msg}), code
    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                              'Status Updated', PAGE, deal_id + ' → Approved')
    return jsonify({'success': True, 'entry': d})


@blueprint.route('/api/new-deals/swap-bullet/delete', methods=['POST'])
def api_swap_bullet_delete():
    err = _auth()
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    items = payload.get('items')
    if not isinstance(items, list) or not items:
        return jsonify({'success': False, 'message': 'No rows provided'}), 400
    apagados, nao = commands.delete(items)
    if apagados:
        _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                                  'Deals Deleted', PAGE, '%d deal(s)' % apagados)
    return jsonify({'success': True, 'deleted': apagados, 'not_found': nao})


@blueprint.route('/api/new-deals/swap-bullet/economic-affirmation', methods=['POST'])
def api_swap_bullet_economic_affirmation():
    """Economic Affirmation do dia para as contrapartes INSTITUIÇÃO FINANCEIRA
    (conta CETIP própria no Reference Data): um rascunho .eml por contraparte
    com o Deal Ticket de cada operação — o mesmo desenho das páginas de
    Commodities (Options e NDF)."""
    err = _auth()
    if err:
        return err
    from apps.pages import otc_emails
    deals = (request.get_json(silent=True) or {}).get('deals', [])
    drafts = otc_emails.build_swap_bullet_affirmation_emails(deals)
    if not drafts:
        return jsonify({'ok': True, 'count': 0})
    return _R()._email_drafts_response(drafts)


@blueprint.route('/api/new-deals/swap-bullet/refdata')
def api_swap_bullet_refdata():
    """A contraparte do Reference Data pela SPN — o modal de edição consulta
    ao sair do campo SPN para mostrar nome, conta B3 e CNPJ antes de gravar
    (a gravação re-puxa de novo no servidor, que é quem manda)."""
    err = _auth()
    if err:
        return err
    spn = str(request.args.get('spn') or '').strip()
    rec = queries.refdata_by_spn(spn) if spn else {}
    if not rec:
        return jsonify({'success': True, 'found': False, 'spn': spn})
    import re as _re
    return jsonify({'success': True, 'found': True, 'spn': spn,
                    'client': str(rec.get('COUNTERPARTY', '') or '').strip(),
                    'account': _re.sub(r'\D', '', str(rec.get('B3 ACCOUNT', '') or '')),
                    'taxid': _re.sub(r'\D', '', str(rec.get('TAX ID', '') or ''))})


@blueprint.route('/api/new-deals/swap-bullet/preview')
def api_swap_bullet_preview():
    """Os arquivos de UM deal, por visão (cliente; ou Banco + Atacama no B2B),
    campo a campo e a linha inteira — o preview do duplo clique/botão. Deal
    com lacuna devolve 422 dizendo quais (é o que o Send recusaria)."""
    err = _auth()
    if err:
        return err
    deal_id = str(request.args.get('deal_id') or '').strip()
    fp, lst, idx = queries.find(deal_id, str(request.args.get('trade_date') or ''))
    if idx is None:
        return jsonify({'success': False, 'message': 'Entry not found'}), 404
    deal = lst[idx]
    try:
        files = commands.preview(deal)
    except ValueError as exc:
        return jsonify({'success': False, 'message': str(exc), 'deal_id': deal_id}), 422
    return jsonify({'success': True, 'deal_id': deal_id, 'files': files,
                    'codes': queries.codes_for(deal)})


@blueprint.route('/api/new-deals/swap-bullet/send-conecta', methods=['POST'])
def api_swap_bullet_send():
    """Gera os arquivos dos deals selecionados no `CONECTA_NEW_PATH` (ou
    devolve o conteúdo com `download`) e vira New/Approved → Sent.
    Body: { items: [{deal_id, trade_date}], download: bool }."""
    err = _auth()
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    items = payload.get('items')
    if not isinstance(items, list) or not items:
        return jsonify({'success': False, 'message': 'No rows provided'}), 400
    try:
        out = commands.send(items, sid=session.get('user_sid', ''), download=bool(payload.get('download')))
    except ValueError as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400
    except Exception as exc:                                # noqa: BLE001
        _R().log.error('[SWAP BULLET] send failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'message': 'File generation failed: %s: %s' % (type(exc).__name__, exc)}), 500
    if not payload.get('download'):
        _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                                  'Sent to B3', PAGE,
                                  '%d deal%s sent' % (out['count'], '' if out['count'] == 1 else 's'))
    out['success'] = True
    return jsonify(out)
