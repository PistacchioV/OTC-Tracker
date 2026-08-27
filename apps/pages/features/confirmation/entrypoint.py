# -*- coding: utf-8 -*-
"""As rotas de Confirmations do New Deals.

Só a casca: os nove editores/validates dos documentos — geração e Inventory são plataforma — o resto fica no routes até a fase platform/, alcançado por _R().
"""
import os
import traceback
from datetime import datetime

from flask import (jsonify, redirect, render_template, request,
                   send_file, session, url_for)

from apps.pages import blueprint


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


@blueprint.route('/confirmation/ndf-comm/strike-usd')
def confirmation_ndfcomm_strike_usd():
    return _R()._conf_generation_page('strike-usd')

@blueprint.route('/confirmation/ndf-comm/platts-strike-usd')
def confirmation_ndfcomm_platts_strike_usd():
    return _R()._conf_generation_page('platts')

@blueprint.route('/confirmation/ndf-comm/strike-brl')
def confirmation_ndfcomm_strike_brl():
    return _R()._conf_generation_page('brl')

@blueprint.route('/confirmation/ndf-comm/palmoil-strike-myrusd')
def confirmation_ndfcomm_palmoil_strike_myrusd():
    return _R()._conf_generation_page('palm-oil')

@blueprint.route('/api/confirmation/ndf-comm/save', methods=['POST'])
def api_conf_ndfcomm_save():
    """Salva a confirmação (com os ajustes feitos no painel) em Word + PDF no
    Electronic Inventory: Confirmations/YYYY/mm. Mês/dd/<produto>/<arquivo>.
    O .doc é o próprio HTML do documento (o Word abre HTML nativamente — os
    templates legados .doc já eram HTML do Word); o PDF é gerado via reportlab."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    payload = request.get_json(silent=True) or {}
    family = (payload.get('family') or 'strike-usd').strip()
    if family not in _R()._CONF_FAMILY_TEMPLATES:
        return jsonify({'success': False, 'message': 'Template not available for this family yet.'}), 400
    fields = payload.get('fields') or {}
    rows = [r for r in (payload.get('rows') or []) if isinstance(r, dict)]
    if not rows:
        return jsonify({'success': False, 'message': 'No operations to save.'}), 400
    # CGD é cláusula do documento ("ambos firmados entre as Partes em <data>"):
    # sem ela a confirmação sai com a lacuna em branco e vai assim para a
    # contraparte. Trava no servidor, não só no painel — o POST é público para
    # qualquer sessão autenticada.
    if not str(fields.get('cgd_date') or '').strip():
        return jsonify({'success': False, 'error': 'missing_cgd',
                        'message': 'Data do CGD não cadastrada para esta contraparte. '
                                   'Cadastre o CGD no Reference Data (ou preencha o campo '
                                   'Data do CGD no painel) antes de salvar a confirmação.'}), 400

    acr = str(payload.get('acronym') or '').strip() or 'CONFIRMATION'
    merc = str(payload.get('mercadoria') or '').strip()
    conf = {
        'ref_date':     str(payload.get('date') or '').strip(),
        'cgd_date':     str(fields.get('cgd_date') or '').strip(),
        'parteb_nome':  str(fields.get('parteb_nome') or '').strip(),
        'parteb_cnpj':  str(fields.get('parteb_cnpj') or '').strip(),
        'data_neg':     str(fields.get('data_neg') or '').strip(),
        'data_extenso': str(fields.get('data_extenso') or '').strip(),
        'acronym':      acr,
        'mercadoria':   merc,
        'rows':         rows,
        'warnings':     [],
    }

    try:
        from apps.pages.confirmation_pdfs import termo_pdf
        pdf_bytes = termo_pdf(conf, variant={'strike-usd': 'usd', 'platts': 'platts',
                                             'brl': 'brl', 'palm-oil': 'palmoil'}[family])
    except ImportError:
        return jsonify({'success': False,
                        'message': 'reportlab is not installed — run pip install -r requirements.txt.'}), 500
    except Exception:
        _R().log.error('[conf] PDF build failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'message': 'PDF generation failed.'}), 500

    doc_html = render_template(_R()._CONF_FAMILY_TEMPLATES[family][0],
                               conf=conf, doc_only=True)

    ref = _R()._parse_date_any(payload.get('date')) or _R()._parse_date_any(conf['data_neg']) or datetime.now()
    # Pasta da contraparte no Electronic Inventory — mesma árvore que o upload
    # manual da página (<Cliente>\Confirmations\YYYY\mm. Month\dd\<produto>),
    # para a confirmação aparecer no browse do EI junto dos demais documentos.
    # O nome do produto sai do TYPE_FOLDER (a pasta É o código do tipo): escrito
    # à mão aqui, ele voltava a divergir do upload manual no primeiro ajuste.
    client_dir = _R()._ei_resolve_client_dir(conf['parteb_nome'] or acr, create=True)
    dir_path = os.path.join(client_dir, 'Confirmations',
                            ref.strftime('%Y'), _R()._ei_month_folder(ref.strftime('%m')),
                            ref.strftime('%d'), _R()._mc_mod.TYPE_FOLDER['NDF COMM'])
    # Nome no padrão legado, mantendo o prefixo contraparte × mercadoria.
    if len(rows) == 1 and str(rows[0].get('num') or '').strip():
        base = '{} - {} - CONFIRMAÇÃO DE OPERAÇÕES DE DERIVATIVOS nº {}'.format(
            acr, merc, str(rows[0]['num']).strip())
    else:
        base = '{} - {} - CONFIRMAÇÃO DE OPERAÇÕES DE DERIVATIVOS - {}'.format(
            acr, merc, ref.strftime('%Y%m%d'))
    base = _R()._ei_sanitize(base)

    try:
        os.makedirs(_R()._ei_long_path(dir_path), exist_ok=True)
        candidate, n = base, 0
        while os.path.exists(_R()._ei_long_path(os.path.join(dir_path, candidate + '.doc'))) or \
                os.path.exists(_R()._ei_long_path(os.path.join(dir_path, candidate + '.pdf'))):
            n += 1
            candidate = '{} ({})'.format(base, n)
        doc_path = os.path.join(dir_path, candidate + '.doc')
        pdf_path = os.path.join(dir_path, candidate + '.pdf')
        with open(_R()._ei_long_path(doc_path), 'w', encoding='utf-8') as fh:
            fh.write(doc_html)
        with open(_R()._ei_long_path(pdf_path), 'wb') as fh:
            fh.write(pdf_bytes)

        # XML do contrato (FepWeb): mesmo nome do numeroContrato, mesma pasta.
        # Calculado a partir dos deals-fonte (status Success) do grupo — não das
        # linhas editadas no painel — porque valor/moeda/CNPJ vêm do cache.
        xml_files, numero_contrato, xml_warns, fep_updated = [], '', [], 0
        picked = _R()._conf_pick_ndfcomm(ref, acr, merc, family)
        if picked:
            numero_contrato, xml_str, xml_warns = _R()._conf_ndf_xml(picked, merc, ref)
            # Mesmo nome-base do .doc/.pdf: os três arquivos da confirmação
            # ficam juntos na listagem da pasta. O numeroContrato continua
            # dentro do XML (é ele que o FepWeb lê), só não nomeia mais o
            # arquivo — com vários deals ele era genérico
            # (NDF_Comm_YYYYMMDD_MERC) e não dizia de qual confirmação era.
            xbase = candidate
            xcand, xn = xbase, 0
            while os.path.exists(_R()._ei_long_path(os.path.join(dir_path, xcand + '.xml'))):
                xn += 1
                xcand = '{} ({})'.format(xbase, xn)
            xml_path = os.path.join(dir_path, xcand + '.xml')
            with open(_R()._ei_long_path(xml_path), 'w', encoding='utf-8') as fh:
                fh.write(xml_str)
            xml_files.append(xml_path)
            # numeroContrato → coluna FepWeb ID das operações no Pending Confirmation
            fep_updated = _R()._conf_pc_set_fepweb([d.get('Deal') for d, _s in picked],
                                              numero_contrato)
        else:
            xml_warns = ['XML não gerado: nenhuma operação com status Success no grupo.']
    except Exception as exc:
        _R().log.error('[conf] save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'message': 'Could not write to the Inventory share: ' + str(exc)}), 500

    # Ciclo da confirmação: salvar = Generated (a validação com checklist +
    # preview do PDF é o passo seguinte, que leva a Success).
    ref_state = _R()._parse_date_any(payload.get('date')) or ref
    with _R()._cache_lock:
        state = _R()._conf_state_load(ref_state)
        state[_R()._conf_key(acr, merc, family)] = {
            'status': 'Generated', 'doc': doc_path, 'pdf': pdf_path,
            'saved_by': session.get('user_sid', ''),
            'saved_at': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
            'checks': {}, 'validated_by': '', 'validated_at': '',
        }
        _R()._conf_state_save(ref_state, state)

    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Confirmation Saved', 'NDF Comm',
                         '{} · {} ({} op{})'.format(acr, merc, len(rows),
                                                    '' if len(rows) == 1 else 's'))
    validate_url = ('/confirmation/ndf-comm/validate?date=' + ref_state.strftime('%Y-%m-%d')
                    + '&acronym=' + _R().quote(acr) + '&mercadoria=' + _R().quote(merc)
                    + '&family=' + _R().quote(family))
    # A confirmação saiu: carimba a Data envio validação OTC nas linhas de
    # Manual Confirmations e guarda o endereço do PDF no Electronic
    # Inventory — é para onde o botão Abrir do Monitor manda. O link é do
    # papel que foi gravado, não da tela que o reconstrói: quem valida
    # precisa ver o que vai ao cliente, e a tela de geração pode montar
    # outra coisa se o day-file mudou desde então.
    _R()._mc_stamp_generated(picked, 'ndf-comm',
                        link=_R()._mc_ei_link(conf['parteb_nome'] or acr,
                                         client_dir, pdf_path))
    return jsonify({'success': True, 'files': [doc_path, pdf_path] + xml_files,
                    'numero_contrato': numero_contrato,
                    'fepweb_updated': fep_updated,
                    'warnings': xml_warns,
                    'validate_url': validate_url})

@blueprint.route('/api/confirmation/ndf-comm/pdf')
def api_conf_ndfcomm_pdf():
    """Preview inline do PDF salvo da confirmação (para a janela de validação)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    _ref, _key, entry, err = _R()._conf_state_entry_or_404(request.args)
    if err:
        return err
    pdf_path = (entry or {}).get('pdf') or ''
    if not pdf_path or not os.path.isfile(pdf_path):
        return ('PDF não encontrado no Inventory ({}).'.format(pdf_path), 404)
    return send_file(pdf_path, mimetype='application/pdf', as_attachment=False,
                     download_name=os.path.basename(pdf_path))

