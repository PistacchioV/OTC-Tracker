# -*- coding: utf-8 -*-
"""Confirmations Escalation (card do Control Panel): quem entra em cada e-mail.

A rotina cobra validação em nome da mesa, e as quatro formas de ela ficar errada
sem dar erro nenhum são as que este script prende:

  1. **o grupo de Front Office** — o produto casa pelo TIPO DE CONFIRMAÇÃO
     (`confirmation_type`), não pelo texto cru da coluna. 'OPTION EDG' NÃO é um
     produto: é a opção de câmbio na LOB EDG, cujo tipo é `FXO`. Cadastrado como
     produto, o grupo nunca casaria com linha nenhuma — e-mail vazio todo dia,
     sem erro no log;
  2. **quem não casa não some calado** — Pending FO fora dos grupos cadastrados vai
     para `unmatched`, que o card mostra. Silêncio aqui é confirmação que nunca
     é cobrada;
  3. **a escalação é o ÚLTIMO DIA ou o vencido**, nunca a véspera: `warn` acende
     um dia antes, e escalar aí chegaria com a mesa ainda dentro do prazo;
  4. **segunda e quinta ROLAM** para o próximo dia útil ANBIMA. A pergunta é
     feita ao contrário (que segunda/quinta desemboca em hoje?) — olhar só o dia
     da semana de hoje perderia a semana inteira quando a quinta cai em feriado.

Mais o contrato dos e-mails: os assuntos por extenso e a lista PRÓPRIA de cada um (é o que a mesa
filtra na caixa de entrada), a data de envio para validação com a cadeia de
fallback das linhas antigas, e o template com as sete colunas + o botão para o
Confirmations Monitor.

Não encosta em dado real: a esteira é stubada (`load_all`), nenhum e-mail é
montado ou enviado (`_ce_send_email` é substituído) e o template é renderizado
por um Jinja próprio, sem Flask.
"""
import io
import os
import sys
from datetime import date, datetime, timedelta

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from apps.pages import routes as R                          # noqa: E402
from apps.pages import manual_conf as M                     # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label +
          ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


# ── 1. os assuntos, por extenso ─────────────────────────────────────────────
print('== 1. os assuntos que a mesa pediu ==')
check('OTC', R._CE_SUBJECT_OTC, 'Confirmations Pending Validation - OTC')
check('MO', R._CE_SUBJECT_MO, 'Confirmations Pending Validation - MO')
subj = {g['id']: g['subject'] for g in R._CE_FO_GROUPS}
check('FO · CEM Swap', subj.get('cem-swap'),
      'Confirmations Pending Validation - FO - CEM Swap')
check('FO · EDG Swap', subj.get('edg-swap'),
      'Confirmations Pending Validation - FO - EDG Swap')
check('FO · EDG Corporate Swap', subj.get('edg-corp-swap'),
      'Confirmations Pending Validation - FO - EDG Swap')
check('FO · EDG Option', subj.get('edg-option'),
      'Confirmations Pending Validation - FO - EDG Option')
# Assunto e corpo no MESMO idioma: um assunto em português sobre um corpo em
# inglês era a única coisa bilíngue do e-mail.
check('   os cinco em inglês, sem acento no cabeçalho',
      all(s.isascii()
          for s in [R._CE_SUBJECT_OTC, R._CE_SUBJECT_MO] + list(subj.values())), True)
# SWAP e SWAP CORPORATE da EDG chegaram a ser um grupo só (mesmo assunto); são
# separados porque quem RECEBE cada um é diferente. Uma lista por e-mail.
check('cada grupo do FO tem lista própria',
      sorted(g['rec'] for g in R._CE_FO_GROUPS),
      ['fo_cem_swap', 'fo_edg_corp_swap', 'fo_edg_option', 'fo_edg_swap'])
check('   e todas as listas do card são conhecidas do servidor',
      sorted(R._CE_REC_KEYS),
      sorted(['otc_to', 'sales_to', 'sales_escalation',
              'fo_cem_swap', 'fo_edg_swap', 'fo_edg_corp_swap', 'fo_edg_option']))


# ── 2. o casamento produto × LOB ────────────────────────────────────────────
print('\n== 2. o grupo de Front Office da linha ==')


