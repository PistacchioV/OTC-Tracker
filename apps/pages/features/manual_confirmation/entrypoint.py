# -*- coding: utf-8 -*-
"""As dezessete rotas da esteira de confirmação manual (Monitor, Track,
validação, geração e o ciclo de upsert/derive).

Só a casca: o MOTOR é o `manual_conf.py` (horizontal) e os helpers `_mc_*` do
routes são compartilhados com os saves do New Deals e com o espelho do Pending
Confirmation (`_mc_save_from_deal`, `_mc_pc_sync`, os carimbos) — ficam lá até
a fase `platform/`, alcançados por `_R()`.
"""
import os
import traceback
from datetime import datetime

from flask import (jsonify, redirect, render_template, request,
                   session, url_for)

from apps.pages import blueprint


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


@blueprint.route('/manual-confirmation')
def manual_confirmation():
    """O item do menu apontava para cá antes das duas telas existirem. Mantido
    como porta de entrada, levando ao Monitor — que é o primeiro item da lista e
    a tela por onde o trabalho começa."""
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return redirect(url_for('pages_blueprint.manual_confirmation_monitor'))

@blueprint.route('/manual-confirmation/monitor')
def manual_confirmation_monitor():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/manual-confirmation-monitor.html',
                           segment='manual-confirmation-monitor')

@blueprint.route('/manual-confirmation/track')
def manual_confirmation_track():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    from apps.pages import manual_conf as _mc
    return render_template('pages/manual-confirmation-track.html',
                           segment='manual-confirmation-track',
                           mc_columns=_mc.COLUMNS,
                           mc_labels=_mc.COLUMN_LABELS,
                           mc_dates=_mc.DATE_COLUMNS,
                           mc_derived=_mc.DERIVED_COLUMNS,
                           mc_key=_mc.KEY_COLUMN,
                           # Colunas de domínio fechado: a tela monta um <select>
                           # em vez de um campo livre. Produto digitado à mão era
                           # o que fazia a linha nascer com um nome que nem o
                           # cadastro de validação nem a pasta do Electronic
                           # Inventory reconheciam.
                           mc_options={'Produto': list(_mc.CONFIRMATION_TYPES)})

@blueprint.route('/api/manual-confirmation/data')
def api_mc_data():
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        from apps.pages import manual_conf as _mc
        rows = _mc.load_all()
        # FepWeb ID: a célula vazia é completada do Pending Confirmation (a
        # fonte, gravada pela geração) — melhor esforço, e `rows` já volta
        # preenchido nesta resposta. Ver `_mc_sync_fepweb_ids`.
        try:
            _R()._mc_sync_fepweb_ids(rows)
        except Exception:
            _R().log.warning('[manual-conf] FepWeb ID sync: %s', traceback.format_exc())
        return jsonify({'columns': _mc.COLUMNS, 'labels': _mc.COLUMN_LABELS,
                        'data': rows, 'counts': _R()._mc_counts(rows)})
    except Exception as e:
        _R().log.error('[manual-conf] data: %s', e)
        return jsonify({'error': str(e)}), 500

@blueprint.route('/api/manual-confirmation/monitor')
def api_mc_monitor():
    """Os cards do Monitor — SEM os documentos.

    Resolver a pasta de cada confirmação no Electronic Inventory custa uma
    varredura do share de rede POR GRUPO; feito aqui dentro, o Monitor levava
    a soma de todas elas para abrir. O payload sai na hora e a página busca os
    PDFs de cada item em paralelo no endpoint /docs abaixo.
    """
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        from apps.pages import manual_conf as _mc
        payload = _mc.monitor_payload()
        # Quem a sessão pode assinar, por etapa. O `monitor_payload` não sabe da
        # sessão (e não deve saber: ele é o retrato da fila, igual para todos), e
        # é a página que troca o botão verde de Validar por um de só leitura.
        payload['can_validate'] = {s: _R()._mc_can_validate(s)
                                   for s in (_mc.STAGE_OTC, _mc.STAGE_MO, _mc.STAGE_FO)}
        # Os botões dos cards Legal/FepWeb são ações do OTC Ops: mesma trava.
        payload['can_validate']['LEGAL'] = payload['can_validate'][_mc.STAGE_OTC]
        payload['can_validate']['FEPWEB'] = payload['can_validate'][_mc.STAGE_OTC]
        payload['stage_role'] = dict(_R()._MC_STAGE_ROLE)
        return jsonify(payload)
    except Exception as e:
        _R().log.error('[manual-conf] monitor: %s', e)
        return jsonify({'error': str(e)}), 500

