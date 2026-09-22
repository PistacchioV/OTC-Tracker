# -*- coding: utf-8 -*-
"""As rotas de Pending Confirmation.

Só a casca: os três DuckDB e as regras _pc_* são plataforma — meia dúzia de features as consome — o resto fica no routes até a fase platform/, alcançado por _R().
"""
import json
import os
import traceback
from datetime import datetime

from flask import (jsonify, redirect, render_template, request,
                   session, url_for)

from apps.pages import blueprint
from apps.pages import data_store as _store  # noqa: E402


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


@blueprint.route('/api/pending-confirmation/snapshot')
def api_pending_confirmation_snapshot():
    """A FOTO de um dia do Pending Confirmation, no formato {columns, rows}.

    Era o que o Advanced Export consultava para montar um arquivo de vários
    dias; desde 22/09/2026 o intervalo da tela pergunta às COLUNAS de data dos
    três bancos (`/range`, aqui embaixo) e não ao calendário de fotos. Ele fica
    como a única porta para a foto de um dia — é por ela que se responde "como
    estava a fila naquele dia", que o `/range` não responde.

    A tela mostra a situação de AGORA, que é viva: o Aging e o Status são
    recalculados na leitura, e a linha muda de banco quando o prazo vira. A
    série só existe porque a manutenção das 11:30 grava uma foto por dia
    (`cache/pending-confirmation/AAAA/MM/DD`), e é ela que responde aqui.

    Dia sem foto devolve `rows: []` e **200**, não 404: quem pede um intervalo
    manda vinte datas de uma vez, e um dia sem movimento (feriado, ou anterior à
    primeira foto gravada) não é erro — é dia sem linha. As COLUNAS vão em
    qualquer caso, senão o consumidor não teria como montar o cabeçalho de um
    intervalo que começa num feriado.

    A foto é devolvida como está gravada, SEM refiltrar por categoria: ela já é
    o balde `pending` daquele dia, e recomputar responderia pelo calendário de
    hoje — a mesma regra da planilha de métricas com data anterior (§).
    """
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    ds = (request.args.get('date') or '').strip()[:10]
    try:
        ref = datetime.strptime(ds, '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid date'}), 400
    path = os.path.join(_R()._PC_SNAPSHOT_DIR, ref.strftime('%Y'), ref.strftime('%m'),
                        ref.strftime('%d'),
                        'pending-confirmation_{}.json'.format(ref.strftime('%Y%m%d')))
    recs = []
    if _store.isfile(path):
        try:
            from apps.pages import duck_read      # DB-only (fase 3): arquivo-dia payload-LISTA.
            data = duck_read.day_records(path)
            recs = data if isinstance(data, list) else []
        except (json.JSONDecodeError, IOError, OSError):
            _R().log.warning('[pc-snapshot] %s ilegível:\n%s', path, traceback.format_exc())
    rows = [[('' if r.get(c) is None else str(r.get(c, ''))) for c in _R()._PC_COLUMNS]
            for r in recs if isinstance(r, dict)]
    return jsonify({'success': True, 'columns': list(_R()._PC_COLUMNS), 'rows': rows,
                    'date': ref.strftime('%Y-%m-%d'), 'found': _store.isfile(path)})

# As colunas de data que o intervalo do Advanced Export oferece. É LISTA BRANCA
# porque o nome chega do navegador e vai escolher uma coluna do `_PC_COLUMNS`:
# aceitar o que vier deixaria a busca responder por uma coluna que não é data
# (comparando texto com texto, sem erro nenhum e com o arquivo saindo errado).
_PC_RANGE_FIELDS = ('Trade Date', 'Maturity Date')


