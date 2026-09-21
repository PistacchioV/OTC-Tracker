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
    # O IR mensal e ACUMULADO num ledger: sem redirecionar, este teste somaria
    # as recompras da fixture ao imposto de verdade da maquina.
    R._ndfsum_ir_ledger_path = lambda ref: os.path.join(
        tmp, 'ledger', 'ndf-ir-ledger_' + ref.strftime('%Y%m') + '.json')

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
        check('a celula do lado da B3 fica VAZIA', cells[11] == '', cells[11])
        # O Settlement Type vem logo a direita da COUNTERPARTY (21/09/2026), e a
        # recompra E o tipo `Unwind` — quem diz e a vertical, nao um evento da B3.
        check('o Settlement Type da recompra e Unwind', cells[2] == 'UNWIND', cells[:3])
        check('o Athena ID e o B3 ID estao na linha',
              cells[3].startswith('STP-') and cells[4] == '26C03202688', cells[:5])
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
    linhas_xe = [t for t in out_ck['trade'] if t['cells'][3] == 'STP-XE-1']
    check('a recompra projetada no Cockpit NAO entra duas vezes',
          len(linhas_xe) == 1, [t['cells'][3] for t in out_ck['trade']])
    check('e a que ficou e a da vertical (sem veredito)',
          linhas_xe and linhas_xe[0].get('unwind') is True and linhas_xe[0]['ok'] is None,
          linhas_xe[0] if linhas_xe else None)

    # ── 3b. o Settlement Type da linha COMUM do Cockpit (21/09/2026) ─────────
    # A linha em `Check` e justamente a que NAO tem resgate da B3 casado — e
    # era nela que o tipo saia vazio: a primeira versao so respondia Maturity
    # quando o vencimento da POSICAO era a data da tela, e o contrato cujo
    # vencimento na B3 e D+1 da liquidacao do Athena nao passava em nenhum dos
    # dois testes. Sem evento da B3, a linha do Cockpit e Maturity (o universo
    # dela e o getTradesBySettle); com evento, quem diz e o cadastro.
    comum = dict(projetada)
    comum.pop('_nc_unwind', None)
    comum.update({'ID_SOURCE_DEAL': 'STP-COMUM-1', 'CD_CETIP_RETURN': '26H04763424', '_nc_id': 'comum-1'})
    _o_load, _o_collect, _o_rows = R._ndfc_load, R._ndfc_collect, R._opb3_settle_rows
    R._ndfc_load = lambda ref: ('jp', [comum])
    R._ndfc_collect = lambda ref: {'rows': [
        [comum.get(c, '') for c in R._NDFC_COLUMNS]
        + [comum.get(k, '') for k in ('_nc_status', '_nc_maker', '_nc_checker', '_nc_id')]]}
    try:
        R._opb3_settle_rows = lambda ref: []
        with app.test_request_context():
            sem = [x for x in R._ndfsum_collect(datetime(2026, 9, 18))['trade']
                   if x['cells'][3] == 'STP-COMUM-1']
        check('linha do Cockpit SEM resgate da B3 (a que fica em Check) sai Maturity',
              bool(sem) and sem[0]['cells'][2] == 'MATURITY' and not sem[0]['ok'],
              sem[0]['cells'][:5] if sem else None)
        R._opb3_settle_rows = lambda ref: [{'Título': '26H04763424', 'Tipo Título': 'OPC',
                                            'Tipo Operação': 'PAGAMENTO DE PREMIO',
                                            'Status': 'FINALIZADA', 'Valor': '1,00'}]
        with app.test_request_context():
            com = [x for x in R._ndfsum_collect(datetime(2026, 9, 18))['trade']
                   if x['cells'][3] == 'STP-COMUM-1']
        check('e o evento da B3 VENCE o padrao quando existe',
              bool(com) and com[0]['cells'][2] == 'PREMIUM', com[0]['cells'][:5] if com else None)
    finally:
        R._ndfc_load, R._ndfc_collect, R._opb3_settle_rows = _o_load, _o_collect, _o_rows

    print('\n== 4. o IR do dia enxerga a recompra ==')
    # O IR incide sobre o ganho do CLIENTE (o banco pagando): 0,005% de
    # 11.144,00 = R$ 0,56 por recompra. O piso de R$ 1,00 e MENSAL e ACUMULADO
    # (§423): uma sozinha nao retem, as duas do dia somam 1,12 e cruzam o piso
    # — e e por isso que as duas aparecem com os R$ 0,56 delas.
    taxas = [t for t in out['trade'] if t.get('unwind')]
    check('duas de R$ 0,56 cruzam o piso MENSAL e as duas retem',
          [t['cells'][13] for t in taxas] == ['0.56', '0.56'],
          [t['cells'][13] for t in taxas])
    grande = dict(BASE, AthenaID='STP-BIG', Result=400000.0, Direction='PAY')
    persistence.upsert(datetime(2026, 9, 18), [grande])
    with app.test_request_context():
        out2 = R._ndfsum_collect(datetime(2026, 9, 18))
    big = [t for t in out2['trade'] if t.get('unwind') and t['cells'][3] == 'STP-BIG']
    check('acima do piso o IR da recompra e calculado e vai para a celula',
          bool(big) and big[0]['cells'][13] not in ('', None), big[0]['cells'][13] if big else None)

    print('\n' + ('tudo ok' if not FALHAS else 'FALHAS: ' + '; '.join(FALHAS)))
    return 1 if FALHAS else 0


if __name__ == '__main__':
    sys.exit(main())