@blueprint.route('/confirmation/ndf-comm/validate')
def confirmation_ndfcomm_validate():
    """Janela de validação da confirmação gerada: checklist + preview do PDF.
    Todos os checks marcados → Validate → status Success."""
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    ref, _key, entry, err = _R()._conf_state_entry_or_404(request.args)
    if err:
        return err
    acr = (request.args.get('acronym') or '').strip()
    merc = (request.args.get('mercadoria') or '').strip().upper()
    fam = (request.args.get('family') or 'strike-usd').strip()
    qs = ('date=' + ref.strftime('%Y-%m-%d') + '&acronym=' + _R().quote(acr)
          + '&mercadoria=' + _R().quote(merc) + '&family=' + _R().quote(fam))
    return render_template('confirmations/validate.html',
                           acronym=acr, mercadoria=merc, family=fam,
                           ref_date=ref.strftime('%Y-%m-%d'),
                           ref_date_disp=ref.strftime('%d/%m/%Y'),
                           status=entry.get('status') or 'Generated',
                           saved_by=entry.get('saved_by') or '',
                           saved_at=entry.get('saved_at') or '',
                           validated_by=entry.get('validated_by') or '',
                           validated_at=entry.get('validated_at') or '',
                           checks=entry.get('checks') or {},
                           api_base='/api/confirmation/ndf-comm',
                           pdf_url='/api/confirmation/ndf-comm/pdf?' + qs)

