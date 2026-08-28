# -*- coding: utf-8 -*-
"""As rotas de Other Products (a família de liquidação).

Só a casca: _ops_trade_rows é o ÚNICO lugar que sabe as famílias; coletores/advices compartilham tudo — os helpers ficam no routes até a fase platform/, alcançados por _R().
"""
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


@blueprint.route('/other-products-summary')
def other_products_summary():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/other-products-summary.html', segment='other-products-summary',
                           today=_R()._br_now().strftime('%Y-%m-%d'))

@blueprint.route('/api/other-products-summary/data')
def api_ops_data():
    """Settlement-batch payload: widget counts for the reference date (from the B3
    position JSONs) + the worksheet rows (empty until seeding is wired)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    ds = (request.args.get('date') or '').strip()
    try:
        settle_ref = datetime.strptime(ds[:10], '%Y-%m-%d').date() if ds else datetime.now().date()
    except ValueError:
        settle_ref = datetime.now().date()
    pos_ref = _R()._forecast_latest_ref()          # cards read the LATEST available position JSON
    trade = _R()._ops_trade_rows(settle_ref)
    try:
        summary = _R()._opssum_rows(trade, datetime(settle_ref.year, settle_ref.month, settle_ref.day))
    except Exception:
        # O Settlement Summary depende do Reference Data (SPN → net type → conta);
        # um cadastro malformado não pode levar junto o Trade Level nem os widgets.
        _R().log.error("[ops-summary] falha montando o settlement summary:\n%s", traceback.format_exc())
        summary = []
    try:
        recon = _R()._ops_recon(trade)
    except Exception:
        _R().log.error("[ops-recon] falha montando os cards:\n%s", traceback.format_exc())
        recon = {}
    for r in trade:                    # chaves internas (_settle_n/_tax_n) não vão para a tela
        for k in [k for k in r if k.startswith('_')]:
            r.pop(k)
    try:
        sources = _R()._ops_batch_status(datetime(settle_ref.year, settle_ref.month, settle_ref.day))
    except Exception:
        _R().log.error("[ops-summary] falha no diagnóstico das fontes:\n%s", traceback.format_exc())
        sources = {'missing': [], 'blocking': False, 'last_batch': None}
    return jsonify({'success': True, 'date': settle_ref.strftime('%Y-%m-%d'),
                    'pos_date': pos_ref.strftime('%Y-%m-%d') if pos_ref else None,
                    'widgets': _R()._ops_settlement_counts(settle_ref, pos_ref),
                    'sources': sources, 'recon': recon,
                    'summary': summary, 'trade': trade})

@blueprint.route('/api/other-products-summary/ted-email', methods=['POST'])
def api_ops_summary_ted_email():
    """Botão TEDs: envia o pedido de liberação de TED para OTC Ops + Settlements.

    Porte do TED do NDF Summary — MESMA regra de quem entra, MESMO template de
    e-mail, MESMOS destinatários. A linha entra quando o **Pay** está preenchido
    **e** a conta default de pagamento do cliente NÃO é do Banco J.P. Morgan
    (BCO 376 → transferência interna, não é TED). Dois blocos por entidade legal
    (BANCO / MGT), e o SSI de cada contraparte (arquivo mais novo do Electronic
    Inventory) vai anexado.

    O que muda é só o assunto: aqui o e-mail cobre Swap/Opção/Commodities.
    """
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

    # Universo = as MESMAS linhas do Settlement Summary da tela. Recalcular o net
    # aqui criaria a segunda cópia da regra de netting, e o e-mail poderia pedir
    # uma TED de valor diferente do que a tela mostra.
    try:
        rows = _R()._opssum_rows(_R()._ops_trade_rows(ref.date()),
                            datetime(ref.year, ref.month, ref.day))
    except Exception:
        _R().log.error('[ops-ted] falha montando as linhas:\n%s', traceback.format_exc())
        return jsonify({'ok': False, 'error': 'Falha lendo as fontes do dia'}), 500

    blocks = {'JPM': [], 'MGT': []}
    for r in rows:
        name = str(r.get('counterparty', '') or '').strip()
        if not name or otc_emails._is_lawton(name) or otc_emails._is_jpmorgan(name):
            continue
        # Perna interna passou a APARECER no Settlement Summary (ela liquida),
        # mas não se pede TED para si mesmo. O `_is_jpmorgan` acima não responde
        # por ela: a entidade pode ser um fundo nosso ('ATACAMA FUNDO ...'), que
        # não tem 'J.P. Morgan' no nome e passaria batido.
        if r.get('internal'):
            continue
        pay = _R()._mtm_parse_num(r.get('pay', ''))
        if not pay:                          # coluna Pay vazia → não há o que transferir
            continue
        acct = r.get('account', '')
        m = re.match(r'BCO:\s*(\d+)', acct or '')
        if (m.group(1).lstrip('0') if m else '') == '376':
            continue                         # conta no Banco JPM → transferência interna
        blocks[otc_emails._ndf_legal_class(r.get('legal'))].append({
            'counterparty': name,
            'product': r.get('product', ''),
            'value': otc_emails._brl(abs(pay)),
            'account': acct or '—'})

    rows_all = blocks['JPM'] + blocks['MGT']
    ref_fmt = ref.strftime('%d/%m/%Y')
    if not rows_all:
        return jsonify({'ok': True, 'count': 0,
                        'message': 'Nenhuma TED a liberar para {} (sem Pay ou contas no BCO 376).'
                        .format(ref_fmt)})

    attach, missing_ssi = [], []
    for name in sorted({r['counterparty'] for r in rows_all}, key=_R()._fcst_norm):
        p = _R()._ted_ssi_attachment(name)
        (attach.append(p) if p else missing_ssi.append(name))

    html = render_template('pages/email-template-ted-release.html',
                           ref_date_fmt=ref_fmt, product_label=_R()._OPS_TED_LABEL,
                           banco_rows=blocks['JPM'], mgt_rows=blocks['MGT'],
                           missing_ssi=missing_ssi,
                           current_year=datetime.now().year)
    try:
        msg = _R().MIMEMultipart('mixed')
        msg['Subject'] = "Liberar TED's - {} - {}".format(_R()._OPS_TED_LABEL, ref_fmt)
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
        _R().log.error('[ops-ted] e-mail FAILED:\n%s', traceback.format_exc())
        return jsonify({'ok': False,
                        'error': 'E-mail failed: {}: {}'.format(type(e).__name__, e)}), 500

    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'TED Release Sent', 'Other Products Summary',
                         '{} TED(s) — {}'.format(len(rows_all), ref.strftime('%Y-%m-%d')))
    return jsonify({'ok': True, 'count': len(rows_all),
                    'attached': len(attach), 'missing_ssi': missing_ssi})

@blueprint.route('/api/other-products-summary/mark-sent', methods=['POST'])
def api_ops_summary_mark_sent():
    """Confirm do Settlement Summary: marca a linha como Sent no overlay do dia
    (mesmo arquivo da observação). Idempotente — reconfirmar não muda nada além
    de quem confirmou e quando."""
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
    try:
        _R()._opssum_set_status(ref, [(name, str(payload.get('lob', '') or ''),
                                  str(payload.get('product', '') or ''))], 'Sent')
        return jsonify({'ok': True})
    except Exception as e:
        _R().log.error('[ops-summary] mark-sent failed:\n%s', traceback.format_exc())
        return jsonify({'ok': False, 'error': '{}: {}'.format(type(e).__name__, e)}), 500

@blueprint.route('/api/other-products-summary/print-advice', methods=['POST'])
def api_ops_summary_print_advice():
    """Print Advice do Settlement Summary: gera os avisos de TODOS os produtos do
    Other Products (Swap, NDF Commodities e Opção) para a data.

    Mesma entrega dos botões das telas — até 2 rascunhos vão como `.eml` em
    base64 (abrem direto no Outlook), 3+ vão num `.zip`. Com as três famílias
    juntas o zip é o caso normal, e é justamente por isso que ele existe.
    """
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    from apps.pages import otc_emails
    payload = request.get_json(silent=True) or {}
    ds = str(payload.get('date', '') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    # Uma família pode ser pedida sozinha (`families`), mas o botão manda as três.
    pedidas = payload.get('families')
    if isinstance(pedidas, list) and pedidas:
        familias = [f for f in _R()._OPSADV_FAMILIES if f in {str(x).strip() for x in pedidas}]
    else:
        familias = list(_R()._OPSADV_FAMILIES)
    drafts, falhas, por_familia, bloqueadas = [], [], {}, []
    for family in familias:
        parte, erro, bloq = _R()._opsadv_family_drafts(family, ref)
        por_familia[family] = len(parte)
        if erro:
            falhas.append(erro)
        bloqueadas.extend(bloq)
        drafts.extend(parte)
    # Todas as famílias falharam: aí sim é erro, e não "nada a gerar".
    if falhas and not drafts and len(falhas) == len(familias):
        return jsonify({'ok': False, 'error': 'Falha lendo as fontes do dia ({})'
                        .format(', '.join(falhas))}), 500
    if not drafts:
        # Zero avisos COM bloqueio não é "nada a gerar": é tudo bloqueado, e a
        # tela precisa dizer isso em vez de um "nenhum aviso para esta data".
        return jsonify({'ok': True, 'count': 0, 'by_family': por_familia,
                        'failed': falhas, 'blocked': bloqueadas})
    cp_count = len({d.get('counterparty', '') for d in drafts})
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
        return jsonify({'ok': True, 'count': len(drafts), 'counterparties': cp_count,
                        'by_family': por_familia, 'failed': falhas,
                        'blocked': bloqueadas, 'files': files})
    resp = _R()._email_drafts_response(
        drafts, zip_name='Avisos_Liquidacao_{}_Other_Products'.format(ref.strftime('%d%m%y')))
    resp.headers['X-Counterparty-Count'] = str(cp_count)
    # O navegador precisa saber o que veio no zip para montar a frase — o corpo é
    # binário e não tem onde carregar o resumo.
    resp.headers['X-Family-Counts'] = ','.join(
        '{}:{}'.format(f, por_familia.get(f, 0)) for f in familias)
    if falhas:
        resp.headers['X-Failed-Families'] = ', '.join(falhas)
    if bloqueadas:
        resp.headers['X-Blocked'] = _R()._opsadv_blocked_header(bloqueadas)
    return resp

@blueprint.route('/api/other-products-summary/observation', methods=['POST'])
def api_ops_summary_observation():
    """Observação livre por linha do Settlement Summary — mesmo overlay diário do
    NDF, mas chaveado por contraparte × LOB × produto, que é a identidade da
    linha aqui. Texto vazio limpa a observação (volta a automática)."""
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
    key = _R()._opssum_key(name, str(payload.get('lob', '') or ''), str(payload.get('product', '') or ''))
    text = str(payload.get('text', '') or '').strip()
    try:
        path, meta = _R()._opssum_meta_load(ref)
        entry = meta.get(key) or {}
        if text:
            entry['obs'] = text
        else:
            entry.pop('obs', None)
        if entry:
            meta[key] = entry
        else:
            meta.pop(key, None)        # entrada vazia não fica ocupando o overlay
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _R()._atomic_write_json(path, meta)     # funil: atômico + espelho (§335)
        return jsonify({'ok': True})
    except Exception as e:
        _R().log.error('[ops-summary] observation save failed:\n%s', traceback.format_exc())
        return jsonify({'ok': False, 'error': '{}: {}'.format(type(e).__name__, e)}), 500

@blueprint.route('/other-products-swap-events')
def other_products_swap_events():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/other-products-swap-events.html',
                           segment='other-products-swap-events',
                           ref_date=datetime.now().strftime('%Y-%m-%d'))

@blueprint.route('/api/other-products-swap-events/data')
def api_swap_events_data():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    ds = (request.args.get('date') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    payload = _R()._ds_display_collect(ref, 'eventos-swap-jpm', _R()._EVENTS_COLUMNS)   # fixed cols; heuristic #,##0.00
    payload.update({'success': True, 'ref_date': ref.strftime('%Y-%m-%d'),
                    'ref_date_fmt': ref.strftime('%d/%m/%Y')})
    return jsonify(payload)

@blueprint.route('/other-products-swap-athena')
def other_products_swap_athena():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/other-products-swap-athena.html',
                           segment='other-products-swap-athena',
                           ref_date=datetime.now().strftime('%Y-%m-%d'))

@blueprint.route('/api/other-products-swap-athena/data')
def api_swap_athena_data():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    ds = (request.args.get('date') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    payload = _R()._athena_settlements(ref)
    # Sort by CounterParty A→Z (accent-insensitive); blank names go last. Vem
    # DEPOIS da resolução do nome: ordenar pelo texto do arquivo deixaria a lista
    # fora de ordem alfabética assim que o nome mudasse na tela.
    if 'CounterParty' in payload['columns']:
        ci = payload['columns'].index('CounterParty')
        payload['rows'].sort(key=lambda r: (str(r[ci]).strip() == '', _R()._fcst_norm(str(r[ci]))))
    payload.update({'success': True, 'ref_date': ref.strftime('%Y-%m-%d'),
                    'ref_date_fmt': ref.strftime('%d/%m/%Y')})
    return jsonify(payload)

@blueprint.route('/other-products-swap-settlement-advice')
def other_products_swap_settlement_advice():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/other-products-swap-settlement-advice.html',
                           segment='other-products-swap-settlement-advice',
                           ref_date=datetime.now().strftime('%Y-%m-%d'))

@blueprint.route('/api/other-products-swap-settlement-advice/row', methods=['POST'])
def api_swadv_row_save():
    """Grava a edição manual de uma linha do aviso.

    Só as células que vieram no payload são gravadas — o resto continua saindo
    dos arquivos, então uma correção pontual não congela a linha inteira no
    valor de hoje."""
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    payload = request.get_json(silent=True) or {}
    ref, key = _R()._swadv_ref_and_key(payload)
    if not key:
        return jsonify({'ok': False, 'error': 'Linha sem Número de Contrato — nada a gravar.'}), 400
    cells = payload.get('cells') or {}
    if not isinstance(cells, dict):
        return jsonify({'ok': False, 'error': 'Payload inválido.'}), 400
    # Ler → alterar → gravar sob o MESMO lock: dois operadores editando linhas
    # diferentes do mesmo dia perderiam uma das duas edições.
    with _R()._cache_lock:
        fp, edits = _R()._swadv_edits_load(ref)
        e = edits.setdefault(key, {})
        cur = e.setdefault('cells', {})
        for k, v in cells.items():
            try:
                i = int(k)
            except (TypeError, ValueError):
                continue
            if 0 <= i < len(_R()._SWADV_COLUMNS):
                cur[str(i)] = '' if v is None else str(v)
        e['edited_by'] = session.get('user_sid', '')
        e['edited_at'] = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        try:
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            _R()._atomic_write_json(fp, edits)
        except Exception as exc:                            # noqa: BLE001
            _R().log.error('[swap-advice] não consegui gravar a edição:\n%s', traceback.format_exc())
            return jsonify({'ok': False, 'error': str(exc)}), 500
    return jsonify({'ok': True})

@blueprint.route('/api/other-products-swap-settlement-advice/row/delete', methods=['POST'])
def api_swadv_row_delete():
    """Tira a linha do aviso do dia.

    Marca como apagada no overlay em vez de mexer nos arquivos de origem: o
    contrato continua existindo na B3 e no Athena, e o que se apagou foi a
    LINHA DESTE AVISO. Reimportar o batch não a traz de volta, e mandar `undo`
    traz."""
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    payload = request.get_json(silent=True) or {}
    ref, key = _R()._swadv_ref_and_key(payload)
    if not key:
        return jsonify({'ok': False, 'error': 'Linha sem Número de Contrato.'}), 400
    with _R()._cache_lock:
        fp, edits = _R()._swadv_edits_load(ref)
        e = edits.setdefault(key, {})
        e['deleted'] = not payload.get('undo')
        e['deleted_by'] = session.get('user_sid', '')
        e['deleted_at'] = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        try:
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            _R()._atomic_write_json(fp, edits)
        except Exception as exc:                            # noqa: BLE001
            _R().log.error('[swap-advice] não consegui apagar a linha:\n%s', traceback.format_exc())
            return jsonify({'ok': False, 'error': str(exc)}), 500
    return jsonify({'ok': True})

@blueprint.route('/api/other-products-swap-settlement-advice/row/confirm', methods=['POST'])
def api_swadv_row_confirm():
    """Confirma a linha → status Sent.

    O status vive no overlay do Settlement Summary e é por **contraparte × LOB ×
    produto**, porque é assim que o aviso é emitido: um documento por
    destinatário. Confirmar uma linha confirma o aviso a que ela pertence — e é
    por isso que a tela avisa quantas linhas mudam junto, em vez de deixar
    parecer que só aquela mudou."""
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    payload = request.get_json(silent=True) or {}
    ref, key = _R()._swadv_ref_and_key(payload)
    try:
        items = _R()._swadv_items(ref)
    except Exception:
        _R().log.error('[swap-advice] falha lendo as linhas:\n%s', traceback.format_exc())
        return jsonify({'ok': False, 'error': 'Falha lendo as linhas do dia.'}), 500
    row = next((r for r in items
                if str(r['cells'][_R()._SWADV_KEY_COL] or '').strip() == key), None)
    if row is None:
        return jsonify({'ok': False, 'error': 'Contrato não encontrado nesta data.'}), 404
    cpty, lob = row.get('counterparty', ''), row.get('lob', '')
    with _R()._cache_lock:
        _R()._opssum_set_status(ref, [(cpty, lob, 'SWAP')], 'Sent')
    n = sum(1 for r in items
            if r.get('counterparty') == cpty and r.get('lob', '') == lob)
    return jsonify({'ok': True, 'status': 'Sent', 'counterparty': cpty, 'rows': n})

@blueprint.route('/api/other-products-swap-settlement-advice/data')
def api_swap_settlement_advice_data():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    ds = (request.args.get('date') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    try:
        items = _R()._swadv_items(ref)
    except Exception:
        _R().log.error('[swap-advice] falha montando o aviso:\n%s', traceback.format_exc())
        items = []
    items.sort(key=lambda r: (str(r['counterparty']).strip() == '',
                              _R()._fcst_norm(str(r['counterparty']))))          # Cliente A→Z
    # Status por linha, do MESMO overlay do Settlement Summary: o contrato herda
    # o estado da linha de aviso a que pertence (contraparte × LOB × produto).
    _p, meta = _R()._opssum_meta_load(ref)
    statuses = [_R()._opssum_status(meta, r['counterparty'], r.get('lob', ''), 'SWAP') for r in items]
    return jsonify({'success': True, 'columns': _R()._SWADV_COLUMNS,
                    'rows': [r['cells'] for r in items], 'statuses': statuses,
                    'widgets': {'total': len(items)},
                    'ref_date': ref.strftime('%Y-%m-%d'),
                    'ref_date_fmt': ref.strftime('%d/%m/%Y')})

@blueprint.route('/api/other-products-swap-settlement-advice/emails', methods=['POST'])
def api_swap_settlement_advice_emails():
    """Print Advice: gera os avisos de liquidação de SWAP (rascunhos .eml) da
    data. Mesma entrega do aviso de NDF — até 2 vão como .eml em base64 (abrem
    direto no Outlook), 3+ vão num .zip."""
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    payload = request.get_json(silent=True) or {}
    ds = str(payload.get('date', '') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    from apps.pages import otc_emails
    try:
        rows = _R()._swadv_email_rows(ref)
    except Exception:
        _R().log.error('[swap-advice] falha montando as linhas do aviso:\n%s', traceback.format_exc())
        return jsonify({'ok': False, 'error': 'Falha lendo as fontes do dia'}), 500
    # Seleção da tela (checkbox por linha): sem a chave, gera tudo — com ela
    # vazia, não gera nada, que é o pedido explícito de quem não marcou ninguém.
    sel = payload.get('contracts')
    if isinstance(sel, list):
        wanted = {str(x).strip().upper() for x in sel if str(x).strip()}
        rows = [r for r in rows if str(r['cells'][0]).strip().upper() in wanted]
    # Blocker: contraparte com Resultado Bruto ou Valor Líquido em branco NÃO
    # vira aviso — o documento é o que o cliente paga, e em branco ele não diz
    # quanto mas parece completo. O corte é da contraparte inteira porque o aviso
    # é netado por ela (ver `_opsadv_block_incomplete`).
    rows, blocked = _R()._opsadv_block_incomplete('swap', rows, _R()._swadv_email_headers(False))
    drafts = otc_emails.build_swap_settlement_emails(
        rows, _R()._swadv_email_headers(False), _R()._swadv_email_headers(True),
        ref.strftime('%d/%m/%Y'))
    if not drafts:
        return jsonify({'ok': True, 'count': 0, 'blocked': blocked})
    cp_count = len({d.get('counterparty', '') for d in drafts})

    # Status → Generated para as linhas que de fato viraram aviso. Best-effort DE
    # PROPÓSITO: os rascunhos já foram produzidos, então uma falha aqui é logada
    # mas não transforma uma geração bem-sucedida em erro na tela.
    try:
        done = {_R()._fcst_norm(d.get('counterparty', '')) for d in drafts}
        _R()._opssum_set_status(ref, [(r['counterparty'], r.get('lob', ''), 'SWAP')
                                 for r in rows
                                 if _R()._fcst_norm(r.get('counterparty', '')) in done], 'Generated')
    except Exception:
        _R().log.error('[swap-advice] generated-status save failed:\n%s', traceback.format_exc())

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
                        'counterparties': cp_count, 'blocked': blocked, 'files': files})
    resp = _R()._email_drafts_response(
        drafts, zip_name='Avisos_Liquidacao_{}_Swap'.format(ref.strftime('%d%m%y')))
    resp.headers['X-Counterparty-Count'] = str(cp_count)
    if blocked:
        # O disclaimer tambem no caminho do .zip: o corpo e binario e nao
        # tem onde carregar o resumo (base64 porque nome tem acento).
        resp.headers['X-Blocked'] = _R()._opsadv_blocked_header(blocked)
    return resp

@blueprint.route('/api/other-products-ndf-settlement-advice/emails', methods=['POST'])
def api_ndf_settlement_advice_emails():
    """Print Advice do Termo de Mercadoria: rascunhos .eml da data, quebrados por
    net type e — para quem está no cadastro `ndfc-advice-split` — por commodity."""
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    payload = request.get_json(silent=True) or {}
    ds = str(payload.get('date', '') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    from apps.pages import otc_emails
    try:
        rows = _R()._ndfadv_email_rows(ref)
    except Exception:
        _R().log.error('[ndf-advice] falha montando as linhas do aviso:\n%s', traceback.format_exc())
        return jsonify({'ok': False, 'error': 'Falha lendo as fontes do dia'}), 500
    # Blocker: ver `_opsadv_block_incomplete`. Foi aqui que ele nasceu — linhas
    # da Mondelez saíam com Resultado Apurado e Líquido em branco.
    rows, blocked = _R()._opsadv_block_incomplete('ndf', rows, _R()._ndfadv_email_headers())
    drafts = otc_emails.build_ndfc_settlement_emails(
        rows, _R()._ndfadv_email_headers(), ref.strftime('%d/%m/%Y'),
        split_commodity=_R()._ndfc_split_by_commodity)
    if not drafts:
        return jsonify({'ok': True, 'count': 0, 'blocked': blocked})
    cp_count = len({d.get('counterparty', '') for d in drafts})
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
                        'counterparties': cp_count, 'blocked': blocked, 'files': files})
    resp = _R()._email_drafts_response(
        drafts, zip_name='Avisos_Liquidacao_{}_NDF_Commodities'.format(ref.strftime('%d%m%y')))
    resp.headers['X-Counterparty-Count'] = str(cp_count)
    if blocked:
        # O disclaimer tambem no caminho do .zip: o corpo e binario e nao
        # tem onde carregar o resumo (base64 porque nome tem acento).
        resp.headers['X-Blocked'] = _R()._opsadv_blocked_header(blocked)
    return resp

@blueprint.route('/other-products-ndf-settlement-advice')
def other_products_ndf_settlement_advice():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/other-products-ndf-settlement-advice.html',
                           segment='other-products-ndf-settlement-advice',
                           ref_date=datetime.now().strftime('%Y-%m-%d'))

@blueprint.route('/api/other-products-ndf-settlement-advice/data')
def api_ndf_settlement_advice_data():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    ds = (request.args.get('date') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    try:
        items = _R()._ndfadv_collect(ref)
    except Exception:
        _R().log.error('[ndf-advice] falha montando o aviso:\n%s', traceback.format_exc())
        items = []
    items.sort(key=lambda r: (str(r['counterparty']).strip() == '',
                              _R()._fcst_norm(str(r['counterparty']))))
    # Status por linha, do MESMO overlay do Settlement Summary — o que o aviso de
    # Swap já fazia. Sem esta chave o visualizador compartilhado cai no badge
    # fixo 'In Custody', que é o rótulo da Live Position (a tela de onde o JS
    # veio) e não diz nada sobre um aviso: o ciclo dele é New → Generated → Sent.
    # A chave é a da linha do Summary a que o contrato pertence (contraparte ×
    # LOB × produto), a mesma que `_ops_ndfc_trade_rows` grava.
    _p, meta = _R()._opssum_meta_load(ref)
    statuses = [_R()._opssum_status(meta, r['counterparty'], 'COMMODITIES', 'TERMO') for r in items]
    return jsonify({'success': True, 'columns': _R()._NDFADV_COLUMNS,
                    'rows': [r['cells'] for r in items], 'statuses': statuses,
                    'widgets': {'total': len(items)},
                    'ref_date': ref.strftime('%Y-%m-%d'),
                    'ref_date_fmt': ref.strftime('%d/%m/%Y')})

@blueprint.route('/other-products-option-settlement-advice')
def other_products_option_settlement_advice():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/other-products-option-settlement-advice.html',
                           segment='other-products-option-settlement-advice',
                           ref_date=datetime.now().strftime('%Y-%m-%d'))

@blueprint.route('/api/other-products-option-settlement-advice/data')
def api_option_settlement_advice_data():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    ds = (request.args.get('date') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    try:
        items = _R()._optadv_items(ref)
    except Exception:
        _R().log.error('[opt-advice] falha montando o aviso:\n%s', traceback.format_exc())
        items = []
    items.sort(key=lambda r: (str(r['counterparty']).strip() == '',
                              _R()._fcst_norm(str(r['counterparty']))))
    _p, meta = _R()._opssum_meta_load(ref)
    statuses = [_R()._opssum_status(meta, r['counterparty'], r.get('lob', ''), 'OPTION')
                for r in items]
    return jsonify({'success': True, 'columns': _R()._OPTADV_COLUMNS,
                    'rows': [r['cells'] for r in items], 'statuses': statuses,
                    'widgets': {'total': len(items)},
                    'ref_date': ref.strftime('%Y-%m-%d'),
                    'ref_date_fmt': ref.strftime('%d/%m/%Y')})

@blueprint.route('/api/other-products-option-settlement-advice/row', methods=['POST'])
def api_optadv_row_save():
    """Grava a edição manual de uma linha do aviso de opção. Só as células que
    vieram no payload — o resto continua saindo dos arquivos."""
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    payload = request.get_json(silent=True) or {}
    ref, key = _R()._optadv_ref_and_key(payload)
    if not key:
        return jsonify({'ok': False, 'error': 'Linha sem B3 ID — nada a gravar.'}), 400
    cells = payload.get('cells') or {}
    if not isinstance(cells, dict):
        return jsonify({'ok': False, 'error': 'Payload inválido.'}), 400
    # Ler → alterar → gravar sob o MESMO lock: dois operadores editando linhas
    # diferentes do mesmo dia perderiam uma das duas edições.
    with _R()._cache_lock:
        fp, edits = _R()._optadv_edits_load(ref)
        e = edits.setdefault(key, {})
        cur = e.setdefault('cells', {})
        for k, v in cells.items():
            try:
                i = int(k)
            except (TypeError, ValueError):
                continue
            if 0 <= i < len(_R()._OPTADV_COLUMNS):
                cur[str(i)] = '' if v is None else str(v)
        e['edited_by'] = session.get('user_sid', '')
        e['edited_at'] = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        try:
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            _R()._atomic_write_json(fp, edits)
        except Exception as exc:                            # noqa: BLE001
            _R().log.error('[opt-advice] não consegui gravar a edição:\n%s', traceback.format_exc())
            return jsonify({'ok': False, 'error': str(exc)}), 500
    return jsonify({'ok': True})

@blueprint.route('/api/other-products-option-settlement-advice/row/delete', methods=['POST'])
def api_optadv_row_delete():
    """Tira a linha do aviso do dia — marca no overlay, não mexe nos arquivos de
    origem. `undo` traz de volta."""
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    payload = request.get_json(silent=True) or {}
    ref, key = _R()._optadv_ref_and_key(payload)
    if not key:
        return jsonify({'ok': False, 'error': 'Linha sem B3 ID.'}), 400
    with _R()._cache_lock:
        fp, edits = _R()._optadv_edits_load(ref)
        e = edits.setdefault(key, {})
        e['deleted'] = not payload.get('undo')
        e['deleted_by'] = session.get('user_sid', '')
        e['deleted_at'] = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        try:
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            _R()._atomic_write_json(fp, edits)
        except Exception as exc:                            # noqa: BLE001
            _R().log.error('[opt-advice] não consegui apagar a linha:\n%s', traceback.format_exc())
            return jsonify({'ok': False, 'error': str(exc)}), 500
    return jsonify({'ok': True})

@blueprint.route('/api/other-products-option-settlement-advice/row/confirm', methods=['POST'])
def api_optadv_row_confirm():
    """Confirma a linha → status Sent.

    O status vive no overlay do Settlement Summary e é por **contraparte × LOB ×
    produto**, porque é assim que o aviso é emitido: um documento por
    destinatário. Confirmar uma linha confirma o aviso a que ela pertence — e é
    por isso que a resposta diz quantas linhas mudam junto."""
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    payload = request.get_json(silent=True) or {}
    ref, key = _R()._optadv_ref_and_key(payload)
    try:
        items = _R()._optadv_items(ref)
    except Exception:
        _R().log.error('[opt-advice] falha lendo as linhas:\n%s', traceback.format_exc())
        return jsonify({'ok': False, 'error': 'Falha lendo as linhas do dia.'}), 500
    row = next((r for r in items
                if str(r['cells'][_R()._OPTADV_KEY_COL] or '').strip() == key), None)
    if row is None:
        return jsonify({'ok': False, 'error': 'B3 ID não encontrado nesta data.'}), 404
    cpty, lob = row.get('counterparty', ''), row.get('lob', '')
    with _R()._cache_lock:
        _R()._opssum_set_status(ref, [(cpty, lob, 'OPTION')], 'Sent')
    n = sum(1 for r in items
            if r.get('counterparty') == cpty and r.get('lob', '') == lob)
    return jsonify({'ok': True, 'status': 'Sent', 'counterparty': cpty, 'rows': n})

@blueprint.route('/api/other-products-option-settlement-advice/emails', methods=['POST'])
def api_option_settlement_advice_emails():
    """Print Advice da Opção: rascunhos .eml da data, quebrados por net type e —
    para quem está no cadastro `ndfc-advice-split` — por ativo subjacente.

    É o MESMO gerador do Termo de Mercadoria (`build_ndfc_settlement_emails`) e o
    MESMO cadastro de quebra: o grupo Mondelez recebe um aviso por mercadoria, e
    isso é uma decisão do CLIENTE, não do produto — uma segunda lista para a opção
    divergiria da primeira no dia em que alguém entrasse só numa delas.

    O assunto é a única diferença, e ele vem da LINHA (`product_label`, resolvido
    da classe do subjacente, mais o prefixo `(Pagamento de Prêmio)`); o rótulo
    passado aqui é só o default de quem chegar sem classe nenhuma."""
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    payload = request.get_json(silent=True) or {}
    ds = str(payload.get('date', '') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    from apps.pages import otc_emails
    try:
        rows = _R()._optadv_email_rows(ref)
    except Exception:
        _R().log.error('[opt-advice] falha montando as linhas do aviso:\n%s', traceback.format_exc())
        return jsonify({'ok': False, 'error': 'Falha lendo as fontes do dia'}), 500
    # Blocker: ver `_opsadv_block_incomplete`.
    rows, blocked = _R()._opsadv_block_incomplete('option', rows, _R()._optadv_email_headers())
    drafts = otc_emails.build_ndfc_settlement_emails(
        rows, _R()._optadv_email_headers(), ref.strftime('%d/%m/%Y'),
        split_commodity=_R()._ndfc_split_by_commodity, product_label='Opção')
    if not drafts:
        return jsonify({'ok': True, 'count': 0, 'blocked': blocked})
    cp_count = len({d.get('counterparty', '') for d in drafts})

    # Status → Generated para as linhas que de fato viraram aviso. Best-effort DE
    # PROPÓSITO: os rascunhos já foram produzidos, então uma falha aqui é logada
    # mas não transforma uma geração bem-sucedida em erro na tela.
    try:
        done = {_R()._fcst_norm(d.get('counterparty', '')) for d in drafts}
        with _R()._cache_lock:
            _R()._opssum_set_status(ref, [(r['counterparty'], r.get('lob', ''), 'OPTION')
                                     for r in rows
                                     if _R()._fcst_norm(r.get('counterparty', '')) in done], 'Generated')
    except Exception:
        _R().log.error('[opt-advice] generated-status save failed:\n%s', traceback.format_exc())

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
                        'counterparties': cp_count, 'blocked': blocked, 'files': files})
    resp = _R()._email_drafts_response(
        drafts, zip_name='Avisos_Liquidacao_{}_Opcao'.format(ref.strftime('%d%m%y')))
    resp.headers['X-Counterparty-Count'] = str(cp_count)
    if blocked:
        # O disclaimer tambem no caminho do .zip: o corpo e binario e nao
        # tem onde carregar o resumo (base64 porque nome tem acento).
        resp.headers['X-Blocked'] = _R()._opsadv_blocked_header(blocked)
    return resp

@blueprint.route('/other-products-swap-kapital-hybrids')
def other_products_swap_kapital_hybrids():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/other-products-swap-kapital-hybrids.html',
                           segment='other-products-swap-kapital-hybrids',
                           ref_date=datetime.now().strftime('%Y-%m-%d'))

@blueprint.route('/api/other-products-swap-kapital-hybrids/data')
def api_swap_kapital_hybrids_data():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    ds = (request.args.get('date') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    payload = _R()._swaphyb_collect(ref)
    payload.update({'success': True, 'ref_date': ref.strftime('%Y-%m-%d'),
                    'ref_date_fmt': ref.strftime('%d/%m/%Y')})
    return jsonify(payload)

@blueprint.route('/other-products-swap-vcp')
def other_products_swap_vcp():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/other-products-swap-vcp.html',
                           segment='other-products-swap-vcp',
                           ref_date=datetime.now().strftime('%Y-%m-%d'))

@blueprint.route('/api/other-products-swap-vcp/data')
def api_swap_vcp_data():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    ds = (request.args.get('date') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    payload = _R()._vcp_collect(ref)
    payload.update({'success': True, 'ref_date': ref.strftime('%Y-%m-%d'),
                    'ref_date_fmt': ref.strftime('%d/%m/%Y')})
    return jsonify(payload)
