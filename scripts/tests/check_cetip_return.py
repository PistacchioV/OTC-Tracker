# -*- coding: utf-8 -*-
"""Save CETIP Files: os arquivos crus que chegam na pasta Return (20/10/2026).

A B3 passou a entregar os arquivos da rotina na Return do Batch Conecta,
compactados e com o nome num ENVELOPE —
`73760_CETIP_261019_SP_CADASTROCURVASMOEDASFEEDERDOMINIOS.txt.zip.S10567296`,
que é o nome antigo (`CETIP_261019_CADASTROCURVASMOEDASFEEDERDOMINIOS.txt`) com
o participante na frente, `_SP` depois da data, `.zip` e a sequência da
entrega. O que este teste prende:

  1. o nome novo vira o antigo (o do cadastro `cetip-files`), e TODA linha do
     seed casa com o arquivo no envelope; o SOURCE pode ser escrito nas duas
     formas; arquivo de outro participante não casa;
  2. o `upgrade` do cadastro leva a linha `CETIP_YYMMDD_COE` ao nome que chega
     (`…_COE_ATIVOS_SUBJACENTES`), e só ela;
  3. a rodada traz da Return os crus da DATA para a pasta de origem (byte a
     byte, com o nome como chegou), abre o zip, salva no destino como sempre e
     só então os apaga da Return. Na Return ficam o retorno do Batch Conecta, o
     arquivo de outro dia e o de outro participante;
  4. duas entregas do mesmo arquivo: vale a de sequência maior;
  5. o arquivo que o cadastro não pede fica guardado na origem e é contado;
  6. o que não se copiou para a origem FICA na Return (é o único exemplar);
  7. reprocessar o dia, com a Return já vazia, lê da origem.

Não encosta em dado real: Return, origem e destino em tempfile, SMTP dublado.
"""
import io, os, shutil, sys, tempfile, zipfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', os.path.join(ROOT, '.check-share'))
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

from apps.pages import routes as R                                   # noqa: E402
from apps import create_app                                          # noqa: E402
from apps.config import DebugConfig                                  # noqa: E402
from apps.pages.features.cetip import domain as CD                   # noqa: E402
from apps.pages.features.cetip.infra import mail as CM               # noqa: E402
from apps.pages.features.cetip.infra import persistence as CP        # noqa: E402

