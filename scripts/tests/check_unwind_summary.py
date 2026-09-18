# -*- coding: utf-8 -*-
"""check_unwind_summary.py — a recompra no Settlement Summary de NDF (§488).

A recompra liquida caixa como qualquer termo do dia, e a mesa ve o dia inteiro
numa tela so. O que este teste prende:

  1. entram as recompras que LIQUIDAM na data, DESDE O IMPORT (mesa,
     18/09/2026: a recompra que liquida hoje e caixa de hoje, e esperar o
     arquivo da B3 deixava o Summary do dia sem ela). A janela nao e so o dia:
     a recompra fica no arquivo-dia em que ENTROU e quem manda e a
     `SettlementDate`;
  2. o SINAL segue a convencao do Summary (negativo = o banco paga) e sai da
     `Direction` APURADA, nunca do campo do e-mail; sem direcao, a recompra
     fica de fora em vez de entrar com o sinal trocado;
  3. ela aparece no Trade Level com o veredito **None** — nao ha resgate da B3
     do outro lado, e "nao ha o que conferir" nao e "diverge";
  4. entra no Summary da contraparte (somando com as liquidacoes do dia);
  5. e fica FORA do `email_trades`: o aviso em lote sai de manha e a recompra
     chega durante o dia — o e-mail dela e processo separado;
  6. mas entra no IR do dia pela regra do piso MENSAL, que e o que faz a
     recompra da tarde ver o que a manha reteve.
"""
import os
import sys
import tempfile
from datetime import date, datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')
if os.name != 'nt' and not os.environ.get('OTC_SHARED_DRIVE_ROOT'):
    os.environ['OTC_SHARED_DRIVE_ROOT'] = tempfile.mkdtemp(prefix='otc-share-')

FALHAS = []


def check(nome, cond, extra=''):
    print(('  ok  ' if cond else ' FAIL ') + nome + (('  — ' + str(extra)) if (not cond and extra) else ''))
    if not cond:
        FALHAS.append(nome)


HOJE = date(2026, 9, 18)
BASE = {'AthenaID': 'STP-XE-1', 'Contract': '26C03202688', 'Currency': 'USD',
        'Counterparty': 'COFCO INTERNATIONAL BRASIL SA', 'TaxID': '02.916.265/0001-60',
        'UnwoundNotional': 42227.42, 'Balance': 587224.31, 'Result': 11144.00,
        'Direction': 'PAY', 'PartyAccount': '73760009', 'CptyAccount': '12345678',
        'TradeDate': '2026-04-01', 'MaturityDate': '2026-09-30',
        'SettlementDate': '2026-09-18', 'OriginalNotional': 587224.31,
        'Status': 'Sent'}


