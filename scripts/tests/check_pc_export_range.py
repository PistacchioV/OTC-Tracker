"""Pending Confirmation: o intervalo do Advanced Export pergunta a uma COLUNA
de data dos TRES bancos, nao ao calendario de fotos diarias (mesa, 22/09/2026).

O intervalo do Advanced Export nasceu para as telas de arquivo-dia: ele le uma
foto por dia util e empilha. Aqui isso respondia outra pergunta. A operacao do
Pending Confirmation nao vive num dia — ela vive nos tres bancos (pending, ok e
backlog) e ANDA entre eles conforme o status resolve e o prazo vira. Pelas
fotos, a mesma operacao saia repetida em todas as fotos em que ainda estava
pendente, e nenhuma vez se ja tivesse sido resolvida antes da primeira foto.

O que este teste prende:

  1. o endpoint `/api/pending-confirmation/range`: os TRES bancos, a coluna
     escolhida, as duas pontas inclusive, a deduplicacao por Trade Number e a
     lista branca de colunas (o nome chega do navegador);
  2. a linha sem a data pedida NAO entra e e CONTADA (`undated`) — sumir calada
     e o que faz ninguem confiar no numero;
  3. a leitura e `strict`: banco ilegivel levanta em vez de virar planilha
     curta, que e indistinguivel de um intervalo sem movimento;
  4. a pagina declara o `range` com as duas colunas (Trade Date o PADRAO, por
     ser o primeiro) e nao declara mais o `daily`;
  5. o `export-advanced.js`: o combobox, a busca unica e a coluna Reference Date
     que NAO entra aqui (nao ha arquivo de um dia a carimbar).

Nao encosta em dado real: os tres bancos sao semeados num tmp.

    OTC_SHARED_DRIVE_ROOT=/tmp/otc-share python scripts/tests/check_pc_export_range.py
"""
import io
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

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


def read(rel):
    return io.open(os.path.join(ROOT, rel), encoding='utf-8', errors='ignore').read()


# ── 4. a pagina ──────────────────────────────────────────────────────────────
print('== 4. a pagina declara o intervalo por coluna de data ==')
HTML = read('apps/templates/pages/pending-confirmation.html')
blk = HTML.split('otcExportAdvanced(\'#pending-confirmation-table\'', 1)[-1].split('});', 1)[0]
check('declara o range', "url: '/api/pending-confirmation/range'" in blk, True)
check('Trade Date e a PRIMEIRA (o padrao)',
      blk.index("v: 'Trade Date'") < blk.index("v: 'Maturity Date'"), True)
check('oferece as duas colunas',
      ("v: 'Trade Date'" in blk and "v: 'Maturity Date'" in blk), True)
# O `daily` aqui leria as fotos, que e a pergunta que esta tela NAO faz. Os dois
# juntos seriam a mesma secao com dois significados.
check('nao declara mais o daily (as fotos)', 'daily:' in blk, False)

# ── 5. o export-advanced.js ──────────────────────────────────────────────────
print('\n== 5. o modo range no export-advanced.js ==')
JS = read('apps/static/js/export-advanced.js')
check('normRange existe', 'function normRange(' in JS, True)
check('fetchRange e UMA requisicao', 'function fetchRange(' in JS, True)
check('runRange usa o caminho comum de montagem',
      ('function runRange(' in JS and 'function montar(' in JS), True)
check('o combobox da coluna de data existe', 'xaDayField' in JS, True)
# O `range` EXCLUI o `daily`: a secao teria dois significados.
check('range desliga o daily', 'if (rango) daily = null;' in JS, True)
# Sem arquivo de um dia nao ha Reference Date a carimbar: uma coluna com a data
# de hoje em todas as linhas seria uma data inventada.
check('a busca por coluna nao carimba Reference Date', 'refDate: false' in JS, True)
check('a serie de arquivos-dia continua carimbando', 'refDate: true' in JS, True)
# O teto de dias e do intervalo por ARQUIVO (uma requisicao por dia util). Aqui
# a busca e uma so, e o mes de um ano atras custa o mesmo que o de ontem.
check('o teto de dias nao vale para a busca nos bancos',
      'if (daily && dayList(a, b).length > MAX_DAYS)' in JS, True)
for lang in ('en', 'br', 'es'):
    bloco = JS.split('        %s: {' % lang, 1)[-1].split('\n        }', 1)[0]
    check('%s tem os textos do intervalo por coluna' % lang,
          all(k in bloco for k in ('rangeTitle:', 'rangeField:', 'rangeHelp:',
                                   'rangeWill:', 'rangeDone:', 'rangeUndated:',
                                   'rangeEmpty:', 'rangeFailed:')), True)

# ── 1-3. o endpoint ──────────────────────────────────────────────────────────
print('\n== 1. o endpoint le os TRES bancos pela coluna escolhida ==')
from apps.pages import routes as R                                    # noqa: E402
from apps import create_app                                           # noqa: E402
from apps.config import DebugConfig                                   # noqa: E402

TMP = tempfile.mkdtemp(prefix='pc-range-')
R._PC_DB_DIR = TMP

