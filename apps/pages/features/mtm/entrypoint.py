# -*- coding: utf-8 -*-
"""As dezesseis rotas do MtM de Swap."""
import os
import traceback
from datetime import datetime

from flask import jsonify, render_template, request, session

from apps.pages import blueprint
from apps.pages.features.mtm import engine


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


@blueprint.route('/mtm-swap')
def mtm_swap():
    if not session.get('authenticated'):
        return _R().redirect(_R().url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/mtm-swap.html', segment='mtm-swap',
                           today=_R()._br_now().strftime('%Y-%m-%d'))

@blueprint.route('/api/mtm-swap/data')
def api_mtm_data():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    # Ler → alterar → gravar sob o _cache_lock (só trabalho em memória aqui).
    with _R()._cache_lock:
        path, data = engine._mtm_load(request.args.get('date'))
        if not data:
            return jsonify({'success': True, 'empty': True})
        # Repair legacy datasets: canonicalize any zero MtM to 0.00 + zero comment so the
        # table shows the exact spreadsheet value (the preview/files bump it to 1 cent).
        if path and engine._mtm_normalize_zeros(data):
            try:
                _R()._atomic_write_json(path, data)
            except Exception:
                _R().log.error('[mtm] zero-normalize save failed:\n%s', traceback.format_exc())
    data['success'] = True
    return jsonify(data)

@blueprint.route('/api/mtm-swap/latest')
def api_mtm_latest():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    return jsonify({'success': True, 'date': engine._mtm_latest_ymd()})

