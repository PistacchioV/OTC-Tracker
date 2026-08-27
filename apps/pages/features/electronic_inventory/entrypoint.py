# -*- coding: utf-8 -*-
"""As quatro rotas da tela Electronic Inventory.

Os helpers `_ei_*` (sanitize, long path, scan do share, localizar arquivo) NÃO
vieram: o Track Confirmations, o TED e os quatro saves de confirmação usam os
mesmos — são plataforma, alcançados por `_R()`.
"""
import os
import re
import traceback
from datetime import datetime

from flask import jsonify, request, session

from apps.pages import blueprint


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


@blueprint.route('/api/electronic-inventory/clients')
def api_ei_clients():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'unauthorized'}), 401
    root = _R().ELECTRONIC_INVENTORY_ROOT
    spn_by_key = {}
    all_ref = _R()._ei_refdata_clients()
    for name, spn in all_ref:
        spn_by_key[_R()._ei_match_key(name)] = (name, spn)
    # Cached, background-warmed share scan — never blocks on a slow network drive.
    root_exists, disk_dirs, complete = _R()._ei_scan_root()
    clients = {}
    for key, folder in disk_dirs.items():
        ref = spn_by_key.get(key)
        clients[key] = {'name': folder, 'spn': ref[1] if ref else '', 'on_disk': True}
    # Fold in RefData names not (yet) matched to a folder. When the scan is still
    # running we don't know if the folder exists, so on_disk = None (unknown) and
    # the UI shows no badge; only a COMPLETE scan justifies a "no folder" badge.
    for name, spn in all_ref:
        key = _R()._ei_match_key(name)
        if key not in clients:
            clients[key] = {'name': name, 'spn': spn,
                            'on_disk': (False if complete else None)}
    out = sorted(clients.values(), key=lambda c: c['name'].upper())
    return jsonify({'success': True, 'clients': out, 'root': root,
                    'root_exists': bool(root_exists),
                    'scan_complete': complete,
                    'share_slow': not complete,
                    'transactional_types': list(_R()._EI_TRANSACTIONAL_TYPES),
                    'confirmation_types': list(_R()._EI_CONFIRMATION_TYPES)})

@blueprint.route('/api/electronic-inventory/documents')
def api_ei_documents():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'unauthorized'}), 401
    client = (request.args.get('client') or '').strip()
    doctype = (request.args.get('type') or 'all').strip()
    if not client:
        return jsonify({'success': False, 'message': 'client required'}), 400
    base = _R()._ei_resolve_client_dir(client)
    folder_exists = bool(base) and os.path.isdir(base)
    docs = []
    if folder_exists:
        types = _R().EI_SUBFOLDERS if doctype in ('all', '', 'All') else (doctype,)
        for dt in types:
            if dt not in _R().EI_SUBFOLDERS:
                continue
            try:
                docs.extend(_R()._ei_iter_files(base, dt))
            except Exception:
                _R().log.warning('[ei] iter %s/%s failed:\n%s', client, dt, traceback.format_exc())
    docs.sort(key=lambda d: d['modified'], reverse=True)
    return jsonify({'success': True, 'documents': docs, 'client': client,
                    'folder': base or '', 'folder_exists': folder_exists})

@blueprint.route('/api/electronic-inventory/file')
def api_ei_file():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'unauthorized'}), 401
    from flask import send_file, abort
    client = (request.args.get('client') or '').strip()
    rel = (request.args.get('rel') or '').strip()
    download = request.args.get('download') in ('1', 'true', 'yes')
    if not client or not rel:
        return abort(404)
    try:
        full = _R()._ei_locate_file(client, rel)
    except ValueError:
        return abort(400)
    if not full:
        return abort(404)
    name = os.path.basename(full)
    try:
        return send_file(full, as_attachment=download, download_name=name)
    except TypeError:   # Flask < 2.0
        return send_file(full, as_attachment=download, attachment_filename=name)

