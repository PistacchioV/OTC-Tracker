# -*- coding: utf-8 -*-
"""As rotas de Operations B3.

Só a casca: o store por dia e os mapas internos alimentam os advices e o _ds_handle — os helpers ficam no routes até a fase platform/, alcançados por _R().
"""
import traceback
from datetime import datetime

from flask import (jsonify, redirect, render_template, request,
                   session, url_for)

from apps.pages import blueprint


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


@blueprint.route('/operations-b3')
def operations_b3():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/operations-b3.html', segment='operations-b3',
                           today=_R()._br_now().strftime('%Y-%m-%d'))

@blueprint.route('/api/operations-b3/data')
def api_opb3_data():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    ds = (request.args.get('date') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    payload = _R()._opb3_collect(ref)
    payload.update({'success': True, 'date': ref.strftime('%Y-%m-%d'),
                    'date_fmt': ref.strftime('%d/%m/%Y')})
    return jsonify(payload)

@blueprint.route('/api/operations-b3/import', methods=['POST'])
def api_opb3_import():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    res = _R()._opb3_import(datetime.now())
    if res.get('success'):
        _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                             'Operations Imported', 'Operations B3',
                             '{}: {} row(s) imported ({})'.format(res.get('file', ''), res.get('rows', 0), res.get('date', '')))
    return jsonify(res)

@blueprint.route('/api/operations-b3/row/add', methods=['POST'])
def api_opb3_row_add():
    """Insert a manual row → status 'New' (maker = current user). Persisted to JSON."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    cells = p.get('cells') or []
    sid = session.get('user_sid', '')
    ref = _R()._opb3_ref_from(p)
    jp, data = _R()._opb3_load(ref)
    if data is None:
        data = []
    rec = {c: (str(cells[i]).strip() if i < len(cells) and cells[i] is not None else '')
           for i, c in enumerate(_R()._OPB3_COLUMNS)}
    rec['_ob_status'], rec['_ob_maker'], rec['_ob_checker'], rec['_ob_id'] = 'New', sid, '', _R()._otm_new_id()
    rec['_ob_src'] = 'manual'                           # keep manual rows across re-imports (merge preserves them)
    data.append(rec)
    try:
        _R()._otm_save(jp, data)
    except Exception:
        _R().log.error('[opb3] add save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Save failed.'}), 500
    _R()._create_notification(sid, session.get('user_name', ''), 'Operations B3 Row Added', 'Operations B3',
                         '{} ({})'.format(rec.get('Num Ctrl Operação', ''), ref.strftime('%Y-%m-%d')))
    return jsonify({'success': True, 'id': rec['_ob_id']})

@blueprint.route('/api/operations-b3/row/edit', methods=['POST'])
def api_opb3_row_edit():
    """Edit a row's cells → status 'Pending', maker = current user (checker reset)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    rid, cells = str(p.get('id', '')), (p.get('cells') or [])
    sid = session.get('user_sid', '')
    jp, data = _R()._opb3_load(_R()._opb3_ref_from(p))
    rec = _R()._opb3_find(data or [], rid)
    if rec is None:
        return jsonify({'success': False, 'error': 'Row not found.'}), 404
    for i, c in enumerate(_R()._OPB3_COLUMNS):
        if i < len(cells):
            rec[c] = str(cells[i]).strip()
    rec['_ob_status'], rec['_ob_maker'], rec['_ob_checker'] = 'Pending', sid, ''
    try:
        _R()._otm_save(jp, data)
    except Exception:
        _R().log.error('[opb3] edit save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Save failed.'}), 500
    _R()._create_notification(sid, session.get('user_name', ''), 'Operations B3 Row Updated', 'Operations B3',
                         '{} ({})'.format(rec.get('Num Ctrl Operação', ''), _R()._opb3_ref_from(p).strftime('%Y-%m-%d')))
    return jsonify({'success': True})

@blueprint.route('/api/operations-b3/row/delete', methods=['POST'])
def api_opb3_row_delete():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    rid = str(p.get('id', ''))
    sid = session.get('user_sid', '')
    jp, data = _R()._opb3_load(_R()._opb3_ref_from(p))
    if data is None:
        return jsonify({'success': False, 'error': 'No data for this date.'}), 404
    rec = _R()._opb3_find(data, rid)
    if rec is None:
        return jsonify({'success': False, 'error': 'Row not found.'}), 404
    data.remove(rec)
    try:
        _R()._otm_save(jp, data)
    except Exception:
        _R().log.error('[opb3] delete save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Save failed.'}), 500
    _R()._create_notification(sid, session.get('user_name', ''), 'Operations B3 Row Deleted', 'Operations B3',
                         '{} ({})'.format(rec.get('Num Ctrl Operação', ''), _R()._opb3_ref_from(p).strftime('%Y-%m-%d')))
    return jsonify({'success': True})

