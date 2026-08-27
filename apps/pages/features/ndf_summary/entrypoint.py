# -*- coding: utf-8 -*-
"""As rotas de NDF Summary.

Só a casca: os coletores (_ndfsum_*), o overlay do dia e o TED são a família de liquidação — os helpers ficam no routes até a fase platform/, alcançados por _R().
"""
import json
import os
import re
import traceback
from datetime import datetime

from flask import (jsonify, redirect, render_template, request,
                   session, url_for)

from apps.pages import blueprint


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


@blueprint.route('/ndf-summary')
def ndf_summary():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/ndf-summary.html', segment='ndf-summary',
                           today=_R()._br_now().strftime('%Y-%m-%d'))

@blueprint.route('/api/ndf-summary/cards')
def api_ndf_summary_cards():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    # Reference date from the picker (defaults to today's D-1 ANBIMA). Cards count
    # only rows whose maturity ("Data de Vencimento") == the picker date AND whose
    # "Classe do Ativo Subjacente" == TAXAS DE CAMBIO (FX NDFs).
    ds = (request.args.get('date') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else _R()._prev_anbima_bizday(datetime.now())
    except ValueError:
        ref = _R()._prev_anbima_bizday(datetime.now())
    want_mat = ref.strftime('%Y%m%d')
    fx = _R()._fcst_norm('TAXAS DE CAMBIO')
    total = vanilla = other_publisher = t0 = 0
    # Position snapshot is always the LATEST available TER (independent of the picker,
    # which only drives the maturity filter below).
    path, dref = _R()._ndf_ter_path(_R()._prev_anbima_bizday(datetime.now()))
    if path:
        try:
            with open(path, encoding='utf-8') as fh:
                data = json.load(fh) or []
        except Exception:
            data = []
        # Resolve "Tipo do Contrato" / "Codigo da Cotacao" by header (real TER only;
        # not present in the minimal dev mock).
        tipo_key = cot_key = None
        if data:
            for k in data[0].keys():
                kn = _R()._fcst_norm(k)
                if kn in ('tipo do contrato', 'tipo de contrato'):
                    tipo_key = k
                elif kn in ('codigo da cotacao', 'codigo de cotacao'):
                    cot_key = k

        def _is_zero_cot(rec):
            v = str(rec.get(cot_key, '') if cot_key else '').strip().replace(',', '.')
            try:
                return float(v) == 0
            except ValueError:
                return True                          # empty / non-numeric → treated as 0

        for rec in data:
            if _R()._fcst_norm(str(rec.get('Classe do Ativo Subjacente', ''))) != fx:
                continue
            d = _R()._fcst_parse_date(rec.get('Data de Vencimento', ''))
            if not (d and d.strftime('%Y%m%d') == want_mat):
                continue
            total += 1
            tipo = _R()._fcst_norm(str(rec.get(tipo_key, ''))) if tipo_key else ''
            if tipo == 'sisbacen':
                if _is_zero_cot(rec):
                    t0 += 1                           # SISBACEN + Cotação = 0
                else:
                    vanilla += 1                      # SISBACEN + Cotação <> 0
            elif tipo == 'feeder':
                other_publisher += 1                  # FEEDER
    return jsonify({'success': True,
                    'cards': {'vanilla': vanilla, 'other_publisher': other_publisher,
                              't0': t0, 'total': total},
                    'ter_date': dref})

@blueprint.route('/api/ndf-summary/data')
def api_ndf_summary_data():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    ds = (request.args.get('date') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    payload = _R()._ndfsum_collect(ref)
    payload.pop('email_trades', None)          # backend-only (settlement notices)
    payload.update({'success': True, 'date': ref.strftime('%Y-%m-%d')})
    return jsonify(payload)

@blueprint.route('/api/ndf-summary/settlement-emails', methods=['POST'])
def api_ndf_summary_settlement_emails():
    """Generate the NDF settlement notices (.eml drafts) for the reference date.
    One draft per counterparty group according to its net type — Total Net: one
    netted notice; Pay/Rec: one per direction; No Net: one per trade. Delivery
    follows the New Deals premium flow (downloadable .eml/.zip, X-Unsent)."""
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    payload = request.get_json(silent=True) or {}
    ds = str(payload.get('date', '') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    from apps.pages import otc_emails
    trades = _R()._ndfsum_collect(ref).get('email_trades') or []
    # Restrict to the counterparties the user ticked on the Settlement Summary.
    # When the key is absent (other callers) we keep the previous all-rows behaviour;
    # an explicit empty list generates nothing.
    sel = payload.get('counterparties')
    if isinstance(sel, list):
        wanted = {_R()._fcst_norm(str(x)) for x in sel if str(x).strip()}
        trades = [t for t in trades if _R()._fcst_norm(str(t.get('counterparty', ''))) in wanted]
    drafts = otc_emails.build_ndf_settlement_emails(trades, ref.strftime('%d/%m/%Y'))
    if not drafts:
        return jsonify({'ok': True, 'count': 0})
    cp_count = len({d.get('counterparty', '') for d in drafts})

    # Persist Generated per notified counterparty (day overlay) — best-effort ON
    # PURPOSE: the drafts are already produced, so a failure here is logged but
    # never turns a successful generation into an error.
    try:
        path, meta = _R()._ndfsum_meta_load(ref)
        sid = session.get('user_sid', '')
        for name in {d.get('counterparty', '') for d in drafts if d.get('counterparty')}:
            entry = meta.get(name) or {}
            entry.update({'status': 'Generated', 'maker': sid,
                          'at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
            meta[name] = entry
        _R()._ndfsum_meta_save(path, meta)
    except Exception:
        _R().log.error('[ndf-summary] generated-status save failed:\n%s', traceback.format_exc())

    # Up to 2 notices → the individual .eml files (open straight in Outlook, no
    # unzip step); 3+ → a single .zip. A one-shot HTTP download can only carry one
    # file, so the ≤2 case ships the .eml bytes as base64 in JSON and the page
    # saves each one; the zip path is unchanged.
    if len(drafts) <= 2:
        files, seen = [], {}
        for d in drafts:
            base = otc_emails._safe_filename(d.get('subject', 'draft'))
            n = seen.get(base, 0)
            seen[base] = n + 1
            entry = base if n == 0 else '{}_{}'.format(base, n + 1)
            raw = otc_emails.build_eml_bytes(d, session.get('user_email'))
            files.append({'filename': entry + '.eml',
                          'b64': _R().base64.b64encode(raw).decode('ascii')})
        return jsonify({'ok': True, 'count': len(drafts),
                        'counterparties': cp_count, 'files': files})

    resp = _R()._email_drafts_response(
        drafts, zip_name='Avisos_Liquidacao_{}_NDF'.format(ref.strftime('%d%m%y')))
    resp.headers['X-Counterparty-Count'] = str(cp_count)
    return resp

@blueprint.route('/api/ndf-summary/mark-sent', methods=['POST'])
def api_ndf_summary_mark_sent():
    """Confirm action on the Settlement Summary: flip a counterparty's day-overlay
    status from Generated → Sent (persisted like the Generated flag). Only rows
    currently Generated transition; returns how many were updated."""
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    payload = request.get_json(silent=True) or {}
    ds = str(payload.get('date', '') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    names = payload.get('counterparties')
    if not isinstance(names, list):
        names = [names] if names else []
    wanted = {_R()._fcst_norm(str(n)) for n in names if str(n or '').strip()}
    if not wanted:
        return jsonify({'ok': False, 'error': 'No counterparty provided'}), 400
    try:
        path, meta = _R()._ndfsum_meta_load(ref)
        sid = session.get('user_sid', '')
        updated = 0
        for name, entry in list(meta.items()):
            if _R()._fcst_norm(name) in wanted and (entry or {}).get('status') == 'Generated':
                entry = entry or {}
                entry.update({'status': 'Sent', 'maker': sid,
                              'at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
                meta[name] = entry
                updated += 1
        if updated:
            _R()._ndfsum_meta_save(path, meta)
        return jsonify({'ok': True, 'updated': updated})
    except Exception as e:
        _R().log.error('[ndf-summary] mark-sent failed:\n%s', traceback.format_exc())
        return jsonify({'ok': False, 'error': '{}: {}'.format(type(e).__name__, e)}), 500

@blueprint.route('/api/ndf-summary/observation', methods=['POST'])
def api_ndf_summary_observation():
    """Observação livre por contraparte no Settlement Summary — persistida no
    mesmo overlay diário do status (Generated/Sent), então sobrevive a reload e
    troca de reference date. Texto vazio limpa a observação."""
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    payload = request.get_json(silent=True) or {}
    ds = str(payload.get('date', '') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    name = str(payload.get('counterparty', '') or '').strip()
    if not name:
        return jsonify({'ok': False, 'error': 'No counterparty provided'}), 400
    text = str(payload.get('text', '') or '').strip()
    try:
        path, meta = _R()._ndfsum_meta_load(ref)
        # O overlay é chaveado pelo nome exato do cockpit; casa por _fcst_norm
        # para não criar chave duplicada por diferença de caixa/espaços.
        key = next((k for k in meta if _R()._fcst_norm(k) == _R()._fcst_norm(name)), name)
        entry = meta.get(key) or {}
        if text:
            entry['obs'] = text
        else:
            entry.pop('obs', None)
        meta[key] = entry
        _R()._ndfsum_meta_save(path, meta)
        return jsonify({'ok': True})
    except Exception as e:
        _R().log.error('[ndf-summary] observation save failed:\n%s', traceback.format_exc())
        return jsonify({'ok': False, 'error': '{}: {}'.format(type(e).__name__, e)}), 500

@blueprint.route('/api/ndf-summary/ted-email', methods=['POST'])
def api_ndf_summary_ted_email():
    """TEDs button: e-mail the TED release request to OTC Ops + Settlements.
    A row qualifies when its netted Pay side is filled AND the counterparty's
    default PAY account is NOT at Banco J.P. Morgan (BCO 376 → internal book
    transfer, no TED). Split into two blocks by legal entity (BANCO / MGT);
    each counterparty's SSI (newest file in Electronic Inventory/<cpty>/SSI)
    goes attached. From = the shared OTC Tracker mailbox."""
    from email.mime.image import MIMEImage
    from email.mime.base import MIMEBase
    from email import encoders
    from apps.pages import otc_emails
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    payload = request.get_json(silent=True) or {}
    ds = str(payload.get('date', '') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()

    # Same universe and netting as the Settlement Summary, but grouped per
    # (legal entity, counterparty) so each LE gets its own e-mail block.
    trades = _R()._ndfsum_collect(ref).get('email_trades') or []
    groups = {}
    for t in trades:
        name = str(t.get('counterparty', '') or '').strip()
        if not name or otc_emails._is_lawton(name) or otc_emails._is_jpmorgan(name):
            continue
        groups.setdefault((otc_emails._ndf_legal_class(t.get('legal')), name), []).append(t)

    cpd = _R()._cpd_load()
    blocks = {'JPM': [], 'MGT': []}
    for (le, name), items in sorted(groups.items()):
        # Per-trade cash net of IR (sign-aware — same rule as the Summary card).
        vals = [(r['settlement'] - r['tax'] if r['settlement'] >= 0
                 else r['settlement'] + r['tax']) for r in items]
        recv = sum(v for v in vals if v > 0)
        pay = sum(v for v in vals if v < 0)
        if str(items[0].get('net_type', '') or 'Total Net') == 'Total Net':
            total = recv + pay
            pay = total if total < 0 else 0.0
        if not pay:                          # Pay column empty → nothing to wire
            continue
        spn = items[0].get('spn', '')
        rec_cpd = _R()._cpd_find(cpd, spn) if spn else None
        banking = _R()._bank_norm((rec_cpd or {}).get('BANKING'))
        acct = _R()._ndfsum_account_fmt(banking, 'PAY')     # same source as the ACCOUNT column
        m = re.match(r'BCO:\s*(\d+)', acct or '')
        if (m.group(1).lstrip('0') if m else '') == '376':
            continue                         # account at Banco JPM → book transfer, no TED
        blocks[le].append({'counterparty': name,
                           'value': otc_emails._brl(abs(pay)),
                           'account': acct or '—'})

    rows_all = blocks['JPM'] + blocks['MGT']
    ref_fmt = ref.strftime('%d/%m/%Y')
    if not rows_all:
        return jsonify({'ok': True, 'count': 0,
                        'message': 'Nenhuma TED a liberar para {} (sem Pay ou contas no BCO 376).'
                        .format(ref_fmt)})

    # SSI attachment per distinct counterparty (a name may appear in both LEs).
    attach, missing_ssi = [], []
    for name in sorted({r['counterparty'] for r in rows_all}, key=_R()._fcst_norm):
        p = _R()._ted_ssi_attachment(name)
        (attach.append(p) if p else missing_ssi.append(name))

    html = render_template('pages/email-template-ted-release.html',
                           ref_date_fmt=ref_fmt, product_label='NDF',
                           banco_rows=blocks['JPM'], mgt_rows=blocks['MGT'],
                           missing_ssi=missing_ssi,
                           current_year=datetime.now().year)
    try:
        msg = _R().MIMEMultipart('mixed')
        msg['Subject'] = "Liberar TED's - NDF - {}".format(ref_fmt)
        msg['From'] = _R().SHARED_MAILBOX
        msg['To'] = ', '.join(_R()._TED_EMAIL_TO)
        related = _R().MIMEMultipart('related')
        alt = _R().MIMEMultipart('alternative')
        alt.attach(_R().MIMEText('Liberação de TED — please view in HTML.', 'plain', 'utf-8'))
        alt.attach(_R().MIMEText(html, 'html', 'utf-8'))
        related.attach(alt)
        logo_path = _R()._get_logo_path()
        if logo_path:
            with open(logo_path, 'rb') as f:
                limg = MIMEImage(f.read())
            limg.add_header('Content-ID', '<otc_logo>')
            limg.add_header('Content-Disposition', 'inline', filename='logo.png')
            related.attach(limg)
        _R()._attach_email_gradient(related)
        msg.attach(related)
        for p in attach:
            with open(p, 'rb') as f:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', 'attachment',
                            filename=os.path.basename(p))
            msg.attach(part)
        with _R().smtplib.SMTP(_R().SMTP_HOST, _R().SMTP_PORT, timeout=30) as server:
            server.sendmail(_R().SHARED_MAILBOX, _R()._TED_EMAIL_TO, msg.as_string())
    except Exception as e:
        _R().log.error('[ndf-ted] e-mail FAILED:\n%s', traceback.format_exc())
        return jsonify({'ok': False,
                        'error': 'E-mail failed: {}: {}'.format(type(e).__name__, e)}), 500

    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'TED Release Sent', 'NDF Summary',
                         '{} TED(s) — {}'.format(len(rows_all), ref.strftime('%Y-%m-%d')))
    return jsonify({'ok': True, 'count': len(rows_all),
                    'attached': len(attach), 'missing_ssi': missing_ssi})
