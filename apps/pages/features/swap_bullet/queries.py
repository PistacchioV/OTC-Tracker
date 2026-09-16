# -*- coding: utf-8 -*-
"""Leituras do Swap Bullet: os deals do(s) arquivo(s)-dia, o finder por Deal,
e os cadastros que o gerador consulta (contas B3, códigos, Reference Data)."""
import os
import re
from datetime import datetime

from apps.pages import data_store as _store
from apps.pages.features.swap_bullet.infra import persistence


def _R():
    from apps.pages import routes
    return routes


def entries(date_str='', date_from='', date_to=''):
    """Os deals: de UM dia (`date`), de um intervalo, ou de toda a árvore."""
    out = []
    if date_from or date_to:
        d_from = _R()._parse_date_any(date_from)
        d_to = _R()._parse_date_any(date_to)
        dias = list(_R()._day_files(persistence.cache_dir(), persistence.SUFFIX, d_from, d_to))
        _R()._day_prefetch(dias)
        for fp, fname, mtime, size in dias:
            fdate = _R()._parse_date_any(fname[:8])
            if fdate is None or (d_from and fdate < d_from) or (d_to and fdate > d_to):
                continue
            out.extend(_R()._day_json(fp, mtime, size))
    elif date_str:
        ref = _R()._parse_date_any(date_str)
        if ref is None:
            return []
        fp = persistence.day_path(datetime(ref.year, ref.month, ref.day))
        try:
            st = _store.stat(fp)
            mtime, size = st.st_mtime, st.st_size
        except OSError:
            return []
        out.extend(_R()._day_json(fp, mtime, size))
    else:
        dias = list(_R()._day_files(persistence.cache_dir(), persistence.SUFFIX))
        _R()._day_prefetch(dias)
        for fp, _fname, mtime, size in dias:
            out.extend(_R()._day_json(fp, mtime, size))
    return [persistence.migrate(dict(e)) for e in out if isinstance(e, dict) and persistence.key_of(e)]


def find(deal_id, trade_date=''):
    """(caminho, lista MUTÁVEL, índice) do deal — pelo arquivo-dia da Trade
    Date quando ela vem; senão varre a árvore. (None, [], None) se não há."""
    deal_id = str(deal_id or '').strip()
    if not deal_id:
        return None, [], None
    cand = []
    ref = _R()._parse_date_any(trade_date) if trade_date else None
    if ref is not None:
        cand.append(persistence.day_path(datetime(ref.year, ref.month, ref.day)))
    else:
        cand.extend(fp for fp, _n, _m, _s in _R()._day_files(persistence.cache_dir(), persistence.SUFFIX))
    for fp in cand:
        try:
            lst = _store.read(fp)
        except FileNotFoundError:
            continue
        except _store.BancoOcupado:
            raise
        except Exception:                                   # noqa: BLE001
            continue
        if not isinstance(lst, list):
            continue
        for i, e in enumerate(lst):
            if isinstance(e, dict) and persistence.key_of(e) == deal_id:
                for x in lst:
                    persistence.migrate(x)      # a lista volta para ser gravada: migra junto
                return fp, lst, i
    if ref is not None:
        return find(deal_id, '')
    return None, [], None


# ── Cadastros ────────────────────────────────────────────────────────────────

def own_accounts():
    """{LE: conta PRÓPRIA só dígitos} do `b3-accounts` — 'JPM': '73760009'."""
    out = {}
    for row in _R()._mapping_rows('b3-accounts'):
        le = str(row.get('LE', '') or '').strip().upper()
        if not le or _R()._b3_account_type(row.get('ACCOUNT TYPE', '')) != 'OWN':
            continue
        acc = re.sub(r'\D', '', str(row.get('ACCOUNT', '') or ''))
        if acc and le not in out:
            out[le] = acc
    return out


def omnibus_account(le='JPM', kind='CLIENT 2'):
    """A conta guarda-chuva de clientes da LE (o omnibus)."""
    for row in _R()._mapping_rows('b3-accounts'):
        if str(row.get('LE', '') or '').strip().upper() != le:
            continue
        if _R()._b3_account_type(row.get('ACCOUNT TYPE', '')) == kind:
            return re.sub(r'\D', '', str(row.get('ACCOUNT', '') or ''))
    return ''


def refdata_by_spn(spn):
    """O registro do Reference Data da SPN (ou {})."""
    key = _R()._spn_key(spn)
    if not key:
        return {}
    for rec in _R()._refdata_records():
        if _R()._spn_key(rec.get('SPN', '')) == key:
            return rec
    return {}


def codes_for(deal):
    """Os códigos B3 dos campos cadastráveis do deal, pelos de-para do
    /mapping. Vazio = lacuna (o preview mostra, o Send recusa)."""
    from apps.pages.features.swap_bullet import domain
    func_rows = _R()._mapping_rows('swap-funcionalidade')
    code_rows = _R()._mapping_rows('swap-code-labels')
    curve_rows = _R()._mapping_rows('swap-bullet-curve')
    func_txt = str(deal.get('Functionality') or '').strip()
    if domain.norm(func_txt) in ('', 'NA', 'N', 'NAO', 'NENHUMA', 'NONE', 'SEM'):
        func_txt = 'SEM FUNCIONALIDADE'
    codes = {
        'functionality': domain.code_by_label(func_rows, func_txt),
        'adhesion': domain.code_by_label(code_rows, deal.get('Adhesion', ''), field='Adesão'),
        'premium_schedule': domain.code_by_label(code_rows, deal.get('PremiumSchedule', ''), field='Sim/Não'),
        'reset': domain.code_by_label(code_rows, deal.get('Reset', ''), field='Sim/Não'),
        'signA': domain.code_by_label(code_rows, deal.get('CurveASign', '+'), field='Sinal Taxa'),
        'signB': domain.code_by_label(code_rows, deal.get('CurveBSign', '+'), field='Sinal Taxa'),
        'curveA': domain.curve_code(curve_rows, deal.get('CurveA', ''), deal.get('CurveACategory', '')),
        'curveB': domain.curve_code(curve_rows, deal.get('CurveB', ''), deal.get('CurveBCategory', '')),
    }
    return codes


def template_blocks(key):
    """Os blocos do template do File Interpreter (lista) — [] sem template."""
    tpl = _R()._fi_tpl_cached(key)
    return list((tpl or {}).get('blocks') or [])
