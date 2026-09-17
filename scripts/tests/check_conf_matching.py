#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Conf. Matching — FepWeb × Athena (a tradução do workflow Alteryx homônimo).

O que este teste protege é o que erra em SILÊNCIO quando quebra:

1. **O lado FepWeb**: cabeçalho achado por NOME (mesmo com título acima), fora
   o `Cancelado`, só o trade date pedido, e o contrato repetido vira UMA linha
   `Duplicated` — não duas operações casadas.
2. **O lado Athena**: fora o `isCancelled`, fora as pernas internas (book com
   `NDF` no nome, interbook, accronym de entidade, ECONOMIC GROUP INTERNAL) e
   fora o que veio com outro Trade Date — tudo por cadastro, nada por lista.
3. **A chave do batimento** é cega a caixa e a `_` × `-`.
4. **Cliente por CHAVE**: CPF/CNPJ (a planilha entrega NÚMERO, sem o zero à
   esquerda) e SPN, os dois contra o Reference Data.
5. **A assinatura é a regra da casa** (`_pc_signature_pending_status`): prazo
   curto e `Internal` → `Ok`; Digital/Manual → `Pending`; Forward Start →
   `Manual Confirmation`.
6. **Sem um dos lados o Run FALHA com o motivo** — rodar só com a Athena
   pintaria o dia inteiro de `Missing FepWeb`.
7. **O comentário é do TRADE**: sobrevive a um novo Run e aparece no cache que
   já estava gravado.
8. **A leitura do box** escolhe o e-mail que COBRE a data (o relatório é uma
   janela de dias) e, sem nenhum, cai no mais recente avisando — e a Recon de
   CGD, que usa a mesma função, continua pegando o mais recente.
9. **As rotas** existem, exigem sessão e o Run devolve `tipo: mensagem`.