@blueprint.route('/api/pending-confirmation/range')
def api_pending_confirmation_range():
    """O intervalo de datas do Advanced Export: as linhas dos TRÊS bancos cuja
    coluna escolhida (`Trade Date` ou `Maturity Date`) cai entre `from` e `to`.

    Os três bancos, e não só o `pending`: a linha ANDA entre eles conforme o
    status resolve e o prazo vira (`_pc_target_category`), então um intervalo de
    datas passadas pedido só ao `pending` sairia exatamente sem o que já foi
    confirmado e sem o que tem mais de 12 meses — que é a maior parte do que se
    pede num intervalo.

    É o que substitui, NESTA tela, o intervalo por arquivo-dia do resto do app
    (o `/snapshot` aqui ao lado): a foto das 11:30 responde "como estava a fila
    naquele dia", e o que a mesa pede aqui é "as operações cuja data cai neste
    intervalo", que é uma pergunta às colunas e não ao calendário.

    A leitura é `strict=True` de propósito: a tolerante devolve `[]` quando o
    banco está ocupado ou ilegível (§4), e num EXPORT isso é uma planilha curta
    que ninguém tem como distinguir de um intervalo sem movimento. Levantando,
    o tratador global responde 503 `database_busy` / 500 com o motivo, e a tela
    diz o que houve em vez de baixar um arquivo incompleto.
    """
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    field = (request.args.get('field') or _PC_RANGE_FIELDS[0]).strip()
    if field not in _PC_RANGE_FIELDS:
        return jsonify({'success': False,
                        'message': 'Invalid field: {}'.format(field)}), 400
    ini = _R()._parse_date_any(request.args.get('from') or '')
    fim = _R()._parse_date_any(request.args.get('to') or '')
    # Uma ponta só é o dia dela nas duas pontas — a mesma leitura do intervalo
    # de arquivos-dia, para o campo não querer dizer uma coisa em cada tela.
    ini, fim = (ini or fim), (fim or ini)
    if not ini or not fim:
        return jsonify({'success': False, 'message': 'from/to required'}), 400
    if fim < ini:
        ini, fim = fim, ini

    seen, achadas, sem_data = set(), [], 0
    for cat in ('backlog', 'pending', 'ok'):
        for r in _R()._pc_load_rows(cat, strict=True):
            # A linha pode estar fisicamente em dois bancos até a manutenção
            # das 11:30 reencaminhá-la; sem isto ela sairia duas vezes.
            tn = str(r.get('Trade Number', '') or '').strip()
            if tn:
                if tn in seen:
                    continue
                seen.add(tn)
            d = _R()._parse_date_any(r.get(field, ''))
            if d is None:
                sem_data += 1
                continue
            if ini <= d <= fim:
                achadas.append((d, r))
    # Ordem pela data pedida: o arquivo sai na ordem em que se lê um intervalo.
    achadas.sort(key=lambda p: (p[0], str(p[1].get('Client', '') or ''),
                                str(p[1].get('Trade Number', '') or '')))
    rows = [[('' if r.get(c) is None else str(r.get(c, ''))) for c in _R()._PC_COLUMNS]
            for _d, r in achadas]
    return jsonify({'success': True, 'columns': list(_R()._PC_COLUMNS), 'rows': rows,
                    'field': field, 'undated': sem_data,
                    'from': ini.strftime('%Y-%m-%d'), 'to': fim.strftime('%Y-%m-%d')})


@blueprint.route('/api/pending-confirmation/search', methods=['POST'])
def api_pending_confirmation_search():
    """Return Pending Confirmation rows filtered by the smart-filter chips. A
    Status chip (Pending / Ok / Backlog) narrows the search to that one DB;
    without it, all three DBs are searched. Every other chip filters the rows via
    _deal_matches."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    body = request.get_json(silent=True) or {}
    filters = body.get('filters', []) or []
    has_status = any(_R()._pc_norm(f.get('field', '')) == 'status' for f in filters)
    if has_status:
        # A Status chip means "rows whose CURRENT status is X". Because status is
        # recomputed at read time (e.g. a now-Exception*/OK row may still physically
        # sit in the pending DB until the daily re-route), we can't trust the DB a
        # row lives in — load all three and keep only rows whose recomputed target
        # category matches the requested one. Prevents e.g. Ok rows leaking into a
        # Pending filter.
        want = _R()._pc_category_from_filters(filters)
        seen, rows = set(), []
        for cat in ('backlog', 'pending', 'ok'):
            for r in _R()._pc_load_rows(cat):
                if _R()._pc_target_category(r) != want:
                    continue
                tn = str(r.get('Trade Number', '') or '')
                key = tn or ('#%d' % len(rows))
                if key in seen:
                    continue
                seen.add(key)
                rows.append(r)
        cats = [want]
    else:
        cats = ['backlog', 'pending', 'ok']
        rows = []
        for cat in cats:
            rows += _R()._pc_load_rows(cat)
    # The Status chip only chose the category; apply every OTHER chip to the rows.
    other = [f for f in filters if _R()._pc_norm(f.get('field', '')) != 'status']
    if other:
        rows = [r for r in rows if _R()._deal_matches(r, other)]
    return jsonify({'success': True, 'categories': cats, 'rows': rows,
                    'columns': _R()._PC_COLUMNS})

@blueprint.route('/api/pending-confirmation/upsert', methods=['POST'])
def api_pending_confirmation_upsert():
    """Persist a row edited/confirmed on the page. Refreshes aging/status and
    routes it to the right DB (pending / ok when resolved / backlog past 12
    months), removing any stale copy from the other DBs."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    body = request.get_json(silent=True) or {}
    # `rows` (lote) veio depois do `row` (uma linha) e é o caminho do mass
    # update: um upsert por linha eram 4 aberturas EXCLUSIVAS de banco no
    # share por request, × um request por linha — o lote faz tudo em três.
    srcs = body.get('rows')
    if srcs is None:
        srcs = [body.get('row') or {}]
    if not isinstance(srcs, list) or not srcs:
        return jsonify({'success': False, 'message': 'rows must be a list'}), 400
    rows = []
    for src in srcs:
        if not isinstance(src, dict) or \
                not str(src.get('Trade Number', '') or '').strip():
            return jsonify({'success': False, 'message': 'Trade Number required'}), 400
        rows.append({c: str(src.get(c, '') or '') for c in _R()._PC_COLUMNS})
    targets = _R()._pc_upsert_rows(rows)
    return jsonify({'success': True, 'category': targets[0], 'categories': targets})

