"""Save CETIP Files: o e-mail do BACC e o recorte do intragrupo.

O BACC recebe DFLUXO swap, posicao swap, posicao OPC e posicao TER — mas nao os
arquivos cheios: so as linhas em que PARTE e CONTRAPARTE sao as tres contas de
casa (00041.00-7 Lawton, 73760.00-9 Banco, 85398.00-5 Atacama). Tres coisas que
erram em SILENCIO se cairem:

1. **`and`, nao `or`.** Uma linha com so um dos lados intragrupo e operacao com
   CLIENTE. Com `or`, o recorte sairia com a carteira de terceiros dentro de um
   arquivo que se chama "intragrupo" — e quem recebe nao tem como perceber.

2. **`'parte (conta)'` e SUBSTRING de `'contraparte (conta)'`.** A resolucao por
   nome tenta cada token contra TODAS as colunas, entao sem o `avoid` o lado da
   parte casa com a coluna da contraparte quando ela vem antes no cabecalho: o
   filtro compara a mesma coluna duas vezes e deixa passar linha de cliente.

3. **Zero a esquerda.** O Lawton e `00041.00-7`; um exportador que trate a conta
   como numero devolve `41007`. Sem o zfill(8) ele nao casa com nada e o recorte
   sai VAZIO — um anexo de zero linha parece "nao teve intragrupo hoje".

E o par de colunas que nao resolve tem de deixar o arquivo FORA do anexo: mandar
o arquivo inteiro com o nome de um recorte e pior do que nao mandar.

Nao encosta em dado real: os arquivos sao sinteticos, em tempfile.
"""
import io
import os
import shutil
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from apps.pages import routes as R                            # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label
          + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def read(rel):
    return io.open(os.path.join(ROOT, rel), encoding='utf-8', errors='ignore').read()


def write(tmp, name, linhas):
    """Arquivo CETIP sintetico: ';' como separador, latin-1, CRLF."""
    p = os.path.join(tmp, name)
    with io.open(p, 'w', encoding='latin-1', newline='') as fh:
        fh.write('\r\n'.join(linhas) + '\r\n')
    return p


def lines_of(path):
    with io.open(path, encoding='latin-1', newline='') as fh:
        return [ln for ln in fh.read().splitlines() if ln.strip()]


LAWTON, BANCO, ATACAMA = '00041.00-7', '73760.00-9', '85398.00-5'
CLIENTE = '12345.00-1'

