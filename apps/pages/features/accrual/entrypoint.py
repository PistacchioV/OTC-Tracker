# -*- coding: utf-8 -*-
"""As quinze rotas do Accrual de Swap."""
import os
import traceback
from datetime import datetime

from flask import jsonify, render_template, request, session

from apps.pages import blueprint
from apps.pages.features.accrual import commands, domain, queries
from apps.pages.features.accrual.infra import mappers, persistence


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


@blueprint.route('/accrual-swap')
def accrual_swap():
    if not session.get('authenticated'):
        return _R().redirect(_R().url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/accrual-swap.html', segment='accrual-swap',
                           today=_R()._br_now().strftime('%Y-%m-%d'))

@blueprint.route('/api/accrual-swap/process', methods=['POST'])
def api_accrual_swap_process():
    """Process the VCP spreadsheet → rows split into CEM/EDG/Hybrids/Commodities."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'success': False, 'error': 'No file uploaded.'}), 400
    blob = f.read()
    try:
        rows = _R()._cc_read_rows(f.filename, blob)
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception:
        _R().log.error('[accrual] read failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Failed to read the spreadsheet.'}), 500

    if len(rows) < domain._ACC_HEADER_ROW:
        return jsonify({'success': False,
                        'error': 'File has fewer than {} rows — headers expected on row {}.'
                        .format(domain._ACC_HEADER_ROW, domain._ACC_HEADER_ROW)}), 400

    result = queries._accrual_build_result(rows)
    try:
        _, saved = persistence._accrual_persist(result, f.filename)
        result['date'] = saved['date']
    except Exception:
        _R().log.error('[accrual] save failed:\n%s', traceback.format_exc())
        result['date'] = datetime.now().strftime('%Y-%m-%d')

    # O ORIGINAL vai para a pasta-fonte do dia DO DADO (result['date'] sai do
    # próprio arquivo) — a mesma que o Import from folder lê e que o End
    # Process usa como evidência. Depois do processamento, e com a falha
    # voltando no payload em vez de sumir no log (pedido 2026-09-01).
    ymd_src = str(result.get('date') or '').replace('-', '') or datetime.now().strftime('%Y%m%d')
    src_path, src_err = persistence._accrual_store_source(ymd_src, f.filename, blob)
    result['source_saved'] = src_path or ''
    if src_err:
        result['source_save_error'] = src_err

    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Accrual Imported', 'Accrual',
                         'VCP · {} classified'.format(result.get('diagnostics', {}).get('matched', 0)) + _R()._nd_token(result.get('date')))
    return jsonify(result)

@blueprint.route('/api/accrual-swap/factors', methods=['POST'])
def api_accrual_swap_factors():
    """Enrich a saved accrual day with a CEM / EDG / HYB factor file (Fator Parte/Contraparte)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'success': False, 'error': 'No file uploaded.'}), 400

    kind = (request.form.get('kind') or '').strip().lower()
    if kind not in mappers._ACC_FACTOR_KINDS:
        base = os.path.splitext(os.path.basename(f.filename))[0].lower()
        kind = ('cem' if base.startswith('cem') else 'edg' if base.startswith('edg')
                else 'hyb' if base.startswith('hyb') else '')
    if kind not in mappers._ACC_FACTOR_KINDS:
        return jsonify({'success': False,
                        'error': 'Unrecognised factor file (expected a CEM, EDG or HYB file).'}), 400

    path, data = persistence._accrual_load(request.form.get('date'))
    if not data or not data.get('tables'):
        return jsonify({'success': False,
                        'error': 'No accrual data for this date — process the VCP file first.'}), 400

    spec = mappers._ACC_FACTOR_KINDS[kind]
    lob  = spec['lob']
    try:
        raw  = f.read()
        fmap = spec['parser'](f.filename, raw)
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception:
        _R().log.error('[accrual] factor read failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Failed to read the factor file.'}), 500

    matched, missing = domain._acc_apply_factors(data, lob, fmap)
    try:
        persistence._accrual_save(path, data)
    except Exception:
        _R().log.error('[accrual] factor save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Failed to save the enriched data.'}), 500

    # O arquivo de fatores solto no dropzone também vai para a pasta-fonte do
    # dia — mesma regra do /process (ver o comentário lá).
    ymd_src = str(data.get('date') or '').replace('-', '') or datetime.now().strftime('%Y%m%d')
    src_path, src_err = persistence._accrual_store_source(ymd_src, f.filename, raw)

    _R().log.info('[accrual] %s factors: %d mapped, %d matched, %d missing', lob, len(fmap), matched, missing)
    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Accrual Mapped', 'Accrual',
                         '{} · {} matched, {} missing'.format(lob, matched, missing) + _R()._nd_token(data.get('date')))
    out = {
        'success': True,
        'headers': data.get('headers') or list(domain._ACC_FIXED_HEADERS),
        'tables':  data.get('tables') or {},
        'counts':  data.get('counts') or {},
        'ref_date': data.get('ref_date'),
        'date': data.get('date'),
        'factors': {'lob': lob, 'matched': matched, 'missing': missing, 'mapped': len(fmap)},
        'source_saved': src_path or '',
    }
    if src_err:
        out['source_save_error'] = src_err
    return jsonify(out)