def grupo(produto, lob):
    return R._ce_fo_group_id({'Produto': produto, 'LOB': lob})


check('SWAP × CEM', grupo('SWAP', 'CEM'), 'cem-swap')
check('SWAP × EDG', grupo('SWAP', 'EDG'), 'edg-swap')
check('SWAP CORPORATE × EDG é OUTRO grupo', grupo('SWAP CORPORATE', 'EDG'),
      'edg-corp-swap')
check('FXO × EDG', grupo('FXO', 'EDG'), 'edg-option')
# 'OPTION' é o nome que o New Deals grava; o tipo dela é FXO. Era ele que fazia
# a linha de opção de câmbio ficar de fora do grupo em silêncio.
check("   'OPTION' × EDG é a MESMA coisa que FXO × EDG",
      grupo('OPTION', 'EDG'), 'edg-option')
check('   e a caixa/acento não decidem nada', grupo(' swap corporate ', 'edg'),
      'edg-corp-swap')
check('SWAP CORPORATE × CEM não entra no CEM Swap', grupo('SWAP CORPORATE', 'CEM'), '')
check('FXO × CEM não tem grupo', grupo('FXO', 'CEM'), '')
check('NDF COMM × CEM não tem grupo', grupo('NDF COMM', 'CEM'), '')


# ── 3. a data de envio para validação ───────────────────────────────────────
print('\n== 3. quando a confirmação chegou na mesa ==')
check('a coluna do MO/FO manda',
      R._ce_sent_date({'Data envio validação MO/FO': '10/08/2026',
                       'Conferido OTC': '09/08/2026',
                       'Data envio validação OTC': '05/08/2026'}), '10/08/2026')
# A linha antiga entrou na esteira antes desse carimbo: sem a cadeia, a coluna
# sairia vazia justamente nas confirmações mais velhas — as que o e-mail cobra.
check('   sem ela, o Conferido OTC',
      R._ce_sent_date({'Conferido OTC': '09/08/2026',
                       'Data envio validação OTC': '05/08/2026'}), '09/08/2026')
check('   sem os dois, o envio para o OTC',
      R._ce_sent_date({'Data envio validação OTC': '05/08/2026'}), '05/08/2026')
check('   sem nenhum, vazio (e não uma data inventada)', R._ce_sent_date({}), '')


# ── 4. o retrato da fila ────────────────────────────────────────────────────
print('\n== 4. quem entra em cada e-mail ==')

HOJE = date(2026, 8, 12)                                    # quarta-feira


def _sub_biz(d, n):
    """`d` recuado em n dias ÚTEIS ANBIMA (o inverso do `_add_bizdays`)."""
    hols = M._anbima_holidays()
    cur, left = d, n
    while left > 0:
        cur -= timedelta(days=1)
        if cur.weekday() < 5 and cur.strftime('%Y-%m-%d') not in hols:
            left -= 1
    return cur


def linha(trade, pending, cliente, produto, lob, trade_id, ativo='USD'):
    return {'Pending': pending, 'Cliente': cliente, 'Produto': produto, 'LOB': lob,
            'Trade ID': trade_id, 'Moeda': ativo,
            'Data Operação': M.fmt_date(trade),
            'Data envio validação MO/FO': M.fmt_date(trade),
            'Conferido OTC': M.fmt_date(trade), 'VALIDADO p/ MO': '',
            'VALIDADO p/ FO': ''}


SLA_MO = M.SLA_BIZDAYS[M.STAGE_MO]
# Prazo do MO = trade date + 4 dias úteis. Recuando o trade date, escolhe-se
# exatamente onde a linha cai contra o prazo de HOJE.
T_VENCIDA = _sub_biz(HOJE, SLA_MO + 2)                      # deadline já passou
T_ULTIMO = _sub_biz(HOJE, SLA_MO)                           # deadline é hoje
T_VESPERA = _sub_biz(HOJE, SLA_MO - 1)                      # falta 1 dia
T_FOLGA = HOJE                                              # sobra o prazo todo

