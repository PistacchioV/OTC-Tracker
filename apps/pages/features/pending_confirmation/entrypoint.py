# -*- coding: utf-8 -*-
"""As rotas de Pending Confirmation.

Só a casca: os três DuckDB e as regras _pc_* são plataforma — meia dúzia de features as consome — o resto fica no routes até a fase platform/, alcançado por _R().
"""
import json
import os
import traceback
from datetime import datetime

from flask import (jsonify, redirect, render_template, request,
                   send_file, session, url_for)

from apps.pages import blueprint


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


@blueprint.route('/api/pending-confirmation/snapshot')
def api_pending_confirmation_snapshot():
    """A FOTO de um dia do Pending Confirmation, no formato {columns, rows} —
    é o que o Advanced Export consulta para montar um arquivo de vários dias.

    A tela mostra a situação de AGORA, que é viva: o Aging e o Status são
    recalculados na leitura, e a linha muda de banco quando o prazo vira. A
    série só existe porque a manutenção das 11:30 grava uma foto por dia
    (`cache/pending-confirmation/AAAA/MM/DD`), e é ela que responde aqui.

    Dia sem foto devolve `rows: []` e **200**, não 404: quem pede um intervalo
    manda vinte datas de uma vez, e um dia sem movimento (feriado, ou anterior à
    primeira foto gravada) não é erro — é dia sem linha. As COLUNAS vão em
    qualquer caso, senão o consumidor não teria como montar o cabeçalho de um
    intervalo que começa num feriado.

    A foto é devolvida como está gravada, SEM refiltrar por categoria: ela já é
    o balde `pending` daquele dia, e recomputar responderia pelo calendário de
    hoje — a mesma regra da planilha de métricas com data anterior (§).
    """
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    ds = (request.args.get('date') or '').strip()[:10]
    try:
        ref = datetime.strptime(ds, '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid date'}), 400
    path = os.path.join(_R()._PC_SNAPSHOT_DIR, ref.strftime('%Y'), ref.strftime('%m'),
                        ref.strftime('%d'),
                        'pending-confirmation_{}.json'.format(ref.strftime('%Y%m%d')))
    recs = []
    if os.path.isfile(path):
        try:
            with open(path, encoding='utf-8') as fh:
                data = json.load(fh)
            recs = data if isinstance(data, list) else []
        except (json.JSONDecodeError, IOError, OSError):
            _R().log.warning('[pc-snapshot] %s ilegível:\n%s', path, traceback.format_exc())
    rows = [[('' if r.get(c) is None else str(r.get(c, ''))) for c in _R()._PC_COLUMNS]
            for r in recs if isinstance(r, dict)]
    return jsonify({'success': True, 'columns': list(_R()._PC_COLUMNS), 'rows': rows,
                    'date': ref.strftime('%Y-%m-%d'), 'found': os.path.isfile(path)})