@blueprint.route('/api/accrual-swap/import-folder', methods=['POST'])
def api_accrual_import_folder():
    """Run the whole pipeline by reading the run folder directly (no dropzone): pick
    the VCP file → split into the four books, then apply any CEM/EDG/HYB factor file
    found alongside it. Persists under the selected date."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p   = request.get_json(silent=True) or {}
    ymd = _R()._accrual_parse_date(p.get('date')) or datetime.now().strftime('%Y%m%d')
    folder = persistence._accrual_source_dir(ymd)
    if not os.path.isdir(folder):
        return jsonify({'success': False, 'error': 'Folder not found: {}'.format(folder)}), 400

    files = [fn for fn in os.listdir(folder) if os.path.isfile(os.path.join(folder, fn))]
    vcp = next((fn for fn in files if domain._accrual_is_vcp_name(fn)), None)
    if not vcp:
        return jsonify({'success': False,
                        'error': 'No VCP file found in {}'.format(folder)}), 400

    try:
        with open(os.path.join(folder, vcp), 'rb') as fh:
            rows = _R()._cc_read_rows(vcp, fh.read())
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception:
        _R().log.error('[accrual] folder VCP read failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Failed to read the VCP file.'}), 500
    if len(rows) < domain._ACC_HEADER_ROW:
        return jsonify({'success': False,
                        'error': 'VCP file has fewer than {} rows.'.format(domain._ACC_HEADER_ROW)}), 400

    result = queries._accrual_build_result(rows)
    path, data = persistence._accrual_persist(result, vcp, ymd=ymd)

    # Apply each factor file present in the folder (CEM / EDG / HYB), in turn.
    applied = []
    for kind, spec in mappers._ACC_FACTOR_KINDS.items():
        fn = next((x for x in files
                   if os.path.splitext(x)[0].lower().startswith(kind)), None)
        if not fn:
            continue
        try:
            with open(os.path.join(folder, fn), 'rb') as fh:
                fmap = spec['parser'](fn, fh.read())
            m, miss = domain._acc_apply_factors(data, spec['lob'], fmap)
            applied.append({'kind': kind, 'lob': spec['lob'], 'file': fn,
                            'matched': m, 'missing': miss, 'mapped': len(fmap)})
        except Exception:
            _R().log.error('[accrual] folder factor (%s) failed:\n%s', kind, traceback.format_exc())
            applied.append({'kind': kind, 'lob': spec['lob'], 'file': fn, 'error': True})

    try:
        persistence._accrual_save(path, data)
    except Exception:
        _R().log.error('[accrual] folder save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Failed to save the imported data.'}), 500

    _R().log.info('[accrual] folder import %s: VCP=%s, factors=%s', folder, vcp,
             ', '.join('{}:{}'.format(a['kind'], a.get('matched', 'err')) for a in applied))
    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Accrual Imported', 'Accrual',
                         'Folder · {} classified · {} factor file(s)'.format(
                             result.get('diagnostics', {}).get('matched', 0), len(applied)) + _R()._nd_token(ymd))
    return jsonify({
        'success': True,
        'headers': data.get('headers') or list(domain._ACC_FIXED_HEADERS),
        'tables':  data.get('tables') or {},
        'counts':  data.get('counts') or {},
        'ref_date': data.get('ref_date'),
        'date': data.get('date'),
        'diagnostics': result.get('diagnostics', {}),
        'folder': folder, 'vcp_file': vcp, 'applied': applied,
    })

@blueprint.route('/api/accrual-swap/data')
def api_accrual_data():
    """Return the saved accrual JSON for a given date (?date=YYYY-MM-DD, default today)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    _, data = persistence._accrual_load(request.args.get('date'))
    if not data:
        return jsonify({'success': True, 'empty': True})
    data['success'] = True
    return jsonify(data)

