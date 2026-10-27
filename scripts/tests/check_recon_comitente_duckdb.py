"""Recon Comitente: o banco é DuckDB, e o SQLite de antes migra sozinho (§707).

O `matching_comitentes.db` era o último SQLite do app. Agora a tabela mora no
`Comitentes_OTCTracker.db` (DuckDB, pelo `duckdb_read`/`duckdb_write` da
camada), e a primeira leitura ou gravação importa o SQLite antigo UMA vez,
deixando-o intacto. Bancos de verdade numa pasta temporária:

  1. a migração: as linhas e os TIPOS (int volta int, float volta float, texto
     volta texto, nulo volta vazio na tela); o SQLite fica como estava; o
     DuckDB existente não é migrado de novo;
  2. o round-trip da gravação do Run (`_grava_tabela`) e a comparação do dia
     seguinte: a mesma linha sai `OK`, a mudada `Check`, a nova `New`;
  3. migração que falha (banco ocupado) SOBE no Run e não marca como feita — lida
     como "vazio", o Run marcaria tudo `New` e gravaria o DuckDB por cima;
  4. o `verify_integrity` da rota (era o `PRAGMA quick_check` do SQLite).
"""
import os
import shutil
import sqlite3
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', tempfile.mkdtemp(prefix='share-root-'))
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

import pandas as pd                                              # noqa: E402

from apps import create_app                                      # noqa: E402
from apps.config import DebugConfig                              # noqa: E402

app = create_app(DebugConfig)
from apps.pages import database_access as DA                     # noqa: E402
from apps.pages import recon_comitente as RC                     # noqa: E402

fails = []


def check(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg)
    if not cond:
        fails.append(msg)


SCORES = ['Address Matching Score (%)', 'Name Matching Score (%)', 'Phone Matching Score (%)',
          'E-mail Matching Score (%)', 'Fins Lucrativos Matching Score (%)',
          'Start Date Matching Score (%)', 'CNAE Matching Score (%)']


def linha(cnpj, nome, media=95.5, natureza='PJ'):
    r = {'Status': 'New', 'LE': 'JPM', 'B3 CNPJ': cnpj, 'B3 Name': nome, 'Party Central Name': nome,
         'Matching Score Averaged': media, 'Natureza Fiscal': natureza, 'Dono do Cadastro': 'N',
         'B3 Address': 'RUA A', 'Party Central Address': 'RUA A', 'B3 Phone': '1', 'Party Central Phone': '1',
         'B3 E-mail': 'a@b', 'Party Central E-mail': 'a@b', 'B3 Fins Lucrativos': 'S',
         'Party Central Fins Lucrativos': 'S', 'Contas': 3}
    r.update({c: 100 for c in SCORES})
    return r


tmp = tempfile.mkdtemp(prefix='comitente-duck-')
_orig = (RC.DB_PATH, RC.LEGACY_SQLITE_PATH)


def aponta(nome):
    RC.DB_PATH = os.path.join(tmp, nome, 'Comitentes_OTCTracker.db')
    RC.LEGACY_SQLITE_PATH = os.path.join(tmp, nome, 'matching_comitentes.db')
    os.makedirs(os.path.dirname(RC.DB_PATH), exist_ok=True)