@blueprint.route('/api/operations-b3/row/confirm', methods=['POST'])
def api_opb3_row_confirm():
    """Confirm a row → 'OK'. Maker/checker guard: the user who changed it cannot
    confirm it (a different user must)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    rid = str(p.get('id', ''))
    sid = session.get('user_sid', '')
    jp, data = _R()._opb3_load(_R()._opb3_ref_from(p))
    rec = _R()._opb3_find(data or [], rid)
    if rec is None:
        return jsonify({'success': False, 'error': 'Row not found.'}), 404
    maker = str(rec.get('_ob_maker', '') or '')
    if maker and maker == sid:
        return jsonify({'success': False, 'error': 'same_user',
                        'message': 'A different user must confirm a row you changed.'}), 403
    rec['_ob_status'], rec['_ob_checker'] = 'OK', sid
    try:
        _R()._otm_save(jp, data)
    except Exception:
        _R().log.error('[opb3] confirm save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Save failed.'}), 500
    _R()._create_notification(sid, session.get('user_name', ''), 'Operations B3 Row Confirmed', 'Operations B3',
                         '{} ({})'.format(rec.get('Num Ctrl Operação', ''), _R()._opb3_ref_from(p).strftime('%Y-%m-%d')))
    return jsonify({'success': True})

@blueprint.route('/api/operations-b3/mensageria/recipients', methods=['GET', 'POST'])
def api_opb3_msg_recipients():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    if request.method == 'GET':
        return jsonify({'success': True, **_R()._opb3_msg_load_recipients()})
    try:
        cur = _R()._opb3_msg_save_recipients(request.get_json(silent=True) or {})
    except Exception as e:
        _R().log.error('[opb3-msg] save recipients failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': '{}: {}'.format(type(e).__name__, e)}), 500
    return jsonify({'success': True, **cur})

@blueprint.route('/api/operations-b3/mensageria', methods=['POST'])
def api_opb3_mensageria():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    from apps.pages import otc_emails
    p = request.get_json(silent=True) or {}
    ref = _R()._opb3_ref_from(p)
    jp, data = _R()._opb3_load(ref)
    if not data:
        return jsonify({'success': False, 'error': 'No Operations B3 data for {}.'.format(
            ref.strftime('%d/%m/%Y'))}), 400

    recips = _R()._opb3_msg_load_recipients()
    tipo_maps = _R()._opb3_tipo_maps(ref)
    names = _R()._opb3_refdata_by_account()
    # Linhas marcadas na tabela: só elas destravam a REgeração de uma operação
    # que já virou e-mail (status Generated). Sem marcação, o botão pega apenas
    # o que ainda não foi gerado.
    picked = {str(i) for i in (p.get('ids') or []) if str(i).strip()}

    # De que VISÃO a mensagem sai — cadastro `b3-accounts`, coluna Messaging.
    # A liquidação intragrupo chega pelos dois arquivos, espelhada (a visão do
    # Banco e a da outra entidade nossa), e as duas virando e-mail o time
    # cobraria duas vezes o mesmo pagamento. Era uma regra escrita aqui — casa
    # == MGT e contraparte == Banco —, que conhecia esse par e só ele: a visão
    # do Lawton e a da Atacama passavam direto.
    def _view_off(rec):
        return not _R()._b3_msg_view_use(rec.get('Conta', ''))

    def _bilateral(rec):
        m = _R()._fcst_norm(str(rec.get('Modalidade Liquidação', '') or ''))
        return m.startswith('bilateral') or m.startswith('bruta')

    # Linhas elegíveis, e são QUATRO perguntas que precisam concordar:
    #   1. o evento entra numa apuração de liquidação? — `opb3-events`, o mesmo
    #      cadastro (e a mesma função) que o NDF Summary, o Other Products e os
    #      avisos consultam: uma operação cancelada na B3 não pode virar
    #      mensagem pedindo o pagamento dela;
    #   2. a Modalidade de Liquidação é Bilateral*/Bruta*? — é o que a mensagem
    #      cobre;
    #   3. a mensagem sai na visão desta conta? — `b3-accounts`;
    #   4. a linha ainda não virou e-mail (ou foi marcada para regerar).
    # É um inner join: basta uma dizer não para a linha ficar de fora.
    ev_rules = _R()._opb3_event_rules()

    def _eligible(rec):
        if not _R()._opb3_settle_ok(rec, ev_rules):
            return False
        if not _bilateral(rec) or _view_off(rec):
            return False
        if str(rec.get('_ob_status', '') or '') == _R()._OPB3_STATUS_GENERATED:
            return str(rec.get('_ob_id', '') or '') in picked
        return True

    groups = {}
    for rec in data:
        if not _eligible(rec):
            continue
        tipo = _R()._opb3_tipo_for(rec, tipo_maps)
        conta_cp = str(rec.get('Conta Contraparte', '') or '').strip()
        tipo_op = str(rec.get('Tipo Operação', '') or '').strip()
        # Um e-mail por Tipo Operação, MENOS os vencimentos de swap: amortização
        # e juros contra a mesma contraparte são o mesmo pagamento partido em dois
        # eventos pela B3, e o time acata um valor só. A tabela do e-mail continua
        # mostrando cada linha com o seu Tipo Operação, então nada se perde ao
        # juntar — o que se ganha é o total a acatar e um batimento interno que
        # compara contrato contra contrato.
        ev = ('vencimento swap'
              if otc_emails.opb3_msg_is_swap_venc(rec.get('Tipo Título', ''), tipo_op)
              else _R()._fcst_norm(tipo_op))
        gkey = (tipo, conta_cp, ev)
        groups.setdefault(gkey, {'tipo': tipo, 'conta_cp': conta_cp, 'tipo_op': tipo_op,
                                 'recs': []})['recs'].append(rec)

    if not groups:
        return jsonify({'success': False,
                        'error': 'No pending Bilateral/Bruta operations for {} — tick the rows to '
                                 'regenerate the ones already marked as Generated.'.format(
                                     ref.strftime('%d/%m/%Y'))}), 400

    # Batimentos internos (carregados uma vez, usados por grupo conforme o caso).
    ter_map = _R()._opb3_internal_ter_map(ref)
    prem_map = _R()._opb3_internal_swapprem_map(ref)
    swap_map = _R()._opb3_internal_swap_map(ref)
    ndfc_map = _R()._opb3_internal_ndfc_map(ref)

    ref_fmt = ref.strftime('%d/%m/%Y')
    drafts, missing, used = [], set(), []
    for g in groups.values():
        recs = g['recs']
        titn = _R()._fcst_norm(str(recs[0].get('Tipo Título', '') or ''))
        opn = _R()._fcst_norm(g['tipo_op'])
        # Nome da contraparte, nesta ordem: Reference Data pela conta (o cliente
        # de fora), o `Reference Data Name` do cadastro `b3-accounts` (a
        # contraparte que é entidade NOSSA — ela não tem linha no Reference Data
        # pela conta B3) e, por último, o Nome Simplificado que veio no arquivo,
        # que é o apelido de 20 caracteres da B3 (`INTRAGLAWTONFDO`).
        cpty = (names.get(g['conta_cp'])
                or _R()._b3_account_refdata_name(g['conta_cp'])
                or str(recs[0].get('Contraparte (Nome Simpl.)', '') or '—'))
        total = sum(_R()._ndfc_valnum(r.get('Valor')) or 0.0 for r in recs)

        # Lado interno: TER de MOEDA → SETTLEMENT do card Trade Level do NDF
        # Summary, pela ótica da conta que assina a mensagem; TER de COMMODITY →
        # o Trade Level do Other Products (o Cockpit não tem a commodity); SWAP
        # prêmio → DAGENDAPREMIOS; SWAP vencimento → o Trade Level do Other
        # Products. A soma é por B3 ID DISTINTO: os mapas já trazem o total do
        # contrato, então iterar linha a linha contaria o mesmo contrato duas
        # vezes quando o grupo tem mais de uma operação sobre ele. Nenhum id
        # casando = sem fonte para comparar e o e-mail sai sem "Favor considerar"
        # — que é o certo: um valor inventado seria pior que a ausência dele.
        ids = {str(r.get('Título', '') or '').strip().upper() for r in recs} - {''}
        casa = _R()._acc_digits(recs[0].get('Conta', ''))
        if 'ter' in titn:
            # Moeda primeiro; o que ela não conhece é commodity. O contrato está
            # numa das duas fontes, nunca nas duas — somar as duas duplicaria.
            vals = [(_R()._opb3_internal_leg(ter_map, i, casa)
                     if i in ter_map else ndfc_map.get(i)) for i in ids]
        elif 'swap' in titn and opn == 'pagamento de premio':
            vals = [prem_map.get(i) for i in ids]
        elif otc_emails.opb3_msg_is_swap_venc(recs[0].get('Tipo Título', ''), g['tipo_op']):
            vals = [swap_map.get(i) for i in ids]
        else:
            vals = []
        vals = [v for v in vals if v is not None]
        internal = sum(vals) if vals else None

        rows = [[
            'JPMORGANBM',
            str(r.get('Conta', '') or ''),
            str(r.get('Tipo Operação', '') or ''),
            str(r.get('C/V', '') or ''),
            str(r.get('Título', '') or ''),
            str(r.get('Tipo Título', '') or ''),
            _R()._swapchar_fmt_value(r.get('Valor', '')),
            'CETIP21',
            str(r.get('Modalidade Liquidação', '') or ''),
            str(r.get('Status', '') or ''),
            str(r.get('Contraparte (Nome Simpl.)', '') or ''),
            str(r.get('Conta Contraparte', '') or ''),
        ] for r in recs]

        rk = _R()._opb3_msg_route_key(g['tipo'])
        to, cc = recips[rk]['to'], recips[rk]['cc']
        if not to:
            missing.add(rk.upper())
        # BCC compliance (GDT): Atacama sempre; Lawton só quando Tipo Título =
        # SWAP e a somatória é "Banco recebe do(a)" (≥ 0) — nos demais casos
        # contra o Lawton o BCC fica em branco.
        #
        # Quem é a contraparte sai da CONTA no cadastro `b3-accounts`, e o Nome
        # Simplificado do arquivo é o plano B: a conta é o identificador, o
        # apelido de 20 caracteres é como aquele arquivo escreveu o nome — e uma
        # entidade nova entra no cadastro, não aqui.
        cp_le = _R()._b3_account_le(g['conta_cp'])
        cp_simpl = str(recs[0].get('Contraparte (Nome Simpl.)', '') or '').strip().upper()
        is_atacama = cp_le == 'ATACAMA' or (not cp_le and cp_simpl.startswith('INTRAGATACAMA'))
        is_lawton = cp_le == 'LAWTON' or (not cp_le and cp_simpl.startswith('INTRAGLAWTON'))
        bcc = ''
        if is_atacama:
            bcc = _R()._OPB3_MSG_GDT_BCC
        elif is_lawton and 'swap' in titn and total >= 0:
            bcc = _R()._OPB3_MSG_GDT_BCC
        drafts.append(otc_emails.build_opb3_mensageria_email({
            'tipo': g['tipo'], 'tipo_titulo': recs[0].get('Tipo Título', ''),
            'tipo_operacao': g['tipo_op'], 'cpty': cpty, 'ref_date': ref_fmt,
            'rows': rows, 'total': total, 'internal': internal, 'to': to, 'cc': cc,
            'bcc': bcc,
        }))
        used.extend(recs)

    if missing:
        return jsonify({'success': False,
                        'error': 'Set the TO recipients on the {} card(s) first.'.format(' and '.join(sorted(missing)))}), 400

    # Só depois de os drafts estarem prontos: as linhas que viraram e-mail ficam
    # Generated (o botão passa a ignorá-las) e o Status B3 vai a FINALIZADA.
    for rec in used:
        rec['_ob_status'] = _R()._OPB3_STATUS_GENERATED
        rec['Status'] = _R()._OPB3_B3_STATUS_DONE
    # A visão marcada como Disregard não gera e-mail, mas a liquidação dela saiu
    # pela outra ponta — fica Generated para a tabela não sugerir que ficou algo
    # pendente. Só a linha que o cadastro `opb3-events` aprova: a operação
    # cancelada na B3 não saiu por ponta nenhuma, e carimbá-la de Generated
    # esconderia justamente a linha que ninguém tratou.
    for rec in data:
        if _bilateral(rec) and _view_off(rec) and _R()._opb3_settle_ok(rec, ev_rules):
            rec['_ob_status'] = _R()._OPB3_STATUS_GENERATED
    try:
        _R()._otm_save(jp, data)
    except Exception:
        _R().log.error('[opb3-msg] status save failed:\n%s', traceback.format_exc())
    return _R()._email_drafts_response(drafts, zip_name='mensageria_{}'.format(ref.strftime('%Y%m%d')))
