# -*- coding: utf-8 -*-
"""O e-mail `BRL NDF Unwind Notification` do Athena -> o registro da recompra.

Teste de CARACTERIZACAO: a fixture e o corpo HTML de um e-mail REAL
(`scripts/tests/fixtures/unwind-ndf-notification.html`, recebido em
10/09/2026). Ela existe porque o e-mail e HTML do Word, e sao os detalhes do
Word — nao a regra de negocio — que quebram o leitor:

  1. rotulo LONGO vem quebrado em duas linhas dentro da celula
     ('Calculated\\n  Termination Fee'): sem colapsar o branco ele nao casa com
     nada e o campo some sem erro;
  2. o titulo da tabela vem com espaco no FIM ('Before Unwind ');
  3. toda celula termina num `<o:p></o:p>` vazio e os espacos sao `&nbsp;`;
  4. o `id` das linhas (`row_0`...) REINICIA na segunda tabela — nao e chave;
  5. `<style>` e o comentario condicional do Office nao podem vazar texto.

E uma coisa que NAO e do Word e vale um teste proprio: a amostra traz
`Notional CCY = USB` num termo de USD/BRL. O dominio devolve como veio, de
proposito — traduzir codigo de moeda e cadastro (§6), nao literal no codigo.

Nao encosta em dado real: le a fixture e so.
"""
import datetime as _dt
import io
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from apps.pages.features.unwinds import domain                          # noqa: E402
from apps.pages.features.unwinds.infra import notification_html         # noqa: E402

FIXTURE = os.path.join(ROOT, 'scripts', 'tests', 'fixtures', 'unwind-ndf-notification.html')
HTML = io.open(FIXTURE, encoding='utf-8').read()
SUBJECT = 'BRL NDF Unwind Notification_STP-XE-10G5U5X-0-0_E5VL-3ICSK0W'

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


print('\n== 1. o leitor acha as duas tabelas ==')
tabelas = notification_html.tables(HTML)
check('quantas tabelas', len(tabelas), 2)
check('titulo 1 (sem o espaco do Word)', tabelas[0][0], ['Before Unwind'])
check('titulo 2', tabelas[1][0], ['After Unwind'])
check('linhas da 1a (titulo + cabecalho + 6 pares)', len(tabelas[0]), 8)
check('linhas da 2a (titulo + cabecalho + 13 pares)', len(tabelas[1]), 15)

print('\n== 2. o rotulo quebrado em duas linhas volta INTEIRO ==')
depois = dict(domain.secoes_das_tabelas(tabelas)[0]['after'])
check('rotulo remontado', 'Calculated Termination Fee' in depois, True)
check('valor dele', depois.get('Calculated Termination Fee'), '11,144.00')

print('\n== 3. style/comentario condicional nao vazam para as celulas ==')
todo = ' '.join(c for t in tabelas for l in t for c in l)
check('sem "Style Definitions"', 'Style Definitions' in todo, False)
check('sem "MsoNormal"', 'MsoNormal' in todo, False)
check('sem "WordDocument"', 'WordDocument' in todo, False)

print('\n== 4. o registro ==')
r = domain.parse_notification(notification_html.tables(HTML), SUBJECT)
check('athena id', r['athena_id'], 'STP-XE-10G5U5X-0-0')
check('o SEGUNDO id do assunto nao vira athena id', r['notification_id'], 'E5VL-3ICSK0W')
check('sem avisos', r['avisos'], [])
check('before/after', sorted(r['secoes']), ['after', 'before'])
antes = r['secoes']['before']
check('Trade Date', antes.get('Trade Date'), '2026-04-01')
check('Maturity Date', antes.get('Maturity Date'), '2026-09-30')
check('Notional', antes.get('Notional'), '78,000.00')
check('Strike', antes.get('Strike'), '5.3748')
dep = r['secoes']['after']
check('Unwind Type', dep.get('Unwind Type'), 'TOTAL')
check('Unwound Amount', dep.get('Unwound Amount'), '42,227.42')
check('Direction', dep.get('Direction'), 'RECEIVE')
check('Client', dep.get('Client'), 'MAXMIXBR-BR')
check('Xccy Rate zero e texto "0", nao vazio', dep.get('Xccy Rate'), '0')

