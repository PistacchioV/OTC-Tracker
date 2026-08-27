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
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

# Fora do Windows o share tem de ser absoluto para o `Config` importar (§8), e
# desde que as recons perguntam a raiz ao Config isto vale para elas também.
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', os.path.join(ROOT, '.check-share'))

from apps.pages import routes as R
# O Save CETIP Files mora em features/cetip (nomes preservados no engine).
# O Save CETIP Files mora em features/cetip, separado em camadas (§321): o
# patch vai no módulo DONO de cada nome (as travessias são por atributo de
# módulo, então o espião intercepta).
from apps.pages.features.cetip import commands as CC   # noqa: E402
from apps.pages.features.cetip import domain as CD     # noqa: E402
from apps.pages.features.cetip.infra import persistence as CP  # noqa: E402

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
    marcados = sorted(k for k, v in CD._CETIP_BEHAVIOUR.items() if v.get('attach_bacc'))
    check('sao exatamente quatro', marcados,
          ['NDF Position (DPOSICAO-TER)', 'Option Position (OPC DPOSICAO)',
           'SWAP Flow (DFLUXO_SWAP)', 'SWAP Position (DPOSICAO-SWAP)'])
    for k in marcados:
        cfg = CD._CETIP_BEHAVIOUR[k].get('bacc') or {}
        check('%-32s tem o par de colunas' % k,
              bool(cfg.get('parte')) and bool(cfg.get('contraparte')), True)
    check('as tres contas do intragrupo', sorted(CD._CETIP_BACC_ACCOUNTS),
          ['00041007', '73760009', '85398005'])
    check('o DFLUXO nao vai para mais ninguem',
          any(CD._CETIP_BEHAVIOUR['SWAP Flow (DFLUXO_SWAP)'].get(k)
              for k in ('attach_sales_support', 'attach_cem_latam')), False)

    print('\n== 2. conta comparavel: pontuacao fora, zero a esquerda de volta ==')
    check('00041.00-7 -> 00041007', CD._cetip_acct_key('00041.00-7'), '00041007')
    check('41007 (numero) -> 00041007', CD._cetip_acct_key('41007'), '00041007')
    check('73760009 fica', CD._cetip_acct_key('73760009'), '73760009')
    check('vazio nao vira conta', CD._cetip_acct_key('') in CD._CETIP_BACC_ACCOUNTS, False)

    print('\n== 3. posicao SWAP (sem cabecalho: Participante col D x Contraparte col H) ==')
    cfg = CD._CETIP_BEHAVIOUR['SWAP Position (DPOSICAO-SWAP)']['bacc']
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
    got = CC._cetip_bacc_copy(src, cfg, out)
    check('devolveu (path, mantidas, total)', bool(got) and got[1:], (3, 5))
    check('so as linhas intragrupo', [ln.split(';')[2] for ln in lines_of(got[0])],
          ['C1', 'C2', 'C5'])
    # O nome do original e MANTIDO e ganha `.txt` no fim: as extensoes da CETIP
    # (.CETIP21/.OPC/.TER) nao abrem com um duplo clique e sao as que o filtro de
    # e-mail barra. Trocar a extensao em vez de acrescentar apagaria justamente a
    # parte do nome que diz qual dos quatro arquivos e aquele.
    check('nome do original + .txt',
          os.path.basename(got[0]), '73760_260817_DPOSICAO-SWAP.CETIP21.txt')
    check('o arquivo salvo nao foi tocado', len(lines_of(src)), 5)
    check('gravado com CRLF',
          io.open(got[0], 'rb').read().count(b'\r\n') >= 3, True)

    print('\n== 4. fluxo SWAP (sem cabecalho: conta cetip parte col C x contraparte col F) ==')
    cfg = CD._CETIP_BEHAVIOUR['SWAP Flow (DFLUXO_SWAP)']['bacc']
    def fluxo_row(parte, cpty, tag):
        return ';'.join(['C' + tag, 'SWAP', parte, 'NOME', 'A', cpty])
    src = write(tmp, '73760_260817_DFLUXO.CETIP21', [
        fluxo_row(BANCO, ATACAMA, '1'),
        fluxo_row(BANCO, CLIENTE, '2'),
        fluxo_row(ATACAMA, LAWTON, '3'),
    ])
    got = CC._cetip_bacc_copy(src, cfg, out)
    check('duas de tres', bool(got) and got[1:], (2, 3))
    check('as certas', [ln.split(';')[0] for ln in lines_of(got[0])], ['C1', 'C3'])

    print('\n== 5. posicao OPC (com cabecalho) — e a armadilha do substring ==')
    cfg = CD._CETIP_BEHAVIOUR['Option Position (OPC DPOSICAO)']['bacc']
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
    got = CC._cetip_bacc_copy(src, cfg, out)
    check('uma de tres (o `and` valendo)', bool(got) and got[1:], (1, 3))
    saida = lines_of(got[0])
    check('cabecalho preservado na 1a linha', saida[0], hdr)
    check('e so a linha intragrupo embaixo', [ln.split(';')[0] for ln in saida[1:]], ['IF1'])

    print('\n== 6. posicao TER (com cabecalho) ==')
    cfg = CD._CETIP_BEHAVIOUR['NDF Position (DPOSICAO-TER)']['bacc']
    hdr = ('Data do Arquivo;Codigo da Parte;Nome da Parte;Codigo da Contraparte;'
           'Nome da Contraparte;Contrato')
    def ter_row(parte, cpty, tag):
        return ';'.join(['20260817', parte, 'PT', cpty, 'CP', 'T' + tag])
    src = write(tmp, '73760_260817_DPOSICAO-TER.TER', [
        hdr,
        ter_row(BANCO, LAWTON, '1'),
        ter_row(LAWTON, CLIENTE, '2'),
    ])
    got = CC._cetip_bacc_copy(src, cfg, out)
    check('uma de duas', bool(got) and got[1:], (1, 2))
    check('a linha certa', [ln.split(';')[5] for ln in lines_of(got[0])[1:]], ['T1'])

    print('\n== 7. coluna que nao resolve deixa o arquivo FORA ==')
    ruim = {'has_header': True,
            'parte': {'column': ['coluna que nao existe']},          # sem index
            'contraparte': {'column': ['outra que nao existe']}}
    src = write(tmp, '73760_260817_QUALQUER.TXT', ['A;B', '1;2'])
    check('devolve None (nao anexa)', CC._cetip_bacc_copy(src, ruim, out), None)
    check('arquivo vazio tambem devolve None',
          CC._cetip_bacc_copy(write(tmp, 'vazio.TXT', []), ruim, out), None)

    print('\n== 8. recorte sem nenhuma linha ainda sai (com o cabecalho) ==')
    cfg = CD._CETIP_BEHAVIOUR['NDF Position (DPOSICAO-TER)']['bacc']
    src = write(tmp, '73760_260817_DPOSICAO-TER-SOCLIENTE.TER',
                [hdr, ter_row(CLIENTE, '99999.00-9', '9')])
    got = CC._cetip_bacc_copy(src, cfg, out)
    check('zero de uma', bool(got) and got[1:], (0, 1))
    check('e o anexo tem so o cabecalho', lines_of(got[0]), [hdr])

    print('\n== 9. as quatro listas de TO, e o merge que nao apaga as outras ==')
    check('quatro chaves', sorted(CD._CETIP_RECIPIENT_KEYS),
          ['bacc_to', 'cem_to', 'hub_to', 'ss_to'])
    _real_load = CP._load_cetip_recipients
    CP._load_cetip_recipients = lambda: {'ss_to': 'ss@x.com', 'cem_to': 'cem@x.com',
                                        'bacc_to': 'bacc@x.com', 'hub_to': 'hub@x.com'}
    try:
        rec, mudou = CP._cetip_merge_recipients({'ss_to': 'novo@x.com'})
        check('o payload sobrescreve o que veio', rec['ss_to'], 'novo@x.com')
        check('   e NAO apaga o cem', rec['cem_to'], 'cem@x.com')
        check('   nem o bacc', rec['bacc_to'], 'bacc@x.com')
        check('   nem o hub', rec['hub_to'], 'hub@x.com')
        check('   e diz que mudou', mudou, True)
        rec, mudou = CP._cetip_merge_recipients({})
        check('payload vazio nao muda nada', (rec['bacc_to'], mudou), ('bacc@x.com', False))
        rec, _ = CP._cetip_merge_recipients({'bacc_to': ''})
        check('mas chave vazia EXPLICITA limpa a lista', rec['bacc_to'], '')
    finally:
        CP._load_cetip_recipients = _real_load

    print('\n== 10. a tela e o envio estao ligados ==')
    TPL = read('apps/templates/pages/control-panel.html')
    check('o campo existe no card', 'id="cp-cetip-bacc-to"' in TPL, True)
    check('   e vai no payload do Run', 'data-payload-key="bacc_to"' in TPL, True)
    check('   e o JS le/grava a chave', "bacc_to: 'cp-cetip-bacc-to'" in TPL, True)
    for lang in ('en', 'br', 'es'):
        check('traducao %s do rotulo' % lang,
              '"cp-cetip-bacc-to"' in read('apps/static/data/translations/%s.json' % lang), True)
    # O corpo do distribute mora em commands.py desde o §321.
    SRC = (read('apps/pages/features/cetip/commands.py')
           + read('apps/pages/features/cetip/infra/mail.py'))
    ENTRY = read('apps/pages/features/cetip/entrypoint.py')
    blk = SRC.split('def _cetip_distribute_emails', 1)[1].split('\ndef ', 1)[0]
    check('o e-mail do BACC sai com os recortes', 'attachments=bacc_paths' in blk, True)
    check('   com OTC Ops em copia', 'bacc_to_list, [_R().CETIP_OTC_OPS_EMAIL]' in blk, True)
    check('   e a pasta temporaria e removida', '_limpa_temp()' in blk, True)
    check('sem TO o recorte nem e montado', 'if rule.get(\'attach_bacc\') and bacc_to_list:' in blk, True)
    check('o ramo distribute passa a lista do bacc',
          "_parse_emails(rec['bacc_to'])" in (SRC + ENTRY), True)

    # ── 11. BACC HUB EQT MO — o outro destino, com os arquivos INTEIROS ────────
    # O HUB e o BACC sao times diferentes do mesmo lado: o BACC recebe o recorte
    # do intragrupo, o HUB recebe a posicao CHEIA para reconciliar. Sao duas
    # listas e dois e-mails, e o que erra em silencio aqui e o HUB receber um
    # arquivo filtrado — ele bateria contra uma posicao que nao e a da CETIP.
    print('\n== 11. BACC HUB EQT MO: arquivos inteiros, em .txt ==')
    src = write(tmp, '73760_260817_DPOSICAO-SWAP.CETIP21', [
        swap_row(BANCO, LAWTON, '1'),
        swap_row(BANCO, CLIENTE, '2'),      # cliente: o HUB leva esta tambem
    ])
    got = CC._cetip_txt_copy(src, out)
    check('nome do original + .txt',
          os.path.basename(got or ''), '73760_260817_DPOSICAO-SWAP.CETIP21.txt')
    check('o arquivo vai INTEIRO (a linha de cliente nao e cortada)',
          len(lines_of(got)), 2)
    check('copia byte a byte do original',
          io.open(got, 'rb').read(), io.open(src, 'rb').read())
    check('o arquivo salvo nao foi tocado', len(lines_of(src)), 2)
    check('origem inexistente devolve None, nao explode',
          CC._cetip_txt_copy(os.path.join(tmp, 'nao-existe.CETIP21'), out), None)

    # Os QUATRO arquivos do HUB, e so eles.
    hub = sorted(k for k, v in CD._CETIP_BEHAVIOUR.items() if v.get('attach_hub'))
    check('os cinco tipos do HUB', hub, [
        'NDF Position (DPOSICAO-TER)',
        'Option Position (OPC DPOSICAO)',
        'SWAP (Strategy)',
        'SWAP Position (DPOSICAO-SWAP)',
        'SWAP Premium Agenda (DAGENDAPREMIOS)'])
    # O TER esta nos DOIS destinos, e com conteudo diferente: recortado no BACC e
    # inteiro no HUB. E o caso que justifica os dois e-mails serem separados —
    # num so, os dois anexos teriam o mesmo nome na mesma mensagem.
    ter = CD._CETIP_BEHAVIOUR['NDF Position (DPOSICAO-TER)']
    check('o TER vai para o BACC recortado E para o HUB inteiro',
          [bool(ter.get('attach_bacc')), bool(ter.get('attach_hub'))], [True, True])
    # O DEST do SWAP (Strategy) JA termina em .txt: um segundo sufixo daria
    # `..._MID.txt.txt`, um nome que ninguem escreveu e que o outro lado nao casa.
    check('nome de anexo: .txt e acrescentado uma vez so',
          [CD._cetip_txt_name('73760_260817_DPOSICAO-TER.TER'),
           CD._cetip_txt_name('CETIP21_260817_DPOSICAOESTRATEGIA_MID.txt'),
           CD._cetip_txt_name('X.TXT')],
          ['73760_260817_DPOSICAO-TER.TER.txt',
           'CETIP21_260817_DPOSICAOESTRATEGIA_MID.txt', 'X.TXT'])
    # Comportamento sem cadastro e regra que nunca roda: `_cetip_rules` une os
    # dois pela coluna TYPE, e um tipo so no codigo nao vira anexo nenhum.
    tipos_seed = {r['TYPE'] for r in R._CETIP_FILES_SEED}
    check('todo tipo do HUB tem linha no cadastro (seed)',
          [t for t in hub if t not in tipos_seed], [])
    tipos_json = {r.get('TYPE') for r in json.load(io.open(
        os.path.join(ROOT, 'apps', 'static', 'data', 'mappings', 'cetip-files.json'),
        encoding='utf-8'))}
    check('   e no arquivo versionado', [t for t in hub if t not in tipos_json], [])
    # O HUB nao tem `bacc`: pedir os dois na mesma linha significaria dois anexos
    # com o mesmo nome de origem no mesmo dia.
    check('o tipo novo nao vira JSON nem recorte',
          [k for k in CD._CETIP_BEHAVIOUR['SWAP (Strategy)']], ['attach_hub'])

    # ── 12. o rotulo do cadastro e DIGITADO, e o comportamento nao pode sumir ──
    # O prefixo do TYPE e descricao: a posicao de termo ja se chamou `Term
    # Position (DPOSICAO-TER)` no codigo e `NDF Position (DPOSICAO-TER)` no
    # cadastro do time (TER e termo, que a mesa chama de NDF). Com a juncao so
    # pelo rotulo inteiro, essa linha perdia TODO o comportamento sem erro nenhum
    # — o arquivo continuava sendo salvo e sumia do e-mail do intragrupo, do
    # Sales Support e do JSON. Foi assim que o .TER sumiu do anexo.
    #
    # Os rotulos foram alinhados depois, mas o teste usa o nome HISTORICO de
    # proposito: e ele que prova que o fallback funciona. Com os dois lados
    # iguais o teste passaria sem testar nada.
    print('\n== 12. TYPE renomeado no cadastro nao pode perder o comportamento ==')
    check('o parentetico e o nome do arquivo',
          [CD._cetip_paren_key('NDF Position (DPOSICAO-TER)'),
           CD._cetip_paren_key('SWAP (Strategy)'),
           CD._cetip_paren_key('sem parenteses')],
          ['DPOSICAO-TER', 'STRATEGY', 'SEM PARENTESES'])
    # Se dois comportamentos tivessem o mesmo parentetico, o fallback entregaria
    # o de qualquer um deles — e a regra errada e pior que regra nenhuma.
    parens = [CD._cetip_paren_key(k) for k in CD._CETIP_BEHAVIOUR]
    check('nenhum parentetico repetido entre os comportamentos',
          len(parens), len(set(parens)))
    exato = CD._cetip_behaviour_for('NDF Position (DPOSICAO-TER)')
    check('o TYPE do codigo resolve', bool(exato.get('attach_bacc')), True)
    # O nome HISTORICO tem de continuar resolvendo: a instancia que ainda nao
    # renomeou a linha na tela nao pode perder o comportamento no pull.
    for antigo in ('Term Position (DPOSICAO-TER)', 'Posicao de Termo (DPOSICAO-TER)'):
        check('%r resolve IGUAL pelo parentetico' % antigo,
              CD._cetip_behaviour_for(antigo), exato)
    check('   inclusive o Sales Support, o HUB e o JSON',
          [bool(exato.get('attach_sales_support')), bool(exato.get('attach_hub')),
           bool(exato.get('json'))], [True, True, True])
    check('o Movement de termo tambem atende pelo nome antigo',
          CD._cetip_behaviour_for('Term Movement (DMOVIMENTO C21)'),
          CD._cetip_behaviour_for('NDF Movement (DMOVIMENTO C21)'))
    check('rotulo desconhecido devolve vazio, e nao explode',
          CD._cetip_behaviour_for('Coisa Nova (NAOEXISTE)'), {})
    check('rotulo vazio idem', CD._cetip_behaviour_for(''), {})

    check('o campo do HUB existe no card', 'id="cp-cetip-hub-to"' in TPL, True)
    check('   e vai no payload do Run', 'data-payload-key="hub_to"' in TPL, True)
    check('   e o JS le/grava a chave', "hub_to: 'cp-cetip-hub-to'" in TPL, True)
    for lang in ('en', 'br', 'es'):
        tr = read('apps/static/data/translations/%s.json' % lang)
        check('traducao %s do rotulo e da dica' % lang,
              ['"cp-cetip-hub-to"' in tr, '"cp-cetip-hub-hint"' in tr], [True, True])
    check('o e-mail do HUB sai com as copias inteiras', 'attachments=hub_paths' in blk, True)
    check('   com OTC Ops em copia', 'hub_to_list, [_R().CETIP_OTC_OPS_EMAIL]' in blk, True)
    # Sem TO, nem a copia e montada: o `quer_hub` ja carrega o teste da lista.
    check('sem TO a copia nem e montada',
          "quer_hub = bool(rule.get('attach_hub')) and bool(hub_to_list)" in blk, True)
    # Arquivo que faltou no dia e DITO, nunca omitido: um e-mail com tres dos
    # quatro se parece com um e-mail completo.
    check('arquivo ausente entra em missing, e nao some',
          ['missing=hub_skipped' in blk, 'hub_skipped.append' in blk], [True, True])
    check('o ramo distribute passa a lista do hub',
          "_parse_emails(rec['hub_to'])" in (SRC + ENTRY), True)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.rmtree(out, ignore_errors=True)

print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
