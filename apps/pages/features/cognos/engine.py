# -*- coding: utf-8 -*-
"""Cognos (FXO Detail) — o import e a coleta da tela.

O STORE por dia (`_cog_json_path/_cog_load/_cog_save/_cog_find/_cog_read_rows/
_cog_extract` e as colunas `_COG_*`) ficou no routes: o Save Daily Settlement
grava o mesmo arquivo e o Settlement Advice de Opção lê o PRM de lá.
"""
import os
import traceback
from datetime import datetime


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


def _cog_import(ref=None):
    """Find "FXO Detail*.xlsx" in COG_SOURCE_ROOT, extract, write today's JSON."""
    ref = ref or _R().datetime.now()
    if not _R().os.path.isdir(_R().COG_SOURCE_ROOT):
        return {'success': False, 'error': 'Source folder not found: {}'.format(_R().COG_SOURCE_ROOT)}
    matches = sorted(f for f in _R().os.listdir(_R().COG_SOURCE_ROOT)
                     if f.lower().startswith('fxo detail') and f.lower().endswith(('.xlsx', '.xls', '.txt')))
    if not matches:
        return {'success': False, 'error': 'No "FXO Detail*" file found in {}'.format(_R().COG_SOURCE_ROOT)}
    src_path = _R().os.path.join(_R().COG_SOURCE_ROOT, matches[0])
    try:
        rows = _R()._cog_read_rows(src_path)
    except Exception:
        _R().log.warning("[cognos] read failed for %s:\n%s", src_path, _R().traceback.format_exc())
        return {'success': False, 'error': 'Could not read {}'.format(matches[0])}
    out, kept = _R()._cog_extract(rows)
    jp = _R()._cog_json_path(ref)
    _R()._cog_save(jp, out)
    _R()._ds_write_updated(jp, ref.strftime('%H:%M:%S'))
    try:
        _R().os.remove(src_path)
    except OSError:
        _R().log.warning("[cognos] could not delete source %s", src_path)
    _R().log.info("[cognos] imported %s: kept %d → %s", matches[0], kept, jp)
    return {'success': True, 'file': matches[0], 'rows': kept, 'date': ref.strftime('%Y-%m-%d')}

def _cog_fmt_date(v):
    """FXO Detail dates → dd/mm/yyyy. Most are yyyy-mm-dd; Event Trade Date comes
    as 'jul 2, 2026 12:00:00 AM'. Tolerant of other formats."""
    s = str(v or '').strip()
    if not s:
        return ''
    for fmt in ('%Y-%m-%d', '%Y/%m/%d'):                 # yyyy-mm-dd (date part)
        try:
            return _R().datetime.strptime(s.split(' ')[0], fmt).strftime('%d/%m/%Y')
        except ValueError:
            continue
    for fmt in ('%b %d, %Y %I:%M:%S %p', '%b %d, %Y'):   # 'jul 2, 2026 12:00:00 AM'
        try:
            return _R().datetime.strptime(s, fmt).strftime('%d/%m/%Y')
        except ValueError:
            continue
    d = _R()._fcst_parse_date(s)
    return d.strftime('%d/%m/%Y') if d else s

def _cog_collect(ref):
    """Read the Cognos JSON for `ref` → display rows + widgets (Call/Put/Total).
    Date columns formatted dd/mm/yyyy."""
    widgets = {'total': 0, 'call': 0, 'put': 0}
    jp = _R()._cog_json_path(ref)
    rows_out = []
    if _R().os.path.isfile(jp):
        try:
            with open(jp, encoding='utf-8') as fh:
                data = _R().json.load(fh) or []
        except Exception:
            data = []
        if _R()._cog_ensure_meta(data) and data:
            try:
                _R()._cog_save(jp, data)
            except Exception:
                pass
        # Counterparty Name pelo **SPN**, não pelo texto do arquivo. O Cognos traz
        # o nome como a Athena o escreve (abreviado, ora com sufixo de entidade,
        # ora sem) enquanto o SPN ao lado é um identificador — e `_otm_cpty_name`
        # é a resposta que o app já dá para essa pergunta: cadastro `le-spn`
        # quando é entidade nossa, Reference Data quando é cliente. Resolver aqui
        # e não na importação faz a correção do cadastro valer na hora, sem
        # reimportar o dia (mesma regra do OTM Settlements). Sem SPN, ou sem
        # cadastro, o nome do arquivo fica: a linha não pode sair anônima.
        #
        # O cache local existe porque `_otm_cpty_name` varre a lista do `le-spn`
        # a cada chamada, e o Cognos costuma repetir a mesma contraparte em
        # dezenas de linhas.
        _name_cache = {}

        def cpty_name(rec):
            spn = str(rec.get('Counterparty SPN', '') or '').strip()
            fallback = str(rec.get('Counterparty Name', '') or '').strip()
            if not spn:
                return fallback
            if spn not in _name_cache:
                _name_cache[spn] = _R()._otm_cpty_name(spn)
            return _name_cache[spn] or fallback

        # Display sorted A→Z pelo nome JÁ RESOLVIDO (case-insensitive; blanks
        # last) — ordenar pelo texto do arquivo deixaria a tela fora de ordem.
        pairs = sorted(((rec, cpty_name(rec)) for rec in data),
                       key=lambda t: (t[1].strip() == '', t[1].strip().lower()))
        for rec, cpname in pairs:
            row = []
            for c in _R()._COG_COLUMNS:
                v = cpname if c == 'Counterparty Name' else rec.get(c, '')
                if c in _R()._COG_DATE_COLS:
                    v = _cog_fmt_date(v)
                row.append('' if v is None else v)
            row += [rec.get('_cg_status', 'OK'), rec.get('_cg_maker', ''),
                    rec.get('_cg_checker', ''), rec.get('_cg_id', '')]
            rows_out.append(row)
            cp = str(rec.get('Call Put Indicator', '') or '').upper()
            if 'CALL' in cp:
                widgets['call'] += 1
            elif 'PUT' in cp:
                widgets['put'] += 1
        widgets['total'] = len(data)
    return {'widgets': widgets, 'columns': _R()._COG_COLUMNS, 'rows': rows_out,
            'value_columns': sorted(_R()._COG_VALUE_COLS),
            'updated': _R()._ds_read_updated(jp)}

def _cog_ref_from(payload):
    ds = str((payload or {}).get('date', '') or '').strip()
    try:
        return _R().datetime.strptime(ds[:10], '%Y-%m-%d') if ds else _R().datetime.now()
    except ValueError:
        return _R().datetime.now()