print('\n== 5. o cabecalho Attribute|Value nao entra como par ==')
check('sem par Attribute', 'Attribute' in antes, False)
check('pares do before', len(r['pares']['before']), 6)
check('pares do after', len(r['pares']['after']), 13)
check('a ORDEM e preservada (e a que o aviso reproduz)',
      [a for a, _ in r['pares']['before']],
      ['Athena ID', 'Trade Date', 'Maturity Date', 'Notional', 'Notional CCY', 'Strike'])

print('\n== 6. numero americano ==')
for txt, exp in (('42,227.42', 42227.42), ('78,000.00', 78000.0), ('0', 0.0),
                 ('5.3748', 5.3748), ('', None), ('RECEIVE', None)):
    check('numero(%r)' % txt, domain.numero(txt), exp)

print('\n== 7. a moeda torta sobe COMO VEIO (quem traduz e cadastro) ==')
check('Notional CCY', antes.get('Notional CCY'), 'USB')

print('\n== 8. tabela que nao reconhecemos VIRA AVISO, nao silencio ==')
outro = HTML.replace('Before Unwind ', 'Something Else ')
r2 = domain.parse_notification(notification_html.tables(outro), SUBJECT)
codigos = [a['code'] for a in r2['avisos']]
check('avisa a tabela estranha', 'unwind_unknown_table' in codigos, True)
check('avisa a secao que faltou', 'unwind_missing_section' in codigos, True)
check('o athena id ainda sai do ASSUNTO', r2['athena_id'], 'STP-XE-10G5U5X-0-0')

print('\n== 9. tabela ANINHADA nao derrete na de fora ==')
aninhada = '<table><tr><td>x</td></tr><tr><td><table><tr><td>dentro</td></tr></table></td></tr></table>'
ts = notification_html.tables(aninhada)
check('duas tabelas', len(ts), 2)
check('a de dentro tem so a linha dela', ts[1], [['dentro']])

print('\n== 10. a ponte ate o contrato da B3 ==')
check('os 14 da direita', domain.identificador('STP-XE-10G5U5X-0-0'), 'XE-10G5U5X-0-0')
check('exatamente 14', len(domain.identificador('STP-XE-10G5U5X-0-0')), 14)
check('id curto volta inteiro (nao se inventa prefixo)', domain.identificador('AB-1'), 'AB-1')
POS = [{'Codigo Identificador': 'OUTRO-0-0', 'Contrato': '26C00000001'},
       {'Codigo Identificador': 'xe-10g5u5x-0-0', 'Contrato': '26C03202688'}]
check('acha o contrato (sem caixa)',
      domain.contrato_por_identificador(POS, 'STP-XE-10G5U5X-0-0')[0], '26C03202688')
check('sem linha -> (None, None)',
      domain.contrato_por_identificador(POS, 'STP-ZZ-0000000-0-0'), (None, None))
check('posicao sem Contrato preenchido -> None, nao string vazia',
      domain.contrato_por_identificador([{'Codigo Identificador': 'XE-10G5U5X-0-0', 'Contrato': '  '}],
                                        'STP-XE-10G5U5X-0-0')[0], None)