ROWS = [
    linha(T_VENCIDA, M.PENDING_MO, 'CLIENTE VENCIDO', 'FXO', 'CEM', 'T1'),
    linha(T_ULTIMO, M.PENDING_MO, 'CLIENTE ULTIMO DIA', 'FXO', 'CEM', 'T2'),
    linha(T_VESPERA, M.PENDING_MO, 'CLIENTE VESPERA', 'FXO', 'CEM', 'T3'),
    linha(T_FOLGA, M.PENDING_MO, 'CLIENTE FOLGA', 'FXO', 'CEM', 'T4'),
    # Parada nas DUAS mesas: entra no e-mail do MO E no do FO — é a mesma
    # confirmação devendo duas assinaturas, e mostrá-la só num esconde trabalho.
    linha(T_ULTIMO, M.PENDING_MOFO, 'CLIENTE DOIS', 'SWAP', 'CEM', 'T5'),
    linha(T_FOLGA, M.PENDING_FO, 'CLIENTE FO CORP', 'SWAP CORPORATE', 'EDG', 'T6'),
    linha(T_FOLGA, M.PENDING_FO, 'CLIENTE FO OPT', 'OPTION', 'EDG', 'T7'),
    # Pending FO fora dos grupos cadastrados: NÃO some calado.
    linha(T_FOLGA, M.PENDING_FO, 'CLIENTE SEM GRUPO', 'NDF COMM', 'CEM', 'T8'),
    # A primeira parada da esteira tem e-mail próprio, para a mesa de OTC Ops.
    linha(T_VENCIDA, M.PENDING_OTC, 'CLIENTE NO OTC', 'FXO', 'CEM', 'T9'),
    linha(T_FOLGA, M.PENDING_FO, 'CLIENTE FO SWAP', 'SWAP', 'EDG', 'T12'),
    linha(T_VENCIDA, M.PENDING_LEGAL, 'CLIENTE NO LEGAL', 'FXO', 'CEM', 'T10'),
    linha(T_VENCIDA, M.STATUS_OK, 'CLIENTE FECHADO', 'FXO', 'CEM', 'T11'),
]