try:
    with app.app_context():
        print('== 1. a migração do SQLite ==')
        aponta('m')
        con = sqlite3.connect(RC.LEGACY_SQLITE_PATH)
        con.execute('CREATE TABLE comitentes ("index", "Status", "B3 CNPJ", "Contas", '
                    '"Matching Score Averaged", "Natureza Fiscal", "Misto")')
        con.executemany('INSERT INTO comitentes VALUES (?, ?, ?, ?, ?, ?, ?)', [
            (0, 'OK', '12.345.678/0001-90', 3, 95.5, 'PJ', 7),
            (1, 'Check', '98.765.432/0001-10', None, 81.0, None, 'texto'),
        ])
        con.commit()
        con.close()
        antes = os.path.getmtime(RC.LEGACY_SQLITE_PATH)
        out = RC.load_from_db()
        rows = out['data']
        check(len(rows) == 2 and out['counts']['ok'] == 1 and out['counts']['check'] == 1,
              'as duas linhas migraram, com o Status (%r)' % out['counts'])
        check('index' not in rows[0], 'a coluna `index` do pandas antigo fica de fora')
        check(rows[0]['Contas'] == 3 and isinstance(rows[0]['Contas'], int), 'int volta int')
        check(rows[0]['Matching Score Averaged'] == 95.5, 'float volta float')
        check(rows[1]['Contas'] == '' and rows[1]['Natureza Fiscal'] == '', 'nulo volta vazio na tela')
        check(rows[0]['Misto'] == '7' and rows[1]['Misto'] == 'texto', 'coluna de tipos misturados vira texto')
        check(os.path.isfile(RC.DB_PATH), 'o DuckDB nasceu')
        with DA.duckdb_read(RC.DB_PATH) as c:
            check(c.execute('SELECT count(*) FROM comitentes').fetchone()[0] == 2, 'e é DuckDB de verdade')
        check(os.path.getmtime(RC.LEGACY_SQLITE_PATH) == antes, 'o SQLite fica intacto')
        RC._MIGRADOS.clear()                                     # um processo novo
        con = sqlite3.connect(RC.LEGACY_SQLITE_PATH)
        con.execute("INSERT INTO comitentes VALUES (2, 'New', '11.111.111/0001-11', 1, 90.0, 'PJ', 1)")
        con.commit()
        con.close()
        check(RC.load_from_db()['counts']['total'] == 2, 'com o DuckDB existente, o SQLite não é lido de novo')

        print('\n== 2. o Run grava e o dia seguinte compara ==')
        aponta('r')
        df = pd.DataFrame([linha('12345678000190', 'ACME'), linha('98765432000110', 'BETA', media=88.25)])
        with DA.duckdb_write(RC.DB_PATH) as c:
            RC._grava_tabela(c, df)
        volta = RC.load_from_db()['data']
        check([r['B3 Name'] for r in volta] == ['ACME', 'BETA'], 'o round-trip da gravação')
        check(volta[1]['Matching Score Averaged'] == 88.25 and volta[0]['Contas'] == 3, 'com os tipos')
        amanha = pd.DataFrame([linha('12345678000190', 'ACME'), linha('98765432000110', 'BETA NOVA', media=88.25),
                               linha('22222222000122', 'GAMA')])
        st = list(RC._compare_with_db(amanha, RC.DB_PATH)['Status'])
        check(st == ['OK', 'Check', 'New'], 'igual = OK, mudada = Check, nova = New (%r)' % st)
        vazio = pd.DataFrame(columns=list(df.columns))
        with DA.duckdb_write(RC.DB_PATH) as c:
            RC._grava_tabela(c, vazio)
        check(RC.load_from_db()['counts']['total'] == 0, 'lote vazio grava a tabela vazia')

        print('\n== 3. migração que falha sobe ==')
        aponta('f')
        shutil.copy(os.path.join(tmp, 'm', 'matching_comitentes.db'), RC.LEGACY_SQLITE_PATH)
        _sr = RC.sqlite_read

        def ocupado(path):
            raise DA.DatabaseLockTimeout(path, 'read', 1.0)
        RC.sqlite_read = ocupado
        try:
            try:
                RC._compare_with_db(amanha, RC.DB_PATH)
                subiu = False
            except DA.DatabaseLockTimeout:
                subiu = True
            check(subiu, 'o Run recebe o OCUPADO (a rota responde 503 retryable)')
            check(not os.path.isfile(RC.DB_PATH), 'e nenhum DuckDB vazio nasce por cima')
            check(RC.load_from_db()['counts']['total'] == 0, 'a tela abre vazia, sem quebrar')
        finally:
            RC.sqlite_read = _sr
        check(RC.load_from_db()['counts']['total'] == 3, 'a leitura seguinte migra')

        print('\n== 4. verify_integrity ==')
        check(RC.verify_integrity() is True, 'o banco abre e a tabela se lê')
        try:
            RC.verify_integrity(os.path.join(tmp, 'nao-existe.db'))
            levantou = False
        except Exception:                                        # noqa: BLE001
            levantou = True
        check(levantou, 'sem o banco, levanta (a rota lê como integrity_ok=False)')
finally:
    RC.DB_PATH, RC.LEGACY_SQLITE_PATH = _orig
    shutil.rmtree(tmp, ignore_errors=True)

print(('\nFAIL: %d' % len(fails)) if fails else '\nTUDO OK')
sys.exit(1 if fails else 0)