@blueprint.route('/api/accrual-swap/latest')
def api_accrual_latest():
    """Most recent saved accrual date (YYYY-MM-DD) so the page can land on real
    data by default — e.g. when opened from a bell notification."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    return jsonify({'success': True, 'date': persistence._accrual_latest_ymd()})

@blueprint.route('/api/accrual-swap/row/delete', methods=['POST'])
def api_accrual_row_delete():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    lob, rid = p.get('lob'), str(p.get('id', ''))
    path, data = persistence._accrual_load(p.get('date'))
    if not data or lob not in (data.get('tables') or {}):
        return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404
    data['tables'][lob] = [r for r in data['tables'][lob] if not (r and str(r[-1]) == rid)]
    try:
        persistence._accrual_save(path, data)
    except Exception:
        _R().log.error('[accrual] save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Save failed.'}), 500
    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Accrual Deleted', 'Accrual', '{} · 1 row'.format(lob) + _R()._nd_token(data.get('date')))
    return jsonify({'success': True, 'counts': data['counts']})

@blueprint.route('/api/accrual-swap/rows/delete', methods=['POST'])
def api_accrual_rows_delete():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    lob = p.get('lob')
    ids = set(str(x) for x in (p.get('ids') or []))
    path, data = persistence._accrual_load(p.get('date'))
    if not data or lob not in (data.get('tables') or {}):
        return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404
    data['tables'][lob] = [r for r in data['tables'][lob] if not (r and str(r[-1]) in ids)]
    try:
        persistence._accrual_save(path, data)
    except Exception:
        _R().log.error('[accrual] save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Save failed.'}), 500
    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Accrual Deleted', 'Accrual', '{} · {} rows'.format(lob, len(ids)) + _R()._nd_token(data.get('date')))
    return jsonify({'success': True, 'counts': data['counts']})

@blueprint.route('/api/accrual-swap/row/edit', methods=['POST'])
def api_accrual_row_edit():
    """Edit a row's data cells → status Pending, maker = current user (checker reset)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    lob, rid = p.get('lob'), str(p.get('id', ''))
    cells = p.get('cells') or []
    sid = session.get('user_sid', '')
    path, data = persistence._accrual_load(p.get('date'))
    if not data or lob not in (data.get('tables') or {}):
        return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404
    target = domain._accrual_find(data, lob, rid)
    if target is None:
        return jsonify({'success': False, 'error': 'Row not found.'}), 404
    ndata = len(target) - 4                         # cells before status/maker/checker/id
    for i in range(min(len(cells), ndata)):
        target[i] = cells[i]
    target[-4], target[-3], target[-2] = 'Pending', sid, ''   # status, maker, checker
    try:
        persistence._accrual_save(path, data)
    except Exception:
        _R().log.error('[accrual] save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Save failed.'}), 500
    _R()._create_notification(sid, session.get('user_name', ''),
                         'Accrual Updated', 'Accrual', '{} · {}'.format(lob, rid) + _R()._nd_token(data.get('date')))
    return jsonify({'success': True, 'row': target})