_load_all, _sla_days = M.load_all, M.sla_days
try:
    M.load_all = lambda: [dict(r) for r in ROWS]
    M.sla_days = lambda: dict(M.SLA_BIZDAYS)                # sem depender do cadastro
    otc, mo, grupos, esc, sem_grupo = R._ce_snapshot(HOJE)
    por_id = {g['id']: g for g in grupos}

    check('o e-mail do MO leva as paradas em MO e em MO/FO',
          sorted(r['trade_id'] for r in mo), ['T1', 'T2', 'T3', 'T4', 'T5'])
    check('   e nada de Pending OTC / Legal / Ok',
          [r['trade_id'] for r in mo if r['trade_id'] in ('T9', 'T10', 'T11')], [])
    check('o e-mail do OTC leva só o que está em Pending OTC',
          [r['trade_id'] for r in otc], ['T9'])
    # Pending Legal é hold manual: a confirmação está parada por decisão de
    # alguém, e cobrar o OTC por ela seria cobrar o trabalho errado.
    check('   e o hold do Legal fica de fora',
          'T10' in [r['trade_id'] for r in otc], False)
    check('CEM Swap leva a que está nas duas mesas',
          [r['trade_id'] for r in por_id['cem-swap']['rows']], ['T5'])
    check('EDG Swap leva o SWAP comum',
          [r['trade_id'] for r in por_id['edg-swap']['rows']], ['T12'])
    check('EDG Corporate Swap é um e-mail à parte',
          [r['trade_id'] for r in por_id['edg-corp-swap']['rows']], ['T6'])
    check('EDG Option leva a opção de câmbio',
          [r['trade_id'] for r in por_id['edg-option']['rows']], ['T7'])
    check('Pending FO sem grupo é AVISADO, não descartado',
          sem_grupo, ['NDF COMM · CEM'])

    print('\n== 5. a escalação: último dia e vencido, nunca a véspera ==')
    check('entra o vencido e o do último dia',
          sorted(r['trade_id'] for r in esc), ['T1', 'T2', 'T5'])
    check('   a véspera fica de fora (a mesa ainda tem prazo)',
          'T3' in [r['trade_id'] for r in esc], False)
    check('   e a folgada também', 'T4' in [r['trade_id'] for r in esc], False)
    niveis = {r['trade_id']: (r['level'], r['left']) for r in mo}
    check('   o vencido vem com level=late', niveis['T1'][0], 'late')
    check('   o último dia vem com warn e left=0', niveis['T2'], ('warn', 0))
    check('   a véspera vem com warn e left=1', niveis['T3'], ('warn', 1))

    print('\n== 6. a fila sai da mais antiga para a mais nova ==')
    # Quem espera há mais tempo vem antes; empate desempata pelo cliente, para a
    # ordem não mudar de um disparo para o outro sem nada ter mudado.
    check('mais antiga primeiro, empate pelo cliente',
          [r['trade_id'] for r in mo], ['T1', 'T5', 'T2', 'T3', 'T4'])

    # ── 7. o disparo, com o envio stubado ───────────────────────────────────
    print('\n== 7. o que cada modo manda ==')
    enviados = []
    _send, _rec = R._ce_send_email, R._load_ce_recipients
    try:
        R._ce_send_email = (lambda subject, scope, rows, to_list, ref, escalation=False:
                            enviados.append({'subject': subject, 'scope': scope,
                                             'rows': len(rows), 'to': list(to_list),
                                             'esc': escalation}) or True)
        R._load_ce_recipients = lambda: {'otc_to': 'otc@x.com', 'sales_to': 'sales@x.com',
                                         'sales_escalation': 'boss@x.com',
                                         'fo_cem_swap': 'cem@x.com',
                                         'fo_edg_swap': 'edg@x.com',
                                         'fo_edg_corp_swap': 'corp@x.com',
                                         'fo_edg_option': 'opt@x.com'}

        del enviados[:]
        out = R._ce_run('routine', datetime(2026, 8, 12, 17, 0))
        check('a rotina manda OTC + MO + os quatro grupos de FO',
              [e['subject'] for e in enviados],
              [R._CE_SUBJECT_OTC, R._CE_SUBJECT_MO, subj['cem-swap'], subj['edg-swap'],
               subj['edg-corp-swap'], subj['edg-option']])
        # Uma lista por e-mail: quem cuida do EDG Corporate Swap não recebe a
        # fila do EDG Swap, e o OTC não recebe a do Sales Support.
        check('   cada e-mail vai para a SUA lista',
              [e['to'][0] for e in enviados],
              ['otc@x.com', 'sales@x.com', 'cem@x.com', 'edg@x.com', 'corp@x.com',
               'opt@x.com'])
        check('   a rotina NÃO manda a escalação',
              [e for e in enviados if e['esc']], [])

        del enviados[:]
        out = R._ce_run('escalation', datetime(2026, 8, 12, 17, 0))
        check('a escalação é UM e-mail, para a lista dela',
              [(e['subject'], e['to'], e['rows']) for e in enviados],
              [(R._CE_SUBJECT_MO, ['boss@x.com'], 3)])

        del enviados[:]
        R._ce_run('fo-edg-corp-swap', datetime(2026, 8, 12, 17, 0))
        check('o Run individual manda SÓ o e-mail daquele item',
              [(e['subject'], e['to']) for e in enviados],
              [(subj['edg-corp-swap'], ['corp@x.com'])])
        del enviados[:]
        R._ce_run('mo', datetime(2026, 8, 12, 17, 0))
        check('   idem para o MO', [e['subject'] for e in enviados], [R._CE_SUBJECT_MO])
        del enviados[:]
        R._ce_run('otc', datetime(2026, 8, 12, 17, 0))
        check('   e para o OTC', [(e['subject'], e['to']) for e in enviados],
              [(R._CE_SUBJECT_OTC, ['otc@x.com'])])

        # Nada parado e lista em branco são desfechos DIFERENTES: o primeiro é a
        # rotina rodando bem, o segundo é cobrança que não saiu de casa.
        del enviados[:]
        M.load_all = lambda: []
        out = R._ce_run('routine', datetime(2026, 8, 12, 17, 0))
        check('fila vazia não manda e-mail', enviados, [])
        check('   e o motivo é "empty"',
              sorted({s['reason'] for s in out['skipped']}), ['empty'])

        M.load_all = lambda: [dict(r) for r in ROWS]
        R._load_ce_recipients = lambda: {k: '' for k in R._CE_REC_KEYS}
        del enviados[:]
        out = R._ce_run('routine', datetime(2026, 8, 12, 17, 0))
        check('sem destinatário salvo, nada é enviado', enviados, [])
        check('   e o card recebe "no_recipient", não "empty"',
              'no_recipient' in {s['reason'] for s in out['skipped']}, True)
    finally:
        R._ce_send_email, R._load_ce_recipients = _send, _rec
