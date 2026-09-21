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


def dashboard_counts(period, now):
    """Quantas recompras o painel mostra:
    `{'total': n, 'monthly': [12], 'products': [{label, total, monthly}]}`.

    Varre `cache/unwinds/` INTEIRA — o card do painel e de recompra, nao de
    recompra de NDF de moeda: os produtos que vierem depois entram sozinhos,
    como entram os de New Deals.

    Reusa o `_dash_scan_files` e o `_dash_dir_matters` do painel para a poda
    de periodo ser a MESMA das outras contagens; uma poda propria aqui
    significaria o card de recompra respondendo a um 'este mes' diferente do
    dos outros quatro, sem nada na tela dizendo isso.

    A regra da LINHA e mais simples que a de New Deals de proposito: uma
    recompra e UMA linha. Nao ha perna espelhada a descartar (o `_is_bank` de
    la existe porque o deal intragrupo e gravado das duas visoes), entao aqui
    conta-se toda linha com Athena ID.
    """
    import os
    from datetime import datetime

    from apps.pages.features.unwinds.infra import persistence

    total, monthly = 0, [0] * 12
    # A QUEBRA por produto (a mesa pediu 'Unwind NDF FX', não um 'Unwinds'
    # genérico): o rótulo sai dos dois primeiros níveis do caminho, que é a
    # mesma leitura que o New Deals Monitor faz da árvore (§454). Recompra de
    # outro produto entra sozinha, sem cadastro nenhum.
    por_produto = {}
    raiz = os.path.normpath(persistence.cache_root())
    if not _store.isdir(raiz):
        return {'total': total, 'monthly': monthly, 'products': []}
    # UMA passada SEM poda ('all'), e o periodo aplicado no laco. O painel faz
    # duas passadas porque as duas compartilham o memo de arquivo-dia; aqui a
    # arvore e pequena, e varrer por 'year' perderia os anos anteriores no
    # periodo 'all' — a serie mensal e sempre do ano corrente, o total nao.
    for fp, fname, _mtime, _size in _R()._dash_scan_files(raiz, 'all', now):
        if fname.endswith('.tmp') or fname.endswith('.bak'):
            continue
        try:
            fdate = datetime.strptime(fname[:8], '%Y%m%d')
        except ValueError:
            continue
        try:
            linhas = _store.read(fp)
        except Exception:                                   # noqa: BLE001
            continue
        # A recompra da Fase 1 se identifica pelo Athena ID; as do catálogo, pelo
        # `_id` interno (FXO e NDF/Opção de Commodities chegam sem id nenhum) —
        # contar só o Athena ID as deixaria invisíveis no painel (§489).
        n = sum(1 for e in (linhas if isinstance(linhas, list) else [])
                if isinstance(e, dict) and (str(e.get('AthenaID') or '').strip()
                                            or str(e.get('_id') or '').strip()))
        if not n:
            continue
        rotulo = _rotulo_do_caminho(raiz, fp)
        p = por_produto.setdefault(rotulo, {'label': rotulo, 'total': 0, 'monthly': [0] * 12})
        if fdate.year == now.year:
            monthly[fdate.month - 1] += n
            p['monthly'][fdate.month - 1] += n
        no_periodo = (period == 'month' and fdate.year == now.year and fdate.month == now.month) \
            or (period == 'year' and fdate.year == now.year) \
            or period not in ('month', 'year')
        if no_periodo:
            total += n
            p['total'] += n
    return {'total': total, 'monthly': monthly,
            'products': sorted(por_produto.values(), key=lambda x: x['label'])}


def _rotulo_do_caminho(raiz, fp):
    """'…/unwinds/NDF/FX/2026/09/…json' -> 'Unwind NDF FX'.

    Os dois primeiros níveis não numéricos, como o Monitor lê a árvore. Sem
    nível nenhum (arquivo direto na raiz) o rótulo é só 'Unwind', que ainda diz
    o que a barra é."""
    import os as _os
    rel = _os.path.relpath(fp, raiz).replace('\\', '/').split('/')
    niveis = [p for p in rel[:-1] if not p.isdigit()][:2]
    return ' '.join(['Unwind'] + niveis)


# ── O Termo de Resilição ─────────────────────────────────────────────────────

def _acr_da_linha(linha):
    """Como a recompra se chama no agrupamento: o accronym do e-mail quando ele
    veio, senão o nome da contraparte da posição. É o mesmo valor que a grade
    mostra, e é o que vai na URL do documento."""
    return (str((linha or {}).get('ClientAcronym') or '').strip()
            or str((linha or {}).get('Counterparty') or '').strip())


def termo_grupo(ref, acr='', moeda=''):
    """As recompras de UMA contraparte (× moeda) na data — as linhas do Anexo I
    do Termo de Resilição, na ordem em que a grade as mostra.

    O eixo é o MESMO em toda parte (§457): contraparte × moeda. Duas recompras
    da mesma contraparte em moedas diferentes são dois termos, porque o Valor
    Base Liquidado de cada linha está na moeda do contrato — misturá-las num
    documento só faria a mesa somar laranja com maçã.

    Linha já resilida NÃO é filtrada aqui: reabrir o documento de um termo já
    salvo é o caminho normal de corrigir um campo e salvar de novo."""
    alvo = str(acr or '').strip().upper()
    m = str(moeda or '').strip().upper()
    out = []
    for e in entries(date_str=str(ref or '')):
        if alvo and alvo not in (_acr_da_linha(e).upper(),
                                 str(e.get('Counterparty') or '').strip().upper()):
            continue
        if m and str(e.get('Currency') or '').strip().upper() != m:
            continue
        out.append(e)
    return out


def spn_por_taxid(taxid):
    """O SPN do Reference Data pelo CPF/CNPJ da contraparte — a chave que o
    `_conf_cgd_lookup` usa para achar o CGD.

    A recompra não traz SPN: a posição entrega nome e documento (§488), e é
    pelo documento que se chega ao cadastro. Sem casar, devolve '' e quem chama
    avisa — o CGD em branco no documento é campo a preencher, nunca uma data
    inventada."""
    import re
    d = re.sub(r'\D', '', str(taxid or ''))
    if not d:
        return ''
    for rec in _R()._refdata_triples():
        if re.sub(r'\D', '', str(rec.get('taxid') or '')) == d:
            return str(rec.get('spn') or '').strip()
    return ''