@blueprint.route('/api/manual-confirmation/docs')
def api_mc_docs():
    """Os PDFs de UMA confirmação (cliente × produto × data da operação).

    Chamado pelo Monitor item a item, depois de os cards já estarem na tela —
    é o que deixa a lista abrir na hora mesmo com o share de rede lento.
    """
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401
    row = {'Cliente': request.args.get('cliente', ''),
           'Produto': request.args.get('produto', ''),
           'LOB': request.args.get('lob', ''),
           'Moeda': request.args.get('ativo', ''),
           'Data Operação': request.args.get('data', '')}
    trades = [t.strip() for t in (request.args.get('trades') or '').split(',') if t.strip()]
    docs = _R()._mc_confirmation_docs(row, trades)
    _R()._mc_flush_email_subjects(_R()._mc_sync_email_subjects(docs, trades))
    return jsonify({'docs': docs})

@blueprint.route('/api/manual-confirmation/docs', methods=['POST'])
def api_mc_docs_batch():
    """Os PDFs de VÁRIAS confirmações de uma vez.

    O Monitor pedia um GET por item. Cada um esperava a sua vez numa fila de 4
    threads (waitress) e ia sozinho ao share, então a última confirmação da tela
    só aparecia depois de todas as anteriores — e o navegador ainda limita as
    conexões simultâneas por host. Numa chamada só, o servidor resolve a lista em
    sequência com o cache de pasta quente: as confirmações do mesmo cliente no
    mesmo dia dividem a MESMA pasta e custam uma ida só.

    A resposta vem na ORDEM em que os itens chegaram — é assim que a tela casa
    cada lista com o seu item, sem precisar de identificador.
    """
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401
    itens = (request.get_json(silent=True) or {}).get('items') or []
    if not isinstance(itens, list):
        return jsonify({'error': 'items must be a list'}), 400
    # Raiz inacessível é o diagnóstico que NENHUM item consegue dar sozinho:
    # cada um só vê a própria pasta "inexistente". Um drive mapeado que o
    # processo não enxerga produz exatamente um Monitor 100% 'no PDF'.
    if not os.path.isdir(_R().ELECTRONIC_INVENTORY_ROOT):
        _R().log.warning('[manual-conf] docs: raiz do Electronic Inventory inacessível '
                    'deste processo: %s', _R().ELECTRONIC_INVENTORY_ROOT)
    else:
        # Aquece o scan da raiz UMA vez por lote. Sem isto, com o cache frio
        # (logo depois de um restart), cada item pagava a própria listagem da
        # raiz inteira pela rede — 50 cards viravam 50 varreduras, o lote
        # estourava o prazo da página e TODOS os cards diziam 'no PDF'. Quem
        # aquecia o cache era a página do Electronic Inventory; a fila do
        # Monitor não pode depender de alguém ter aberto outra tela.
        _R()._ei_scan_root(grace=10.0)
    out, assuntos = [], {}
    for it in itens[:200]:
        if not isinstance(it, dict):
            out.append([])
            continue
        trades = it.get('trades') or []
        docs = _R()._mc_confirmation_docs({
            'Cliente': it.get('cliente', ''), 'Produto': it.get('produto', ''),
            'LOB': it.get('lob', ''), 'Moeda': it.get('ativo', ''),
            'Data Operação': it.get('data', '')}, trades)
        out.append(docs)
        assuntos.update(_R()._mc_sync_email_subjects(docs, trades))
    # UMA gravação para o lote inteiro: por item, cada uma releria os dois bancos
    # para escrever uma célula, e o Monitor manda até 200 itens de uma vez.
    _R()._mc_flush_email_subjects(assuntos)
    return jsonify({'docs': out})

