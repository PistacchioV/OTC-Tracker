"""Manual Deals EA: as operacoes que o EA automatico nao pode considerar.

Duas rotinas no mesmo card, e o que erra em SILENCIO em cada uma:

1. **O Deal do FWD Start e o do VANILLA.** No dia da fixacao a mesa cancela o
   FWD Start e faz um booking novo, ja como vanilla, com Deal ID NOVO — e e esse
   o numero que o EA automatico ve. Mandar o Deal do FWD Start original pediria
   para excluir uma operacao que nao existe mais, deixando a que existe DENTRO
   do EA. O par so e visto junto no pull, e por isso ele e GRAVADO.

2. **Other Publisher: so contraparte EXTERNA.** O teste e o ECONOMIC GROUP do
   Reference Data (`_pc_is_internal_counterparty`), nunca o nome comecar em
   "BANCO" — isso derrubaria Banco Safra, Bradesco e Santander, que sao clientes.

3. **Lista vazia NAO envia**, ao contrario do BACC EA Metrics (la a planilha
   vazia e ela propria a metrica). Aqui o e-mail PEDE para excluir as operacoes
   abaixo: sem operacao nenhuma nao ha o que pedir, e um e-mail com a tabela
   vazia faria quem recebe procurar o que nao existe.

4. **A Legal Entity sai do Reference Data** (cadastro `le-spn`), nunca de um
   literal — seria uma segunda grafia das mesmas entidades.

Nao encosta em rede (SMTP stubado) nem em dado real (arquivos-dia em tempfile).
"""
import io
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from apps import create_app                                  # noqa: E402
from apps.config import DebugConfig                          # noqa: E402
from apps.pages import routes as R                           # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label
          + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def read(rel):
    return io.open(os.path.join(ROOT, rel), encoding='utf-8', errors='ignore').read()


app = create_app(DebugConfig)
REF = datetime(2026, 8, 11)
tmp = tempfile.mkdtemp(prefix='check-mdea-')

_orig = {'dir': R._GENERIC_ND_PRODUCTS['other-publishers']['dir'],
         'rebook': R._MDEA_REBOOK_DIR, 'intern': R._pc_is_internal_counterparty,
         'recfile': R._MDEA_REC_FILE, 'claim': R._MDEA_CLAIM_FILE,
         'status': R._MDEA_STATUS_FILE, 'mdir': R._MDEA_DIR}