@blueprint.route('/api/electronic-inventory/upload', methods=['POST'])
def api_ei_upload():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'unauthorized'}), 401
    client  = (request.form.get('client') or '').strip()
    doctype = (request.form.get('type') or '').strip()
    subtype = (request.form.get('subtype') or '').strip()
    date_s  = (request.form.get('date') or '').strip()
    f = request.files.get('file')
    if not client or doctype not in _R().EI_SUBFOLDERS or not f or not f.filename:
        return jsonify({'success': False, 'message': 'client, a valid type and a file are required'}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in _R()._EI_ALLOWED_UPLOAD:
        return jsonify({'success': False, 'message': 'File type %s is not allowed.' % (ext or '?')}), 400
    if not os.path.isdir(_R().ELECTRONIC_INVENTORY_ROOT):
        return jsonify({'success': False, 'message': 'Electronic Inventory share is not reachable.'}), 503
    digits = re.sub(r'\D', '', date_s)
    ddmmyyyy = digits if len(digits) == 8 else datetime.now().strftime('%d%m%Y')
    dd, mm, yyyy = ddmmyyyy[0:2], ddmmyyyy[2:4], ddmmyyyy[4:8]
    base = _R()._ei_resolve_client_dir(client, create=True)
    cname = _R()._ei_sanitize(client)
    if doctype == 'Confirmations':
        # Confirmations: Confirmations/<yyyy>/<mm>. <Month>/<dd>/<Product>. The
        # product folder keeps a busy trading day readable instead of dumping
        # every product's PDFs side by side.
        #
        # A pasta sai do `TYPE_FOLDER`, que é o MESMO nome que o app usa ao gravar
        # a confirmação que ele gera. Antes daqui saía o nome do tipo cru, e o
        # upload de um FXO ia para `.../FXO/` enquanto o app gravava em
        # `.../FX Options/` — dois lugares para o mesmo produto, e o Monitor
        # procurando PDF só no segundo: a confirmação subida à mão ficava
        # invisível para ele, com o arquivo lá no share.
        prefix = (_R()._ei_sanitize(subtype).upper() or 'CONFIRMATION')
        pasta = _R()._mc_mod.TYPE_FOLDER.get(_R()._mc_mod.upper_norm(subtype))
        product_dir = _R()._ei_sanitize(pasta or subtype) or 'Other'
        target_dir = os.path.join(base, 'Confirmations', yyyy, _R()._ei_month_folder(mm), dd, product_dir)
    elif doctype == 'SSI':
        target_dir = os.path.join(base, 'SSI')
        prefix = 'SSI'
    else:  # Transactional
        target_dir = os.path.join(base, 'Transactional')
        prefix = (_R()._ei_sanitize(subtype).upper() or 'DOC')
    try:
        os.makedirs(_R()._ei_long_path(target_dir), exist_ok=True)
        # A counterparty can legitimately have several documents of the same kind
        # (a 2nd CGD Amendment, a 3rd, …). Number the new one instead of either
        # clobbering the previous or hiding it behind a meaningless " (2)".
        nth = _R()._ei_next_ordinal(target_dir, prefix, cname)
        style = 'hash' if doctype == 'Confirmations' else 'ordinal'
        fname = '%s%s - %s - %s%s' % (
            _R()._ei_version_prefix(nth, style), prefix, cname, ddmmyyyy, ext)
        dest = os.path.join(target_dir, fname)
        stem, e = os.path.splitext(dest)
        i = 2
        while os.path.exists(_R()._ei_long_path(dest)):   # same kind AND same date — still never clobber
            dest = '%s (%d)%s' % (stem, i, e)
            i += 1
        f.save(_R()._ei_long_path(dest))     # `dest` itself stays clean for relpath/basename below
    except Exception:
        _R().log.error('[ei] upload failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'message': 'Could not save the file to the share.'}), 500
    return jsonify({'success': True, 'saved': {
        'name': os.path.basename(dest),
        'rel': os.path.relpath(dest, base).replace('\\', '/'),
        'doctype': doctype}})
