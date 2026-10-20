# -*- coding: utf-8 -*-
"""As duas rotas do card Save CETIP Files."""
import os
import shutil
import tempfile
import traceback
from datetime import datetime

from flask import jsonify, request, session

from apps.pages import blueprint
from apps.pages.features.cetip import commands, domain, queries
from apps.pages.features.cetip.infra import mail, persistence
from apps.pages import data_store as _store  # noqa: E402
from apps.pages.platform import task_runs


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
        rec = persistence._load_cetip_recipients()
        return jsonify({'success': True,
                        'ss_to': rec['ss_to'] or _R().CETIP_SALES_SUPPORT_EMAIL,
                        'cem_to': rec['cem_to'] or '; '.join(_R().CETIP_CEM_LATAM_EMAILS),
                        'bacc_to': rec['bacc_to'],
                        'hub_to': rec['hub_to']})
    payload = request.get_json(silent=True) or {}
    try:
        rec, _mudou = persistence._cetip_merge_recipients(payload)
        persistence._save_cetip_recipients(rec)
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
        rec, mudou = persistence._cetip_merge_recipients(payload)
        if mudou:
            try:
                persistence._save_cetip_recipients(rec)
            except Exception:
                _R().log.error('[cetip] save recipients failed:\n%s', traceback.format_exc())
        return commands._cetip_distribute_emails(ref, dest_dir, send_mail,
                                        _R()._parse_emails(rec['ss_to']),
                                        _R()._parse_emails(rec['cem_to']),
                                        _R()._parse_emails(rec['bacc_to']),
                                        _R()._parse_emails(rec['hub_to']))

    # Os crus da data chegam na Return do Batch Conecta (20/10/2026): primeiro
    # eles vêm para a pasta de origem do dia, que é onde o cru fica guardado e
    # de onde o reprocessamento de um dia passado os lê. Saem da Return só
    # DEPOIS da rodada (mais abaixo), e só os que já estão na origem.
    ref_yymmdd = ref.strftime('%y%m%d')
    retorno = _R().CETIP_RETURN_PATH
    trazidos, errors = persistence._cetip_trazer_do_retorno(retorno, src_dir, ref_yymmdd)

    # Ensure the dated source folder exists (B3 daily drop). On Windows create it
    # in the standard layout if missing; on dev (POSIX) just error out cleanly.
    if not _store.isdir(src_dir):
        if os.name == 'nt':
            try:
                os.makedirs(src_dir, exist_ok=True)
                _R().log.info("[cetip] created source folder: %s", src_dir)
            except Exception:
                _R().log.warning("[cetip] could not create source %s:\n%s", src_dir, traceback.format_exc())
        if not _store.isdir(src_dir):
            return jsonify({'success': False,
                            'error': 'No CETIP files for {} in the Return folder ({}), and the '
                                     'source folder was not found: {}'.format(
                                         ref.strftime('%d/%m/%Y'), retorno, src_dir)}), 400

    files = [f for f in _store.listdir(src_dir) if _store.isfile(os.path.join(src_dir, f))]
    if not files:
        return jsonify({'success': False,
                        'error': 'No CETIP files for {} in the Return folder ({}) nor in the '
                                 'source folder ({})'.format(ref.strftime('%d/%m/%Y'), retorno,
                                                             src_dir)}), 400

    # Make sure the destination day folder exists before saving anything.
    os.makedirs(dest_dir, exist_ok=True)
    saved = []
    # (Sales Support / CEM Latam attachments are gathered in stage 2 from dest_dir,
    # so stage 1 only saves + e-mails OTC Ops — see _cetip_distribute_emails.)

    # One pass per rule (mirrors the independent Alteryx branches). All matched
    # files land in the single per-day destination folder, renamed. Rules with no
    # matching source file are collected in `missing` so the e-mail can flag the
    # expected-but-absent files (expected name derived from the reference date).
    missing = []
    # O arquivo salvo NÃO é o que as telas leem: quem alimenta o Live Position, o
    # Settlement Forecast, a Swap Characteristics e o Other Products é o JSON que
    # o `_b3_export_json` deriva dele. Ele é best-effort e devolve None quando
    # falha — e o retorno era DESCARTADO, então a rotina dizia "N file(s) saved"
    # e o e-mail dizia "required for the KPI generation have been saved
    # successfully" com o JSON do dia inexistente. As telas então caíam no dia
    # anterior (o walk-back de cada uma) e ficavam certas e desatualizadas ao
    # mesmo tempo, que é o pior dos dois mundos: nada na tela, no e-mail ou no
    # retorno da rotina dizia que faltava o dia.
    json_falhou = []
    # Anexos do e-mail de stage 1 (OTC Ops) — hoje só o cadastro de domínios.
    ops_anexos = []
    # O que de fato se usou da pasta de origem: o resto (os arquivos da B3 que o
    # cadastro não pede) fica guardado lá, e a rodada diz quantos são — é por
    # ele que se acha um arquivo cujo nome mudou e parou de casar.
    usados = set()
    # O cru compactado (o que vem da Return) é aberto num temporário: o que fica
    # guardado na origem é o arquivo como a B3 o entregou.
    tmp_cru = tempfile.mkdtemp(prefix='cetip-cru-')
    try:
        for rule in queries._cetip_rules():
            # A comparação é pelo nome ANTIGO (o do cadastro): o nome novo da
            # Return volta a ele sem o envelope (`domain._cetip_nome_legado`).
            # A MESMA linha pode ter mais de uma entrega da mesma data (a B3
            # reenvia com outra sequência): vale a mais nova, e as outras ficam
            # guardadas na origem sem ir para o destino.
            por_data = {}
            for name in files:
                chave = domain._cetip_nome_legado(name)
                if not rule['match'](chave.lower()):
                    continue
                dref = chave[rule['date_start']:rule['date_start'] + 6]
                por_data.setdefault(dref, []).append(name)
            if not por_data:
                try:
                    exp = rule['dest_name'](ref_yymmdd)
                except Exception:
                    exp = ''
                missing.append({'dest': exp, 'type': rule['label']})
                continue
            for dref, nomes in sorted(por_data.items()):
                usados.update(nomes)
                name = max(nomes, key=domain._cetip_ordem)
                if len(dref) < 6 or not dref.isdigit():
                    errors.append({'file': name, 'type': rule['label'],
                                   'error': 'Could not parse date from filename.'})
                    continue
                dest_name = rule['dest_name'](dref)
                dest_path = os.path.join(dest_dir, dest_name)
                try:
                    src_path = persistence._cetip_texto_cru(os.path.join(src_dir, name), tmp_cru)
                    persistence._cetip_save_file(src_path, dest_path)
                    entry = {'src': name, 'dest': dest_name, 'type': rule['label']}
                    saved.append(entry)
                    # Also emit a tidy JSON (NDF / Option / Swap / Operations), split
                    # into per-day folders (<category>/YYYY/MM/DD/).
                    if rule.get('json'):
                        if _R()._b3_export_json(dest_path, rule['json'], dest_name, dref) is None:
                            json_falhou.append({'dest': dest_name, 'type': rule['label']})
                            _R().log.warning('[cetip] %s salvo, mas o JSON do dia NAO foi gerado '
                                             '(categoria %s, ref %s): as telas que leem esse '
                                             'arquivo vao continuar no dia anterior. O motivo esta '
                                             'na linha [b3-json] logo acima.',
                                             dest_name, rule['json'].get('category', '?'), dref)
                    # INDEXADORESSWAP_VCP → refresh the VCP indexer reference JSON.
                    if rule.get('vcp_update'):
                        persistence._cetip_update_vcp_json(dest_path)
                    # CADASTROCURVASMOEDASFEEDERDOMINIOS → atualiza a base de domínios.
                    if rule.get('dominio_update'):
                        persistence._cetip_update_dominio_json(dest_path)
                    # CETIP_YYMMDD_COE → atualiza a base de ativos subjacentes.
                    if rule.get('subj_update'):
                        persistence._cetip_update_subj_json(dest_path)
                    # Anexo do e-mail de stage 1 (OTC Ops). O caminho é o do arquivo
                    # JÁ SALVO no destino — nunca o da origem: é o que foi salvo que
                    # se confere, e a origem some no dia seguinte.
                    if rule.get('attach_ops'):
                        ops_anexos.append(dest_path)
                except Exception as e:
                    errors.append({'file': name, 'type': rule['label'], 'error': str(e)})
                    continue
                # Optional secondary copy to a flat network share (mirrors Alteryx 2nd output).
                extra = rule.get('extra_dest')
                if extra:
                    try:
                        os.makedirs(extra, exist_ok=True)
                        persistence._cetip_save_file(src_path, os.path.join(extra, dest_name))
                    except Exception:
                        _R().log.warning("[cetip] secondary copy failed %s → %s:\n%s",
                                         name, extra, traceback.format_exc())
    finally:
        shutil.rmtree(tmp_cru, ignore_errors=True)

    # Os crus que vieram da Return já estão guardados na origem: saem de lá.
    do_retorno, erros_apagar = persistence._cetip_apagar_do_retorno(trazidos)
    errors.extend(erros_apagar)
    sem_cadastro = sorted(set(files) - usados)

    # O Intraday Monitor cobra o Save do dia (tarefa `save-cetip`): conta como
    # feito quando ao menos um arquivo foi salvo — pasta vazia não é rotina feita.
    if saved:
        task_runs.record('save-cetip', session.get('user_sid', ''), session.get('user_name', ''),
                         ref=ref.strftime('%Y-%m-%d'),
                         summary={'saved': len(saved), 'missing': len(missing)})

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
        if json_falhou:
            # Sem esta frase o e-mail afirma que os arquivos do KPI estão prontos
            # justamente no dia em que não estão.
            ops_msg += (' <b>Warning:</b> <b>{}</b> file(s) were saved but their per-day JSON '
                        'could <b>not</b> be generated ({}). The screens that read them '
                        '(Live Position, Settlement Forecast, Swap Characteristics, Other '
                        'Products) will keep showing the previous day until this is '
                        'reprocessed.'.format(len(json_falhou),
                                              ', '.join(j['dest'] for j in json_falhou)))
        if ops_anexos:
            ops_msg += (' The <b>{}</b> file(s) listed as attachments go with this '
                        'e-mail.'.format(len(ops_anexos)))
        mail_ops = mail._send_cetip_email(
            [_R().CETIP_OTC_OPS_EMAIL], [], 'CETIP Files Saved',
            'Hello,', ops_msg,
            ref_fmt, saved, dest_folder=dest_dir, missing=missing,
            attachments=ops_anexos)

    msg = '<b>{}</b> file(s) saved.'.format(len(saved))
    if do_retorno:
        msg += ('<br>{} raw file(s) moved from the Return folder to the source folder.'
                .format(len(do_retorno)))
    if sem_cadastro:
        msg += ('<br><span class="text-muted">{} other raw file(s) kept in the source folder '
                '— not in the CETIP Files mapping.</span>'.format(len(sem_cadastro)))
    if errors:
        msg += '<br><span class="text-warning">{} file(s) skipped/failed.</span>'.format(len(errors))
    if json_falhou:
        msg += ('<br><span class="text-warning">{} file(s) saved WITHOUT their per-day JSON '
                '({}) — the screens that read them stay on the previous day.</span>'
                .format(len(json_falhou), ', '.join(j['dest'] for j in json_falhou)))
    if send_mail and saved:
        # _send_cetip_email returns True on success or an error string on failure.
        if mail_ops is True:
            msg += '<br>Confirmation e-mail sent to OTC Ops.'
        else:
            msg += ('<br><span class="text-warning">Files saved, but the OTC Ops e-mail failed: {}</span>'
                    .format(mail_ops))

    return jsonify({'success': True, 'message': msg, 'saved': saved, 'errors': errors,
                    'json_failed': json_falhou,
                    'source': src_dir, 'destination': dest_dir,
                    'return': retorno, 'from_return': do_retorno, 'unmatched': sem_cadastro,
                    'email_sent': {'otc_ops': mail_ops}})