@blueprint.route('/api/accrual-swap/row/send', methods=['POST'])
def api_accrual_row_send():
    """Send/approve a row — maker/checker guard: the user who changed it cannot send it."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    lob, rid = p.get('lob'), str(p.get('id', ''))
    sid = session.get('user_sid', '')
    path, data = persistence._accrual_load(p.get('date'))
    if not data or lob not in (data.get('tables') or {}):
        return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404
    target = domain._accrual_find(data, lob, rid)
    if target is None:
        return jsonify({'success': False, 'error': 'Row not found.'}), 404
    maker = str(target[-3] or '')
    if maker and maker == sid:
        return jsonify({'success': False, 'error': 'same_user',
                        'message': 'A different user must send a row you changed.'}), 403
    target[-4], target[-2] = 'Sent', sid            # status, checker
    try:
        persistence._accrual_save(path, data)
    except Exception:
        _R().log.error('[accrual] save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Save failed.'}), 500
    _R()._create_notification(sid, session.get('user_name', ''),
                         'Accrual Sent', 'Accrual', '{} · {}'.format(lob, rid) + _R()._nd_token(data.get('date')))
    return jsonify({'success': True, 'row': target})

@blueprint.route('/api/accrual-swap/send-batch', methods=['POST'])
def api_accrual_send_batch():
    """Generate the CETIP PU/Factor batch files for one LOB book, split by view
    (BANCO / LAWTON / ATACAMA) into the Batch Conecta folder."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    lob = p.get('lob')
    path, data = persistence._accrual_load(p.get('date'))
    if not data or lob not in (data.get('tables') or {}):
        return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404
    missing = domain._acc_missing_accrual_rows(data, [lob])          # block when any factor is missing
    if missing:
        return jsonify({'success': False, 'error': 'missing_accrual', 'missing': missing}), 400
    ymd = _R()._accrual_parse_date(p.get('date')) or datetime.now().strftime('%Y%m%d')
    try:
        generated = commands._acc_write_batch_files(data, lob, datetime.now().strftime('%Y%m%d'),
                                           evidence_dir=persistence._accrual_source_dir(ymd))
    except ValueError:
        _R().log.error('[accrual] send-batch failed:\n%s', traceback.format_exc())
        return jsonify({'success': False,
                        'error': 'File Interpreter template missing/invalid — check /file-interpreter'}), 500
    except Exception:
        _R().log.error('[accrual] send-batch failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Failed to write the batch files.'}), 500
    if not generated:
        return jsonify({'success': False, 'error': 'No VCP records to send for this book.'}), 400
    total = sum(g['count'] for g in generated)
    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Accrual Sent', 'Accrual',
                         '{} · {} file(s), {} line(s)'.format(lob, len(generated), total) + _R()._nd_token(ymd))
    files = [{'filename': g['filename'], 'view': g['view'], 'count': g['count']} for g in generated]
    return jsonify({'success': True, 'files': files, 'total': total, 'lob': lob})

