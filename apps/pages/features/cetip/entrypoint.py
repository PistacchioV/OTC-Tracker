# -*- coding: utf-8 -*-
"""As duas rotas do card Save CETIP Files."""
import os
import traceback
from datetime import datetime

from flask import jsonify, request, session

from apps.pages import blueprint
from apps.pages.features.cetip import engine


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


@blueprint.route('/api/control-panel/cetip-settlement/recipients', methods=['GET', 'POST'])
def api_cp_cetip_recipients():
    """GET → the TO lists for the four distribution e-mails (defaults shown when
    nothing is saved yet; BACC e BACC HUB não têm default e voltam vazios);
    POST → persist them. CC (OTC Ops) is fixed in code."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    if request.method == 'GET':
        rec = engine._load_cetip_recipients()
        return jsonify({'success': True,
                        'ss_to': rec['ss_to'] or _R().CETIP_SALES_SUPPORT_EMAIL,
                        'cem_to': rec['cem_to'] or '; '.join(_R().CETIP_CEM_LATAM_EMAILS),
                        'bacc_to': rec['bacc_to'],
                        'hub_to': rec['hub_to']})
    payload = request.get_json(silent=True) or {}
    try:
        rec, _mudou = engine._cetip_merge_recipients(payload)
        engine._save_cetip_recipients(rec)
    except Exception as e:
        _R().log.error('[cetip] save recipients failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': '{}: {}'.format(type(e).__name__, e)}), 500
    return jsonify({'success': True})

@blueprint.route('/api/control-panel/cetip-settlement', methods=['POST'])
def api_cp_cetip_settlement():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401

    payload   = request.get_json(silent=True) or {}
    date_str  = (payload.get('date') or '').strip()
    send_mail = payload.get('send_email', True)
    # Two-stage split: 'save' (default) saves the files/JSONs + e-mails OTC Ops only;
    # 'distribute' only e-mails the other areas (Sales Support + CEM Latam) with the
    # already-saved position files — no re-save.
    stage     = (payload.get('stage') or 'save').strip().lower()

    try:
        ref = (datetime.strptime(date_str, '%Y-%m-%d') if date_str
               else _R()._prev_anbima_bizday(datetime.now()))
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid date (expected YYYY-MM-DD).'}), 400

    # Folder pattern: YYYY\mm. Month\dd (e.g. 2026\06. June\24) — same for source
    # and destination, both keyed on the reference date.
    month_folder = ref.strftime('%m') + '. ' + _R()._EN_MONTH_NAMES[ref.month - 1]
    src_dir  = os.path.join(_R().CETIP_SOURCE_ROOT, ref.strftime('%Y'), month_folder, ref.strftime('%d'))
    dest_dir = os.path.join(_R().CETIP_DEST_ROOT,   ref.strftime('%Y'), month_folder, ref.strftime('%d'))

    # Stage 2 ("Send to other areas") — no re-save; e-mail Sales Support + CEM Latam
    # from the already-saved files. Requires stage 1 ("Save CETIP Files") to have run.
    # TO lists: run payload (what's on the card) > saved > hardcoded default; when
    # the payload carries them they are persisted for the next runs.
    if stage == 'distribute':
        # Merge, não substituição: o payload traz o que está na tela, e uma tela que
        # não conhecesse uma das quatro chaves apagaria aquela lista ao rodar.
        rec, mudou = engine._cetip_merge_recipients(payload)
        if mudou:
            try:
                engine._save_cetip_recipients(rec)
            except Exception:
                _R().log.error('[cetip] save recipients failed:\n%s', traceback.format_exc())
        return engine._cetip_distribute_emails(ref, dest_dir, send_mail,
                                        _R()._parse_emails(rec['ss_to']),
                                        _R()._parse_emails(rec['cem_to']),
                                        _R()._parse_emails(rec['bacc_to']),
                                        _R()._parse_emails(rec['hub_to']))

    # Ensure the dated source folder exists (B3 daily drop). On Windows create it
    # in the standard layout if missing; on dev (POSIX) just error out cleanly.
    if not os.path.isdir(src_dir):
        if os.name == 'nt':
            try:
                os.makedirs(src_dir, exist_ok=True)
                _R().log.info("[cetip] created source folder: %s", src_dir)
            except Exception:
                _R().log.warning("[cetip] could not create source %s:\n%s", src_dir, traceback.format_exc())
        if not os.path.isdir(src_dir):
            return jsonify({'success': False,
                            'error': 'Source folder not found: {}'.format(src_dir)}), 400

    files = [f for f in os.listdir(src_dir) if os.path.isfile(os.path.join(src_dir, f))]
    if not files:
        return jsonify({'success': False,
                        'error': 'No files found in the source folder: {}'.format(src_dir)}), 400

    # Make sure the destination day folder exists before saving anything.
    os.makedirs(dest_dir, exist_ok=True)
    saved, errors = [], []
    # (Sales Support / CEM Latam attachments are gathered in stage 2 from dest_dir,
    # so stage 1 only saves + e-mails OTC Ops — see _cetip_distribute_emails.)

    # One pass per rule (mirrors the independent Alteryx branches). All matched
    # files land in the single per-day destination folder, renamed. Rules with no
    # matching source file are collected in `missing` so the e-mail can flag the
    # expected-but-absent files (expected name derived from the reference date).
    ref_yymmdd = ref.strftime('%y%m%d')
    missing = []
    for rule in engine._cetip_rules():
        rule_matched = False
        for name in files:
            if not rule['match'](name.lower()):
                continue
            rule_matched = True
            dref = name[rule['date_start']:rule['date_start'] + 6]
            if len(dref) < 6 or not dref.isdigit():
                errors.append({'file': name, 'type': rule['label'],
                               'error': 'Could not parse date from filename.'})
                continue
            dest_name = rule['dest_name'](dref)
            dest_path = os.path.join(dest_dir, dest_name)
            src_path  = os.path.join(src_dir, name)
            try:
                engine._cetip_save_file(src_path, dest_path)
                entry = {'src': name, 'dest': dest_name, 'type': rule['label']}
                saved.append(entry)
                # Also emit a tidy JSON (NDF / Option / Swap / Operations), split
                # into per-day folders (<category>/YYYY/MM/DD/).
                if rule.get('json'):
                    _R()._b3_export_json(dest_path, rule['json'], dest_name, dref)
                # INDEXADORESSWAP_VCP → refresh the VCP indexer reference JSON.
                if rule.get('vcp_update'):
                    engine._cetip_update_vcp_json(dest_path)
            except Exception as e:
                errors.append({'file': name, 'type': rule['label'], 'error': str(e)})
                continue
            # Optional secondary copy to a flat network share (mirrors Alteryx 2nd output).
            extra = rule.get('extra_dest')
            if extra:
                try:
                    os.makedirs(extra, exist_ok=True)
                    engine._cetip_save_file(src_path, os.path.join(extra, dest_name))
                except Exception:
                    _R().log.warning("[cetip] secondary copy failed %s → %s:\n%s",
                                name, extra, traceback.format_exc())
        if not rule_matched:
            try:
                exp = rule['dest_name'](ref_yymmdd)
            except Exception:
                exp = ''
            missing.append({'dest': exp, 'type': rule['label']})

    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'CETIP Files Saved', 'Control Panel',
                         '{} file(s) saved ({})'.format(len(saved), ref.strftime('%Y-%m-%d')))

    # Stage 1 e-mail — Brazil OTC Ops only: saved-files notice + the complete list
    # (no attachment). The Sales Support + CEM Latam e-mails go out in stage 2
    # ("Send to other areas" → _cetip_distribute_emails).
    ref_fmt = ref.strftime('%d/%m/%Y')
    mail_ops = None
    if send_mail and saved:
        ops_msg = ('The CETIP files required for the KPI generation have been saved successfully. '
                   'The complete list is shown below.')
        if missing:
            ops_msg += (' <b>{}</b> expected file(s) were <b>not found</b> in the source folder '
                        'and are flagged as <i>Not found</i> in the table.'.format(len(missing)))
        mail_ops = engine._send_cetip_email(
            [_R().CETIP_OTC_OPS_EMAIL], [], 'CETIP Files Saved',
            'Hello,', ops_msg,
            ref_fmt, saved, dest_folder=dest_dir, missing=missing)

    msg = '<b>{}</b> file(s) saved.'.format(len(saved))
    if errors:
        msg += '<br><span class="text-warning">{} file(s) skipped/failed.</span>'.format(len(errors))
    if send_mail and saved:
        # _send_cetip_email returns True on success or an error string on failure.
        if mail_ops is True:
            msg += '<br>Confirmation e-mail sent to OTC Ops.'
        else:
            msg += ('<br><span class="text-warning">Files saved, but the OTC Ops e-mail failed: {}</span>'
                    .format(mail_ops))

    return jsonify({'success': True, 'message': msg, 'saved': saved, 'errors': errors,
                    'source': src_dir, 'destination': dest_dir,
                    'email_sent': {'otc_ops': mail_ops}})