finally:
    M.load_all, M.sla_days = _load_all, _sla_days


# ── 8. segunda e quinta, rolando o feriado ──────────────────────────────────
print('\n== 8. o dia do relatório agendado ==')
_hols, _loaded = R._ANBIMA_HOLIDAYS, R._anbima_loaded
try:
    R._anbima_loaded = True
    R._ANBIMA_HOLIDAYS = set()
    check('segunda-feira é dia', R._ce_is_routine_day(date(2026, 8, 10)), True)
    check('quinta-feira é dia', R._ce_is_routine_day(date(2026, 8, 13)), True)
    check('terça não é', R._ce_is_routine_day(date(2026, 8, 11)), False)
    check('sexta não é (sem feriado na semana)', R._ce_is_routine_day(date(2026, 8, 14)), False)
    check('sábado nunca é', R._ce_is_routine_day(date(2026, 8, 15)), False)

    # Segunda feriado → o relatório sai na terça, e a segunda não emite.
    R._ANBIMA_HOLIDAYS = {'2026-08-10'}
    check('segunda feriado não emite', R._ce_is_routine_day(date(2026, 8, 10)), False)
    check('   e a terça passa a ser o dia', R._ce_is_routine_day(date(2026, 8, 11)), True)
    check('   sem virar dia também na quarta', R._ce_is_routine_day(date(2026, 8, 12)), False)

    # Quinta feriado → sexta. É este caso que a pergunta ao contrário resolve:
    # olhar só o dia da semana de hoje (sexta) perderia o relatório da semana.
    R._ANBIMA_HOLIDAYS = {'2026-08-13'}
    check('quinta feriado não emite', R._ce_is_routine_day(date(2026, 8, 13)), False)
    check('   e a sexta paga a quinta', R._ce_is_routine_day(date(2026, 8, 14)), True)

    # Dois feriados seguidos rolam de novo.
    R._ANBIMA_HOLIDAYS = {'2026-08-13', '2026-08-14'}
    check('quinta e sexta feriado caem na segunda',
          R._ce_is_routine_day(date(2026, 8, 17)), True)
    check('   e a segunda é UM disparo, não dois',
          sum(1 for d in (date(2026, 8, 17),) if R._ce_is_routine_day(d)), 1)
finally:
    R._ANBIMA_HOLIDAYS, R._anbima_loaded = _hols, _loaded


# ── 9. o template do e-mail ─────────────────────────────────────────────────
print('\n== 9. o template (um só para todos) ==')
from jinja2 import Environment, FileSystemLoader                      # noqa: E402

env = Environment(loader=FileSystemLoader(os.path.join(ROOT, 'apps', 'templates')))
tpl = env.get_template('pages/email-template-confirmations-escalation.html')
html = tpl.render(ref_date_fmt='12/08/2026', scope='Sales Support · MO',
                  rows=[{'trade_date': '05/08/2026', 'client': 'CLIENTE X',
                         'product': 'FXO', 'lob': 'CEM', 'trade_id': 'T1',
                         'asset': 'USD', 'sent': '06/08/2026', 'deadline': '11/08/2026',
                         'level': 'late', 'left': -1}],
                  escalation=False, monitor_url='http://maquina:8050/manual-confirmation/monitor',
                  current_year=2026)
for h in ('Trade Date', 'Client', 'Product', 'LOB', 'Trade ID', 'Asset',
          'Sent for validation'):
    check('a coluna %-20s está no cabeçalho' % h, h in html, True)
check('o logo vem do cid, como nos outros e-mails', 'cid:otc_logo' in html, True)
check('o botão aponta para o Confirmations Monitor',
      'http://maquina:8050/manual-confirmation/monitor' in html, True)