@blueprint.route('/api/accrual-swap/validation', methods=['POST'])
def api_accrual_validation():
    """EOM Validation: generate the batch files for ALL LOB books, then e-mail the
    Lawton/Atacama view files to Brazil OTC Ops for validation."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    path, data = persistence._accrual_load(p.get('date'))
    if not data or not (data.get('tables')):
        return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404

    missing = domain._acc_missing_accrual_rows(data, ['CEM', 'EDG', 'Hybrids', 'Commodities'])   # block across all books
    if missing:
        return jsonify({'success': False, 'error': 'missing_accrual', 'missing': missing}), 400

    ymd = _R()._accrual_parse_date(p.get('date')) or datetime.now().strftime('%Y%m%d')
    ref = datetime.strptime(ymd, '%Y%m%d')
    today = datetime.now().strftime('%Y%m%d')
    evidence_dir = persistence._accrual_source_dir(ymd)

    generated = []
    try:
        for lob in ('CEM', 'EDG', 'Hybrids', 'Commodities'):
            if lob in (data.get('tables') or {}):
                generated.extend(commands._acc_write_batch_files(data, lob, today, evidence_dir=evidence_dir))
    except ValueError:
        _R().log.error('[accrual] validation generate failed:\n%s', traceback.format_exc())
        return jsonify({'success': False,
                        'error': 'File Interpreter template missing/invalid — check /file-interpreter'}), 500
    except Exception:
        _R().log.error('[accrual] validation generate failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Failed to write the batch files.'}), 500
    if not generated:
        return jsonify({'success': False, 'error': 'No VCP records to validate.'}), 400

    # Attach ONLY the Lawton / Atacama view files.
    attach = [g['path'] for g in generated if g['view'] in ('LAWTON', 'ATACAMA')]
    subject = 'Accrual EOM - {} - Validation'.format(ref.strftime('%d/%m/%Y'))
    summary = [{'filename': g['filename'], 'view': g['view'], 'count': g['count']} for g in generated]

    # Render the HTML + resolve the logo HERE (needs the Flask app context), then send
    # the e-mail in a background thread so a slow/unreachable SMTP host never blocks
    # (or times out) the HTTP response — the files are already written either way.
    try:
        html = render_template(
            'pages/email-template-accrual-validation.html',
            ref_date_fmt=ref.strftime('%d/%m/%Y'), generated_files=summary,
            attachment_names=[os.path.basename(a) for a in attach],
            current_year=datetime.now().year)
        logo_path = _R()._get_logo_path()
        _R().threading.Thread(
            target=_R()._send_accrual_validation_email,
            args=(subject, html, logo_path, attach), daemon=True).start()
    except Exception:
        _R().log.error('[accrual] validation e-mail prep failed:\n%s', traceback.format_exc())

    total = sum(g['count'] for g in generated)
    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Accrual Sent', 'Accrual',
                         'EOM Validation · {} file(s), {} attached'.format(len(generated), len(attach)) + _R()._nd_token(ymd))
    return jsonify({
        'success': True,
        'files': summary,
        'attached': [os.path.basename(a) for a in attach],
        'total': total, 'mail': 'queued',
    })

@blueprint.route('/api/accrual-swap/recon', methods=['POST'])
def api_accrual_recon():
    """Reconcile the saved accrual factors against the operacoes return file (uploaded
    via the dropzone, or read from the run folder when from_folder=1)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    f = request.files.get('file')
    date_arg = request.form.get('date')
    path, data = persistence._accrual_load(date_arg)
    if not data or not data.get('tables'):
        return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404

    # O ymd ANTES do try: ele era definido só no ramo da pasta, e o caminho do
    # UPLOAD estourava NameError na notificação lá embaixo — um 500 DEPOIS de o
    # recon já ter sido salvo, que a tela mostrava como "Error" com o trabalho
    # feito (achado em 2026-09-01, na mesma mexida do store do dropzone).
    ymd = _R()._accrual_parse_date(date_arg) or datetime.now().strftime('%Y%m%d')
    blob = None
    try:
        if f and f.filename:
            blob = f.read()
            rows = _R()._cc_read_rows(f.filename, blob)
        else:
            folder = persistence._accrual_source_dir(ymd)
            op = persistence._acc_find_operacoes(folder)
            if not op:
                return jsonify({'success': False,
                                'error': 'operacoes file not found in {}'.format(folder)}), 400
            with open(op, 'rb') as fh:
                rows = _R()._cc_read_rows(os.path.basename(op), fh.read())
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception:
        _R().log.error('[accrual] recon read failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Failed to read the operacoes file.'}), 500

    summary = commands._acc_run_recon(data, rows)
    try:
        persistence._accrual_save(path, data)
    except Exception:
        _R().log.error('[accrual] recon save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Failed to save the recon result.'}), 500

    # O operações solto no dropzone também vai para a pasta-fonte do dia —
    # mesma regra do /process; do ramo da pasta ele já veio de lá.
    src_err = None
    if blob is not None:
        _sp, src_err = persistence._accrual_store_source(ymd, f.filename, blob)

    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Accrual Mapped', 'Accrual',
                         'Recon · {} ok, {} check'.format(summary['success_rows'], summary['check_rows']) + _R()._nd_token(ymd))
    out = {
        'success': True,
        'headers': data.get('headers') or list(domain._ACC_FIXED_HEADERS),
        'tables': data.get('tables') or {},
        'counts': data.get('counts') or {},
        'recon': data.get('recon') or {},
        'ref_date': data.get('ref_date'), 'date': data.get('date'),
        'summary': summary,
    }
    if src_err:
        out['source_save_error'] = src_err
    return jsonify(out)