def main():
    from run import app  # noqa: F401
    from apps.pages import routes as R
    from apps.pages.features.unwinds import commands
    from apps.pages.features.unwinds.infra import persistence

    tmp = tempfile.mkdtemp(prefix='otc-unwsum-')
    persistence.cache_root = lambda: os.path.join(tmp, 'cache')
    persistence.cache_dir = lambda: os.path.join(tmp, 'cache', 'NDF', 'FX')
    commands._hoje = lambda: HOJE

    # A recompra fica no arquivo-dia de ONTEM e liquida HOJE: e o caso que a
    # janela de busca existe para cobrir.
    persistence.upsert(datetime(2026, 9, 17), [dict(BASE)])
    # Uma so IMPORTADA liquidando hoje (entra), uma enviada que liquida OUTRO
    # dia (nao entra) e uma sem direcao apurada (nao entra).
    persistence.upsert(datetime(2026, 9, 18), [
        dict(BASE, AthenaID='STP-NEW', Status='Imported'),
        dict(BASE, AthenaID='STP-AMANHA', SettlementDate='2026-09-21'),
        dict(BASE, AthenaID='STP-SEMDIR', Direction=''),
    ])

    print('\n== 1. quem entra no dia ==')
    rows = commands.settlement_rows(HOJE)
    ids = sorted(r['athena'] for r in rows)
    check('a recompra de ontem que liquida hoje entra', 'STP-XE-1' in ids, ids)
    # O gatilho e o IMPORT: a recompra que liquida hoje entra mesmo sem ter ido
    # para a B3. O que fica de fora nao e questao de status — e linha que
    # ninguem sabe somar, ou que liquida noutro dia.
    check('a ainda NAO enviada tambem entra (o gatilho e o import)',
          'STP-NEW' in ids, ids)
    check('a que liquida em outro dia NAO entra', 'STP-AMANHA' not in ids, ids)
    check('a sem direcao apurada fica de fora (em vez de entrar com o sinal trocado)',
          'STP-SEMDIR' not in ids, ids)
    check('e sao essas duas', len(rows) == 2, len(rows))

    print('\n== 2. o sinal segue a convencao do Summary ==')
    r = next(x for x in rows if x['athena'] == 'STP-XE-1')
    check('PAY -> negativo (o banco paga)', r['settlement'] == -11144.00, r['settlement'])
    check('a linha vem marcada como recompra', r.get('unwind') is True)
    # O mesmo resultado com a direcao trocada muda so o SINAL.
    persistence.upsert(datetime(2026, 9, 17), [dict(BASE, AthenaID='STP-XE-1',
                                                    Direction='RECEIVE')])
    rec = [x for x in commands.settlement_rows(HOJE) if x['athena'] == 'STP-XE-1']
    check('RECEIVE -> positivo', rec and rec[0]['settlement'] == 11144.00,
          rec[0]['settlement'] if rec else None)
    persistence.upsert(datetime(2026, 9, 17), [dict(BASE)])      # de volta ao PAY

    print('\n== 3. no Trade Level, no Summary e FORA do e-mail ==')
    with app.test_request_context():
        out = R._ndfsum_collect(datetime(2026, 9, 18))
    unw = [t for t in out['trade'] if t.get('unwind')]
    check('as duas recompras entraram no Trade Level', len(unw) == 2, len(unw))
    if unw:
        check('sem veredito (nao ha resgate da B3 para conferir)',
              all(u['ok'] is None for u in unw))
        check('e sem diferenca', all(u['diff'] == '' for u in unw))
        cells = unw[0]['cells']
        check('a celula do lado da B3 fica VAZIA', cells[10] == '', cells[10])
        check('o Athena ID e o B3 ID estao na linha',
              cells[2].startswith('STP-') and cells[3] == '26C03202688', cells[:4])
    cp = [s for s in out['summary'] if s['counterparty'] == BASE['Counterparty']]
    check('a contraparte aparece no Summary', bool(cp), [s['counterparty'] for s in out['summary']])
    if cp:
        # O banco paga: o caixa entra na coluna Pay, com o valor da recompra.
        # As duas sao da MESMA contraparte e do mesmo lado: o Summary soma —
        # 2 x 11.144,00 MENOS o IR retido das duas (R$ 0,56 cada), que e o que
        # a secao 4 explica.
        check('com o caixa das duas somado na coluna certa, liquido de IR',
              cp[0]['pay'] == '-22,286.88' and cp[0]['receive'] == '',
              (cp[0]['receive'], cp[0]['pay']))
        check('e a direcao do grupo e PAY', cp[0]['direction'] == 'PAY', cp[0]['direction'])
    check('e NENHUMA delas vai no aviso em lote',
          not any(t.get('unwind') for t in out['email_trades']))

    # A recompra tambem e PROJETADA no dia do Cockpit (a tela onde a mesa ve o
    # IR). O Summary tem de IGNORAR essa linha: lida dos dois lados, o mesmo
    # caixa sairia duas vezes no Trade Level e no IR do dia — o ledger monta o
    # dia inteiro de uma vez (§423).
    from apps.pages.features.unwinds import commands as _uc
    projetada = _uc._cockpit_rec(dict(BASE))
    _orig_load, _orig_collect = R._ndfc_load, R._ndfc_collect
    R._ndfc_load = lambda ref: ('jp', [projetada])
    R._ndfc_collect = lambda ref: {'rows': [
        [projetada.get(c, '') for c in R._NDFC_COLUMNS]
        + [projetada.get(k, '') for k in ('_nc_status', '_nc_maker', '_nc_checker', '_nc_id')]]}
    try:
        with app.test_request_context():
            out_ck = R._ndfsum_collect(datetime(2026, 9, 18))
    finally:
        R._ndfc_load, R._ndfc_collect = _orig_load, _orig_collect
    linhas_xe = [t for t in out_ck['trade'] if t['cells'][2] == 'STP-XE-1']
    check('a recompra projetada no Cockpit NAO entra duas vezes',
          len(linhas_xe) == 1, [t['cells'][2] for t in out_ck['trade']])
    check('e a que ficou e a da vertical (sem veredito)',
          linhas_xe and linhas_xe[0].get('unwind') is True and linhas_xe[0]['ok'] is None,
          linhas_xe[0] if linhas_xe else None)

    print('\n== 4. o IR do dia enxerga a recompra ==')
    # O IR incide sobre o ganho do CLIENTE (o banco pagando): 0,005% de
    # 11.144,00 = R$ 0,56 por recompra. O piso de R$ 1,00 e MENSAL e ACUMULADO
    # (§423): uma sozinha nao retem, as duas do dia somam 1,12 e cruzam o piso
    # — e e por isso que as duas aparecem com os R$ 0,56 delas.
    taxas = [t for t in out['trade'] if t.get('unwind')]
    check('duas de R$ 0,56 cruzam o piso MENSAL e as duas retem',
          [t['cells'][12] for t in taxas] == ['0.56', '0.56'],
          [t['cells'][12] for t in taxas])
    grande = dict(BASE, AthenaID='STP-BIG', Result=400000.0, Direction='PAY')
    persistence.upsert(datetime(2026, 9, 18), [grande])
    with app.test_request_context():
        out2 = R._ndfsum_collect(datetime(2026, 9, 18))
    big = [t for t in out2['trade'] if t.get('unwind') and t['cells'][2] == 'STP-BIG']
    check('acima do piso o IR da recompra e calculado e vai para a celula',
          bool(big) and big[0]['cells'][12] not in ('', None), big[0]['cells'][12] if big else None)

    print('\n' + ('tudo ok' if not FALHAS else 'FALHAS: ' + '; '.join(FALHAS)))
    return 1 if FALHAS else 0


if __name__ == '__main__':
    sys.exit(main())
