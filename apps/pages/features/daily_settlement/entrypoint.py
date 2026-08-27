# -*- coding: utf-8 -*-
"""As rotas de Save Daily Settlement Files (card do Control Panel).

Só a casca: o `_ds_handle` e os stores por dia são plataforma — cinco telas leem o que ele grava.
"""

from flask import jsonify, request, session



def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


@_R().blueprint.route('/api/control-panel/daily-settlement-save', methods=['POST'])
def api_cp_daily_settlement_save():
    """Control Panel — "Save Daily Settlement Files". Source files come from the
    card's dropzone (multipart 'files'); if none were attached, fall back to
    scanning SETTLEMENTS_ROOT. Each recognised file is read (tab-delimited),
    filtered per the VBA ImportarTexto rules and written to a per-type JSON under
    the daily-settlement cache (today's date). Folder sources are deleted after
    processing (mirrors the VBA Kill). OTM cashflows are handled on their own
    page and are ignored here. No file anywhere → error (UI warns the user)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401

    ref = _R().datetime.now()
    uploaded = [f for f in request.files.getlist('files') if f and f.filename]
    processed, skipped = [], []
    source = 'dropzone'

    if uploaded:
        for f in uploaded:
            _R()._ds_handle(f.filename, f.read(), None, ref, processed, skipped)
    else:
        source = 'folder'
        folder_files = []
        if _R().os.path.isdir(_R().SETTLEMENTS_ROOT):
            try:
                folder_files = [f for f in _R().os.listdir(_R().SETTLEMENTS_ROOT)
                                if _R().os.path.isfile(_R().os.path.join(_R().SETTLEMENTS_ROOT, f))]
            except OSError:
                folder_files = []
        if not folder_files:
            return jsonify({'success': False,
                            'error': ('Nenhum arquivo encontrado para processamento — o dropzone está '
                                      'vazio e não há arquivos em {}.'.format(_R().SETTLEMENTS_ROOT))}), 400
        # Latam Desk Position: a pasta pode ter mais de um relatório (ele é
        # reemitido no mesmo dia), e processar os dois deixaria o vencedor por
        # conta da ordem do `os.listdir` — o JSON do dia sairia com a posição da
        # manhã em uma máquina e com a da tarde em outra. Vale o MAIS RECENTE, o
        # mesmo que o botão Import da página lê (`_latam_pick_source`); os demais
        # ficam em disco, não processados, e vão para o log.
        _lt_pick, _lt_old = _R()._latam_pick_source(folder_files, _R().SETTLEMENTS_ROOT)
        if _lt_old:
            folder_files = [f for f in folder_files if f not in set(_lt_old)]
        folder_files.sort()                            # ordem estável para os demais tipos
        for name in folder_files:
            p = _R().os.path.join(_R().SETTLEMENTS_ROOT, name)
            try:
                with open(p, 'rb') as fh:
                    raw = fh.read()
            except OSError:
                skipped.append(name)
                continue
            _R()._ds_handle(name, raw, p, ref, processed, skipped)

    if processed:
        types = ', '.join(p['type'] for p in processed)
        _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                             'Daily Settlement Saved', 'Control Panel',
                             '{} file(s) processed: {} ({})'.format(len(processed), types, ref.strftime('%Y-%m-%d')))

    # The user-facing message is built client-side from the structured fields
    # below so it follows the UI language; this English string is only a fallback.
    lines = ['<b>{}</b>: {} of {} line(s)'.format(p['type'], p['kept'], p['total']) for p in processed]
    msg = ''
    if lines:
        msg += '{} file(s) processed via {}:<br>'.format(len(processed),
               'dropzone' if source == 'dropzone' else 'folder') + '<br>'.join(lines)
    if skipped:
        msg += ('<br><br>' if msg else '') + \
            '<span class="text-muted">{} ignored (unrecognized): {}</span>'.format(
                len(skipped), ', '.join(skipped[:8]) + ('…' if len(skipped) > 8 else ''))
    return jsonify({'success': True, 'source': source, 'processed': processed,
                    'skipped': skipped, 'message': msg or 'Nothing to process.'})
