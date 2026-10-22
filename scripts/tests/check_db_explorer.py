"""Database Explorer (Data Base › Database Explorer) — só o master (22/10/2026).

Prende:
  1. as regras puras (`domain`): o tipo que se edita, o valor que vai e volta
     da tela, a impressão digital da linha, o caminho do banco;
  2. a trava: sem sessão é 401, quem não é master leva 403 na API e volta do
     endereço da página — o menu só aparece para o master, mas `Page_Access`
     vazio é acesso total, então quem segura é a ROTA; e a página fica fora da
     checklist do /page-access;
  3. a API ponta a ponta num `DATABASE_DIR` temporário: a lista de bancos (sem
     `_recuperado`, sem `.lock`), as tabelas e views, as linhas com a
     impressão, o Edit de uma linha (data dd/mm/aaaa, NULL), a linha que mudou
     desde a leitura RECUSADA sem gravar nada, o lote tudo-ou-nada, o valor que
     o CAST recusa, a coluna só leitura, o Delete, o banco do ARMAZÉM (com
     `_manifest`) só leitura, `..` e o SQLite recusados;
  4. o JSON EM COLUNAS: a forma do ledger de IR (`{dia: {contraparte: {name,
     due, withheld…}}}`) vira uma linha por dia × contraparte, na `__meta` e no
     `__raw`; o dia sem lançamento não vira linha; campo com o nome
     de outra coluna leva prefixo; a tabela "chave + JSON" do armazém abre já
     expandida, "como está gravado" volta ao cru, e a tabela editável só expande
     quando pedida — e aí é só leitura.

Não toca em dado real: tudo num tmp.
"""
import json
import os
import sqlite3
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, ROOT)
RAIZ = tempfile.mkdtemp(prefix='otc-dbx-')
DBDIR = os.path.join(RAIZ, 'db')
os.makedirs(DBDIR)
os.environ['OTC_DATA_DIR'] = RAIZ
os.environ['OTC_DATABASE_DIR'] = DBDIR
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')
if os.name != 'nt' and not os.environ.get('OTC_SHARED_DRIVE_ROOT'):
    os.environ['OTC_SHARED_DRIVE_ROOT'] = tempfile.mkdtemp(prefix='otc-share-')

import duckdb  # noqa: E402

FALHAS = []
# a forma do ledger de IR do NDF Summary (`ndf-ir-ledger_AAAAMM.json`)
LEDGER = {
    '2026-10-01': {'ebazar ltda': {'name': 'EBAZAR', 'due': 10.5, 'withheld': 0.0, 'carry_in': 0.0, 'carry_after': 10.5}},
    '2026-10-02': {},
    '2026-10-05': {'bayer sa': {'name': 'BAYER S.A.', 'due': 1139.4, 'withheld': 1139.4, 'carry_in': 0.0, 'carry_after': 0.0},
                   'suzano sa': {'name': 'SUZANO SA', 'due': 0.4, 'withheld': 0.0, 'carry_in': 0.6, 'carry_after': 1.0}},
}


def check(nome, cond, extra=''):
    print(('  ok  ' if cond else ' FAIL ') + nome + (('  — ' + str(extra)) if (not cond and extra) else ''))
    if not cond:
        FALHAS.append(nome)


