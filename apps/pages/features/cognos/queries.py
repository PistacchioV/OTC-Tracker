# -*- coding: utf-8 -*-
"""A leitura do arquivo-dia do Cognos (FXO Detail) — as linhas formatadas para
a tela. O STORE por dia é do `routes` (o Save Daily Settlement grava o mesmo
arquivo e o Settlement Advice de Opção lê o PRM de lá).
"""
import os
from datetime import datetime

def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


def _cog_fmt_date(v):
    """FXO Detail dates → dd/mm/yyyy. Most are yyyy-mm-dd; Event Trade Date comes
    as 'jul 2, 2026 12:00:00 AM'. Tolerant of other formats."""
    s = str(v or '').strip()
    if not s:
        return ''
    for fmt in ('%Y-%m-%d', '%Y/%m/%d'):                 # yyyy-mm-dd (date part)
        try:
            return datetime.strptime(s.split(' ')[0], fmt).strftime('%d/%m/%Y')
        except ValueError:
            continue
    for fmt in ('%b %d, %Y %I:%M:%S %p', '%b %d, %Y'):   # 'jul 2, 2026 12:00:00 AM'
        try:
            return datetime.strptime(s, fmt).strftime('%d/%m/%Y')
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
    if os.path.isfile(jp):
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