tmp = tempfile.mkdtemp(prefix='check-cetip-bacc-')
out = tempfile.mkdtemp(prefix='check-cetip-bacc-out-')
try:
    print('== 1. os quatro arquivos estao marcados para o BACC ==')
    marcados = sorted(k for k, v in R._CETIP_BEHAVIOUR.items() if v.get('attach_bacc'))
    check('sao exatamente quatro', marcados,
          ['Option Position (OPC DPOSICAO)', 'SWAP Flow (DFLUXO_SWAP)',
           'SWAP Position (DPOSICAO-SWAP)', 'Term Position (DPOSICAO-TER)'])
    for k in marcados:
        cfg = R._CETIP_BEHAVIOUR[k].get('bacc') or {}
        check('%-32s tem o par de colunas' % k,
              bool(cfg.get('parte')) and bool(cfg.get('contraparte')), True)
    check('as tres contas do intragrupo', sorted(R._CETIP_BACC_ACCOUNTS),
          ['00041007', '73760009', '85398005'])
    check('o DFLUXO nao vai para mais ninguem',
          any(R._CETIP_BEHAVIOUR['SWAP Flow (DFLUXO_SWAP)'].get(k)
              for k in ('attach_sales_support', 'attach_cem_latam')), False)

    print('\n== 2. conta comparavel: pontuacao fora, zero a esquerda de volta ==')
    check('00041.00-7 -> 00041007', R._cetip_acct_key('00041.00-7'), '00041007')
    check('41007 (numero) -> 00041007', R._cetip_acct_key('41007'), '00041007')
    check('73760009 fica', R._cetip_acct_key('73760009'), '73760009')
    check('vazio nao vira conta', R._cetip_acct_key('') in R._CETIP_BACC_ACCOUNTS, False)

    print('\n== 3. posicao SWAP (sem cabecalho: Participante col D x Contraparte col H) ==')
    cfg = R._CETIP_BEHAVIOUR['SWAP Position (DPOSICAO-SWAP)']['bacc']
    # 8 campos: [3] = Participante, [7] = Contraparte.
    def swap_row(parte, cpty, tag):
        c = ['1', '20260817', 'C' + tag, parte, '', '', '', cpty]
        return ';'.join(c)
    src = write(tmp, '73760_260817_DPOSICAO-SWAP.CETIP21', [
        swap_row(BANCO, LAWTON, '1'),        # intragrupo  -> fica
        swap_row(LAWTON, ATACAMA, '2'),      # intragrupo  -> fica
        swap_row(BANCO, CLIENTE, '3'),       # cliente     -> sai
        swap_row(CLIENTE, BANCO, '4'),       # cliente     -> sai
        swap_row('41007', BANCO, '5'),       # zero perdido-> fica
    ])
    got = R._cetip_bacc_copy(src, cfg, out)
    check('devolveu (path, mantidas, total)', bool(got) and got[1:], (3, 5))
    check('so as linhas intragrupo', [ln.split(';')[2] for ln in lines_of(got[0])],
          ['C1', 'C2', 'C5'])
    check('mesmo nome do arquivo original',
          os.path.basename(got[0]), '73760_260817_DPOSICAO-SWAP.CETIP21')
    check('o arquivo salvo nao foi tocado', len(lines_of(src)), 5)
    check('gravado com CRLF',
          io.open(got[0], 'rb').read().count(b'\r\n') >= 3, True)

    print('\n== 4. fluxo SWAP (sem cabecalho: conta cetip parte col C x contraparte col F) ==')
    cfg = R._CETIP_BEHAVIOUR['SWAP Flow (DFLUXO_SWAP)']['bacc']
    def fluxo_row(parte, cpty, tag):
        return ';'.join(['C' + tag, 'SWAP', parte, 'NOME', 'A', cpty])
    src = write(tmp, '73760_260817_DFLUXO.CETIP21', [
        fluxo_row(BANCO, ATACAMA, '1'),
        fluxo_row(BANCO, CLIENTE, '2'),
        fluxo_row(ATACAMA, LAWTON, '3'),
    ])
    got = R._cetip_bacc_copy(src, cfg, out)
    check('duas de tres', bool(got) and got[1:], (2, 3))
    check('as certas', [ln.split(';')[0] for ln in lines_of(got[0])], ['C1', 'C3'])

    print('\n== 5. posicao OPC (com cabecalho) — e a armadilha do substring ==')
    cfg = R._CETIP_BEHAVIOUR['Option Position (OPC DPOSICAO)']['bacc']
    # A CONTRAPARTE vem ANTES da PARTE no cabecalho: e o caso em que 'parte
    # (conta)' casaria com 'Contraparte (Conta)' se nao houvesse o `avoid`.
    hdr = 'Codigo IF;Contraparte (Conta);Contraparte (Nome);Parte (Conta);Parte (Nome)'
    def opc_row(parte, cpty, tag):
        return ';'.join(['IF' + tag, cpty, 'CP', parte, 'PT'])
    src = write(tmp, '73760_260817_DPOSICAO.OPC', [
        hdr,
        opc_row(BANCO, LAWTON, '1'),         # intragrupo -> fica
        opc_row(BANCO, CLIENTE, '2'),        # cliente na contraparte -> sai
        opc_row(CLIENTE, LAWTON, '3'),       # cliente na parte -> sai
    ])
    got = R._cetip_bacc_copy(src, cfg, out)
    check('uma de tres (o `and` valendo)', bool(got) and got[1:], (1, 3))
    saida = lines_of(got[0])
    check('cabecalho preservado na 1a linha', saida[0], hdr)
    check('e so a linha intragrupo embaixo', [ln.split(';')[0] for ln in saida[1:]], ['IF1'])

    print('\n== 6. posicao TER (com cabecalho) ==')
    cfg = R._CETIP_BEHAVIOUR['Term Position (DPOSICAO-TER)']['bacc']
    hdr = ('Data do Arquivo;Codigo da Parte;Nome da Parte;Codigo da Contraparte;'
           'Nome da Contraparte;Contrato')
    def ter_row(parte, cpty, tag):
        return ';'.join(['20260817', parte, 'PT', cpty, 'CP', 'T' + tag])
    src = write(tmp, '73760_260817_DPOSICAO-TER.TER', [
        hdr,
        ter_row(BANCO, LAWTON, '1'),
        ter_row(LAWTON, CLIENTE, '2'),
    ])
    got = R._cetip_bacc_copy(src, cfg, out)
    check('uma de duas', bool(got) and got[1:], (1, 2))
    check('a linha certa', [ln.split(';')[5] for ln in lines_of(got[0])[1:]], ['T1'])

    print('\n== 7. coluna que nao resolve deixa o arquivo FORA ==')
    ruim = {'has_header': True,
            'parte': {'column': ['coluna que nao existe']},          # sem index
            'contraparte': {'column': ['outra que nao existe']}}
    src = write(tmp, '73760_260817_QUALQUER.TXT', ['A;B', '1;2'])
    check('devolve None (nao anexa)', R._cetip_bacc_copy(src, ruim, out), None)
    check('arquivo vazio tambem devolve None',
          R._cetip_bacc_copy(write(tmp, 'vazio.TXT', []), ruim, out), None)

    print('\n== 8. recorte sem nenhuma linha ainda sai (com o cabecalho) ==')
    cfg = R._CETIP_BEHAVIOUR['Term Position (DPOSICAO-TER)']['bacc']
    src = write(tmp, '73760_260817_DPOSICAO-TER-SOCLIENTE.TER',
                [hdr, ter_row(CLIENTE, '99999.00-9', '9')])
    got = R._cetip_bacc_copy(src, cfg, out)
    check('zero de uma', bool(got) and got[1:], (0, 1))
    check('e o anexo tem so o cabecalho', lines_of(got[0]), [hdr])

    print('\n== 9. as tres listas de TO, e o merge que nao apaga as outras ==')
    check('tres chaves', sorted(R._CETIP_RECIPIENT_KEYS), ['bacc_to', 'cem_to', 'ss_to'])
    _real_load = R._load_cetip_recipients
    R._load_cetip_recipients = lambda: {'ss_to': 'ss@x.com', 'cem_to': 'cem@x.com',
                                        'bacc_to': 'bacc@x.com'}
    try:
        rec, mudou = R._cetip_merge_recipients({'ss_to': 'novo@x.com'})
        check('o payload sobrescreve o que veio', rec['ss_to'], 'novo@x.com')
        check('   e NAO apaga o cem', rec['cem_to'], 'cem@x.com')
        check('   nem o bacc', rec['bacc_to'], 'bacc@x.com')
        check('   e diz que mudou', mudou, True)
        rec, mudou = R._cetip_merge_recipients({})
        check('payload vazio nao muda nada', (rec['bacc_to'], mudou), ('bacc@x.com', False))
        rec, _ = R._cetip_merge_recipients({'bacc_to': ''})
        check('mas chave vazia EXPLICITA limpa a lista', rec['bacc_to'], '')
    finally:
        R._load_cetip_recipients = _real_load

    print('\n== 10. a tela e o envio estao ligados ==')
    TPL = read('apps/templates/pages/control-panel.html')
    check('o campo existe no card', 'id="cp-cetip-bacc-to"' in TPL, True)
    check('   e vai no payload do Run', 'data-payload-key="bacc_to"' in TPL, True)
    check('   e o JS le/grava a chave', "bacc_to: 'cp-cetip-bacc-to'" in TPL, True)
    for lang in ('en', 'br', 'es'):
        check('traducao %s do rotulo' % lang,
              '"cp-cetip-bacc-to"' in read('apps/static/data/translations/%s.json' % lang), True)
    SRC = read('apps/pages/routes.py')
    blk = SRC.split('def _cetip_distribute_emails', 1)[1].split('\n@blueprint', 1)[0]
    check('o e-mail do BACC sai com os recortes', 'attachments=bacc_paths' in blk, True)
    check('   com OTC Ops em copia', 'bacc_to_list, [CETIP_OTC_OPS_EMAIL]' in blk, True)
    check('   e a pasta temporaria e removida', 'shutil.rmtree(bacc_tmp' in blk, True)
    check('sem TO o recorte nem e montado', 'if rule.get(\'attach_bacc\') and bacc_to_list:' in blk, True)
    check('o ramo distribute passa a lista do bacc',
          "_parse_emails(rec['bacc_to'])" in SRC, True)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.rmtree(out, ignore_errors=True)

print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