@blueprint.route('/api/pending-confirmation/search', methods=['POST'])
def api_pending_confirmation_search():
    """Return Pending Confirmation rows filtered by the smart-filter chips. A
    Status chip (Pending / Ok / Backlog) narrows the search to that one DB;
    without it, all three DBs are searched. Every other chip filters the rows via
    _deal_matches."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    body = request.get_json(silent=True) or {}
    filters = body.get('filters', []) or []
    has_status = any(_R()._pc_norm(f.get('field', '')) == 'status' for f in filters)
    if has_status:
        # A Status chip means "rows whose CURRENT status is X". Because status is
        # recomputed at read time (e.g. a now-Exception*/OK row may still physically
        # sit in the pending DB until the daily re-route), we can't trust the DB a
        # row lives in — load all three and keep only rows whose recomputed target
        # category matches the requested one. Prevents e.g. Ok rows leaking into a
        # Pending filter.
        want = _R()._pc_category_from_filters(filters)
        seen, rows = set(), []
        for cat in ('backlog', 'pending', 'ok'):
            for r in _R()._pc_load_rows(cat):
                if _R()._pc_target_category(r) != want:
                    continue
                tn = str(r.get('Trade Number', '') or '')
                key = tn or ('#%d' % len(rows))
                if key in seen:
                    continue
                seen.add(key)
                rows.append(r)
        cats = [want]
    else:
        cats = ['backlog', 'pending', 'ok']
        rows = []
        for cat in cats:
            rows += _R()._pc_load_rows(cat)
    # The Status chip only chose the category; apply every OTHER chip to the rows.
    other = [f for f in filters if _R()._pc_norm(f.get('field', '')) != 'status']
    if other:
        rows = [r for r in rows if _R()._deal_matches(r, other)]
    return jsonify({'success': True, 'categories': cats, 'rows': rows,
                    'columns': _R()._PC_COLUMNS})

@blueprint.route('/api/pending-confirmation/upsert', methods=['POST'])
def api_pending_confirmation_upsert():
    """Persist a row edited/confirmed on the page. Refreshes aging/status and
    routes it to the right DB (pending / ok when resolved / backlog past 12
    months), removing any stale copy from the other DBs."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    body = request.get_json(silent=True) or {}
    src = body.get('row') or {}
    if not str(src.get('Trade Number', '') or '').strip():
        return jsonify({'success': False, 'message': 'Trade Number required'}), 400
    row = {c: str(src.get(c, '') or '') for c in _R()._PC_COLUMNS}
    target = _R()._pc_upsert_row(row)
    return jsonify({'success': True, 'category': target})

@blueprint.route('/api/pending-confirmation/derive', methods=['POST'])
def api_pending_confirmation_derive():
    """Recalcula as colunas derivadas de várias linhas de uma vez — é o que a
    atualização em massa chama depois de aplicar o valor na coluna escolhida.

    Uma chamada para o lote inteiro: o Reference Data é lido uma vez por
    requisição, e linha a linha seriam N leituras e N idas ao servidor."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    rows = (request.get_json(silent=True) or {}).get('rows') or []
    if not isinstance(rows, list):
        return jsonify({'success': False, 'message': 'rows must be a list'}), 400
    return jsonify({'success': True,
                    'rows': [_R()._pc_derive_row(r if isinstance(r, dict) else {}) for r in rows]})

@blueprint.route('/api/pending-confirmation/delete', methods=['POST'])
def api_pending_confirmation_delete():
    """Delete a row (by Trade Number) from all three DBs."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    tn = str((request.get_json(silent=True) or {}).get('trade_number', '') or '').strip()
    if not tn:
        return jsonify({'success': False, 'message': 'Trade Number required'}), 400
    for cat in ('backlog', 'pending', 'ok'):
        _R()._pc_delete_tn(cat, tn)
    return jsonify({'success': True})

@blueprint.route('/api/pending-confirmation/import-update', methods=['POST'])
def api_pending_confirmation_import_update():
    """Bulk-upsert operations from an uploaded 'Pending Update' xlsx."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'success': False, 'message': 'No file uploaded.'}), 400
    if not f.filename.lower().endswith('.xlsx'):
        return jsonify({'success': False, 'message': 'Please upload a .xlsx file.'}), 400
    try:
        res = _R()._pc_import_update(f.read())
    except Exception:
        _R().log.error('[pending-confirmation] update import failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'message': 'Failed to process the spreadsheet.'}), 500
    return jsonify({'success': True, 'updated': res['updated'], 'skipped': res['skipped']})

@blueprint.route('/metrics-pending-confirmation')
def metrics_pending_confirmation():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/metrics-pending-confirmation.html',
                           segment='metrics-pending-confirmation')

@blueprint.route('/api/metrics-pending-confirmation/offenders')
def api_pc_metrics_offenders():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    # Always read the live pending DuckDB (not the daily snapshot) so edits on the
    # Pending Confirmation page reflect on the dashboard immediately; snapshots
    # remain history-only (see /history).
    rows = [r for r in _R()._pc_load_rows('pending')
            if not _R()._pc_is_ok_status(r.get('Pending Status', ''))]
    return jsonify({'success': True, 'source': 'live', **_R()._pc_metrics_offenders(rows)})

@blueprint.route('/api/metrics-pending-confirmation/history')
def api_pc_metrics_history():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    return jsonify({'success': True, **_R()._pc_metrics_history()})
