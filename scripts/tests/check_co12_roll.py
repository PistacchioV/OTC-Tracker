"""Ticker CO1-2 (Brent rolling): quais Datas de Verificacao sao do 2o futuro.

A confirmacao de Termo e de Opcao de Commodities nao imprime um codigo fixo para
o CO1-2: imprime uma frase dizendo, das Datas de Verificacao, quais valem o
PRIMEIRO futuro e quais valem o SEGUNDO. A regra e do calendario do Brent:

  * dezembro  -> as DUAS ultimas datas sao do segundo futuro;
  * demais    -> so a ULTIMA.

O codigo aplicava a regra de dezembro o ano inteiro, entao em qualquer outro mes
a penultima data saia apontada para o segundo futuro — um dia a mais de rolagem
do que a operacao tem, num documento que a contraparte assina.

O que este script protege:

  1. dezembro continua saindo EXATAMENTE como antes (a frase inteira, byte a
     byte) — a correcao nao podia mexer no mes que ja estava certo;
  2. os demais meses citam uma data so, no singular;
  3. o corte anda em dias UTEIS (fim de semana e feriado ANBIMA);
  4. os meses do futuro saem do SETTLEMENT (+1 e +2), com virada de ano;
  5. os dois builders de confirmacao usam a mesma funcao — a regra e do ativo,
     nao do produto.

Nao encosta em dado real: o calendario de feriados e stub.
"""
import io
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from apps.pages import routes as R                            # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


HOLIDAYS = set()
_orig = R._anbima_holidays
R._anbima_holidays = lambda: HOLIDAYS


def texto(fim, settle=None):
    return R._conf_co12_text({'FixingEndDate': fim,
                              'SettlementDate': settle or fim}, 1)


try:
    print('\n== 1. dezembro: as duas ultimas (comportamento historico) ==')
    # 31/12/2026 e quinta; 30 e quarta; 29 e terca.
    check('frase de dezembro, inteira', texto('31/12/2026'),
          'Para as Datas de Verificação entre a Data Inicial de Verificação de Mercadoria e '
          '29/12/2026 significa COF7 e para as Datas de Verificação em 30/12/2026 e '
          '31/12/2026, significa COG7')

    print('\n== 2. demais meses: so a ultima, no singular ==')
    # 31/08/2026 e segunda -> o dia util anterior e sexta, 28/08.
    check('frase de agosto, inteira', texto('31/08/2026'),
          'Para as Datas de Verificação entre a Data Inicial de Verificação de Mercadoria e '
          '28/08/2026 significa COU6 e para a Data de Verificação em 31/08/2026, significa COV6')
    check('agosto cita UMA data', texto('31/08/2026').count('/2026'), 2)
    check('dezembro cita DUAS', texto('31/12/2026').count('/2026'), 3)
    check('singular fora de dezembro', 'para a Data de Verificação em' in texto('31/08/2026'), True)
    check('plural em dezembro', 'para as Datas de Verificação em' in texto('31/12/2026'), True)
    # Janeiro e o outro extremo da virada: cai na regra de UM dia.
    check('janeiro usa um dia so',
          'para a Data de Verificação em 29/01/2027' in texto('29/01/2027'), True)

    print('\n== 3. o corte anda em dias UTEIS ==')
    # 03/08/2026 e segunda: o dia util anterior e sexta, 31/07.
    check('pula o fim de semana', '31/07/2026 significa' in texto('03/08/2026'), True)
    HOLIDAYS = {'2026-07-31'}
    R._anbima_holidays = lambda: HOLIDAYS
    check('pula o feriado tambem', '30/07/2026 significa' in texto('03/08/2026'), True)
    # Dezembro com feriado no dia util anterior: as duas datas do 2o futuro
    # passam a ser 29 e 31, e o corte recua para 28.
    HOLIDAYS = {'2026-12-30'}
    check('dezembro com feriado anda dois uteis',
          'e 28/12/2026 significa COF7 e para as Datas de Verificação em '
          '29/12/2026 e 31/12/2026' in texto('31/12/2026'), True)
    HOLIDAYS = set()

    print('\n== 4. os futuros saem do settlement (+1 e +2) ==')
    check('agosto -> setembro/outubro',
          ('COU6' in texto('31/08/2026'), 'COV6' in texto('31/08/2026')), (True, True))
    # Settlement em dezembro vira o ano: +1 = janeiro, +2 = fevereiro do ano seguinte.
    t = texto('20/12/2026', settle='31/12/2026')
    check('dezembro vira o ano', ('COF7' in t, 'COG7' in t), (True, True))
    # A data de verificacao e o settlement sao independentes: quem escolhe o
    # numero de datas e o FixingEndDate; quem escolhe o contrato e o settlement.
    t2 = texto('31/08/2026', settle='31/12/2026')
    check('mes das datas x mes do contrato',
          ('COF7' in t2 and 'para a Data de Verificação em 31/08/2026' in t2), True)

    print('\n== 5. sem data nao inventa frase ==')
    check('sem FixingEndDate', R._conf_co12_text({'SettlementDate': '31/08/2026'}, 1), 'CO1-2')
    check('sem SettlementDate', R._conf_co12_text({'FixingEndDate': '31/08/2026'}, 1), 'CO1-2')
    check('deal vazio', R._conf_co12_text({}, 1), 'CO1-2')
finally:
    R._anbima_holidays = _orig

print('\n== 6. os dois produtos usam a MESMA funcao ==')
src = io.open('apps/pages/routes.py', encoding='utf-8').read()
check('a regra existe uma vez so',
      src.count("if refd.month == 12:"), 1)
check('Termo chama', src.count("ticker = _conf_co12_text(deal, i)"), 2)
check('e o gatilho e o ativo, nos dois', src.count("if ua == 'CO1-2':"), 2)

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