@blueprint.route('/manual-confirmation/generate')
def manual_confirmation_generate():
    """Abre o editor da confirmação de um item do Monitor (botão Generate).

    Redireciona em vez de renderizar: a tela de geração é a mesma de sempre, e
    duplicá-la aqui criaria um segundo documento para o mesmo produto. O que vai
    junto é o `mc_keys` — é por ele que o editor sabe que, depois de gravar,
    quem abre é a validação da ESTEIRA e não o checklist do documento.
    """
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    from apps.pages import manual_conf as _mc
    keys = [k.strip() for k in (request.args.get('keys') or '').split(',') if k.strip()]
    rows = [r for r in (_mc.find_row(k) for k in keys) if r is not None]
    if not rows:
        return render_template('confirmations/manual-validate.html',
                               found=False, stage=_mc.STAGE_OTC, keys=keys), 404
    url, motivo = '', ''
    for row in rows:
        url, motivo = _R()._mc_generate_url(row, keys)
        if url:
            break
    if not url:
        _R().log.warning('[manual-conf] Generate sem destino para %s: %s', keys, motivo)
        return render_template('confirmations/manual-generate-error.html',
                               keys=keys, motivo=motivo,
                               cliente=rows[0].get('Cliente', ''),
                               produto=rows[0].get('Produto', ''),
                               data=rows[0].get('Data Operação', '')), 404
    return redirect(url + '&mc_keys=' + _R().quote(','.join(keys)))

@blueprint.route('/manual-confirmation/validate')
def manual_confirmation_validate():
    """A tela de validação de UMA confirmação: PDF ao lado, checklist da etapa e
    o histórico das três mesas.

    O Monitor abria a validação com um clique só, e um clique não é conferência:
    quem carimba assina que olhou o documento. Esta é a mesma ideia da tela de
    checklist do OTC no New Deals — e por isso ela mostra o PDF que foi (ou vai
    ser) enviado ao cliente, não uma remontagem dele.

    A confirmação é identificada pelas CHAVES do grupo, porque um documento cobre
    várias operações: validar trade a trade faria a mesma folha ser conferida dez
    vezes.
    """
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    from apps.pages import manual_conf as _mc
    keys = [k.strip() for k in (request.args.get('keys') or '').split(',') if k.strip()]
    stage = (request.args.get('stage') or '').strip().upper()
    if stage not in (_mc.STAGE_OTC, _mc.STAGE_MO, _mc.STAGE_FO):
        stage = _mc.STAGE_OTC
    rows = [r for r in (_mc.find_row(k) for k in keys) if r is not None]
    if not rows:
        return render_template('confirmations/manual-validate.html',
                               found=False, stage=stage, keys=keys), 404
    row = rows[0]
    sla = _mc.sla_state(row, stage)
    # O grupo vale pela operação MAIS APERTADA — o documento é um só.
    for r in rows[1:]:
        s = _mc.sla_state(r, stage)
        if _mc._SLA_ORDEM.index(s['level']) > _mc._SLA_ORDEM.index(sla['level']):
            sla = s
    col_data, _col_stamp = _mc.STAGE_COLUMNS[stage]
    # A tela de validação varre a MESMA pasta que o Monitor, então ela também
    # atualiza o E-mail Subject: sem isto, a coluna só se preenchia para as
    # confirmações que apareceram num card, e uma confirmação aberta direto pelo
    # link ficava com a célula vazia com o recap na pasta.
    _keys = [str(r.get(_mc.KEY_COLUMN, '') or '') for r in rows]
    docs = _R()._mc_confirmation_docs(row, _keys)
    _R()._mc_flush_email_subjects(_R()._mc_sync_email_subjects(docs, _keys))
    return render_template(
        'confirmations/manual-validate.html',
        found=True,
        keys=keys, stage=stage,
        cliente=row.get('Cliente', ''), tipo=_mc.confirmation_type(row.get('Produto'), row.get('LOB')),
        lob=row.get('LOB', ''), ativo=row.get('Moeda', ''),
        trade_date=row.get('Data Operação', ''),
        legal_entity=row.get('Legal Entity', ''),
        trades=[str(r.get(_mc.KEY_COLUMN, '') or '') for r in rows],
        checks=_mc.checklist_for(stage),
        history=_mc.stage_history(row),
        # `already` trava o botão: revalidar recarimbaria por cima de quem
        # assinou antes, apagando o dono da conferência anterior.
        already=bool(str(row.get(col_data, '') or '').strip()),
        # A etapa é assinada pela MESA dela. Quem não é da mesa abre a tela e lê
        # o documento — o que some são os dois botões, não o papel: esconder a
        # confirmação faria o OTC deixar de ver o que o MO está conferindo.
        can_validate=_R()._mc_can_validate(stage),
        stage_role=_R()._MC_STAGE_ROLE.get(stage, ''),
        # Rejeitar é devolver ao OTC — que é quem monta o documento. O próprio
        # OTC não tem para quem devolver, então o botão não existe na etapa dele.
        can_reject=(stage != _mc.STAGE_OTC and _R()._mc_can_validate(stage)),
        sla_level=sla['level'], sla_left=sla['left'],
        sla_deadline=_mc.fmt_date(sla['deadline']),
        sla_days=_mc.sla_days().get(stage),
        comment=row.get(_mc.STAGE_COMMENT_COLUMN.get(stage, ''), ''),
        docs=docs)

