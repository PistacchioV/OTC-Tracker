#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_ndf_asian_calendar.py — o calendário das datas de verificação do NDF
asiático (Vanilla, e o campo 59 das três páginas genéricas).

Uma operação de NDF Vanilla asiático foi à B3 com o 07/09/2026 (Independência)
como data de verificação. O deal da API chega SEM `FXHolidaySchedule` (o import
não o grava e o modal não o edita), e as linhas tipo 2 saíam de Seg–Sex puro;
o campo 59 (Quantidade de Datas de Verificação) contava pelo ANBIMA — o arquivo
declarava N datas e levava N+1 linhas. O que este script prende:

  1. sem calendário no deal, as datas saem no ANBIMA: o 07/09 fica de fora;
  2. o campo 59 é a contagem das MESMAS datas que viram linhas tipo 2;
  3. janela começando num feriado não conta o feriado (o `+1` contava);
  4. calendário que não se lê LEVANTA (ValueError com o nome) em vez de virar
     Seg–Sex calado;
  5. o preview das três páginas usa o mesmo padrão (ANBIMA, nome minúsculo).

Não toca em dado real: lê o calendário ANBIMA do checkout.
"""
import io
import os
import sys
from datetime import date

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', '/tmp/otc-share')
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')

from apps.pages import routes as R                            # noqa: E402

fails = []


def check(label, got, exp=True):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label +
          ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def deal(first, last, sched=''):
    return dict(Deal='NDFV-ASIAN-1', Client='ACME EXPORTADORA S.A.', LE='JPM',
                Status='Success', Direction='BUY', TaxID='12.345.678/0001-90',
                TradeDate='2026-08-03', SettlementDate='2026-09-15',
                FirstFixingDate=first, LastFixingDate=last, FXHolidaySchedule=sched,
                Publisher='PTAX', QuantityCurrency='USD', OtherQuantityCurrency='BRL',
                Notional='1,000,000.00', Rate='5.40000000', IsBRRFixed='NO')


def campo59(d):
    """O valor que o gerador entrega ao motor para o campo 59."""
    visto = {}
    orig = R._fi_build_line

    def espiao(key, block, values, *a, **k):
        if block == 'registro-dados-fixos':
            visto['59'] = values.get('59')
        return orig(key, block, values, *a, **k)
    R._fi_build_line = espiao
    try:
        R._generic_ndf_ter_line(dict(d), False, page_url='/new_deals-ndf-vanilla')
    finally:
        R._fi_build_line = orig
    return (visto.get('59') or '').strip()


check('o ANBIMA do checkout tem o 07/09/2026', '2026-09-07' in R._anbima_holidays())

print('== 1-2. sem calendário no deal: ANBIMA, e campo 59 = linhas ==')
d = deal('2026-09-01', '2026-09-10')
datas, _h = R._asian_verification_dates(d)
check('07/09/2026 NÃO é data de verificação', date(2026, 9, 7) in datas, False)
check('são 7 datas (01–10/09 menos o fim de semana e o feriado)', len(datas), 7)
linhas = R._vanilla_verification_lines(d, '/new_deals-ndf-vanilla',
                                       R._ter_le_pair(R._TER_BUCKET_LE['BANCO'], d['Client']))
check('linhas tipo 2 = datas', len(linhas), len(datas))
check('nenhuma linha carrega o 07/09', any('20260907' in l for l in linhas), False)
check('campo 59 = quantidade de linhas', campo59(d), '%03d' % len(linhas))

print('\n== 3. janela começando num feriado ==')
d2 = deal('2026-11-02', '2026-11-13')                 # 02/11 = Finados
check('Finados não conta: 9 datas', len(R._asian_verification_dates(d2)[0]), 9)
check('   e o campo 59 diz 009 (o +1 antigo dizia 010)', campo59(d2), '009')

print('\n== 4. calendário ilegível levanta ==')
try:
    R._asian_verification_dates(deal('2026-09-01', '2026-09-10', 'CALENDARIO-QUE-NAO-EXISTE'))
    check('calendário inexistente levanta', False)
except ValueError as exc:
    check('calendário inexistente levanta', 'calendario_que_nao_existe' in str(exc))
orig = R._anbima_holidays
R._anbima_holidays = lambda: set()
try:
    try:
        R._asian_verification_dates(deal('2026-09-01', '2026-09-10'))
        check('ANBIMA vazio (não lido) levanta, não vira Seg–Sex', False)
    except ValueError:
        check('ANBIMA vazio (não lido) levanta, não vira Seg–Sex', True)
finally:
    R._anbima_holidays = orig
check('fixing único (sem janela) não pede calendário',
      R._asian_verification_dates(deal('', '2026-09-10', 'NAO-EXISTE')), ([], set()))

print('\n== 5. o preview das três páginas ==')
for pg in ('vanilla', 'fwdstart', 'otherpublisher'):
    src = io.open(os.path.join(ROOT, 'apps/templates/pages/new_deals-ndf-%s.html' % pg),
                  encoding='utf-8').read()
    check('%s: sem calendário o preview usa o ANBIMA' % pg,
          "_sh(deal.FXHolidaySchedule || '') || 'ANBIMA'" in src)
    check('%s: e busca o arquivo em minúsculas, como o servidor' % pg,
          "replace(/-/g, '_').toLowerCase()) + '.json'" in src)

print()
if fails:
    print('FAILED: %d check(s)' % len(fails))
    sys.exit(1)
print('TUDO OK')
sys.exit(0)
