# -*- coding: utf-8 -*-
"""As rotas de File Interpreter.

Só a casca: o MOTOR (_fi_*) é o gerador de layout de TODO arquivo do app — os helpers ficam no routes até a fase platform/, alcançados por _R().
"""
import os
import traceback

from flask import (jsonify, redirect, render_template, request,
                   session, url_for)

from apps.pages import blueprint


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


@blueprint.route('/file-interpreter')
def file_interpreter_page():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/file-interpreter.html', segment='file-interpreter')

@blueprint.route('/file-interface')
def file_interface_legacy():
    """URL antiga da tela (o nome sempre foi File Interpreter; a rota seguiu
    o histórico 'file-interface' até 2026-08-21). Redireciona para o nome
    atual — bookmark e link antigo não podem virar 404."""
    return redirect('/file-interpreter')

@blueprint.route('/api/file-interpreter/page-spec', methods=['GET'])
@blueprint.route('/api/file-interface/page-spec', methods=['GET'])   # alias legado
def api_file_interpreter_page_spec():
    """Spec dos templates vinculados a UMA página — o que o preview de duplo
    clique consome: ordem e rótulo dos campos, largura e os literais Fixed já
    resolvidos para aquela página. Editar o template pela tela muda o preview
    no próximo duplo clique, sem tocar em código."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    url = (request.args.get('url') or '').strip()
    out = []
    try:
        names = sorted(os.listdir(_R()._FILE_INTERPRETER_DIR))
    except OSError:
        names = []
    for fn in names:
        if not fn.endswith('.json'):
            continue
        tpl = _R()._fi_tpl_cached(fn[:-5])
        if not tpl or not any(p.get('url') == url for p in tpl.get('linked_pages', [])):
            continue
        blocks = []
        for b in tpl.get('blocks', []):
            fields = []
            for f in b.get('fields', []):
                src = _R()._fi_field_src(f, url)
                fields.append({'seq': f.get('seq', ''), 'field': f.get('field', ''),
                               'format': f.get('format', ''),
                               'width': _R()._fi_width(f.get('format')),
                               'content': f.get('content', ''),
                               'source': src.get('source', ''),
                               'source_detail': src.get('source_detail', ''),
                               'source_note': src.get('source_note', '')})
            blocks.append({'id': b.get('id', ''), 'title': b.get('title', ''),
                           'note': b.get('note', ''), 'fields': fields})
        out.append({'key': tpl.get('key'), 'name': tpl.get('name'),
                    'file_type': tpl.get('file_type'),
                    'separator': tpl.get('separator'),
                    'base_key': tpl.get('base_key', '') or '',
                    'le_pair': tpl.get('le_pair', '') or '',
                    'file_name': tpl.get('file_name', '') or '',
                    'blocks': blocks})
    return jsonify({'success': True, 'url': url, 'templates': out})

@blueprint.route('/api/file-interpreter/options', methods=['GET'])
@blueprint.route('/api/file-interface/options', methods=['GET'])   # alias legado
def api_file_interpreter_options():
    """Opções dos dropdowns de Origem: os mappings existentes no registro.
    As colunas de página não saem daqui — vivem em `linked_pages[].columns`
    de cada template, cadastráveis pela própria tela."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    return jsonify({'success': True, 'mappings': [
        {'key': k, 'label': d.get('label', k)} for k, d in sorted(_R()._MAPPING_DEFS.items())]})

@blueprint.route('/api/file-interpreter/templates', methods=['GET'])
@blueprint.route('/api/file-interface/templates', methods=['GET'])   # alias legado
def api_file_interpreter_list():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    items = []
    try:
        names = sorted(os.listdir(_R()._FILE_INTERPRETER_DIR))
    except OSError:
        names = []
    for fn in names:
        if not fn.endswith('.json'):
            continue
        t = _R()._fi_load(fn[:-5])
        if not t or not _R()._FI_KEY_RE.match(str(t.get('key', ''))):
            continue
        items.append({k: t.get(k) for k in
                      ('key', 'name', 'system_id', 'category', 'file_type',
                       'separator', 'record_length', 'status', 'linked_pages',
                       'manual_section', 'manual_pages', 'base_key', 'le_pair',
                       'variant_label', 'file_name')})
        items[-1]['blocks'] = len(t.get('blocks') or [])
        items[-1]['fields'] = sum(len(b.get('fields') or [])
                                  for b in (t.get('blocks') or []))
    return jsonify({'success': True, 'templates': items})

@blueprint.route('/api/file-interpreter/templates/<key>', methods=['GET', 'POST', 'DELETE'])
@blueprint.route('/api/file-interface/templates/<key>', methods=['GET', 'POST', 'DELETE'])   # alias legado
def api_file_interpreter_template(key):
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    if not _R()._FI_KEY_RE.match(key or ''):
        return jsonify({'success': False, 'error': 'Invalid template key.'}), 400
    if request.method == 'GET':
        t = _R()._fi_load(key)
        if not t:
            return jsonify({'success': False, 'error': 'Unknown template.'}), 404
        return jsonify({'success': True, 'template': t})
    if request.method == 'DELETE':
        with _R()._cache_lock:
            try:
                os.remove(_R()._fi_path(key))
            except FileNotFoundError:
                return jsonify({'success': False, 'error': 'Unknown template.'}), 404
            except OSError as e:
                return jsonify({'success': False, 'error': str(e)}), 500
        _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                             'File Interpreter Template Deleted', 'File Interpreter', key)
        return jsonify({'success': True})
    clean, err = _R()._fi_clean_template(key, request.get_json(silent=True) or {})
    if err:
        return jsonify({'success': False, 'error': err}), 400
    with _R()._cache_lock:
        try:
            os.makedirs(_R()._FILE_INTERPRETER_DIR, exist_ok=True)
            _R()._atomic_write_json(_R()._fi_path(key), clean)
        except Exception as e:
            _R().log.error('[file-interpreter] save failed for %s:\n%s', key, traceback.format_exc())
            return jsonify({'success': False, 'error': '{}: {}'.format(type(e).__name__, e)}), 500
    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'File Interpreter Template Updated', 'File Interpreter',
                         '{} ({} block(s))'.format(clean['name'], len(clean['blocks'])))
    return jsonify({'success': True, 'template': clean})