@blueprint.route('/api/confirmation/ndf-comm/validate', methods=['POST'])
def api_conf_ndfcomm_validate():
    """Marca a confirmação como Success após o checklist completo."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    payload = request.get_json(silent=True) or {}
    ref, key, entry, err = _R()._conf_state_entry_or_404(payload)
    if err:
        return jsonify({'success': False, 'message': err[0]}), err[1]
    checks = payload.get('checks') or {}
    if not checks or not all(bool(v) for v in checks.values()):
        return jsonify({'success': False,
                        'message': 'Todos os itens do checklist precisam ser confirmados.'}), 400
    with _R()._cache_lock:
        state = _R()._conf_state_load(ref)
        entry = state.get(key) or entry
        entry['status'] = 'Success'
        entry['checks'] = {str(k): True for k in checks}
        entry['validated_by'] = session.get('user_sid', '')
        entry['validated_at'] = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        state[key] = entry
        _R()._conf_state_save(ref, state)
    # O checklist fecha o ciclo do DOCUMENTO. A etapa do OTC na esteira NÃO é
    # carimbada aqui — ela é validada no Monitor. Ver o comentário onde o
    # `_mc_stamp_otc_validated` existia.
    #
    # E ele NÃO gera aviso no sino. Gerava um 'Confirmation Validated', e o sino
    # ficava com DOIS itens dizendo validado para a mesma confirmação: este, do
    # documento, e o 'Validated by OTC' da esteira — que é o que a mesa precisa
    # ver, porque diz quem assinou, quantas operações e para quem a confirmação
    # foi. O ciclo do documento (New → Generated → Success) continua visível no
    # card de Confirmations do New Deals Monitor, que é onde ele já era
    # acompanhado; o que saiu foi só a linha no sino.
    return jsonify({'success': True, 'status': 'Success'})

@blueprint.route('/confirmation/opt-comm/strike-usd')
def confirmation_optcomm_strike_usd():
    return _R()._conf_opt_generation_page('strike-usd')

@blueprint.route('/confirmation/opt-comm/strike-brl')
def confirmation_optcomm_strike_brl():
    return _R()._conf_opt_generation_page('brl')

@blueprint.route('/confirmation/opt-comm/palmoil-strike-myrusd')
def confirmation_optcomm_palmoil_strike_myrusd():
    return _R()._conf_opt_generation_page('palm-oil')

@blueprint.route('/api/confirmation/opt-comm/save', methods=['POST'])
def api_conf_optcomm_save():
    """Salva a confirmação de Opção (Word + PDF + XML) no Electronic Inventory
    e grava o numeroContrato na coluna FepWeb ID — mesmo fluxo do NDF Comm."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    payload = request.get_json(silent=True) or {}
    family = (payload.get('family') or 'strike-usd').strip()
    if family not in _R()._CONF_OPT_FAMILY_TEMPLATES:
        return jsonify({'success': False, 'message': 'Template not available for this family yet.'}), 400
    fields = payload.get('fields') or {}
    rows = [r for r in (payload.get('rows') or []) if isinstance(r, dict)]
    if not rows:
        return jsonify({'success': False, 'message': 'No operations to save.'}), 400
    # CGD é cláusula do documento ("ambos firmados entre as Partes em <data>"):
    # sem ela a confirmação sai com a lacuna em branco e vai assim para a
    # contraparte. Trava no servidor, não só no painel — o POST é público para
    # qualquer sessão autenticada.
    if not str(fields.get('cgd_date') or '').strip():
        return jsonify({'success': False, 'error': 'missing_cgd',
                        'message': 'Data do CGD não cadastrada para esta contraparte. '
                                   'Cadastre o CGD no Reference Data (ou preencha o campo '
                                   'Data do CGD no painel) antes de salvar a confirmação.'}), 400

    acr = str(payload.get('acronym') or '').strip() or 'CONFIRMATION'
    merc = str(payload.get('mercadoria') or '').strip()
    conf = {
        'ref_date':     str(payload.get('date') or '').strip(),
        'cgd_date':     str(fields.get('cgd_date') or '').strip(),
        'parteb_nome':  str(fields.get('parteb_nome') or '').strip(),
        'parteb_cnpj':  str(fields.get('parteb_cnpj') or '').strip(),
        'data_neg':     str(fields.get('data_neg') or '').strip(),
        'data_extenso': str(fields.get('data_extenso') or '').strip(),
        'acronym':      acr,
        'mercadoria':   merc,
        'rows':         rows,
        'warnings':     [],
    }

    # O HTML do documento é montado ANTES do PDF: nas famílias novas ele É a
    # fonte do PDF (`word_html_pdf`), e nas antigas continua sendo só o `.doc`.
    doc_html = render_template(_R()._CONF_OPT_FAMILY_TEMPLATES[family][0],
                               conf=conf, doc_only=True)

    try:
        if family in _R()._CONF_OPT_PDF_FROM_HTML:
            from apps.pages.confirmation_pdfs import word_html_pdf
            pdf_bytes = word_html_pdf(doc_html)
        else:
            from apps.pages.confirmation_pdfs import opcao_pdf
            pdf_bytes = opcao_pdf(conf, variant=_R()._CONF_OPT_PDF_VARIANT.get(family, 'usd'))
    except ImportError:
        return jsonify({'success': False,
                        'message': 'reportlab is not installed — run pip install -r requirements.txt.'}), 500
    except Exception:
        _R().log.error('[conf] PDF build failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'message': 'PDF generation failed.'}), 500

    ref = _R()._parse_date_any(payload.get('date')) or _R()._parse_date_any(conf['data_neg']) or datetime.now()
    # Pasta da contraparte no Electronic Inventory (mesma árvore do upload
    # manual) — ver api_conf_ndfcomm_save.
    client_dir = _R()._ei_resolve_client_dir(conf['parteb_nome'] or acr, create=True)
    dir_path = os.path.join(client_dir, 'Confirmations',
                            ref.strftime('%Y'), _R()._ei_month_folder(ref.strftime('%m')),
                            ref.strftime('%d'), _R()._mc_mod.TYPE_FOLDER['OPTION COMM'])
    if len(rows) == 1 and str(rows[0].get('num') or '').strip():
        base = '{} - {} - CONFIRMAÇÃO DE OPERAÇÕES DE DERIVATIVOS nº {}'.format(
            acr, merc, str(rows[0]['num']).strip())
    else:
        base = '{} - {} - CONFIRMAÇÃO DE OPERAÇÕES DE DERIVATIVOS - {}'.format(
            acr, merc, ref.strftime('%Y%m%d'))
    base = _R()._ei_sanitize(base)

    try:
        os.makedirs(_R()._ei_long_path(dir_path), exist_ok=True)
        candidate, n = base, 0
        while os.path.exists(_R()._ei_long_path(os.path.join(dir_path, candidate + '.doc'))) or \
                os.path.exists(_R()._ei_long_path(os.path.join(dir_path, candidate + '.pdf'))):
            n += 1
            candidate = '{} ({})'.format(base, n)
        doc_path = os.path.join(dir_path, candidate + '.doc')
        pdf_path = os.path.join(dir_path, candidate + '.pdf')
        with open(_R()._ei_long_path(doc_path), 'w', encoding='utf-8') as fh:
            fh.write(doc_html)
        with open(_R()._ei_long_path(pdf_path), 'wb') as fh:
            fh.write(pdf_bytes)

        # XML do contrato: tipoOperacao Option, numeroContrato com prefixo
        # Opt_Comm — o resto do padrão (valores, moedas, datas) é o do NDF.
        xml_files, numero_contrato, xml_warns, fep_updated = [], '', [], 0
        picked = _R()._conf_pick_optcomm(ref, acr, merc, family)
        if picked:
            numero_contrato, xml_str, xml_warns = _R()._conf_ndf_xml(
                # MAIÚSCULO: é como o FepWeb espera o tipo de operação, e é
                # como o `NDF` (que sempre saiu em caixa alta) já ia. O
                # `Option` com inicial maiúscula era a única saída fora do
                # padrão, nas duas famílias de opção.
                picked, merc, ref, tipo='OPTION', prefixo='Opt_Comm')
            # Mesmo nome-base do .doc/.pdf: os três arquivos da confirmação
            # ficam juntos na listagem da pasta. O numeroContrato continua
            # dentro do XML (é ele que o FepWeb lê), só não nomeia mais o
            # arquivo — com vários deals ele era genérico
            # (NDF_Comm_YYYYMMDD_MERC) e não dizia de qual confirmação era.
            xbase = candidate
            xcand, xn = xbase, 0
            while os.path.exists(_R()._ei_long_path(os.path.join(dir_path, xcand + '.xml'))):
                xn += 1
                xcand = '{} ({})'.format(xbase, xn)
            xml_path = os.path.join(dir_path, xcand + '.xml')
            with open(_R()._ei_long_path(xml_path), 'w', encoding='utf-8') as fh:
                fh.write(xml_str)
            xml_files.append(xml_path)
            fep_updated = _R()._conf_pc_set_fepweb([d.get('Deal') for d, _s in picked],
                                              numero_contrato)
        else:
            xml_warns = ['XML não gerado: nenhuma operação com status Success no grupo.']
    except Exception as exc:
        _R().log.error('[conf] save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'message': 'Could not write to the Inventory share: ' + str(exc)}), 500

    ref_state = _R()._parse_date_any(payload.get('date')) or ref
    with _R()._cache_lock:
        state = _R()._conf_state_load(ref_state, 'opt-comm')
        state[_R()._conf_key(acr, merc, family)] = {
            'status': 'Generated', 'doc': doc_path, 'pdf': pdf_path,
            'saved_by': session.get('user_sid', ''),
            'saved_at': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
            'checks': {}, 'validated_by': '', 'validated_at': '',
        }
        _R()._conf_state_save(ref_state, state, 'opt-comm')

    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Confirmation Saved', 'Opt Comm',
                         '{} · {} ({} op{})'.format(acr, merc, len(rows),
                                                    '' if len(rows) == 1 else 's'))
    validate_url = ('/confirmation/opt-comm/validate?date=' + ref_state.strftime('%Y-%m-%d')
                    + '&acronym=' + _R().quote(acr) + '&mercadoria=' + _R().quote(merc)
                    + '&family=' + _R().quote(family))
    # A confirmação saiu: carimba a Data envio validação OTC nas linhas de
    # Manual Confirmations e guarda o endereço do PDF no Electronic
    # Inventory — é para onde o botão Abrir do Monitor manda. O link é do
    # papel que foi gravado, não da tela que o reconstrói: quem valida
    # precisa ver o que vai ao cliente, e a tela de geração pode montar
    # outra coisa se o day-file mudou desde então.
    _R()._mc_stamp_generated(picked, 'opt-comm',
                        link=_R()._mc_ei_link(conf['parteb_nome'] or acr,
                                         client_dir, pdf_path))
    return jsonify({'success': True, 'files': [doc_path, pdf_path] + xml_files,
                    'numero_contrato': numero_contrato,
                    'fepweb_updated': fep_updated,
                    'warnings': xml_warns,
                    'validate_url': validate_url})

@blueprint.route('/api/confirmation/opt-comm/pdf')
def api_conf_optcomm_pdf():
    """Preview inline do PDF salvo da confirmação de Opção."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    _ref, _key, entry, err = _R()._conf_state_entry_or_404(request.args, 'opt-comm')
    if err:
        return err
    pdf_path = (entry or {}).get('pdf') or ''
    if not pdf_path or not os.path.isfile(pdf_path):
        return ('PDF não encontrado no Inventory ({}).'.format(pdf_path), 404)
    return send_file(pdf_path, mimetype='application/pdf', as_attachment=False,
                     download_name=os.path.basename(pdf_path))

@blueprint.route('/confirmation/opt-comm/validate')
def confirmation_optcomm_validate():
    """Janela de validação da confirmação de Opção (checklist + preview)."""
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    ref, _key, entry, err = _R()._conf_state_entry_or_404(request.args, 'opt-comm')
    if err:
        return err
    acr = (request.args.get('acronym') or '').strip()
    merc = (request.args.get('mercadoria') or '').strip().upper()
    fam = (request.args.get('family') or 'strike-usd').strip()
    qs = ('date=' + ref.strftime('%Y-%m-%d') + '&acronym=' + _R().quote(acr)
          + '&mercadoria=' + _R().quote(merc) + '&family=' + _R().quote(fam))
    return render_template('confirmations/validate.html',
                           acronym=acr, mercadoria=merc, family=fam,
                           ref_date=ref.strftime('%Y-%m-%d'),
                           ref_date_disp=ref.strftime('%d/%m/%Y'),
                           status=entry.get('status') or 'Generated',
                           saved_by=entry.get('saved_by') or '',
                           saved_at=entry.get('saved_at') or '',
                           validated_by=entry.get('validated_by') or '',
                           validated_at=entry.get('validated_at') or '',
                           checks=entry.get('checks') or {},
                           api_base='/api/confirmation/opt-comm',
                           pdf_url='/api/confirmation/opt-comm/pdf?' + qs)

@blueprint.route('/api/confirmation/opt-comm/validate', methods=['POST'])
def api_conf_optcomm_validate():
    """Marca a confirmação de Opção como Success após o checklist completo."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    payload = request.get_json(silent=True) or {}
    ref, key, entry, err = _R()._conf_state_entry_or_404(payload, 'opt-comm')
    if err:
        return jsonify({'success': False, 'message': err[0]}), err[1]
    checks = payload.get('checks') or {}
    if not checks or not all(bool(v) for v in checks.values()):
        return jsonify({'success': False,
                        'message': 'Todos os itens do checklist precisam ser confirmados.'}), 400
    with _R()._cache_lock:
        state = _R()._conf_state_load(ref, 'opt-comm')
        entry = state.get(key) or entry
        entry['status'] = 'Success'
        entry['checks'] = {str(k): True for k in checks}
        entry['validated_by'] = session.get('user_sid', '')
        entry['validated_at'] = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        state[key] = entry
        _R()._conf_state_save(ref, state, 'opt-comm')
    # O checklist fecha o ciclo do DOCUMENTO. A etapa do OTC na esteira NÃO é
    # carimbada aqui — ela é validada no Monitor. Ver o comentário onde o
    # `_mc_stamp_otc_validated` existia.
    #
    # E ele NÃO gera aviso no sino. Gerava um 'Confirmation Validated', e o sino
    # ficava com DOIS itens dizendo validado para a mesma confirmação: este, do
    # documento, e o 'Validated by OTC' da esteira — que é o que a mesa precisa
    # ver, porque diz quem assinou, quantas operações e para quem a confirmação
    # foi. O ciclo do documento (New → Generated → Success) continua visível no
    # card de Confirmations do New Deals Monitor, que é onde ele já era
    # acompanhado; o que saiu foi só a linha no sino.
    return jsonify({'success': True, 'status': 'Success'})

@blueprint.route('/confirmation/opt-fxo/vanilla')
def confirmation_optfxo_vanilla():
    return _R()._conf_fxo_generation_page('vanilla')

@blueprint.route('/confirmation/opt-fxo/asian')
def confirmation_optfxo_asian():
    return _R()._conf_fxo_generation_page('asian')

@blueprint.route('/api/confirmation/opt-fxo/save', methods=['POST'])
def api_conf_optfxo_save():
    """Salva a confirmação de Opção de Câmbio (Word + PDF + XML) no Electronic
    Inventory e grava o numeroContrato na coluna FepWeb ID."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    payload = request.get_json(silent=True) or {}
    family = (payload.get('family') or 'vanilla').strip()
    if family not in _R()._CONF_FXO_FAMILY_TEMPLATES:
        return jsonify({'success': False, 'message': 'Template not available for this family yet.'}), 400
    fields = payload.get('fields') or {}
    rows = [r for r in (payload.get('rows') or []) if isinstance(r, dict)]
    if not rows:
        return jsonify({'success': False, 'message': 'No operations to save.'}), 400
    # CGD é cláusula do documento ("ambos firmados entre as Partes em <data>"):
    # sem ela a confirmação sai com a lacuna em branco e vai assim para a
    # contraparte. Trava no servidor, não só no painel.
    if not str(fields.get('cgd_date') or '').strip():
        return jsonify({'success': False, 'error': 'missing_cgd',
                        'message': 'Data do CGD não cadastrada para esta contraparte. '
                                   'Cadastre o CGD no Reference Data (ou preencha o campo '
                                   'Data do CGD no painel) antes de salvar a confirmação.'}), 400

    acr = str(payload.get('acronym') or '').strip() or 'CONFIRMATION'
    merc = str(payload.get('mercadoria') or '').strip()
    conf = {
        'ref_date':     str(payload.get('date') or '').strip(),
        'cgd_date':     str(fields.get('cgd_date') or '').strip(),
        'parteb_nome':  str(fields.get('parteb_nome') or '').strip(),
        'parteb_cnpj':  str(fields.get('parteb_cnpj') or '').strip(),
        'data_neg':     str(fields.get('data_neg') or '').strip(),
        'data_extenso': str(fields.get('data_extenso') or '').strip(),
        'acronym':      acr,
        'mercadoria':   merc,
        'rows':         rows,
        'warnings':     [],
    }

    # O documento sai PRIMEIRO: nas confirmações de FXO o PDF é gerado a partir
    # deste mesmo HTML (ver opcao_fx_pdf), e não de uma segunda transcrição do
    # texto do Word — assim os dois arquivos não têm como divergir.
    doc_html = render_template(_R()._CONF_FXO_FAMILY_TEMPLATES[family][0],
                               conf=conf, doc_only=True)
    try:
        from apps.pages.confirmation_pdfs import opcao_fx_pdf
        pdf_bytes = opcao_fx_pdf(conf, variant=family, doc_html=doc_html)
    except ImportError:
        return jsonify({'success': False,
                        'message': 'reportlab is not installed — run pip install -r requirements.txt.'}), 500
    except Exception:
        _R().log.error('[conf] PDF build failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'message': 'PDF generation failed.'}), 500

    ref = _R()._parse_date_any(payload.get('date')) or _R()._parse_date_any(conf['data_neg']) or datetime.now()
    # Pasta da contraparte no Electronic Inventory (mesma árvore do upload
    # manual) — ver api_conf_ndfcomm_save.
    client_dir = _R()._ei_resolve_client_dir(conf['parteb_nome'] or acr, create=True)
    dir_path = os.path.join(client_dir, 'Confirmations',
                            ref.strftime('%Y'), _R()._ei_month_folder(ref.strftime('%m')),
                            ref.strftime('%d'), _R()._mc_mod.TYPE_FOLDER['FXO'])
    if len(rows) == 1 and str(rows[0].get('num') or '').strip():
        base = '{} - {} - CONFIRMAÇÃO DE OPERAÇÕES DE DERIVATIVOS nº {}'.format(
            acr, merc, str(rows[0]['num']).strip())
    else:
        base = '{} - {} - CONFIRMAÇÃO DE OPERAÇÕES DE DERIVATIVOS - {}'.format(
            acr, merc, ref.strftime('%Y%m%d'))
    base = _R()._ei_sanitize(base)

    try:
        os.makedirs(_R()._ei_long_path(dir_path), exist_ok=True)
        candidate, n = base, 0
        while os.path.exists(_R()._ei_long_path(os.path.join(dir_path, candidate + '.doc'))) or \
                os.path.exists(_R()._ei_long_path(os.path.join(dir_path, candidate + '.pdf'))):
            n += 1
            candidate = '{} ({})'.format(base, n)
        doc_path = os.path.join(dir_path, candidate + '.doc')
        pdf_path = os.path.join(dir_path, candidate + '.pdf')
        with open(_R()._ei_long_path(doc_path), 'w', encoding='utf-8') as fh:
            fh.write(doc_html)
        with open(_R()._ei_long_path(pdf_path), 'wb') as fh:
            fh.write(pdf_bytes)

        # XML do contrato: tipoOperacao Option, prefixo Opt_FXO e a moeda
        # estrangeira do Underlying Asset (na opção de câmbio é ele que diz a
        # moeda da operação; StrikeCurrency guarda a mesma coisa, mas quem
        # manda no documento e no registro é o Underlying).
        xml_files, numero_contrato, xml_warns, fep_updated = [], '', [], 0
        picked = _R()._conf_pick_optfxo(ref, acr, merc, family)
        if picked:
            numero_contrato, xml_str, xml_warns = _R()._conf_ndf_xml(
                # MAIÚSCULO, pela mesma razão do Opt Comm.
                picked, merc, ref, tipo='OPTION', prefixo='Opt_FXO',
                ccy_field='UnderlyingAsset', warn_no_spot=False)
            # Mesmo nome-base do .doc/.pdf: os três arquivos da confirmação
            # ficam juntos na listagem da pasta.
            xbase = candidate
            xcand, xn = xbase, 0
            while os.path.exists(_R()._ei_long_path(os.path.join(dir_path, xcand + '.xml'))):
                xn += 1
                xcand = '{} ({})'.format(xbase, xn)
            xml_path = os.path.join(dir_path, xcand + '.xml')
            with open(_R()._ei_long_path(xml_path), 'w', encoding='utf-8') as fh:
                fh.write(xml_str)
            xml_files.append(xml_path)
            fep_updated = _R()._conf_pc_set_fepweb([d.get('Deal') for d, _s in picked],
                                              numero_contrato)
        else:
            xml_warns = ['XML não gerado: nenhuma operação com status Success no grupo.']
    except Exception as exc:
        _R().log.error('[conf] save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'message': 'Could not write to the Inventory share: ' + str(exc)}), 500

    ref_state = _R()._parse_date_any(payload.get('date')) or ref
    with _R()._cache_lock:
        state = _R()._conf_state_load(ref_state, 'opt-fxo')
        state[_R()._conf_key(acr, merc, family)] = {
            'status': 'Generated', 'doc': doc_path, 'pdf': pdf_path,
            'saved_by': session.get('user_sid', ''),
            'saved_at': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
            'checks': {}, 'validated_by': '', 'validated_at': '',
        }
        _R()._conf_state_save(ref_state, state, 'opt-fxo')

    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Confirmation Saved', 'Opt FXO',
                         '{} · {} ({} op{})'.format(acr, merc, len(rows),
                                                    '' if len(rows) == 1 else 's'))
    validate_url = ('/confirmation/opt-fxo/validate?date=' + ref_state.strftime('%Y-%m-%d')
                    + '&acronym=' + _R().quote(acr) + '&mercadoria=' + _R().quote(merc)
                    + '&family=' + _R().quote(family))
    # A confirmação saiu: carimba a Data envio validação OTC nas linhas de
    # Manual Confirmations e guarda o endereço do PDF no Electronic
    # Inventory — é para onde o botão Abrir do Monitor manda. O link é do
    # papel que foi gravado, não da tela que o reconstrói: quem valida
    # precisa ver o que vai ao cliente, e a tela de geração pode montar
    # outra coisa se o day-file mudou desde então.
    _R()._mc_stamp_generated(picked, 'opt-fxo',
                        link=_R()._mc_ei_link(conf['parteb_nome'] or acr,
                                         client_dir, pdf_path))
    return jsonify({'success': True, 'files': [doc_path, pdf_path] + xml_files,
                    'numero_contrato': numero_contrato,
                    'fepweb_updated': fep_updated,
                    'warnings': xml_warns,
                    'validate_url': validate_url})

@blueprint.route('/api/confirmation/opt-fxo/pdf')
def api_conf_optfxo_pdf():
    """Preview inline do PDF salvo da confirmação de Opção de Câmbio."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    _ref, _key, entry, err = _R()._conf_state_entry_or_404(request.args, 'opt-fxo')
    if err:
        return err
    pdf_path = (entry or {}).get('pdf') or ''
    if not pdf_path or not os.path.isfile(pdf_path):
        return ('PDF não encontrado no Inventory ({}).'.format(pdf_path), 404)
    return send_file(pdf_path, mimetype='application/pdf', as_attachment=False,
                     download_name=os.path.basename(pdf_path))

@blueprint.route('/confirmation/opt-fxo/validate')
def confirmation_optfxo_validate():
    """Janela de validação da confirmação de Opção de Câmbio (checklist + preview)."""
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    ref, _key, entry, err = _R()._conf_state_entry_or_404(request.args, 'opt-fxo')
    if err:
        return err
    acr = (request.args.get('acronym') or '').strip()
    merc = (request.args.get('mercadoria') or '').strip().upper()
    fam = (request.args.get('family') or 'vanilla').strip()
    qs = ('date=' + ref.strftime('%Y-%m-%d') + '&acronym=' + _R().quote(acr)
          + '&mercadoria=' + _R().quote(merc) + '&family=' + _R().quote(fam))
    return render_template('confirmations/validate.html',
                           acronym=acr, mercadoria=merc, family=fam,
                           ref_date=ref.strftime('%Y-%m-%d'),
                           ref_date_disp=ref.strftime('%d/%m/%Y'),
                           status=entry.get('status') or 'Generated',
                           saved_by=entry.get('saved_by') or '',
                           saved_at=entry.get('saved_at') or '',
                           validated_by=entry.get('validated_by') or '',
                           validated_at=entry.get('validated_at') or '',
                           checks=entry.get('checks') or {},
                           api_base='/api/confirmation/opt-fxo',
                           pdf_url='/api/confirmation/opt-fxo/pdf?' + qs)

@blueprint.route('/api/confirmation/opt-fxo/validate', methods=['POST'])
def api_conf_optfxo_validate():
    """Marca a confirmação de Opção de Câmbio como Success após o checklist."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    payload = request.get_json(silent=True) or {}
    ref, key, entry, err = _R()._conf_state_entry_or_404(payload, 'opt-fxo')
    if err:
        return jsonify({'success': False, 'message': err[0]}), err[1]
    checks = payload.get('checks') or {}
    if not checks or not all(bool(v) for v in checks.values()):
        return jsonify({'success': False,
                        'message': 'Todos os itens do checklist precisam ser confirmados.'}), 400
    with _R()._cache_lock:
        state = _R()._conf_state_load(ref, 'opt-fxo')
        entry = state.get(key) or entry
        entry['status'] = 'Success'
        entry['checks'] = {str(k): True for k in checks}
        entry['validated_by'] = session.get('user_sid', '')
        entry['validated_at'] = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        state[key] = entry
        _R()._conf_state_save(ref, state, 'opt-fxo')
    # O checklist fecha o ciclo do DOCUMENTO. A etapa do OTC na esteira NÃO é
    # carimbada aqui — ela é validada no Monitor. Ver o comentário onde o
    # `_mc_stamp_otc_validated` existia.
    #
    # E ele NÃO gera aviso no sino. Gerava um 'Confirmation Validated', e o sino
    # ficava com DOIS itens dizendo validado para a mesma confirmação: este, do
    # documento, e o 'Validated by OTC' da esteira — que é o que a mesa precisa
    # ver, porque diz quem assinou, quantas operações e para quem a confirmação
    # foi. O ciclo do documento (New → Generated → Success) continua visível no
    # card de Confirmations do New Deals Monitor, que é onde ele já era
    # acompanhado; o que saiu foi só a linha no sino.
    return jsonify({'success': True, 'status': 'Success'})

@blueprint.route('/confirmation/ndf-fwdstart/strike-me')
def confirmation_fwdstart_strike_me():
    """Confirmação de NDF FWD Start pré-preenchida para um grupo
    contraparte × moeda base da reference date."""
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    family = 'strike-me'
    ds = (request.args.get('date') or '').strip()
    acr = (request.args.get('acronym') or '').strip()
    merc = (request.args.get('mercadoria') or '').strip().upper()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()

    picked = _R()._conf_pick_fwdstart(ref, acr, merc, family)
    if not picked:
        return ('Nenhuma operação elegível para essa confirmação '
                '(contraparte {} × {} em {}).'.format(acr, merc, ref.strftime('%d/%m/%Y')), 404)

    first = picked[0][0]
    warnings = []
    rows = _R()._conf_fwdstart_rows(picked, warnings)

    cgd_txt = _R()._conf_cgd_lookup(first)
    if not cgd_txt:
        warnings.append('CGD não cadastrado no Reference Data — preencha no painel.')

    partea_nome, partea_cnpj = _R()._conf_fwdstart_partea(picked, warnings)

    trade_date = first.get('TradeDate') or ref
    conf = {
        'ref_date':     ref.strftime('%Y-%m-%d'),
        # Nº do cabeçalho: o B3 ID quando o grupo tem UMA operação — com várias
        # não há um número que represente o documento, e chutar o da primeira
        # daria à confirmação o número de uma das operações que ela contém.
        'num_conf':     rows[0]['num'] if len(rows) == 1 else '',
        'cgd_date':     cgd_txt,
        'partea_nome':  partea_nome,
        'partea_cnpj':  partea_cnpj,
        'parteb_nome':  str(first.get('Client') or '').strip(),
        'parteb_cnpj':  _R()._conf_fmt_cnpj(first.get('TaxID')),
        'data_neg':     _R()._conf_fmt_date(trade_date),
        'data_extenso': _R()._conf_date_extenso(trade_date),
        'mercadoria':   merc,
        'acronym':      acr,
        'rows':         rows,
        'warnings':     warnings,
    }
    return render_template(_R()._CONF_FWDSTART_FAMILY_TEMPLATES[family][0], conf=conf)

@blueprint.route('/api/confirmation/ndf-fwdstart/save', methods=['POST'])
def api_conf_fwdstart_save():
    """Salva a confirmação de NDF FWD Start (Word + PDF + XML) no Electronic
    Inventory e grava o numeroContrato na coluna FepWeb ID."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    payload = request.get_json(silent=True) or {}
    family = (payload.get('family') or 'strike-me').strip()
    if family not in _R()._CONF_FWDSTART_FAMILY_TEMPLATES:
        return jsonify({'success': False, 'message': 'Template not available for this family yet.'}), 400
    fields = payload.get('fields') or {}
    rows = [r for r in (payload.get('rows') or []) if isinstance(r, dict)]
    if not rows:
        return jsonify({'success': False, 'message': 'No operations to save.'}), 400
    if not str(fields.get('cgd_date') or '').strip():
        return jsonify({'success': False, 'error': 'missing_cgd',
                        'message': 'Data do CGD não cadastrada para esta contraparte. '
                                   'Cadastre o CGD no Reference Data (ou preencha o campo '
                                   'Data do CGD no painel) antes de salvar a confirmação.'}), 400
    # A Parte A em branco sairia num documento assinado sem dizer QUEM assina —
    # a rota da página só a deixa vazia quando a LE do grupo não a define
    # (ausente/mista), e aí o painel é onde a mesa decide.
    if not str(fields.get('partea_nome') or '').strip():
        return jsonify({'success': False, 'error': 'missing_partea',
                        'message': 'Parte A em branco — a Legal Entity das operações não a '
                                   'define. Preencha o nome (e o CNPJ) da Parte A no painel '
                                   'antes de salvar a confirmação.'}), 400

    acr = str(payload.get('acronym') or '').strip() or 'CONFIRMATION'
    merc = str(payload.get('mercadoria') or '').strip()
    conf = {
        'ref_date':     str(payload.get('date') or '').strip(),
        'num_conf':     str(fields.get('num_conf') or '').strip(),
        'cgd_date':     str(fields.get('cgd_date') or '').strip(),
        'partea_nome':  str(fields.get('partea_nome') or '').strip(),
        'partea_cnpj':  str(fields.get('partea_cnpj') or '').strip(),
        'parteb_nome':  str(fields.get('parteb_nome') or '').strip(),
        'parteb_cnpj':  str(fields.get('parteb_cnpj') or '').strip(),
        'data_neg':     str(fields.get('data_neg') or '').strip(),
        'data_extenso': str(fields.get('data_extenso') or '').strip(),
        'acronym':      acr,
        'mercadoria':   merc,
        'rows':         rows,
        'warnings':     [],
    }

    # O documento sai PRIMEIRO e o PDF sai DELE — mesma regra do FXO (§139): uma
    # segunda transcrição do texto do Word é a forma conhecida de os dois
    # arquivos divergirem sem ninguém notar.
    doc_html = render_template(_R()._CONF_FWDSTART_FAMILY_TEMPLATES[family][0],
                               conf=conf, doc_only=True)
    try:
        from apps.pages.confirmation_pdfs import word_html_pdf
        pdf_bytes = word_html_pdf(doc_html)
    except ImportError:
        return jsonify({'success': False,
                        'message': 'reportlab is not installed — run pip install -r requirements.txt.'}), 500
    except Exception:
        _R().log.error('[conf] PDF build failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'message': 'PDF generation failed.'}), 500

    ref = _R()._parse_date_any(payload.get('date')) or _R()._parse_date_any(conf['data_neg']) or datetime.now()
    client_dir = _R()._ei_resolve_client_dir(conf['parteb_nome'] or acr, create=True)
    dir_path = os.path.join(client_dir, 'Confirmations',
                            ref.strftime('%Y'), _R()._ei_month_folder(ref.strftime('%m')),
                            ref.strftime('%d'), _R()._mc_mod.TYPE_FOLDER['NDF FWD START'])
    if len(rows) == 1 and str(rows[0].get('num') or '').strip():
        base = '{} - {} - CONFIRMAÇÃO DE OPERAÇÕES DE DERIVATIVOS nº {}'.format(
            acr, merc, str(rows[0]['num']).strip())
    else:
        base = '{} - {} - CONFIRMAÇÃO DE OPERAÇÕES DE DERIVATIVOS - {}'.format(
            acr, merc, ref.strftime('%Y%m%d'))
    base = _R()._ei_sanitize(base)

    try:
        os.makedirs(_R()._ei_long_path(dir_path), exist_ok=True)
        candidate, n = base, 0
        while os.path.exists(_R()._ei_long_path(os.path.join(dir_path, candidate + '.doc'))) or \
                os.path.exists(_R()._ei_long_path(os.path.join(dir_path, candidate + '.pdf'))):
            n += 1
            candidate = '{} ({})'.format(base, n)
        doc_path = os.path.join(dir_path, candidate + '.doc')
        pdf_path = os.path.join(dir_path, candidate + '.pdf')
        with open(_R()._ei_long_path(doc_path), 'w', encoding='utf-8') as fh:
            fh.write(doc_html)
        with open(_R()._ei_long_path(pdf_path), 'wb') as fh:
            fh.write(pdf_bytes)

        xml_files, numero_contrato, xml_warns, fep_updated = [], '', [], 0
        picked = _R()._conf_pick_fwdstart(ref, acr, merc, family)
        if picked:
            # A moeda do XML é a Moeda Base (a estrangeira do par), a mesma que
            # dá nome ao grupo — não a Quantity Currency, que pode ser o BRL.
            # `tipoOperacao` = **NDF**, e não `Termo`. O FWD Start é um NDF —
            # o que ele tem de próprio é a data de início lá na frente, não o
            # tipo de operação. `Termo` não pertence ao domínio que o FepWeb
            # espera nesse campo, e o arquivo era recusado / classificado errado
            # do outro lado. As outras três confirmações que geram XML já usam o
            # nome do produto: NDF Commodities manda `NDF` e as duas de opção,
            # `Option`.
            numero_contrato, xml_str, xml_warns = _R()._conf_ndf_xml(
                picked, merc, ref, tipo='NDF', prefixo='NDF_FwdStart',
                ccy_field='QuantityCurrency', warn_no_spot=False,
                legs_fn=_R()._conf_fx_legs, ccy=merc)
            xcand, xn = candidate, 0
            while os.path.exists(_R()._ei_long_path(os.path.join(dir_path, xcand + '.xml'))):
                xn += 1
                xcand = '{} ({})'.format(candidate, xn)
            xml_path = os.path.join(dir_path, xcand + '.xml')
            with open(_R()._ei_long_path(xml_path), 'w', encoding='utf-8') as fh:
                fh.write(xml_str)
            xml_files.append(xml_path)
            fep_updated = _R()._conf_pc_set_fepweb([d.get('Deal') for d, _s in picked],
                                              numero_contrato)
        else:
            xml_warns = ['XML não gerado: nenhuma operação com status Success no grupo.']
    except Exception as exc:
        _R().log.error('[conf] save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'message': 'Could not write to the Inventory share: ' + str(exc)}), 500

    ref_state = _R()._parse_date_any(payload.get('date')) or ref
    with _R()._cache_lock:
        state = _R()._conf_state_load(ref_state, 'ndf-fwdstart')
        state[_R()._conf_key(acr, merc, family)] = {
            'status': 'Generated', 'doc': doc_path, 'pdf': pdf_path,
            'saved_by': session.get('user_sid', ''),
            'saved_at': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
            'checks': {}, 'validated_by': '', 'validated_at': '',
        }
        _R()._conf_state_save(ref_state, state, 'ndf-fwdstart')

    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Confirmation Saved', 'NDF FWD Start',
                         '{} · {} ({} op{})'.format(acr, merc, len(rows),
                                                    '' if len(rows) == 1 else 's'))
    validate_url = ('/confirmation/ndf-fwdstart/validate?date=' + ref_state.strftime('%Y-%m-%d')
                    + '&acronym=' + _R().quote(acr) + '&mercadoria=' + _R().quote(merc)
                    + '&family=' + _R().quote(family))
    # A confirmação saiu: carimba a Data envio validação OTC nas linhas de
    # Manual Confirmations e guarda o endereço do PDF no Electronic
    # Inventory — é para onde o botão Abrir do Monitor manda. O link é do
    # papel que foi gravado, não da tela que o reconstrói: quem valida
    # precisa ver o que vai ao cliente, e a tela de geração pode montar
    # outra coisa se o day-file mudou desde então.
    _R()._mc_stamp_generated(picked, 'ndf-fwdstart',
                        link=_R()._mc_ei_link(conf['parteb_nome'] or acr,
                                         client_dir, pdf_path))
    return jsonify({'success': True, 'files': [doc_path, pdf_path] + xml_files,
                    'numero_contrato': numero_contrato,
                    'fepweb_updated': fep_updated,
                    'warnings': xml_warns,
                    'validate_url': validate_url})

@blueprint.route('/api/confirmation/ndf-fwdstart/pdf')
def api_conf_fwdstart_pdf():
    """Preview inline do PDF salvo da confirmação de NDF FWD Start."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    _ref, _key, entry, err = _R()._conf_state_entry_or_404(request.args, 'ndf-fwdstart')
    if err:
        return err
    pdf_path = (entry or {}).get('pdf') or ''
    if not pdf_path or not os.path.isfile(pdf_path):
        return ('PDF não encontrado no Inventory ({}).'.format(pdf_path), 404)
    return send_file(pdf_path, mimetype='application/pdf', as_attachment=False,
                     download_name=os.path.basename(pdf_path))

@blueprint.route('/confirmation/ndf-fwdstart/validate')
def confirmation_fwdstart_validate():
    """Janela de validação da confirmação de NDF FWD Start (checklist + preview)."""
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    ref, _key, entry, err = _R()._conf_state_entry_or_404(request.args, 'ndf-fwdstart')
    if err:
        return err
    acr = (request.args.get('acronym') or '').strip()
    merc = (request.args.get('mercadoria') or '').strip().upper()
    fam = (request.args.get('family') or 'strike-me').strip()
    qs = ('date=' + ref.strftime('%Y-%m-%d') + '&acronym=' + _R().quote(acr)
          + '&mercadoria=' + _R().quote(merc) + '&family=' + _R().quote(fam))
    return render_template('confirmations/validate.html',
                           acronym=acr, mercadoria=merc, family=fam,
                           ref_date=ref.strftime('%Y-%m-%d'),
                           ref_date_disp=ref.strftime('%d/%m/%Y'),
                           status=entry.get('status') or 'Generated',
                           saved_by=entry.get('saved_by') or '',
                           saved_at=entry.get('saved_at') or '',
                           validated_by=entry.get('validated_by') or '',
                           validated_at=entry.get('validated_at') or '',
                           checks=entry.get('checks') or {},
                           api_base='/api/confirmation/ndf-fwdstart',
                           pdf_url='/api/confirmation/ndf-fwdstart/pdf?' + qs)

@blueprint.route('/api/confirmation/ndf-fwdstart/validate', methods=['POST'])
def api_conf_fwdstart_validate():
    """Marca a confirmação de NDF FWD Start como Success após o checklist."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    payload = request.get_json(silent=True) or {}
    ref, key, entry, err = _R()._conf_state_entry_or_404(payload, 'ndf-fwdstart')
    if err:
        return jsonify({'success': False, 'message': err[0]}), err[1]
    checks = payload.get('checks') or {}
    if not checks or not all(bool(v) for v in checks.values()):
        return jsonify({'success': False,
                        'message': 'Todos os itens do checklist precisam ser confirmados.'}), 400
    with _R()._cache_lock:
        state = _R()._conf_state_load(ref, 'ndf-fwdstart')
        entry = state.get(key) or entry
        entry['status'] = 'Success'
        entry['checks'] = {str(k): True for k in checks}
        entry['validated_by'] = session.get('user_sid', '')
        entry['validated_at'] = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        state[key] = entry
        _R()._conf_state_save(ref, state, 'ndf-fwdstart')
    # O checklist fecha o ciclo do DOCUMENTO. A etapa do OTC na esteira NÃO é
    # carimbada aqui — ela é validada no Monitor. Ver o comentário onde o
    # `_mc_stamp_otc_validated` existia.
    #
    # E ele NÃO gera aviso no sino. Gerava um 'Confirmation Validated', e o sino
    # ficava com DOIS itens dizendo validado para a mesma confirmação: este, do
    # documento, e o 'Validated by OTC' da esteira — que é o que a mesa precisa
    # ver, porque diz quem assinou, quantas operações e para quem a confirmação
    # foi. O ciclo do documento (New → Generated → Success) continua visível no
    # card de Confirmations do New Deals Monitor, que é onde ele já era
    # acompanhado; o que saiu foi só a linha no sino.
    return jsonify({'success': True, 'status': 'Success'})