print('\n== 11. a prova real: UMA formula, tres operacoes reais ==')
# (rotulo, antes, depois, brl_fixed, banco comprado, resultado esperado, ME esperado)
CASOS = [
    ('USD 10/09/2026', {'Strike': '5.3748'},
     {'Unwound Amount': '42,227.42', 'Termination Rate': '5.109', 'Pre FWD Rate': '13.75',
      'DU': '14', 'Input Termination Fee': '11,144.00', 'Direction': 'RECEIVE'},
     False, False, 11144.00, 42227.42),
    ('BRL fixed #1', {'Strike': '5.2039'},
     {'Unwound Amount': '59,999.98', 'Termination Rate': '5.2077', 'Pre FWD Rate': '13.93',
      'DU': '45', 'Input Termination Fee': '42.80', 'Direction': 'PAY'},
     True, True, 42.80, 11529.81),
    ('BRL fixed #2', {'Strike': '5.2039'},
     {'Unwound Amount': '750,000.01', 'Termination Rate': '5.2067', 'Pre FWD Rate': '13.81',
      'DU': '23', 'Input Termination Fee': '398.81', 'Direction': 'PAY'},
     True, True, 398.81, 144122.68),
]
for rot, a, d, fx, cp, esperado, me_esp in CASOS:
    res = domain.conferir_apuracao(a, d, brl_fixed=fx, comprado=cp)
    check('%s fecha' % rot, res['conferido'], True)
    check('%s  resultado' % rot, round(res['resultado_calc'], 2), esperado)
    check('%s  nocional ME' % rot, round(res['notional_me'], 2), me_esp)

print('\n== 12. o nocional FIXO EM REAIS divide pelo strike ==')
check('59.999,98 / 5,2039', round(domain.notional_me({'Strike': '5.2039'},
      {'Unwound Amount': '59,999.98'}, True), 2), 11529.81)
check('sem BRL fixed NAO divide', domain.notional_me({'Strike': '5.2039'},
      {'Unwound Amount': '59,999.98'}, False), 59999.98)
check('strike zero nao explode', domain.notional_me({'Strike': '0'},
      {'Unwound Amount': '10'}, True), None)

print('\n== 13. o resultado e o Input Termination Fee, NUNCA o Present Value ==')
# No BRL fixed o aviso afirma Present Value -222,75 num caso cujo resultado e
# +42,80: copiar o Present Value mandaria ao cliente o valor E o sinal errados.
mentiroso = {'Input Termination Fee': '42.80', 'Present Value': '-222.75',
             'Calculated Termination Fee': '-222.75', 'Future Value': '-228.00'}
check('pega o Input Termination Fee', domain.resultado_apurado(mentiroso), 42.80)

print('\n== 14. a DIRECAO sai do sinal do resultado, nao do campo do aviso ==')
r13 = domain.conferir_apuracao(CASOS[1][1], CASOS[1][2], brl_fixed=True, comprado=True)
check('o aviso diz PAY', CASOS[1][2]['Direction'], 'PAY')
check('mas o banco RECEBE', r13['direcao_calc'], 'RECEIVE')
check('e isso vira aviso', 'unwind_direction_mismatch' in [x['code'] for x in r13['avisos']], True)
check('e NAO reprova a conta (a conta fecha)', r13['conferido'], True)

print('\n== 15. numero adulterado NAO passa ==')
for campo, valor in (('Input Termination Fee', '99,999.00'), ('Termination Rate', '5.9000'),
                     ('Unwound Amount', '42,999.42'), ('DU', '99')):
    ruim = dict(CASOS[0][2]); ruim[campo] = valor
    res = domain.conferir_apuracao(CASOS[0][1], ruim, brl_fixed=False, comprado=False)
    check('%s adulterado reprova' % campo, res['conferido'], False)
    check('  e diz que foi o resultado', 'unwind_result_mismatch' in [x['code'] for x in res['avisos']], True)

print('\n== 16. "nao da para conferir" NAO e "nao fecha" ==')
check('sem a posicao do banco -> None',
      domain.conferir_apuracao(CASOS[0][1], CASOS[0][2])['conferido'], None)
check('e diz o porque',
      domain.conferir_apuracao(CASOS[0][1], CASOS[0][2])['avisos'][0]['code'],
      'unwind_position_unknown')
falta = dict(CASOS[0][2]); falta.pop('DU')
check('parcela ausente -> None',
      domain.conferir_apuracao(CASOS[0][1], falta, comprado=False)['conferido'], None)