check('   e o rótulo dele é o da página', 'Open the Confirmations Monitor' in html, True)
# A ALTURA do botão vem de height + line-height, e não de padding vertical: o
# Word do Outlook ignora padding em cima/embaixo de link, e sem isso o botão
# volta a ser o retângulo magro que a mesa reclamou duas vezes.
check('   alto por height + line-height, não por padding vertical',
      'height:52px;line-height:52px' in html, True)
check('   e com canto de pílula', 'border-radius:26px' in html, True)
# O Outlook desktop não conhece border-radius: sem o roundrect o canto sai
# quadrado só nele — e é justamente o cliente da mesa.
check('   com o v:roundrect para o Outlook desktop',
      'v:roundrect' in html and 'arcsize="50%"' in html, True)
check('   e o link normal escondido só do Outlook (mso-hide)',
      'mso-hide:all' in html and '[if !mso]' in html, True)
check('a assinatura é a da mesa',
      'OTC Tracker — Brazil OTC Operations' in html, True)
check('a linha vencida sai marcada', 'overdue' in html, True)
esc_html = tpl.render(ref_date_fmt='12/08/2026', scope='Escalation · MO', rows=[],
                      escalation=True, monitor_url='http://x/y', current_year=2026)
check('o e-mail de escalação muda o texto de abertura',
      'last day of the validation deadline' in esc_html, True)
check('   e o da rotina não fala em último dia',
      'last day of the validation deadline' in html, False)


# ── 10. o card e o acesso ───────────────────────────────────────────────────
print('\n== 10. o card no Control Panel ==')
check('o card está registrado',
      [c['label'] for c in R._CONTROL_PANEL_CARDS if c['id'] == 'confescalation'],
      ['Confirmations Escalation'])
# Sem o endpoint no mapa, a rotina roda para quem não tem o card liberado.
for ep in ('/api/control-panel/confirmations-escalation/recipients',
           '/api/control-panel/confirmations-escalation/run'):
    check('%s é barrado pelo card' % ep, R._CP_ENDPOINT_CARD.get(ep), 'confescalation')

CP = io.open(os.path.join(ROOT, 'apps', 'templates', 'pages', 'control-panel.html'),
             encoding='utf-8').read()
# Um Run por e-mail: são os quatro da rotina + a escalação + o "Run all".
modos = set()
for parte in CP.split('data-ce-run="')[1:]:
    modos.add(parte.split('"', 1)[0])
check('a tela tem um Run para cada e-mail', sorted(modos),
      sorted(['routine', 'otc', 'mo', 'escalation'] +
             ['fo-' + g['id'] for g in R._CE_FO_GROUPS]))
# Um campo de destinatário por lista, e o campo tem de EXISTIR: o mapa do JS
# liga a chave do servidor ao id do input, e uma ponta sem a outra deixa a lista
# sem onde ser preenchida — o e-mail simplesmente nunca sai.
mapa = CP.split('var FIELDS = {', 1)[1].split('};', 1)[0]
pares = dict(p.strip().split(': ') for p in mapa.replace('\n', ' ').split(',') if ': ' in p)
pares = {k.strip(): v.strip().strip("'") for k, v in pares.items()}
check('   e um campo de destinatário para cada lista',
      sorted(k for k in R._CE_REC_KEYS if k not in pares), [])
check('   com o input correspondente no DOM',
      sorted(i for i in pares.values() if ('id="%s"' % i) not in CP), [])
check('   e todos são modos que o servidor aceita',
      sorted(m for m in modos if m not in R._CE_MODES), [])
# A seção de cada card é o DOM, não um mapa card → grupo escrito à mão (que
# envelhecia calado quando um card mudava de seção). O que prende isso para
# TODOS os cards é o check_control_panel_sections; aqui basta o deste card.
_sec = CP.split('data-cp-card="confescalation"', 1)[0]
check('o card está dentro de uma seção do painel',
      _sec.rfind('data-cp-hdr=') > 0 and
      _sec.rfind('class="row g-3 g-xl-4 mb-4 cp-cards"') > _sec.rfind('data-cp-hdr='), True)

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
