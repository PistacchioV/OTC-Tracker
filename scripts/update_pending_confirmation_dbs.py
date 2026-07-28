# -*- coding: utf-8 -*-
"""Migra os 3 DBs do Pending Confirmation para o layout novo da página.

1. Remove as colunas "Baixa Sem Abono" e "Abono" (retiradas da página;
   "Pendência" fica e virou texto livre — como tudo é VARCHAR, não há
   mudança de tipo a fazer).
2. Preenche "Economic Group" e "Signature Type" de cada linha a partir do
   RefData.json (chave: SPN, ignorando zeros à esquerda; fallback: nome do
   Client). Quando o RefData tem valor, ele PREVALECE sobre o que estiver no
   DB (RefData é a fonte da verdade dessas duas colunas); linhas cujo
   SPN/Client não existem no RefData ficam como estão.

Idempotente — rodar de novo não muda nada. Uso:

    source .venv311/bin/activate
    python scripts/update_pending_confirmation_dbs.py
"""
import json
import os
import re
import sys
import unicodedata

import duckdb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_DIR = os.path.join(ROOT, 'apps', 'static', 'data', 'db')
REFDATA = os.path.join(ROOT, 'apps', 'static', 'data', 'RefData.json')
DBS = ['pending-confirmation-backlog.db',
       'pending-confirmation-pending.db',
       'pending-confirmation-ok.db']
TABLE = 'pending_confirmation'
DROP_COLS = ['Baixa Sem Abono', 'Abono']


def norm_spn(value):
    s = str(value or '').strip()
    if s.endswith('.0'):
        s = s[:-2]
    s = s.lstrip('0')
    return s or ('0' if value not in (None, '') else '')


def norm_name(s):
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^a-z0-9]', '', s.lower())


def load_refdata():
    with open(REFDATA, encoding='utf-8') as fh:
        rows = json.load(fh)
    by_spn, by_name = {}, {}
    for rec in rows:
        eg = str(rec.get('ECONOMIC GROUP', '') or '').strip()
        st = str(rec.get('SIGNATURE TYPE', '') or '').strip()
        if not (eg or st):
            continue
        k = norm_spn(rec.get('SPN', ''))
        if k and k not in by_spn:
            by_spn[k] = (eg, st)
        n = norm_name(rec.get('COUNTERPARTY', ''))
        if n and n not in by_name:
            by_name[n] = (eg, st)
    return by_spn, by_name


def migrate(path, by_spn, by_name):
    name = os.path.basename(path)
    if not os.path.isfile(path):
        print(f'{name}: não existe — pulado')
        return
    con = duckdb.connect(path)
    try:
        cols = [r[1] for r in con.execute(
            "PRAGMA table_info('{}')".format(TABLE)).fetchall()]
        dropped = []
        for c in DROP_COLS:
            if c in cols:
                con.execute('ALTER TABLE {} DROP COLUMN "{}"'.format(TABLE, c))
                dropped.append(c)

        rows = con.execute(
            'SELECT rowid, "SPN", "Client", "Economic Group", "Signature Type" '
            'FROM {}'.format(TABLE)).fetchall()
        filled = 0
        for rowid, spn, client, eg_cur, st_cur in rows:
            ref = by_spn.get(norm_spn(spn)) or by_name.get(norm_name(client))
            if not ref:
                continue
            eg_new = ref[0] or str(eg_cur or '').strip()
            st_new = ref[1] or str(st_cur or '').strip()
            if eg_new != str(eg_cur or '').strip() or st_new != str(st_cur or '').strip():
                con.execute(
                    'UPDATE {} SET "Economic Group" = ?, "Signature Type" = ? '
                    'WHERE rowid = ?'.format(TABLE), [eg_new, st_new, rowid])
                filled += 1
        print(f'{name}: {len(rows)} linhas · colunas removidas: '
              f'{dropped or "nenhuma (já migrado)"} · '
              f'Economic Group/Signature Type atualizados em {filled} linha(s)')
    finally:
        con.close()


def main():
    if not os.path.isfile(REFDATA):
        print('RefData.json não encontrado em', REFDATA)
        sys.exit(1)
    by_spn, by_name = load_refdata()
    print(f'RefData: {len(by_spn)} SPNs com Economic Group/Signature Type')
    for db in DBS:
        migrate(os.path.join(DB_DIR, db), by_spn, by_name)
    print('Concluído.')


if __name__ == '__main__':
    main()