@blueprint.route('/api/mtm-swap/mapping/add', methods=['POST'])
def api_mtm_mapping_add():
    """Append a Hybrids Trade Name mapping (B3 ID / Hybrids ID / Trade Name) to
    mapping_swap-hyb.json (used by the Hybrids MtM SUMIF)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p    = request.get_json(silent=True) or {}
    b3   = str(p.get('b3_id') or '').strip()
    hyb  = str(p.get('hybrids_id') or '').strip()
    name = str(p.get('trade_name') or '').strip()
    if not (b3 and hyb and name):
        return jsonify({'success': False, 'error': 'All three fields are required.'}), 400
    # Ler → append → gravar sob o lock: dois usuários cadastrando ao mesmo tempo
    # perderiam um dos mapeamentos (cada um gravaria a lista que leu).
    with _R()._cache_lock:
        mapping = engine._mtm_load_hyb_mapping()
        mapping.append({'b3_id': b3, 'hybrids_id': hyb, 'trade_name': name})
        try:
            _R()._atomic_write_json(engine._MTM_HYB_MAP_PATH, mapping)
        except Exception:
            _R().log.error('[mtm] mapping add failed:\n%s', traceback.format_exc())
            return jsonify({'success': False, 'error': 'Save failed.'}), 500
    return jsonify({'success': True, 'count': len(mapping),
                    'entry': {'b3_id': b3, 'hybrids_id': hyb, 'trade_name': name}})

@blueprint.route('/api/mtm-swap/import-folder', methods=['POST'])
def api_mtm_import_folder():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p   = request.get_json(silent=True) or {}
    ymd = _R()._accrual_parse_date(p.get('date')) or datetime.now().strftime('%Y%m%d')
    folder = engine._mtm_source_dir(ymd)
    if not os.path.isdir(folder):
        return jsonify({'success': False, 'error': 'Folder not found: {}'.format(folder)}), 400
    try:
        result, (swap_fn, coe_fn) = engine._mtm_build_from_folder(folder)
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception:
        _R().log.error('[mtm] import-folder failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Failed to read the MTM files.'}), 500
    if not swap_fn and not coe_fn:
        return jsonify({'success': False, 'error': 'No MTM files found in {}'.format(folder)}), 400

    result['date'] = datetime.strptime(ymd, '%Y%m%d').strftime('%Y-%m-%d')
    try:
        engine._mtm_save(engine._mtm_path_for(ymd), result)
    except Exception:
        _R().log.error('[mtm] save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Failed to save the imported data.'}), 500

    swap_n = sum(result['counts'].get(k, 0) for k in engine._MTM_SWAP_BOOKS)
    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'MTM Imported', 'MtM',
                         '{} swap · {} COE'.format(swap_n, result['counts'].get('COE', 0)) + _R()._nd_token(ymd))
    return jsonify(result)

@blueprint.route('/api/mtm-swap/row/comment', methods=['POST'])
def api_mtm_row_comment():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    with _R()._cache_lock:                        # ler → alterar → gravar
        path, data = engine._mtm_load(p.get('date'))
        if not data:
            return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404
        r = engine._mtm_find_row(data, p.get('lob', ''), p.get('id', ''))
        if not r:
            return jsonify({'success': False, 'error': 'Row not found.'}), 404
        r[len(r) - 5] = str(p.get('comment', ''))            # Comments = last data cell
        try:
            _R()._atomic_write_json(path, data)
        except Exception:
            return jsonify({'success': False, 'error': 'Save failed.'}), 500
    return jsonify({'success': True})

@blueprint.route('/api/mtm-swap/row/edit', methods=['POST'])
def api_mtm_row_edit():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    sid = session.get('user_sid', '')
    with _R()._cache_lock:                        # ler → alterar → gravar
        path, data = engine._mtm_load(p.get('date'))
        if not data:
            return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404
        r = engine._mtm_find_row(data, p.get('lob', ''), p.get('id', ''))
        if not r:
            return jsonify({'success': False, 'error': 'Row not found.'}), 404
        cells = p.get('cells', [])
        for i, v in enumerate(cells):
            if i < len(r) - 4:
                r[i] = v
        r[-4], r[-3], r[-2] = 'Pending', sid, ''             # status, maker, checker (reset)
        try:
            _R()._atomic_write_json(path, data)
        except Exception:
            return jsonify({'success': False, 'error': 'Save failed.'}), 500
    _R()._create_notification(sid, session.get('user_name', ''), 'MTM Updated', 'MtM',
                         '{} · {}'.format(p.get('lob', ''), p.get('id', '')) + _R()._nd_token(p.get('date')))
    return jsonify({'success': True, 'row': r})

@blueprint.route('/api/mtm-swap/row/send', methods=['POST'])
def api_mtm_row_send():
    """Confirm a row (New/Pending → Sent). Maker/checker guard: whoever last changed
    the row cannot confirm it — a different user must."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    sid = session.get('user_sid', '')
    # Ler → checar maker → gravar sob o lock: fora dele, dois usuários podiam
    # passar a checagem de quatro olhos na mesma linha ao mesmo tempo.
    with _R()._cache_lock:
        path, data = engine._mtm_load(p.get('date'))
        if not data:
            return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404
        r = engine._mtm_find_row(data, p.get('lob', ''), p.get('id', ''))
        if not r:
            return jsonify({'success': False, 'error': 'Row not found.'}), 404
        if str(r[-3] or '') == sid:                          # maker == current user → blocked
            return jsonify({'success': False, 'error': 'same_user'}), 403
        r[-4], r[-2] = 'Sent', sid                           # status, checker
        try:
            _R()._atomic_write_json(path, data)
        except Exception:
            return jsonify({'success': False, 'error': 'Save failed.'}), 500
    _R()._create_notification(sid, session.get('user_name', ''), 'MTM Sent', 'MtM',
                         '{} · {}'.format(p.get('lob', ''), p.get('id', '')) + _R()._nd_token(p.get('date')))
    return jsonify({'success': True, 'row': r})

@blueprint.route('/api/mtm-swap/row/delete', methods=['POST'])
def api_mtm_row_delete():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    lob, rid = p.get('lob', ''), str(p.get('id', ''))
    with _R()._cache_lock:                        # ler → remover → gravar
        path, data = engine._mtm_load(p.get('date'))
        if not data:
            return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404
        rows = (data.get('tables') or {}).get(lob)
        if rows is None:
            return jsonify({'success': False, 'error': 'Book not found.'}), 404
        data['tables'][lob] = [r for r in rows if not (r and str(r[-1]) == rid)]
        data['counts'][lob] = len(data['tables'][lob])
        try:
            _R()._atomic_write_json(path, data)
        except Exception:
            return jsonify({'success': False, 'error': 'Save failed.'}), 500
    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'MTM Deleted', 'MtM', '{} · 1 row'.format(lob) + _R()._nd_token(p.get('date')))
    return jsonify({'success': True, 'counts': data['counts']})