try:
    op_dir = os.path.join(tmp, 'OtherPublisher', '2026', '08')
    os.makedirs(op_dir, exist_ok=True)
    io.open(os.path.join(op_dir, '20260811_ndfotherpub.json'), 'w', encoding='utf-8').write(
        json.dumps([
            {'Deal': 'D5VL-AAA', 'Client': 'INDUSTRIA E COMERCIO DE COSMETICOS NATURA LTDA',
             'LE': 'JPM', 'SPN': '111'},
            {'Deal': 'D5VL-BBB', 'Client': 'BANCO SAFRA S.A.', 'LE': 'MGT', 'SPN': '222'},
            {'Deal': 'D5VL-INT', 'Client': 'LAWTON MULTIMERCADO EXCLUSIVO', 'LE': 'JPM', 'SPN': '999'},
            {'Deal': '', 'Client': 'SEM DEAL', 'LE': 'JPM', 'SPN': '111'},
        ]))
    R._GENERIC_ND_PRODUCTS['other-publishers']['dir'] = os.path.join(tmp, 'OtherPublisher')
    R._MDEA_REBOOK_DIR = os.path.join(tmp, 'FwdStartRebooks')
    R._MDEA_DIR = tmp
    R._MDEA_REC_FILE = os.path.join(tmp, 'rec.json')
    R._MDEA_CLAIM_FILE = os.path.join(tmp, 'sent.json')
    R._MDEA_STATUS_FILE = os.path.join(tmp, 'status.json')
    # O ECONOMIC GROUP do RefData e quem responde; aqui so a Lawton e interna —
    # e o Banco Safra, que COMECA com "BANCO", e cliente.
    R._pc_is_internal_counterparty = lambda c, spn='': 'LAWTON' in str(c).upper()

    print('== 1. Other Publisher: so contraparte externa, do proprio dia ==')
    with app.test_request_context():
        op = R._mdea_rows('otherpub', REF)
    check('so as externas entram', [r['deal'] for r in op], ['D5VL-AAA', 'D5VL-BBB'])
    check('a perna interna (Lawton) fica de fora',
          [r for r in op if 'LAWTON' in r['cpty'].upper()], [])
    # "Banco Safra" comeca com BANCO e e CLIENTE: se o filtro fosse por nome, ele
    # sumiria do e-mail e a operacao ficaria dentro do EA automatico.
    check('contraparte que COMECA com BANCO nao e cortada por isso',
          [r['deal'] for r in op if r['cpty'].startswith('BANCO')], ['D5VL-BBB'])
    check('linha sem Deal Id nao entra (o e-mail casa POR ele)',
          [r for r in op if not r['deal']], [])
    # A razao social vem do cadastro le-spn; a sigla so aparece se nao houver
    # linha cadastrada — vazio esconderia de que entidade e a operacao.
    check('a Legal Entity vem por extenso, do Reference Data',
          all(len(r['le']) > 4 for r in op), True)

    print('\n== 2. FWD Start: o Deal e o do VANILLA, e o par e GRAVADO ==')
    with app.test_request_context():
        R._mdea_rebook_record([({'Deal': 'D5VL-VANILLA', 'Client': 'NATURA LTDA', 'LE': 'JPM',
                                 'SPN': '111', 'TradeDate': '11/08/2026'}, 'D5VL-FWDORIG')], REF)
        fs = R._mdea_rows('fwdstart', REF)
    check('uma linha, com o Deal do re-booking em vanilla',
          [r['deal'] for r in fs], ['D5VL-VANILLA'])
    # O Deal do FWD Start original NAO pode sair: ele foi cancelado, e pedir para
    # excluir uma operacao que nao existe deixa a que existe dentro do EA.
    check('o Deal do FWD Start original NAO aparece',
          [r for r in fs if r['deal'] == 'D5VL-FWDORIG'], [])
    check('mas ele fica gravado no par, para a conferencia',
          [r.get('FwdStartDeal') for r in R._mdea_rebook_rows(REF)], ['D5VL-FWDORIG'])
    # A API e puxada a cada 20 min: o mesmo par volta em toda corrida do dia.
    with app.test_request_context():
        R._mdea_rebook_record([({'Deal': 'D5VL-VANILLA', 'Client': 'NATURA LTDA'}, 'D5VL-FWDORIG')], REF)
    check('a mesma operacao nao e gravada duas vezes', len(R._mdea_rebook_rows(REF)), 1)
    check('dia sem fixacao devolve lista vazia, e nao erro',
          R._mdea_rows('fwdstart', datetime(2026, 8, 12)), [])

    # FWD Start bookado e fixado no MESMO dia nao entra: ele nao ficou esperando
    # o fixing, e um trade normal do dia — o EA automatico o enxerga como
    # qualquer outro, e pedir para exclui-lo tiraria da metrica uma operacao que
    # nao tem nada de manual. A data comparada e a do FWD START ORIGINAL: a do
    # vanilla E a Strike Set Date por construcao do pareamento, entao compara-la
    # excluiria TODAS as linhas.
    with app.test_request_context():
        R._mdea_rebook_record([
            ({'Deal': 'VAN-ANTIGO', 'Client': 'NATURA LTDA', 'LE': 'JPM'},
             {'deal': 'FWD-ANTIGO', 'trade': '20/07/2026'}),
            ({'Deal': 'VAN-MESMODIA', 'Client': 'BAYER S.A.', 'LE': 'JPM'},
             {'deal': 'FWD-MESMODIA', 'trade': '11/08/2026'}),
            ({'Deal': 'VAN-SEMDATA', 'Client': 'NUTRADE LTDA', 'LE': 'JPM'},
             {'deal': 'FWD-SEMDATA', 'trade': ''}),
        ], REF)
        fs2 = [r['deal'] for r in R._mdea_rows('fwdstart', REF)]
    check('o FWD Start bookado e fixado no mesmo dia fica FORA',
          'VAN-MESMODIA' in fs2, False)
    check('   e o bookado antes continua entrando', 'VAN-ANTIGO' in fs2, True)
    # Sem a data gravada nao da para afirmar que foi no mesmo dia: o lado seguro
    # e INCLUIR — uma operacao a mais e revisada por quem recebe, uma a menos
    # fica no EA sem ninguem ver.
    check('   e sem a data gravada, na duvida, ENTRA', 'VAN-SEMDATA' in fs2, True)
    # As datas vem de arquivos diferentes e ja apareceram com zero a esquerda de
    # um jeito e de outro: comparar o texto cru erraria em silencio.
    check('a comparacao de data e normalizada, nao textual',
          [R._mdea_date_key('11/08/2026'), R._mdea_date_key('2026-08-11'),
           R._mdea_date_key(''), R._mdea_date_key('lixo')],
          ['2026-08-11', '2026-08-11', '', ''])
    # O store NAO pode morar no cache do New Deals: o Monitor varre aquela arvore
    # e trata todo diretorio novo como um PRODUTO — foi assim que nasceu um card
    # "NDF FwdStartRebooks" na secao Others.
    check('o store do par fica FORA do cache do New Deals',
          R.NEW_DEALS_CACHE_ROOT in _orig['rebook'], False)

    print('\n== 3. Os desfechos do envio sao TRES, e nao dois ==')
    enviados = []
    R._mdea_send_email = lambda kind, rows, to, cc, ref: (
        enviados.append({'kind': kind, 'rows': len(rows), 'to': list(to), 'cc': list(cc)}) or True)
    with app.test_request_context():
        # Sem destinatario, MAS com operacao: o pedido nao saiu de casa.
        R._save_mdea_recipients({'to': '', 'cc': ''})
        out = R._mdea_run('otherpub', REF)
        check('sem TO nao envia, e diz por que', (out['sent'], out['reason']), (False, 'no_recipient'))
        check('   e nem monta o e-mail', enviados, [])
        # Lista vazia NAO envia — ao contrario do BACC EA Metrics.
        R._save_mdea_recipients({'to': 'hub@x.com'})
        out = R._mdea_run('fwdstart', datetime(2026, 8, 12))
        check('sem operacao nao envia', (out['sent'], out['reason']), (False, 'empty'))
        check('   e o desfecho vazio nao e erro', out.get('error'), None)
        out = R._mdea_run('otherpub', REF)
        check('com TO e com operacao, envia', out['sent'], True)
        check('   com as linhas do dia', enviados[-1]['rows'], 2)

    print('\n== 4. O Cc nasce com a mesa, e o merge nao apaga a outra lista ==')
    os.remove(R._MDEA_REC_FILE)
    check('Cc padrao e a caixa do OTC Ops',
          R._load_mdea_recipients()['cc'], 'brazil.otc.ops@jpmorgan.com')
    R._save_mdea_recipients({'to': 'hub@x.com'})
    check('gravar so o TO nao apaga o Cc', R._load_mdea_recipients()['cc'],
          'brazil.otc.ops@jpmorgan.com')
    R._save_mdea_recipients({'cc': ''})
    check('mas limpar o Cc EXPLICITAMENTE vale', R._load_mdea_recipients()['cc'], '')

    print('\n== 5. Horarios, claim e catch-up ==')
    check('Other Publisher as 20:00 e FWD Start as 16:30',
          [R._MDEA_TIME['otherpub'], R._MDEA_TIME['fwdstart']], [(20, 0), (16, 30)])
    check('o slot so e reservado uma vez',
          [R._mdea_claim_slot('2026-08-11 otherpub 20:00'),
           R._mdea_claim_slot('2026-08-11 otherpub 20:00')], [True, False])
    # Falha de envio DEVOLVE o slot: uma queda transitoria do SMTP nao pode
    # custar o e-mail do dia inteiro.
    R._mdea_release_slot('2026-08-11 otherpub 20:00')
    check('e devolvido quando o envio falha', R._mdea_claim_slot('2026-08-11 otherpub 20:00'), True)

    print('\n== 6. O card, o template e os tres mapas de acesso ==')
    TPL = read('apps/templates/pages/control-panel.html')
    check('o card existe', 'data-cp-card="manualdealsea"' in TPL, True)
    # `.cp-reveal` e `display: flex` em LINHA: dois cards dentro do mesmo ficam
    # LADO A LADO, e foi assim que este card nasceu desalinhado com o BACC EA.
    # Quem empilha e o `flex-column` da coluna — um card por reveal.
    # O card vive na secao Economic Affirmation, numa coluna PROPRIA — os tres
    # cards dela (Manual Deals EA, BACC EA Metrics e MT300) tem alturas
    # parecidas, entao nao ha o que empilhar. A coluna empilhada do painel e a
    # da Intraday, e quem prende aquela geometria e o
    # check_control_panel_sections.
    _sec = TPL.split('data-cp-hdr="affirmation"', 1)[1]
    check('o card esta na secao Economic Affirmation',
          re.findall(r'data-cp-card="([^"]+)"', _sec.split('data-cp-hdr=', 1)[0]),
          ['manualdealsea', 'baccea', 'mt300'])
    # `.cp-reveal` e `display: flex` em LINHA: dois cards dentro do mesmo ficam
    # LADO A LADO, e foi assim que este card nasceu desalinhado com o BACC EA.
    _col = _sec.split('<div class="col-12 col-lg-6 d-flex" data-cp-group="affirmation">', 2)[1]
    check('um card por .cp-reveal',
          [b.count('class="cp-card"') for b in _col.split('<div class="cp-reveal">')[1:2]], [1])
    check('   e o espacamento vem do gap da coluna, nao de margem no card',
          'cp-card mt-3' in _col, False)
    check('   com UM botao Run por rotina',
          ['data-mdea-run="otherpub"' in TPL, 'data-mdea-run="fwdstart"' in TPL], [True, True])
    check('   e o campo TO — BACC HUB', 'id="cp-mdea-to"' in TPL, True)
    # Card do Control Panel e controlado por token: sem o registro, a rotina
    # ficaria fora do /page-access e o endpoint sem dono.
    check('o card esta no registro de acesso',
          any(c['id'] == 'manualdealsea' for c in R._CONTROL_PANEL_CARDS), True)
    check('   e os dois endpoints apontam para ele',
          [R._CP_ENDPOINT_CARD.get('/api/control-panel/manual-deals-ea/recipients'),
           R._CP_ENDPOINT_CARD.get('/api/control-panel/manual-deals-ea/run')],
          ['manualdealsea', 'manualdealsea'])
    check('o template do e-mail existe',
          os.path.exists(os.path.join(ROOT, 'apps', 'templates', 'pages',
                                      'email-template-manual-deals-ea.html')), True)
    # O corpo do e-mail e o PEDIDO, e a tabela e o conteudo dele: quem recebe
    # casa linha a linha pelo Deal Id.
    MAIL = read('apps/templates/pages/email-template-manual-deals-ea.html')
    check('   com as tres colunas da imagem',
          ['>Deal Id<' in MAIL, '>Legal Entity<' in MAIL, '>Counterparty<' in MAIL],
          [True, True, True])
    check('   e o pedido por extenso', 'do not consider the deal(s) below' in MAIL, True)
    # O cabecalho e cor solida + gradiente CSS, nunca imagem/VML (CLAUDE.md §2).
    check('usa o header de gradiente da casa, sem VML',
          ["{% include 'partials/email-gradient-header.html' %}" in MAIL,
           '<v:rect' in MAIL], [True, False])
    for lang in ('en', 'br', 'es'):
        tr = json.load(io.open(os.path.join(ROOT, 'apps', 'static', 'data', 'translations',
                                            lang + '.json'), encoding='utf-8'))
        faltando = [k for k in ('cp-r-mdea-title', 'cp-r-mdea-desc', 'cp-mdea-to', 'cp-mdea-cc',
                                'cp-mdea-meta', 'cp-mdea-run-op', 'cp-mdea-run-fs',
                                'cp-mdea-never', 'cp-mdea-sent', 'cp-mdea-empty',
                                'cp-mdea-norec', 'cp-mdea-now') if k not in tr]
        check('%s.json tem as chaves do card' % lang, faltando, [])

    print('\n== 7. O par e gravado no pull, e nao so registrado no log ==')
    SRC = read('apps/pages/routes.py')
    check('o pull chama o _mdea_rebook_record', '_mdea_rebook_record(rebooks, now)' in SRC, True)
    # O scheduler roda fora de request: sem application context o
    # render_template e o _get_logo_path morrem, e so o automatico falha —
    # o botao Run funciona porque roda dentro de um request (CLAUDE.md §7).
    bloco = SRC.split('def _mdea_send_email', 1)[1].split('\ndef ', 1)[0]
    check('o envio monta a mensagem dentro do application context',
          'with _app_context():' in bloco, True)
    check('e o horario e o do Brasil, nao o do servidor',
          '_br_now()' in SRC.split('def _mdea_scheduler_loop', 1)[1].split('\ndef ', 1)[0], True)
finally:
    R._GENERIC_ND_PRODUCTS['other-publishers']['dir'] = _orig['dir']
    R._MDEA_REBOOK_DIR = _orig['rebook']
    R._pc_is_internal_counterparty = _orig['intern']
    R._MDEA_REC_FILE, R._MDEA_CLAIM_FILE = _orig['recfile'], _orig['claim']
    R._MDEA_STATUS_FILE, R._MDEA_DIR = _orig['status'], _orig['mdir']
    shutil.rmtree(tmp, ignore_errors=True)

print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