@blueprint.route('/api/pending-confirmation/derive', methods=['POST'])
def api_pending_confirmation_derive():
    """Recalcula as colunas derivadas de várias linhas de uma vez — é o que a
    atualização em massa chama depois de aplicar o valor na coluna escolhida.

    Uma chamada para o lote inteiro: o Reference Data é lido uma vez por
    requisição, e linha a linha seriam N leituras e N idas ao servidor."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    rows = (request.get_json(silent=True) or {}).get('rows') or []
    if not isinstance(rows, list):
        return jsonify({'success': False, 'message': 'rows must be a list'}), 400
    return jsonify({'success': True,
                    'rows': [_R()._pc_derive_row(r if isinstance(r, dict) else {}) for r in rows]})

@blueprint.route('/api/pending-confirmation/delete', methods=['POST'])
def api_pending_confirmation_delete():
    """Delete a row (by Trade Number) from all three DBs."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    tn = str((request.get_json(silent=True) or {}).get('trade_number', '') or '').strip()
    if not tn:
        return jsonify({'success': False, 'message': 'Trade Number required'}), 400
    for cat in ('backlog', 'pending', 'ok'):
        _R()._pc_delete_tn(cat, tn)
    return jsonify({'success': True})

@blueprint.route('/api/pending-confirmation/import-update', methods=['POST'])
def api_pending_confirmation_import_update():
    """Bulk-upsert operations from an uploaded 'Pending Update' xlsx."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'success': False, 'message': 'No file uploaded.'}), 400
    if not f.filename.lower().endswith('.xlsx'):
        return jsonify({'success': False, 'message': 'Please upload a .xlsx file.'}), 400
    try:
        res = _R()._pc_import_update(f.read())
    except Exception:
        _R().log.error('[pending-confirmation] update import failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'message': 'Failed to process the spreadsheet.'}), 500
    return jsonify({'success': True, 'updated': res['updated'], 'skipped': res['skipped']})

@blueprint.route('/metrics-pending-confirmation')
def metrics_pending_confirmation():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/metrics-pending-confirmation.html',
                           segment='metrics-pending-confirmation')

@blueprint.route('/api/metrics-pending-confirmation/offenders')
def api_pc_metrics_offenders():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    # Always read the live pending DuckDB (not the daily snapshot) so edits on the
    # Pending Confirmation page reflect on the dashboard immediately; snapshots
    # remain history-only (see /history).
    rows = [r for r in _R()._pc_load_rows('pending')
            if not _R()._pc_is_ok_status(r.get('Pending Status', ''))]
    return jsonify({'success': True, 'source': 'live', **_R()._pc_metrics_offenders(rows)})

@blueprint.route('/api/metrics-pending-confirmation/history')
def api_pc_metrics_history():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    return jsonify({'success': True, **_R()._pc_metrics_history()})
