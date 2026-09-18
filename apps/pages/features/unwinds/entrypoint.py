# -*- coding: utf-8 -*-
"""Rotas da recompra (unwind) de NDF de moeda — `/unwinds/ndf/fx`.

A pagina tem rota PROPRIA porque a URL tem tres segmentos: o catch-all do
`routes.py` so atende `/<template>`, e sem isto a tela responderia 404 sem
erro nenhum na subida.

So a casca: leitura em `queries`, escrita em `commands`, regra em `domain`.
"""
import traceback

from flask import jsonify, render_template, request, session

from apps.pages import blueprint
from apps.pages.features.unwinds import commands, domain, queries


def _R():
    from apps.pages import routes
    return routes


PAGE = commands.PAGE


def _auth():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    return None


@blueprint.route('/unwinds/ndf/fx')
def unwinds_ndf_fx():
    from flask import redirect, url_for
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/unwinds-ndf-fx.html', segment='unwinds-ndf-fx')


@blueprint.route('/api/unwinds/ndf/fx')
def api_unwinds_ndf_fx():
    err = _auth()
    if err:
        return err
    rows = queries.entries(request.args.get('date', '').strip(),
                           request.args.get('date_from', '').strip(),
                           request.args.get('date_to', '').strip())
    return jsonify({'success': True, 'entries': rows,
                    'fields': list(domain.UNW_FIELDS),
                    'labels': list(domain.UNW_LABELS)})


@blueprint.route('/api/unwinds/ndf/fx/import-file', methods=['POST'])
def api_unwinds_ndf_fx_import():
    """O corpo do e-mail no dropzone (multipart `file`, .htm/.html/.txt).
    `dry_run` so parseia — e a tela quem confere as duplicatas e pergunta."""
    err = _auth()
    if err:
        return err
    f = request.files.get('file')
    if f is None or not f.filename:
        return jsonify({'success': False, 'message': 'No file received'}), 400
    ref_dt = _R()._api_ref_date(request.form.get('date'))
    dry_run = (request.args.get('dry_run') in ('1', 'true', 'yes')
               or request.form.get('dry_run') in ('1', 'true', 'yes'))
    try:
        out = commands.import_email_upload(f.filename, f.read(), ref_dt=ref_dt,
                                           dry_run=dry_run)
    except ValueError as exc:
        return jsonify({'success': False, 'message': 'Could not read the e-mail: ' + str(exc)}), 400
    except Exception as exc:                                # noqa: BLE001
        _R().log.error('[UNWIND NDF FX] import failed:\n%s', traceback.format_exc())
        return jsonify({'success': False,
                        'message': 'Import failed: %s: %s' % (type(exc).__name__, exc)}), 500
    out['success'] = True
    return jsonify(out)


@blueprint.route('/api/unwinds/ndf/fx/scan', methods=['POST'])
def api_unwinds_ndf_fx_scan():
    """Roda a varredura do box AGORA. So responde onde ha Outlook (Windows):
    fora dele a falha volta com o MOTIVO, nunca como "nada encontrado"."""
    err = _auth()
    if err:
        return err
    ref_dt = _R()._api_ref_date(request.form.get('date') or
                                (request.get_json(silent=True) or {}).get('date'))
    try:
        out = commands.scan_box(ref_dt=ref_dt)
    except Exception as exc:                                # noqa: BLE001
        _R().log.error('[UNWIND NDF FX] box scan failed:\n%s', traceback.format_exc())
        return jsonify({'success': False,
                        'message': 'Box scan failed: %s: %s' % (type(exc).__name__, exc)}), 500
    out['success'] = True
    return jsonify(out)


@blueprint.route('/api/unwinds/ndf/fx/preview')
def api_unwinds_ndf_fx_preview():
    """O arquivo da B3 de UMA recompra, campo a campo e a linha inteira.
    Linha com lacuna devolve 422 dizendo quais — e o que o Send recusaria."""
    err = _auth()
    if err:
        return err
    aid = str(request.args.get('athena_id') or '').strip()
    fp, lst, idx = queries.find(aid, str(request.args.get('date') or ''))
    if idx is None:
        return jsonify({'success': False, 'message': 'Entry not found'}), 404
    try:
        files = commands.preview(lst[idx])
    except ValueError as exc:
        return jsonify({'success': False, 'message': str(exc), 'athena_id': aid}), 422
    return jsonify({'success': True, 'athena_id': aid, 'files': files,
                    'record_length': domain.TER_RECORD_LENGTH})


@blueprint.route('/api/unwinds/ndf/fx/send-conecta', methods=['POST'])
def api_unwinds_ndf_fx_send():
    """Gera o arquivo das recompras selecionadas no Batch Conecta (ou devolve
    o conteudo com `download`) e vira Imported -> Sent.
    Body: { items: [{athena_id, ref_date}], date, download: bool }."""
    err = _auth()
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    items = payload.get('items')
    if not isinstance(items, list) or not items:
        return jsonify({'success': False, 'message': 'No rows provided'}), 400
    try:
        out = commands.send(items, sid=session.get('user_sid', ''),
                            download=bool(payload.get('download')),
                            ref_date=str(payload.get('date') or ''))
    except ValueError as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400
    except Exception as exc:                                # noqa: BLE001
        _R().log.error('[UNWIND NDF FX] send failed:\n%s', traceback.format_exc())
        return jsonify({'success': False,
                        'message': 'File generation failed: %s: %s' % (type(exc).__name__, exc)}), 500
    if not payload.get('download'):
        _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                                  'Sent to B3', PAGE,
                                  '%d unwind%s sent' % (out['count'], '' if out['count'] == 1 else 's'))
    out['success'] = True
    return jsonify(out)


@blueprint.route('/api/unwinds/ndf/fx/delete', methods=['POST'])
def api_unwinds_ndf_fx_delete():
    err = _auth()
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    try:
        apagou = commands.delete(payload.get('athena_id'), str(payload.get('date') or ''))
    except ValueError as exc:
        return jsonify({'success': False, 'message': str(exc)}), 409
    if not apagou:
        return jsonify({'success': False, 'message': 'Entry not found'}), 404
    return jsonify({'success': True})
