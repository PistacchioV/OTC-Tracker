# -*- coding: utf-8 -*-
"""Regressão da página Intrag › DCE › NDF.

A diferença que define esta página: o extrato de termo **NÃO é um relatório, são
CINCO** — um por portfólio/carteira (LN FX Flow, Client FX, CETE, GC ONS BJPM,
GC ONS Lawton), em hosts diferentes —, e o Import passa por todos numa clicada.
Daí para a frente o ciclo é o das irmãs: editar (Pending) → aprovar (Approved,
maker ≠ checker) → mapear (Success) → enviar.

O que este script prende:

1. o PARSER casa coluna por NOME normalizado (`TYPE (FORM)` → `TYPE FORM`) e
   devolve as 30 chaves do extrato; coluna desconhecida sai em `unknown`, nunca
   descartada em silêncio;
2. o Import percorre TODOS os endereços e **um relatório que falha não derruba
   os outros** — as cinco carteiras moram em hosts diferentes, e um host fora do
   ar não pode fazer as outras quatro deixarem de entrar. O que falhou volta em
   `failed`, com o motivo; se NENHUM responder, aí sim é erro;
3. as linhas vão para o arquivo-dia do PRÓPRIO Trade Date e o RE-IMPORT preserva
   a esteira (status/maker/checker/intrag_id): importar de novo não desfaz
   validação nem mapeamento;
4. os endereços saem do cadastro `api-links` (`Intrag DCE` × NDF) com a data no
   CAMINHO; sem cadastro caem nas cinco carteiras do fallback — nunca em erro,
   nunca numa carteira só;
5. o contrato com a TELA: 30 colunas no cabeçalho, 30 rótulos e 30 chaves no JS
   na MESMA ordem do `_DCE_NDF_FIELDS`, e os índices da tabela conferindo. Ordem
   trocada aqui desloca a linha inteira sem erro nenhum;
6. o mapping usa o critério do TERMO (`NDF - TERMO`), não o da opção que veio do
   molde: herdar `OPCAO` faria a tela dizer "nenhum Intrag ID" para um CSV que
   tem todos eles.

Roda em tmp: o cache da página aponta para um diretório temporário e o download
é stubado — nada de rede, nada de dado real.
"""
import io
import os
import re
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')
if os.name != 'nt' and not os.environ.get('OTC_SHARED_DRIVE_ROOT'):
    os.environ['OTC_SHARED_DRIVE_ROOT'] = tempfile.mkdtemp(prefix='otc-share-')

FALHAS = []


def check(nome, obtido, esperado=True):
    ok = obtido == esperado
    print(('  ok  ' if ok else ' FAIL ') + nome +
          ('' if ok else '\n        got=%r\n        exp=%r' % (obtido, esperado)))
    if not ok:
        FALHAS.append(nome)


from apps import create_app                                            # noqa: E402
from apps.config import DebugConfig                                    # noqa: E402
app = create_app(DebugConfig)

from apps.pages import athena_api                                      # noqa: E402
from apps.pages.features.intrag import commands, domain, queries       # noqa: E402
from apps.pages.features.intrag.infra import persistence               # noqa: E402

# O cabeçalho REAL do bob-report, colado do extrato.
CAB = ('NDF CONTRACT TYPE;TRADE ID;PORTFOLIO CODE;PARTICIPANT POSITION;CLIENT CPF/CNPJ;'
       'COUNTERPARTY;COUNTERPARTY CPF/CNPJ;COUNTERPARTY COLLATERAL BASKET;'
       'PARTY COLLATERAL BASKET;NOTIONAL;START DATE;TRADE DATE;MATURITY DATE;'
       'REFERENCE CURRENCY;REFERENCE EXCHANGE;COMMODITY;TYPE (FORM);QUANTITY;TRADING UNIT;'
       'TRANSACTION PRICE;QUOTED CURRENCY;MATURITY MONTH AND YEAR;QUOTE FOR ADJUSTMENT;'
       'FORWARD RATE;ASIAN NDF AVERAGE RATE;INFORMATION SOURCE;FIXING;ADJUSTMENT TYPE;'
       'REMARKS;LIMITS')


