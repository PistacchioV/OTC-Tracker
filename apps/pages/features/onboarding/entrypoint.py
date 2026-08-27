# -*- coding: utf-8 -*-
"""As rotas do Onboarding: as duas páginas, o endereço antigo e as quatro APIs.

Camada FINA de tradução — sessão, validação do PAYLOAD e código de status. As
regras (etapa, encerrado, aging, as filas) são do `cgd_docs`; o que se decide
aqui é o que a validação do corpo recusa e com que número.
"""
from flask import jsonify, redirect, render_template, request, session, url_for

from apps.pages import blueprint
from apps.pages.features.onboarding import commands, queries
from apps.pages.features.onboarding.infra import mappers


def _nao_autenticado():
    return jsonify({'success': False, 'error': 'Not authenticated'}), 401


def _falhou(exc, o_que):
    """A exceção da gravação vira 500 com o motivo, e o traceback vai para o log.

    Ver a nota em `features/support/infra/persistence.py`: o `log` ainda é do
    `routes` e a busca é ATRASADA, para o teste continuar podendo trocá-lo.
    """
    from apps.pages import routes
    routes.log.exception('[onboarding] %s', o_que)
    return jsonify({'success': False, 'error': str(exc)}), 500


@blueprint.route('/cgd')
def cgd_legacy():
    """O endereço antigo do item de menu. A página virou a seção Onboarding, e
    o link que alguém guardou continua chegando em algum lugar."""
    return redirect(url_for('pages_blueprint.onboarding_overview'))


@blueprint.route('/onboarding')
def onboarding_overview():
    return render_template('pages/onboarding-overview.html', segment='onboarding',
                           **mappers.form_context())


@blueprint.route('/onboarding/tracking-docs')
def onboarding_tracking_docs():
    return render_template('pages/onboarding-tracking-docs.html',
                           segment='onboarding-tracking-docs',
                           **mappers.form_context())


@blueprint.route('/api/onboarding/overview')
def api_onboarding_overview():
    if not session.get('authenticated'):
        return _nao_autenticado()
    return jsonify({'success': True, **queries.overview()})


@blueprint.route('/api/onboarding/docs')
def api_onboarding_docs():
    if not session.get('authenticated'):
        return _nao_autenticado()
    return jsonify({'success': True, **queries.docs()})


@blueprint.route('/api/onboarding/docs/save', methods=['POST'])
def api_onboarding_docs_save():
    if not session.get('authenticated'):
        return _nao_autenticado()
    payload = request.get_json(silent=True) or {}
    valores = payload.get('values') or {}
    if not isinstance(valores, dict):
        return jsonify({'success': False, 'error': 'invalid_values'}), 400
    ids = payload.get('ids')
    if isinstance(ids, list) and ids:
        try:
            return jsonify({'success': True,
                            'count': commands.save_many(ids, valores)})
        except Exception as exc:                              # pragma: no cover
            return _falhou(exc, 'falha na gravação em massa')
    rid = str(payload.get('id') or '').strip()
    try:
        rid = commands.save_one(rid, valores) if rid else commands.create(valores)
    except Exception as exc:                                  # pragma: no cover
        return _falhou(exc, 'falha ao gravar a linha')
    return jsonify({'success': True, 'id': rid})


@blueprint.route('/api/onboarding/docs/stamp', methods=['POST'])
def api_onboarding_docs_stamp():
    """Os três carimbos da esteira. O upload do ARQUIVO (taxonomy, abonado) é o
    do Electronic Inventory — o navegador sobe o anexo por lá primeiro e só
    então carimba aqui, na mesma ordem do New Request: o upload é a parte que
    depende do share e é a que falha, e carimbar antes deixaria a etapa fechada
    sem o papel que a fecha."""
    if not session.get('authenticated'):
        return _nao_autenticado()
    payload = request.get_json(silent=True) or {}
    rid = str(payload.get('id') or '').strip()
    acao = str(payload.get('action') or '').strip()
    if not rid:
        return jsonify({'success': False, 'error': 'missing_id'}), 400
    sid = session.get('user_sid') or ''
    try:
        if acao == 'taxonomy':
            return jsonify({'success': True,
                            'stamp': commands.stamp_taxonomy(rid, sid)})
        if acao == 'otc':
            issue = str(payload.get('issue_date') or '').strip()
            assinatura = str(payload.get('signature_date') or '').strip()
            b3 = str(payload.get('b3_id') or '').strip()
            if not issue or not assinatura or not b3:
                return jsonify({'success': False,
                                'error': 'missing_fields'}), 400
            return jsonify({'success': True,
                            'values': commands.stamp_otc(rid, sid, issue,
                                                         assinatura, b3)})
        if acao == 'mo':
            return jsonify({'success': True,
                            'values': commands.stamp_mo(rid, sid)})
    except Exception as exc:                                  # pragma: no cover
        return _falhou(exc, 'falha ao carimbar a etapa (%s)' % acao)
    return jsonify({'success': False, 'error': 'unknown_action'}), 400


@blueprint.route('/api/onboarding/docs/delete', methods=['POST'])
def api_onboarding_docs_delete():
    if not session.get('authenticated'):
        return _nao_autenticado()
    payload = request.get_json(silent=True) or {}
    ids = payload.get('ids')
    if isinstance(ids, list) and ids:
        try:
            return jsonify({'success': True, 'count': commands.delete_many(ids)})
        except Exception as exc:                              # pragma: no cover
            return _falhou(exc, 'falha ao apagar o lote')
    rid = str(payload.get('id') or '').strip()
    if not rid:
        return jsonify({'success': False, 'error': 'missing_id'}), 400
    try:
        commands.delete_one(rid)
    except Exception as exc:                                  # pragma: no cover
        return _falhou(exc, 'falha ao apagar a linha')
    return jsonify({'success': True})
