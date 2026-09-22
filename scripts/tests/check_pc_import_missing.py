"""Carga do que FALTA no Pending Confirmation a partir da planilha
(`scripts/import_pending_confirmation_missing.py`, mesa 22/09/2026).

O script acrescenta aos tres bancos o que a planilha tem e eles nao tem. Tres
coisas nele quebram SEM ERRO NENHUM, e sao o que este teste prende:

  1. O MATCH DO NOME. SPN, Client e Owner saem do Reference Data; o nome da
     planilha e quem os encontra. Match exato vale sempre; parecido so vale
     acima do limiar E com vantagem sobre o segundo colocado. Um SPN "quase
     certo" nao e um SPN: ele leva a operacao para outra contraparte, com
     Owner, Economic Group e Signature Type de outra contraparte junto.

  2. O QUE JA EXISTE E PULADO. A chave e o Trade Number, olhado nos TRES
     bancos — a linha anda entre eles. E a leitura e ESTRITA: banco que nao
     abre PARA o script, porque lido como vazio ele reinseriria como novo tudo
     que ja estava la, duplicando a fila da mesa.

  3. AS COLUNAS. Cabecalho resolvido pelo NOME (a planilha muda de ordem entre
     versoes), as duas escritas que convivem (`Client` e `End Counterparty
     Desc`), data guardada dd/mm/aaaa e `#NULL!` de formula quebrada virando
     vazio em vez de entrar no banco como dado.

Nao encosta em dado real: planilha gerada no tmp, bancos no tmp, Reference Data
trocado por um cadastro de mentira.

    OTC_SHARED_DRIVE_ROOT=/tmp/otc-share python scripts/tests/check_pc_import_missing.py
"""
import importlib.util
import io
import os
import shutil
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', '/tmp/otc-share')
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label +
          ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def carrega_script():
    caminho = os.path.join(ROOT, 'scripts', 'import_pending_confirmation_missing.py')
    spec = importlib.util.spec_from_file_location('pc_import_missing', caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


S = carrega_script()
from apps.pages import routes as R                                    # noqa: E402
from apps.pages.platform import pending_confirmation as PC            # noqa: E402

# Um cadastro de mentira, com um par PROXIMO de proposito (as duas VOTORANTIM):
# e nele que se ve a diferenca entre "parecido" e "escolhido no par ou impar".
REFDATA = [
    {'COUNTERPARTY': 'BANCO SAFRA S/A', 'SPN': '1000001', 'BANKER': 'ANA SOUZA',
     'ECONOMIC GROUP': 'SAFRA', 'SIGNATURE TYPE': 'Digital'},
    {'COUNTERPARTY': 'ITAU UNIBANCO S.A.', 'SPN': '1000002', 'BANKER': 'BRUNO LIMA',
     'ECONOMIC GROUP': 'ITAU', 'SIGNATURE TYPE': 'Physical'},
    {'COUNTERPARTY': 'VOTORANTIM CIMENTOS S.A.', 'SPN': '1000003', 'BANKER': 'CARLA DIAS',
     'ECONOMIC GROUP': 'VOTORANTIM', 'SIGNATURE TYPE': 'Digital'},
    {'COUNTERPARTY': 'VOTORANTIM CIMENTOS N/NE S.A.', 'SPN': '1000004', 'BANKER': 'DIRCE M',
     'ECONOMIC GROUP': 'VOTORANTIM', 'SIGNATURE TYPE': 'Digital'},
]
BY_NAME = {PC._pc_norm(r['COUNTERPARTY']): r for r in REFDATA}
BY_SPN = {R._norm_spn(r['SPN']): r for r in REFDATA}

PC._pc_refdata_by_name = lambda: dict(BY_NAME)
R._fxo_refdata_by_spn = lambda: dict(BY_SPN)

# ── 1. o match do nome ──────────────────────────────────────────────────────
print('== 1. o nome da planilha contra o Reference Data ==')
cad = S.Cadastro(dict(BY_NAME), 90.0, 3.0)

rec, tipo, pct, _alt = cad.casa('BANCO SAFRA S/A')
check('igual e EXATO', (tipo, rec.get('SPN')), ('exato', '1000001'))
# A grafia da mesa nao e a do cadastro: ponto, barra, "S.A." contra "S/A".
rec, tipo, pct, _alt = cad.casa('BANCO SAFRA S.A.')
check('so a pontuacao muda: exato mesmo assim (o _norm tira)',
      (tipo, rec.get('SPN')), ('exato', '1000001'))
rec, tipo, pct, _alt = cad.casa('ITAU UNIBANCO')
check('falta um pedaco do nome: SEMELHANTE e aplicado',
      (tipo, rec.get('SPN'), pct >= 90.0), ('semelhante', '1000002', True))
rec, tipo, pct, alt = cad.casa('PETROBRAS DISTRIBUIDORA')
check('nome que nao existe no cadastro fica SEM SPN', (tipo, rec.get('SPN')), ('fraco', None))
check('   e o relatorio ainda diz qual era o melhor', bool(alt), True)
# Duas contrapartes parecidissimas entre si: escolher uma e sortear.
rec, tipo, pct, alt = cad.casa('VOTORANTIM CIMENTOS NE S.A.')
check('duas igualmente parecidas: AMBIGUO, sem SPN', (tipo, rec.get('SPN')), ('ambiguo', None))
check('   e diz as duas no relatorio', alt.count('VOTORANTIM'), 2)
check('linha sem Client', cad.casa('')[1], 'sem-nome')

# ── 2. a planilha ───────────────────────────────────────────────────────────
print('\n== 2. as colunas da planilha ==')
TMP = tempfile.mkdtemp(prefix='pc-miss-')
XLSX = os.path.join(TMP, 'Copy of PENDING - Outstanding Confirmation OTC.xlsx')


def escreve_planilha(caminho, cabecalho, linhas):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(cabecalho)
    for l in linhas:
        ws.append(l)
    wb.save(caminho)


CAB = ['LOB', 'Client', 'Aging', 'Status', 'Product Type', 'Trade Date',
       'Maturity Date', 'Trade Number', 'Pending Status', 'Owner', 'EA',
       'JP sending documentation', 'Client return the document', 'Break Reason',
       'Overall Comments', 'Economic Group', 'Signature Type',
       'Trade Number IS FEP WEB', 'Pendência']


def linha(client, tn, trade='10/03/2026', mat='10/09/2027', pend='Pending Original',
          lob='EDG', prod='NDF', status='0-30', ea='', comments=''):
    return [lob, client, '', status, prod, trade, mat, tn, pend, 'QUEM MANDOU',
            ea, '', '', '', comments, '', '', '', '']


escreve_planilha(XLSX, CAB, [
    linha('BANCO SAFRA S/A', 'T-EXATO'),
    linha('ITAU UNIBANCO', 'T-SEMELHANTE'),
    linha('PETROBRAS DISTRIBUIDORA', 'T-SEM-SPN'),
    linha('VOTORANTIM CIMENTOS NE S.A.', 'T-AMBIGUO'),
    linha('BANCO SAFRA S/A', 'T-JA-EXISTE'),           # ja nos bancos
    linha('BANCO SAFRA S/A', ''),                      # sem Trade Number
    linha('BANCO SAFRA S/A', 'T-REPETIDO'),
    linha('BANCO SAFRA S/A', 'T-REPETIDO'),            # a mesma, duas vezes
    linha('BANCO SAFRA S/A', 'T-ANTIGA', trade='10/03/2023', mat='10/09/2023'),
    linha('BANCO SAFRA S/A', 'T-ERRO-XL', comments='#NULL!'),
])

linhas, resolvidos, faltando = S.le_planilha(XLSX, R._XL_ERROR_TEXT)
check('leu todas as linhas', len(linhas), 10)
check('resolveu Trade Date pelo nome do cabecalho', resolvidos['Trade Date'][1], 'Trade Date')
check('resolveu Comments pela grafia da planilha', resolvidos['Comments'][1], 'Overall Comments')
check('#NULL! de formula quebrada vira vazio', linhas[9]['Comments'], '')
# A outra escrita do mesmo arquivo (a do Pending Update) tem de resolver igual.
XLSX2 = os.path.join(TMP, 'update.xlsx')
escreve_planilha(XLSX2, ['LOB', 'End Counterparty Desc', 'Product Type', 'Booking Date',
                         'Settlement Date', 'Deal Name', 'Pending Status'],
                 [['EDG', 'BANCO SAFRA S/A', 'NDF', '10/03/2026', '10/09/2026', 'X1', '']])
l2, r2, f2 = S.le_planilha(XLSX2, R._XL_ERROR_TEXT)
check('a grafia do Pending Update resolve nas mesmas colunas',
      (r2['Client'][1], r2['Trade Date'][1], r2['Trade Number'][1]),
      ('End Counterparty Desc', 'Booking Date', 'Deal Name'))
check('coluna que nao veio e RELATADA', 'Status' in f2, True)

# ── 3. a carga ──────────────────────────────────────────────────────────────
print('\n== 3. insere o que falta, pula o que ja existe ==')
DBS = os.path.join(TMP, 'db')
os.makedirs(DBS)
R._PC_DB_DIR = DBS


def linha_db(tn, **kw):
    r = {c: '' for c in PC._PC_COLUMNS}
    r.update({'Trade Number': tn, 'Client': 'BANCO SAFRA S/A', 'Trade Date': '10/03/2026'})
    r.update(kw)
    return r


PC._pc_rewrite_db('pending', [linha_db('T-JA-EXISTE')])
PC._pc_rewrite_db('ok', [])
PC._pc_rewrite_db('backlog', [])


def roda(*extra):
    argv = sys.argv
    sys.argv = ['x', '--xlsx', XLSX, '--db-dir', DBS,
                '--relatorio', os.path.join(TMP, 'rel.csv')] + list(extra)
    try:
        saida = io.StringIO()
        stdout = sys.stdout
        sys.stdout = saida
        try:
            cod = S.main()
        finally:
            sys.stdout = stdout
        return cod, saida.getvalue()
    finally:
        sys.argv = argv


cod, saida = roda()
check('o modo padrao NAO grava', cod, 0)
check('   e diz isso', 'NADA FOI GRAVADO' in saida, True)
check('   e os bancos seguem como estavam',
      sum(len(PC._pc_load_rows(c)) for c in ('pending', 'ok', 'backlog')), 1)

cod, saida = roda('--gravar')
todas = {}
for cat in ('pending', 'ok', 'backlog'):
    for r in PC._pc_load_rows(cat):
        todas[str(r.get('Trade Number') or '')] = (cat, r)
check('inseriu as novas', sorted(todas), sorted([
    'T-EXATO', 'T-SEMELHANTE', 'T-SEM-SPN', 'T-AMBIGUO', 'T-REPETIDO', 'T-ANTIGA',
    'T-ERRO-XL', 'T-JA-EXISTE']))
check('a linha que ja existia nao foi duplicada',
      sum(1 for tn in todas if tn == 'T-JA-EXISTE'), 1)
# A linha repetida na planilha entra UMA vez: duas seriam duas pendencias para a
# mesma operacao, e a mesa cobraria o cliente duas vezes.
check('a repetida na planilha entrou uma vez so', 'T-REPETIDO' in todas, True)

cat, r = todas['T-EXATO']
check('SPN veio do cadastro', r['SPN'], '1000001')
check('Client veio do cadastro (a grafia do contrato)', r['Client'], 'BANCO SAFRA S/A')
check('Owner e o BANKER do cadastro', r['Owner'], 'ANA SOUZA')
check('Economic Group e Signature Type tambem',
      (r['Economic Group'], r['Signature Type']), ('SAFRA', 'Digital'))
check('LOB e Product Type vieram da PLANILHA', (r['LOB'], r['Product Type']), ('EDG', 'NDF'))
check('as datas ficam dd/mm/aaaa', (r['Trade Date'], r['Maturity Date']),
      ('10/03/2026', '10/09/2027'))

cat, r = todas['T-SEMELHANTE']
check('o match por semelhanca aplica o SPN', r['SPN'], '1000002')
cat, r = todas['T-SEM-SPN']
check('sem match, a linha ENTRA com o SPN vazio', r['SPN'], '')
check('   e mantem o nome da planilha', r['Client'], 'PETROBRAS DISTRIBUIDORA')
cat, r = todas['T-AMBIGUO']
check('o ambiguo tambem entra sem SPN', r['SPN'], '')
check('a de mais de 12 meses foi para o BACKLOG', todas['T-ANTIGA'][0], 'backlog')
check('a recente ficou em pending', todas['T-EXATO'][0], 'pending')

rel = io.open(os.path.join(TMP, 'rel.csv'), encoding='utf-8-sig').read()
check('o relatorio lista os nomes por tipo de match',
      all(x in rel for x in ('exato', 'semelhante', 'fraco', 'ambiguo')), True)

# Rodar de novo nao insere nada: e o que torna a carga repetivel sem duplicar.
antes = sum(len(PC._pc_load_rows(c)) for c in ('pending', 'ok', 'backlog'))
cod, saida = roda('--gravar')
depois = sum(len(PC._pc_load_rows(c)) for c in ('pending', 'ok', 'backlog'))
check('rodar DE NOVO nao duplica nada', (antes, depois), (depois, depois))

# ── 4. banco ilegivel PARA a carga ──────────────────────────────────────────
print('\n== 4. banco que nao abre para o script ==')
with io.open(os.path.join(DBS, 'pending-confirmation-ok.db'), 'wb') as fh:
    fh.write(b'nao sou um duckdb')
try:
    cod, saida = roda('--gravar')
except SystemExit as e:
    cod, saida = e.code, ''
check('sai com erro em vez de reinserir tudo como novo', cod != 0, True)

shutil.rmtree(TMP, ignore_errors=True)
print('\nTUDO OK' if not fails else '\n%d FALHA(S): %s' % (len(fails), ', '.join(fails)))
sys.exit(1 if fails else 0)
