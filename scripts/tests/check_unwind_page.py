# -*- coding: utf-8 -*-
"""check_unwind_page.py — a pagina `/unwinds/ndf/fx` ponta a ponta.

A recompra de NDF de moeda entra pelo e-mail do Athena e sai no arquivo da
B3. Este teste percorre o caminho inteiro com o e-mail REAL da fixture:

  1. a rota da PAGINA existe (URL de tres segmentos: o catch-all do
     `routes.py` so atende `/<template>`, e sem rota propria a tela
     responderia 404 sem erro nenhum na subida);
  2. o import le o e-mail, casa com a posicao pelos 14 caracteres a direita
     do Athena ID e grava o dia;
  3. o re-import PRESERVA o que a mesa decidiu — Status, Nº de Controle
     Interno e a data de liquidacao (reemitir o controle interno de uma
     antecipacao ja enviada faria a B3 ver duas);
  4. o preview monta o TER 0014 de 133 caracteres;
  5. o Send escreve o arquivo no Batch Conecta e vira Sent; linha ja enviada
     NAO se apaga;
  6. recompra sem contrato na posicao nao gera arquivo: o Send recusa o LOTE
     dizendo o que falta, e nada vai pela metade.

Roda em tmp: cache e pasta Conecta apontam para diretorios temporarios, e a
posicao e um stub — nao encosta em dado real.
"""
import io
import json
import os
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')
if os.name != 'nt' and not os.environ.get('OTC_SHARED_DRIVE_ROOT'):
    os.environ['OTC_SHARED_DRIVE_ROOT'] = tempfile.mkdtemp(prefix='otc-share-')

FALHAS = []


def _erro(fn, *a, **k):
    """A MENSAGEM do ValueError que `fn` levanta, ou None se ela nao levanta.
    Recusa tem de dizer o motivo — e o motivo e o que se prende aqui."""
    try:
        fn(*a, **k)
    except ValueError as exc:
        return str(exc)
    return None


def check(nome, cond, extra=''):
    print(('  ok  ' if cond else ' FAIL ') + nome + (('  — ' + str(extra)) if (not cond and extra) else ''))
    if not cond:
        FALHAS.append(nome)


FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       'fixtures', 'unwind-ndf-notification.html')
HTML = io.open(FIXTURE, encoding='utf-8').read()
SUBJECT = 'BRL NDF Unwind Notification_STP-XE-10G5U5X-0-0_E5VL-3ICSK0W'

# A linha do Live Position do contrato recomprado. `Codigo Identificador` e o
# que a ponte procura: os 14 caracteres a direita do Athena ID do e-mail.
#
# O stub entra pela porta do `_lpndf_collect`, e NAO pelo `position_rows`: o
# coletor devolve cada linha como LISTA posicional alinhada com `columns`, e
# um stub de dicionarios esconderia exatamente a juncao que a vertical faz.
# Foi assim que o import morreu em `'list' object has no attribute 'get'` no
# primeiro e-mail de verdade, com o teste verde.
POS = {
    'Codigo Identificador': 'XE-10G5U5X-0-0',
    'Contrato': '26C03202688',
    'Simbolo da Moeda': 'USD',
    # Banco VENDIDO: e o lado que fecha a conta desta operacao (o §11 do
    # check_unwind_notification prova os tres casos reais, e este e o
    # 'USD 10/09/2026'). Com o lado trocado a conferencia NAO fecha, e e
    # justamente isso que o veredito de tres estados existe para dizer.
    'Descricao da posicao do Participante': 'VENDEDOR',
    'Valor Base no registro': '587,224.31',
    'Valor Antecipado': '155,652.49',
    'Codigo da Parte': '73760.00-9',
    'Codigo da Contraparte': '41007',
    'Nome da Contraparte': 'COFCO INTERNATIONAL BRASIL SA',
    'CPF/CNPJ da Contraparte': '02.916.265/0001-60',
}
HOJE = date(2026, 9, 10)