app = create_app(DebugConfig)
app.config['TESTING'] = True

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def cliente():
    c = app.test_client()
    with c.session_transaction() as s:
        s['authenticated'] = True
        s['user_sid'] = 'A111111'
        s['user_name'] = 'Alice Souza'
        s['user_role'] = 'BO'
        s['session_ip'] = '127.0.0.1'
        s['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()
    return c


def envelope(legado, seq):
    """O nome antigo `SIS_YYMMDD_RESTO` no envelope da Return."""
    sis, data, resto = legado.split('_', 2)
    return '73760_%s_%s_SP_%s.zip.S%d' % (sis, data, resto, seq)


def zipa(caminho, membros):
    with zipfile.ZipFile(caminho, 'w') as z:
        for nome, texto in membros:
            z.writestr(nome, texto.encode('latin-1'))


print('== 1. o nome novo é lido pelo nome antigo ==')
NOVO = '73760_CETIP_261019_SP_CADASTROCURVASMOEDASFEEDERDOMINIOS.txt.zip.S10567296'
env = CD._cetip_envelope(NOVO)
check('o envelope da captura se desmonta',
      (env['participante'], env['sistema'], env['data'], env['nome'], env['seq'], env['zip']),
      ('73760', 'CETIP', '261019', 'CADASTROCURVASMOEDASFEEDERDOMINIOS.txt', 10567296, True))
check('e o nome antigo é o do cadastro', CD._cetip_nome_legado(NOVO),
      'CETIP_261019_CADASTROCURVASMOEDASFEEDERDOMINIOS.txt')
check('sem `.txt` dentro, sem extensão', CD._cetip_nome_legado(
      '73760_CETIP_261019_SP_DLIQFINANCBILATBL.zip.S10557695'), 'CETIP_261019_DLIQFINANCBILATBL')
check('o nome antigo volta como veio', CD._cetip_nome_legado('CETIP21_261019_DPOSICAO-SWAP.TXT'),
      'CETIP21_261019_DPOSICAO-SWAP.TXT')
check('o de outro participante NÃO perde o envelope (não casaria com a linha do banco)',
      CD._cetip_nome_legado('04880_CETIP21_261019_SP_DPOSICAO-SWAP.zip.S2'),
      '04880_CETIP21_261019_SP_DPOSICAO-SWAP.zip.S2')
check('o retorno do Batch Conecta não está no envelope', CD._cetip_envelope('RET_20261019.txt'), None)
nao_casam = []
for linha in R._CETIP_FILES_SEED:
    m = CD._cetip_make_matcher(linha['SOURCE'], linha['TYPE'])
    nome = envelope(CD._cetip_apply_date(linha['SOURCE'], '261019') + '.txt', 777)
    if not m(nome.lower()):
        nao_casam.append((linha['TYPE'], nome))
check('toda linha do seed casa com o seu arquivo no envelope', nao_casam, [])
m = CD._cetip_make_matcher('CETIP21_YYMMDD_DPOSICAO-SWAP', 't')
check('o de outro participante não casa', m('04880_cetip21_261019_sp_dposicao-swap.zip.s2'), False)
m = CD._cetip_make_matcher('73760_CETIP_YYMMDD_SP_COE_ATIVOS_SUBJACENTES', 't')
check('o SOURCE escrito no nome novo também vale',
      (m('73760_cetip_261019_sp_coe_ativos_subjacentes.txt.zip.s9'),
       m('cetip_261019_coe_ativos_subjacentes.txt')), (True, True))
check('a entrega mais nova vem depois',
      sorted(['x.zip.S9', '73760_CETIP_261019_SP_A.zip.S200', '73760_CETIP_261019_SP_A.zip.S100'],
             key=CD._cetip_ordem)[-1], '73760_CETIP_261019_SP_A.zip.S200')

print('\n== 2. o upgrade do cadastro: o arquivo de subjacentes ==')
up = R._cetip_files_upgrade([
    {'TYPE': 'Underlying Assets (COE)', 'SOURCE': 'CETIP_YYMMDD_COE', 'DEST': 'CETIP_YYMMDD_COE.txt'},
    {'TYPE': 'Outra (X)', 'SOURCE': 'CETIP_YYMMDD_COE_EDITADO', 'DEST': 'x'}])
check('a linha com o nome curto passa ao nome que chega',
      up[0]['SOURCE'], 'CETIP_YYMMDD_COE_ATIVOS_SUBJACENTES')
check('o DEST não muda', up[0]['DEST'], 'CETIP_YYMMDD_COE.txt')
check('linha editada pela mesa fica como está', up[1]['SOURCE'], 'CETIP_YYMMDD_COE_EDITADO')

print('\n== 3. a rodada: Return -> origem -> destino, e a Return limpa ==')
REF = datetime(2026, 9, 10)
DREF = REF.strftime('%y%m%d')
tmp = tempfile.mkdtemp(prefix='check-cetip-ret-')
ret, src_root, dst_root = (os.path.join(tmp, n) for n in ('Return', 'src', 'dst'))
os.makedirs(ret)
mes = REF.strftime('%m') + '. ' + R._EN_MONTH_NAMES[REF.month - 1]
d_src = os.path.join(src_root, REF.strftime('%Y'), mes, REF.strftime('%d'))
d_dst = os.path.join(dst_root, REF.strftime('%Y'), mes, REF.strftime('%d'))
swap_velho = envelope('CETIP21_%s_DPOSICAO-SWAP.txt' % DREF, 100)
swap_novo = envelope('CETIP21_%s_DPOSICAO-SWAP.txt' % DREF, 200)
fora = envelope('CETIP_%s_CADASTROIMPEDIDOSNEGOCIAR.txt' % DREF, 300)
dois = envelope('CETIP21_%s_DFLUXO_SWAP.txt' % DREF, 400)
outro_dia = envelope('CETIP21_260911_DPOSICAO-SWAP.txt', 500)
outro_part = '04880_CETIP21_%s_SP_DPOSICAO-SWAP.txt.zip.S600' % DREF
retorno_bc = 'RET_%s.txt' % REF.strftime('%Y%m%d')
zipa(os.path.join(ret, swap_velho), [('CETIP21_%s_DPOSICAO-SWAP.txt' % DREF, '1;VELHO\n')])
zipa(os.path.join(ret, swap_novo), [('CETIP21_%s_DPOSICAO-SWAP.txt' % DREF, '1;NOVO\n2;NOVO\n')])
zipa(os.path.join(ret, fora), [('x.txt', 'impedidos\n')])
zipa(os.path.join(ret, dois), [('a.txt', 'a\n'), ('b.txt', 'b\n')])
zipa(os.path.join(ret, outro_dia), [('y.txt', 'amanha\n')])
zipa(os.path.join(ret, outro_part), [('z.txt', 'mgt\n')])
io.open(os.path.join(ret, retorno_bc), 'w').write('1;26C0;0014;EXECUCAO OK;TER  10014\n')
bytes_novo = open(os.path.join(ret, swap_novo), 'rb').read()

orig = (R.CETIP_RETURN_PATH, R.CETIP_SOURCE_ROOT, R.CETIP_DEST_ROOT, R._create_notification,
        CM._send_cetip_email, R._b3_export_json)
R.CETIP_RETURN_PATH, R.CETIP_SOURCE_ROOT, R.CETIP_DEST_ROOT = ret, src_root, dst_root
R._create_notification = lambda *a, **kw: None
CM._send_cetip_email = lambda *a, **kw: True
R._b3_export_json = lambda *a, **kw: '/tmp/ok.json'
try:
    c = cliente()
    r = c.post('/api/control-panel/cetip-settlement', json={'date': '2026-09-10', 'send_email': False})
    d = r.get_json() or {}
    check('a rotina responde 200', r.status_code, 200)
    destino = os.path.join(d_dst, '73760_%s_DPOSICAO-SWAP.CETIP21' % DREF)
    check('o destino recebe o arquivo de DENTRO do zip, em CRLF',
          open(destino, 'rb').read() if os.path.isfile(destino) else None, b'1;NOVO\r\n2;NOVO\r\n')
    check('a entrega de sequência maior venceu (e a tela diz qual)',
          [s['src'] for s in d.get('saved', []) if 'SWAP Position' in s['type']], [swap_novo])
    na_origem = sorted(os.listdir(d_src)) if os.path.isdir(d_src) else []
    check('a origem do dia guarda os crus da DATA, com o nome como chegaram',
          na_origem, sorted([swap_velho, swap_novo, fora, dois]))
    check('byte a byte (o zip, não o conteúdo)', open(os.path.join(d_src, swap_novo), 'rb').read(),
          bytes_novo)
    check('na Return ficam o retorno do Batch Conecta, o de outro dia e o de outro participante',
          sorted(os.listdir(ret)), sorted([retorno_bc, outro_dia, outro_part]))
    check('a resposta diz o que saiu da Return', sorted(d.get('from_return') or []),
          sorted([swap_velho, swap_novo, fora, dois]))
    check('o zip com dois arquivos é erro com o motivo, sem chutar qual',
          [e['file'] for e in d.get('errors', []) if 'expected exactly one' in e.get('error', '')],
          [dois])
    check('o arquivo que o cadastro não pede fica na origem e é contado',
          d.get('unmatched'), [fora])
    check('e a mensagem diz as duas coisas',
          ('moved from the Return folder' in d.get('message', ''),
           'not in the CETIP Files mapping' in d.get('message', '')), (True, True))

    print('\n== 4. o que não se copiou fica na Return ==')
    falha = envelope('CETIP21_%s_DOPERACOES.txt' % DREF, 700)
    zipa(os.path.join(ret, falha), [('o.txt', 'h\n1\n')])
    orig_copy = CP.shutil.copy2

    def _copia(a, b, *k, **kw):
        if os.path.basename(a) == falha:
            raise IOError('share indisponivel')
        return orig_copy(a, b, *k, **kw)
    CP.shutil.copy2 = _copia
    try:
        d = c.post('/api/control-panel/cetip-settlement',
                   json={'date': '2026-09-10', 'send_email': False}).get_json() or {}
    finally:
        CP.shutil.copy2 = orig_copy
    check('o arquivo continua na Return', falha in os.listdir(ret), True)
    check('e a rodada diz por quê',
          [e['file'] for e in d.get('errors', []) if e.get('type') == 'Return'], [falha])

    print('\n== 5. reprocessar o dia lê da origem ==')
    os.remove(os.path.join(ret, falha))
    os.remove(destino)
    d = c.post('/api/control-panel/cetip-settlement',
               json={'date': '2026-09-10', 'send_email': False}).get_json() or {}
    check('com a Return vazia para a data, o destino volta a sair da origem',
          open(destino, 'rb').read() if os.path.isfile(destino) else None, b'1;NOVO\r\n2;NOVO\r\n')
    check('e nada mais sai da Return', d.get('from_return'), [])
finally:
    (R.CETIP_RETURN_PATH, R.CETIP_SOURCE_ROOT, R.CETIP_DEST_ROOT, R._create_notification,
     CM._send_cetip_email, R._b3_export_json) = orig
    shutil.rmtree(tmp, ignore_errors=True)

print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
