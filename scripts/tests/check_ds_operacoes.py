#!/usr/bin/env python3
"""check_ds_operacoes.py — o filtro do arquivo de operações do Daily Settlement.

Duas colunas decidem o que entra no `operacoes-jpm.json`: a CONTA e o TIPO DE
TÍTULO. E o que entra alcança muito mais do que o card: este é o JSON que a
página Operations B3 lê, e é dele que saem a mensageria, os avisos de liquidação
e os cards de reconciliação. Uma conta que não passa por aqui não existe para
nenhum deles — some sem erro nenhum, e a tela mostra a menos.

O outro jeito de quebrar isto é sutil: a coluna dos filtros do `_DS_IMPORTS` é
**1-based** (`_ds_cell(row, col - 1)`), enquanto a do `_CETIP_BEHAVIOUR`, logo
acima no mesmo arquivo, é 0-based. Trocar um pelo outro filtra pela coluna
vizinha, e o resultado é um arquivo vazio ou uma lista com o que não devia estar
lá — nos dois casos sem exceção nenhuma.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', os.path.join(ROOT, '.tmp-share'))

from apps.pages import routes as R          # noqa: E402

fails = []


def check(label, got, want):
    ok = got == want
    print(('  ok  ' if ok else ' FAIL ') + label)
    if not ok:
        print('        esperado: %r' % (want,))
        print('        veio:     %r' % (got,))
        fails.append(label)


# A ordem das colunas é a do arquivo real (header na linha 5): Conta é a 2ª e
# Tipo Título a 10ª — os dois números que os filtros do spec citam.
HEADER = ['Data', 'Conta', 'Tipo Operação', 'C/V', 'Título', 'Tipo de Regime',
          'Data Vencimento', 'Valor', 'Modalidade Liquidação', 'Tipo Título', 'Status']


def linha(conta, tipo_titulo):
    r = ['-'] * len(HEADER)
    r[1] = conta
    r[9] = tipo_titulo
    return r


def arquivo(linhas):
    rows = [['c1'], ['c2'], ['c3'], ['c4'], HEADER] + linhas
    return '\n'.join('\t'.join(map(str, r)) for r in rows).encode('latin-1')


print('\n== 1. o spec ==')
spec = R._opb3_spec()
check('o spec existe', spec is not None, True)
check('e alimenta a página Operations B3', spec.get('opb3'), True)
contas = next(f[2] for f in spec['filters'] if f[0] == 'digits')
# 73760.00-9 é a conta PRÓPRIA, 73760.20-5 a de CLIENTE 2 (ver `b3-accounts`) e
# 73760.40-1 a conta em que o COE é registrado — o Tipo Título COE já estava no
# filtro de títulos e nenhuma linha entrava, porque todas chegam por esta conta.
# A de CLIENTE 1 (73760.10-2) fica de fora, como sempre esteve.
check('as contas do Banco que entram', contas, {'73760009', '73760205', '73760401'})
check('a coluna da conta é a 2ª (1-based)',
      next(f[1] for f in spec['filters'] if f[0] == 'digits'), 2)

print('\n== 2. o que passa e o que não passa ==')
recs, total = R._ds_process(arquivo([
    linha('73760.00-9', 'TER'),
    linha('73760.20-5', 'SWAP'),
    linha('7376020 5', 'OPC'),          # mesma conta, outra pontuação
    linha('73760.10-2', 'TER'),         # CLIENT 1 — fora
    linha('04880.00-6', 'SWAP'),        # MGT — é o outro spec
    linha('73760.20-5', 'CDB'),         # tipo de título fora da lista
    linha('73760.40-1', 'COE'),         # a conta do COE — entra
    linha('73760.40-1', 'CDB'),         # conta certa, título fora — fora
]), spec)
check('leu as oito linhas de dado', total, 8)
check('manteve quatro', len(recs), 4)
check('o COE entra pela conta dele',
      [r for r in recs if r['Conta'] == '73760.40-1' and r['Tipo Título'] == 'COE'] != [], True)
check('mas a conta do COE não abre a porta para outro título',
      [r for r in recs if r['Tipo Título'] == 'CDB'], [])
check('a própria entra', [r for r in recs if r['Conta'] == '73760.00-9'] != [], True)
check('a de cliente 2 entra', [r for r in recs if r['Conta'] == '73760.20-5'] != [], True)
# A conta chega ora `73760.20-5`, ora `7376020 5`: a comparação é por DÍGITOS, e
# comparar string deixaria metade do arquivo de fora em silêncio.
check('e entra escrita sem pontuação',
      [r for r in recs if r['Conta'] == '7376020 5'] != [], True)
check('a de cliente 1 fica de fora',
      [r for r in recs if r['Conta'] == '73760.10-2'], [])
check('a da MGT fica de fora (é o outro spec)',
      [r for r in recs if r['Conta'] == '04880.00-6'], [])
check('e o tipo de título de fora da lista também',
      [r for r in recs if r['Tipo Título'] == 'CDB'], [])

print('\n== 3. o spec da MGT continua o dele ==')
mgt = next((s for s in R._DS_IMPORTS if s.get('key') == 'operacoes-mgt'), None)
check('o spec da MGT existe', mgt is not None, True)
check('e só a conta da MGT', next(f[2] for f in mgt['filters'] if f[0] == 'digits'),
      {'04880006'})
recs_mgt, _ = R._ds_process(arquivo([linha('04880.00-6', 'SWAP'),
                                     linha('73760.20-5', 'SWAP')]), mgt)
check('o arquivo da MGT não leva conta do Banco', len(recs_mgt), 1)

print('\n== 3b. o Participante da A3 escolhe JPM x MGT, nao o nome ==')
def _com_part(part):
    # A A3 real traz o usuario depois do codigo: `Participante: X - Usuário: E93017`.
    rows = [['c1'], ['c2'], ['Participante: ' + part + ' - Usuário: E93017'], ['c4'], HEADER,
            linha('04880.00-6', 'SWAP')]
    return '\n'.join('\t'.join(r) for r in rows).encode('latin-1')
check('Operacoes*.txt com MORGANBC vira MGT',
      R._ds_match_spec('Operacoes_20260929.txt', _com_part('MORGANBC'))['key'], 'operacoes-mgt')
check('Operacoes*.txt com JPMORGANBM segue JPM',
      R._ds_match_spec('Operacoes_20260929.txt', _com_part('JPMORGANBM'))['key'], 'operacoes-jpm')
check('mgt.* com JPMORGANBM vira JPM (o conteudo vence)',
      R._ds_match_spec('mgt.txt', _com_part('JPMORGANBM'))['key'], 'operacoes-jpm')
check('sem a linha do Participante vale o nome',
      R._ds_match_spec('mgt.txt', arquivo([]))['key'], 'operacoes-mgt')
check('e sem o conteudo tambem',
      R._ds_match_spec('Operacoes.txt')['key'], 'operacoes-jpm')
import io as _io0, openpyxl as _ox                                      # noqa: E402
_wb = _ox.Workbook(); _ws = _wb.active
for _r in [['c1'], ['c2'], ['Participante: MORGANBC'], ['c4'], HEADER]:
    _ws.append(_r)
_b = _io0.BytesIO(); _wb.save(_b)
check('xlsx com MORGANBC na A3 vira MGT',
      R._ds_match_spec('Operacoes.xlsx', _b.getvalue())['key'], 'operacoes-mgt')

# O export da B3 grava um <dimension> MENOR que a planilha, e o openpyxl em
# read_only confia nele: o card lia 5 linhas e dizia "0 de 5" em arquivo de
# centenas. Aqui o carimbo diz A1:E5 e a planilha tem 5 + 40 linhas.
import re as _re0, zipfile as _zf0                                       # noqa: E402
_wb = _ox.Workbook(); _ws = _wb.active
for _r in ([['B3'], ['Op'], ['Participante: MORGANBC - Usuário: E93017'], [], HEADER]
           + [linha('04880.00-6', 'SWAP')] * 30 + [linha('73760.00-9', 'SWAP')] * 10):
    _ws.append(_r)
_b = _io0.BytesIO(); _wb.save(_b)
_zi = _zf0.ZipFile(_b); _o = _io0.BytesIO(); _zo = _zf0.ZipFile(_o, 'w')
for _i in _zi.infolist():
    _d = _zi.read(_i.filename)
    if _i.filename == 'xl/worksheets/sheet1.xml':
        _d = _re0.sub(rb'<dimension ref="[^"]*"/>', b'<dimension ref="A1:E5"/>', _d)
    _zo.writestr(_i, _d)
_zo.close()
_raw = _o.getvalue()
_sp = R._ds_match_spec('Operacoes_20260928.xlsx', _raw)
check('xlsx da B3 (dimension errado) com MORGANBC vira MGT', _sp['key'], 'operacoes-mgt')
check('e le a planilha INTEIRA, nao so o que o dimension diz',
      tuple(len(x) if isinstance(x, list) else x for x in R._ds_process(_raw, _sp)), (30, 40))

# O aviso do card diz o Participante lido: vai no `processed` da resposta.
_w_real, _side_real = R._ds_write, R._opb3_side_write
R._ds_write = lambda jp, recs, name, spec, total, processed, dp: processed.append(
    {'file': name, 'type': spec['label'], 'kept': len(recs), 'total': total})
R._opb3_side_write = lambda *a, **k: None
try:
    _proc, _skip = [], []
    R._ds_handle('Operacoes.txt', _com_part('MORGANBC'), None,
                 R.datetime(2026, 9, 29), _proc, _skip)
    check('o processed diz o Participante e o tipo',
          (_proc[0]['participant'], _proc[0]['type']), ('MORGANBC', 'Operações MGT'))
    _proc = []
    R._ds_handle('mgt.txt', arquivo([]), None, R.datetime(2026, 9, 29), _proc, _skip)
    check('sem A3 o participant vem vazio (decidiu o nome)', _proc[0]['participant'], '')
finally:
    R._ds_write, R._opb3_side_write = _w_real, _side_real

# ── 4. a Reference date do card decide o DIA em que os JSONs sao gravados ────
#  O dia era o relogio do servidor, e um arquivo de ontem processado hoje ia
#  parar na pasta de hoje — onde as cinco telas que leem esses JSONs nunca o
#  procurariam. A data vai no FORM quando ha arquivos (multipart) e no JSON
#  quando o dropzone esta vazio: os dois caminhos tem de ler, senao o campo
#  vale metade das vezes e em silencio.
print('\n== 4. a Reference date do Save Daily Settlement ==')
import io as _io                                                        # noqa: E402
import tempfile as _tmp                                                 # noqa: E402
from datetime import datetime as _dt, timedelta as _td, timezone as _tz  # noqa: E402
from apps import create_app                                             # noqa: E402
from apps.config import DebugConfig                                     # noqa: E402

os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')
_app = create_app(DebugConfig)
_app.config['TESTING'] = True
_TMP = _tmp.mkdtemp(prefix='otc-ds-ref-')
R.SETTLEMENTS_ROOT = os.path.join(_TMP, 'src')
os.makedirs(R.SETTLEMENTS_ROOT, exist_ok=True)
_vistos = []
_handle_real, _notif_real = R._ds_handle, R._create_notification


def _fake_handle(nome, raw, path, ref, processados, ignorados):
    _vistos.append(ref.strftime('%Y-%m-%d'))
    processados.append({'type': 'X', 'kept': 1, 'total': 1})


R._ds_handle = _fake_handle
R._create_notification = lambda *a, **k: None
try:
    _c = _app.test_client()
    with _c.session_transaction() as _s:
        _s['authenticated'] = True
        _s['user_sid'] = 'A000000'
        _s['user_name'] = 'dev'
        # O expiry vai em UTC: em horario local o before_request ja o le como
        # vencido e a rota responde 401, que se parece com autenticacao quebrada.
        _s['session_expires_at'] = (_dt.now(tz=_tz.utc) + _td(hours=8)).isoformat()
    _URL = '/api/control-panel/daily-settlement-save'

    def _arq():
        return {'files': (_io.BytesIO(b'a\tb'), 'OTM.txt')}

    def _semear():
        with open(os.path.join(R.SETTLEMENTS_ROOT, 'OTM.txt'), 'wb') as fh:
            fh.write(b'a\tb')

    _hoje = R._br_now().strftime('%Y-%m-%d')
    _r = _c.post(_URL, data=dict(_arq(), date='2026-09-02'),
                 content_type='multipart/form-data')
    check('4. multipart: a data do form manda', (_r.status_code, _vistos[-1],
          _r.get_json().get('date')), (200, '2026-09-02', '2026-09-02'))
    _vistos[:] = []
    _c.post(_URL, data=_arq(), content_type='multipart/form-data')
    check('4. sem data, o padrao e HOJE', _vistos[-1], _hoje)
    _vistos[:] = []
    _semear()
    _r = _c.post(_URL, json={'date': '2026-08-11'})
    check('4. dropzone vazio: a data do JSON manda',
          (_vistos[-1], _r.get_json().get('date')), ('2026-08-11', '2026-08-11'))
    _semear()
    check('4. data ilegivel e 400, nao um dia errado em silencio',
          _c.post(_URL, json={'date': 'banana'}).status_code, 400)
    _semear()
    # O arquivo fecha um dia que ainda nao aconteceu.
    check('4. futuro e recusado',
          _c.post(_URL, json={'date': '2027-01-01'}).status_code, 400)
finally:
    R._ds_handle, R._create_notification = _handle_real, _notif_real

# O campo existe na tela, nasce em HOJE e viaja nos dois caminhos do POST.
_CP = open(os.path.join(ROOT, 'apps', 'templates', 'pages', 'control-panel.html'),
           encoding='utf-8').read()
check('4. o campo esta no card, com o default de hoje',
      ('id="cp-ds-date"' in _CP and 'id="cpDsDateWrap" data-default-today' in _CP), True)
check('4. e a data vai no multipart E no JSON',
      ("fd.append('date', iso)" in _CP and 'JSON.stringify(iso ? { date: iso } : {})' in _CP),
      True)

print('\nFALHAS: %d' % len(fails))
sys.exit(1 if fails else 0)