def semear():
    """Um banco de plataforma, um do armazém, um SQLite com `.db` no nome e
    uma cópia de segurança do recover."""
    con = duckdb.connect(os.path.join(DBDIR, 'Plataforma.db'))
    con.execute('CREATE TABLE people (id INTEGER PRIMARY KEY, name VARCHAR, born DATE, amount DECIMAL(18,2), '
                'active BOOLEAN, seen TIMESTAMP, tags VARCHAR[])')
    con.execute("INSERT INTO people VALUES (1, 'Ana', '1990-05-01', 10.50, true, '2026-01-02 03:04:05', ['a']),"
                "(2, 'Bia', NULL, 20.00, true, NULL, NULL), (3, 'Caio', '1985-12-31', NULL, false, NULL, ['x', 'y'])")
    con.execute('CREATE VIEW active_people AS SELECT * FROM people WHERE active')
    con.execute('CREATE SCHEMA extra')
    con.execute('CREATE TABLE extra."odd ""name""" (v VARCHAR)')
    con.execute("INSERT INTO extra.\"odd \"\"name\"\"\" VALUES ('z')")
    con.execute('CREATE TABLE prefs (sid VARCHAR, doc VARCHAR)')
    con.execute('INSERT INTO prefs VALUES (?, ?)', ['A1', json.dumps({'theme': 'dark', 'ui': {'wall': 'slate'}})])
    con.close()
    # pasta e nome que a semeadura da subida não usa (ela grava o armazém real
    # neste mesmo tmp, e um `mappings/bank-name.db` seria sobrescrito)
    os.makedirs(os.path.join(DBDIR, 'zz-armazem'))
    con = duckdb.connect(os.path.join(DBDIR, 'zz-armazem', 'teste.db'))
    con.execute('CREATE TABLE _manifest (path VARCHAR, mtime DOUBLE, fsize BIGINT, targets VARCHAR)')
    con.execute('CREATE TABLE bank_name (NAME VARCHAR, _seq BIGINT, _raw VARCHAR)')
    con.execute("INSERT INTO bank_name VALUES ('BANCO X', 0, '{\"NAME\": \"BANCO X\"}')")
    con.execute('CREATE TABLE ledger__meta (key VARCHAR, value VARCHAR)')
    con.executemany('INSERT INTO ledger__meta VALUES (?, ?)', [[k, json.dumps(v)] for k, v in LEDGER.items()])
    con.execute('CREATE TABLE ledger__raw (_seq BIGINT, _raw VARCHAR)')
    con.execute('INSERT INTO ledger__raw VALUES (0, ?)', [json.dumps(LEDGER)])
    con.close()
    lite = sqlite3.connect(os.path.join(DBDIR, 'comitentes.db'))
    lite.execute('CREATE TABLE t (a INTEGER)')
    lite.commit()
    lite.close()
    os.makedirs(os.path.join(DBDIR, '_recuperado', '20261022'))
    duckdb.connect(os.path.join(DBDIR, '_recuperado', '20261022', 'velho.db')).close()
    open(os.path.join(DBDIR, 'Plataforma.db.lock'), 'w').close()


def ler(sql, params=None):
    con = duckdb.connect(os.path.join(DBDIR, 'Plataforma.db'), read_only=True)
    try:
        return con.execute(sql, params or []).fetchall()
    finally:
        con.close()