@blueprint.route('/api/accrual-swap/row/comment', methods=['POST'])
def api_accrual_row_comment():
    """Update only the Comments cell (no status change) — used by the inline comment
    field that the recon enables on Check rows."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    lob, rid = p.get('lob'), str(p.get('id', ''))
    path, data = persistence._accrual_load(p.get('date'))
    if not data or lob not in (data.get('tables') or {}):
        return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404
    target = domain._accrual_find(data, lob, rid)
    if target is None:
        return jsonify({'success': False, 'error': 'Row not found.'}), 404
    target[-5] = str(p.get('comment', ''))                # Comments = last data cell
    try:
        persistence._accrual_save(path, data)
    except Exception:
        _R().log.error('[accrual] comment save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Save failed.'}), 500
    return jsonify({'success': True})

@blueprint.route('/api/accrual-swap/end-process', methods=['POST'])
def api_accrual_end_process():
    """Finish the EOM Accrual Swap process: every 'Check' row must be commented; then
    e-mail the final status to OTC Ops (cc Middle Office)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    path, data = persistence._accrual_load(p.get('date'))
    if not data or not data.get('tables'):
        return jsonify({'success': False, 'error': 'No saved data for this date.'}), 404

    checks, pending = domain._acc_check_status_rows(data)
    if pending:
        return jsonify({'success': False, 'error': 'uncommented', 'pending': pending}), 400

    ymd = _R()._accrual_parse_date(p.get('date')) or datetime.now().strftime('%Y%m%d')
    ref = datetime.strptime(ymd, '%Y%m%d')
    subject = 'Accrual Swap - EOM - Final Status - {}'.format(ref.strftime('%d/%m/%Y'))
    try:
        html = render_template(
            'pages/email-template-accrual-endprocess.html',
            ref_date_fmt=ref.strftime('%d/%m/%Y'), has_check=bool(checks), checks=checks,
            folder=persistence._accrual_source_dir(ymd), current_year=datetime.now().year)
        logo_path = _R()._get_logo_path()
        _R().threading.Thread(target=_R()._send_accrual_endprocess_email,
                         args=(subject, html, logo_path), daemon=True).start()
    except Exception:
        _R().log.error('[accrual] end-process e-mail prep failed:\n%s', traceback.format_exc())

    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Accrual Sent', 'Accrual',
                         'End Process · {} check row(s)'.format(len(checks)) + _R()._nd_token(ymd))
    return jsonify({'success': True, 'checks': len(checks)})