@blueprint.route('/api/mtm-swap/rows/delete', methods=['POST'])
def api_mtm_rows_delete():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    lob = p.get('lob', '')
    ids = {str(x) for x in (p.get('ids') or [])}
    with _R()._cache_lock:                        # ler → remover → gravar
        path, data = engine._mtm_load(p.get('date'))
        if not data or lob not in (data.get('tables') or {}):
            return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404
        data['tables'][lob] = [r for r in data['tables'][lob] if not (r and str(r[-1]) in ids)]
        data['counts'][lob] = len(data['tables'][lob])
        try:
            _R()._atomic_write_json(path, data)
        except Exception:
            return jsonify({'success': False, 'error': 'Save failed.'}), 500
    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'MTM Deleted', 'MtM', '{} · {} rows'.format(lob, len(ids)) + _R()._nd_token(p.get('date')))
    return jsonify({'success': True, 'counts': data['counts']})

@blueprint.route('/api/mtm-swap/process', methods=['POST'])
def api_mtm_process():
    """Dropzone upload: detect swap vs COE by filename, build that portion and merge
    it into the selected date's saved dataset (the other portion is preserved)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'success': False, 'error': 'No file provided.'}), 400
    ymd = _R()._accrual_parse_date(request.form.get('date')) or datetime.now().strftime('%Y%m%d')
    try:
        rows = _R()._cc_read_rows(f.filename, f.read())
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception:
        _R().log.error('[mtm] process read failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Failed to read the file.'}), 500

    # Ler → mesclar → gravar sob o lock. A leitura da planilha já aconteceu
    # acima, então aqui dentro só roda trabalho em memória — importar dois
    # arquivos para a mesma data ao mesmo tempo não perde mais um deles.
    with _R()._cache_lock:
        # Load existing dataset for the date (or start a fresh skeleton).
        _, data = engine._mtm_load(datetime.strptime(ymd, '%Y%m%d').strftime('%Y-%m-%d'))
        if not data:
            data = {'success': True, 'tables': {k: [] for k in engine._MTM_SWAP_BOOKS},
                    'counts': {}, 'ref_date': None, 'coe_ref_date': None,
                    'date': datetime.strptime(ymd, '%Y%m%d').strftime('%Y-%m-%d')}
            data['tables']['COE'] = []

        if engine._mtm_is_cem_value_name(f.filename):
            cem_rows = (data.get('tables') or {}).get('CEM', [])
            if not cem_rows:
                return jsonify({'success': False,
                                'error': 'No CEM contracts loaded for this date — import the swap file first.'}), 400
            m, z, miss = engine._mtm_apply_cem_values(cem_rows, rows)   # Valor MTM + Missing MtM on CEM
            data['diagnostics'] = dict(data.get('diagnostics') or {},
                                       cem_value_file=f.filename, cem_matched=m, cem_zeros=z, cem_missing=miss)
        elif engine._mtm_is_edg_value_name(f.filename):
            if not (data.get('tables') or {}).get('EDG') and not (data.get('tables') or {}).get('COE'):
                return jsonify({'success': False,
                                'error': 'No EDG/COE rows loaded for this date — import the swap/COE files first.'}), 400
            em, cm, z, miss = engine._mtm_apply_edg_values(data, rows)  # JP* → COE, else EDG; + Missing MtM
            data['diagnostics'] = dict(data.get('diagnostics') or {},
                                       edg_value_file=f.filename, edg_matched=em, edg_coe_matched=cm,
                                       edg_zeros=z, edg_missing=miss)
        elif engine._mtm_is_coe_name(f.filename):
            coe_rows, coe_ref = engine._mtm_build_coe(rows)
            for i, rw in enumerate(coe_rows):
                rw.extend(['New', '', ''])
                rw.append('COE-{}'.format(i))
            data['tables']['COE'] = coe_rows
            data['coe_ref_date'] = coe_ref
        elif engine._mtm_is_swap_name(f.filename):
            buckets, ref_date, _kept, _matched = engine._mtm_build_swap(rows)
            for lob in engine._MTM_SWAP_BOOKS:
                rws = buckets.get(lob, [])
                for i, rw in enumerate(rws):
                    rw.extend(['New', '', ''])
                    rw.append('{}-{}'.format(lob, i))
                data['tables'][lob] = rws
            data['ref_date'] = ref_date
        else:
            return jsonify({'success': False,
                            'error': 'Unrecognized file. Expected the swap (…SemAtualMID), COE (…ConsultaMTMCOE), CEM values (VCP_CETIP_MTM) or EDG/COE values (Stream_level_MTM) file.'}), 400

        data['counts'] = {k: len(v) for k, v in data['tables'].items()}
        try:
            engine._mtm_save(engine._mtm_path_for(ymd), data)
        except Exception:
            _R().log.error('[mtm] process save failed:\n%s', traceback.format_exc())
            return jsonify({'success': False, 'error': 'Failed to save.'}), 500
    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'MTM Imported', 'MtM', f.filename + _R()._nd_token(ymd))
    return jsonify(data)

@blueprint.route('/api/mtm-swap/send-batch', methods=['POST'])
def api_mtm_send_batch():
    """Generate the fixed-width Conecta file(s) for ONE book (Send batch)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    lob = p.get('lob', '')
    ymd = _R()._accrual_parse_date(p.get('date')) or datetime.now().strftime('%Y%m%d')
    _, data = engine._mtm_load(datetime.strptime(ymd, '%Y%m%d').strftime('%Y-%m-%d'))
    if not data:
        return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404
    rows = (data.get('tables') or {}).get(lob) or []
    if not rows:
        return jsonify({'success': False, 'error': 'No rows in this book to generate.'}), 400
    try:
        files = engine._mtm_generate_coe(rows, ymd) if lob == 'COE' else engine._mtm_generate_book(lob, rows, ymd)
    except ValueError:
        _R().log.error('[mtm] send-batch build failed:\n%s', traceback.format_exc())
        return jsonify({'success': False,
                        'error': 'File Interpreter template missing/invalid — check /file-interpreter'}), 500
    except Exception:
        _R().log.error('[mtm] send-batch build failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Generation failed.'}), 500
    if not files:
        return jsonify({'success': False, 'error': 'Nothing to generate for this book.'}), 400
    written = engine._mtm_write_gen_files(files, ymd)
    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'MTM Sent', 'MtM',
                         '{} · {} file(s)'.format(lob, len(files)) + _R()._nd_token(ymd))
    return jsonify({'success': True, 'files': engine._mtm_gen_preview(files), 'written': len(written)})

