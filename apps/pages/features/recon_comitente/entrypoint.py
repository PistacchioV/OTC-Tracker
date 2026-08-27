# -*- coding: utf-8 -*-
"""As três rotas da Recon de Comitentes."""
from flask import jsonify, redirect, render_template, request, session, url_for

from apps.pages import blueprint
# Import no TOPO, e não preguiçoso: as exceções são capturadas em `except`
# das rotas, e um nome resolvido só na primeira chamada faria o `except`
# referenciar algo que ainda não existe.
from apps.pages.database_access import (
    DatabaseCleanupError,
    DatabaseLockTimeout,
    TransactionOutcomeUnknown,
    verify_sqlite_integrity,
)
from apps.pages.features.recon_comitente import commands, queries


def _routes():
    from apps.pages import routes
    return routes


@blueprint.route('/reconciliation-comitente')
def reconciliation_comitente():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/reconciliation-comitente.html',
                           segment='reconciliation-comitente')


@blueprint.route('/reconciliation-comitente/data')
def reconciliation_comitente_data():
    R = _routes()
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        return jsonify(queries.data())
    except DatabaseLockTimeout:
        # 503 e `retryable`, não 500: o banco está OCUPADO, não quebrado. A tela
        # pode tentar de novo sozinha, e um 500 a faria desistir e mostrar erro.
        return jsonify({
            'error': 'O banco de reconciliação está ocupado. Tente novamente em instantes.',
            'retryable': True,
        }), 503
    except DatabaseCleanupError:
        R.log.exception('[recon_comitente_data] falha ao liberar recursos do banco')
        return jsonify({'error': 'Falha ao finalizar o acesso ao banco de reconciliação.'}), 500
    except Exception:                                       # noqa: BLE001
        R.log.exception('[recon_comitente_data] falha ao carregar dados')
        return jsonify({'error': 'Não foi possível carregar os dados de reconciliação.'}), 500


@blueprint.route('/reconciliation-comitente/run', methods=['POST'])
def reconciliation_comitente_run():
    R = _routes()
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401

    mode = request.form.get('mode', 'auto')
    recon_date = request.form.get('recon_date', '')

    try:
        files = None
        if mode != 'auto':
            f_b3_cgd = request.files.get('file_b3_cgd')
            f_dcad = request.files.get('file_dcad')
            f_party = request.files.get('file_party')
            if not f_b3_cgd or not f_dcad or not f_party:
                return jsonify({'error': 'Os 3 arquivos são obrigatórios no modo manual.'}), 400
            files = (f_b3_cgd, f_dcad, f_party)
        result = commands.run(mode, recon_date, files)
        counts = result.get('counts', {})
        if counts.get('total', 0) > 0:
            R._create_notification(
                session.get('user_sid', ''),
                session.get('user_name', ''),
                'Recon Generated',
                'Recon Comitente',
                f"{counts.get('total', 0)} records — OK:{counts.get('ok', 0)} "
                f"Check:{counts.get('check', 0)} Amend:{counts.get('amend', 0)} ({recon_date})"
            )
        return jsonify(result)
    except FileNotFoundError as e:
        R.log.warning('[reconciliation_comitente_run] arquivo não encontrado: %s', e)
        return jsonify({'not_found': True, 'missing': getattr(e, 'missing', None), 'detail': str(e)})
    except DatabaseLockTimeout:
        # Ocupado, não quebrado: 503 + `retryable` para a tela poder tentar de
        # novo. Com 500 ela desiste e o operador reexecuta a rotina inteira.
        return jsonify({
            'error': 'O banco de reconciliação está ocupado. Tente novamente em instantes.',
            'retryable': True,
        }), 503
    except TransactionOutcomeUnknown as e:
        # O pior desfecho: a gravação PODE ter acontecido. Reexecutar às cegas
        # duplicaria a reconciliação do dia; não reexecutar pode deixá-la pela
        # metade. A resposta não escolhe por quem opera — ela diz que o
        # resultado é DESCONHECIDO e devolve o `operation_id` para a conferência.
        from apps.pages.recon_comitente import DB_PATH

        try:
            integrity_ok = verify_sqlite_integrity(DB_PATH)
        except Exception:                                   # noqa: BLE001
            # A própria verificação falhar é informação, não motivo de queda:
            # `False` diz "não deu para confirmar", que é o que o operador tem
            # de saber antes de decidir.
            R.log.exception('[reconciliation_comitente_run] verificação de integridade falhou')
            integrity_ok = False
        R.log.error(
            '[reconciliation_comitente_run] resultado da gravação é desconhecido '
            'operation_id=%s integrity_ok=%s',
            e.operation_id,
            integrity_ok,
        )
        return jsonify({
            'error': 'O resultado da gravação não pôde ser confirmado. '
                     'Não execute novamente antes da verificação operacional.',
            'outcome_unknown': True,
            'operation_id': e.operation_id,
            'integrity_ok': integrity_ok,
        }), 500
    except DatabaseCleanupError:
        # A reconciliação TERMINOU; o que falhou foi soltar o recurso depois.
        # A mensagem separa as duas coisas, senão o operador refaz um trabalho
        # que já está feito.
        R.log.exception('[reconciliation_comitente_run] falha ao liberar recursos do banco')
        return jsonify({'error': 'A reconciliação foi concluída, mas houve falha ao '
                                 'finalizar o acesso ao banco.'}), 500
    except Exception:                                       # noqa: BLE001
        R.log.exception('[reconciliation_comitente_run] falha na reconciliação')
        return jsonify({'error': 'Não foi possível concluir a reconciliação.'}), 500