def linha(tid, td='2026-08-11'):
    return ('NDF - TERMO DE MOEDAS;{};GCIN;COMPRADOR;;JPM;;NAO;NAO;11000000;{};{};2026-08-14;'
            'BRL;N/A;N/A;N/A;N/A;N/A;N/A;N/A;N/A;N/A;3.5;N/A;BCB;PTAX;D-1;N/A;N/A'
            ).format(tid, td, td)


print('== 1. o parser ==')
rows, unknown = domain._dce_ndf_parse_report(CAB + '\n' + linha('NB-A'))
check('o cabecalho real do extrato nao tem coluna desconhecida', unknown, [])
check('uma linha por operacao', len(rows), 1)
check('as 30 chaves do extrato', len(rows[0]), 30)
check('`TYPE (FORM)` normaliza para TYPE FORM e casa', 'type_form' in rows[0])
check('e o dado cai na coluna certa',
      (rows[0]['ndf_contract_type'], rows[0]['trade_id'], rows[0]['portfolio_code'],
       rows[0]['participant_position'], rows[0]['forward_rate'], rows[0]['fixing']),
      ('NDF - TERMO DE MOEDAS', 'NB-A', 'GCIN', 'COMPRADOR', '3.5', 'PTAX'))
# Coluna que o mapa nao conhece AVISA em vez de sumir: e o que faz um extrato
# novo aparecer na tela como pergunta, e nao como coluna vazia.
_r, _u = domain._dce_ndf_parse_report(CAB + ';COLUNA NOVA\n' + linha('NB-B') + ';x')
check('coluna fora do mapa volta em unknown', _u, ['COLUNA NOVA'])

print('\n== 2. os CINCO enderecos ==')
with app.test_request_context():
    import datetime
    urls = commands._dce_ndf_urls(datetime.datetime(2026, 9, 15))
check('sao cinco carteiras, nao uma', len(urls), 5)
check('a data entra no CAMINHO, nao em query string',
      all('/2026-09-15/' in u and '?' not in u for u in urls))
check('   e cada carteira tem o seu endereco', len(set(urls)), 5)
check('todos apontam para o extrator de NDF',
      all(u.endswith('ITAUDataExtractor_NDF') for u in urls))
# O fallback existe para a instalacao cujo `api-links.json` ja existe: o `seed`
# so escreve arquivo NOVO (§6) e o `upgrade` nao alcanca o `_api_link_rows`.
_reais = athena_api.registered_links
try:
    athena_api.registered_links = lambda *a, **k: []
    with app.test_request_context():
        check('sem cadastro, o fallback traz as CINCO — nunca zero, nunca uma',
              len(commands._dce_ndf_urls(datetime.datetime(2026, 9, 15))), 5)
finally:
    athena_api.registered_links = _reais


print('\n== 3. o import dos cinco, com um host fora do ar ==')


class _Resp(object):
    def __init__(self, texto):
        self.content = texto.encode('utf-8')

    def raise_for_status(self):
        pass


class _Sessao(object):
    """Cada carteira devolve um deal; a 3a esta fora do ar."""

    def __init__(self, morrer=(3,)):
        self.pedidos, self.morrer = [], morrer

    def get(self, url, timeout=None):
        self.pedidos.append(url)
        if len(self.pedidos) in self.morrer:
            raise IOError('connection refused')
        return _Resp(CAB + '\n' + linha('NB-CART%d' % len(self.pedidos)))