@blueprint.route('/api/mtm-swap/row/preview', methods=['POST'])
def api_mtm_row_preview():
    """Preview the fixed-width Conecta file line(s) that ONE row would generate
    (double-click on a table row). Same generator/format as Send batch, but scoped
    to the single contract — nothing is written to disk."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    lob = p.get('lob', '')
    rid = str(p.get('id', ''))
    ymd = _R()._accrual_parse_date(p.get('date')) or datetime.now().strftime('%Y%m%d')
    _, data = engine._mtm_load(datetime.strptime(ymd, '%Y%m%d').strftime('%Y-%m-%d'))
    if not data:
        return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404
    rows = (data.get('tables') or {}).get(lob) or []
    row = next((r for r in rows if str(r[-1]) == rid), None)
    if row is None:
        return jsonify({'success': False, 'error': 'Row not found.'}), 404
    if str(row[-4]) == engine._MTM_STATUS_MISSING:
        return jsonify({'success': False, 'error': 'missing_mtm'}), 400
    try:
        files = engine._mtm_generate_coe([row], ymd) if lob == 'COE' else engine._mtm_generate_book(lob, [row], ymd)
    except ValueError:
        _R().log.error('[mtm] row preview build failed:\n%s', traceback.format_exc())
        return jsonify({'success': False,
                        'error': 'File Interpreter template missing/invalid — check /file-interpreter'}), 500
    except Exception:
        _R().log.error('[mtm] row preview build failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Generation failed.'}), 500
    if not files:
        return jsonify({'success': False, 'error': 'Nothing to generate for this row.'}), 400
    return jsonify({'success': True, 'files': engine._mtm_gen_preview(files)})

@blueprint.route('/api/mtm-swap/validation', methods=['POST'])
def api_mtm_validation():
    """EOM Validation: generate the batch files for ALL MtM books (CEM/EDG/Hybrids
    swap + COE), then e-mail the Lawton/Atacama view files to Brazil OTC Ops."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    ymd = _R()._accrual_parse_date(p.get('date')) or datetime.now().strftime('%Y%m%d')
    path, data = engine._mtm_load(datetime.strptime(ymd, '%Y%m%d').strftime('%Y-%m-%d'))
    if not data or not data.get('tables'):
        return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404

    missing = engine._mtm_missing_rows(data, list(engine._MTM_VAL_BOOKS) + ['COE'])   # block if any row lacks a value
    if missing:
        return jsonify({'success': False, 'error': 'missing_accrual', 'missing': missing}), 400

    tables = data.get('tables') or {}
    files = {}
    try:
        for lob in engine._MTM_VAL_BOOKS:
            rows = tables.get(lob) or []
            if rows:
                files.update(engine._mtm_generate_book(lob, rows, ymd))
        coe_rows = tables.get('COE') or []
        if coe_rows:
            files.update(engine._mtm_generate_coe(coe_rows, ymd))
    except Exception:
        _R().log.error('[mtm] validation generate failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Failed to write the batch files.'}), 500
    if not files:
        return jsonify({'success': False, 'error': 'No records to validate.'}), 400

    engine._mtm_write_gen_files(files, ymd)

    # All batch files generated → mark EVERY row in ALL tables as 'Sent'
    # (checker = current user) and persist, so the page reflects the finished run.
    # Recarrega DENTRO do lock: o `data` acima é de antes da geração dos arquivos,
    # que escreve no share e leva tempo — gravar aquele objeto apagaria qualquer
    # edição feita nesse meio. O lock NÃO cobre a geração, senão a aplicação
    # inteira ficaria parada durante a escrita no share.
    sid = session.get('user_sid', '')
    with _R()._cache_lock:
        path, data = engine._mtm_load(datetime.strptime(ymd, '%Y%m%d').strftime('%Y-%m-%d'))
        for lob_rows in (data.get('tables') or {}).values():
            for r in lob_rows or []:
                if r and len(r) >= 4:
                    r[-4], r[-2] = 'Sent', sid
        try:
            engine._mtm_save(path, data)
        except Exception:
            _R().log.error('[mtm] validation status save failed:\n%s', traceback.format_exc())

    ref = datetime.strptime(ymd, '%Y%m%d')
    summary = [{'filename': fn + '.txt', 'view': fd['view'], 'count': len(fd['rows'])}
               for fn, fd in files.items()]
    attach = [os.path.join(_R().CONECTA_NEW_PATH, fn + '.txt')
              for fn, fd in files.items() if fd['view'] in ('LAWTON', 'ATACAMA')]
    subject = 'MtM EOM - {} - Validation'.format(ref.strftime('%d/%m/%Y'))
    try:
        html = render_template(
            'pages/email-template-mtm-validation.html',
            ref_date_fmt=ref.strftime('%d/%m/%Y'), generated_files=summary,
            attachment_names=[os.path.basename(a) for a in attach],
            current_year=datetime.now().year)
        logo_path = _R()._get_logo_path()
        _R().threading.Thread(target=engine._send_mtm_validation_email,
                         args=(subject, html, logo_path, attach), daemon=True).start()
    except Exception:
        _R().log.error('[mtm] validation e-mail prep failed:\n%s', traceback.format_exc())

    total = sum(len(fd['rows']) for fd in files.values())
    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'MTM Sent', 'MtM',
                         'EOM Validation · {} file(s), {} attached'.format(len(files), len(attach)) + _R()._nd_token(ymd))
    return jsonify({'success': True, 'files': summary,
                    'attached': [os.path.basename(a) for a in attach],
                    'total': total, 'mail': 'queued'})

