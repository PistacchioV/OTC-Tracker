# -*- coding: utf-8 -*-
"""Corrige a coluna "Owner" (banker) dos 3 DBs do Pending Confirmation.

Alguns registros foram carregados com o banker errado. A fonte da verdade é o
RefData.json (campo BANKER): para cada linha, procura o registro do RefData
pelo SPN (ignorando zeros à esquerda; fallback: nome do Client) e, quando o
RefData tem BANKER, ele PREVALECE sobre o que estiver no DB. Linhas cujo
SPN/Client não existem no RefData — ou cujo registro não tem BANKER — ficam
como estão.

A página lê direto desses DBs, então corrigir aqui corrige a página.
Idempotente — rodar de novo não muda nada. Uso:

    source .venv311/bin/activate
    python scripts/update_pending_confirmation_bankers.py
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
        banker = str(rec.get('BANKER', '') or '').strip()
        if not banker:
            continue
        k = norm_spn(rec.get('SPN', ''))
        if k and k not in by_spn:
            by_spn[k] = banker
        n = norm_name(rec.get('COUNTERPARTY', ''))
        if n and n not in by_name:
            by_name[n] = banker
    return by_spn, by_name


def migrate(path, by_spn, by_name):
    name = os.path.basename(path)
    if not os.path.isfile(path):
        print(f'{name}: não existe — pulado')
        return
    con = duckdb.connect(path)
    try:
        rows = con.execute(
            'SELECT rowid, "SPN", "Client", "Owner" FROM {}'.format(TABLE)).fetchall()
        fixed = 0
        for rowid, spn, client, owner_cur in rows:
            banker = by_spn.get(norm_spn(spn)) or by_name.get(norm_name(client))
            if not banker:
                continue
            if banker != str(owner_cur or '').strip():
                con.execute(
                    'UPDATE {} SET "Owner" = ? WHERE rowid = ?'.format(TABLE),
                    [banker, rowid])
                fixed += 1
        print(f'{name}: {len(rows)} linhas · Owner corrigido em {fixed} linha(s)')
    finally:
        con.close()


def main():
    if not os.path.isfile(REFDATA):
        print('RefData.json não encontrado em', REFDATA)
        sys.exit(1)
    by_spn, by_name = load_refdata()
    print(f'RefData: {len(by_spn)} SPNs com BANKER')
    for db in DBS:
        migrate(os.path.join(DB_DIR, db), by_spn, by_name)
    print('Concluído.')


if __name__ == '__main__':
    main()