tmp = tempfile.mkdtemp(prefix='dce-ndf-test-')
_dir_real, _sessao_real = persistence.INTRAG_DCE_NDF_CACHE_DIR, athena_api.build_session
try:
    persistence.INTRAG_DCE_NDF_CACHE_DIR = os.path.join(tmp, 'DCE NDF')
    sess = _Sessao()
    athena_api.build_session = lambda *a, **k: sess
    with app.test_request_context():
        r = commands._dce_ndf_import(ref_date='2026-09-15', sid='E1', actor_name='Teste')
    check('passou pelos cinco enderecos', len(sess.pedidos), 5)
    check('quatro responderam', r['reports_read'], 4)
    check('o host fora do ar volta em `failed`, com o motivo',
          (len(r['failed']), 'refused' in r['failed'][0]['error']), (1, True))
    check('   e NAO derruba as outras quatro', r['imported'], 4)
    check('as linhas foram para o arquivo-dia do Trade Date, nao o do extrato',
          (r['files'], r['date_min'], r['date_max']), (1, '2026-08-11', '2026-08-11'))

    # Re-import: a esteira e o mapeamento sobrevivem.
    from apps.pages import routes as R
    with app.test_request_context():
        fp, entries, idx = queries._find_intrag_dce_ndf_entry('NB-CART4', '2026-08-11')
        entries[idx]['status'] = 'Approved'
        entries[idx]['maker'], entries[idx]['checker'] = 'E1', 'E2'
        entries[idx]['intrag_id'] = 'ITG-9'
        R._atomic_write_json(fp, entries)
        athena_api.build_session = lambda *a, **k: _Sessao(morrer=())
        commands._dce_ndf_import(ref_date='2026-09-15')
        fp, entries, idx = queries._find_intrag_dce_ndf_entry('NB-CART4', '2026-08-11')
    e = entries[idx]
    check('re-import preserva status, maker, checker e Intrag ID',
          (e['status'], e['maker'], e['checker'], e['intrag_id']),
          ('Approved', 'E1', 'E2', 'ITG-9'))

    # Nenhum relatorio respondendo e ERRO, nunca um import vazio de sucesso.
    athena_api.build_session = lambda *a, **k: _Sessao(morrer=(1, 2, 3, 4, 5))
    erro = ''
    try:
        with app.test_request_context():
            commands._dce_ndf_import(ref_date='2026-09-15')
    except Exception as exc:                                   # noqa: BLE001
        erro = str(exc)
    check('nenhum relatorio respondendo e ERRO, nao sucesso vazio',
          'none of the' in erro)
finally:
    persistence.INTRAG_DCE_NDF_CACHE_DIR = _dir_real
    athena_api.build_session = _sessao_real
    shutil.rmtree(tmp, ignore_errors=True)


print('\n== 4. o contrato com a tela ==')
HTML = io.open('apps/templates/pages/intrag-dce-ndf.html', encoding='utf-8').read()
cols = re.findall(r"var DCE_COLS = \[(.*?)\];", HTML, re.S)[0]
keys = re.findall(r"var DCE_ENTRY_FIELDS = \[(.*?)\];", HTML, re.S)[0]
cols = re.findall(r"'([^']+)'", cols)
keys = re.findall(r"'([^']+)'", keys)
check('30 rotulos e 30 chaves no JS', (len(cols), len(keys)), (30, 30))
check('as chaves do JS sao as do servidor, na MESMA ordem',
      tuple(keys), domain._DCE_NDF_FIELDS)
check('30 colunas de dado no cabecalho',
      len(set(re.findall(r'<th data-lang="intrag-dce-ndf-col-(\d+)">', HTML))), 30)
check('e a linha de filtro tem uma por coluna (+ Status e Intrag ID)',
      HTML.count('bg-light-subtle border-light'), 32)
check('os indices da tabela acompanham as 30 colunas (4 fixas + 30)',
      (re.search(r'DCE_ID_COL = (\d+)', HTML).group(1),
       re.search(r'DCE_DATA_END = (\d+)', HTML).group(1)), ('34', '34'))
# Datas: Start, Trade e Maturity. No molde da Option elas ficavam em outros
# indices — herda-los aqui poria o flatpickr em campo de texto e deixaria as
# datas sem ele, sem erro nenhum.
check('os tres campos de data do modal sao Start/Trade/Maturity',
      re.search(r'var DATE_FIELDS = \[([^\]]*)\]', HTML).group(1).replace(' ', ''),
      "'dce-f-10','dce-f-11','dce-f-12'")
check('a pagina fala com as rotas dela, nao com as da Option',
      ('/api/intrag/dce-ndf' in HTML, 'dce-option' in HTML), (True, False))
check('o Delete aponta para a familia dce-ndf',
      ("otcIntragDelete('dce-ndf'" in HTML, "otcIntragDelete('dce-opt'" in HTML), (True, False))