print('\n== 17. o SINAL vem da posicao, e inverte o resultado ==')
vendido = domain.conferir_apuracao(CASOS[1][1], CASOS[1][2], brl_fixed=True, comprado=False)
check('a mesma recompra com o banco VENDIDO inverte',
      round(vendido['resultado_calc'], 2), -42.80)
check('e ai a conta NAO fecha contra o fee informado', vendido['conferido'], False)

print('\n== 18. o marcador do nocional FIXO EM REAIS e o Notional CCY ==')
check('BRR e fixo em reais', domain.fixo_em_reais({'Notional CCY': 'BRR'}), True)
check('BRL tambem (se o Athena passar a mandar o ISO)',
      domain.fixo_em_reais({'Notional CCY': 'BRL'}), True)
check('USB nao e', domain.fixo_em_reais({'Notional CCY': 'USB'}), False)
check('vazio nao e', domain.fixo_em_reais({}), False)

print('\n== 19. o que a posicao entrega ao aviso ==')
POS = {'Contrato': '26C03202688', 'Simbolo da Moeda': 'USD',
       'Descricao da posicao do Participante': 'COMPRADOR',
       'Valor Base no registro': '587,224.31', 'Valor Antecipado': '155,652.49',
       # As duas contas saem da POSICAO: a recompra e de operacao ja
       # registrada, e a posicao carrega as contas como foram para a B3.
       'Codigo da Parte': '73760.00-9', 'Codigo da Contraparte': '41007',
       'Nome da Contraparte': 'COFCO INTERNATIONAL BRASIL SA',
       'CPF/CNPJ da Contraparte': '02916265000160'}
d = domain.dados_da_posicao(POS)
check('contrato', d['contrato'], '26C03202688')
check('moeda estrangeira (o e-mail so diz BRR)', d['moeda'], 'USD')
check('comprado', d['comprado'], True)
check('saldo = base - antecipado', round(d['saldo'], 2), 431571.82)
check('conta da PARTE, com os zeros', d['conta_parte'], '73760009')
check('conta da CONTRAPARTE (o Live Position entrega 41007, §487)',
      d['conta_contraparte'], '00041007')
check('nome da contraparte (o aviso nao precisa buscar por apelido)',
      d['nome_contraparte'], 'COFCO INTERNATIONAL BRASIL SA')
check('CPF/CNPJ da contraparte', d['taxid_contraparte'], '02916265000160')
check('sem avisos', d['avisos'], [])

print('\n== 20. o saldo confere com as DUAS recompras do mesmo Athena ID ==')
# 155.652,49 de Valor Antecipado = 11.529,81 + 144.122,68, que sao as duas
# recompras convertidas para USD. Se a conversao estivesse errada, nao fechava.
u1 = domain.notional_me({'Strike': '5.2039'}, {'Unwound Amount': '59,999.98'}, True)
u2 = domain.notional_me({'Strike': '5.2039'}, {'Unwound Amount': '750,000.01'}, True)
check('a soma das recompras e o Valor Antecipado', round(u1 + u2, 2), 155652.49)
check('e o Notional/Strike e o Valor Base no registro',
      round(domain.notional_original_me(
          {'Notional': '3,055,856.61', 'Strike': '5.2039', 'Notional CCY': 'BRR'}), 2), 587224.31)

print('\n== 21. numero da POSICAO le BR e US (o do e-mail e so US) ==')
for txt, exp in (('587,224.31', 587224.31), ('587.224,31', 587224.31), ('1,234', 1234.0),
                 ('1,5', 1.5), ('-222.75', -222.75), ('(222,75)', -222.75), ('', None)):
    check('numero_flex(%r)' % txt, domain.numero_flex(txt), exp)

print('\n== 22. o que falta na posicao VIRA AVISO, nunca palpite ==')
vazia = domain.dados_da_posicao({})
codigos = [a['code'] for a in vazia['avisos']]
for c in ('unwind_no_contract', 'unwind_no_currency', 'unwind_position_unknown', 'unwind_no_balance'):
    check('avisa %s' % c, c in codigos, True)
