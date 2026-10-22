# -*- coding: utf-8 -*-
"""As gravações do Database Explorer: editar e apagar linhas, uma ou em lote.

Tudo dentro de UM `duckdb_write` (trava exclusiva entre instâncias +
transação): confere o catálogo, confere a impressão digital de cada linha e
só então grava. Lote é tudo ou nada — uma linha que mudou desde a leitura
recusa o pedido inteiro, e nada é gravado."""
import duckdb

from apps.pages import database_access
from apps.pages.features.db_explorer import domain, queries

# O `rowid` vai numa lista só (`unnest`), e não numa sequência de `IN (?, ?…)`
# em fatias: no DuckDB o UPDATE de algumas colunas troca o `rowid` da linha, e
# uma segunda fatia rodando depois da primeira poderia achar a linha errada.
_IDS = '(SELECT unnest(CAST(? AS BIGINT[])))'


def _ids(items):
    """[(rowid, impressão)] do pedido, sem repetir; vazio ou malformado recusa."""
    if not isinstance(items, list) or not items:
        raise domain.ExplorerError('no_rows', 'No rows selected')
    out, vistos = [], set()
    for it in items:
        try:
            rid = int(it.get('rowid'))
        except (AttributeError, TypeError, ValueError):
            raise domain.ExplorerError('bad_rows', 'Invalid row reference')
        h = str(it.get('h') or '')
        if rid in vistos:
            continue
        vistos.add(rid)
        out.append((rid, h))
    return out


def _alvo_editavel(con, schema, table):
    alvo = queries.find_table(con, schema, table)
    cols = queries.columns_of(con, schema, table)
    motivo = domain.readonly_reason(queries.is_store(con), alvo['kind'], [c[0] for c in cols])
    if motivo:
        raise domain.ExplorerError('readonly_' + motivo, 'This table is read-only here (%s)' % motivo, 409)
    return cols


def _confere(con, q, pedidos):
    ids = [rid for rid, _h in pedidos]
    atual = {r[0]: domain.row_hash(r[1:])
             for r in con.execute('SELECT rowid, * FROM %s WHERE rowid IN %s' % (q, _IDS), [ids]).fetchall()}
    mudaram = [rid for rid, h in pedidos if atual.get(rid) != h]
    if mudaram:
        raise domain.ExplorerError(
            'row_changed', '%d row(s) changed or were removed since they were loaded — reload and try again'
            % len(mudaram), 409, count=len(mudaram))
    return ids


def _grava(rel, fn):
    path = queries.db_path(rel)
    try:
        with database_access.duckdb_write(path) as con:
            return fn(con)
    except domain.ExplorerError:
        raise
    except (duckdb.Error, database_access.DatabaseAccessError, OSError) as e:
        raise queries.as_explorer_error(e)


def update_rows(rel, schema, table, items, values):
    """Grava `values` (coluna → {value, null}) nas linhas `items`. Uma linha é
    o Edit do modal; várias, a alteração em lote. Devolve quantas mudaram."""
    pedidos = _ids(items)
    if not isinstance(values, dict) or not values:
        raise domain.ExplorerError('nothing_to_change', 'No column to change')

    def fn(con):
        cols = _alvo_editavel(con, schema, table)
        meta = {n: (t, domain.kind_of(t)) for n, t in cols}
        sets, params = domain.set_clause(meta, values)
        q = domain.qualified(schema, table)
        ids = _confere(con, q, pedidos)
        n = con.execute('UPDATE %s SET %s WHERE rowid IN %s' % (q, sets, _IDS), params + [ids]).fetchone()[0]
        return int(n)
    return _grava(rel, fn)


def delete_rows(rel, schema, table, items):
    pedidos = _ids(items)

    def fn(con):
        _alvo_editavel(con, schema, table)
        q = domain.qualified(schema, table)
        ids = _confere(con, q, pedidos)
        n = con.execute('DELETE FROM %s WHERE rowid IN %s' % (q, _IDS), [ids]).fetchone()[0]
        return int(n)
    return _grava(rel, fn)
