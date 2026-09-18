# -*- coding: utf-8 -*-
"""Leituras da recompra de NDF de moeda: as linhas do(s) arquivo(s)-dia, o
finder por Athena ID e a posicao do Live Position que a ponte consulta."""
from datetime import datetime

from apps.pages import data_store as _store
from apps.pages.features.unwinds.infra import persistence


def _R():
    from apps.pages import routes
    return routes


def entries(date_str='', date_from='', date_to=''):
    """As linhas: de UM dia (`date`), de um intervalo, ou de toda a arvore."""
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
        except OSError:
            return []
        out.extend(_R()._day_json(fp, st.st_mtime, st.st_size))
    else:
        dias = list(_R()._day_files(persistence.cache_dir(), persistence.SUFFIX))
        _R()._day_prefetch(dias)
        for fp, _n, mtime, size in dias:
            out.extend(_R()._day_json(fp, mtime, size))
    return [e for e in out if isinstance(e, dict) and persistence.key_of(e)]


def find(athena_id, ref_date=''):
    """(caminho, lista MUTAVEL, indice) da linha — pelo arquivo-dia de
    `ref_date` quando ela vem; senao varre a arvore."""
    alvo = str(athena_id or '').strip().upper()
    if not alvo:
        return None, [], None
    cand = []
    ref = _R()._parse_date_any(ref_date) if ref_date else None
    if ref is not None:
        cand.append(persistence.day_path(datetime(ref.year, ref.month, ref.day)))
    else:
        cand.extend(fp for fp, _n, _m, _s in
                    _R()._day_files(persistence.cache_dir(), persistence.SUFFIX))
    for fp in cand:
        try:
            lst = _store.read(fp)
        except Exception:                                   # noqa: BLE001
            continue
        if not isinstance(lst, list):
            continue
        for i, e in enumerate(lst):
            if isinstance(e, dict) and persistence.key_of(e) == alvo:
                return fp, lst, i
    return None, [], None


def position_rows(ref):
    """As linhas do Live Position de NDF que a ponte do identificador varre,
    como DICIONARIOS coluna -> valor.

    O `_lpndf_collect` devolve cada linha como LISTA posicional alinhada com
    `columns` (e o que a tela consome): quem le por nome tem de casar as duas
    aqui, uma vez. Linha mais curta que o cabecalho completa com vazio em vez
    de deslocar tudo — arquivo de posicao com coluna faltando existe.

    `exact=False` de proposito: o resolvedor anda ate dez dias uteis para tras
    quando falta arquivo (§8), e a recompra de hoje e de um contrato que esta
    na posicao de ontem. Devolve (linhas, data lida em ISO)."""
    dados = _R()._lpndf_collect(ref) or {}
    colunas = list(dados.get('columns') or [])
    linhas = []
    for r in dados.get('rows') or []:
        if isinstance(r, dict):
            linhas.append(r)                    # ja veio por nome
            continue
        r = list(r or [])
        linhas.append({c: (r[i] if i < len(r) else '') for i, c in enumerate(colunas)})
    return linhas, dados.get('source_date') or ''


def template_blocks(key):
    """Os blocos do template do File Interpreter, para o preview campo a
    campo. Template ausente e ValueError — arquivo para a B3 nao sai meio
    montado em silencio (o `_fi_build_line` faz a mesma coisa)."""
    tpl = _R()._fi_tpl_cached(key)
    if tpl is None:
        raise ValueError('file-interpreter template missing: ' + str(key))
    return list(tpl.get('blocks') or [])


def participant_name(le='BANCO'):
    """O Nome Simplificado da entidade dona do arquivo, do cadastro
    `b3-accounts` — a mesma porta do `_ter_file_header`."""
    return _R()._b3_participant_name(le)