check('posicao com lado ilegivel -> None, nao False',
      domain.comprado_na_posicao({'Descricao da posicao do Participante': 'XYZ'}), None)

print('\n== 23. os valores do TER 0014 (secao 4.9.3, pag. 730-732) ==')
A = {'Notional': '3,055,856.61', 'Notional CCY': 'BRR', 'Strike': '5.2039'}
Dp = {'Unwound Amount': '750,000.01', 'Termination Rate': '5.2067', 'Pre FWD Rate': '13.81'}
campos, av = domain.campos_ter_0014(A, Dp, POS, _dt.date(2026, 8, 28),
                                    controle_interno='1001000100')
check('sem avisos com tudo resolvido', av, [])
check('5  Lançamento do Participante vem da POSICAO (conta OWN)',
      campos['Lançamento do Participante (Conta)'], '73760009')
check('7  Contraparte vem da POSICAO', campos['Contraparte'], '00041007')
check('6  Papel: comprado = 0', campos['Papel (Posição do participante)'], '0')
check('8  Contrato vem da posicao', campos['Contrato'], '26C03202688')
check('9  Valor Base a Antecipar em MOEDA ESTRANGEIRA',
      round(campos['Valor Base a Antecipar'], 2), 144122.68)
check('10 Data Antecipação = hoje', campos['Data Antecipação'], '20260828')
check('11 Data Liquidação = hoje', campos['Data Liquidação'], '20260828')
check('12 Taxa Termo = Termination Rate', campos['Taxa Termo'], 5.2067)
check('13 Taxa Juros = Pre FWD Rate', campos['Taxa Juros'], 13.81)
check('14 Taxa de Câmbio = 1 (o "000100000000" do layout)',
      campos['Taxa de Câmbio (R$/Moeda Cotada)'], 1.0)
check('15 Liquidante em branco (a mesa nao preenche)', campos['Liquidante'], '')
check('16 sem media -> 000', campos['Quantidade de Datas de Verificação'], '000')

print('\n== 24. campo que nao se pode responder e AVISO, nunca zero ==')
c2, a2 = domain.campos_ter_0014(A, Dp, {}, _dt.date(2026, 8, 28))
codigos = [x['code'] for x in a2]
for c in ('unwind_no_contract', 'unwind_position_unknown',
          'unwind_no_participant_account', 'unwind_no_counterparty_account'):
    check('avisa %s' % c, c in codigos, True)
check('Contrato ausente e None, nao ""', c2['Contrato'], None)
check('Papel ilegivel e None, nao "0"', c2['Papel (Posição do participante)'], None)

print('\n== 25. papel VENDIDO ==')
pos_v = dict(POS, **{'Descricao da posicao do Participante': 'VENDEDOR'})
cv, _ = domain.campos_ter_0014(A, Dp, pos_v, _dt.date(2026, 8, 28))
check('vendido = 1', cv['Papel (Posição do participante)'], '1')

print('\n== 26. campo 14: 1 em reais, paridade fora deles ==')
cm, am = domain.campos_ter_0014(A, Dp, POS, _dt.date(2026, 8, 28),
                                taxa_termo_em_brl=False, paridade=5.41)
check('taxa termo em USD -> vai a paridade USD/BRL',
      cm['Taxa de Câmbio (R$/Moeda Cotada)'], 5.41)
check('e nao avisa nada', [x['code'] for x in am], [])
cs, asem = domain.campos_ter_0014(A, Dp, POS, _dt.date(2026, 8, 28),
                                  taxa_termo_em_brl=False)
check('sem a paridade o campo fica None, nao 1',
      cs['Taxa de Câmbio (R$/Moeda Cotada)'], None)
check('e avisa', 'unwind_no_parity' in [x['code'] for x in asem], True)

print('')
if fails:
    print('FALHAS (%d): %s' % (len(fails), ', '.join(fails)))
    sys.exit(1)
print('tudo ok')