@blueprint.route('/api/manual-confirmation/upsert', methods=['POST'])
def api_mc_upsert():
    """Grava uma linha (edição no modal, linha nova ou edição em massa)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    from apps.pages import manual_conf as _mc
    payload = request.get_json(silent=True) or {}
    rows = payload.get('rows')
    if rows is None:
        rows = [payload.get('row') or {}]
    if not isinstance(rows, list):
        return jsonify({'success': False, 'message': 'rows must be a list'}), 400
    sid = session.get('user_sid', '')
    etapas = (_mc.STAGE_OTC, _mc.STAGE_MO, _mc.STAGE_FO)
    # Monta TUDO antes de gravar: uma edição em massa que falha na quinta linha
    # não pode deixar as quatro primeiras salvas e o usuário sem saber quais.
    pendentes = []
    for src in rows:
        if not isinstance(src, dict):
            continue
        key = str(src.get(_mc.KEY_COLUMN, '') or '').strip()
        if not key:
            # Sem Trade ID a linha não tem chave: o próximo upsert apagaria a
            # anterior sem chave e ficaria uma só. Recusa em vez de perder linha.
            return jsonify({'success': False,
                            'message': 'Trade ID é obrigatório — é a chave da linha.'}), 400
        row = _mc.find_row(key) or _mc.blank_row()
        # Estado ANTES da edição: é ele que diz se esta gravação é uma validação
        # nova (a coluna estava vazia e passou a ter data) ou só um ajuste de
        # cadastro numa linha que já estava validada.
        antes = {s: str(row.get(_mc.STAGE_COLUMNS[s][0], '') or '').strip() for s in etapas}
        # O prazo é medido no estado ANTERIOR: depois de escrever a data, a
        # própria `sla_state` responde `done` e o atraso desapareceria da conta.
        atrasado = {s: _mc.sla_breached(row, s) for s in etapas}

        for c in _mc.COLUMNS:
            if c in src and c not in _mc.DERIVED_COLUMNS:
                row[c] = str(src.get(c) or '')

        # ── Pending é derivada, MAS aceita dois valores à mão (§254/§255) ─────
        # 'Pending Legal' é o hold manual (a linha sai da fila do OTC até alguém
        # soltá-la) e 'Pending OTC' REABRE a esteira: a confirmação foi regerada
        # e precisa ser validada de novo, então as datas de validação e o
        # Enviado p/ cliente são limpos (os carimbos caem no undo logo abaixo) e
        # a derivação a devolve à fila do OTC — cada mesa revalida e os carimbos
        # novos substituem os antigos. Numa linha que só estava em hold Legal
        # não há o que limpar, e o mesmo valor age como o release de antes. Todo
        # o resto — FepWeb, Ok, MO/FO — continua saindo SÓ da derivação: gravar
        # 'Pending FepWeb' à mão afirmaria que a esteira terminou sem ninguém
        # ter validado nada, e por isso qualquer outro valor é ignorado.
        if 'Pending' in src:
            novo = str(src.get('Pending') or '').strip()
            if _mc.upper_norm(novo) == _mc.upper_norm(_mc.PENDING_LEGAL):
                row['Pending'] = _mc.PENDING_LEGAL
            elif _mc.upper_norm(novo) == _mc.upper_norm(_mc.PENDING_OTC):
                limpar = [c for c in ('Conferido OTC', 'VALIDADO p/ MO',
                                      'VALIDADO p/ FO', _mc.SENT_COLUMN)
                          if str(row.get(c, '') or '').strip()]
                # Reabrir é desfazer validação alheia — ato da mesa de OTC Ops,
                # como os dois botões do Monitor. Soltar um hold sem nada
                # validado não apaga trabalho de ninguém e segue livre.
                if limpar and not _R()._mc_can_validate(_mc.STAGE_OTC):
                    return jsonify({'success': False, 'stage_forbidden': True,
                                    'stage': _mc.STAGE_OTC, 'key': key,
                                    'message': _R()._mc_stage_denied(_mc.STAGE_OTC)}), 403
                row['Pending'] = ''          # a derivação decide (→ Pending OTC)
                for c in limpar:
                    row[c] = ''

        # ── Preencher a coluna de validação pela grade É VALIDAR ──────────────
        # A tela de validação passa pelo `mark_validated`, que carimba quem
        # assinou, cobra a justificativa fora do prazo e exige a mesa certa. A
        # grade escrevia a MESMA coluna como texto livre: a validação entrava sem
        # dono, sem motivo do atraso e assinada por qualquer papel — e a
        # segregação de funções valia só no caminho de cima.
        for stage in etapas:
            col_data, col_stamp = _mc.STAGE_COLUMNS[stage]
            depois = str(row.get(col_data, '') or '').strip()
            if depois and not antes[stage]:
                if not _R()._mc_can_validate(stage):
                    return jsonify({'success': False, 'stage_forbidden': True,
                                    'stage': stage, 'key': key,
                                    'message': _R()._mc_stage_denied(stage)}), 403
                comentario = str(row.get(_mc.STAGE_COMMENT_COLUMN.get(stage, ''), '') or '').strip()
                if atrasado[stage] and not comentario:
                    # 409, não 400: o pedido está bem formado — o ESTADO é que
                    # exige mais um campo. A tela usa isso para abrir a coluna de
                    # comentário em vez de mostrar um erro genérico.
                    return jsonify({'success': False, 'sla_comment_required': True,
                                    'stage': stage, 'key': key,
                                    'column': _mc.STAGE_COMMENT_COLUMN.get(stage, ''),
                                    # Em INGLÊS, como todo texto de servidor que
                                    # a tela exibe: a SweetAlert do Track mostra
                                    # a frase crua, e ela apareceria em português
                                    # com a aplicação em inglês.
                                    'message': ('{} validation on {} is past the deadline — '
                                                'fill in "{}" with the reason for the delay.'
                                                .format(stage, key,
                                                        _mc.STAGE_COMMENT_COLUMN.get(stage, '')))}), 409
                # Carimbo de quem assinou. Um `Time Stamp` que veio no corpo é
                # respeitado (a grade também serve para corrigir cadastro
                # antigo); o que não pode é a validação nascer sem dono.
                if not str(row.get(col_stamp, '') or '').strip():
                    row[col_stamp] = _mc.stamp_now(sid)
            elif antes[stage] and not depois:
                # Desfez a validação: o carimbo não sobrevive a ela. Deixá-lo
                # afirmaria que alguém assinou uma etapa que está pendente.
                row[col_stamp] = ''
        pendentes.append(row)

    saved = []
    for row in pendentes:
        _mc.upsert_row(row)
        saved.append(row)
    _R()._mc_pc_sync(saved)
    return jsonify({'success': True, 'rows': saved})

@blueprint.route('/api/manual-confirmation/legal-release', methods=['POST'])
def api_mc_legal_release():
    """O botão do card Pending Legal do Monitor: solta o hold do jurídico e a
    confirmação entra na fila do OTC — aqui e no Pending Confirmation (espelho).
    A ação é da mesa de OTC Ops, a mesma trava da etapa OTC."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    from apps.pages import manual_conf as _mc
    if not _R()._mc_can_validate(_mc.STAGE_OTC):
        return jsonify({'success': False, 'stage_forbidden': True,
                        'message': _R()._mc_stage_denied(_mc.STAGE_OTC)}), 403
    payload = request.get_json(silent=True) or {}
    keys = [str(k).strip() for k in (payload.get('keys') or []) if str(k or '').strip()]
    saved = []
    for k in keys:
        row = _mc.find_row(k)
        if row is None or _mc.upper_norm(row.get('Pending')) != _mc.upper_norm(_mc.PENDING_LEGAL):
            continue                     # só solta o que está de fato no hold
        row['Pending'] = ''              # a derivação decide a etapa real
        _mc.refresh_derived(row)
        _mc.upsert_row(row)
        saved.append(row)
    if not saved:
        return jsonify({'success': False,
                        'message': 'No confirmation in Pending Legal for these trades.'}), 404
    _R()._mc_pc_sync(saved)
    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Manual Confirmation', 'Confirmation',
                         'Legal hold released · {}{}'.format(
                             saved[0].get('Cliente', '') or keys[0],
                             ' (%d ops)' % len(saved) if len(saved) > 1 else ''),
                         target_role=_R()._mc_notify_roles(saved))
    return jsonify({'success': True, 'rows': saved})