check('o menu de Export esta COMPLETO (o molde tinha meio menu)',
      all(("extend:'" + b) in HTML for b in ('copy', 'csv', 'excel', 'print', 'pdf')))

# ── o FILTRO INTELIGENTE ────────────────────────────────────────────────────
# Duas coisas vinham do molde e nao se percebia na tela, so no resultado vazio:
#
# 1. o mapa de TIPOS era o da Option ('Strike Price', 'Fixing Date', 'Premium'…)
#    e nenhum daqueles rotulos existe aqui, entao TODA coluna caia em 'text' e o
#    filtro perdia datas e numeros;
# 2. a coluna que COMANDA o fetch era `SF_COLS[3]` — na Option o Trade Date e a
#    4a coluna; aqui a 4a e Participant Position. O chip de data (inclusive o
#    padrao de hoje, que ABRE a tela) filtrava a coluna errada.
#
# Por isso ela e achada pelo RÓTULO (`isDate`), nunca por indice fixo.
TIPOS = dict(re.findall(r"'([^']+)':'(\w+)'", re.search(r'var DCE_TYPES = \{(.*?)\};', HTML, re.S).group(1)))
check('os tipos do filtro sao os ROTULOS do NDF, nao os da Option',
      (sorted(k for k, t in TIPOS.items() if t == 'date'),
       sorted(k for k, t in TIPOS.items() if t == 'number')),
      (['Maturity Date', 'Start Date', 'Trade Date'],
       ['Asian NDF Average Rate', 'Forward Rate', 'Notional', 'Quantity', 'Transaction Price']))
check('   e todo rotulo tipado EXISTE entre as colunas',
      sorted(set(TIPOS) - set(cols)), [])
check('a coluna que comanda o fetch e achada pelo rotulo, nunca por indice fixo',
      ('var SF_TRADE_DATE = SF_COLS.filter(function(c){return c.isDate;})[0]' in HTML,
       'SF_COLS[3]' in HTML), (True, False))
check('   e o rotulo marcado como isDate e o Trade Date',
      "if(lbl==='Trade Date') c.isDate=true;" in HTML)
# O indice herdado apontava para ca — a asserção existe para dizer POR QUE o
# `SF_COLS[3]` não serve, e não só que ele saiu.
check('   (a 4a coluna do NDF e Participant Position, nao Trade Date)',
      (cols[3], cols[11]), ('Participant Position', 'Trade Date'))

print('\n== 5. as rotas e o resto do wiring ==')
regras = {str(r) for r in app.url_map.iter_rules()}
for rota in ('/api/intrag/dce-ndf', '/api/intrag/dce-ndf/import-api',
             '/api/intrag/dce-ndf/send-file', '/api/intrag/dce-ndf/edit',
             '/api/intrag/dce-ndf/approve', '/api/intrag/dce-ndf/mapping-intrag-id'):
    check('rota %s' % rota, rota in regras)
check('a familia do Delete conhece a pagina',
      'dce-ndf' in commands._INTRAG_DELETE_FAMILIES)
# O send agrupa por Trade Date, que no NDF e a 12a coluna de dado (no Option e a
# 4a). Indice errado escreve o dia errado no nome do arquivo e no caminho.
ENT = io.open('apps/pages/features/intrag/entrypoint.py', encoding='utf-8').read()
bloco = ENT[ENT.index('def api_intrag_dce_ndf_send_file'):]
bloco = bloco[:bloco.index('@blueprint.route', 10)]
check('o send agrupa pelo Trade Date do NDF (indice 11)',
      'TRADE_DATE_IDX = 11' in bloco)
check('   e escreve o arquivo com o nome da pagina',
      "'Intrag-DCE-NDF-'" in bloco)
check('o mapping usa o criterio do TERMO, nao o da opcao que veio do molde',
      ("'NDF - TERMO'" in ENT[ENT.index('def api_intrag_dce_ndf_mapping_intrag_id'):][:900]))

print()
print(('FALHAS: %d' % len(FALHAS)) if FALHAS else 'TUDO OK')
sys.exit(1 if FALHAS else 0)
