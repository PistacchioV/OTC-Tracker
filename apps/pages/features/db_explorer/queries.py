# -*- coding: utf-8 -*-
"""As leituras do Database Explorer: os bancos da pasta, as tabelas de um
banco e as linhas de uma tabela. Toda abertura passa pela camada
`database_access` (lock compartilhado + semáforo, §4), nunca `duckdb.connect`."""
import os
import threading
import time

import duckdb

from apps.pages import database_access
from apps.pages.features.db_explorer import domain

# A lista de bancos é uma varredura da pasta — no share, uma ida à rede por
# diretório. Memória de processo curta: abrir o combo de novo não refaz a
# varredura; o Refresh da tela pede `fresh`.
_LIST_TTL = 60.0
_list_memo = {}
_list_lock = threading.Lock()


def _R():
    """Busca ATRASADA no routes (o `Config` é superfície de teste)."""
    from apps.pages import routes
    return routes


def root():
    return os.path.normpath(os.path.abspath(_R().Config.DATABASE_DIR))


def _varre(raiz):
    out = []
    pilha = ['']
    while pilha:
        rel_dir = pilha.pop()
        try:
            entradas = list(os.scandir(os.path.join(raiz, rel_dir) if rel_dir else raiz))
        except OSError:
            continue
        for e in entradas:
            rel = (rel_dir + '/' + e.name) if rel_dir else e.name
            try:
                if e.is_dir(follow_symlinks=False):
                    if e.name not in domain.SKIP_DIRS and e.name != '__pycache__':
                        pilha.append(rel)
                    continue
                if not e.name.lower().endswith(domain.DB_EXTS) or not e.is_file(follow_symlinks=False):
                    continue
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            out.append({'path': rel, 'name': e.name, 'folder': rel_dir,
                        'size': st.st_size, 'mtime': st.st_mtime})
    # a raiz primeiro (os bancos de plataforma), depois cada pasta em ordem
    out.sort(key=lambda d: (d['folder'] != '', d['folder'].lower(), d['name'].lower()))
    return out


def databases(fresh=False):
    raiz = root()
    agora = time.monotonic()
    with _list_lock:
        hit = _list_memo.get(raiz)
        if hit and not fresh and agora - hit[0] < _LIST_TTL:
            return hit[1]
    lista = _varre(raiz)
    with _list_lock:
        _list_memo[raiz] = (time.monotonic(), lista)
    return lista


def db_path(rel):
    """O caminho absoluto de um banco que EXISTE e É DuckDB (a marca do
    cabeçalho) — o SQLite de comitentes, uma cópia truncada ou um arquivo
    qualquer com `.db` no nome param aqui, com o motivo."""
    alvo = domain.resolve_db(root(), rel)
    if not os.path.isfile(alvo):
        raise domain.ExplorerError('db_not_found', 'Database not found: %s' % rel, 404, db=rel)
    try:
        with open(alvo, 'rb') as fh:
            cab = fh.read(12)
    except OSError as e:
        raise domain.ExplorerError('db_error', '%s: %s' % (type(e).__name__, e), 500, msg=str(e))
    if cab[8:12] != domain.DUCK_MAGIC:
        raise domain.ExplorerError('not_duckdb', 'Not a DuckDB database: %s' % rel, 400, db=rel)
    return alvo


def as_explorer_error(exc):
    """A exceção do banco como erro com código: arquivo preso pela instância
    vizinha é 503 (`db_busy`), valor que o CAST recusa e restrição violada são
    400 com a frase do DuckDB, o resto 500 com o motivo (§476)."""
    if isinstance(exc, domain.ExplorerError):
        return exc
    if database_access.is_file_in_use(exc) or isinstance(exc, database_access.DatabaseAccessError):
        return domain.ExplorerError('db_busy', 'Database in use: %s' % exc, 503, msg=str(exc))
    if isinstance(exc, (duckdb.ConversionException, duckdb.InvalidInputException)):
        return domain.ExplorerError('bad_value', str(exc), 400, msg=str(exc))
    if isinstance(exc, duckdb.ConstraintException):
        return domain.ExplorerError('constraint', str(exc), 400, msg=str(exc))
    return domain.ExplorerError('db_error', '%s: %s' % (type(exc).__name__, exc), 500,
                                msg='%s: %s' % (type(exc).__name__, exc))


def _ler(path, fn):
    try:
        with database_access.duckdb_read(path) as con:
            return fn(con)
    except domain.ExplorerError:
        raise
    except (duckdb.Error, database_access.DatabaseAccessError, OSError) as e:
        raise as_explorer_error(e)


# ── catálogo ────────────────────────────────────────────────────────────────

def is_store(con):
    return con.execute(
        "SELECT count(*) FROM duckdb_tables() WHERE database_name = current_database() "
        "AND table_name = ? AND NOT internal", [domain.STORE_MARK]).fetchone()[0] > 0


def catalog(con):
    """Tabelas e views do banco aberto, com o tamanho ESTIMADO (o exato seria
    um `count(*)` por tabela — num banco do armazém, duzentas varreduras)."""
    out = []
    for schema, nome, est, ncols in con.execute(
            "SELECT schema_name, table_name, estimated_size, column_count FROM duckdb_tables() "
            "WHERE database_name = current_database() AND NOT internal AND NOT temporary").fetchall():
        out.append({'schema': schema, 'name': nome, 'kind': 'table', 'rows': est, 'columns': ncols})
    for schema, nome, ncols in con.execute(
            "SELECT schema_name, view_name, column_count FROM duckdb_views() "
            "WHERE database_name = current_database() AND NOT internal AND NOT temporary").fetchall():
        out.append({'schema': schema, 'name': nome, 'kind': 'view', 'rows': None, 'columns': ncols})
    out.sort(key=lambda t: (t['schema'] != 'main', t['schema'], t['name'].lower()))
    return out