app = create_app(DebugConfig)
cl = app.test_client()
with cl.session_transaction() as s:
    s['authenticated'] = True
    s['user_sid'] = 'T000000'
    s['user_name'] = 'T'
    s['user_role'] = 'ADMIN'
    s['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()


def linha(tn, trade, maturity, client='CLIENTE X', pending='Pending Original'):
    r = {c: '' for c in R._PC_COLUMNS}
    r.update({'Trade Number': tn, 'Trade Date': trade, 'Maturity Date': maturity,
              'Client': client, 'Pending Status': pending})
    return r


# Um banco por balde, com datas que separam os tres casos: dentro, fora e sem
# data. A `Trade Date` e a `Maturity Date` apontam para intervalos DIFERENTES de
# proposito — e o que prova que a coluna escolhida e a que manda.
R._pc_rewrite_db('pending', [
    linha('P1', '10/03/2026', '10/09/2026'),
    linha('P2', '20/03/2026', '20/12/2026'),
    linha('P3', '01/06/2026', '01/07/2026'),     # fora do intervalo de trade
])
R._pc_rewrite_db('ok', [
    linha('O1', '15/03/2026', '15/11/2026', pending='Concluded'),
    linha('O2', '', '05/09/2026', pending='Concluded'),   # sem Trade Date
])
R._pc_rewrite_db('backlog', [
    linha('B1', '05/03/2026', '05/10/2026'),
    # A MESMA operacao ainda no backlog e no pending (ate a manutencao das 11:30
    # reencaminhar): sem deduplicacao ela sairia duas vezes no arquivo.
    linha('P1', '10/03/2026', '10/09/2026'),
])


def rng(**kw):
    q = '&'.join('%s=%s' % (k, v) for k, v in kw.items())
    r = cl.get('/api/pending-confirmation/range?' + q)
    return r.status_code, (r.get_json() or {})


def tns(j):
    i = list(R._PC_COLUMNS).index('Trade Number')
    return sorted(row[i] for row in j.get('rows', []))


st, j = rng(**{'from': '2026-03-01', 'to': '2026-03-31', 'field': 'Trade Date'})
check('responde 200', st, 200)
check('varre os TRES bancos', tns(j), ['B1', 'O1', 'P1', 'P2'])
check('a coluna volta declarada', j.get('field'), 'Trade Date')
check('as colunas sao as do banco', j.get('columns'), list(R._PC_COLUMNS))

st, j = rng(**{'from': '2026-09-01', 'to': '2026-09-30', 'field': 'Maturity Date'})
check('a MESMA busca pela Maturity Date da outra resposta', tns(j), ['O2', 'P1'])

# As duas pontas entram: um intervalo que exclui a ponta perde o dia que a
# pessoa digitou, e ninguem confere um intervalo pelo que ele NAO trouxe.
st, j = rng(**{'from': '2026-03-10', 'to': '2026-03-15', 'field': 'Trade Date'})
check('as duas pontas sao inclusive', tns(j), ['O1', 'P1'])

# Uma ponta so vale como aquele dia — a mesma leitura do intervalo de
# arquivos-dia, para o campo nao querer dizer uma coisa em cada tela.
st, j = rng(**{'from': '2026-03-20', 'field': 'Trade Date'})
check('uma ponta so e aquele dia', tns(j), ['P2'])
st, j = rng(**{'to': '2026-03-05', 'field': 'Trade Date'})
check('a outra ponta so, idem', tns(j), ['B1'])

# Invertidas, o intervalo e o mesmo: recusar seria recusar uma digitacao que
# diz sem ambiguidade o que se quer.
st, j = rng(**{'from': '2026-03-31', 'to': '2026-03-01', 'field': 'Trade Date'})
check('pontas invertidas dao o mesmo intervalo', tns(j), ['B1', 'O1', 'P1', 'P2'])

# A ordem e a da data pedida: o arquivo sai como se le um intervalo.
st, j = rng(**{'from': '2026-01-01', 'to': '2026-12-31', 'field': 'Trade Date'})
check('sai ordenado pela data pedida', tns(j) == sorted(tns(j)) and
      [row[list(R._PC_COLUMNS).index('Trade Date')] for row in j['rows']] ==
      ['05/03/2026', '10/03/2026', '15/03/2026', '20/03/2026', '01/06/2026'], True)
check('a operacao repetida nos dois bancos sai UMA vez',
      tns(j).count('P1'), 1)

print('\n== 2. a linha sem a data pedida nao entra, e e contada ==')
st, j = rng(**{'from': '2026-01-01', 'to': '2026-12-31', 'field': 'Trade Date'})
check('a linha sem Trade Date fica de fora', 'O2' in tns(j), False)
check('   e e CONTADA', j.get('undated'), 1)
st, j = rng(**{'from': '2026-01-01', 'to': '2026-12-31', 'field': 'Maturity Date'})
check('pela Maturity Date nenhuma esta sem data', j.get('undated'), 0)

print('\n== 3. a lista branca e a leitura estrita ==')
st, j = rng(**{'from': '2026-03-01', 'to': '2026-03-31', 'field': 'Client'})
check('coluna que nao e data e recusada', st, 400)
check('   dizendo qual', 'Client' in str(j.get('message', '')), True)
st, j = rng(**{'from': '2026-03-01', 'to': '2026-03-31', 'field': 'Trade Date; DROP'})
check('nome inventado tambem', st, 400)
st, j = rng(**{'field': 'Trade Date'})
check('sem data nenhuma e recusado', st, 400)

# Banco ILEGIVEL nao pode virar planilha curta: ela e indistinguivel de um
# intervalo sem movimento e vai assinada por quem a mandou.
with io.open(os.path.join(TMP, 'pending-confirmation-pending.db'), 'wb') as fh:
    fh.write(b'nao sou um duckdb')
st, j = rng(**{'from': '2026-03-01', 'to': '2026-03-31', 'field': 'Trade Date'})
check('banco ilegivel NAO devolve 200 com o que sobrou', st != 200, True)
check('   e a resposta diz o motivo',
      bool(str(j.get('message', '') or j.get('error', '') or '')), True)

shutil.rmtree(TMP, ignore_errors=True)

print('\nTUDO OK' if not fails else '\n%d FALHA(S): %s' % (len(fails), ', '.join(fails)))
sys.exit(1 if fails else 0)