@blueprint.route('/api/mtm-swap/end-process', methods=['POST'])
def api_mtm_end_process():
    """Finish the EOM MtM Swap process: every 'Check' row must be commented; then
    e-mail the final status to Brazil OTC Ops (summary table or 'no divergence')."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    ymd = _R()._accrual_parse_date(p.get('date')) or datetime.now().strftime('%Y%m%d')
    _, data = engine._mtm_load(datetime.strptime(ymd, '%Y%m%d').strftime('%Y-%m-%d'))
    if not data or not data.get('tables'):
        return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404

    checks, pending = engine._mtm_check_status_rows(data)
    if pending:
        return jsonify({'success': False, 'error': 'uncommented', 'pending': pending}), 400

    ref = datetime.strptime(ymd, '%Y%m%d')
    subject = 'MtM Swap - EOM - Final Status - {}'.format(ref.strftime('%d/%m/%Y'))
    try:
        html = render_template(
            'pages/email-template-mtm-endprocess.html',
            ref_date_fmt=ref.strftime('%d/%m/%Y'), has_check=bool(checks), checks=checks,
            folder=engine._mtm_source_dir(ymd), current_year=datetime.now().year)
        logo_path = _R()._get_logo_path()
        _R().threading.Thread(target=engine._send_mtm_endprocess_email,
                         args=(subject, html, logo_path), daemon=True).start()
    except Exception:
        _R().log.error('[mtm] end-process e-mail prep failed:\n%s', traceback.format_exc())

    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'MTM Sent', 'MtM',
                         'End Process · {} check row(s)'.format(len(checks)) + _R()._nd_token(ymd))
    return jsonify({'success': True, 'checks': len(checks)})

@blueprint.route('/api/mtm-swap/recon', methods=['POST'])
def api_mtm_recon():
    """Reconcile the saved MtM values against the B3 ConsultaInformacoesAtualizMID
    return file (uploaded via the dropzone, or read from the run folder)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    f = request.files.get('file')
    date_arg = request.form.get('date')
    path, data = engine._mtm_load(date_arg)
    if not data or not data.get('tables'):
        return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404

    ymd = _R()._accrual_parse_date(date_arg) or datetime.now().strftime('%Y%m%d')
    try:
        if f and f.filename:
            rows = _R()._cc_read_rows(f.filename, f.read())
        else:
            op = engine._mtm_find_recon_file(engine._mtm_source_dir(ymd))
            if not op:
                return jsonify({'success': False,
                                'error': 'ConsultaInformacoesAtualizMID file not found in {}'.format(engine._mtm_source_dir(ymd))}), 400
            with open(op, 'rb') as fh:
                rows = _R()._cc_read_rows(os.path.basename(op), fh.read())
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception:
        _R().log.error('[mtm] recon read failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Failed to read the recon file.'}), 500

    # Recarrega dentro do lock: entre o load do começo e aqui houve leitura do
    # arquivo de retorno (dropzone ou share), tempo suficiente para outro usuário
    # ter mexido no dataset. A leitura do arquivo fica FORA do lock de propósito.
    with _R()._cache_lock:
        path, data = engine._mtm_load(date_arg)
        if not data or not data.get('tables'):
            return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404
        summary = engine._mtm_run_recon(data, rows)
        try:
            engine._mtm_save(path, data)
        except Exception:
            _R().log.error('[mtm] recon save failed:\n%s', traceback.format_exc())
            return jsonify({'success': False, 'error': 'Failed to save the recon result.'}), 500

    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'MTM Mapped', 'MtM',
                         'Recon · {} ok, {} check'.format(summary['success_rows'], summary['check_rows']) + _R()._nd_token(ymd))
    return jsonify({
        'success': True,
        'tables': data.get('tables') or {},
        'counts': data.get('counts') or {},
        'recon': data.get('recon') or {},
        'ref_date': data.get('ref_date'), 'date': data.get('date'),
        'summary': summary,
    })