@blueprint.route('/api/manual-confirmation/fepweb-sent', methods=['POST'])
def api_mc_fepweb_sent():
    """O botão do card Pending FepWeb do Monitor: carimba o Enviado p/ cliente
    com a data de hoje — a confirmação vira Ok na esteira e, no Pending
    Confirmation, passa a aguardar a assinatura (Digital/Original pelo
    Signature Type do Reference Data, via `_mc_pc_sync`)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    from apps.pages import manual_conf as _mc
    if not _R()._mc_can_validate(_mc.STAGE_OTC):
        return jsonify({'success': False, 'stage_forbidden': True,
                        'message': _R()._mc_stage_denied(_mc.STAGE_OTC)}), 403
    payload = request.get_json(silent=True) or {}
    keys = [str(k).strip() for k in (payload.get('keys') or []) if str(k or '').strip()]
    hoje = datetime.now().strftime('%d/%m/%Y')
    saved = []
    for k in keys:
        row = _mc.find_row(k)
        if row is None or _mc.upper_norm(row.get('Pending')) != _mc.upper_norm(_mc.PENDING_FEPWEB):
            continue                     # enviado é só para quem terminou a esteira
        if not str(row.get(_mc.SENT_COLUMN, '') or '').strip():
            row[_mc.SENT_COLUMN] = hoje
        _mc.refresh_derived(row)
        _mc.upsert_row(row)
        saved.append(row)
    if not saved:
        return jsonify({'success': False,
                        'message': 'No confirmation in Pending FepWeb for these trades.'}), 404
    _R()._mc_pc_sync(saved)
    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Manual Confirmation', 'Confirmation',
                         'Sent to client (FepWeb) · {}{}'.format(
                             saved[0].get('Cliente', '') or keys[0],
                             ' (%d ops)' % len(saved) if len(saved) > 1 else ''),
                         target_role=_R()._mc_notify_roles(saved))
    return jsonify({'success': True, 'rows': saved})

@blueprint.route('/api/manual-confirmation/derive', methods=['POST'])
def api_mc_derive():
    """Recalcula as derivadas de um lote de linhas SEM gravar — é o que a edição
    em massa usa para mostrar Pending e Aging já corretos antes de salvar."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    from apps.pages import manual_conf as _mc
    payload = request.get_json(silent=True) or {}
    rows = payload.get('rows')
    if not isinstance(rows, list):
        return jsonify({'success': False, 'message': 'rows must be a list'}), 400
    rules = _mc.validation_rules()
    out = []
    for src in rows:
        row = dict(src) if isinstance(src, dict) else {}
        _mc.refresh_derived(row, rules)
        out.append({c: row.get(c, '') for c in _mc.DERIVED_COLUMNS})
    return jsonify({'success': True, 'rows': out})

