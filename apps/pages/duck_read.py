# -*- coding: utf-8 -*-
"""Leitura DB-first com contrato de FRESCOR — a fase 3 da migração (HANDOFF §328).

O leitor religado não confia cegamente no banco: ele só o usa quando o
`_manifest` do próprio banco (caminho, mtime, tamanho — gravado pelo motor a
cada conversão) prova que a tabela reflete o JSON **como ele está agora** em
disco. Qualquer outra situação — banco ausente, manifest defasado (alguém
editou o JSON por fora do app), arquivo em uso pelo espelho neste instante —
devolve `None`: o chamador cai no JSON de sempre e o espelho é avisado para se
curar. O flip nunca pode ser a fonte de um dado velho; no pior caso ele é só
um caminho a mais que não funcionou, e o comportamento é o de ontem.

As conexões aqui são as CRUAS do DuckDB (como as do motor/espelho), não as do
`database_access`: os bancos espelhados têm um escritor só (a thread do
espelho, ou o script de carga) e leitores de melhor esforço — a colisão
intra-processo com o espelho escrevendo vira exceção, capturada, `None`,
fallback. Nenhuma fila, nenhum lock no share.
"""
import json
import os

import duckdb

from apps.pages.json_to_duckdb import q


def _data_root():
    from apps.pages import routes
    return os.path.normpath(routes._B3_DATA_DIR)


def _limpo(rows):
    """NULL → '' nas colunas de texto: o JSON de origem guarda string em tudo
    que existe, e um `str(None)` no consumidor viraria o literal 'None'."""
    out = []
    for r in rows:
        out.append({k: ('' if v is None else v) for k, v in r.items()})
    return out


def table_rows(db_name, table, rel, schema='main', order_by=None, heal=None,
               manifest_key=None, expected_path=None):
    """As linhas de `table` SE o manifest prova que o banco reflete o JSON
    `rel` atual — senão `None` (e o espelho é avisado para se curar).

    `rel` é o caminho relativo à raiz de dados; `manifest_key` é a CHAVE no
    `_manifest` quando ela difere do caminho (as tabelas de cadastro levam a
    versão do formato no sufixo — um banco no formato antigo simplesmente não
    casa, cai no JSON e o espelho reconverte no novo). `heal` troca o aviso
    padrão (`notify_write` do caminho) — os arquivos de calendário precisam do
    aviso explícito."""
    try:
        raiz = _data_root()
        jpath = os.path.join(raiz, rel.replace('/', os.sep))
        # `expected_path` é o guarda da SUPERFÍCIE DE PATCH: o chamador diz de
        # que arquivo ELE leria, e se não for o canônico que o espelho cobre
        # (um `_cpd_path`/`data_path` trocado por teste ou config), o banco não
        # responde — refletir OUTRO arquivo com carimbo de fresco seria a
        # fonte errada.
        if expected_path is not None and \
                os.path.normpath(str(expected_path)) != os.path.normpath(jpath):
            return None
        st = os.stat(jpath)
    except Exception:                                       # noqa: BLE001
        return None

    def _cura():
        try:
            from apps.pages import duck_mirror
            if heal is not None:
                heal()
            else:
                duck_mirror.notify_write(jpath)
        except Exception:                                   # noqa: BLE001
            pass

    try:
        from apps.pages import duck_mirror
        db = os.path.join(duck_mirror._out_dir(raiz), db_name)
        if not os.path.isfile(db):
            _cura()
            return None
        con = duckdb.connect(db, read_only=True)
        try:
            row = con.execute('SELECT mtime, fsize FROM _manifest WHERE path = ?',
                              [manifest_key or rel]).fetchone()
            if not row or abs(row[0] - st.st_mtime) >= 1e-6 or row[1] != st.st_size:
                _cura()
                return None
            sql = 'SELECT * FROM %s.%s' % (q(schema), q(table))
            if order_by:
                sql += ' ORDER BY ' + order_by
            cur = con.execute(sql)
            cols = [d[0] for d in cur.description]
            return _limpo(dict(zip(cols, r)) for r in cur.fetchall())
        finally:
            con.close()
    except Exception:                                       # noqa: BLE001
        # Banco em uso pelo espelho, tabela ausente, formato inesperado: o
        # fallback é o JSON — nunca um erro para quem só pediu as linhas.
        return None


def raw_records(db_name, table, rel, expected_path=None):
    """Os REGISTROS ORIGINAIS de uma tabela de cadastro — a coluna `_raw`,
    que guarda cada registro exatamente como está no JSON.

    É o canal de fidelidade do flip: reconstruir pelo conjunto de colunas
    poria chave com NULL onde o JSON não tinha chave nenhuma, e há consumidor
    que decide pela AUSÊNCIA (o `_contacts_norm` do CounterpartyDetails).
    Linha sem `_raw` (banco em formato antigo) devolve `None` — o manifest
    versionado já impede o caso, isto é o cinto de segurança."""
    from apps.pages.json_to_duckdb import _refdata_manifest_key
    rows = table_rows(db_name, table, rel,
                      manifest_key=_refdata_manifest_key(rel),
                      expected_path=expected_path)
    if rows is None:
        return None
    out = []
    for r in rows:
        cru = r.get('_raw')
        if not cru:
            return None
        try:
            out.append(json.loads(cru))
        except ValueError:
            return None
    return out


def refdata_rows(expected_path=None):
    """Os registros originais do RefData — do `reference_data.db` quando fresco."""
    return raw_records('reference_data.db', 'refdata', 'RefData.json',
                       expected_path=expected_path)


def cpd_records(expected_path=None):
    """Os registros originais do CounterpartyDetails — fidelidade total,
    chave-ausente incluída."""
    return raw_records('reference_data.db', 'counterparty_details',
                       'CounterpartyDetails.json', expected_path=expected_path)