def find_table(con, schema, table):
    """A tabela/view pedida, conferida no catálogo: é esta conferência que
    deixa o nome entrar no SQL (entre aspas)."""
    for t in catalog(con):
        if t['schema'] == schema and t['name'] == table:
            return t
    raise domain.ExplorerError('bad_table', 'Unknown table: %s.%s' % (schema, table), 404,
                               table='%s.%s' % (schema, table))


def columns_of(con, schema, table):
    """[(nome, tipo)] da tabela, na ordem do `SELECT *`."""
    return con.execute(
        "SELECT column_name, data_type FROM duckdb_columns() WHERE database_name = current_database() "
        "AND schema_name = ? AND table_name = ? ORDER BY column_index", [schema, table]).fetchall()


# ── leituras da tela ────────────────────────────────────────────────────────

def tables(rel):
    path = db_path(rel)
    st = os.stat(path)

    def fn(con):
        return {'store': is_store(con), 'tables': catalog(con)}
    out = _ler(path, fn)
    out['db'] = {'path': rel, 'size': st.st_size, 'mtime': st.st_mtime}
    return out


def _expandida(cols, valores, escolha, section=None):
    """A visão EXPANDIDA (`domain.expand`) com a família de cada coluna: as
    da tabela mantêm a do catálogo (texto que é sempre data ISO vira data,
    para a tela escrever dd/mm/aaaa), as que saíram do JSON pela dos valores.
    A contagem de uma seção (visão geral) é a família `section`: a tela a
    desenha como o link que abre a seção."""
    names = [n for n, _t in cols]
    nomes, linhas, cortou = domain.expand(names, valores, names.index(escolha), section=section)
    catalogo = {n: t for n, t in cols if n != escolha and n != '_seq'}
    meta = []
    for i, n in enumerate(nomes):
        tipo = catalogo.get(n) if i < len(catalogo) else None
        kind = domain.kind_of(tipo) if tipo else None
        if tipo is None and any(isinstance(l[i], domain.Rows) for l in linhas):
            meta.append({'name': n, 'type': 'JSON', 'kind': 'section'})
            continue
        if tipo is None or kind in ('text', None):
            achado = domain.infer_kind([l[i] for l in linhas])
            kind = achado if tipo is None or achado == 'date' else kind
        meta.append({'name': n, 'type': str(tipo) if tipo else 'JSON', 'kind': kind})
    return meta, [[None, None] + [domain.cell(v) for v in l] for l in linhas], cortou


def rows(rel, schema, table, limit, expand=None, section=None):
    """As linhas para a grade: `[rowid, impressão, valores…]` numa tabela que
    se edita, `[None, None, valores…]` numa que não. A impressão é da linha
    INTEIRA, e é ela que a gravação confere.

    `expand`: a coluna JSON a abrir em linhas e colunas (`''` = como está
    gravado; `None` = o padrão, que no armazém abre a tabela "chave + JSON" já
    expandida). A visão expandida é só leitura. `section`: a seção do objeto
    (`domain.sections`) a abrir; fora da lista, a visão geral."""
    path = db_path(rel)
    limit = domain.clamp_limit(limit)

    def fn(con):
        alvo = find_table(con, schema, table)
        q = domain.qualified(schema, table)
        store = is_store(con)
        total = con.execute('SELECT count(*) FROM %s' % q).fetchone()[0]
        if alvo['kind'] == 'table':
            cols = columns_of(con, schema, table)
            motivo = domain.readonly_reason(store, 'table', [c[0] for c in cols])
            sql = ('SELECT rowid, * FROM %s ORDER BY rowid LIMIT ?' if motivo is None
                   else 'SELECT * FROM %s LIMIT ?') % q
            cur = con.execute(sql, [limit])
            dados = cur.fetchall()
        else:
            motivo = 'view'
            cur = con.execute('SELECT * FROM %s LIMIT ?' % q, [limit])
            dados = cur.fetchall()
            cols = [(d[0], str(d[1])) for d in cur.description]
        names = [n for n, _t in cols]
        valores = [list(r[1:]) if motivo is None else list(r) for r in dados]
        candidatos = domain.json_columns(names, valores)
        if expand is None:
            escolha = domain.default_expand(names, candidatos, store)
        else:
            escolha = expand if expand in candidatos else None
        out = {'total': total, 'limit': limit, 'kind': alvo['kind'], 'store': store,
               'json_columns': candidatos, 'expanded': escolha, 'truncated': False,
               'source_rows': len(dados), 'sections': [], 'section': None}
        if escolha:
            secoes = domain.sections(valores, names.index(escolha))
            sec = section if section in {s['name'] for s in secoes} else None
            out.update(sections=secoes, section=sec)
            meta, linhas, out['truncated'] = _expandida(cols, valores, escolha, sec)
            out.update(columns=meta, rows=linhas, readonly=motivo or 'expanded')
            return out
        meta = [{'name': n, 'type': str(t), 'kind': domain.kind_of(t)} for n, t in cols]
        if motivo is None:
            linhas = [[r[0], domain.row_hash(r[1:])] + [domain.cell(v) for v in r[1:]] for r in dados]
        else:
            linhas = [[None, None] + [domain.cell(v) for v in r] for r in dados]
        out.update(columns=meta, rows=linhas, readonly=motivo)
        return out
    return _ler(path, fn)