@blueprint.route('/api/manual-confirmation/delete', methods=['POST'])
def api_mc_delete():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    from apps.pages import manual_conf as _mc
    payload = request.get_json(silent=True) or {}
    keys = payload.get('keys') or ([payload.get('key')] if payload.get('key') else [])
    n = 0
    for k in keys:
        if str(k or '').strip():
            _mc.delete_row(k)
            n += 1
    return jsonify({'success': True, 'deleted': n})

@blueprint.route('/api/manual-confirmation/validate', methods=['POST'])
def api_mc_validate():
    """Valida uma etapa. O SPN vem da SESSÃO, não do corpo do POST — quem
    carimba é quem está logado, e aceitar o SPN do cliente deixaria qualquer
    sessão assinar por outra pessoa."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    from apps.pages import manual_conf as _mc
    payload = request.get_json(silent=True) or {}
    # A validação é da CONFIRMAÇÃO, e um documento cobre várias operações — por
    # isso o corpo traz `keys`. Validar trade a trade faria a mesma folha ser
    # conferida dez vezes, e bastaria esquecer uma para o grupo travar.
    keys = payload.get('keys') or ([payload.get('key')] if payload.get('key') else [])
    keys = [str(k).strip() for k in keys if str(k or '').strip()]
    stage = str(payload.get('stage') or '').strip().upper()
    if stage not in (_mc.STAGE_OTC, _mc.STAGE_MO, _mc.STAGE_FO):
        return jsonify({'success': False, 'message': 'Etapa inválida.'}), 400
    # A trava de verdade é aqui, e não no botão: a tela esconde, o endpoint
    # garante. Sem isto, um POST direto assinaria pela mesa de qualquer um.
    if not _R()._mc_can_validate(stage):
        return jsonify({'success': False, 'stage_forbidden': True,
                        'message': _R()._mc_stage_denied(stage)}), 403
    comment = str(payload.get('comment') or '').strip()
    try:
        rows = [r for r in (_mc.mark_validated(k, stage, session.get('user_sid', ''), comment)
                            for k in keys) if r is not None]
    except _mc.SlaCommentRequired:
        # 409 e não 400: o pedido está bem formado, o ESTADO é que exige mais um
        # campo. A tela usa `sla_comment_required` para abrir o campo em vez de
        # mostrar um erro genérico.
        return jsonify({'success': False, 'sla_comment_required': True,
                        'stage': stage,
                        'message': 'Validação fora do prazo: informe o motivo do atraso.'}), 409
    if not rows:
        return jsonify({'success': False, 'message': 'Confirmação não encontrada.'}), 404
    _R()._mc_pc_sync(rows)
    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Manual Confirmation', 'Confirmation',
                         # Em INGLÊS como todo o resto do sino: o detalhe é
                         # gravado no banco e o feed o mostra cru, então texto de
                         # servidor em português aparecia em português com a tela
                         # em inglês.
                         'Validated by {} · {}{}'.format(
                             stage, rows[0].get('Cliente', '') or keys[0],
                             ' (%d ops)' % len(rows) if len(rows) > 1 else ''),
                         # Avisa a mesa que a confirmação ACABOU de cair em cima,
                         # não a que acabou de assinar: quem precisa agir é quem
                         # vem depois. O Back Office vai junto porque acompanha a
                         # esteira inteira — é dele o documento.
                         target_role=_R()._mc_notify_roles(rows))
    return jsonify({'success': True, 'row': rows[0], 'rows': rows})

@blueprint.route('/api/manual-confirmation/reject', methods=['POST'])
def api_mc_reject():
    """Reject de MO/FO: devolve a confirmação para Pending OTC e avisa a mesa.

    A gravação vem ANTES do e-mail de propósito: a confirmação precisa voltar
    para o OTC mesmo que o relay não responda. O retorno diz se o e-mail saiu.
    """
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    from apps.pages import manual_conf as _mc
    payload = request.get_json(silent=True) or {}
    keys = payload.get('keys') or ([payload.get('key')] if payload.get('key') else [])
    keys = [str(k).strip() for k in keys if str(k or '').strip()]
    stage = str(payload.get('stage') or '').strip().upper()
    comment = str(payload.get('comment') or '').strip()
    if stage not in (_mc.STAGE_MO, _mc.STAGE_FO):
        return jsonify({'success': False, 'message': 'Só MO e FO rejeitam.'}), 400
    # Rejeitar é a outra resposta à MESMA pergunta que o validar responde — o
    # documento está certo? —, então quem não assina a etapa também não a devolve.
    if not _R()._mc_can_validate(stage):
        return jsonify({'success': False, 'stage_forbidden': True,
                        'message': _R()._mc_stage_denied(stage)}), 403
    if not comment:
        # Sem comentário o aviso chega dizendo "refaça" e nada mais — e o OTC
        # tem de perguntar de volta o que estava errado.
        return jsonify({'success': False,
                        'message': 'O comentário é obrigatório: é ele que diz o que refazer.'}), 400
    before = next((r for r in (_mc.find_row(k) for k in keys) if r is not None), None)
    if before is None:
        return jsonify({'success': False, 'message': 'Confirmação não encontrada.'}), 404
    sid = session.get('user_sid', '')
    # O documento inteiro volta para o OTC: rejeitar só uma operação deixaria as
    # outras esperando um papel que já foi devolvido.
    for k in keys:
        _mc.reject(k, stage, sid, comment)
    _R()._mc_pc_sync([r for r in (_mc.find_row(k) for k in keys) if r is not None])
    emailed = False
    try:
        from apps.pages.otc_emails import send_mc_reject_email
        emailed = send_mc_reject_email(before, stage, sid, comment)
    except Exception:
        _R().log.warning('[manual-conf] aviso de reject falhou:\n%s', traceback.format_exc())
    _R()._create_notification(sid, session.get('user_name', ''),
                         'Manual Confirmation', 'Confirmation',
                         # `keys[0]`, não `key`: essa variável nunca existiu nesta
                         # função — a linha só não estourava porque o `or` à
                         # esquerda quase sempre tem o Cliente preenchido.
                         'Rejected by {} · {}'.format(
                             stage, before.get('Cliente', '') or (keys[0] if keys else '')),
                         # O reject devolve o documento para Pending OTC, então
                         # quem precisa saber é o Back Office — é ele que vai
                         # refazer. Mesma regra da validação, lida do estado.
                         target_role=_R()._mc_notify_roles(
                             [r for r in (_mc.find_row(k) for k in keys) if r is not None]))
    return jsonify({'success': True, 'emailed': bool(emailed)})

@blueprint.route('/api/manual-confirmation/email-preview')
def api_mc_email_preview():
    """O e-mail de recap (.msg/.eml) da pasta da confirmação, como HTML — o
    Monitor o abre numa aba nova. Abrir o arquivo cru baixaria o .msg e
    mandaria a pessoa para o Outlook, que é o passeio que este endpoint evita.

    O HTML do corpo é o que veio no e-mail, então a resposta leva
    `Content-Security-Policy: sandbox` — script de e-mail não roda na aba.
    """
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'unauthorized'}), 401
    from flask import Response, abort
    from html import escape
    client = (request.args.get('client') or '').strip()
    rel = (request.args.get('rel') or '').strip()
    if not client or not rel or not rel.lower().endswith(('.msg', '.eml')):
        return abort(404)
    try:
        full = _R()._ei_locate_file(client, rel)
    except ValueError:
        return abort(400)
    if not full:
        return abort(404)
    # Mesmo teto do /api/parse-msg-html: o parser OLE/CFB não pode receber um
    # arquivo sem limite de tamanho.
    _MAX = 25 * 1024 * 1024
    if os.path.getsize(full) > _MAX:
        return abort(413)
    subject = sender = to = when = ''
    body_html = ''
    try:
        if full.lower().endswith('.msg'):
            import extract_msg
            msg = extract_msg.openMsg(full)
            subject = str(getattr(msg, 'subject', '') or '')
            sender = str(getattr(msg, 'sender', '') or '')
            to = str(getattr(msg, 'to', '') or '')
            when = str(getattr(msg, 'date', '') or '')
            hb = getattr(msg, 'htmlBody', None)
            if hb:
                body_html = hb.decode('utf-8', errors='replace') if isinstance(hb, bytes) else hb
            else:
                body = getattr(msg, 'body', None) or ''
                if isinstance(body, bytes):
                    body = body.decode('utf-8', errors='replace')
                body_html = '<pre style="white-space:pre-wrap">{}</pre>'.format(escape(body))
        else:
            import email as _email
            from email import policy as _policy
            with open(full, 'rb') as fh:
                msg = _email.message_from_binary_file(fh, policy=_policy.default)
            subject = str(msg.get('Subject', '') or '')
            sender = str(msg.get('From', '') or '')
            to = str(msg.get('To', '') or '')
            when = str(msg.get('Date', '') or '')
            part = msg.get_body(preferencelist=('html', 'plain'))
            if part is not None:
                content = part.get_content()
                if part.get_content_type() == 'text/html':
                    body_html = content
                else:
                    body_html = '<pre style="white-space:pre-wrap">{}</pre>'.format(escape(content))
    except Exception:
        _R().log.warning('[manual-conf] email-preview falhou para %s:\n%s', full,
                    traceback.format_exc())
        return jsonify({'success': False,
                        'message': 'Could not read the e-mail file.'}), 500
    cab = ''.join(
        '<div><span style="display:inline-block;min-width:64px;color:#7b8299">{}</span>{}</div>'
        .format(rot, escape(val)) for rot, val in
        (('Subject', subject), ('From', sender), ('To', to), ('Date', when)) if val)
    html = ('<!doctype html><html><head><meta charset="utf-8"></head>'
            '<body style="margin:0;font-family:Segoe UI,Helvetica,Arial,sans-serif">'
            '<div style="padding:10px 14px;border-bottom:1px solid #e3e6ef;'
            'background:#f6f7fb;font-size:12px;line-height:1.5">{}</div>'
            '<div style="padding:12px 14px">{}</div></body></html>').format(cab, body_html)
    resp = Response(html, mimetype='text/html')
    resp.headers['Content-Security-Policy'] = 'sandbox'
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    return resp