def main():
    from run import app  # noqa: F401
    from apps.pages import routes as R
    from apps.pages.features.unwinds import commands, domain, queries
    from apps.pages.features.unwinds.infra import persistence

    tmp = tempfile.mkdtemp(prefix='otc-unw-')
    # As DUAS portas, e a de baixo derivada da de cima como em produção: o
    # painel varre pela `cache_root` e a gravação usa a `cache_dir`. Trocando
    # só uma, o teste grava no tmp e CONTA a árvore real da máquina.
    persistence.cache_root = lambda: os.path.join(tmp, 'cache')
    persistence.cache_dir = lambda: os.path.join(tmp, 'cache', 'NDF', 'FX')
    R.CONECTA_NEW_PATH = os.path.join(tmp, 'conecta')
    # O import PROJETA a recompra no arquivo-dia do NDF Cockpit — e ele mora no
    # DATA_DIR, que na dev é o próprio checkout. Sem redirecionar, este teste
    # gravaria no Cockpit REAL da máquina, que é dado de verdade.
    R._ndfc_json_path = lambda ref: os.path.join(
        tmp, 'cockpit', ref.strftime('%Y%m%d') + '_ndf-cockpit.json')
    COLUNAS = list(POS.keys())
    def _collect(rows):
        return lambda ref: {'columns': COLUNAS, 'source_date': '2026-09-09',
                            'rows': [[r.get(c, '') for c in COLUNAS] for r in rows]}
    R._lpndf_collect = _collect([POS])
    commands._hoje = lambda: HOJE

    print('\n== 1. a rota da pagina existe (URL de tres segmentos) ==')
    regras = {str(r) for r in app.url_map.iter_rules()}
    check('GET /unwinds/ndf/fx', '/unwinds/ndf/fx' in regras)
    for r in ('/api/unwinds/ndf/fx', '/api/unwinds/ndf/fx/import-file',
              '/api/unwinds/ndf/fx/scan', '/api/unwinds/ndf/fx/preview',
              '/api/unwinds/ndf/fx/send-conecta', '/api/unwinds/ndf/fx/delete'):
        check('rota ' + r, r in regras)
    check('e o arquivo-dia NAO mora em cache/new deals (o Monitor varre de la)',
          'new deals' not in persistence.day_path(datetime(2026, 9, 10)).replace(tmp, ''))

    print('\n== 2. o import le o e-mail e casa com a posicao ==')
    out = commands.import_email(HTML, SUBJECT, ref_dt=HOJE)
    linha = out['rows'][0]
    check('Athena ID do e-mail', linha['AthenaID'] == 'STP-XE-10G5U5X-0-0', linha['AthenaID'])
    check('o contrato veio pela ponte dos 14 caracteres', linha['Contract'] == '26C03202688', linha['Contract'])
    check('a contraparte veio da POSICAO', linha['Counterparty'] == 'COFCO INTERNATIONAL BRASIL SA')
    check('a moeda veio da POSICAO (o e-mail so traz USB)',
          linha['Currency'] == 'USD' and linha['NotionalCCY'] == 'USB')
    check('as contas saem da posicao, normalizadas em 8 digitos',
          (linha['PartyAccount'], linha['CptyAccount']) == ('73760009', '00041007'))
    check('nocional recomprado', round(linha['UnwoundNotional'], 2) == 42227.42, linha['UnwoundNotional'])
    check('resultado = Input Termination Fee', round(linha['Result'], 2) == 11144.00)
    check('a conferencia fecha', linha['Check'] == 'OK', linha['Warnings'])
    check('a direcao e a do SINAL, nao a do campo do e-mail',
          linha['Direction'] and linha['EmailDirection'] == 'RECEIVE')
    check('nasce Imported', linha['Status'] == 'Imported')
    check('liquidacao = hoje', linha['SettlementDate'] == '2026-09-10')
    check('gravou no arquivo-dia', len(queries.entries('2026-09-10')) == 1)

    print('\n== 3. o re-import preserva o que a mesa decidiu ==')
    fp, lst, idx = queries.find('STP-XE-10G5U5X-0-0', '2026-09-10')
    numero_antes = lst[idx]['MyNumber']
    lst[idx].update(Status='Sent', SettlementDate='2026-09-11')
    persistence.save(fp, lst)
    commands.import_email(HTML, SUBJECT, ref_dt=HOJE)
    _f, l2, i2 = queries.find('STP-XE-10G5U5X-0-0', '2026-09-10')
    check('o Nº de Controle Interno e o MESMO', l2[i2]['MyNumber'] == numero_antes)
    check('o Status sobrevive', l2[i2]['Status'] == 'Sent')
    check('a data de liquidacao editada sobrevive', l2[i2]['SettlementDate'] == '2026-09-11')
    check('e nao duplicou a linha', len(queries.entries('2026-09-10')) == 1)
    l2[i2].update(Status='Imported', SettlementDate='2026-09-10')
    persistence.save(_f, l2)

    print('\n== 4. o preview monta o TER 0014 ==')
    _f, l3, i3 = queries.find('STP-XE-10G5U5X-0-0', '2026-09-10')
    arqs = commands.preview(l3[i3])
    check('um arquivo', len(arqs) == 1)
    f0 = arqs[0]
    check('registro com 133 caracteres', len(f0['records'][0]) == 133, len(f0['records'][0]))
    check('header com 43', len(f0['header']) == 43)
    check('visao JPM — a conta da parte respondida pelo cadastro b3-accounts',
          f0['view'] == 'JPM', f0['view'])
    check('nome do arquivo', f0['file_name'] == 'UNWIND_BANCO.txt')
    rec = f0['records'][0]
    check('campo 5: a conta propria', rec[20:28] == '73760009', rec[20:28])
    check('campo 6: papel VENDIDO', rec[28:29] == '1', rec[28:29])
    check('campo 7: a contraparte com os zeros', rec[29:37] == '00041007', rec[29:37])
    check('campo 8: o contrato', rec[37:48] == '26C03202688', rec[37:48])
    check('campo 9: o nocional recomprado em ME', rec[48:64] == '0000000004222742', rec[48:64])
    check('campo 13: a taxa pre em percentual ao ano', rec[100:110] == '1375000000', rec[100:110])
    check('campo 14: taxa termo em BRL -> 1', rec[110:122] == '000100000000')
    # O preview le o template do BANCO, nao o JSON do repositorio: o JSON e a
    # SEED, e a semeadura nao sobrescreve o que ja esta no banco (§434). Um
    # cadastro corrigido no repositorio so alcanca o motor pelo
    # import_file_interpreter_template.py — e e por isso que este teste olha
    # pela porta do motor, e nao pelo arquivo.
    check('o preview mostra cada campo com o rotulo e a origem do CADASTRO',
          any(c['field'] == 'Valor Base a Antecipar' and c['source'] == 'Page' for c in f0['fields']),
          'template do banco desatualizado? rode scripts/import_file_interpreter_template.py')

    print('\n== 5. o Send escreve o arquivo e vira Sent ==')
    out = commands.send([{'athena_id': 'STP-XE-10G5U5X-0-0', 'ref_date': '2026-09-10'}], sid='T000000')
    check('um arquivo gravado', out['count'] == 1 and out['files'][0]['filename'] == 'UNWIND_BANCO.txt')
    escrito = io.open(os.path.join(R.CONECTA_NEW_PATH, 'UNWIND_BANCO.txt'), encoding='utf-8').read().split('\n')
    check('header + um registro', len(escrito) == 2 and len(escrito[1]) == 133)
    check('e o registro e o mesmo do preview', escrito[1] == rec)
    _f, l4, i4 = queries.find('STP-XE-10G5U5X-0-0', '2026-09-10')
    check('a linha virou Sent', l4[i4]['Status'] == 'Sent' and l4[i4]['SentFiles'] == ['UNWIND_BANCO.txt'])
    try:
        commands.delete('STP-XE-10G5U5X-0-0', '2026-09-10')
        check('linha enviada NAO se apaga', False)
    except ValueError as exc:
        check('linha enviada NAO se apaga', 'already sent' in str(exc))
    try:
        commands.send([{'athena_id': 'STP-XE-10G5U5X-0-0', 'ref_date': '2026-09-10'}])
        check('e nao se envia de novo', False)
    except ValueError as exc:
        check('e nao se envia de novo', 'status Sent' in str(exc))

    print('\n== 6. sem contrato na posicao, nada sai ==')
    R._lpndf_collect = _collect([])
    out2 = commands.import_email(HTML, SUBJECT, ref_dt=date(2026, 9, 11))
    codigos = {a['code'] for a in out2['warnings']}
    check('avisa que nao achou o contrato', 'unwind_no_contract' in codigos, sorted(codigos))
    check('o Check nao vira OK por omissao', out2['rows'][0]['Check'] != 'OK')
    try:
        commands.send([{'athena_id': 'STP-XE-10G5U5X-0-0', 'ref_date': '2026-09-11'}])
        check('o Send recusa o lote dizendo o que falta', False)
    except ValueError as exc:
        check('o Send recusa o lote dizendo o que falta',
              'Nothing sent' in str(exc) and 'Contrato' in str(exc), str(exc))
    check('e nada foi escrito por cima',
          len(io.open(os.path.join(R.CONECTA_NEW_PATH, 'UNWIND_BANCO.txt'), encoding='utf-8').read().split('\n')) == 2)

    print('\n== 7. o rotulo do sino tem destino nos TRES mapas (§8) ==')
    # O `check_notif_page_url` casa por LITERAL e nao ve o rotulo que vai numa
    # constante (`PAGE`): passou verde com o mapa vazio. Sem entrada aqui, o
    # aviso aparece no sino e o clique nao vai a lugar nenhum.
    from apps.pages.platform import notifications as _notif
    check('_NOTIF_PAGE_URL', _notif._NOTIF_PAGE_URL.get(commands.PAGE) == '/unwinds/ndf/fx')
    for arq in ('apps/templates/partials/topbar.html', 'apps/static/js/sw-push.js'):
        txt = io.open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))), arq), encoding='utf-8').read()
        check(arq.split('/')[-1],
              ("'" + commands.PAGE + "'") in txt and '/unwinds/ndf/fx' in txt)

    print('\n== 8. o dropzone le .msg, .eml e o corpo solto ==')
    # A mesa arrasta o e-mail do Outlook: pedir que ela o salvasse como HTML
    # antes era uma etapa manual que as paginas de New Deals nao pedem. E quem
    # decide o formato e o CONTEUDO, nao a extensao — o Outlook renomeia
    # anexo, e um `.msg` chega como `.txt` sem aviso.
    from apps.pages.features.unwinds.infra import email_file
    import email.message as _emsg

    eml = _emsg.EmailMessage()
    eml['Subject'] = SUBJECT
    eml['From'] = 'athena@jpmorgan.com'
    eml.set_content('sem html')
    eml.add_alternative(HTML, subtype='html')
    bytes_eml = eml.as_bytes()

    html_eml, assunto_eml = email_file.ler('qualquer-nome.eml', bytes_eml)
    check('o .eml devolve o corpo HTML', 'Before Unwind' in html_eml)
    check('e o ASSUNTO do proprio e-mail (nao o nome do arquivo)',
          assunto_eml == SUBJECT, assunto_eml)
    # Extensao errada nao muda nada: quem decide e o conteudo.
    _h2, _a2 = email_file.ler('renomeado.txt', bytes_eml)
    check('o mesmo .eml com extensao .txt continua sendo lido',
          _a2 == SUBJECT and 'Before Unwind' in _h2)

    # O .eml que o Outlook EXPORTA nao e o do EmailMessage acima: corpo em
    # quoted-printable, assunto em RFC 2047 e headers DOBRADOS. E a unica
    # forma que a mesa vai arrastar de verdade.
    import quopri
    outlook_eml = (
        'Received: from mail.jpmorgan.com\r\n\tby EXCH01; Wed, 10 Sep 2026 09:14:02 -0300\r\n'
        'MIME-Version: 1.0\r\n'
        'Content-Type: text/html; charset="utf-8"\r\n'
        'Content-Transfer-Encoding: quoted-printable\r\n'
        'Subject: =?utf-8?Q?BRL_NDF_Unwind_Notification=5FSTP-XE-10G5U5X-0-0=5FE5VL-3ICSK0W?=\r\n'
        'From: athena@jpmorgan.com\r\n\r\n'
        + quopri.encodestring(HTML.encode('utf-8')).decode('ascii')
    ).encode('utf-8')
    h_out, a_out = email_file.ler('Mensagem do Outlook.eml', outlook_eml)
    check('o .eml do Outlook: quoted-printable decodificado',
          'Before Unwind' in h_out and 'Calculated' in h_out)
    check('e o assunto RFC 2047 volta legivel', a_out == SUBJECT, a_out)
    check('arquivo SEM extensao nenhuma tambem e lido',
          email_file.ler('sem-extensao', outlook_eml)[1] == SUBJECT)

    corpo, assunto_corpo = email_file.ler('unwind.htm', HTML.encode('utf-8'))
    check('o corpo solto passa direto', 'Before Unwind' in corpo)
    check('e nao inventa assunto (quem chama cai para o nome do arquivo)',
          assunto_corpo == '', repr(assunto_corpo))

    _vazio = _erro(email_file.ler, 'x.msg', b'')
    check('arquivo vazio recusa dizendo o motivo',
          _vazio == 'the file is empty', _vazio)
    _grande = _erro(email_file.ler, 'x.msg',
                    b'\xd0\xcf\x11\xe0' + b'0' * email_file.MAX_BYTES)
    check('arquivo grande demais recusa antes de parsear',
          _grande == 'file too large', _grande)
    # `.msg` de verdade: o magic do Compound File Binary e o que o identifica.
    check('lixo com o magic de .msg falha como .msg, nao como corpo HTML',
          (_erro(email_file.ler, 'x.msg', b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1' + b'lixo') or '')
          .startswith('could not read the .msg'))

    # E o caminho inteiro pelo comando, que e o que a tela chama.
    R._lpndf_collect = _collect([POS])
    out_eml = commands.import_email_upload('seja-la-o-nome.eml', bytes_eml,
                                           ref_dt=date(2026, 9, 10))
    check('o import do .eml chega na mesma linha',
          out_eml['rows'][0]['AthenaID'] == 'STP-XE-10G5U5X-0-0'
          and out_eml['rows'][0]['Contract'] == '26C03202688')

    print('\n== 9. a recompra tem card proprio no painel ==')
    # O painel varre `cache/new deals/`, e a recompra grava em `cache/unwinds/`:
    # sem fonte propria ela simplesmente nao aparece. E o card e PROPRIO porque
    # recompra nao e registro novo — somada ao card do produto, o numero passaria
    # a querer dizer duas coisas.
    #
    # Mede pela DIFERENCA: as secoes acima ja deixaram linhas na arvore, e uma
    # expectativa absoluta aqui passaria a depender da ordem delas.
    from datetime import datetime as _dtm
    hoje = _dtm(2026, 9, 10)
    R._lpndf_collect = _collect([POS])
    with app.test_request_context():
        antes_all = queries.dashboard_counts('all', hoje)
        antes_mes = queries.dashboard_counts('month', hoje)
    commands.import_email(HTML.replace('STP-XE-10G5U5X-0-0', 'STP-ZZ-9999999-0-0'),
                          'BRL NDF Unwind Notification_STP-ZZ-9999999-0-0_X',
                          ref_dt=date(2026, 8, 20))
    commands.import_email(HTML.replace('STP-XE-10G5U5X-0-0', 'STP-YY-8888888-0-0'),
                          'BRL NDF Unwind Notification_STP-YY-8888888-0-0_X',
                          ref_dt=date(2026, 9, 10))
    with app.test_request_context():
        todo = queries.dashboard_counts('all', hoje)
        ano = queries.dashboard_counts('year', hoje)
        mes = queries.dashboard_counts('month', hoje)
    check('as duas novas entraram no periodo todo',
          todo['total'] - antes_all['total'] == 2, (antes_all, todo))
    check('mas so a de setembro entrou no MES',
          mes['total'] - antes_mes['total'] == 1, (antes_mes, mes))
    check('o ano pega as duas', ano['total'] == todo['total'], (ano, todo))
    check('a serie mensal poe cada uma no seu mes',
          (todo['monthly'][7] - antes_all['monthly'][7],
           todo['monthly'][8] - antes_all['monthly'][8]) == (1, 1), todo['monthly'])
    check('a serie mensal NAO muda com o periodo pedido',
          mes['monthly'] == todo['monthly'])
    # Uma recompra e UMA linha: nao ha perna espelhada a descartar, como no
    # intragrupo de New Deals — o re-import da MESMA nao soma.
    commands.import_email(HTML.replace('STP-XE-10G5U5X-0-0', 'STP-YY-8888888-0-0'),
                          'BRL NDF Unwind Notification_STP-YY-8888888-0-0_X',
                          ref_dt=date(2026, 9, 10))
    with app.test_request_context():
        denovo = queries.dashboard_counts('all', hoje)
    check('re-import da mesma recompra nao soma de novo',
          denovo['total'] == todo['total'], (todo, denovo))
    check('e a arvore contada e a do tmp, nao a da maquina',
          todo['total'] < 20, todo)

    print('\n== 10. a recompra aparece no New Deals Monitor ==')
    # O arquivo-dia mora FORA de `cache/new deals/` (§454), entao o Monitor so
    # a ve se varrer a outra arvore — e com o pkey PREFIXADO, senao um `NDF/FX`
    # de la cairia no mesmo balde de um `NDF/FX` criado aqui.
    from apps.pages.features.deals_monitor import domain as NDM
    from apps.pages.features.deals_monitor import queries as ndm_q

    card = next((c for c in NDM._NDM_CARDS if c['key'] == 'unwind-ndf-fx'), None)
    check('existe card para a recompra', bool(card))
    check('e ele aponta para a pagina', (card or {}).get('url') == '/unwinds/ndf/fx')
    check('a pasta do card leva o prefixo',
          (card or {}).get('dirs') == (NDM.PREFIXO_UNWIND + 'NDF/FX',), (card or {}).get('dirs'))
    check('a chave NAO e de Intrag (recompra e registro na B3)',
          not (card or {}).get('key', '').startswith('intrag-'))
    check('tem taxonomia (senao o e-mail parte o rotulo em duas palavras)',
          NDM._NDM_TAXONOMY.get('unwind-ndf-fx') == ('NDF', 'Unwind FX'))
    check('e esta num grupo do GROUPS da tela',
          "'unwind-ndf-fx'" in io.open(os.path.join(
              os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
              'apps', 'templates', 'pages', 'new-deals-monitor.html'),
              encoding='utf-8').read())

    # O snapshot de verdade, com a linha gravada no arquivo-dia.
    from apps.pages.data_paths import unwinds_cache_root
    import apps.pages.data_paths as _dp
    _dp.unwinds_cache_root = persistence.cache_root
    import apps.pages.features.deals_monitor.queries as _q
    _q.unwinds_cache_root = persistence.cache_root
    with app.test_request_context():
        cards, _conf = ndm_q._ndm_monitor_snapshot(_dtm(2026, 9, 10))
    c10 = next((c for c in cards if c['key'] == 'unwind-ndf-fx'), None)
    check('o card conta a recompra do dia', bool(c10) and c10['total'] >= 1,
          c10 and c10['total'])
    _extras = [c['key'] for c in cards if c['key'].startswith('extra-') and 'ndf' in c['key']]
    check('e NAO nasceu um card generico "extra-" ao lado', not _extras, _extras)

    # A pendencia: `Sent` e o estado FECHADO desta recompra (o B3 ID de volta
    # ainda nao existe para ela). Sem o `done`, toda recompra ja enviada
    # apareceria no aviso das 19h todos os dias.
    check('o card declara onde fecha', c10 and c10.get('done') == ['Sent'], c10 and c10.get('done'))
    fp10, l10, i10 = queries.find('STP-XE-10G5U5X-0-0', '2026-09-10')
    for e in l10:
        e['Status'] = 'Sent'
    persistence.save(fp10, l10)
    with app.test_request_context():
        blocos, _tot = ndm_q._ndm_pending_blocks(_dtm(2026, 9, 10))
    pend = [r for b in blocos for r in b['rows'] if r['detail'] == 'Unwind FX']
    check('recompra ENVIADA sai da pendencia do aviso', not pend, pend)
    for e in l10:
        e['Status'] = 'Imported'
    persistence.save(fp10, l10)
    with app.test_request_context():
        blocos2, _t2 = ndm_q._ndm_pending_blocks(_dtm(2026, 9, 10))
    pend2 = [(b['type'], r) for b in blocos2 for r in b['rows'] if r['detail'] == 'Unwind FX']
    check('e recompra IMPORTADA entra', bool(pend2), pend2)
    check('na zona Registration, nao na de Intrag',
          pend2 and pend2[0][0] == 'Registration', pend2 and pend2[0][0])

    print('\n== 11. a pagina responde e as APIs tambem ==')
    R._lpndf_collect = _collect([POS])
    cl = app.test_client()
    with cl.session_transaction() as ss:
        ss['authenticated'] = True
        ss['user_sid'] = 'T000000'
        ss['user_name'] = 'Teste'
        # UTC: o `session_expires_at` e comparado em UTC, e o horario local
        # faria a sessao parecer expirada.
        ss['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()
    pg = cl.get('/unwinds/ndf/fx')
    corpo = pg.data.decode('utf-8')
    check('a pagina abre', pg.status_code == 200, pg.status_code)
    check('com a tabela e o dropzone', 'id="unw-table"' in corpo and 'myAwesomeDropzone' in corpo)
    # UM botao de Import, e a varredura do box e a rota automatica dele quando
    # a dropzone esta vazia — o mesmo desenho do NDF/Opt Commodities. Um
    # 'Scan Box' proprio fazia a mesa escolher entre dois caminhos que levam
    # ao mesmo lugar.
    check('nao existe botao Scan Box separado', 'scanBtn' not in corpo)
    check('e o Import cai no runScan com a dropzone vazia',
          'if (!files.length) { return runScan(); }' in corpo)
    api = cl.get('/api/unwinds/ndf/fx?date=2026-09-10').get_json()
    # A secao 8 deixou outra recompra neste mesmo dia: o que se prende aqui e
    # que a linha ESTA na resposta, nao quantas ha no arquivo-dia.
    check('o GET devolve a linha e o contrato de colunas',
          api.get('success')
          and 'STP-XE-10G5U5X-0-0' in [e.get('AthenaID') for e in api['entries']]
          and api['fields'] == list(domain.UNW_FIELDS)
          and len(api['labels']) == len(domain.UNW_FIELDS), api.get('entries'))
    # O cabecalho e montado por JS a partir do UNW_COLS da pagina; o que se
    # prende aqui e que essa copia do contrato nao saiu da ordem do dominio.
    import re as _re
    js = _re.search(r'var UNW_COLS = \[(.*?)\];', corpo, _re.S).group(1)
    check('a copia do contrato na tela esta na ordem do dominio',
          _re.findall(r"\['([A-Za-z0-9]+)'", js) == list(domain.UNW_FIELDS))
    prev = cl.get('/api/unwinds/ndf/fx/preview?athena_id=STP-XE-10G5U5X-0-0&date=2026-09-10').get_json()
    check('o preview responde 133', prev.get('success') and len(prev['files'][0]['records'][0]) == 133)
    sub = cl.post('/api/unwinds/ndf/fx/import-file',
                  data={'file': (io.BytesIO(HTML.encode('utf-8')), 'unwind.htm'), 'date': '2026-09-12'},
                  content_type='multipart/form-data').get_json()
    check('o dropzone importa o corpo do e-mail',
          sub.get('success') and sub['rows'][0]['Contract'] == '26C03202688')
    dele = cl.post('/api/unwinds/ndf/fx/delete',
                   json={'athena_id': 'STP-XE-10G5U5X-0-0', 'date': '2026-09-12'}).get_json()
    check('e o delete remove a linha nao enviada', dele.get('success'))
    check('o dia ficou vazio', queries.entries('2026-09-12') == [])

    print('\n== 12. os quatro botoes padrao e o 4-olhos da edicao ==')
    # Os botoes da linha sao os da casa (§7): Confirm, Edit, Delete, Send. O
    # olho e o documento saiam daqui — o preview e o DUPLO CLIQUE e o Termo de
    # Resilicao se gera no Confirmations Monitor.
    check('a linha tem os quatro botoes padrao',
          all(c in corpo for c in ('btn-row-approve', 'btn-row-edit',
                                   'btn-row-delete', 'btn-row-send')))
    check('e nao tem mais o olho nem o documento',
          'btn-row-preview' not in corpo and 'btn-row-termo' not in corpo)
    check('o preview continua no duplo clique', "on('dblclick', 'tr'" in corpo)
    # O Status e a PRIMEIRA coluna de dado: no fim de dezoito colunas a
    # resposta "esta linha ja foi?" so aparece depois de rolar a grade toda.
    check('o Status e a primeira coluna de dado', domain.UNW_FIELDS[0] == 'Status',
          domain.UNW_FIELDS[0])

    # Editar poe em Pending e marca o maker; quem confirma tem de ser OUTRO.
    ed = cl.post('/api/unwinds/ndf/fx/edit',
                 json={'athena_id': 'STP-XE-10G5U5X-0-0', 'date': '2026-09-11',
                       'fields': {'SettlementDate': '2026-09-15', 'Check': 'OK',
                                  'Status': 'Sent'}}).get_json()
    check('a edicao grava e poe em Pending',
          ed.get('success') and ed.get('status') == domain.STATUS_PENDENTE, ed)
    _fp, _lst, _i = queries.find('STP-XE-10G5U5X-0-0', '2026-09-11')
    linha = _lst[_i] if _i is not None else {}
    check('o campo editado entrou', linha.get('SettlementDate') == '2026-09-15',
          linha.get('SettlementDate'))
    # O `Status` e o `Check` vao na mesma requisicao de proposito: um e estado
    # da esteira e o outro e veredito apurado, e nenhum dos dois se digita.
    check('o Status mandado pela tela nao vence o da esteira',
          linha.get('Status') == domain.STATUS_PENDENTE, linha.get('Status'))
    check('o veredito Check nao se edita', linha.get('Check') != 'OK', linha.get('Check'))
    check('o maker ficou registrado', linha.get('Maker') == 'T000000', linha.get('Maker'))

    # Pending NAO vai para a B3: e o gate inteiro.
    check('recompra Pending nao e enviavel',
          domain.STATUS_PENDENTE not in domain.STATUS_ENVIAVEL)
    _err = _erro(commands.send,
                 [{'athena_id': 'STP-XE-10G5U5X-0-0', 'ref_date': '2026-09-11'}], sid='T111111')
    check('e o Send recusa dizendo o status', _err and 'Pending' in _err, _err)

    mesmo = cl.post('/api/unwinds/ndf/fx/approve',
                    json={'athena_id': 'STP-XE-10G5U5X-0-0', 'date': '2026-09-11'})
    check('o proprio maker nao confirma', mesmo.status_code == 403, mesmo.status_code)
    check('e o erro vai por CODIGO, nao por frase',
          (mesmo.get_json() or {}).get('code') == 'unwind_maker_is_checker',
          mesmo.get_json())

    cl2 = app.test_client()
    with cl2.session_transaction() as ss:
        ss['authenticated'] = True
        ss['user_sid'] = 'T999999'
        ss['user_name'] = 'Outro'
        ss['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()
    outro = cl2.post('/api/unwinds/ndf/fx/approve',
                     json={'athena_id': 'STP-XE-10G5U5X-0-0', 'date': '2026-09-11'}).get_json()
    check('outro usuario confirma', outro.get('success')
          and outro.get('status') == domain.STATUS_APROVADO, outro)
    _fp, _lst, _i = queries.find('STP-XE-10G5U5X-0-0', '2026-09-11')
    check('e o checker ficou registrado',
          _i is not None and _lst[_i].get('Checker') == 'T999999',
          _i is not None and _lst[_i].get('Checker'))
    check('confirmar de novo nao faz sentido e o diz',
          cl2.post('/api/unwinds/ndf/fx/approve',
                   json={'athena_id': 'STP-XE-10G5U5X-0-0', 'date': '2026-09-11'}).status_code == 400)
    check('e Approved volta a ser enviavel',
          domain.STATUS_APROVADO in domain.STATUS_ENVIAVEL)

    # TODA acao da pagina toca o sino, que e onde a mesa ve o que os outros
    # fizeram no arquivo-dia. O `dry_run` e a excecao de proposito: e a
    # pergunta das duplicatas do primeiro passo do Import, e nada foi gravado.
    avisos = []
    _orig_notif = R._create_notification
    R._create_notification = lambda *a, **k: avisos.append(a[2:4])
    try:
        cl.post('/api/unwinds/ndf/fx/import-file?dry_run=1',
                data={'file': (io.BytesIO(HTML.encode('utf-8')), 'unwind.htm'),
                      'date': '2026-09-16'}, content_type='multipart/form-data')
        check('o dry_run do Import NAO avisa', avisos == [], avisos)
        cl.post('/api/unwinds/ndf/fx/import-file',
                data={'file': (io.BytesIO(HTML.encode('utf-8')), 'unwind.htm'),
                      'date': '2026-09-16'}, content_type='multipart/form-data')
        check('o Import avisa', avisos and avisos[-1] == ('Deals Imported', commands.PAGE), avisos)
        cl.post('/api/unwinds/ndf/fx/delete',
                json={'athena_id': 'STP-XE-10G5U5X-0-0', 'date': '2026-09-16'})
        check('o Delete avisa', avisos and avisos[-1] == ('Deal Deleted', commands.PAGE), avisos)
    finally:
        R._create_notification = _orig_notif

    print('\n== 13. a recompra projetada no NDF Cockpit ==')
    # A mesa acompanha liquidacao e IR pelo Cockpit, e a recompra nao vem da
    # API: a vertical a PROJETA no arquivo-dia do Cockpit da DATA DE
    # LIQUIDACAO, marcada com `_nc_unwind`.
    from apps.pages import data_store as _ds
    jp_ck = R._ndfc_json_path(date(2026, 9, 10))
    recs = _ds.read(jp_ck) if _ds.isfile(jp_ck) else []
    unw = [r for r in recs if r.get('_nc_unwind')]
    check('o import escreveu a recompra no dia do Cockpit', len(unw) == 1, len(recs))
    if unw:
        r = unw[0]
        check('com o Athena ID no ID_SOURCE_DEAL',
              r['ID_SOURCE_DEAL'] == 'STP-XE-10G5U5X-0-0', r['ID_SOURCE_DEAL'])
        check('o contrato da B3 na coluna do CETIP',
              r['CD_CETIP_RETURN'] == '26C03202688', r['CD_CETIP_RETURN'])
        # RECEIVE e positivo, PAY e negativo — a convencao do Summary, e o sinal
        # vem da direcao APURADA (o sinal do resultado), nunca do campo do
        # e-mail (§488).
        _lin = (queries.find('STP-XE-10G5U5X-0-0', '2026-09-10')[1] or [{}])
        _dir = (_lin[queries.find('STP-XE-10G5U5X-0-0', '2026-09-10')[2]] or {}).get('Direction')
        _neg = r['[PROD] Cockpit.SETTLEMENT'].startswith('-')
        check('o caixa com o SINAL da direcao apurada',
              _neg == (_dir == 'PAY'), (_dir, r['[PROD] Cockpit.SETTLEMENT']))
        check('o IR nasce VAZIO (quem calcula e o dia inteiro montado)',
              r['VL_TAX_INCOME'] == '', r['VL_TAX_INCOME'])
        check('e a chave e derivada do Athena ID',
              r['_nc_id'] == commands.COCKPIT_ID_PREFIX + 'STP-XE-10G5U5X-0-0', r['_nc_id'])
    # Reimportar ATUALIZA a mesma linha — nao cria uma segunda.
    commands.import_email(HTML, SUBJECT, ref_dt=HOJE)
    recs2 = _ds.read(jp_ck) if _ds.isfile(jp_ck) else []
    check('reimportar nao duplica a linha do Cockpit',
          len([r for r in recs2 if r.get('_nc_unwind')]) == 1, len(recs2))
    # E o import do COCKPIT preserva a recompra ao reescrever o dia: ele monta
    # o dia inteiro a partir da API, onde a recompra nao existe.
    do_zero = [{'ID_SOURCE_DEAL': 'OUTRO', '_nc_id': 'X1'}]
    R._ndfc_keep_unwinds(date(2026, 9, 10), do_zero)
    check('o reimport do Cockpit PRESERVA a recompra',
          [r.get('_nc_id') for r in do_zero if r.get('_nc_unwind')]
          == [commands.COCKPIT_ID_PREFIX + 'STP-XE-10G5U5X-0-0'],
          [r.get('_nc_id') for r in do_zero])

    print('\n== 14. a varredura do box roda sozinha ==')
    # A tela promete "also runs on its own every 30 minutes". Ate 18/09/2026 a
    # frase era falsa: nenhum laco estava registrado, e a recompra so entrava
    # no clique do Import — sem erro nenhum para denunciar isso.
    check('o laco esta registrado no wiring do routes',
          any(l == 'unwind-boxscan' for l, _ in R._SCHEDULERS),
          [l for l, _ in R._SCHEDULERS])
    from apps.pages.features.unwinds import entrypoint as _unw_ep
    check('e o entrypoint expoe o mesmo start_scheduler',
          _unw_ep.start_scheduler is commands.start_scheduler)
    check('o intervalo e o mesmo do box de New Deals (BOX_SCAN_POLL_MIN)',
          commands.POLL_MIN == int(os.getenv('BOX_SCAN_POLL_MIN', '30') or 30),
          commands.POLL_MIN)
    # Varredura VAZIA nao avisa ninguem: o laco roda o dia inteiro e a caixa
    # esta vazia quase sempre. Um sino a cada 30 min seria o fim do sino.
    avisos = []
    _orig_notif = R._create_notification
    R._create_notification = lambda *a, **k: avisos.append(a)
    try:
        commands._avisar_varredura({'rows': [], 'failed': [], 'scanned': 0})
        check('caixa vazia nao toca o sino', avisos == [], avisos)
        commands._avisar_varredura({'rows': [{'AthenaID': 'X'}], 'failed': [],
                                    'scanned': 1})
        check('recompra importada toca o sino', len(avisos) == 1, avisos)
        check('e o rotulo da pagina e o dos tres mapas',
              avisos and avisos[0][3] == commands.PAGE, avisos)
    finally:
        R._create_notification = _orig_notif

    print('')
    if FALHAS:
        print('FALHAS (%d): %s' % (len(FALHAS), ', '.join(FALHAS)))
        return 1
    print('tudo ok')
    return 0


if __name__ == '__main__':
    sys.exit(main())
