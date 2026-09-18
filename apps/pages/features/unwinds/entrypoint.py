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
from apps.pages import data_store as _store
from apps.pages.features.unwinds import commands, domain, queries


def _R():
    from apps.pages import routes
    return routes


PAGE = commands.PAGE

# O wiring do routes registra o scheduler com este nome (`_schedule_on_start`);
# a feature nunca sobe thread no proprio import.
start_scheduler = commands.start_scheduler


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
    # O `dry_run` é só a conferência de duplicatas do primeiro passo do Import:
    # ali nada foi gravado, e avisar seria tocar o sino por uma pergunta.
    if not dry_run and (out.get('rows') or []):
        _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                                  'Deals Imported', PAGE,
                                  '%d unwind%s imported' % (len(out['rows']),
                                                            '' if len(out['rows']) == 1 else 's'))
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
    if out.get('rows'):
        _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                                  'Deals Imported', PAGE,
                                  'Outlook box: %d unwind%s' % (len(out['rows']),
                                                                '' if len(out['rows']) == 1 else 's'))
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


@blueprint.route('/api/unwinds/ndf/fx/edit', methods=['POST'])
def api_unwinds_ndf_fx_edit():
    """Edição de linha → status `Pending` e o editor vira o maker (4 olhos).

    O mesmo contrato das páginas de Intrag: mexer na linha NÃO a manda para a
    B3 — ela sai da fila de envio até outro usuário conferir."""
    err = _auth()
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    aid = str(payload.get('athena_id') or '').strip()
    if not aid:
        return jsonify({'success': False, 'message': 'Missing athena_id'}), 400
    try:
        linha = commands.editar(aid, str(payload.get('date') or ''),
                                payload.get('fields') or {},
                                sid=session.get('user_sid', ''))
    except ValueError as exc:
        # O erro sai com CÓDIGO (§486): quem diz a frase é a tela, no idioma
        # de quem está olhando; o `message` é só o fallback.
        return jsonify({'success': False, 'code': 'unwind_already_sent',
                        'message': str(exc)}), 409
    if linha is None:
        return jsonify({'success': False, 'code': 'unwind_not_found',
                        'message': 'Entry not found'}), 404
    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                              'Deal Updated', PAGE, aid)
    return jsonify({'success': True, 'status': linha.get('Status'), 'row': linha})


@blueprint.route('/api/unwinds/ndf/fx/approve', methods=['POST'])
def api_unwinds_ndf_fx_approve():
    """`Pending` → `Approved`, com maker ≠ checker. Aprovar a própria edição é
    403: sem isso a conferência não afirma nada."""
    err = _auth()
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    aid = str(payload.get('athena_id') or '').strip()
    if not aid:
        return jsonify({'success': False, 'message': 'Missing athena_id'}), 400
    try:
        linha = commands.aprovar(aid, str(payload.get('date') or ''),
                                 sid=session.get('user_sid', ''))
    except PermissionError as exc:
        return jsonify({'success': False, 'code': 'unwind_maker_is_checker',
                        'message': str(exc)}), 403
    except ValueError as exc:
        return jsonify({'success': False, 'code': 'unwind_only_pending',
                        'message': str(exc)}), 400
    if linha is None:
        return jsonify({'success': False, 'code': 'unwind_not_found',
                        'message': 'Entry not found'}), 404
    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                              'Status Updated', PAGE, aid + ' → Approved')
    return jsonify({'success': True, 'status': linha.get('Status'), 'row': linha})


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
        return jsonify({'success': False, 'code': 'unwind_not_found',
                        'message': 'Entry not found'}), 404
    # Apagar TAMBÉM avisa, como nas páginas de New Deals ('Deal Deleted'): o
    # arquivo-dia é da mesa inteira, e a linha que sumiu sem rastro é a que
    # ninguém consegue explicar depois.
    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                              'Deal Deleted', PAGE,
                              str(payload.get('athena_id') or ''))
    return jsonify({'success': True})


# ── O Termo de Resilição (o distrato da recompra) ────────────────────────────
@blueprint.route('/confirmation/unwind/termo-resilicao')
def confirmation_unwind_termo():
    """Termo de Resilição pré-preenchido para um grupo contraparte × moeda da
    data. Rota PRÓPRIA (três segmentos), como a página da recompra."""
    from datetime import datetime

    from flask import redirect, url_for
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    ds = (request.args.get('date') or '').strip()
    acr = (request.args.get('acronym') or '').strip()
    moeda = (request.args.get('mercadoria') or '').strip().upper()
    ref = _R()._parse_date_any(ds) or datetime.now()
    linhas = queries.termo_grupo(ref.strftime('%Y-%m-%d'), acr, moeda)
    aid = (request.args.get('athena_id') or '').strip().upper()
    if aid:
        # O botão da grade abre o termo de UMA recompra; sem ele vale o grupo
        # inteiro (contraparte × moeda), que é o que a esteira gera.
        linhas = [l for l in linhas
                  if str(l.get('AthenaID') or '').strip().upper() == aid] or linhas
    if not linhas:
        return ('Nenhuma recompra para esse termo (contraparte {} × {} em {}).'
                .format(acr or '(todas)', moeda or '(todas)', ref.strftime('%d/%m/%Y')), 404)
    conf, _ = commands.termo_conf(ref, acr, moeda, linhas,
                                  sid=session.get('user_sid', ''))
    return render_template(commands.TERMO_TEMPLATE, conf=conf)


@blueprint.route('/api/unwinds/ndf/fx/termo-resilicao/save', methods=['POST'])
def api_unwinds_termo_save():
    """Grava o Termo (Word + PDF) no Electronic Inventory e carimba a linha."""
    err = _auth()
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    try:
        out = commands.termo_salvar(payload, sid=session.get('user_sid', ''))
    except ValueError as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400
    except ImportError:
        return jsonify({'success': False,
                        'message': 'reportlab is not installed — run pip install -r requirements.txt.'}), 500
    except Exception as exc:                                # noqa: BLE001
        _R().log.error('[UNWIND NDF FX] termo save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False,
                        'message': 'Could not write to the Inventory share: %s: %s'
                                   % (type(exc).__name__, exc)}), 500
    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                              'Confirmation Saved', PAGE,
                              '%s · Termo de Resilição' % (payload.get('acronym') or ''))
    out['success'] = True
    return jsonify(out)


@blueprint.route('/api/unwinds/ndf/fx/termo-resilicao/pdf')
def api_unwinds_termo_pdf():
    """Preview inline do PDF do Termo já salvo (o caminho está na linha)."""
    from flask import send_file
    err = _auth()
    if err:
        return err
    fp, lst, idx = queries.find(request.args.get('athena_id'),
                                str(request.args.get('date') or ''))
    if idx is None:
        return ('Recompra não encontrada.', 404)
    pdf = str(lst[idx].get('TermoPdf') or '')
    if not pdf or not _store.isfile(pdf):
        return ('Termo ainda não gerado para esta recompra.', 404)
    import os as _os
    return send_file(pdf, mimetype='application/pdf', as_attachment=False,
                     download_name=_os.path.basename(pdf))
