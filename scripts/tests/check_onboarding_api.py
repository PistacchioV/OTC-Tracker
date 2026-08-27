# -*- coding: utf-8 -*-
"""A camada HTTP do Onboarding (CGD), ponta a ponta.

O `check_cgd_docs.py` protege o MODULO — o aging, as etapas, o formulario. O que
ninguem prendia era o que a TELA recebe: os dominios que ela usa para montar os
campos de edicao, o `_stage`/`_closed` que vao junto de cada linha, e o
comportamento do lote no save e no delete.

Este script existe por causa disso e foi escrito ANTES de o Onboarding sair do
`routes.py` — com o codigo ainda no lugar, para o verde valer como linha de base.
Extrair sem essa linha de base seria mover codigo no escuro.

Nada real e tocado: o DuckDB do CGD vai para um tmp.
"""
import os, sys, tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)

TMP = tempfile.mkdtemp()

from apps.pages import cgd_docs                            # noqa: E402
cgd_docs.DB_PATH = os.path.join(TMP, 'db', 'cgd_sharepoint.db')

from apps import create_app                                # noqa: E402
from apps.config import DebugConfig                        # noqa: E402

app = create_app(DebugConfig)
app.config['TESTING'] = True

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def cliente(auth=True):
    c = app.test_client()
    if auth:
        with c.session_transaction() as s:
            s['authenticated'] = True
            s['user_sid'] = 'A111111'
            s['user_name'] = 'Alice Souza'
            s['user_role'] = 'BO'
            s['user_email'] = 'alice.souza@jpmorgan.com'
            # UTC: a sessao expira contra o relogio UTC, e uma data local em
            # fuso negativo nasce vencida — o 401 resultante se le como
            # autenticacao quebrada quando e so fuso.
            s['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()
    return c


c = cliente()
anon = cliente(auth=False)


def jget(cli, url):
    r = cli.get(url)
    return r.status_code, (r.get_json() or {})


def jpost(cli, url, body):
    r = cli.post(url, json=body)
    return r.status_code, (r.get_json() or {})


API = ('/api/onboarding/overview', '/api/onboarding/docs')
POSTS = ('/api/onboarding/docs/save', '/api/onboarding/docs/delete')

print('\n== 1. sem sessao, nenhum endpoint responde ==')
for u in API:
    check('GET %s -> 401' % u, jget(anon, u)[0], 401)
for u in POSTS:
    check('POST %s -> 401' % u, jpost(anon, u, {})[0], 401)

print('\n== 2. banco AUSENTE: a tela diz onde ele deveria estar ==')
# "Nenhum documento" e "o script de importacao nunca rodou" se resolvem de
# jeitos opostos, e sem o caminho na resposta a tela nao tem como distinguir.
check('o arquivo realmente nao existe', os.path.isfile(cgd_docs.DB_PATH), False)
st, d = jget(c, '/api/onboarding/overview')
check('overview responde 200', st, 200)
check('   db_ready False', d['db_ready'], False)
check('   e diz o caminho', d['db'], cgd_docs.DB_PATH)
check('   sem linha nenhuma', d['counts']['total'], 0)
st, d = jget(c, '/api/onboarding/docs')
check('docs responde 200', st, 200)
check('   db_ready False', d['db_ready'], False)
check('   rows vazio', d['rows'], [])
check('   mas as COLUNAS vao junto', bool(d['columns']), True)

print('\n== 3. o payload das docs carrega os dominios da tela ==')
# A tela monta o campo de edicao a partir deles. Uma lista escrita no template
# seria uma segunda copia, que envelhece calada no dia em que a do servidor
# mudar.
cgd_docs.ensure_db()
id_a = cgd_docs.add_row({'Razão Social': 'ACME LTDA', 'CNPJ': '11.222.333/0001-44',
                         'Status': 'Em andamento', 'Doc Type': 'CGD',
                         'Signature Type': 'DocuSign'})
id_b = cgd_docs.add_row({'Razão Social': 'BETA SA', 'CNPJ': '55.666.777/0001-88',
                         'Status': 'Active', 'Doc Type': 'CSA'})
st, d = jget(c, '/api/onboarding/docs')
check('db_ready True', d['db_ready'], True)
check('duas linhas', len(d['rows']), 2)
for campo, esperado in (('id_column', cgd_docs.ID_COLUMN),
                        ('signature_column', cgd_docs.SIGNATURE_COLUMN),
                        ('doc_type_column', cgd_docs.DOC_TYPE_COLUMN)):
    check('   %s' % campo, d[campo], esperado)
for campo, esperado in (('date_columns', list(cgd_docs.DATE_COLUMNS)),
                        ('stages', list(cgd_docs.STAGES)),
                        ('signature_types', list(cgd_docs.SIGNATURE_TYPES)),
                        ('doc_types', list(cgd_docs.DOC_TYPES)),
                        ('guarantor_options', list(cgd_docs.GUARANTOR_OPTIONS))):
    check('   %s vem do modulo' % campo, d[campo], esperado)
check('   columns e a lista do modulo', d['columns'], cgd_docs.COLUMNS)

print('\n== 4. a etapa vai JUNTO da linha, calculada no servidor ==')
# Recalcular no navegador seria a mesma regra escrita duas vezes, e a copia do
# JS discordaria da do servidor no primeiro status novo que a lista trouxesse.
por_id = {r[cgd_docs.ID_COLUMN]: r for r in d['rows']}
linha_a, linha_b = por_id[str(id_a)], por_id[str(id_b)]
check('a linha aberta tem _stage', bool(linha_a['_stage']), True)
check('   e diz se a etapa foi DERIVADA', isinstance(linha_a['_stage_derived'], bool), True)
check('   _stage bate com o modulo', linha_a['_stage'],
      (cgd_docs.pending_stage(linha_a)[0] or ''))
# `_stages` e a LISTA: Legal e OTC correm em paralelo e a coluna mostra as duas.
check('   _stages e a lista do modulo', linha_a['_stages'],
      cgd_docs.pending_stages(linha_a)[0])
check('   e a linha nova esta nas DUAS mesas', linha_a['_stages'], ['Legal', 'OTC'])
check('a linha Active NAO esta encerrada por engano', linha_b['_closed'],
      bool(cgd_docs.is_closed(linha_b)))
check('   e Active e encerrada de verdade', linha_b['_closed'], True)
check('   entao ela nao tem etapa', linha_b['_stage'], '')

print('\n== 5. save: cria, edita e o LOTE ==')
st, d = jpost(c, '/api/onboarding/docs/save', {'values': {'Razão Social': 'NOVA LTDA'}})
check('sem id -> cria', st, 200)
novo = str(d['id'])
check('   devolve o id novo', novo not in ('', 'None'), True)
st, d = jpost(c, '/api/onboarding/docs/save',
              {'id': novo, 'values': {'Razão Social': 'NOVA LTDA EDITADA'}})
check('com id -> edita', (st, d['success']), (200, True))
linhas = {r[cgd_docs.ID_COLUMN]: r for r in cgd_docs.load_all()}
check('   e a gravacao chegou ao banco',
      linhas[novo]['Razão Social'], 'NOVA LTDA EDITADA')
st, d = jpost(c, '/api/onboarding/docs/save',
              {'ids': [str(id_a), novo], 'values': {'Status': 'Cancelado'}})
check('ids -> edicao em massa', (st, d['count']), (200, 2))
linhas = {r[cgd_docs.ID_COLUMN]: r for r in cgd_docs.load_all()}
check('   as duas linhas mudaram',
      [linhas[str(id_a)]['Status'], linhas[novo]['Status']],
      ['Cancelado', 'Cancelado'])

print('\n== 6. save recusa o payload malformado ==')
st, d = jpost(c, '/api/onboarding/docs/save', {'id': novo, 'values': 'nao sou dict'})
check('values que nao e dict -> 400', (st, d['error']), (400, 'invalid_values'))

print('\n== 7. delete: a linha, o lote, e o id repetido ==')
st, d = jpost(c, '/api/onboarding/docs/delete', {'id': novo})
check('id -> apaga', (st, d['success']), (200, True))
check('   e sumiu do banco',
      novo in {r[cgd_docs.ID_COLUMN] for r in cgd_docs.load_all()}, False)
id_c = cgd_docs.add_row({'Razão Social': 'C LTDA'})
id_d = cgd_docs.add_row({'Razão Social': 'D LTDA'})
# O id repetido na lista faria a contagem devolvida MENTIR sobre quantos
# documentos sairam — o `set` do endpoint e o que impede isso.
st, d = jpost(c, '/api/onboarding/docs/delete',
              {'ids': [str(id_c), str(id_d), str(id_c)]})
check('ids repetidos contam UMA vez', (st, d['count']), (200, 2))
restantes = {r[cgd_docs.ID_COLUMN] for r in cgd_docs.load_all()}
check('   e os dois sairam', {str(id_c), str(id_d)} & restantes, set())
st, d = jpost(c, '/api/onboarding/docs/delete', {})
check('sem id -> 400 missing_id', (st, d['error']), (400, 'missing_id'))

print('\n== 7b. os carimbos da esteira ==')
# Quem escreve data e SID e o SERVIDOR: um relogio errado ou um SID digitado
# assinariam a etapa por outra pessoa. O upload do arquivo e o do Electronic
# Inventory, testado la — aqui se prende so o carimbo.
id_e = cgd_docs.add_row({'Razão Social': 'ESTEIRA LTDA', 'Status': 'Em andamento',
                         'Legal Entity': 'JPMORGAN CHASE BANK, N.A. - SAO PAULO BRANCH'})
st, d = jpost(c, '/api/onboarding/docs/stamp', {'id': str(id_e), 'action': 'taxonomy'})
check('taxonomy -> 200', (st, d['success']), (200, True))
lin = {r[cgd_docs.ID_COLUMN]: r for r in cgd_docs.load_all()}[str(id_e)]
check('   a coluna Taxonomy leva data e SID', 'A111111' in lin['Taxonomy'], True)
check('   e a pendencia da Legal passou ao CEM MO',
      cgd_docs.pending_stages(lin)[0], ['OTC', 'CEM MO'])
st, d = jpost(c, '/api/onboarding/docs/stamp',
              {'id': str(id_e), 'action': 'otc', 'issue_date': '20/08/2026',
               'signature_date': '21/08/2026', 'b3_id': 'B3X-123'})
check('otc -> 200', (st, d['success']), (200, True))
lin = {r[cgd_docs.ID_COLUMN]: r for r in cgd_docs.load_all()}[str(id_e)]
check('   Emissao e assinatura gravadas',
      (lin['Emissão'], lin['Signature Date']), ('20/08/2026', '21/08/2026'))
# A LE da linha e a Chase: o B3 ID cai na coluna MGT, nunca na JPM.
check('   o B3 ID caiu na coluna da LE (MGT)', lin['B3 ID - MGT'], 'B3X-123')
check('   e a JPM ficou em branco', lin['B3 ID - JPM'], '')
check('   OTC - STAMP fechou a mesa', bool(lin['OTC - STAMP']), True)
check('   sobrou so o CEM MO', cgd_docs.pending_stages(lin)[0], ['CEM MO'])
st, d = jpost(c, '/api/onboarding/docs/stamp', {'id': str(id_e), 'action': 'mo'})
check('mo -> 200', (st, d['success']), (200, True))
lin = {r[cgd_docs.ID_COLUMN]: r for r in cgd_docs.load_all()}[str(id_e)]
check('   MO - STAMP e Conclusion gravados',
      bool(lin['MO - STAMP']) and bool(lin['Conclusion - Stamp']), True)
check('   o Status virou Active e o documento saiu das filas',
      (lin['Status'], cgd_docs.pending_stages(lin)[0]), ('Active', []))
st, d = jpost(c, '/api/onboarding/docs/stamp',
              {'id': str(id_e), 'action': 'otc', 'issue_date': '20/08/2026'})
check('otc sem os tres campos -> 400', (st, d['error']), (400, 'missing_fields'))
st, d = jpost(c, '/api/onboarding/docs/stamp', {'id': str(id_e), 'action': 'x'})
check('acao desconhecida -> 400', (st, d['error']), (400, 'unknown_action'))
st, d = jpost(c, '/api/onboarding/docs/stamp', {'action': 'mo'})
check('sem id -> 400', (st, d['error']), (400, 'missing_id'))
check('sem sessao -> 401',
      jpost(anon, '/api/onboarding/docs/stamp', {'id': '1', 'action': 'mo'})[0], 401)
cgd_docs.delete_row(id_e)

print('\n== 8. as paginas sobem, com o formulario do MODULO ==')
# O `REQUEST_FORM` define o modal de New Request E os campos obrigatorios que
# seguram o documento no Banking. Escrito no template, o dia em que um campo
# deixasse de ser obrigatorio o modal pararia de pedi-lo e a fila continuaria
# cobrando.
for url in ('/onboarding', '/onboarding/tracking-docs'):
    r = c.get(url)
    check('GET %s -> 200' % url, r.status_code, 200)
    corpo = r.get_data(as_text=True)
    rotulo = cgd_docs.REQUEST_FORM[0]['label']
    check('   o formulario veio do modulo (%s)' % rotulo, rotulo in corpo, True)
r = c.get('/cgd')
check('/cgd redireciona para o Overview', r.status_code, 302)
check('   para /onboarding', r.headers.get('Location', '').endswith('/onboarding'), True)

print(('FAIL: %d' % len(fails)) if fails else 'TUDO OK')
sys.exit(1 if fails else 0)