Não toca em rede, Outlook nem dado real: tudo sintético, num tmp.
"""

import os
import shutil
import sys
import tempfile
import types
from datetime import date, datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

TMP = tempfile.mkdtemp(prefix='conf-matching-')
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', os.path.join(TMP, 'share'))
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'
os.environ['CONFMATCH_INPUT_ROOT'] = os.path.join(TMP, 'input')

from apps.pages import routes as R                               # noqa: E402
from apps.pages import recon_cgd as CGD                          # noqa: E402
from apps.pages import recon_conf_matching as M                  # noqa: E402

# Cache e comentários vão para o tmp: o teste não escreve no dado real.
M._CACHE_DIR = os.path.join(TMP, 'cache')
M._COMMENTS_PATH = os.path.join(TMP, 'comments.json')

falhas = []


def check(label, got, exp):
    ok = got == exp
    print(('ok   ' if ok else 'FAIL ') + label + '  ->  ' + repr(got))
    if not ok:
        falhas.append('%s: %r != %r' % (label, got, exp))


REF = date(2026, 9, 16)                     # quarta-feira
LONGO = REF + timedelta(days=120)           # prazo > 60 dias: vale a assinatura
CURTO = REF + timedelta(days=30)            # prazo ≤ 60 dias: Exception FepWeb

# ── Reference Data de mentira ────────────────────────────────────────────────
REFDATA = [
    {'SPN': '1001', 'COUNTERPARTY': 'DIGITAL SA', 'TAX ID': '01.234.567/0001-88',
     'SIGNATURE TYPE': 'Digital', 'ECONOMIC GROUP': 'DIGITAL'},
    {'SPN': '1002', 'COUNTERPARTY': 'INTERNAL SIGN LTDA', 'TAX ID': '22.222.222/0001-22',
     'SIGNATURE TYPE': 'Internal', 'ECONOMIC GROUP': 'ISIGN'},
    {'SPN': '1003', 'COUNTERPARTY': 'MANUAL SA', 'TAX ID': '33.333.333/0001-33',
     'SIGNATURE TYPE': 'Manual', 'ECONOMIC GROUP': 'MANUAL'},
    {'SPN': '9999', 'COUNTERPARTY': 'BANCO J.P. MORGAN S.A.', 'TAX ID': '99.999.999/0001-99',
     'SIGNATURE TYPE': '', 'ECONOMIC GROUP': 'INTERNAL'},
]
R._refdata_records = lambda: REFDATA
R._fxo_refdata_by_spn = lambda: {R._norm_spn(r['SPN']): r for r in REFDATA}
R._ndf_is_interbook = lambda norm: norm.get('OTHER BOOK') == 'INTERBOOK'
R._ndf_le_from_accronym = lambda acr: 'JPM' if acr == 'BANCJPBR' else None
R._pc_is_internal_counterparty = lambda client, spn='': (
    (R._fxo_refdata_by_spn().get(R._norm_spn(spn)) or {}).get('ECONOMIC GROUP') == 'INTERNAL')


def ath(deal, end_cp, spn, settle=LONGO, trade=REF, instr='Cash Settled Forward', **extra):
    rec = {'Deal Name': deal, 'End Counterparty': end_cp, 'Cetip ID': 'C-' + deal,
           'End Counterparty Description': end_cp + ' DESC', 'Trade Date': trade.strftime('%Y-%m-%d'),
           'Settlement Date': settle.strftime('%Y-%m-%d'), 'SPN': spn, 'Instrument Type': instr,
           'Other Quantity': -5158000.75, 'Other Quantity Units': 'BRL',
           'Quantity Currency': 'USD', 'Quantity': 1000000, 'Publisher': 'PTAX',
           'Strike': 5.158}
    rec.update(extra)
    return rec


ATHENA = [
    ath('D1', 'DIGITALBR', '1001'),
    ath('D2', 'ISIGNBR', '1002'),
    ath('D3', 'MANUALBR', '1003', settle=CURTO),
    ath('D4', 'MANUALBR', '1003'),                                  # só na Athena
    ath('D5', 'DIGITALBR', '1001', isCancelled=True),               # cancelada
    ath('D6', 'BR ON - LN LAWTON NDF', ''),                         # book
    ath('D7', 'JPMBR', '9999'),                                     # ECONOMIC GROUP INTERNAL
    ath('D8', 'DIGITALBR', '1001', instr='FX Forward Start'),       # manual
    ath('D9', 'DIGITALBR', '1001', trade=REF - timedelta(days=1)),  # outro trade date
    ath('D_10', 'SEMCADBR', '7777'),                                # `_` × `-`, sem cadastro
    ath('D11', 'BANCJPBR', '1001'),                                 # accronym de entidade
    ath('D12', 'DIGITALBR', '1001', **{'Other Book': 'INTERBOOK'}), # interbook
    ath('D1', 'DIGITALBR', '1001'),                                 # a API repete o trade
]


def fep_xlsx(path):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(['FEPWeb - Operações D-4'])                           # título acima do cabeçalho
    ws.append([])
    ws.append(['Nome Cliente', 'CPF/CNPJ Cliente', 'Contrato', 'Tipo Operação',
               'Data Operação', 'Status Operação'])
    dia = datetime(REF.year, REF.month, REF.day)
    ws.append(['Digital (nome do FepWeb)', 1234567000188, 'D1', 'NDF', dia, 'Ativo'])
    ws.append(['Internal Sign', '22.222.222/0001-22', 'D2', 'NDF', dia, 'Ativo'])
    ws.append(['Manual', '33333333000133', 'D3', 'NDF', dia, 'Ativo'])
    ws.append(['Só FepWeb', '33333333000133', 'F1', 'NDF', REF.strftime('%d/%m/%Y'), 'Ativo'])
    ws.append(['Dup', 1234567000188, 'DUP', 'NDF', dia, 'Ativo'])
    ws.append(['Dup', 1234567000188, 'DUP', 'NDF', dia, 'Ativo'])
    ws.append(['Cancelada', 1234567000188, 'X1', 'NDF', dia, 'Cancelado'])
    ws.append(['Outro dia', 1234567000188, 'Y1', 'NDF', dia - timedelta(days=1), 'Ativo'])
    ws.append(['Fwd', 1234567000188, 'D8', 'NDF', dia, 'Ativo'])
    ws.append(['Sem cadastro', '55.555.555/0001-55', 'd-10', 'NDF', dia, 'Ativo'])
    wb.save(path)
    return path


FEP = fep_xlsx(os.path.join(TMP, 'fep.xlsx'))

try:
    print('=== 1. O batimento ===')
    res = M.executar(REF, fep_path=FEP, athena_records=ATHENA)
    por = {r['key']: r for r in res['rows']}
    check('as chaves do dia', sorted(por), ['D-10', 'D1', 'D2', 'D3', 'D4', 'D8', 'DUP', 'F1'])
    check('columns é o contrato do Advanced Export', res['columns'], list(M.COLUMNS))
    check('toda linha tem todas as colunas',
          [k for k, r in por.items() if any(c not in r for c in M.COLUMNS)], [])

    check('D1 digital, prazo longo', (por['D1']['Status'], por['D1']['Pending Status']),
          ('Pending', 'Pending Digital Signature'))
    check('D2 Internal não cobra assinatura', (por['D2']['Status'], por['D2']['Pending Status']),
          ('Ok', 'Exception Digital Fep Web'))
    check('D3 prazo curto', (por['D3']['Status'], por['D3']['Pending Status']),
          ('Ok', 'Exception FepWeb'))
    check('D4 só na Athena', por['D4']['Status'], 'Missing FepWeb')
    check('D4 ainda diz a assinatura', por['D4']['Pending Status'], 'Pending Original')
    check('F1 só no FepWeb', (por['F1']['Status'], por['F1']['Pending Status']), ('Missing Athena', ''))
    check('DUP é UMA linha', (por['DUP']['Status'], por['DUP']['FepWeb Count']), ('Duplicated', 2))
    check('D8 Forward Start', (por['D8']['Status'], por['D8']['Pending Status']),
          ('Manual Confirmation', M.PS_MANUAL))
    check('D_10 × d-10 casam', (por['D-10']['FepWeb ID'], por['D-10']['Athena ID'], por['D-10']['Status']),
          ('D-10', 'D-10', 'Pending'))

    print('=== 2. Cliente por chave ===')
    check('CNPJ numérico sem o zero acha o cadastro', por['D1']['FepWeb Client'], 'DIGITAL SA')
    check('SPN acha o cadastro', por['D1']['Athena Client'], 'DIGITAL SA')
    check('CNPJ sai mascarado do cadastro', por['D1']['CNPJ'], '01.234.567/0001-88')
    check('sem cadastro: o nome que veio da fonte',
          (por['D-10']['FepWeb Client'], por['D-10']['Athena Client']),
          ('Sem cadastro', 'SEMCADBR DESC'))
    check('sem cadastro AVISA', any('Sem cadastro no Reference Data' in w for w in res['warnings']), True)
    check('números crus (a tela formata)', (por['D1']['Quantity'], por['D1']['Strike'], por['D1']['Tenor']),
          (1000000.0, 5.158, 120))

    print('=== 3. Cortes ===')
    check('FepWeb', res['fep_info'], {'lidas': 10, 'canceladas': 1, 'outras_datas': 1})
    check('Athena', res['athena_info'],
          {'lidas': 13, 'canceladas': 1, 'internas': 4, 'outras_datas': 1})
    check('outro Trade Date AVISA', any('Trade Date diferente' in w for w in res['warnings']), True)
    check('counts', res['counts'], {'missing_fepweb': 1, 'missing_athena': 1, 'duplicated': 1,
                                    'manual': 1, 'pending': 2, 'ok': 2})
    check('a ordem é a da gravidade', [r['Status'] for r in res['rows']],
          ['Missing FepWeb', 'Missing Athena', 'Duplicated', 'Manual Confirmation',
           'Pending', 'Pending', 'Ok', 'Ok'])

    print('=== 4. Sem um dos lados o Run falha com o motivo ===')
    try:
        M.executar(REF, fep_path=os.path.join(TMP, 'nao-existe.xlsx'), athena_records=ATHENA)
        check('FepWeb ausente levanta', False, True)
    except RuntimeError as e:
        check('FepWeb ausente levanta', 'não encontrado' in str(e), True)

    def _api_fora(ref):
        raise ConnectionError('SSO recusado')
    _orig_busca = M.buscar_athena
    M.buscar_athena = _api_fora
    try:
        M.executar(REF, fep_path=FEP)
        check('Athena fora levanta', False, True)
    except ConnectionError as e:
        check('Athena fora levanta', str(e), 'SSO recusado')
    finally:
        M.buscar_athena = _orig_busca

    from openpyxl import Workbook
    ruim = os.path.join(TMP, 'ruim.xlsx')
    wb = Workbook(); wb.active.append(['Cliente', 'Valor']); wb.save(ruim)
    try:
        M.executar(REF, fep_path=ruim, athena_records=ATHENA)
        check('planilha sem as colunas levanta', False, True)
    except RuntimeError as e:
        check('planilha sem as colunas levanta', '"Contrato"' in str(e), True)

    print('=== 5. Cache e comentário ===')
    M.salvar(res)
    lido = M.carregar(REF.strftime('%Y-%m-%d'))
    check('o cache lê o que gravou', [r['key'] for r in lido['rows']], [r['key'] for r in res['rows']])
    check('dia que ninguém rodou é None', M.carregar('2020-01-02'), None)
    check('sem data, grava e lê no MESMO dia (D-1)',
          M._cache_path(None), M._cache_path(CGD.dia_util_anterior().strftime('%Y-%m-%d')))

    check('save devolve o texto gravado', M.save_comment(' d4 ', '  em contato com o cliente  '),
          'em contato com o cliente')
    lido = {r['key']: r for r in M.carregar(REF.strftime('%Y-%m-%d'))['rows']}
    check('o comentário aparece no cache JÁ gravado', lido['D4']['Comments'], 'em contato com o cliente')
    de_novo = {r['key']: r for r in M.executar(REF, fep_path=FEP, athena_records=ATHENA)['rows']}
    check('e sobrevive a um novo Run', de_novo['D4']['Comments'], 'em contato com o cliente')
    check('comentar não muda o Status', de_novo['D4']['Status'], 'Missing FepWeb')
    M.save_comment('D4', '')
    check('vazio apaga', M.load_comments(), {})
    try:
        M.save_comment('', 'x')
        check('sem chave recusa', False, True)
    except ValueError:
        check('sem chave recusa', True, True)

    print('=== 5b. No app a gravação vai para o ARMAZÉM, não para o disco (§434) ===')
    _raiz, _cache, _com = R._B3_DATA_DIR, M._CACHE_DIR, M._COMMENTS_PATH
    ARM = os.path.join(TMP, 'armazem')
    os.makedirs(ARM)
    R._B3_DATA_DIR = ARM
    M._CACHE_DIR = os.path.join(ARM, 'cache', 'reconciliation', 'conf-matching')
    M._COMMENTS_PATH = os.path.join(ARM, 'recon-conf-matching-comments.json')
    try:
        p = M.salvar(res)
        M.save_comment('F1', 'ç no banco')
        check('nenhum JSON no disco', (os.path.exists(p), os.path.exists(M._COMMENTS_PATH)), (False, False))
        check('o banco da recon nasceu', os.path.isfile(
            os.path.join(ARM, 'db', 'cache', 'reconciliation', 'conf-matching.db')), True)
        volta = M.carregar(REF.strftime('%Y-%m-%d'))
        check('o payload-objeto volta EXATO', {**volta, 'rows': None}, {**res, 'rows': None})
        check('e o comentário vem do banco dele',
              {r['key']: r['Comments'] for r in volta['rows']}['F1'], 'ç no banco')
    finally:
        R._B3_DATA_DIR, M._CACHE_DIR, M._COMMENTS_PATH = _raiz, _cache, _com

    print('=== 6. A leitura do box ===')

    class _Col(list):
        @property
        def Count(self):
            return len(self)

        def Item(self, i):
            return self[i - 1]

        def __getitem__(self, k):
            if isinstance(k, str):
                return next(f for f in self if f.Name == k)
            return list.__getitem__(self, k)

    class _Att:
        def __init__(self, nome):
            self.FileName = nome

        def SaveAsFile(self, alvo):
            with open(alvo, 'wb') as fh:
                fh.write(self.FileName.encode('utf-8'))

    class _Msg:
        def __init__(self, assunto, recebido, anexos):
            self.Subject, self.ReceivedTime = assunto, recebido
            self.Attachments = _Col(_Att(a) for a in anexos)

    class _Items(_Col):
        def Restrict(self, q):
            raise RuntimeError('caixa que recusa o pré-filtro')

        def Sort(self, campo, desc):
            self.sort(key=lambda m: m.ReceivedTime, reverse=bool(desc))

    class _Folder:
        def __init__(self, nome, subs=(), itens=()):
            self.Name, self.Folders, self.Items = nome, _Col(subs), _Items(itens)

    OPS = '(REPORT) FEPWeb - Operacoes D-4'
    itens = [
        _Msg('RES: ' + OPS, datetime(2026, 9, 10, 7, 0), ['ops-0910.xlsx']),
        _Msg(OPS, datetime(2026, 9, 17, 7, 0), ['logo.png', 'ops-0917.xlsx']),
        _Msg(OPS, datetime(2026, 9, 3, 7, 0), ['ops-0903.xlsx']),
        _Msg('FEPWEB-CGD-ContratoGlobalDerivativos - SEM FILTRO DATAS',
             datetime(2026, 9, 17, 8, 0), ['cgd-0917.xlsx']),
        _Msg('Outra rotina', datetime(2026, 9, 17, 9, 0), ['outra.xlsx']),
    ]
    caixa = _Folder(CGD.FEP_MAILBOX, [_Folder('Inbox', [_Folder('automatico ', itens=itens)])])

    class _NS:
        Folders = _Col([caixa])

    w32 = types.ModuleType('win32com')
    w32c = types.ModuleType('win32com.client')
    w32c.Dispatch = lambda nome: types.SimpleNamespace(GetNamespace=lambda n: _NS())
    w32.client = w32c
    pyc = types.ModuleType('pythoncom')
    pyc.CoInitialize = pyc.CoUninitialize = lambda: None
    sys.modules.update({'win32com': w32, 'win32com.client': w32c, 'pythoncom': pyc})

    def baixa(ref):
        av = []
        p, desc = CGD.baixar_fep_do_box(av, assunto=M.FEP_MAIL_SUBJECT, prefixo='t-ops-',
                                        aceita=M._aceita_email(ref))
        return os.path.basename(p or ''), av

    check('D-1: o e-mail de hoje', baixa(date(2026, 9, 16)), ('t-ops-ops-0917.xlsx', []))
    check('data antiga: o e-mail que a COBRE', baixa(date(2026, 9, 8))[0], 't-ops-ops-0910.xlsx')
    nome, av = baixa(date(2026, 7, 1))
    check('nenhum cobre: o mais recente, AVISANDO', (nome, len(av)), ('t-ops-ops-0917.xlsx', 1))
    av = []
    p, desc = CGD.baixar_fep_do_box(av)
    check('a CGD segue lendo o relatório DELA', (os.path.basename(p), av), ('fepweb-cgd-cgd-0917.xlsx', []))
    check('e a descrição diz o e-mail lido', '17/09/2026 08:00' in desc, True)
    for m in ('win32com', 'win32com.client', 'pythoncom'):
        sys.modules.pop(m, None)

    print('=== 7. As rotas ===')
    from apps import create_app
    from apps.config import DebugConfig
    app = create_app(DebugConfig)
    regras = {str(r) for r in app.url_map.iter_rules()}
    for rota in ('/reconciliation-conf-matching', '/api/reconciliation-conf-matching/data',
                 '/reconciliation-conf-matching/run', '/reconciliation-conf-matching/comment'):
        check(rota + ' registrada', rota in regras, True)

    def cliente(auth=True):
        c = app.test_client()
        if auth:
            with c.session_transaction() as s:
                s['authenticated'] = True
                s['user_sid'] = 'A111111'
                s['user_name'] = 'Alice Souza'
                s['user_role'] = 'BO'
                s['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()
        return c

    c, anon = cliente(), cliente(auth=False)
    check('API sem sessão é 401', anon.get('/api/reconciliation-conf-matching/data').status_code, 401)
    j = c.get('/api/reconciliation-conf-matching/data?recon_date=2020-01-02').get_json()
    check('dia sem Run abre VAZIO, dizendo o dia', (j['empty'], j['ref_fmt'], j['rows']), (True, '02/01/2020', []))
    j = c.get('/api/reconciliation-conf-matching/data?recon_date=' + REF.strftime('%Y-%m-%d')).get_json()
    check('dia rodado devolve as linhas e as colunas', (len(j['rows']), j['columns'][0]), (8, 'Status'))

    M.executar_orig = M.executar
    M.executar = lambda ref=None: M.executar_orig(ref, fep_path=FEP, athena_records=ATHENA)
    j = c.post('/reconciliation-conf-matching/run', json={'recon_date': '16/09/2026'}).get_json()
    check('Run aceita dd/mm/aaaa', (j['success'], j['ref']), (True, '2026-09-16'))

    def _quebra(ref=None):
        raise ConnectionError('SSO recusado')
    M.executar = _quebra
    r = c.post('/reconciliation-conf-matching/run', json={})
    check('Run que falha diz tipo: mensagem', (r.status_code, r.get_json()['error']),
          (500, 'ConnectionError: SSO recusado'))
    M.executar = M.executar_orig

    r = c.post('/reconciliation-conf-matching/comment', json={'comment': 'x'})
    check('comentário sem chave é 400', r.status_code, 400)
    j = c.post('/reconciliation-conf-matching/comment', json={'key': 'F1', 'comment': ' ok '}).get_json()
    check('comentário grava', (j['success'], j['comment'], M.load_comments()), (True, 'ok', {'F1': 'ok'}))
    r = c.get('/reconciliation-conf-matching')
    html = r.get_data(as_text=True)
    check('a página abre', r.status_code, 200)
    check('o <thead> e o JS saem da MESMA lista',
          (html.count('data-lang="cfm-c-'), '"name": "FepWeb Count"' in html),
          (len(M.COLUMNS) + 1, True))
    check('o menu lateral tem a entrada', 'href="/reconciliation-conf-matching"' in html, True)
finally:
    shutil.rmtree(TMP, ignore_errors=True)

print()
if falhas:
    print('%d FALHA(S):' % len(falhas))
    for f in falhas:
        print('  - ' + f)
    sys.exit(1)
print('TUDO OK')
