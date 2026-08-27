# -*- coding: utf-8 -*-
"""Acrescenta ao `cgd_sharepoint.db` as colunas que o `cgd_docs.py` já espera.

Isto NÃO deveria precisar de script (CLAUDE.md §7 — `ensure_db()` roda
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS` a cada escrita), mas até agora
`load_all()` era o único ponto do módulo que NUNCA chamava `ensure_db` — só
lia. Numa instância cujo banco é anterior a uma coluna nova (o caso de
`Taxonomy`, `ECI`, `SPN`, `CASID`, `UCN`, `Legal Entity`,
`Instituição Financeira`, `B3 Account`), a tela quebrava com
`BinderException: column not found` antes de qualquer escrita ter chance de
corrigir o schema. Esse bug foi corrigido em `cgd_docs.load_all` nesta mesma
mudança; este script é só o atalho para quem já está com o app fora do ar
AGORA, sem esperar o próximo restart bater o `load_all` corrigido.

É idempotente e não apaga nem move nada — só `ALTER TABLE ADD COLUMN IF NOT
EXISTS`, a mesma operação que `ensure_db()` já faz. Rodar de novo, ou nunca
rodar (o próximo restart já resolve sozinho), dá o mesmo resultado.

    source .venv311/bin/activate
    python scripts/fix_cgd_docs_schema.py
"""
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Fora do Windows o `Config` exige o share absoluto (§8); este script só lê o
# `Config.DATABASE_DIR` para achar o banco, nunca escreve fora dele.
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', os.path.join(REPO_ROOT, '.import-share'))


def main():
    import duckdb
    from apps.pages import cgd_docs

    path = cgd_docs.DB_PATH
    if not os.path.isfile(path):
        print('Banco não existe ainda em {} — nada a corrigir '
              '(a próxima importação já cria com o schema atual).'.format(path))
        return 0

    con = duckdb.connect(path)
    try:
        antes = {r[1] for r in con.execute(
            "PRAGMA table_info('{}')".format(cgd_docs.TABLE)).fetchall()}
    finally:
        con.close()

    faltando = [c for c in cgd_docs.DB_COLUMNS if c not in antes]
    if not faltando:
        print('{}: schema já está completo ({} colunas). Nada a fazer.'
              .format(path, len(antes)))
        return 0

    print('{}: faltam {} coluna(s): {}'.format(path, len(faltando), ', '.join(faltando)))
    cgd_docs.ensure_db(path)

    con = duckdb.connect(path)
    try:
        depois = {r[1] for r in con.execute(
            "PRAGMA table_info('{}')".format(cgd_docs.TABLE)).fetchall()}
    finally:
        con.close()

    ainda_faltando = [c for c in faltando if c not in depois]
    if ainda_faltando:
        print('ERRO: continuam faltando: {}'.format(', '.join(ainda_faltando)))
        return 1
    print('OK — acrescentadas: {}'.format(', '.join(faltando)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