def main():
    from apps.pages.features.db_explorer import domain

    print('== 1. regras puras ==')
    check('identificador com aspa dobrada', domain.quote_ident('a"b') == '"a""b"')
    check('qualificado', domain.qualified('main', 'x y') == '"main"."x y"')
    tipos = {'VARCHAR': 'text', 'INTEGER': 'int', 'DECIMAL(18,4)': 'decimal', 'DOUBLE': 'float', 'BOOLEAN': 'bool',
             'DATE': 'date', 'TIMESTAMP': 'timestamp', 'JSON': 'json', 'UUID': 'other',
             'TIMESTAMP WITH TIME ZONE': 'other', 'BLOB': None, 'VARCHAR[]': None,
             'STRUCT(a INTEGER)': None, "ENUM('a', 'b')": None}
    check('família de cada tipo (lista/STRUCT/BLOB/ENUM só leitura)',
          {t: domain.kind_of(t) for t in tipos} == tipos, {t: domain.kind_of(t) for t in tipos})
    from datetime import date, datetime
    from decimal import Decimal
    check('valor para a tela', [domain.cell(v) for v in (None, True, 5, 2 ** 60, 1.5, Decimal('1.10'),
                                                         date(2026, 1, 2), datetime(2026, 1, 2, 3, 4, 5),
                                                         b'\xaa', ['a'])]
          == [None, True, 5, str(2 ** 60), 1.5, '1.10', '2026-01-02', '2026-01-02 03:04:05', '\\xaa', '["a"]'])
    check('impressão estável e sensível à mudança',
          domain.row_hash([1, 'a']) == domain.row_hash([1, 'a']) and domain.row_hash([1, 'a']) != domain.row_hash([1, 'b']))
    check('data dd/mm/aaaa vira ISO', domain.input_value('date', '05/03/2026', False) == '2026-03-05')
    check('timestamp dd/mm/aaaa hh:mm', domain.input_value('timestamp', '05/03/2026 14:30', False) == '2026-03-05 14:30:00')
    check('texto vazio fica texto vazio; número vazio é NULL',
          domain.input_value('text', '', False) == '' and domain.input_value('int', '  ', False) is None)
    check('NULL marcado é NULL até no texto', domain.input_value('text', 'x', True) is None)
    check('booleano por palavra', domain.input_value('bool', 'Sim', False) == 'true'
          and domain.input_value('bool', '0', False) == 'false')
    for ruim in ('../x.db', '/etc/x.db', 'C:/x.db', 'a/../../x.db', '_recuperado/x/velho.db', 'x.txt', ''):
        try:
            domain.resolve_db(DBDIR, ruim)
            check('recusa o caminho %r' % ruim, False)
        except domain.ExplorerError as e:
            check('recusa o caminho %r' % ruim, e.code == 'bad_db')
    check('caminho bom', domain.resolve_db(DBDIR, 'zz-armazem/teste.db') == os.path.join(DBDIR, 'zz-armazem', 'teste.db'))
    check('limite com teto', domain.clamp_limit('999999') == domain.MAX_LIMIT and domain.clamp_limit('x') == domain.DEFAULT_LIMIT)
    try:
        domain.set_clause({'tags': ('VARCHAR[]', None)}, {'tags': {'value': 'x'}})
        check('coluna só leitura recusada no SET', False)
    except domain.ExplorerError as e:
        check('coluna só leitura recusada no SET', e.code == 'readonly_column')

    print('== 1b. JSON em colunas ==')
    meta = [[k, json.dumps(v)] for k, v in LEDGER.items()]
    check('acha a coluna JSON', domain.json_columns(['key', 'value'], meta) == ['value'])
    check('texto comum não é JSON', domain.json_columns(['a'], [['abc'], ['{x']]) == [])
    nomes, linhas, cortou = domain.expand(['key', 'value'], meta, 1)
    check('__meta: dia, contraparte e os campos em colunas',
          nomes == ['key', 'value › key', 'name', 'due', 'withheld', 'carry_in', 'carry_after'], nomes)
    check('...uma linha por dia × contraparte, o dia sem lançamento fora',
          [l[:3] for l in linhas] == [['2026-10-01', 'ebazar ltda', 'EBAZAR'],
                                     ['2026-10-05', 'bayer sa', 'BAYER S.A.'], ['2026-10-05', 'suzano sa', 'SUZANO SA']])
    check('...com os números', linhas[1][3:5] == [1139.4, 1139.4] and not cortou)
    nomes, linhas, _ = domain.expand(['_seq', '_raw'], [[0, json.dumps(LEDGER)]], 1)
    check('__raw: o mês inteiro, dia e contraparte em duas colunas (o _seq sai)',
          nomes[:3] == ['_raw › key 1', '_raw › key 2', 'name'] and len(linhas) == 3, nomes)
    check('família pelos valores', [domain.infer_kind([l[i] for l in linhas]) for i in (0, 2, 3)] == ['date', 'text', 'float'])
    nomes, linhas, _ = domain.expand(['key', 'value'], [['k', json.dumps({'key': 1, 'a': {'b': 2}})]], 1)
    check('campo homônimo leva prefixo; objeto aninhado vira a.b', nomes == ['key', 'value.key', 'a.b'], nomes)
    check('lista de registros: uma linha por item',
          domain.expand(['x'], [[json.dumps([{'a': 1}, {'a': 2}])]], 0)[1] == [[1], [2]])
    check('o teto corta e diz que cortou', domain.expand(['key', 'value'], meta, 1, cap=2)[2] is True)
    check('armazém "chave + JSON" abre expandido', domain.default_expand(['key', 'value'], ['value'], True) == 'value'
          and domain.default_expand(['_seq', '_raw'], ['_raw'], True) == '_raw')
    check('...dataset tipado e banco de plataforma, não',
          domain.default_expand(['NAME', '_seq', '_raw'], ['_raw'], True) is None
          and domain.default_expand(['key', 'value'], ['value'], False) is None)

    semear()
    from apps import create_app
    from apps.config import DebugConfig
    from apps.pages import routes as R
    from apps.pages.platform import authz
    app = create_app(DebugConfig)

    print('== 2. a trava ==')
    check('a página fica fora da checklist do /page-access', '/database-explorer' not in authz._NAV_URLS)
    anon = app.test_client()
    check('sem sessão: 401', anon.get('/api/database-explorer/databases').status_code == 401)

    def cliente(sid, role):
        c = app.test_client()
        with c.session_transaction() as s:
            s['authenticated'] = True
            s['user_sid'] = sid
            s['user_name'] = 'Teste'
            s['user_role'] = role
            s['session_ip'] = '127.0.0.1'
        return c
    admin = cliente('A000001', 'ADMIN')
    r = admin.get('/api/database-explorer/databases')
    check('admin (não master): 403 master_only', r.status_code == 403 and r.get_json().get('code') == 'master_only')
    r = admin.post('/api/database-explorer/update', json={})
    check('admin não grava', r.status_code == 403)
    r = admin.get('/database-explorer')
    check('admin pelo endereço volta ao dashboard', r.status_code == 302 and '/dashboard' in r.headers.get('Location', ''))
    master_sid = sorted(R._MASTER_SIDS)[0]
    m = cliente(master_sid, 'MASTER')
    r = m.get('/database-explorer')
    html = r.get_data(as_text=True)
    check('master abre a página', r.status_code == 200 and 'id="dbxTable"' in html)
    check('o menu do master tem o link', 'href="/database-explorer"' in html)
    with app.test_request_context('/'):
        from flask import render_template, session
        session['user_role'] = 'ADMIN'
        check('o menu do admin não tem', 'href="/database-explorer"' not in render_template('partials/sidenav.html'))

    print('== 3. a API ==')
    dbs = m.get('/api/database-explorer/databases').get_json()['databases']
    caminhos = [d['path'] for d in dbs]
    pastas = [d['folder'] for d in dbs]
    check('lista os bancos: a raiz primeiro, depois as pastas em ordem',
          pastas == sorted(pastas, key=lambda f: (f != '', f.lower())), pastas[:6])
    check('...com os da raiz', {'comitentes.db', 'Plataforma.db'} <= set(caminhos))
    check('...e o da subpasta', 'zz-armazem/teste.db' in caminhos)
    check('...sem o _recuperado e sem .lock', not any('_recuperado' in p or p.endswith('.lock') for p in caminhos))

    r = m.get('/api/database-explorer/tables?db=comitentes.db')
    check('SQLite com .db no nome: not_duckdb', r.status_code == 400 and r.get_json()['code'] == 'not_duckdb')
    r = m.get('/api/database-explorer/tables?db=../x.db')
    check('..: bad_db', r.status_code == 400 and r.get_json()['code'] == 'bad_db')
    tb = m.get('/api/database-explorer/tables?db=Plataforma.db').get_json()
    nomes = {(t['schema'], t['name'], t['kind']) for t in tb['tables']}
    check('tabelas e views', {('main', 'people', 'table'), ('main', 'active_people', 'view'),
                              ('extra', 'odd "name"', 'table')} <= nomes, nomes)
    check('banco de plataforma não é do armazém', tb['store'] is False)

    def rows(table, schema='main', db='Plataforma.db', limit=1000):
        return m.post('/api/database-explorer/rows', json={'db': db, 'schema': schema, 'table': table, 'limit': limit})
    d = rows('people').get_json()
    kinds = {c['name']: c['kind'] for c in d['columns']}
    check('colunas com a família', kinds == {'id': 'int', 'name': 'text', 'born': 'date', 'amount': 'decimal',
                                             'active': 'bool', 'seen': 'timestamp', 'tags': None}, kinds)
    check('editável', d['readonly'] is None and d['total'] == 3 and len(d['rows']) == 3)
    por_id = {r[2]: r for r in d['rows']}
    check('linha = [rowid, impressão, valores…]', por_id[1][3] == 'Ana' and por_id[1][4] == '1990-05-01'
          and por_id[1][5] == '10.50' and len(por_id[1][1]) == 20)
    check('identificador estranho entre aspas', rows('odd "name"', schema='extra').get_json()['rows'][0][2] == 'z')
    check('view: só leitura', rows('active_people').get_json()['readonly'] == 'view')
    check('limite', rows('people', limit=2).get_json()['rows'].__len__() == 2)
    check('tabela inexistente: bad_table', rows('nope').status_code == 404)

    def upd(items, values, table='people', db='Plataforma.db'):
        return m.post('/api/database-explorer/update',
                      json={'db': db, 'schema': 'main', 'table': table, 'items': items, 'values': values})
    ana = por_id[1]
    r = upd([{'rowid': ana[0], 'h': ana[1]}], {'name': {'value': 'Ana Maria'}, 'born': {'value': '07/08/1991'},
                                               'amount': {'value': None, 'null': True}})
    check('Edit de uma linha', r.status_code == 200 and r.get_json()['updated'] == 1, r.get_json())
    check('...gravou nome, data dd/mm/aaaa e NULL',
          ler('SELECT name, born, amount FROM people WHERE id = 1') == [('Ana Maria', date(1991, 8, 7), None)])
    r = upd([{'rowid': ana[0], 'h': ana[1]}], {'name': {'value': 'Outra'}})
    check('impressão velha: 409 row_changed', r.status_code == 409 and r.get_json()['code'] == 'row_changed')
    check('...e nada gravado', ler('SELECT name FROM people WHERE id = 1') == [('Ana Maria',)])

    d = rows('people').get_json()
    por_id = {r[2]: r for r in d['rows']}
    lote = [{'rowid': por_id[i][0], 'h': por_id[i][1]} for i in (2, 3)]
    ruim = lote + [{'rowid': por_id[1][0], 'h': 'x' * 20}]
    r = upd(ruim, {'active': {'value': 'false'}})
    check('lote com uma linha velha: recusa o lote inteiro', r.status_code == 409)
    check('...sem gravar nenhuma', ler('SELECT count(*) FROM people WHERE NOT active') == [(1,)])
    r = upd(lote, {'active': {'value': 'false'}, 'name': {'value': 'Lote'}})
    check('lote de duas linhas', r.status_code == 200 and r.get_json()['updated'] == 2, r.get_json())
    check('...gravado nas duas', ler("SELECT count(*) FROM people WHERE name = 'Lote' AND NOT active") == [(2,)])

    d = rows('people').get_json()
    por_id = {r[2]: r for r in d['rows']}
    um = [{'rowid': por_id[1][0], 'h': por_id[1][1]}]
    r = upd(um, {'amount': {'value': 'abc'}})
    check('valor que o CAST recusa: 400 bad_value', r.status_code == 400 and r.get_json()['code'] == 'bad_value')
    r = upd(um, {'tags': {'value': '[q]'}})
    check('coluna só leitura: 400 readonly_column', r.status_code == 400 and r.get_json()['code'] == 'readonly_column')
    r = upd(um, {'nope': {'value': '1'}})
    check('coluna inexistente: bad_column', r.get_json().get('code') == 'bad_column')
    r = upd([], {'name': {'value': 'x'}})
    check('sem linha: no_rows', r.get_json().get('code') == 'no_rows')
    r = upd(um, {})
    check('sem coluna: nothing_to_change', r.get_json().get('code') == 'nothing_to_change')
    r = upd(um, {'seen': {'value': '01/02/2026 10:11:12'}})
    check('timestamp dd/mm/aaaa', r.status_code == 200
          and ler('SELECT seen FROM people WHERE id = 1') == [(datetime(2026, 2, 1, 10, 11, 12),)])

    d = rows('people').get_json()
    por_id = {r[2]: r for r in d['rows']}
    r = m.post('/api/database-explorer/delete', json={'db': 'Plataforma.db', 'schema': 'main', 'table': 'people',
                                                      'items': [{'rowid': por_id[3][0], 'h': por_id[3][1]}]})
    check('Delete', r.status_code == 200 and r.get_json()['deleted'] == 1 and ler('SELECT count(*) FROM people') == [(2,)])
    r = m.post('/api/database-explorer/delete', json={'db': 'Plataforma.db', 'schema': 'main', 'table': 'people',
                                                      'items': [{'rowid': por_id[3][0], 'h': por_id[3][1]}]})
    check('Delete de linha já apagada: 409', r.status_code == 409)

    print('== 4. o armazém é só leitura ==')
    tb = m.get('/api/database-explorer/tables?db=zz-armazem/teste.db').get_json()
    check('banco com _manifest é do armazém', tb['store'] is True)
    d = rows('bank_name', db='zz-armazem/teste.db').get_json()
    check('linhas sem rowid/impressão e readonly=store',
          d['readonly'] == 'store' and d['rows'][0][:2] == [None, None] and d['rows'][0][2] == 'BANCO X')
    r = upd([{'rowid': 0, 'h': 'x'}], {'NAME': {'value': 'Y'}}, table='bank_name', db='zz-armazem/teste.db')
    check('gravar no armazém: 409 readonly_store', r.status_code == 409 and r.get_json()['code'] == 'readonly_store')

    print('== 5. JSON em colunas pela API ==')
    d = rows('ledger__meta', db='zz-armazem/teste.db').get_json()
    check('a __meta do armazém abre expandida', d['expanded'] == 'value' and d['readonly'] == 'store'
          and [c['name'] for c in d['columns']][:4] == ['key', 'value › key', 'name', 'due'], d.get('expanded'))
    check('...a data da chave vira data, o número vira número',
          [c['kind'] for c in d['columns']][:4] == ['date', 'text', 'text', 'float'])
    check('...3 linhas (dia × contraparte) de 3 registros', len(d['rows']) == 3 and d['source_rows'] == 3)
    d = m.post('/api/database-explorer/rows', json={'db': 'zz-armazem/teste.db', 'schema': 'main',
                                                    'table': 'ledger__meta', 'expand': ''}).get_json()
    check('"como está gravado" volta ao cru', d['expanded'] is None and len(d['rows']) == 3
          and d['json_columns'] == ['value'])
    d = rows('ledger__raw', db='zz-armazem/teste.db').get_json()
    check('o __raw do mês inteiro também', d['expanded'] == '_raw' and len(d['rows']) == 3)
    d = rows('prefs').get_json()
    check('tabela editável com JSON não expande sozinha', d['expanded'] is None and d['readonly'] is None
          and d['json_columns'] == ['doc'])
    d = m.post('/api/database-explorer/rows', json={'db': 'Plataforma.db', 'schema': 'main', 'table': 'prefs',
                                                    'expand': 'doc'}).get_json()
    check('...pedida, expande e fica só leitura', d['expanded'] == 'doc' and d['readonly'] == 'expanded'
          and [c['name'] for c in d['columns']] == ['sid', 'theme', 'ui.wall'] and d['rows'][0][:2] == [None, None])
    d = m.post('/api/database-explorer/rows', json={'db': 'Plataforma.db', 'schema': 'main', 'table': 'prefs',
                                                    'expand': 'sid'}).get_json()
    check('coluna que não é JSON não expande', d['expanded'] is None)

    print('== 6. a tela: um dia por vez, com o total ==')
    tpl = open(os.path.join(ROOT, 'apps', 'templates', 'pages', 'database-explorer.html'), encoding='utf-8').read()
    js = open(os.path.join(ROOT, 'apps', 'static', 'js', 'pages', 'database-explorer.js'), encoding='utf-8').read()
    check('o seletor do dia na barra', 'id="dbxDay"' in tpl)
    check('o filtro do dia é um ext.search próprio (o column().search() o funil zera)',
          'jQuery.fn.dataTable.ext.search.push' in js and 'row[S.dayCol + 2] === S.day' in js)
    check('a visão expandida por data abre ordenada pelo dia', "order: S.dayCol >= 0 ? [[off + S.dayCol, 'asc']] : []" in js)
    check('o rodapé soma o que a grade mostra, e vai no Export',
          "api.rows({ search: 'applied' })" in js and 'footer: true' in js and '<tfoot>' in js)
    check('o Clear Filters volta a todos os dias', "S.day = ''; el('dbxDay').value = '';" in js)

    print()
    print('TUDO OK' if not FALHAS else '%d FALHA(S): %s' % (len(FALHAS), ', '.join(FALHAS)))
    return 1 if FALHAS else 0


if __name__ == '__main__':
    sys.exit(main())
